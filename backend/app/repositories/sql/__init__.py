"""
The SQLAlchemy backend.

This package is the only place in the app that both names SQLAlchemy and is
reachable from a route. Everything above it depends on `app.repositories.base`,
so a second backend means a sibling package shaped like this one and a one-line
change in `app/repositories/__init__.py` — not an edit to any route or service.

One module per aggregate, named for the table it owns rather than for the class
inside it, so where a query lives is a question about the data and not about the
code. `_shared` is private to the package: what is in there is a statement about
SQLAlchemy or about a column, never about the domain.

Note where the session is declared: on the providers below, inside the backend.
A backend that needs no session, or a different one, declares its own
dependencies there, and the route asking for a repository is unaffected either
way.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.common.db import get_db, get_session_factory
from app.repositories.base import (
    ConversationRepository,
    RefreshSessionRepository,
    TokenRepository,
    TranscriptRepository,
    UserRepository,
)
from app.repositories.sql.conversation import SQLConversationRepository
from app.repositories.sql.refresh_session import SQLRefreshSessionRepository
from app.repositories.sql.token import SQLTokenRepository
from app.repositories.sql.transcript import SQLTranscriptRepository
from app.repositories.sql.user import SQLUserRepository

__all__ = [
    "SQLConversationRepository",
    "SQLRefreshSessionRepository",
    "SQLTokenRepository",
    "SQLTranscriptRepository",
    "SQLUserRepository",
    "provide_conversation_repository",
    "provide_refresh_session_repository",
    "provide_token_repository",
    "provide_transcript_repository",
    "provide_user_repository",
]


def provide_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    """
    Annotated with the abstraction, not the class, so a caller asking for this
    by `Depends` is typed against the base and can be handed any backend.
    """
    return SQLUserRepository(db=db)


def provide_token_repository(db: AsyncSession = Depends(get_db)) -> TokenRepository:
    # FastAPI caches `Depends(get_db)` for the life of a request, so every
    # repository below is handed the *same* session, and therefore the same
    # transaction. That is what keeps issuing a token atomic without anything
    # above this package knowing a transaction exists.
    return SQLTokenRepository(db=db)


def provide_refresh_session_repository(
    db: AsyncSession = Depends(get_db),
) -> RefreshSessionRepository:
    return SQLRefreshSessionRepository(db=db)


def provide_transcript_repository(
    factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> TranscriptRepository:
    # The factory, not a session: this repository has to still work after the
    # request that created it has torn down.
    return SQLTranscriptRepository(factory=factory)


def provide_conversation_repository(
    db: AsyncSession = Depends(get_db),
) -> ConversationRepository:
    return SQLConversationRepository(db=db)
