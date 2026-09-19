import json
from collections.abc import Mapping
from typing import Any


def frame(payload: Mapping[str, Any]) -> bytes:
    """
    One Server-Sent Events frame.

    Deliberately the whole module. The previous version branched on the event
    name to log when a chat turn finished, which put domain observability inside
    a serializer and meant two layers owned the same log line. Encoding a frame
    is all this does; what the frame means is the caller's business.

    The shape is load-bearing: one `data:` line with a single space, terminated
    by a blank line, carrying the event type inside the JSON rather than in an
    SSE `event:` field. The browser client splits on "\\n\\n" and strips
    /^data:\\s*/ by hand, so a second line in the frame would be dropped.
    """
    return f"data: {json.dumps(payload)}\n\n".encode()