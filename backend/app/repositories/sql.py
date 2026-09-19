"""
The SQLAlchemy backend.

This is the only module in the app that both names SQLAlchemy and is reachable
from a route. Everything above it depends on `app.repositories.base`, so a
second backend means a second module shaped like this one and a one-line change
in `app/repositories/__init__.py` — not an edit to any route or service.

Note where the session is declared: on the providers at the bottom, inside the
backend. A backend that needs no session, or a different one, declares its own
dependencies there, and the route asking for a repository is unaffected either
way.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from fastapi import Depends
from sqlalchemy import CursorResult, Result, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.common.config import (
    OWNER_NOTIFY_THROTTLE_SECONDS,
    REFRESH_ROTATION_GRACE_SECONDS,
)
from app.common.db import get_db, get_session_factory, transaction
from app.common.exceptions import (
    InvalidRefreshToken,
    InvalidToken,
    QuotaExhausted,
    RefreshTokenExpired,
    RefreshTokenReplayed,
    RotationInProgress,
    SessionRevoked,
    TokenExpired,
    TokenRevoked,
)
from app.common.models import (
    ChatMessage,
    Conversation,
    ConversationPreview,
    Grant,
    RefreshSession,
    User,
)
from app.common.models.utc import as_utc
from app.common.schemas import (
    DatabaseChatMessage,
    DatabaseConversation,
    DatabaseRefreshToken,
    DatabaseToken,
    DatabaseUser,
)
from app.repositories.base import (
    ConversationRepositoryBase,
    ReplyOutcome,
    SessionRepositoryBase,
    TranscriptRepositoryBase,
    TokenRepositoryBase,
    UserRepositoryBase,
)


def _rowcount(result: Result[Any]) -> int:
    """
    How many rows a statement touched.

    `session.execute()` is typed as returning `Result`, which has no `rowcount`;
    a DML statement actually returns a `CursorResult`, which does. Narrowing it
    once here beats a cast at each of the half-dozen call sites, and puts the
    reason in one place rather than none.
    """
    return cast("CursorResult[Any]", result).rowcount


class SQLUserRepository(UserRepositoryBase):
    """The users table, behind UserRepositoryBase."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db

    async def get_by_name(self, name: str) -> User | None:
        self.logger.debug("Checking if user (company) exists", extra={"company (name)": name})
        result = await self.db.execute(select(DatabaseUser).where(DatabaseUser.name == name))
        row = result.scalar_one_or_none()
        if row is None:
            self.logger.info("User does not exist", extra={"company (name)": name})
            return None
        user = User.model_validate(row)
        self.logger.info(
            "User exists",
            extra={
                "id": user.id, "company (name)": user.name,
                "email": user.email, "phone": user.phone,
            },
        )
        return user

    async def add(self, name: str, email: str | None, phone: str | None) -> User:
        # Lower-cased on the way in and on the way out of get_by_name, so a
        # lookup and the row it would have matched agree on spelling.
        email = email.lower() if email else None
        self.logger.info(
            "Creating new user",
            extra={"company (name)": name, "email": email, "phone": phone},
        )
        row = DatabaseUser(name=name, email=email, phone=phone)
        self.db.add(row)
        # Flush, not commit: this assigns row.id so the grant can reference it,
        # while leaving the transaction for the request scope to close.
        await self.db.flush()
        user = User.model_validate(row)
        self.logger.debug(
            "Changes flushed to database: user assigned with user.id without ending the transaction",
            extra={
                "id": user.id, "company (name)": user.name,
                "email": user.email, "phone": user.phone,
            },
        )
        return user


class SQLTokenRepository(TokenRepositoryBase):
    """The tokens table, behind TokenRepositoryBase."""

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


