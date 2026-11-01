"""The tokens table — grants, and everything spent against one."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import MAX_QUESTION_ATTEMPTS, get_settings
from app.common.exceptions import (
    IdempotencyKeyReused,
    InvalidToken,
    QuotaExhausted,
    RetriesExhausted,
    TokenExpired,
    TokenRevoked,
)
from app.common.models import Grant
from app.common.models.utc import as_utc
from app.common.schemas import DatabaseQuestionKey, DatabaseToken
from app.repositories.base import SpentQuestion, TokenRepository
from app.repositories.sql._shared import _rowcount


class SQLTokenRepository(TokenRepository):
    """The tokens table, behind TokenRepository."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db

    async def add(self, grant: Grant) -> Grant:
        self.logger.debug(
            "Creating token entry in database",
            extra={
                "user_id": grant.user_id,
                "token_hash": grant.token_hash,
                "subject": grant.subject,
                "company": grant.company,
                "job_title": grant.job_title,
                "created_at": grant.created_at,
                "max_queries": grant.max_queries,
                "expires_at": grant.expires_at,
                "version": grant.version,
                "kind": grant.kind,
            },
        )
        row = DatabaseToken(
            id=grant.id,
            user_id=grant.user_id,
            subject=grant.subject,
            company=grant.company,
            job_title=grant.job_title,
            token_hash=grant.token_hash,
            max_queries=grant.max_queries,
            expires_at=grant.expires_at,
            created_at=grant.created_at,
            version=grant.version,
            kind=grant.kind,
            # Set at birth for a grant that is opened rather than claimed — a
            # trial is its own session from the start, with no link to spend.
            claimed_at=grant.claimed_at,
        )
        self.db.add(row)
        await self.db.flush()
        return Grant.model_validate(row)

    async def get(self, token_id: uuid.UUID) -> Grant | None:
        row = await self.db.get(DatabaseToken, token_id)
        return Grant.model_validate(row) if row is not None else None

    async def spend_question(
        self,
        token_id: uuid.UUID,
        key: uuid.UUID,
        message_hash: str,
        expected_version: int | None = None,
    ) -> SpentQuestion:
        self.logger.debug(
            "Updating token used query count",
            extra={"token_id": token_id, "expected_version": expected_version},
        )
        # The cheap answer for a retry. The primary key below still decides a
        # race; this only spares a retry an increment that would be rolled back.
        if await self._key_hash(token_id, key) is not None:
            return await self._retry(token_id, key, message_hash, expected_version)

        now = datetime.now(timezone.utc)
        # Atomic consume: increments used_queries only if the grant is still
        # valid (not revoked, not expired, under its query limit). This is what
        # avoids the read-then-write race a check in Python would have.
        predicates = [
            DatabaseToken.id == token_id,
            DatabaseToken.revoked_at.is_(None),
            DatabaseToken.expires_at > now,
            DatabaseToken.used_queries < DatabaseToken.max_queries,
        ]
        # Version is a predicate rather than a check on the returned row so that
        # a mismatch costs nothing: presenting a v1-shaped token against a v2
        # grant fails without first spending one of that grant's questions.
        if expected_version is not None:
            predicates.append(DatabaseToken.version == expected_version)

        result = await self.db.execute(
            update(DatabaseToken)
            .where(*predicates)
            .values(used_queries=DatabaseToken.used_queries + 1)
            .returning(DatabaseToken)
            # RETURNING is the only source of truth we want here. Left on
            # "evaluate", SQLAlchemy re-runs the expires_at predicate in Python
            # against any row already in the session, and a driver that drops
            # tzinfo on read (SQLite) makes that comparison raise. The row we
            # act on comes back from the DB, and populate_existing is what makes
            # it so when the session has already loaded that row.
            .execution_options(synchronize_session=False, populate_existing=True)
        )
        row: DatabaseToken | None = result.scalar_one_or_none()

        if row is None:
            await self.db.commit()
            # The grant exists but failed a condition above, or is not there at
            # all — read it back to say which, now the spend has been decided.
            raise await self._explain_failed_spend(token_id, expected_version, now)

        # The spend and the key are one transaction, and that is the whole
        # mechanism: a key without a spend would be a free question, and a spend
        # without a key would charge the retry.
        self.db.add(DatabaseQuestionKey(token_id=token_id, key=key, message_hash=message_hash))
        try:
            # Durable before returning: a spend the rest of the request could
            # undo is a free question, and an aborted stream would take every
            # one. A retry is free, but capped and tied to this one question.
            await self.db.commit()
        except IntegrityError:
            # A twin request won the race between the read above and here. This
            # rollback hands back the spend, and the twin's is the one that holds.
            await self.db.rollback()
            return await self._retry(token_id, key, message_hash, expected_version)

        grant = Grant.model_validate(row)
        self.logger.info(
            "Token updated",
            extra={
                "token_id": grant.id,
                "user_id": grant.user_id,
                "subject": grant.subject,
                "company": grant.company,
                "job_title": grant.job_title,
                "used_queries": grant.used_queries,
                "max_queries": grant.max_queries,
                "expires_at": grant.expires_at,
                "created_at": grant.created_at,
            },
        )
        return SpentQuestion(grant=grant)

    async def _key_hash(self, token_id: uuid.UUID, key: uuid.UUID) -> str | None:
        result = await self.db.execute(
            select(DatabaseQuestionKey.message_hash).where(
                DatabaseQuestionKey.token_id == token_id,
                DatabaseQuestionKey.key == key,
            )
        )
        return result.scalar_one_or_none()

    async def _retry(
        self,
        token_id: uuid.UUID,
        key: uuid.UUID,
        message_hash: str,
        expected_version: int | None,
    ) -> SpentQuestion:
        """
        Another attempt at a question already paid for. Spends nothing.

        Everything a spend checks except the allowance: a revoked link stays
        revoked, but the question that failed may have been the last one.
        """
        if await self._key_hash(token_id, key) != message_hash:
            self.logger.warning("Idempotency key reused", extra={"token_id": token_id})
            raise IdempotencyKeyReused()

        now = datetime.now(timezone.utc)
        refusal = await self._dead_grant(token_id, expected_version, now)
        if refusal is not None:
            raise refusal

        # The cap, held by one statement, like the spend: two retries racing for
        # the last attempt cannot both get it.
        result = await self.db.execute(
            update(DatabaseQuestionKey)
            .where(
                DatabaseQuestionKey.token_id == token_id,
                DatabaseQuestionKey.key == key,
                DatabaseQuestionKey.attempts < MAX_QUESTION_ATTEMPTS,
            )
            .values(attempts=DatabaseQuestionKey.attempts + 1)
            .returning(DatabaseQuestionKey.conversation_id)
            .execution_options(synchronize_session=False)
        )
        taken = result.first()
        await self.db.commit()
        if taken is None:
            self.logger.warning("Question out of retries", extra={"token_id": token_id})
            raise RetriesExhausted()

        grant = await self.get(token_id)
        # `_dead_grant` has just read it, and nothing here deletes a grant.
        assert grant is not None
        return SpentQuestion(grant=grant, conversation_id=taken.conversation_id)

    async def _explain_failed_spend(
        self, token_id: uuid.UUID, expected_version: int | None, now: datetime
    ) -> Exception:
        """
        Which of the spend's conditions was the one that failed.

        Returned rather than raised so the caller's `raise` keeps the traceback
        pointing at the spend. A live grant that could not pay is an exhausted one.
        """
        return await self._dead_grant(token_id, expected_version, now) or QuotaExhausted()

    async def _dead_grant(
        self, token_id: uuid.UUID, expected_version: int | None, now: datetime
    ) -> Exception | None:
        """
        What is wrong with this grant, whatever its allowance, or None. Order
        matters: revoked before expired, so the most specific reason wins.
        """
        # Read fresh: the spend's UPDATE deliberately does not touch rows already
        # in the session, and this is the read that has to see what is true.
        existing = await self.db.get(DatabaseToken, token_id, populate_existing=True)
        if existing is None:
            self.logger.warning("Invalid token", extra={"token_id": token_id})
            return InvalidToken()
        if existing.revoked_at is not None:
            self.logger.warning("Revoked token", extra={"token_id": token_id})
            return TokenRevoked()
        if expected_version is not None and existing.version != expected_version:
            self.logger.warning(
                "Token version does not match its grant",
                extra={
                    "token_id": token_id,
                    "expected_version": expected_version,
                    "version": existing.version,
                },
            )
            return InvalidToken()
        if as_utc(existing.expires_at) <= now:
            self.logger.warning("Expired token", extra={"token_id": token_id})
            return TokenExpired()
        return None

    async def claim_once(self, token_id: uuid.UUID) -> bool:
        # The `claimed_at IS NULL` predicate is the whole mechanism — two
        # requests arriving together cannot both match it, so a claim link opens
        # exactly one session no matter how it is raced.
        result = await self.db.execute(
            update(DatabaseToken)
            .where(DatabaseToken.id == token_id, DatabaseToken.claimed_at.is_(None))
            .values(claimed_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        return bool(_rowcount(result))

    async def mark_owner_notified(self, token_id: uuid.UUID) -> bool:
        # Same gate shape as claim_once, and for the same reason: a dead link
        # hit in a loop must produce one message, not one per request. The
        # window predicate lives in SQL so concurrent requests cannot both win.
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=get_settings().owner_notify_throttle_seconds)
        result = await self.db.execute(
            update(DatabaseToken)
            .where(
                DatabaseToken.id == token_id,
                or_(
                    DatabaseToken.owner_notified_at.is_(None),
                    DatabaseToken.owner_notified_at < cutoff,
                ),
            )
            .values(owner_notified_at=now)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        return bool(_rowcount(result))

    async def revoke(self, token_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            update(DatabaseToken)
            .where(DatabaseToken.id == token_id, DatabaseToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        # Read the rowcount before committing: whether this call was the one
        # that revoked is the answer, and a commit discards the result.
        already_revoked = not _rowcount(result)
        await self.db.commit()
        return already_revoked
