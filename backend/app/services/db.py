import hashlib
import hmac
import uuid

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.common.logging import logging
from app.common.schemas import (
    DatabaseChatMessage,
    DatabaseConversation,
    DatabaseToken,
    DatabaseUser,
)
from app.common.config import TOKEN_HASHING_SECRET

logger = logging.logger

def hash_token(raw_token: str) -> str:
    return hmac.new(
        TOKEN_HASHING_SECRET.encode(), raw_token.encode(), hashlib.sha256
    ).hexdigest()


async def get_or_create_user(
        name: str,
        email: str,
        phone: str,
        db: AsyncSession
) -> DatabaseUser:
    """

    Args:
        name: Company name
        email:
        phone:
        db:

    Returns:

    """
    logger.debug(
        "Checking if user (company) exists",
        extra={"company (name)": name}
    )
    result = await db.execute(select(DatabaseUser).where(DatabaseUser.name == name))
    user = result.scalar_one_or_none()
    if user is not None:
        logger.info(
            "User exists",
            extra={"id": user.id, "company (name)": user.name, "email": user.email, "phone": user.phone}
        )
        return user

    user = DatabaseUser(name=name, email=email, phone=phone)
    logger.info(
        "Creating new user",
        extra={"company (name)": user.name, "email": user.email, "phone": user.phone}
    )
    db.add(user)
    await db.flush()
    logger.debug(
        "Changes flushed to database: user assigned with user.id without ending the transaction",
        extra={"id": user.id, "company (name)": user.name, "email": user.email, "phone": user.phone}
    )
    return user


async def create_user_and_relate_token(
        token_id: uuid.UUID,
        raw_token: str,
        max_queries: int,
        expires_at: datetime,
        subject: str,
        company: str,
        created_at: datetime,
        db: AsyncSession,
        email: str | None = None,
        phone: str | None = None,
        job_title: str | None = None,
) -> DatabaseToken:
    logger.debug(
        "Relating access token to user",
        extra={
            "subject": subject, "job_title": job_title, "company": company,
            "email": email, "phone": phone, "expires_at": expires_at,
            "max_queries": max_queries
        }
    )
    user = await get_or_create_user(name=company, email=email.lower() if email else None, phone=phone, db=db)

    token_hash = hash_token(raw_token)
    token_row = DatabaseToken(
        id=token_id,
        user_id=user.id,
        token_hash=token_hash,
        subject=subject,
        company=company,
        job_title=job_title,
        created_at=created_at,
        max_queries=max_queries,
        expires_at=expires_at,
    )
    logger.debug(
        "Creating token entry in database",
        extra={
            "user_id": user.id,
            "token_hash": token_hash,
            "subject": subject,
            "company": company,
            "job_title": job_title,
            "created_at": created_at,
            "max_queries": max_queries,
            "expires_at": expires_at
        }
    )
    db.add(token_row)
    await db.commit()
    await db.refresh(token_row)
    logger.info(
        "Committed token and user changes to database",
        extra={
            "token": {
                "user_id": user.id,
                "token_hash": token_hash,
                "subject": subject,
                "company": company,
                "job_title": job_title,
                "created_at": created_at,
                "max_queries": max_queries,
                "expires_at": expires_at
            },
            "user": {
                "id": user.id,
                "company (name)": user.name,
                "email": user.email,
                "phone": user.phone
            }
        }
    )
    return token_row

async def update_token_used_query_count(
        token_id: uuid.UUID,
        db: AsyncSession
):
    logger.debug(
        "Updating token used query count",
        extra={
            "token_id": token_id
        }
    )
    now = datetime.now(timezone.utc)
    # Atomic consume: increments used_queries only if the token is still
    # valid (not revoked, not expired, under its query limit). This avoids
    # the read-then-write race condition of the in-memory version.
    result = await db.execute(
        update(DatabaseToken)
        .where(
            DatabaseToken.id == token_id,
            DatabaseToken.revoked_at.is_(None),
            DatabaseToken.expires_at > now,
            DatabaseToken.used_queries < DatabaseToken.max_queries,
        )
        .values(used_queries=DatabaseToken.used_queries + 1)
        .returning(DatabaseToken)
    )
    row: DatabaseToken = result.scalar_one_or_none()
    await db.commit()

    if row is None:
        # Token exists but failed a condition above, or doesn't exist at all —
        # look it up again (read-only) to give a precise error message.
        existing = await db.get(DatabaseToken, token_id)
        if existing is None:
            logger.warning("Invalid token", extra={"token_id": token_id})
            raise HTTPException(401, "Invalid token")
        if existing.revoked_at is not None:
            logger.warning("Revoked token", extra={"token_id": token_id})
            raise HTTPException(401, "Token revoked")
        # DBs that don't preserve tzinfo (e.g. SQLite in tests) return naive
        # datetimes even though the column is DateTime(timezone=True). Treat
        # naive stored values as UTC before comparing to a tz-aware `now`.
        expires_at = existing.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            logger.warning("Expired token", extra={"token_id": token_id})
            raise HTTPException(401, "Token expired")
        raise HTTPException(429, "Query limit reached")
    logger.info(
        "Token updated",
        extra={
            "token_id": row.id,
            "user_id": row.user_id,
            "subject": row.subject,
            "company": row.company,
            "job_title": row.job_title,
            "used_queries": row.used_queries,
            "max_queries": row.max_queries,
            "expires_at": row.expires_at,
            "created_at": row.created_at
        }
    )
    return row


