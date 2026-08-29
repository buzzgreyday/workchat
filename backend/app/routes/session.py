"""
What the client needs to know before it asks anything.

Unversioned, like the chat routes and for the same reason: a v1 link and a v2
access token are both valid ways to be here, and the answer is the same either
way. Reading this spends no quota — a hirer with none left is exactly the person
who needs to be told, so this reports zero rather than refusing.
"""

from fastapi import APIRouter, Depends

from app.common.logging.logging import logger
from app.common.models import SessionInfo, TokenContext, Usage
from app.services.auth import auth

router = APIRouter(tags=["Session"])


@router.get(
    "/session",
    response_model=SessionInfo,
    summary="Who this session is, and what is left of it",
    description=(
        "Reports the subject and remaining query allowance for the presented "
        "access token, without spending any of it. Accepts a v1 `?token=` JWT or "
        "a v2 access token. Returns `usage.remaining: 0` for an exhausted grant "
        "rather than 429 — that is a state to display, not an error."
    ),
)
async def session(token: TokenContext = Depends(auth.verify)) -> SessionInfo:
    logger.info(
        "Session queried",
        extra={
            "subject": token.sub,
            "version": token.version,
            "remaining_queries": token.remaining_queries,
        },
    )
    return SessionInfo(
        subject=token.sub,
        version=token.version,
        usage=Usage(
            used=token.used_queries,
            remaining=token.remaining_queries,
            max=token.max_queries,
        ),
        expires_at=token.expires_at,
        session_id=token.session_id,
    )
