from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.common.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """
    The engine, built on first use rather than at import.

    Module-level, it made importing anything that reaches this file open a
    connection pool against whatever DATABASE_URL happened to be set — and fail
    at import if nothing was. One per process, which is what an engine is for.
    """
    settings = get_settings()
    return create_async_engine(settings.database_url, echo=settings.sql_echo)


@asynccontextmanager
async def transaction(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """
    A session whose transaction ends with the scope that opened it.

    Committing here rather than in a service is what keeps persistence out of
    the domain: a service writes through repositories and never names a
    mechanism. SQLAlchemy's Session is already a unit of work, so there is
    nothing to wrap it in — and a `commit` on some abstraction above this would
    be a verb a store without transactions could not honour.

    Takes the factory rather than using the module-level one so the tests bind
    the same semantics to their own engine, instead of restating them.
    """
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    The request's session, and the request's transaction.

    Two FastAPI behaviours this leans on, both worth not rediscovering:

    Exception handlers run *outside* the dependency exit stacks, so a route
    raising an AppError reaches the teardown below before the handler turns it
    into a response — the rollback fires rather than being skipped.

    A dependency with yield registers on the request stack, not the function
    stack, and the response is sent inside that stack. So for a streaming
    response the session outlives the streamed body and commits after it. The
    transcript recorder still needs get_session_factory, because it has to
    outlive even that.
    """
    async with transaction(get_session_factory()) as session:
        yield session


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    The factory itself, not a session.

    Deliberately not a yield-dependency: nothing is registered on the request's
    exit stack, so this stays usable after the request has torn down. The chat
    transcript recorder needs exactly that — on client abort it runs after the
    request-scoped session from get_db is already closed.

    Cached, so every caller shares one factory over one engine — which is what
    the module-level binding used to provide before it moved behind a call.
    """
    return async_sessionmaker(get_engine(), expire_on_commit=False)

class Base(DeclarativeBase):
    pass
