"""
Domain exceptions, and the one place that decides what they mean over HTTP.

Services raise these; only the boundary translates them. That split is the point
of the module. Before it, `services/db.py` and `services/auth.py` both imported
`fastapi.HTTPException` and hard-coded status codes and wording inline, which put
three problems in the same place: the wording of a 401 was scattered across two
files and easy to drift, the services could not be used outside a request without
dragging FastAPI in, and `ReplayDetected` had to exist as a *second*, separate
exception type purely because the layer that detected a replay could not be the
layer that answered one.

Every class carries its own `status_code` and default `detail`, so adding a case
is one class here rather than an edit in a service plus a matching change to
whatever asserted on the old string. `main.py` registers a single handler for
`AppError` that renders `{"detail": ...}` — the same shape FastAPI produces for
`HTTPException`, so nothing downstream can tell the difference.
"""

import uuid


class AppError(Exception):
    """
    Base for anything this application raises deliberately.

    `detail` is what the caller is told and must stay free of anything that would
    help someone probing: which of several checks failed, whether an id exists,
    what a token contained. The specifics belong in the log line at the raise
    site, which is why `context` is kept separate from `detail`.
    """

    status_code: int = 500
    detail: str = "Internal error"

    def __init__(self, detail: str | None = None, **context):
        self.detail = detail or type(self).detail
        self.context = context
        super().__init__(self.detail)


# --- Authentication and authorisation ----------------------------------------

class AuthError(AppError):
    """Anything that stops a caller proving who they are."""

    status_code = 401
    detail = "Invalid token"


class MissingCredentials(AuthError):
    detail = "Missing or malformed Authorization header"


class InvalidToken(AuthError):
    detail = "Invalid token"


class TokenExpired(AuthError):
    detail = "Token expired"


class TokenRevoked(AuthError):
    detail = "Token revoked"


class UnsupportedTokenVersion(AuthError):
    detail = "Unsupported token version"


# Deliberately distinct from InvalidToken: each of these is a validly signed
# token being used for something it was not minted for, which is worth telling
# apart in a log even though the caller only ever sees a 401.

class NotAnAccessToken(AuthError):
    detail = "Not an access token"


class NotAClaimToken(AuthError):
    detail = "Not a claim token"


class NotARefreshToken(AuthError):
    detail = "Not a refresh token"


class MissingRefreshToken(AuthError):
    detail = "Missing refresh token"


class InvalidRefreshToken(AuthError):
    detail = "Invalid refresh token"


class RefreshTokenExpired(AuthError):
    detail = "Refresh token expired"


class SessionRevoked(AuthError):
    detail = "Session revoked"


class RefreshTokenReplayed(AuthError):
    """
    A refresh token presented well after it was rotated away.

    Carries the grant so the layer that answers can tell the operator who is now
    locked out — the sessions are already cut by the time this is raised, and
    with a single-use claim the hirer has no way back on their own.
    """

    detail = "Refresh token already used"

    def __init__(self, token_id: uuid.UUID, detail: str | None = None):
        self.token_id = token_id
        super().__init__(detail, token_id=str(token_id))


class AdminForbidden(AppError):
    status_code = 403
    detail = "Forbidden"


# --- Conflicts ---------------------------------------------------------------
#
# 409 rather than 401 on purpose. Neither of these means "your credentials are
# bad", and a client that treats every non-200 from the auth endpoints as a
# logout would be wrong about both.

class RotationInProgress(AppError):
    """
    This client racing itself — parallel requests that all expired at once, or a
    retry after a network flake. The session it already holds is still good.
    """

    status_code = 409
    detail = "Refresh already rotated; retry with the newest token"


class ClaimAlreadyUsed(AppError):
    """A spent claim link. Only the operator can issue a replacement."""

    status_code = 409
    detail = "This link has already been used. Ask for a new one."


# --- Quota -------------------------------------------------------------------

class QuotaExhausted(AppError):
    status_code = 429
    detail = "Query limit reached"
