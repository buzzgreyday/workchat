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

Per-grant usage is enforced by an atomic UPDATE in the tokens table
(see services/db.update_token_used_query_count), not in-memory, so it
survives restarts and works across replicas.
"""

import hmac
import time
import uuid
from datetime import datetime, timezone

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import (
    ACCESS_TOKEN_TTL_SECONDS,
    ADMIN_KEY,
    ALGORITHM,
    REFRESH_TOKEN_TTL_SECONDS,
    SECRET_KEY,
)
from app.common.db import get_db
from app.common.exceptions import (
    AdminForbidden,
    ClaimAlreadyUsed,
    InvalidRefreshToken,
    InvalidToken,
    MissingCredentials,
    NotAClaimToken,
    NotAnAccessToken,
    NotARefreshToken,
    RefreshTokenReplayed,
    SessionRevoked,
    TokenExpired,
    UnsupportedTokenVersion,
)
from app.common.logging.logging import logger
from app.common.models import JWT, TokenContext, TokenPair
from app.common.schemas import DatabaseToken
from app.services.db import (
    claim_grant_once,
    create_refresh_token,
    get_active_grant,
    get_refresh_token,
    hash_token,
    rotate_refresh_token,
    should_notify_owner,
    update_token_used_query_count,
)
from app.services.notify import notifier

bearer_scheme = HTTPBearer(auto_error=False)


class Auth:
    """
    Everything that mints or verifies a token.

    A class rather than loose functions because the v2 flow has state worth
    naming — the signing key, the two lifetimes — and because minting now
    happens in three places (admin issue, claim, refresh) that must agree on the
    claim shape exactly. Tests construct one with a short TTL instead of
    monkeypatching module globals.

    The bound methods are used directly as FastAPI dependencies; see the module
    level aliases at the bottom, which keep `from app.services.auth import
    verify_and_consume` working for the callers that already do it.
    """

    def __init__(
            self,
            secret_key: str = SECRET_KEY,
            algorithm: str = ALGORITHM,
            admin_key: str = ADMIN_KEY,
            access_ttl_seconds: int = ACCESS_TOKEN_TTL_SECONDS,
            refresh_ttl_seconds: int = REFRESH_TOKEN_TTL_SECONDS,
    ):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.admin_key = admin_key
        self.access_ttl_seconds = access_ttl_seconds
        self.refresh_ttl_seconds = refresh_ttl_seconds

    # --- decoding primitives -------------------------------------------------

    def decode(self, raw_token: str) -> dict:
        """Signature and expiry only. What the claims *mean* is decided by the
        caller, because a claim token and an access token are both validly
        signed and only one of them may buy a chat message."""
        try:
            return jwt.decode(raw_token, self.secret_key, algorithms=[self.algorithm])
        except jwt.ExpiredSignatureError:
            raise TokenExpired()
        except jwt.InvalidTokenError:
            raise InvalidToken()

    @staticmethod
    def version_of(payload: dict) -> int:
        """No `ver` means v1. The tokens in the wild predate the claim and can
        never grow one, so their silence has to keep meaning version 1."""
        ver = payload.get("ver")
        # bool is an int in Python, and `ver: true` would otherwise compare equal
        # to 1 and be waved through as a v1 token.
        if isinstance(ver, bool) or not isinstance(ver, int):
            return 1
        return ver

    @staticmethod
    def _uuid(value, field: str) -> uuid.UUID:
        try:
            return uuid.UUID(value)
        except (AttributeError, TypeError, ValueError):
            logger.warning("Token carries an unusable id", extra={"field": field})
            raise InvalidToken()

    @staticmethod
    def _matches(raw_token: str, stored_hash: str) -> bool:
        """A valid signature proves we minted *a* token; this proves it is the
        one still on the row, so revoking or replacing a stored hash actually
        takes the old token out of service."""
        return hmac.compare_digest(hash_token(raw_token), stored_hash)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    # --- minting -------------------------------------------------------------

    def _clamped_exp(self, now_ts: int, ttl_seconds: int, grant_expires_at: datetime) -> int:
        """
        A derived token never outlives its grant.

        Without this a refresh token minted an hour before the grant lapses
        would still be rotating a week later, quietly extending an access
        window that was supposed to have a hard end date.
        """
        grant_exp_ts = int(self._as_utc(grant_expires_at).timestamp())
        return min(now_ts + ttl_seconds, grant_exp_ts)

    def mint_grant_token(
            self,
            subject: str,
            token_id: uuid.UUID,
            issued_at: int,
            expires_at: int,
            max_queries: int,
            version: int = 1,
    ) -> str:
        """
        The token that goes in the link the hirer receives.

        v1 mints the access token itself, with `jti` doubling as the grant id.
        v2 mints a claim token instead: same delivery, but all it buys is one
        call to /v2/auth/claim.
        """
        if version == 1:
            return JWT(
                sub=subject,
                iat=issued_at,
                exp=expires_at,
                jti=str(token_id),
                max_queries=max_queries,
            ).generate(self.secret_key, self.algorithm)

        return JWT(
            sub=subject,
            iat=issued_at,
            exp=expires_at,
            jti=str(uuid.uuid4()),
            max_queries=None,
            ver=2,
            typ="claim",
            tid=str(token_id),
        ).generate(self.secret_key, self.algorithm)

    def _mint_access(self, grant: DatabaseToken, session_id: uuid.UUID) -> tuple[str, int]:
        now_ts = int(time.time())
        exp_ts = self._clamped_exp(now_ts, self.access_ttl_seconds, grant.expires_at)
        token = JWT(
            sub=grant.subject,
            iat=now_ts,
            exp=exp_ts,
            jti=str(uuid.uuid4()),
            max_queries=grant.max_queries,
            ver=2,
            typ="access",
            tid=str(grant.id),
            sid=str(session_id),
        ).generate(self.secret_key, self.algorithm)
        return token, exp_ts - now_ts

    def _mint_refresh(
            self, grant: DatabaseToken, session_id: uuid.UUID
    ) -> tuple[str, datetime, int]:
        now_ts = int(time.time())
        exp_ts = self._clamped_exp(now_ts, self.refresh_ttl_seconds, grant.expires_at)
        token = JWT(
            sub=grant.subject,
            iat=now_ts,
            exp=exp_ts,
            # The refresh token's jti *is* its row: rotation needs to find the
            # row from the token without a second lookup by hash.
            jti=str(session_id),
            max_queries=None,
            ver=2,
            typ="refresh",
            tid=str(grant.id),
        ).generate(self.secret_key, self.algorithm)
        return token, datetime.fromtimestamp(exp_ts, tz=timezone.utc), exp_ts - now_ts

    # --- v2 endpoints --------------------------------------------------------

    async def claim(self, raw_claim: str, db: AsyncSession) -> TokenPair:
        """
        Exchange a claim token for a session. Once, and only once.

        The link is a one-shot: whoever presents it first gets the session, and
        every later presentation is refused. That makes a leaked URL — sitting in
        a browser history, a mail thread, a photographed QR code — worth far less
        than a reusable one, at the cost of a hirer who clears their site data or
        moves device needing a new link. The operator is told when that happens,
        since only they can issue one.

        Costs no quota; questions are what quota is for.
        """
        payload = self.decode(raw_claim)
        if self.version_of(payload) != 2 or payload.get("typ") != "claim":
            logger.warning("Non-claim token presented at claim", extra={"typ": payload.get("typ")})
            raise NotAClaimToken()

        grant_id = self._uuid(payload.get("tid"), "tid")
        grant = await get_active_grant(grant_id, db)

        if grant.version != 2 or not self._matches(raw_claim, grant.token_hash):
            logger.warning("Claim token does not match its grant", extra={"token_id": grant_id})
            raise InvalidToken()

        if not await claim_grant_once(grant_id, db):
            await self._notify_owner(
                grant.id, grant.subject, grant.company, db,
                event="claim_reuse", reason="claim link presented after it was spent",
            )
            raise ClaimAlreadyUsed()

        session_id = uuid.uuid4()
        refresh_token, refresh_expires_at, refresh_expires_in = self._mint_refresh(grant, session_id)
        await create_refresh_token(
            token_id=grant.id,
            raw_token=refresh_token,
            expires_at=refresh_expires_at,
            db=db,
            refresh_id=session_id,
        )
        access_token, expires_in = self._mint_access(grant, session_id)

        logger.info(
            "Claim exchanged for a session",
            extra={"token_id": grant.id, "session_id": session_id, "subject": grant.subject},
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            refresh_expires_in=refresh_expires_in,
        )

    async def refresh(self, raw_refresh: str, db: AsyncSession) -> TokenPair:
        """
        Rotate a session: one refresh token in, a fresh pair out.

        The old token dies on use, which is what makes a replay detectable — see
        rotate_refresh_token, which cuts every session on the grant when it sees
        one outside the grace window, and answers 409 inside it. Like claim, this
        costs no quota.
        """
        payload = self.decode(raw_refresh)
        if self.version_of(payload) != 2 or payload.get("typ") != "refresh":
            logger.warning("Non-refresh token presented at refresh", extra={"typ": payload.get("typ")})
            raise NotARefreshToken()

        session_id = self._uuid(payload.get("jti"), "jti")
        grant_id = self._uuid(payload.get("tid"), "tid")
        grant = await get_active_grant(grant_id, db)

        session = await get_refresh_token(session_id, db)
        # The token_id check stops a refresh token being spent against a grant
        # it does not belong to, which is what would let one hirer's session
        # mint access to another hirer's quota.
        if session is None or session.token_id != grant_id:
            logger.warning("Unknown refresh session", extra={"session_id": session_id, "token_id": grant_id})
            raise InvalidRefreshToken()
        if not self._matches(raw_refresh, session.token_hash):
            logger.warning("Refresh token does not match its session", extra={"session_id": session_id})
            raise InvalidRefreshToken()

        successor_id = uuid.uuid4()
        refresh_token, refresh_expires_at, refresh_expires_in = self._mint_refresh(grant, successor_id)
        # Snapshot who this grant belongs to before rotating. The replay branch
        # rolls back, which expires every object loaded in this session, and
        # reading grant.subject afterwards would attempt lazy IO outside the
        # async context and raise MissingGreenlet instead of notifying anyone.
        owner = (grant.id, grant.subject, grant.company)
        try:
            successor = await rotate_refresh_token(
                refresh_id=session_id,
                raw_new_token=refresh_token,
                new_expires_at=refresh_expires_at,
                db=db,
                new_refresh_id=successor_id,
            )
        except RefreshTokenReplayed:
            # The sessions are already cut by the time this lands. All that is
            # left is telling the operator, because a single-use claim leaves the
            # hirer no way back in on their own.
            await self._notify_owner(
                *owner, db, event="sessions_cut", reason="refresh token replayed after rotation"
            )
            raise

        access_token, expires_in = self._mint_access(grant, successor.id)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            refresh_expires_in=refresh_expires_in,
        )

    async def _notify_owner(
            self,
            token_id: uuid.UUID,
            subject: str,
            company: str | None,
            db: AsyncSession,
            event: str,
            reason: str,
    ) -> None:
        """
        Tell the operator a hirer is locked out, at most once per grant per window.

        Takes plain values rather than the grant row because one caller reaches
        here after a rollback, where that row's attributes are no longer safe to
        touch. Never raises: nothing about notifying anyone may change what the
        caller returns, and the hirer's answer is already decided by this point.
        """
        try:
            if not await should_notify_owner(token_id, db):
                return
            if event == "claim_reuse":
                await notifier.claim_link_reused(token_id, subject, company)
            else:
                await notifier.sessions_cut(token_id, subject, company, reason)
        except Exception:
            logger.exception("Failed to notify owner", extra={"token_id": token_id, "event": event})

    # --- request-time verification -------------------------------------------

    async def _authenticate(
            self,
            credentials: HTTPAuthorizationCredentials | None,
            db: AsyncSession,
    ) -> tuple[uuid.UUID, int, uuid.UUID | None]:
        """
        Everything both dependencies do before they diverge: prove the bearer,
        work out which grant it names, and for v2 prove the session is still
        live. Returns (grant_id, version, session_id).

        Shared so that reading the quota and spending it cannot drift apart on
        what counts as a valid token — an endpoint that reported a usable session
        which the next request then rejected would be worse than no endpoint.
        """
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise MissingCredentials()

        raw_token = credentials.credentials  # already stripped of "Bearer " prefix
        payload = self.decode(raw_token)
        version = self.version_of(payload)

        if version == 1:
            return self._uuid(payload.get("jti"), "jti"), version, None

        if version == 2:
            # A claim or refresh token is validly signed and would otherwise sail
            # through: only typ="access" may buy a message.
            if payload.get("typ") != "access":
                logger.warning("Non-access token presented at chat", extra={"typ": payload.get("typ")})
                raise NotAnAccessToken()
            grant_id = self._uuid(payload.get("tid"), "tid")
            session_id = self._uuid(payload.get("sid"), "sid")
            # Checked before the quota is consumed, so a token from a session cut
            # for replay is rejected without costing the hirer a question. The
            # cost is one extra read per v2 request; the alternative is honouring
            # a stolen access token for the rest of its lifetime.
            await self._require_live_session(session_id, grant_id, db)
            return grant_id, version, session_id

        logger.warning("Unknown token version", extra={"ver": payload.get("ver")})
        raise UnsupportedTokenVersion()

    @staticmethod
    def _context(row, version: int, session_id: uuid.UUID | None) -> TokenContext:
        return TokenContext(
            sub=row.subject,
            jti=str(row.id),
            max_queries=row.max_queries,
            used_queries=row.used_queries,
            remaining_queries=max(row.max_queries - row.used_queries, 0),
            version=version,
            session_id=str(session_id) if session_id else None,
            expires_at=Auth._as_utc(row.expires_at),
        )

    async def verify_and_consume(
            self,
            credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
            db: AsyncSession = Depends(get_db),
    ) -> TokenContext:
        """
        The chat endpoints' dependency. Accepts a v1 or a v2 access token and
        spends one query from the grant either way.
        """
        grant_id, version, session_id = await self._authenticate(credentials, db)
        row = await update_token_used_query_count(
            token_id=grant_id, db=db, expected_version=version
        )
        return self._context(row, version, session_id)

    async def verify(
            self,
            credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
            db: AsyncSession = Depends(get_db),
    ) -> TokenContext:
        """
        Same checks, no spending. What /session is built on.

        Deliberately does *not* raise when the quota is gone: a hirer with none
        left still has a valid session and is precisely the person who needs to
        be told how many they have. Reporting zero is the answer, not a 429.
        """
        grant_id, version, session_id = await self._authenticate(credentials, db)
        row = await get_active_grant(grant_id, db, expected_version=version)
        return self._context(row, version, session_id)

    async def _require_live_session(
            self, session_id: uuid.UUID, grant_id: uuid.UUID, db: AsyncSession
    ) -> None:
        session = await get_refresh_token(session_id, db)
        if session is None or session.token_id != grant_id:
            logger.warning("Access token names an unknown session", extra={"session_id": session_id})
            raise InvalidToken()
        if session.revoked_at is not None:
            # Revoked is revoked, rotated included: an access token dies with the
            # refresh token it was minted alongside. Sparing rotated rows here
            # would have left a hole — after replay detection cuts a grant, an
            # access token from a *earlier* rotation of that same session would
            # still have had a live-looking row behind it. The client is handed a
            # fresh access token by the same call that rotates, so the strict rule
            # costs it nothing but a retry on an in-flight request.
            logger.warning("Access token belongs to a revoked session", extra={"session_id": session_id})
            raise SessionRevoked()
        if self._as_utc(session.expires_at) <= datetime.now(timezone.utc):
            logger.warning("Access token belongs to an expired session", extra={"session_id": session_id})
            raise SessionRevoked("Session expired")

    # --- admin ---------------------------------------------------------------

    def require_admin(self, x_admin_key: str = Header(...)) -> None:
        """FastAPI dependency for the token-issuing endpoint. Only you should
        be able to mint tokens — protect this with a secret only you know."""
        # compare_digest avoids leaking key length / prefix through response timing.
        if not hmac.compare_digest(x_admin_key.encode(), self.admin_key.encode()):
            raise AdminForbidden()


auth = Auth()

# Bound-method aliases so existing imports keep working unchanged. FastAPI reads
# a bound method's signature with `self` already applied, so these are usable as
# dependencies exactly as the plain functions they replaced were.
verify_and_consume = auth.verify_and_consume
require_admin = auth.require_admin
