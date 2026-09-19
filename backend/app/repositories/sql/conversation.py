"""Reading transcripts back — the admin half of the same two tables."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.models import ChatMessage, Conversation, ConversationPreview
from app.common.schemas import DatabaseChatMessage, DatabaseConversation
from app.repositories.base import ConversationRepository
from app.repositories.sql._shared import _rowcount


class SQLConversationRepository(ConversationRepository):
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
