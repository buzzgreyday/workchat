"""
Bits every table in this backend needs.

Private to the package: nothing outside `sql` should reach for these, because
each is a statement about SQLAlchemy or about a column, not about the domain.
"""

from typing import Any, cast

from sqlalchemy import CursorResult, Result


def _rowcount(result: Result[Any]) -> int:
    """
    How many rows a statement touched.

    `session.execute()` is typed as returning `Result`, which has no `rowcount`;
    a DML statement actually returns a `CursorResult`, which does. Narrowing it
    once here beats a cast at each of the half-dozen call sites, and puts the
    reason in one place rather than none.
    """
    return cast("CursorResult[Any]", result).rowcount


MAX_CONTENT_CHARS = 16000
MAX_ERROR_CHARS = 255
MAX_TOOL_NAMES_CHARS = 255


def _truncate(text: str | None, limit: int) -> tuple[str | None, int]:
    """Returns (clipped_text, truncated_flag)."""
    if text is None:
        return None, 0
    if len(text) <= limit:
        return text, 0
    return text[:limit], 1
