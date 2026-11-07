"""
Checking the bearer on a request: a v1 link token or a v2 access token.

The v1 path is frozen: decode, read the grant id from `jti`, done. Those tokens
are in inboxes and on printed QR codes, so nothing here may add a lookup or a
claim to it.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi.security import HTTPAuthorizationCredentials

from app.common.exceptions import (
    InvalidToken,
    MissingCredentials,
    NotAnAccessToken,
    SessionRevoked,
    UnsupportedTokenVersion,
)
from app.common.logging.logging import logger
from app.common.models import Grant, TokenContext, TokenVersion
from app.repositories.base import RefreshSessionRepository, TokenRepository
from app.services.auth.grants import active_grant
from app.services.auth.tokens import TokenCodec, claimed_id


@dataclass(frozen=True, slots=True)
class Bearer:
    """Who a request's token says it is: the grant, the flow, and for v2 the session."""

    grant_id: uuid.UUID
    version: TokenVersion
    session_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class PaidQuestion:
    """
    A request's token, with one question paid for on it.

    `earlier_conversation` is where an earlier attempt at the same question
    recorded it, if one did.
    """

    token: TokenContext
    earlier_conversation: uuid.UUID | None


class Authenticator:
    """What the chat and /session endpoints are built on."""

    def __init__(self, codec: TokenCodec) -> None:
        self.codec = codec

    async def verify_and_consume(
            self,
            credentials: HTTPAuthorizationCredentials | None,
            tokens: TokenRepository,
            sessions: RefreshSessionRepository,
            question_key: uuid.UUID,
            message_hash: str,
    ) -> PaidQuestion:
        """
        Accepts a v1 or a v2 access token and spends one query from the grant
        either way, unless this key has already paid for this question.
        """
        bearer = await self._authenticate(credentials, sessions)
        spent = await tokens.spend_question(
            bearer.grant_id, question_key, message_hash, expected_version=bearer.version
        )
        return PaidQuestion(_context(spent.grant, bearer), spent.conversation_id)

    async def verify(
            self,
            credentials: HTTPAuthorizationCredentials | None,
            tokens: TokenRepository,
            sessions: RefreshSessionRepository,
    ) -> TokenContext:
        """
        Same checks, no spending. What /session is built on.

        Deliberately does *not* raise when the quota is gone: a hirer with none
        left still has a valid session and is precisely the person who needs to
        be told how many they have. Reporting zero is the answer, not a 429.
        """
        bearer = await self._authenticate(credentials, sessions)
        grant = await active_grant(tokens, bearer.grant_id, expected_version=bearer.version)
        return _context(grant, bearer)

    async def _authenticate(
            self,
            credentials: HTTPAuthorizationCredentials | None,
            sessions: RefreshSessionRepository,
    ) -> Bearer:
        """
        Everything both checks do before they diverge: prove the bearer, work
        out which grant it names, and for v2 prove the session is still live.

        Shared so that reading the quota and spending it cannot drift apart on
        what counts as a valid token — an endpoint that reported a usable session
        which the next request then rejected would be worse than no endpoint.
        """
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise MissingCredentials()

        claims = self.codec.decode(credentials.credentials)

        if claims.version == TokenVersion.V1:
            return Bearer(claimed_id(claims.jti, "jti"), TokenVersion.V1)

        if claims.version == TokenVersion.V2:
            # A claim or refresh token is validly signed and would otherwise sail
            # through: only typ="access" may buy a message.
            if claims.typ != "access":
                logger.warning("Non-access token presented at chat", extra={"typ": claims.typ})
                raise NotAnAccessToken()
            grant_id = claimed_id(claims.tid, "tid")
            session_id = claimed_id(claims.sid, "sid")
            # Checked before the quota is consumed, so a token from a session cut
            # for replay is rejected without costing the hirer a question. The
            # cost is one extra read per v2 request; the alternative is honouring
            # a stolen access token for the rest of its lifetime.
            await _require_live_session(session_id, grant_id, sessions)
            return Bearer(grant_id, TokenVersion.V2, session_id)

        logger.warning("Unknown token version", extra={"ver": claims.ver})
        raise UnsupportedTokenVersion()


async def _require_live_session(
        session_id: uuid.UUID, grant_id: uuid.UUID, sessions: RefreshSessionRepository
) -> None:
    session = await sessions.get(session_id)
    if session is None or session.token_id != grant_id:
        logger.warning("Access token names an unknown session", extra={"session_id": session_id})
        raise InvalidToken()
    if session.revoked_at is not None:
        # Revoked is revoked, rotated included: an access token dies with the
        # refresh token it was minted alongside. Sparing rotated rows would leave
        # a hole — after replay detection cuts a grant, an access token from an
        # *earlier* rotation of that same session would still have a
        # live-looking row behind it. The client is handed a fresh access token
        # by the same call that rotates, so the strict rule costs it nothing but
        # a retry on an in-flight request.
        logger.warning("Access token belongs to a revoked session", extra={"session_id": session_id})
        raise SessionRevoked()
    if session.expires_at <= datetime.now(timezone.utc):
        logger.warning("Access token belongs to an expired session", extra={"session_id": session_id})
        raise SessionRevoked("Session expired")


def _context(grant: Grant, bearer: Bearer) -> TokenContext:
    return TokenContext(
        sub=grant.subject,
        jti=str(grant.id),
        max_queries=grant.max_queries,
        used_queries=grant.used_queries,
        remaining_queries=max(grant.max_queries - grant.used_queries, 0),
        version=bearer.version,
        session_id=str(bearer.session_id) if bearer.session_id else None,
        expires_at=grant.expires_at,
    )