# --- Chat transcript capture -------------------------------------------------
#
# Every function below opens its own session from the factory rather than reusing
# the request-scoped one. That is forced, not stylistic: on client abort the
# request session is already closed by the time the recorder's finally block runs,
# so reusing it would be a use-after-close. Opening our own also keeps one code
# path for the streaming and non-streaming endpoints.
#
# None of them may raise. Capturing the transcript is an operator convenience;
# failing to capture it must never change what the hirer sees.

MAX_CONTENT_CHARS = 16000
MAX_ERROR_CHARS = 255
MAX_TOOL_NAMES_CHARS = 255


def _truncate(text: str | None, limit: int) -> tuple[str | None, int]:
    """Returns (clipped_text, truncated_flag). Guards against the column bound and
    the ChatRequest bound drifting apart and raising into a user's chat."""
    if text is None:
        return None, 0
    if len(text) <= limit:
        return text, 0
    return text[:limit], 1


async def _resolve_conversation(
        conversation_id: uuid.UUID | None,
        token_row: DatabaseToken,
        db: AsyncSession,
) -> DatabaseConversation:
    """
    Reuse the caller's conversation when it is genuinely theirs, otherwise mint one.

    The token_id predicate is load-bearing: without it any bearer could append
    into another hirer's conversation just by guessing an id. A mismatch is never
    a 4xx — a bad correlation id must not break someone's chat.
    """
    if conversation_id is not None:
        result = await db.execute(
            select(DatabaseConversation).where(
                DatabaseConversation.id == conversation_id,
                DatabaseConversation.token_id == token_row.id,
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is not None:
            return conversation
        logger.warning(
            "Conversation id not found for this token, starting a new conversation",
            extra={"conversation_id": conversation_id, "token_id": token_row.id},
        )

    conversation = DatabaseConversation(
        token_id=token_row.id,
        user_id=token_row.user_id,
        subject=token_row.subject,
        company=token_row.company,
        job_title=token_row.job_title,
    )
    db.add(conversation)
    await db.flush()
    logger.info(
        "Started new conversation",
        extra={"conversation_id": conversation.id, "token_id": token_row.id},
    )
    return conversation


async def record_user_message(
        session_factory: async_sessionmaker[AsyncSession],
        token_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        message: str,
        endpoint: str,
        request_id: str,
) -> uuid.UUID | None:
    """
    Persist the question before the model is called.

    This commit — not the terminal recorder — is what guarantees the question
    survives. Once it lands, nothing that happens to the stream, the LLM or the
    process can lose it. Returns the conversation id, or None if persistence
    failed (in which case the chat continues regardless).
    """
    try:
        async with session_factory() as db:
            token_row = await db.get(DatabaseToken, token_id)
            if token_row is None:
                logger.warning("Cannot record message, token is gone", extra={"token_id": token_id})
                return None

            conversation = await _resolve_conversation(conversation_id, token_row, db)
            content, truncated = _truncate(message, MAX_CONTENT_CHARS)

            db.add(
                DatabaseChatMessage(
                    conversation_id=conversation.id,
                    token_id=token_id,
                    request_id=request_id,
                    role="user",
                    content=content,
                    content_chars=len(message),
                    truncated=truncated,
                    endpoint=endpoint,
                    status="received",
                )
            )
            conversation.message_count += 1
            conversation.last_message_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "Recorded user message",
                extra={
                    "conversation_id": conversation.id,
                    "request_id": request_id,
                    "content_chars": len(message),
                },
            )
            return conversation.id
    except Exception:
        logger.exception(
            "Failed to record user message",
            extra={"token_id": token_id, "request_id": request_id},
        )
        return None


async def record_assistant_message(
        session_factory: async_sessionmaker[AsyncSession],
        token_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        reply: str,
        endpoint: str,
        request_id: str,
        status: str,
        finish_reason: str | None = None,
        tool_names: list[str] | None = None,
        tool_calls_count: int = 0,
        model: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
) -> None:
    """
    Persist the reply as it finished — completed, aborted or failed.

    Enrichment, not durability: the question is already committed by the time this
    runs. A failure here loses the reply, never the question.
    """
    if conversation_id is None:
        # record_user_message failed, so there is no conversation to attach to.
        return
    try:
        async with session_factory() as db:
            content, truncated = _truncate(reply, MAX_CONTENT_CHARS)
            names, _ = _truncate(",".join(tool_names or []) or None, MAX_TOOL_NAMES_CHARS)
            error_text, _ = _truncate(error, MAX_ERROR_CHARS)

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
                    status=status,
                    finish_reason=finish_reason,
                    tool_calls_count=tool_calls_count,
                    tool_names=names,
                    model=model,
                    latency_ms=latency_ms,
                    error=error_text,
                )
            )
            conversation = await db.get(DatabaseConversation, conversation_id)
            if conversation is not None:
                conversation.message_count += 1
                conversation.last_message_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "Recorded assistant message",
                extra={
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                    "status": status,
                    "latency_ms": latency_ms,
                    "content_chars": len(reply or ""),
                },
            )
    except Exception:
        logger.exception(
            "Failed to record assistant message",
            extra={"conversation_id": conversation_id, "request_id": request_id},
        )