class SQLSessionRepository(SessionRepositoryBase):
    """The refresh_tokens table, behind SessionRepositoryBase."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db

    async def get(self, session_id: uuid.UUID) -> RefreshSession | None:
        row = await self.db.get(DatabaseRefreshToken, session_id)
        return RefreshSession.model_validate(row) if row is not None else None

    async def add(self, session: RefreshSession) -> RefreshSession:
        row = self._row(session)
        self.db.add(row)
        await self.db.flush()
        self.logger.info(
            "Opened refresh session",
            extra={"refresh_id": row.id, "token_id": row.token_id},
        )
        return RefreshSession.model_validate(row)

    @staticmethod
    def _row(session: RefreshSession) -> DatabaseRefreshToken:
        return DatabaseRefreshToken(
            id=session.id,
            token_id=session.token_id,
            token_hash=session.token_hash,
            expires_at=session.expires_at,
        )

    async def rotate(
        self, session_id: uuid.UUID, successor: RefreshSession
    ) -> RefreshSession:
        now = datetime.now(timezone.utc)

        existing = await self.db.get(DatabaseRefreshToken, session_id)
        if existing is None:
            self.logger.warning("Unknown refresh token", extra={"refresh_id": session_id})
            raise InvalidRefreshToken()

        # The successor is inserted *before* the predecessor is claimed so that
        # rotated_to has something to point at — the FK is checked immediately,
        # not deferred. If the claiming UPDATE then matches nothing, the
        # rollback takes this insert with it and a lost race leaves no orphan.
        row = self._row(successor)
        self.db.add(row)
        await self.db.flush()

        result = await self.db.execute(
            update(DatabaseRefreshToken)
            .where(
                DatabaseRefreshToken.id == session_id,
                DatabaseRefreshToken.revoked_at.is_(None),
                DatabaseRefreshToken.expires_at > now,
            )
            .values(revoked_at=now, last_used_at=now, rotated_to=successor.id)
            .execution_options(synchronize_session=False)
        )

        if not _rowcount(result):
            await self.db.rollback()
            raise await self._explain_failed_rotation(session_id, now)

        # Durable before returning: the client is handed this successor, so a
        # rotation the rest of the request could undo would leave it holding a
        # token the store has never seen.
        await self.db.commit()
        rotated = RefreshSession.model_validate(row)
        self.logger.info(
            "Rotated refresh token",
            extra={
                "refresh_id": session_id,
                "successor_id": rotated.id,
                "token_id": rotated.token_id,
            },
        )
        return rotated

    async def _explain_failed_rotation(
        self, session_id: uuid.UUID, now: datetime
    ) -> Exception:
        """
        Why the claiming UPDATE matched nothing — and, for a replay, the
        response to it.

        Runs after the rollback, so everything it reads is re-read from the
        store rather than remembered from before.
        """
        stale = await self.db.get(DatabaseRefreshToken, session_id)
        if stale is None or stale.revoked_at is None:
            self.logger.warning("Expired refresh token", extra={"refresh_id": session_id})
            return RefreshTokenExpired()

        if stale.rotated_to is None:
            # Revoked without a successor: an operator cut this grant, or replay
            # detection did. Not a replay in itself, and re-cutting adds nothing.
            self.logger.warning(
                "Refresh token belongs to a revoked session",
                extra={"refresh_id": session_id},
            )
            return SessionRevoked()

        rotated_ago = (now - (as_utc(stale.revoked_at) or now)).total_seconds()
        if rotated_ago <= REFRESH_ROTATION_GRACE_SECONDS:
            # This client racing itself, not an attacker: parallel requests that
            # all expired at once, or a retry after a network flake. Rejecting
            # without cutting keeps the winner's session — cutting here would
            # take down the pair just handed out and log the hirer out of their
            # own tab.
            self.logger.info(
                "Refresh token re-presented inside the rotation grace window",
                extra={"refresh_id": session_id, "rotated_ago_s": round(rotated_ago, 3)},
            )
            return RotationInProgress()

        self.logger.warning(
            "Refresh token replayed after rotation, cutting the grant's sessions",
            extra={
                "refresh_id": session_id,
                "token_id": stale.token_id,
                "rotated_ago_s": round(rotated_ago, 3),
            },
        )
        token_id = stale.token_id
        await self.revoke_all_for_grant(token_id)
        return RefreshTokenReplayed(token_id)

    async def revoke_all_for_grant(self, token_id: uuid.UUID) -> int:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(DatabaseRefreshToken)
            .where(
                DatabaseRefreshToken.token_id == token_id,
                DatabaseRefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .execution_options(synchronize_session=False)
        )
        revoked = _rowcount(result) or 0
        await self.db.commit()
        self.logger.warning(
            "Revoked refresh sessions", extra={"token_id": token_id, "count": revoked}
        )
        return revoked


# Column bounds. Guards against these and the ChatRequest bound drifting apart
# and raising into a user's chat.
MAX_CONTENT_CHARS = 16000
MAX_ERROR_CHARS = 255
MAX_TOOL_NAMES_CHARS = 255


def _truncate(text: str | None, limit: int) -> tuple[str | None, int]:
    """Returns (clipped_text, truncated_flag)."""
    if text is None:
        return None, 0
    if len(text) <= limit:
        return text, 0
    return text[:limit], 1


class SQLTranscriptRepository(TranscriptRepositoryBase):
    """
    Chat transcript capture, over its own session.

    Takes the factory rather than a session because it has to outlive the
    request: on client abort the request's session is already closed by the time
    the recorder runs.
    """

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__()
        self.factory = factory

    async def record_question(
        self,
        token_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        message: str,
        endpoint: str,
        request_id: str,
    ) -> uuid.UUID:
        content, truncated = _truncate(message, MAX_CONTENT_CHARS)
        async with transaction(self.factory) as db:
            resolved = await self._resolve_conversation(conversation_id, token_id, db)
            db.add(
                DatabaseChatMessage(
                    conversation_id=resolved,
                    token_id=token_id,
                    request_id=request_id,
                    role="user",
                    content=content,
                    # Pre-truncation length, so the size signal survives both
                    # clipping here and redaction later.
                    content_chars=len(message),
                    truncated=truncated,
                    endpoint=endpoint,
                    status="received",
                )
            )
            await self._bump(resolved, db)
        self.logger.info(
            "Recorded user message",
            extra={
                "conversation_id": resolved,
                "request_id": request_id,
                "content_chars": len(message),
            },
        )
        return resolved

    async def record_reply(
        self,
        token_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reply: str,
        endpoint: str,
        request_id: str,
        outcome: ReplyOutcome,
    ) -> None:
        content, truncated = _truncate(reply, MAX_CONTENT_CHARS)
        names, _ = _truncate(",".join(outcome.tool_names) or None, MAX_TOOL_NAMES_CHARS)
        error_text, _ = _truncate(outcome.error, MAX_ERROR_CHARS)

        async with transaction(self.factory) as db:
            db.add(
                DatabaseChatMessage(
                    conversation_id=conversation_id,
                    token_id=token_id,
                    request_id=request_id,
                    role="assistant",
                    content=content,
                    content_chars=len(reply or ""),
                    truncated=truncated,
                    endpoint=endpoint,
                    status=outcome.status,
                    finish_reason=outcome.finish_reason,
                    tool_calls_count=outcome.tool_calls_count,
                    tool_names=names,
                    model=outcome.model,
                    latency_ms=outcome.latency_ms,
                    error=error_text,
                )
            )
            await self._bump(conversation_id, db)
        self.logger.info(
            "Recorded assistant message",
            extra={
                "conversation_id": conversation_id,
                "request_id": request_id,
                "status": outcome.status,
                "latency_ms": outcome.latency_ms,
                "content_chars": len(reply or ""),
            },
        )

    @staticmethod
    async def _bump(conversation_id: uuid.UUID, db: AsyncSession) -> None:
        """
        Count the turn, in SQL.

        The increment is computed by the database rather than in Python: two
        turns landing together would otherwise both read the same count and one
        would overwrite the other. It also saves loading the row at all, which
        matters here because each recorder opens a fresh session and so can
        never have it already.
        """
        await db.execute(
            update(DatabaseConversation)
            .where(DatabaseConversation.id == conversation_id)
            .values(
                message_count=DatabaseConversation.message_count + 1,
                last_message_at=datetime.now(timezone.utc),
            )
            .execution_options(synchronize_session=False)
        )

    async def _resolve_conversation(
        self, conversation_id: uuid.UUID | None, token_id: uuid.UUID, db: AsyncSession
    ) -> uuid.UUID:
        """
        Reuse the caller's conversation when it is genuinely theirs, otherwise
        mint one.

        The token_id predicate is load-bearing: without it any bearer could
        append into another hirer's conversation just by guessing an id. A
        mismatch is never an error — a bad correlation id must not break
        someone's chat — it simply starts a new conversation.
        """
        if conversation_id is not None:
            existing = (
                await db.execute(
                    select(DatabaseConversation.id).where(
                        DatabaseConversation.id == conversation_id,
                        DatabaseConversation.token_id == token_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing
            self.logger.warning(
                "Conversation id not found for this token, starting a new conversation",
                extra={"conversation_id": conversation_id, "token_id": token_id},
            )

        # Only now is the grant needed — for the snapshot columns. On the reuse
        # path above it is never read, which is why this is not fetched upfront.
        grant = await db.get(DatabaseToken, token_id)
        if grant is None:
            raise InvalidToken()

        conversation = DatabaseConversation(
            token_id=grant.id,
            user_id=grant.user_id,
            # Snapshots, not references: these still read correctly after the
            # grant behind them is rotated or revoked.
            subject=grant.subject,
            company=grant.company,
            job_title=grant.job_title,
        )
        db.add(conversation)
        await db.flush()
        self.logger.info(
            "Started new conversation",
            extra={"conversation_id": conversation.id, "token_id": token_id},
        )
        return conversation.id


class SQLConversationRepository(ConversationRepositoryBase):
    """The conversations and chat_messages tables, read side."""

    PREVIEW_CHARS = 120
    REPLY_PREVIEW_CHARS = 200

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db

    async def list_previews(
        self,
        limit: int = 50,
        offset: int = 0,
        company: str | None = None,
        since: datetime | None = None,
    ) -> list[ConversationPreview]:
        self.logger.debug(
            "Listing conversations",
            extra={"limit": limit, "offset": offset, "company": company, "since": since},
        )

        stmt = select(DatabaseConversation)
        if company:
            stmt = stmt.where(DatabaseConversation.company == company)
        if since:
            stmt = stmt.where(DatabaseConversation.created_at >= since)
        stmt = (
            stmt.order_by(
                DatabaseConversation.last_message_at.desc().nullslast(),
                DatabaseConversation.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        conversations = (await self.db.execute(stmt)).scalars().all()
        if not conversations:
            return []

        previews = await self._previews_for([c.id for c in conversations])
        return [
            ConversationPreview(
                **Conversation.model_validate(conversation).model_dump(),
                preview=previews.get((conversation.id, "user")),
                reply_preview=previews.get((conversation.id, "assistant")),
            )
            for conversation in conversations
        ]

    async def _previews_for(
        self, conversation_ids: list[uuid.UUID]
    ) -> dict[tuple[uuid.UUID, str], str | None]:
        """
        The opening question and the latest reply for each conversation, in one
        query rather than two per row.

        A window function rather than `DISTINCT ON`, which is Postgres-only —
        the tests run on SQLite, so a Postgres-only statement would only fail in
        production.

        Both ranks are computed and then selected from, rather than one rank
        over a conditional sort: a CASE cannot carry ASC/DESC, so a single
        direction-switching ORDER BY is not expressible. The first question is
        what was asked, and the *last* reply is where the thread ended up —
        which is what catches the agent answering wrongly.
        """
        window = (DatabaseChatMessage.conversation_id, DatabaseChatMessage.role)
        ranked = (
            select(
                DatabaseChatMessage.conversation_id,
                DatabaseChatMessage.role,
                DatabaseChatMessage.content,
                func.row_number()
                .over(partition_by=window, order_by=DatabaseChatMessage.created_at.asc())
                .label("first_rank"),
                func.row_number()
                .over(partition_by=window, order_by=DatabaseChatMessage.created_at.desc())
                .label("last_rank"),
            )
            .where(
                DatabaseChatMessage.conversation_id.in_(conversation_ids),
                DatabaseChatMessage.role.in_(("user", "assistant")),
            )
            .subquery()
        )
        rows = (
            await self.db.execute(
                select(ranked.c.conversation_id, ranked.c.role, ranked.c.content).where(
                    or_(
                        and_(ranked.c.role == "user", ranked.c.first_rank == 1),
                        and_(ranked.c.role == "assistant", ranked.c.last_rank == 1),
                    )
                )
            )
        ).all()

        limits = {"user": self.PREVIEW_CHARS, "assistant": self.REPLY_PREVIEW_CHARS}
        return {
            (conversation_id, role): (content[: limits[role]] if content else None)
            for conversation_id, role, content in rows
        }

    async def get_with_messages(
        self, conversation_id: uuid.UUID
    ) -> tuple[Conversation | None, list[ChatMessage]]:
        self.logger.debug("Fetching conversation", extra={"conversation_id": conversation_id})
        row = await self.db.get(DatabaseConversation, conversation_id)
        if row is None:
            return None, []

        messages = (
            await self.db.execute(
                select(DatabaseChatMessage)
                .where(DatabaseChatMessage.conversation_id == conversation_id)
                .order_by(DatabaseChatMessage.created_at.asc())
            )
        ).scalars().all()
        return (
            Conversation.model_validate(row),
            [ChatMessage.model_validate(m) for m in messages],
        )

    async def exists(self, conversation_id: uuid.UUID) -> bool:
        # Selecting the id rather than the row: the callers that ask this are
        # answering a 404, and loading a transcript to do it would pull every
        # message body back for nothing.
        found = (
            await self.db.execute(
                select(DatabaseConversation.id).where(
                    DatabaseConversation.id == conversation_id
                )
            )
        ).scalar_one_or_none()
        return found is not None

    async def redact(self, conversation_id: uuid.UUID) -> int:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(DatabaseChatMessage)
            .where(
                DatabaseChatMessage.conversation_id == conversation_id,
                DatabaseChatMessage.content.is_not(None),
            )
            .values(content=None, redacted_at=now)
            .execution_options(synchronize_session=False)
        )
        redacted = _rowcount(result) or 0
        await self.db.execute(
            update(DatabaseConversation)
            .where(DatabaseConversation.id == conversation_id)
            .values(redacted_at=now)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        self.logger.warning(
            "Redacted conversation",
            extra={"conversation_id": conversation_id, "messages_redacted": redacted},
        )
        return redacted


def provide_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepositoryBase:
    """
    Annotated with the abstraction, not the class, so a caller asking for this
    by `Depends` is typed against the base and can be handed any backend.
    """
    return SQLUserRepository(db=db)


def provide_token_repository(db: AsyncSession = Depends(get_db)) -> TokenRepositoryBase:
    # FastAPI caches `Depends(get_db)` for the life of a request, so this
    # repository and the user one above are handed the *same* session, and
    # therefore the same transaction. That is what keeps issuing a token atomic
    # without anything above this module knowing a transaction exists.
    return SQLTokenRepository(db=db)


def provide_session_repository(db: AsyncSession = Depends(get_db)) -> SessionRepositoryBase:
    return SQLSessionRepository(db=db)


def provide_transcript_repository(
    factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> TranscriptRepositoryBase:
    # The factory, not a session: this repository has to still work after the
    # request that created it has torn down.
    return SQLTranscriptRepository(factory=factory)


def provide_conversation_repository(
    db: AsyncSession = Depends(get_db),
) -> ConversationRepositoryBase:
    return SQLConversationRepository(db=db)
