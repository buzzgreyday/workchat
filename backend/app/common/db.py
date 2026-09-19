from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.common.config import DATABASE_URL, DEV_MODE

engine = create_async_engine(DATABASE_URL, echo=DEV_MODE)
async_session = async_sessionmaker(engine, expire_on_commit=False)


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
    async with transaction(async_session) as session:
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
