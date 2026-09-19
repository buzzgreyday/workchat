"""The users table."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.models import User
from app.common.schemas import DatabaseUser
from app.repositories.base import UserRepository


class SQLUserRepository(UserRepository):
    """The users table, behind UserRepository."""

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
