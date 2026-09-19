import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class User(BaseModel):
    """
    A user as the rest of the app sees one, independent of how it is stored.

    `from_attributes` is what lets the repository hand back `User.model_validate(row)`
    so a `DatabaseUser` never leaves the repository layer.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str = Field(max_length=255, min_length=1)
    email: EmailStr | None = None
    # Matches IssueTokenRequest.phone rather than the column's String(255): the
    # value always arrives through that request, and a model stricter than the
    # column would reject rows the database happily holds.
    phone: str | None = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
