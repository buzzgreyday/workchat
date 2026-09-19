"""
Persistence, as its own layer — and the one place that names a backend.

Services depend on the abstractions in `base`; nothing here depends on a
service, and nothing here knows that HTTP exists. The bindings below are the
composition root: to move to another store, write a module shaped like `sql`
and change which one is imported here. No route and no service mentions a
backend, so nothing else has to change.

There is deliberately no completion verb anywhere in `base` — no `commit`, no
unit of work. Durability is the backend's business: SQLAlchemy's Session is
already a unit of work and ends with the request, while a store without
transactions has nothing to commit and could only stub one, implying a
guarantee it cannot keep.

There is likewise no config switch. A `STORAGE_BACKEND` env var would be a
branch guarding a module that does not exist yet; when a second backend does
exist, the branch belongs here and nowhere else.
"""

# Storage repository configuration
from app.repositories import sql as _backend
from app.repositories.base import (
    ConversationRepositoryBase,
    ReplyOutcome,
    RepositoryBase,
    SessionRepositoryBase,
    TokenRepositoryBase,
    TranscriptRepositoryBase,
    UserRepositoryBase,
)

__all__ = [
    "ConversationRepositoryBase",
    "ReplyOutcome",
    "RepositoryBase",
    "SessionRepositoryBase",
    "TokenRepositoryBase",
    "TranscriptRepositoryBase",
    "UserRepositoryBase",
    "get_conversation_repository",
    "get_session_repository",
    "get_transcript_repository",
    "get_token_repository",
    "get_user_repository",
]

# The FastAPI dependencies the routes use. Their own dependencies are whatever
# the chosen backend declares — a session here, something else elsewhere —
# which is exactly what a route asking for a repository should not have to know.
get_user_repository = _backend.provide_user_repository
get_token_repository = _backend.provide_token_repository
get_session_repository = _backend.provide_session_repository
get_transcript_repository = _backend.provide_transcript_repository
get_conversation_repository = _backend.provide_conversation_repository
