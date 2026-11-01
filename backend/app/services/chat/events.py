"""
What happens during a turn, said in domain terms.

The old service yielded SSE bytes from inside its tool loop, which is why the
same algorithm existed twice — once for a stream and once for JSON. These are
what it yields instead: a caller that wants frames encodes them, a caller that
wants a transcript reads them, and neither concern reaches the loop.

Not every event has a rendering. `ToolInvoked` and `RoundFinished` exist so the
recorder can know what a turn did even when it is aborted and `TurnFinished`
never arrives — which is the job the mutable instance attributes used to do.

`TurnStarted`, `ModelCalled` and `ToolStarted` are the other way round: nothing
records them, and they exist so the hirer can see the turn is moving before the
first word arrives.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from app.common.models import Usage


@dataclass(frozen=True, slots=True)
class TurnStarted:
    """The stream is open, and the question is about to be read and stored."""


@dataclass(frozen=True, slots=True)
class ModelCalled:
    """A model call is about to go out. A turn has one per round."""


@dataclass(frozen=True, slots=True)
class ToolStarted:
    """
    A tool the model asked for, before it runs.

    `ToolInvoked` says the same afterwards, which is too late to tell anyone
    what the wait is for.
    """

    name: str


@dataclass(frozen=True, slots=True)
class TokenProduced:
    """A fragment of the reply, as the model writes it."""

    text: str


@dataclass(frozen=True, slots=True)
class ToolInvoked:
    """A tool the model asked for, after it ran."""

    name: str


@dataclass(frozen=True, slots=True)
class RoundFinished:
    """One model call completed, and why it stopped."""

    finish_reason: str | None


@dataclass(frozen=True, slots=True)
class TurnFinished:
    """
    The turn completed. Terminal.

    `conversation_id` is filled in by the recorder rather than the loop: where a
    transcript lives is not something the loop should have to know.
    """

    reply: str
    history: list[dict[str, Any]]
    usage: Usage
    finish_reason: str | None = None
    conversation_id: uuid.UUID | None = None
    # The server's signature on `history`, so the client can send it back next
    # turn and be believed (services/chat/history.py). Filled in last, once the
    # conversation it is bound to is known.
    history_signature: str | None = None


@dataclass(frozen=True, slots=True)
class TurnFailed:
    """
    The turn broke. Terminal.

    Carries a message fit to show someone, not the exception — the detail is
    logged where it happened.
    """

    message: str


TurnEvent = (
    TurnStarted
    | ModelCalled
    | ToolStarted
    | TokenProduced
    | ToolInvoked
    | RoundFinished
    | TurnFinished
    | TurnFailed
)
