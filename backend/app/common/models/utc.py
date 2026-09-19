from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BeforeValidator


def as_utc(value: Any) -> Any:
    """
    Read a naive datetime as UTC.

    A driver that does not preserve tzinfo (SQLite, in the tests) hands back
    naive values from a `DateTime(timezone=True)` column. Everything stored is
    UTC, so coercing at the edge of the domain model means nothing downstream
    has to wonder, and a comparison against an aware `now` cannot raise.

    This used to live in three places — a helper in services/db.py, a copy
    inlined in the quota spend, and a static method on Auth. Attaching it to the
    type instead means it cannot be forgotten at a fourth call site.
    """
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


UTCDateTime = Annotated[datetime, BeforeValidator(as_utc)]