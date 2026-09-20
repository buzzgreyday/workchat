"""
What every LogRecord gets on its way to a handler: the correlation ids, and a
pass that keeps secrets and contact details out of the line.

CorrelationFilter sets its attributes unconditionally — defaulting to "-" — so a
format string may reference %(request_id)s without risking a KeyError on records
emitted outside a request. That is the same shape config_otel.json already
assumes for %(trace_id)s / %(span_id)s, which is what makes the OTel step
additive.
"""
import logging
from typing import Any

from app.common.context import conversation_id_var, request_id_var, token_sub_var

MISSING = "-"
REDACTED = "[redacted]"

# Field names that must never reach a log line, wherever they appear in an
# extra={...} — including nested inside one, which is how a whole ORM-shaped
# dict used to carry a token_hash and a hirer's email out of the issue path.
SENSITIVE_KEYS = frozenset(
    {
        "email",
        "phone",
        "password",
        "secret",
        "token",
        "token_hash",
        "access_token",
        "refresh_token",
        "claim_token",
        "raw_token",
        "api_key",
        "authorization",
    }
)

# LogRecord's own mutable attributes, left alone. Rebuilding `args` as a list
# would break record.getMessage(), which does `msg % args`.
_UNTOUCHED = frozenset({"msg", "args", "exc_info", "exc_text", "stack_info"})

# Deep enough for the nested dicts this codebase logs, shallow enough that a
# self-referencing structure cannot spin.
_MAX_DEPTH = 6


def _scrub(key: str | None, value: object, depth: int = 0) -> Any:
    """
    One extra value, with anything sensitive replaced.

    A sensitive key holding a scalar is redacted outright. A sensitive key
    holding a *dict* is recursed into instead, because the useful case is a
    record-shaped payload whose leaves are what matter — redacting the whole
    thing would lose the ids that make a line worth keeping.

    Returns copies, never the caller's own containers: an extra={} is live
    application state, and a filter that edited it in place would corrupt it.
    """
    if depth > _MAX_DEPTH:
        return REDACTED
    if isinstance(value, dict):
        return {k: _scrub(str(k), v, depth + 1) for k, v in value.items()}
    if key is not None and key.lower() in SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, (list, tuple, set)):
        return [_scrub(None, v, depth + 1) for v in value]
    return value


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or MISSING
        record.conversation_id = conversation_id_var.get() or MISSING
        record.token_sub = token_sub_var.get() or MISSING
        return True


class RedactionFilter(logging.Filter):
    """
    Keeps credential material and contact details out of the log.

    The call sites are already written not to pass them; this is what stops the
    next one. Logs are the only store here with no retention policy, no
    redaction endpoint and no scrub job, so a detail that reaches one is there
    for as long as the logs are — which is why this is enforced at the handler
    rather than trusted to reviewers.

    Fails closed. If scrubbing a value raises, the value is dropped rather than
    emitted, because the whole point is that the unscrubbed version must not be
    what survives an error.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in list(record.__dict__.items()):
            if key in _UNTOUCHED or key.startswith("_"):
                continue
            try:
                record.__dict__[key] = _scrub(key, value)
            except Exception:
                record.__dict__[key] = REDACTED
        return True
