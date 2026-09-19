import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from app.common.models.utc import UTCDateTime


class RefreshSession(BaseModel):
    """
    One session within a grant, as the rest of the app sees one.

    A hirer who opens the claim link on two devices has two of these, each
    rotating independently. Rows are kept rather than updated in place:
    `rotated_to` chains a session's history, which is what lets a refresh token
    presented after it was spent be recognised as a replay rather than merely
    unknown.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    token_id: uuid.UUID
    token_hash: str
    expires_at: UTCDateTime
    revoked_at: UTCDateTime | None = None
    # Stamped both when a token is rotated away and when it is cut for replay;
    # this is what tells the two apart.
    rotated_to: uuid.UUID | None = None
    last_used_at: UTCDateTime | None = None
    created_at: UTCDateTime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))