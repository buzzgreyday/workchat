from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.common.config import DATABASE_URL, DEV_MODE

engine = create_async_engine(DATABASE_URL, echo=DEV_MODE)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


def get_session_factory() -> async_sessionmaker:
    """
    The factory itself, not a session.

    Deliberately not a yield-dependency: nothing is registered on the request's
    exit stack, so this stays usable after the request has torn down. The chat
    transcript recorder needs exactly that — on client abort it runs after the
    request-scoped session from get_db is already closed.
    """
    return async_session

class Base(DeclarativeBase):
    pass
