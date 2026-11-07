"""The grant behind a token, read for both the session flow and a request."""

import uuid
from datetime import datetime, timezone

from app.common.exceptions import InvalidToken
from app.common.logging.logging import logger
from app.common.models import Grant, TokenVersion
from app.repositories.base import TokenRepository


async def active_grant(
        tokens: TokenRepository,
        token_id: uuid.UUID,
        expected_version: TokenVersion | None = None,
) -> Grant:
    """
    The grant behind a claim, refresh or access token, if it is still usable.

    Here rather than in the repository because "usable" is policy, not storage
    (`Grant.refusal` states it). Read-only and quota-free on purpose —
    exchanging a claim, rotating a refresh token or asking how many questions
    are left must not cost the hirer one of them.

    Note what is *not* checked: whether any quota remains. A grant with none
    left is still a valid grant, and /session reports it as zero.
    """
    grant = await tokens.get(token_id)
    if grant is None:
        logger.warning("Invalid token", extra={"token_id": token_id})
        raise InvalidToken()
    refusal = grant.refusal(datetime.now(timezone.utc), expected_version)
    if refusal is not None:
        raise refusal
    return grant