# --- Admin read/redact queries -----------------------------------------------

async def list_conversations(
        db: AsyncSession,
        limit: int = 50,
        offset: int = 0,
        company: str | None = None,
        since: datetime | None = None,
) -> list[dict]:
    """Conversation summaries, newest activity first, each with a short preview of
    the opening question so the list is scannable without opening every thread."""
    logger.debug(
        "Listing conversations",
        extra={"limit": limit, "offset": offset, "company": company, "since": since},
    )

    stmt = select(DatabaseConversation)
    if company:
        stmt = stmt.where(DatabaseConversation.company == company)
    if since:
        stmt = stmt.where(DatabaseConversation.created_at >= since)
    stmt = stmt.order_by(
        DatabaseConversation.last_message_at.desc().nullslast(),
        DatabaseConversation.created_at.desc(),
    ).limit(limit).offset(offset)

    conversations = (await db.execute(stmt)).scalars().all()

    summaries = []
    for conversation in conversations:
        first = (
            await db.execute(
                select(DatabaseChatMessage.content)
                .where(
                    DatabaseChatMessage.conversation_id == conversation.id,
                    DatabaseChatMessage.role == "user",
                )
                .order_by(DatabaseChatMessage.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()

        # The reply matters as much as the question here — the point of reading
        # these is catching the agent answering wrongly, which the question alone
        # cannot show. Latest rather than first, so a thread shows where it ended up.
        last_reply = (
            await db.execute(
                select(DatabaseChatMessage.content)
                .where(
                    DatabaseChatMessage.conversation_id == conversation.id,
                    DatabaseChatMessage.role == "assistant",
                )
                .order_by(DatabaseChatMessage.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        summaries.append(
            {
                "id": conversation.id,
                "subject": conversation.subject,
                "company": conversation.company,
                "job_title": conversation.job_title,
                "message_count": conversation.message_count,
                "created_at": conversation.created_at,
                "last_message_at": conversation.last_message_at,
                "redacted_at": conversation.redacted_at,
                "preview": (first[:120] if first else None),
                "reply_preview": (last_reply[:200] if last_reply else None),
            }
        )

    logger.info("Listed conversations", extra={"count": len(summaries)})
    return summaries


async def get_conversation_messages(
        conversation_id: uuid.UUID,
        db: AsyncSession,
) -> tuple[DatabaseConversation | None, list[DatabaseChatMessage]]:
    """The full transcript, oldest first."""
    logger.debug("Fetching conversation", extra={"conversation_id": conversation_id})

    conversation = await db.get(DatabaseConversation, conversation_id)
    if conversation is None:
        return None, []

    messages = (
        await db.execute(
            select(DatabaseChatMessage)
            .where(DatabaseChatMessage.conversation_id == conversation_id)
            .order_by(DatabaseChatMessage.created_at.asc())
        )
    ).scalars().all()

    logger.info(
        "Fetched conversation",
        extra={"conversation_id": conversation_id, "messages": len(messages)},
    )
    return conversation, list(messages)


async def redact_conversation(
        conversation_id: uuid.UUID,
        db: AsyncSession,
) -> int:
    """
    Null the content, keep the row.

    Deletion would take the counts and timings with it, and every FK here is
    RESTRICT so rows cannot be removed piecemeal anyway. Redaction erases the
    personal data while leaving the operational record intact.
    """
    logger.debug("Redacting conversation", extra={"conversation_id": conversation_id})
    now = datetime.now(timezone.utc)

    result = await db.execute(
        update(DatabaseChatMessage)
        .where(
            DatabaseChatMessage.conversation_id == conversation_id,
            DatabaseChatMessage.content.is_not(None),
        )
        .values(content=None, redacted_at=now)
    )
    await db.execute(
        update(DatabaseConversation)
        .where(DatabaseConversation.id == conversation_id)
        .values(redacted_at=now)
    )
    await db.commit()

    redacted = result.rowcount or 0
    logger.info(
        "Redacted conversation",
        extra={"conversation_id": conversation_id, "messages_redacted": redacted},
    )
    return redacted
