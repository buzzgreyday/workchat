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
        result = await self.db.execute(select(DatabaseUser).where(DatabaseUser.name == name))
        row = result.scalar_one_or_none()
        if row is None:
            self.logger.debug("No user for this company yet", extra={"company (name)": name})
            return None
        user = User.model_validate(row)
        self.logger.debug("Found the user for this company", extra={"user_id": user.id})
        return user

    async def add(self, name: str, email: str | None, phone: str | None) -> User:
        # Lower-cased on the way in and on the way out of get_by_name, so a
        # lookup and the row it would have matched agree on spelling.
        email = email.lower() if email else None
        row = DatabaseUser(name=name, email=email, phone=phone)
        self.db.add(row)
        # Flush, not commit: this assigns row.id so the grant can reference it,
        # while leaving the transaction for the request scope to close.
        await self.db.flush()
        user = User.model_validate(row)
        # The id, not the row. A contact detail is worth exactly one copy, in a
        # store with a retention policy — and the service above already records
        # that a user was created.
        self.logger.debug(
            "Flushed a new user; id assigned without ending the transaction",
            extra={"user_id": user.id, "company (name)": user.name},
        )
        return user
