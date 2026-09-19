"""The tokens table — grants, and everything spent against one."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import OWNER_NOTIFY_THROTTLE_SECONDS
from app.common.exceptions import (
    InvalidToken,
    QuotaExhausted,
    TokenExpired,
    TokenRevoked,
)
from app.common.models import Grant
from app.common.models.utc import as_utc
from app.common.schemas import DatabaseToken
from app.repositories.base import TokenRepository
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
        )
        self.db.add(row)
        await self.db.flush()
        return Grant.model_validate(row)

    async def get(self, token_id: uuid.UUID) -> Grant | None:
        row = await self.db.get(DatabaseToken, token_id)
        return Grant.model_validate(row) if row is not None else None

    async def consume_query(
        self, token_id: uuid.UUID, expected_version: int | None = None
    ) -> Grant:
        self.logger.debug(
            "Updating token used query count",
            extra={"token_id": token_id, "expected_version": expected_version},
        )
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
            # act on comes back from the DB.
            .execution_options(synchronize_session=False)
        )
        row: DatabaseToken | None = result.scalar_one_or_none()
        # Durable before returning: a spend the rest of the request could undo
        # is a free question, and an aborted stream would take every one.
        await self.db.commit()

        if row is None:
            # The grant exists but failed a condition above, or is not there at
            # all — read it back to say which, now the spend has been decided.
            raise await self._explain_failed_spend(token_id, expected_version, now)

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
        return grant

    async def _explain_failed_spend(
        self, token_id: uuid.UUID, expected_version: int | None, now: datetime
    ) -> Exception:
        """
        Which of the spend's conditions was the one that failed.

        Returned rather than raised so the caller's `raise` keeps the traceback
        pointing at the spend. Order matters: revoked before expired before
        exhausted, so the most specific reason wins.
        """
        existing = await self.db.get(DatabaseToken, token_id)
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
        return QuotaExhausted()

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
        cutoff = now - timedelta(seconds=OWNER_NOTIFY_THROTTLE_SECONDS)
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
