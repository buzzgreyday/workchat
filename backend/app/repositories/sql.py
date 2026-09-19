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

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db import get_db
from app.common.models import Grant, User
from app.common.schemas import DatabaseToken, DatabaseUser
from app.repositories.base import TokenRepositoryBase, UserRepositoryBase


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
