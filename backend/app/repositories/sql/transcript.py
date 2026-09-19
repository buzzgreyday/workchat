"""
Capturing a transcript — the write half of conversations and chat_messages.

Split from `conversation` by session ownership rather than by table: this one
has to outlive the request that started it, and that difference is the whole
reason it exists separately.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.common.db import transaction
from app.common.exceptions import InvalidToken
from app.common.schemas import (
    DatabaseChatMessage,
    DatabaseConversation,
    DatabaseToken,
)
from app.repositories.base import ReplyOutcome, TranscriptRepository
from app.repositories.sql._shared import (
    MAX_CONTENT_CHARS,
    MAX_ERROR_CHARS,
    MAX_TOOL_NAMES_CHARS,
    _truncate,
)


class SQLTranscriptRepository(TranscriptRepository):
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
