import json

from pydantic import BaseModel

from app.common.config import LOG_CHAT_CONTENT
from app.common.logging import logging

logger = logging.logger
def sse_event(event: str, data: dict) -> bytes:
    payload = {
        "type": event,
        **{
            k: v.model_dump() if isinstance(v, BaseModel) else v
            for k, v in data.items()
        },
    }
    if event == "done":
        logger.info(
            "Chat message sent to user",
            extra={"usage": payload.get("usage")}
        )
        if LOG_CHAT_CONTENT:
            logger.debug(
                "Chat message content sent to user",
                extra=payload
            )

    return f"data: {json.dumps(payload)}\n\n".encode()