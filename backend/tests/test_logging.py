"""
The formatter that makes extra={} visible.

Before this, every structured field the codebase passed via extra was silently
dropped by the format string, so these are the first tests that any of it renders.
"""
import json
import logging

from app.common.context import conversation_id_var, request_id_var, token_sub_var
from app.common.logging.filters import CorrelationFilter
from app.common.logging.formatters import JsonExtraFormatter


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_renders_extra():
    out = json.loads(JsonExtraFormatter().format(_record(usage={"used": 1}, tool="search_cv")))
    assert out["msg"] == "hello"
    assert out["level"] == "INFO"
    assert out["usage"] == {"used": 1}
    assert out["tool"] == "search_cv"


def test_formatter_survives_unserializable_extra():
    """
    main.py logs a FastAPI app and an AsyncOpenAI client through extra, and
    test_admin.py records a past TypeError from logging an ORM row. Those were
    harmless only while extras were dropped — rendering them must not raise.
    """
    class Awkward:
        def __repr__(self):
            return "<awkward>"

    out = json.loads(JsonExtraFormatter().format(_record(obj=Awkward(), fn=len)))
    assert out["obj"] == "<awkward>"
    assert "len" in out["fn"]


def test_formatter_includes_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = _record()
        record.exc_info = sys.exc_info()
        out = json.loads(JsonExtraFormatter().format(record))
    assert "ValueError: boom" in out["exc"]


def test_correlation_filter_injects_ids():
    token = request_id_var.set("abc123")
    conversation = conversation_id_var.set("conv-1")
    sub = token_sub_var.set("test-hire")
    try:
        record = _record()
        assert CorrelationFilter().filter(record) is True
        assert record.request_id == "abc123"
        assert record.conversation_id == "conv-1"
        assert record.token_sub == "test-hire"
    finally:
        request_id_var.reset(token)
        conversation_id_var.reset(conversation)
        token_sub_var.reset(sub)


def test_correlation_filter_defaults_when_unset():
    record = _record()
    CorrelationFilter().filter(record)
    assert record.request_id == "-"
    assert record.conversation_id == "-"
    assert record.token_sub == "-"


async def test_request_id_is_echoed_back(client):
    """The response carries the id, so a log line can be traced from a request."""
    resp = await client.get("/health")
    assert len(resp.headers["x-request-id"]) == 32


async def test_inbound_request_id_is_honoured(client):
    """An upstream id wins, which is how a future traceparent will thread through."""
    resp = await client.get("/health", headers={"X-Request-Id": "f" * 32})
    assert resp.headers["x-request-id"] == "f" * 32
