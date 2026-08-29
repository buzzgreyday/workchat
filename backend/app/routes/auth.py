"""
The v2 auth surface.

Only the auth endpoints are versioned. /chat and /chat/stream stay where they
are and take a v1 or a v2 access token indifferently, because the point of the
exercise is that the links already handed out keep working — moving the chat
routes under /v2 would have meant every v1 hirer holds a link to a frozen API.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db import get_db
from app.common.logging.logging import logger
from app.common.models import ClaimRequest, RefreshRequest, TokenPair
from app.services.auth import auth

router = APIRouter(prefix="/v2/auth", tags=["Auth"])


@router.post(
    "/claim",
    response_model=TokenPair,
    summary="Exchange a claim token for a session",
    description=(
        "Trades the claim token from a `?claim=...` link for a short-lived access "
        "token and a rotating refresh token. Repeatable until the grant expires, so "
        "the same link still works on a second device; each exchange opens its own "
        "session. Costs no queries."
    ),
)
async def claim(req: ClaimRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    logger.info("Claim token presented")
    return await auth.claim(req.claim_token, db)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotate a session",
    description=(
        "Exchanges a refresh token for a fresh pair and retires the one presented. "
        "Presenting a refresh token twice is treated as a replay: every session on "
        "the grant is revoked and the hirer has to re-claim. Costs no queries."
    ),
)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    logger.info("Refresh token presented")
    return await auth.refresh(req.refresh_token, db)
