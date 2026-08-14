"""
Injects the correlation ids onto every LogRecord.

It sets the attributes unconditionally — defaulting to "-" — so a format string
may reference %(request_id)s without risking a KeyError on records emitted
outside a request. That is the same shape config_otel.json already assumes for
%(trace_id)s / %(span_id)s, which is what makes the OTel step additive.
"""
import logging

from app.common.context import conversation_id_var, request_id_var, token_sub_var

MISSING = "-"


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or MISSING
        record.conversation_id = conversation_id_var.get() or MISSING
        record.token_sub = token_sub_var.get() or MISSING
        return True
