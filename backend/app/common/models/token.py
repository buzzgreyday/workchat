import uuid
from datetime import datetime, timezone
from enum import IntEnum

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.common.exceptions import AppError, InvalidToken, TokenExpired, TokenRevoked
from app.common.logging.logging import logger
from app.common.models.utc import UTCDateTime


class TokenVersion(IntEnum):
    """
    Which token flow a grant was issued for.

    V1 is the long-lived JWT delivered as `?token=`, which is the grant itself;
    V2 is a `?claim=` link exchanged for refresh and access tokens. An int enum
    because the number is what the column, the JSON and the `ver` claim carry,
    and it still goes out as that number.
    """

    V1 = 1
    V2 = 2


class Grant(BaseModel):
    """
    One grant, as the rest of the app sees one.

    The domain counterpart of the `tokens` row. Named for what it is rather than
    for the table: in v1 the JWT in the link *was* the grant, in v2 the row
    outlives every token derived from it, and the quota is counted here either
    way.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    subject: str = Field(max_length=255)
    token_hash: str
    max_queries: int
    expires_at: UTCDateTime
    company: str | None = None
    job_title: str | None = None
    used_queries: int = 0
    revoked_at: UTCDateTime | None = None
    claimed_at: UTCDateTime | None = None
    owner_notified_at: UTCDateTime | None = None
    version: TokenVersion = TokenVersion.V1
    # "link" for a grant issued to someone, "trial" for one a visitor opened
    # for themselves (see the tokens.kind column).
    kind: Literal["link", "trial"] = "link"
    created_at: UTCDateTime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def refusal(self, now: datetime, expected_version: TokenVersion | None = None) -> AppError | None:
        """
        Why this grant cannot be used, or None if it can.

        The one statement of it: the auth service asks before exchanging a
        claim, rotating a session or reporting one, and the token store asks
        to explain a spend that did not happen.

        Returned rather than raised, so a caller that raises it keeps the
        traceback at its own call site. Revoked before expired, so the most
        specific reason wins. Quota is deliberately not checked: a grant with
        none left is still a valid grant, and /session reports it as zero.
        """
        if self.revoked_at is not None:
            logger.warning("Revoked token", extra={"token_id": self.id})
            return TokenRevoked()
        if expected_version is not None and self.version != expected_version:
            logger.warning(
                "Token version does not match its grant",
                extra={"token_id": self.id, "expected_version": expected_version, "version": self.version},
            )
            return InvalidToken()
        if self.expires_at <= now:
            logger.warning("Expired token", extra={"token_id": self.id})
            return TokenExpired()
        return None
