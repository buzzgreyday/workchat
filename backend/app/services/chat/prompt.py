"""
Building the message list a turn starts from.

Plain functions: none of this needs an object, and making the clock an argument
is what lets the date injection be tested without freezing time globally.
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, cast

from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from app.common.config import SYSTEM_PROMPT


def system_content(now: datetime | None = None) -> str:
    """
    The system prompt plus today's date.

    Without it the model falls back on its training cutoff — it was telling
    hirers "today is in early 2025" and miscalculating role tenure from there.
    Added here rather than in system-prompt.md because that file is gitignored
    and a hardcoded date would go stale the next day.
    """
    today = now or datetime.now(timezone.utc)
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Today's date is {today.strftime('%A, %d %B %Y')}. Use it whenever a "
        f"question depends on the current date — the length of a role, how "
        f"recent something is, or whether a date is past or future. Never "
        f"assume the date from your training data."
    )


def build_messages(message: str, history: Sequence[dict[str, Any]] | None) -> list[ChatCompletionMessageParam]:
    """The system prompt, the client's history, then what was just asked."""
    # Annotated rather than cast: a literal that has to satisfy the TypedDict is
    # checked against it, where `| dict` merely widened the type until the
    # checker stopped looking.
    system_message: ChatCompletionSystemMessageParam = {"role": "system", "content": system_content()}
    user_message: ChatCompletionUserMessageParam = {"role": "user", "content": message}
    return [system_message, *strip_system(history), user_message]


def strip_system(
    messages: Sequence[ChatCompletionMessageParam] | Sequence[dict[str, Any]] | None,
) -> list[ChatCompletionMessageParam]:
    """
    The system prompt is backend-only: it never leaves the API and is re-added
    on every request.

    Used in both directions — inbound client history and the outbound history a
    turn hands back — which is why it accepts either shape. Client history
    arrives off the wire as plain dicts, while a turn holds SDK message params.
    """
    kept = [m for m in (messages or []) if _role(m) != "system"]
    return cast(list[ChatCompletionMessageParam], kept)


def _role(message: ChatCompletionMessageParam | dict[str, Any]) -> str | None:
    return message.get("role") if isinstance(message, dict) else getattr(message, "role", None)
