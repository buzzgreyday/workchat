import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


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
    expires_at: datetime
    company: str | None = None
    job_title: str | None = None
    used_queries: int = 0
    revoked_at: datetime | None = None
    claimed_at: datetime | None = None
    owner_notified_at: datetime | None = None
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))