"""
JSON formatter that actually emits extra={...}.

Lives in its own module rather than beside load_logging_config(): dictConfig
imports the formatter by path while logging.py is still initialising, so keeping
it there is a circular import.
"""
import json
import logging

# LogRecord's own attributes. Anything outside this set arrived via extra={...}
# and is what we actually want to emit.
_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "message", "module", "msecs", "msg", "name",
    "pathname", "process", "processName", "relativeCreated", "stack_info",
    "taskName", "thread", "threadName",
    # injected by CorrelationFilter, rendered explicitly below
    "request_id", "conversation_id", "token_sub",
}


class JsonExtraFormatter(logging.Formatter):
    """
    The previous format string was "%(asctime)s %(name)s %(levelname)s %(message)s",
    so every structured field this codebase carefully passes via extra was silently
    discarded. Callers pass live objects through extra (a FastAPI app in main.py, an
    AsyncOpenAI client, ORM rows), so serialisation must never raise into a request —
    hence default=str rather than a strict encoder.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "conversation_id": getattr(record, "conversation_id", "-"),
            "token_sub": getattr(record, "token_sub", "-"),
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str)
