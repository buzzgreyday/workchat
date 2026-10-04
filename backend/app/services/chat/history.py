"""
The history a client sends back, made trustworthy without storing it.

The model is handed the whole conversation every turn, and the client carries
it between turns. Left at that, the history is whatever the client says it is:
earlier "questions" of any length, answers the assistant never gave, a whole
prompt smuggled in as a past turn — each paid for on every model call after it.

So the server signs the history it hands back (HMAC), bound to the grant and the
conversation, and on the next turn believes a history only if the signature
holds. Anything else is dropped and the turn starts a new conversation, which is
what already happens to a conversation id that is not the caller's. Nothing is
stored to make this work, and nothing caps how long a conversation or a reply
may grow: a signed history is one the server wrote, however long it is.

Resending an older history of one's own conversation still verifies. That is
harmless — it only drops the turns after it.
"""

import hashlib
import hmac
import json
import uuid
from typing import Any


def sign(
    key: str,
    grant_id: str,
    conversation_id: uuid.UUID | None,
    history: list[dict[str, Any]],
) -> str:
    message = "\n".join([grant_id, str(conversation_id or ""), _canonical(history)])
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify(
    key: str,
    grant_id: str,
    conversation_id: uuid.UUID | None,
    history: list[dict[str, Any]],
    signature: str | None,
) -> bool:
    """Whether this history is one the server handed this grant, in this
    conversation. An empty history needs no signature: there is nothing in it
    to forge."""
    if not history:
        return True
    if not signature:
        return False
    return hmac.compare_digest(signature, sign(key, grant_id, conversation_id, history))


def _canonical(history: list[dict[str, Any]]) -> str:
    """
    One spelling of a history, whatever the client's JSON looked like.

    Sorted keys and no whitespace, so the bytes signed on the way out are the
    bytes recomputed on the way back in even after a client has parsed and
    re-serialised them. Not ASCII-escaped, which would sign the same text two
    ways depending on who wrote it.
    """
    return json.dumps(history, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
