"""
Per-request correlation identity.

ContextVars rather than parameters, because the values are needed by the logging
filter, which sits far from any call signature. The ids set here are what tie a
log line to a chat_messages row today, and to a span when OpenTelemetry lands.
"""
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
conversation_id_var: ContextVar[str | None] = ContextVar("conversation_id", default=None)
token_sub_var: ContextVar[str | None] = ContextVar("token_sub", default=None)


def new_request_id() -> str:
    """32 hex chars — W3C trace-id shaped, so OTel can supply this later unchanged."""
    return uuid.uuid4().hex


def current_request_id() -> str:
    """Never None at a call site: mints one if no middleware ran (e.g. in tests)."""
    request_id = request_id_var.get()
    if request_id is None:
        request_id = new_request_id()
        request_id_var.set(request_id)
    return request_id
