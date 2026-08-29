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
    DatabaseRefreshToken,
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
        version: int = 1,
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
        version=version,
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
            "expires_at": expires_at,
            "version": version
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
        db: AsyncSession,
        expected_version: int | None = None,
):
    logger.debug(
        "Updating token used query count",
        extra={
            "token_id": token_id,
            "expected_version": expected_version
        }
    )
    now = datetime.now(timezone.utc)
    # Atomic consume: increments used_queries only if the token is still
    # valid (not revoked, not expired, under its query limit). This avoids
    # the read-then-write race condition of the in-memory version.
    predicates = [
        DatabaseToken.id == token_id,
        DatabaseToken.revoked_at.is_(None),
        DatabaseToken.expires_at > now,
        DatabaseToken.used_queries < DatabaseToken.max_queries,
    ]
    # Version is a predicate rather than a check on the returned row so that a
    # mismatch costs nothing: presenting a v1-shaped token against a v2 grant
    # fails without first spending one of that grant's questions.
    if expected_version is not None:
        predicates.append(DatabaseToken.version == expected_version)

    result = await db.execute(
        update(DatabaseToken)
        .where(*predicates)
        .values(used_queries=DatabaseToken.used_queries + 1)
        .returning(DatabaseToken)
        # RETURNING is the only source of truth we want here. Left on "evaluate",
        # SQLAlchemy re-runs the expires_at predicate in Python against any row
        # already in the session, and a driver that drops tzinfo on read (SQLite)
        # makes that comparison raise. The row we act on comes back from the DB.
        .execution_options(synchronize_session=False)
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
        if expected_version is not None and existing.version != expected_version:
            logger.warning(
                "Token version does not match its grant",
                extra={"token_id": token_id, "expected_version": expected_version, "version": existing.version},
            )
            raise HTTPException(401, "Invalid token")
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


# --- v2 grants and refresh sessions ------------------------------------------
#
# The v1 path never needed any of this: its JWT was the grant, so verifying the
# signature and consuming a query was the whole story. v2 mints tokens from a
# grant repeatedly, which means the grant has to be re-checked on every mint and
# refresh tokens have to be tracked as rows rather than trusted as signatures.


def _as_utc(value: datetime) -> datetime:
    """
    DBs that don't preserve tzinfo (SQLite in tests) hand back naive datetimes
    from a DateTime(timezone=True) column. Everything stored is UTC, so read a
    naive value as UTC rather than letting it raise against a tz-aware `now`.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def get_active_grant(token_id: uuid.UUID, db: AsyncSession) -> DatabaseToken:
    """
    The grant behind a claim or refresh token, if it is still good for minting.

    Read-only and quota-free on purpose: exchanging a claim or rotating a refresh
    token must not cost the hirer one of their questions. Quota is spent in
    update_token_used_query_count, when a question is actually asked.
    """
    now = datetime.now(timezone.utc)
    grant = await db.get(DatabaseToken, token_id)
    if grant is None:
        logger.warning("Invalid token", extra={"token_id": token_id})
        raise HTTPException(401, "Invalid token")
    if grant.revoked_at is not None:
        logger.warning("Revoked token", extra={"token_id": token_id})
        raise HTTPException(401, "Token revoked")
    if _as_utc(grant.expires_at) <= now:
        logger.warning("Expired token", extra={"token_id": token_id})
        raise HTTPException(401, "Token expired")
    return grant


async def create_refresh_token(
        token_id: uuid.UUID,
        raw_token: str,
        expires_at: datetime,
        db: AsyncSession,
        refresh_id: uuid.UUID | None = None,
        commit: bool = True,
) -> DatabaseRefreshToken:
    """Open a new session on a grant. Called on every claim exchange, so opening
    the link on a second device adds a session rather than stealing the first."""
    row = DatabaseRefreshToken(
        id=refresh_id or uuid.uuid4(),
        token_id=token_id,
        token_hash=hash_token(raw_token),
        expires_at=expires_at,
    )
    db.add(row)
    if commit:
        await db.commit()
        await db.refresh(row)
    else:
        await db.flush()
    logger.info(
        "Opened refresh session",
        extra={"refresh_id": row.id, "token_id": token_id, "expires_at": expires_at},
    )
    return row


async def revoke_refresh_sessions(token_id: uuid.UUID, db: AsyncSession) -> int:
    """Cut every live session on a grant. The blunt response to a replayed
    refresh token: we cannot tell the thief from the hirer, so both re-claim."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(DatabaseRefreshToken)
        .where(
            DatabaseRefreshToken.token_id == token_id,
            DatabaseRefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    revoked = result.rowcount or 0
    logger.warning("Revoked refresh sessions", extra={"token_id": token_id, "count": revoked})
    return revoked


async def rotate_refresh_token(
        refresh_id: uuid.UUID,
        raw_new_token: str,
        new_expires_at: datetime,
        db: AsyncSession,
        new_refresh_id: uuid.UUID | None = None,
) -> DatabaseRefreshToken:
    """
    Exchange one refresh token for its successor, atomically.

    The new row is inserted *before* the old one is claimed so that rotated_to
    has something to point at — the FK is checked immediately, not deferred. If
    the claiming UPDATE then matches nothing, the rollback takes the insert with
    it, so a lost race leaves no orphan.

    Matching nothing means the token was already spent. That is either a client
    that retried, or a stolen token being replayed, and nothing here can tell
    which — so every live session on the grant is cut and the hirer re-claims.
    """
    now = datetime.now(timezone.utc)
    new_id = new_refresh_id or uuid.uuid4()

    existing = await db.get(DatabaseRefreshToken, refresh_id)
    if existing is None:
        logger.warning("Unknown refresh token", extra={"refresh_id": refresh_id})
        raise HTTPException(401, "Invalid refresh token")

    successor = await create_refresh_token(
        token_id=existing.token_id,
        raw_token=raw_new_token,
        expires_at=new_expires_at,
        db=db,
        refresh_id=new_id,
        commit=False,
    )

    result = await db.execute(
        update(DatabaseRefreshToken)
        .where(
            DatabaseRefreshToken.id == refresh_id,
            DatabaseRefreshToken.revoked_at.is_(None),
            DatabaseRefreshToken.expires_at > now,
        )
        .values(revoked_at=now, last_used_at=now, rotated_to=new_id)
        .execution_options(synchronize_session=False)
    )

    if not result.rowcount:
        await db.rollback()
        stale = await db.get(DatabaseRefreshToken, refresh_id)
        if stale is not None and stale.revoked_at is not None:
            logger.warning(
                "Refresh token replayed after rotation, cutting the grant's sessions",
                extra={"refresh_id": refresh_id, "token_id": stale.token_id},
            )
            await revoke_refresh_sessions(stale.token_id, db)
            raise HTTPException(401, "Refresh token already used")
        logger.warning("Expired refresh token", extra={"refresh_id": refresh_id})
        raise HTTPException(401, "Refresh token expired")

    await db.commit()
    await db.refresh(successor)
    logger.info(
        "Rotated refresh token",
        extra={"refresh_id": refresh_id, "successor_id": successor.id, "token_id": successor.token_id},
    )
    return successor


async def get_refresh_token(refresh_id: uuid.UUID, db: AsyncSession) -> DatabaseRefreshToken | None:
    return await db.get(DatabaseRefreshToken, refresh_id)


async def mark_grant_claimed(token_id: uuid.UUID, db: AsyncSession) -> None:
    """
    Stamp the first exchange of a claim link and leave it alone thereafter.

    The predicate is what keeps it first-only. The claim stays reusable until the
    grant expires, so this is a record of whether the link was ever opened, not
    a gate on opening it again.
    """
    await db.execute(
        update(DatabaseToken)
        .where(DatabaseToken.id == token_id, DatabaseToken.claimed_at.is_(None))
        .values(claimed_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    await db.commit()


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
