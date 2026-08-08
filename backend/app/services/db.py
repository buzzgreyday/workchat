import hashlib
import hmac
import uuid

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.logging import logging
from app.common.schemas import DatabaseUser, DatabaseToken
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
