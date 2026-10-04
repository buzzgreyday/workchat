"""
The v2 auth surface.

Only the auth endpoints are versioned. /chat and /chat/stream stay where they
are and take a v1 or a v2 access token indifferently, because the point of the
exercise is that the links already handed out keep working — moving the chat
routes under /v2 would have meant every v1 hirer holds a link to a frozen API.

The refresh token is delivered as an httpOnly cookie and is never in a response
body. The access token is, because the client has to put it in an Authorization
header and therefore has to be able to read it; it is short-lived for exactly
that reason. So an XSS on the page can steal minutes of access, not a week of it.
"""

from fastapi import APIRouter, Cookie, Depends, Request, Response

from app.common.client_ip import client_ip
from app.common.config import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH, get_settings
from app.common.exceptions import MissingRefreshToken
from app.common.logging.logging import logger
from app.common.models import ClaimRequest, RefreshRequest, SessionOut, TokenPair, TrialRequest
from app.repositories import (
    get_refresh_session_repository,
    get_token_repository,
    get_trial_repository,
    get_user_repository,
)
from app.repositories.base import (
    RefreshSessionRepository,
    TokenRepository,
    TrialRepository,
    UserRepository,
)
from app.services import trial as trial_service
from app.services.auth import Auth, get_auth

router = APIRouter(prefix="/v2/auth", tags=["Auth"])


def _set_refresh_cookie(response: Response, pair: TokenPair) -> SessionOut:
    """
    Put the refresh token in a cookie and return the half the client may read.

    SameSite=Strict is safe here because nothing in this flow is a cross-site
    request: the claim link is a top-level navigation that does not need the
    cookie, and every call afterwards is same-site. It also means a hostile page
    cannot silently force a rotation and knock the hirer's session over.
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=pair.refresh_token,
        max_age=pair.refresh_expires_in,
        httponly=True,
        secure=get_settings().refresh_cookie_secure,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )
    return SessionOut(
        access_token=pair.access_token,
        expires_in=pair.expires_in,
        refresh_expires_in=pair.refresh_expires_in,
    )


@router.post(
    "/claim",
    response_model=SessionOut,
    summary="Exchange a claim token for a session",
    description=(
        "Trades the claim token from a `?claim=...` link for a short-lived access "
        "token in the body and a rotating refresh token in an httpOnly cookie. "
        "**Single use**: a second presentation is refused with 409 and the operator "
        "is notified, because only they can issue a replacement link. Costs no queries."
    ),
    responses={409: {"description": "The link has already been used."}},
)
async def claim(
    req: ClaimRequest,
    response: Response,
    tokens: TokenRepository = Depends(get_token_repository),
    sessions: RefreshSessionRepository = Depends(get_refresh_session_repository),
    auth: Auth = Depends(get_auth),
) -> SessionOut:
    logger.info("Claim token presented")
    pair = await auth.claim(req.claim_token, tokens=tokens, sessions=sessions)
    return _set_refresh_cookie(response, pair)


@router.post(
    "/refresh",
    response_model=SessionOut,
    summary="Rotate a session",
    description=(
        "Reads the refresh cookie, retires it and sets its successor. A token "
        "re-presented within the rotation grace window answers 409 — that is this "
        "client racing itself, and the session it already has stays good. Outside "
        "the window it is treated as a replay: every session on the grant is cut "
        "and the hirer needs a new link. Costs no queries."
    ),
    responses={
        409: {"description": "Already rotated inside the grace window; retry with the newest token."},
    },
)
async def refresh(
    response: Response,
    req: RefreshRequest | None = None,
    refresh_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    tokens: TokenRepository = Depends(get_token_repository),
    sessions: RefreshSessionRepository = Depends(get_refresh_session_repository),
    auth: Auth = Depends(get_auth),
) -> SessionOut:
    # Cookie first: that is where a browser keeps it. The body is the escape
    # hatch for callers that have no cookie jar.
    raw = refresh_cookie or (req.refresh_token if req else None)
    if not raw:
        raise MissingRefreshToken()

    logger.info("Refresh token presented", extra={"via": "cookie" if refresh_cookie else "body"})
    pair = await auth.refresh(raw, tokens=tokens, sessions=sessions)
    return _set_refresh_cookie(response, pair)


@router.get(
    "/trial/challenge",
    response_model=trial_service.Challenge,
    summary="A proof-of-work for a guest trial",
    description=(
        "A signed challenge to solve before asking for a trial: find the number "
        "`n` for which `sha256(salt + n) == challenge`, at most `maxnumber`. "
        "Valid for five minutes. Answers 404 while trials are switched off, "
        "which is also how a client learns whether to offer one."
    ),
    responses={404: {"description": "Trials are switched off."}},
)
async def trial_challenge() -> trial_service.Challenge:
    return trial_service.challenge(get_settings())


@router.post(
    "/trial",
    response_model=SessionOut,
    summary="Open a guest trial",
    description=(
        "Trades a solved challenge for a session on a small grant of its own, "
        "set up exactly as a claim's: access token in the body, refresh token "
        "in an httpOnly cookie. One per address per day, one per challenge, "
        "and a ceiling per day for everyone. Costs no queries."
    ),
    responses={
        400: {"description": "The solution does not hold, has expired, or was already used."},
        404: {"description": "Trials are switched off."},
        429: {"description": "This address has had today's trial."},
        503: {"description": "Today's trials are all gone."},
    },
)
async def trial(
    req: TrialRequest,
    request: Request,
    response: Response,
    users: UserRepository = Depends(get_user_repository),
    tokens: TokenRepository = Depends(get_token_repository),
    sessions: RefreshSessionRepository = Depends(get_refresh_session_repository),
    trials: TrialRepository = Depends(get_trial_repository),
    auth: Auth = Depends(get_auth),
) -> SessionOut:
    logger.info("Trial requested")
    pair = await trial_service.start_trial(
        req.solution,
        client_ip(request),
        settings=get_settings(),
        users=users,
        tokens=tokens,
        sessions=sessions,
        trials=trials,
        auth=auth,
    )
    return _set_refresh_cookie(response, pair)
