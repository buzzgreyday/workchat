"""
Minting and reading tokens: the one place that knows the signing key.

Minting happens for three callers — admin issue, claim, refresh — that must
agree on the claim shape exactly, which is why it is a class with the key and
the two lifetimes as its state rather than functions handed them each time.
"""

import hmac
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
from pydantic import ValidationError

from app.common.config import ALGORITHM, Settings
from app.common.crypto import hash_token
from app.common.exceptions import InvalidToken, TokenExpired
from app.common.logging.logging import logger
from app.common.models import JWT, Grant, RefreshSession, TokenClaims, TokenPair, TokenVersion


@dataclass(frozen=True, slots=True)
class NewSession:
    """A session's first token pair, and the row that stores its refresh token."""

    row: RefreshSession
    pair: TokenPair


class TokenCodec:
    """Everything that signs a token or checks a signature."""

    def __init__(
            self,
            secret_key: str,
            access_ttl_seconds: int,
            refresh_ttl_seconds: int,
            algorithm: str = ALGORITHM,
    ) -> None:
        self.secret_key = secret_key
        self.access_ttl_seconds = access_ttl_seconds
        self.refresh_ttl_seconds = refresh_ttl_seconds
        self.algorithm = algorithm

    @classmethod
    def from_settings(cls, settings: Settings) -> "TokenCodec":
        return cls(
            secret_key=settings.secret_key,
            access_ttl_seconds=settings.access_token_ttl_seconds,
            refresh_ttl_seconds=settings.refresh_token_ttl_seconds,
        )

    def decode(self, raw_token: str) -> TokenClaims:
        """Signature, expiry and shape only. What the claims *mean* is decided
        by the caller, because a claim token and an access token are both
        validly signed and only one of them may buy a chat message.

        A claim set that will not parse is an invalid token rather than a
        server error: `TokenClaims` holds every field optional, so the only way
        to fail it is a claim of the wrong type — `ver: true` being the one that
        matters, since a lax field would read it as version 1."""
        try:
            payload = jwt.decode(raw_token, self.secret_key, algorithms=[self.algorithm])
        except jwt.ExpiredSignatureError:
            raise TokenExpired()
        except jwt.InvalidTokenError:
            raise InvalidToken()
        try:
            return TokenClaims.model_validate(payload)
        except ValidationError:
            logger.warning("Token claims will not parse")
            raise InvalidToken()

    def mint_grant_token(
            self,
            subject: str,
            token_id: uuid.UUID,
            issued_at: int,
            expires_at: int,
            max_queries: int,
            version: TokenVersion = TokenVersion.V1,
    ) -> str:
        """
        The token that goes in the link the hirer receives.

        v1 mints the access token itself, with `jti` doubling as the grant id.
        v2 mints a claim token instead: same delivery, but all it buys is one
        call to /v2/auth/claim.

        `max_queries` on a v1 token is vestigial: nothing reads it back, because
        the quota that matters is the one in the grant row and a token cannot
        count. It stays because the v1 claim set is frozen — those links are in
        inboxes and on printed QR codes, and a token minted today has to be
        claim-for-claim what one minted last year was.
        """
        if version == TokenVersion.V1:
            return self._sign(JWT(
                sub=subject,
                iat=issued_at,
                exp=expires_at,
                jti=str(token_id),
                max_queries=max_queries,
            ))

        return self._sign(JWT(
            sub=subject,
            iat=issued_at,
            exp=expires_at,
            jti=str(uuid.uuid4()),
            max_queries=None,
            ver=TokenVersion.V2,
            typ="claim",
            tid=str(token_id),
        ))

    def new_session(self, grant: Grant) -> NewSession:
        """
        A fresh session on a grant: its refresh and access tokens, and the row
        the refresh token is stored as.

        Mints only. Storing the row — as a first session, or as the successor
        in a rotation — is the caller's decision, and so is whether to.
        """
        now_ts = int(time.time())
        session_id = uuid.uuid4()
        refresh_exp = _clamped_exp(now_ts, self.refresh_ttl_seconds, grant.expires_at)
        access_exp = _clamped_exp(now_ts, self.access_ttl_seconds, grant.expires_at)

        refresh_token = self._sign(JWT(
            sub=grant.subject,
            iat=now_ts,
            exp=refresh_exp,
            # The refresh token's jti *is* its row: rotation needs to find the
            # row from the token without a second lookup by hash.
            jti=str(session_id),
            max_queries=None,
            ver=TokenVersion.V2,
            typ="refresh",
            tid=str(grant.id),
        ))
        access_token = self._sign(JWT(
            sub=grant.subject,
            iat=now_ts,
            exp=access_exp,
            jti=str(uuid.uuid4()),
            max_queries=grant.max_queries,
            ver=TokenVersion.V2,
            typ="access",
            tid=str(grant.id),
            sid=str(session_id),
            knd=grant.kind,
        ))

        return NewSession(
            row=RefreshSession(
                id=session_id,
                token_id=grant.id,
                token_hash=hash_token(refresh_token),
                expires_at=datetime.fromtimestamp(refresh_exp, tz=timezone.utc),
            ),
            pair=TokenPair(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=access_exp - now_ts,
                refresh_expires_in=refresh_exp - now_ts,
            ),
        )

    def _sign(self, claims: JWT) -> str:
        return claims.generate(self.secret_key, self.algorithm)


def _clamped_exp(now_ts: int, ttl_seconds: int, grant_expires_at: datetime) -> int:
    """
    A derived token never outlives its grant.

    Without this a refresh token minted an hour before the grant lapses would
    still be rotating a week later, quietly extending an access window that was
    supposed to have a hard end date.
    """
    return min(now_ts + ttl_seconds, int(grant_expires_at.timestamp()))


def claimed_id(value: object, field: str) -> uuid.UUID:
    """An id carried in a claim, or InvalidToken if it is not one."""
    try:
        return uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        logger.warning("Token carries an unusable id", extra={"field": field})
        raise InvalidToken()


def matches_stored(raw_token: str, stored_hash: str) -> bool:
    """A valid signature proves we minted *a* token; this proves it is the one
    still on the row, so revoking or replacing a stored hash actually takes the
    old token out of service."""
    return hmac.compare_digest(hash_token(raw_token), stored_hash)
