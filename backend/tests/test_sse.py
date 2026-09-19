"""The frame format, which the browser parses by hand."""
import json

from app.common import sse


def test_frame_is_one_data_line_terminated_by_a_blank_line():
    out = sse.frame({"type": "token", "value": "hi"})
    assert out.startswith(b"data: "), "the client matches on this prefix exactly"
    assert out.endswith(b"\n\n")
    assert out.count(b"\n") == 2, "a second line in the frame would be dropped by the client"


def test_frame_carries_the_payload_as_json():
    payload = {"type": "done", "reply": "hi", "usage": {"used": 1}}
    body = json.loads(sse.frame(payload).removeprefix(b"data: ").decode())
    assert body == payload


def test_frame_escapes_newlines_in_content():
    """A reply containing a blank line must not look like a frame boundary."""
    out = sse.frame({"type": "token", "value": "one\n\ntwo"})
    assert out.count(b"\n\n") == 1
