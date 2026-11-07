"""
Access control for the CV chat backend, in two versions at once.

**v1** — the tokens already handed out. One long-lived JWT per grant, delivered
as `?token=...`, carrying `sub` / `exp` / `jti` / `max_queries`, where `jti` *is*
the tokens row. Those links are in inboxes and on printed QR codes and cannot be
reissued, so this path is frozen: a v1 bearer takes exactly the same route
through the code it always did, and nothing below may add a lookup or a claim to
it.

**v2** — a claim token, delivered as `?claim=...`, exchanged at /v2/auth/claim
for a short-lived access token plus a rotating refresh token. The grant row
outlives all three; quota is still counted there, so a hirer refreshing all day
gets no extra questions.

Versions are told apart by the `ver` claim, and its *absence* is what marks v1 —
that is the only signal an already-issued token can offer. The chat endpoints
stay unversioned and accept either kind; only the auth endpoints are under /v2.

Per-grant usage is enforced by an atomic write in the store
(see TokenRepository.spend_question), not in-memory, so it survives restarts
and works across replicas.

One class per reason to change, each taking plain arguments and knowing nothing
about `Depends`:

  - `TokenCodec` (tokens.py) — the signing key and lifetimes: decode, and mint
    the link token or a new session's pair.
  - `SessionService` (sessions.py) — the v2 flow: claim, open, refresh.
  - `Authenticator` (bearer.py) — what a request's bearer is worth: verify, or
    verify and spend a question.

The admin key is not among them: it is a different secret for a different
person, and checking it needs nothing the others hold.

Why this is a dependency and not middleware, since it comes up: middleware would
be the usual way to make an auth check impossible to forget, and it is the wrong
tool here for three reasons.

  - It has no dependency injection. verify_and_consume takes its repositories
    from Depends, and tests/conftest.py swaps the session under them through
    app.dependency_overrides — a mechanism that only exists for dependencies.
    Auth in middleware means the suite can no longer point the app at its
    in-memory database.
  - verify_and_consume *spends a query*, which is a business action rather than an
    authentication one. Middleware runs on whatever matches a path, so depending
    on where it sat in the stack a CORS preflight could cost a hirer a question.
  - The three protected surfaces want different checks — /chat verifies and
    consumes, /session verifies only, /admin authenticates a key — so one
    middleware would need a path-to-policy table, which is a second router.

The fail-closed property middleware would buy is worth having by other means if
this grows: FastAPI takes dependencies at router level, and a test that walks
app.routes asserting each is either public or guarded catches more than either.
"""

import hmac

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.common.config import Settings, get_settings
from app.common.exceptions import AdminForbidden
from app.common.models import TokenContext
from app.repositories import get_refresh_session_repository, get_token_repository
from app.repositories.base import RefreshSessionRepository, TokenRepository
from app.services.auth.bearer import Authenticator, Bearer, PaidQuestion
from app.services.auth.sessions import SessionService
from app.services.auth.tokens import NewSession, TokenCodec
from app.services.notify import notifier as default_notifier

__all__ = [
    "Authenticator",
    "Bearer",
    "NewSession",
    "PaidQuestion",
    "SessionService",
    "TokenCodec",
    "bearer_scheme",
    "get_authenticator",
    "get_session_service",
    "get_token_codec",
    "require_admin",
    "verify",
]

bearer_scheme = HTTPBearer(auto_error=False)


# --- providers -----------------------------------------------------------------
#
# Functions rather than module-level instances: FastAPI evaluates a `Depends(...)`
# argument when the route is *declared*, so an instance built at import would
# read the signing key at import, and the application could not be imported
# without a fully configured environment. Each is built from the one before it
# by `Depends`, so `dependency_overrides[get_settings]` reaches all three, and
# overriding any one reaches every endpoint that uses it.

def get_token_codec(settings: Settings = Depends(get_settings)) -> TokenCodec:
    return TokenCodec.from_settings(settings)


def get_session_service(codec: TokenCodec = Depends(get_token_codec)) -> SessionService:
    return SessionService(codec, notifier=default_notifier)


def get_authenticator(codec: TokenCodec = Depends(get_token_codec)) -> Authenticator:
    return Authenticator(codec)


# --- adapters ------------------------------------------------------------------

async def verify(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        tokens: TokenRepository = Depends(get_token_repository),
        sessions: RefreshSessionRepository = Depends(get_refresh_session_repository),
        authenticator: Authenticator = Depends(get_authenticator),
) -> TokenContext:
    """`/session`'s dependency: the same checks as chat, spending nothing."""
    return await authenticator.verify(credentials, tokens, sessions)


def require_admin(
        x_admin_key: str = Header(...),
        settings: Settings = Depends(get_settings),
) -> None:
    """The admin endpoints' dependency: a static header secret only the
    operator holds."""
    # compare_digest, so neither the key's length nor a matching prefix shows
    # in how long a refusal takes.
    if not hmac.compare_digest(x_admin_key.encode(), settings.admin_key.encode()):
        raise AdminForbidden()
