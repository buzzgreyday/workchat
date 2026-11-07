"""
The v2 session flow: a claim link exchanged once, then a refresh token rotated.

Neither step costs quota; questions are what quota is for.
"""

from collections.abc import Awaitable, Callable

from app.common.exceptions import (
    ClaimAlreadyUsed,
    InvalidRefreshToken,
    InvalidToken,
    NotAClaimToken,
    NotARefreshToken,
    RefreshTokenReplayed,
)
from app.common.logging.logging import logger
from app.common.models import Grant, TokenPair, TokenVersion
from app.repositories.base import RefreshSessionRepository, TokenRepository
from app.services.auth.grants import active_grant
from app.services.auth.tokens import TokenCodec, claimed_id, matches_stored
from app.services.notify import Notifier


class SessionService:
    """Opening, claiming and rotating sessions on a grant."""

    def __init__(self, codec: TokenCodec, notifier: Notifier) -> None:
        self.codec = codec
        self.notifier = notifier

    async def claim(
            self,
            raw_claim: str,
            tokens: TokenRepository,
            sessions: RefreshSessionRepository,
    ) -> TokenPair:
        """
        Exchange a claim token for a session. Once, and only once.

        The link is a one-shot: whoever presents it first gets the session, and
        every later presentation is refused. That makes a leaked URL — sitting in
        a browser history, a mail thread, a photographed QR code — worth far less
        than a reusable one, at the cost of a hirer who clears their site data or
        moves device needing a new link. The operator is told when that happens,
        since only they can issue one.
        """
        claims = self.codec.decode(raw_claim)
        if claims.version != TokenVersion.V2 or claims.typ != "claim":
            logger.warning("Non-claim token presented at claim", extra={"typ": claims.typ})
            raise NotAClaimToken()

        grant_id = claimed_id(claims.tid, "tid")
        grant = await active_grant(tokens, grant_id)

        if grant.version != TokenVersion.V2 or not matches_stored(raw_claim, grant.token_hash):
            logger.warning("Claim token does not match its grant", extra={"token_id": grant_id})
            raise InvalidToken()

        if not await tokens.claim_once(grant_id):
            await self._tell_owner_once(
                tokens, grant,
                lambda: self.notifier.claim_link_reused(grant.id, grant.subject, grant.company),
            )
            raise ClaimAlreadyUsed()

        pair = await self.open_session(grant, sessions)
        logger.info("Claim exchanged for a session", extra={"token_id": grant.id, "subject": grant.subject})
        return pair

    async def open_session(self, grant: Grant, sessions: RefreshSessionRepository) -> TokenPair:
        """
        A first session on a grant: a refresh token, stored, and an access token.

        What a spent claim link buys, and what a guest trial is opened with — the
        two ways into a grant end in the same pair, so the rest of the app cannot
        tell a session that began with a link from one that began with a trial.

        Checks nothing. The caller has already decided this grant may be opened.
        """
        new = self.codec.new_session(grant)
        await sessions.add(new.row)
        logger.info("Session opened", extra={"token_id": grant.id, "session_id": new.row.id})
        return new.pair

    async def refresh(
            self,
            raw_refresh: str,
            tokens: TokenRepository,
            sessions: RefreshSessionRepository,
    ) -> TokenPair:
        """
        Rotate a session: one refresh token in, a fresh pair out.

        The old token dies on use, which is what makes a replay detectable — see
        RefreshSessionRepository.rotate, which cuts every session on the grant
        when it sees one outside the grace window, and answers 409 inside it.
        """
        claims = self.codec.decode(raw_refresh)
        if claims.version != TokenVersion.V2 or claims.typ != "refresh":
            logger.warning("Non-refresh token presented at refresh", extra={"typ": claims.typ})
            raise NotARefreshToken()

        session_id = claimed_id(claims.jti, "jti")
        grant_id = claimed_id(claims.tid, "tid")
        grant = await active_grant(tokens, grant_id)

        session = await sessions.get(session_id)
        # The token_id check stops a refresh token being spent against a grant
        # it does not belong to, which is what would let one hirer's session
        # mint access to another hirer's quota.
        if session is None or session.token_id != grant_id:
            logger.warning("Unknown refresh session", extra={"session_id": session_id, "token_id": grant_id})
            raise InvalidRefreshToken()
        if not matches_stored(raw_refresh, session.token_hash):
            logger.warning("Refresh token does not match its session", extra={"session_id": session_id})
            raise InvalidRefreshToken()

        successor = self.codec.new_session(grant)
        try:
            await sessions.rotate(session_id, successor.row)
        except RefreshTokenReplayed:
            # The sessions are already cut by the time this lands. All that is
            # left is telling the operator, because a single-use claim leaves the
            # hirer no way back in on their own.
            await self._tell_owner_once(
                tokens, grant,
                lambda: self.notifier.sessions_cut(
                    grant.id, grant.subject, grant.company, "refresh token replayed after rotation"
                ),
            )
            raise
        return successor.pair

    @staticmethod
    async def _tell_owner_once(
            tokens: TokenRepository,
            grant: Grant,
            send: Callable[[], Awaitable[None]],
    ) -> None:
        """
        Tell the operator a hirer is locked out, at most once per grant per window.

        `send` is called only if this call wins the window, so a dead link hit
        in a loop produces one message. Never raises: nothing about notifying
        anyone may change what the caller returns, and the hirer's answer is
        already decided by this point.
        """
        try:
            if await tokens.mark_owner_notified(grant.id):
                await send()
        except Exception:
            logger.exception("Failed to notify owner", extra={"token_id": grant.id})
