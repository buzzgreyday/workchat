"""
Capturing what a turn did, without the turn knowing.

A pass-through generator: every event goes out unchanged, and what the recorder
learns on the way is enough to write the transcript however the turn ends —
completed, aborted or failed. The loop upstream never mentions persistence.

Accumulating as events pass is what makes an abort recordable. The reply is
built a token at a time rather than read off the terminal event, because when a
client hangs up mid-answer that event never arrives and the partial is exactly
what is worth keeping.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace

from app.common.config import get_settings
from app.common.context import conversation_id_var
from app.common.logging.logging import logger
from app.common.models import TokenContext
from app.repositories.base import ReplyOutcome, TranscriptRepository
from app.services.chat.events import (
    RoundFinished,
    TokenProduced,
    ToolInvoked,
    TurnEvent,
    TurnFinished,
)


async def record_question(
    transcripts: TranscriptRepository | None,
    token: TokenContext,
    message: str,
    conversation_id: uuid.UUID | None,
    endpoint: str,
    request_id: str,
) -> uuid.UUID | None:
    """
    Store the question before the model is called.

    The swallow lives here rather than in the repository: *nothing* about
    capturing a transcript may cost the hirer a reply, and this is the layer
    that knows a reply is at stake. It also covers what a repository could
    not — a malformed jti reaching UUID().
    """
    if transcripts is None:
        return None
    try:
        stored = await transcripts.record_question(
            token_id=uuid.UUID(token.jti),
            conversation_id=conversation_id,
            message=message,
            endpoint=endpoint,
            request_id=request_id,
        )
    except Exception:
        logger.exception("Failed to record user message", extra={"request_id": request_id})
        return None
    conversation_id_var.set(str(stored))
    return stored


async def recorded(
    events: AsyncIterator[TurnEvent],
    transcripts: TranscriptRepository | None,
    token: TokenContext,
    conversation_id: uuid.UUID | None,
    endpoint: str,
    request_id: str,
) -> AsyncIterator[TurnEvent]:
    """
    Pass events through, then record the reply however the turn ended.

    The finally block may await but must never yield: yielding from a generator
    being closed raises "async generator ignored GeneratorExit". Awaiting there
    is why the transcript repository opens its own connection scope — by the
    time a generator finalises, the request's session is already closed.
    """
    reply = ""
    tool_names: list[str] = []
    finish_reason: str | None = None
    status = "completed"
    error: str | None = None
    started_at = asyncio.get_running_loop().time()

    try:
        async for event in events:
            if isinstance(event, TokenProduced):
                reply += event.text
            elif isinstance(event, ToolInvoked):
                tool_names.append(event.name)
            elif isinstance(event, RoundFinished):
                finish_reason = event.finish_reason
            elif isinstance(event, TurnFinished):
                # The loop does not know where its transcript lives, so the id
                # is attached on the way past.
                event = replace(event, conversation_id=conversation_id)
                _log_completion(event)
            yield event
    except BaseException as exc:  # noqa: BLE001 - re-raised below
        # GeneratorExit/CancelledError arrive here when the client goes away
        # mid-stream; anything else is a genuine failure.
        status = "aborted" if isinstance(exc, (GeneratorExit, asyncio.CancelledError)) else "failed"
        if status == "failed":
            error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if transcripts is not None and conversation_id is not None:
            try:
                await transcripts.record_reply(
                    token_id=uuid.UUID(token.jti),
                    conversation_id=conversation_id,
                    reply=reply,
                    endpoint=endpoint,
                    request_id=request_id,
                    outcome=ReplyOutcome(
                        status=status,
                        finish_reason=finish_reason,
                        tool_names=tool_names,
                        tool_calls_count=len(tool_names),
                        model=get_settings().openai_model,
                        latency_ms=int((asyncio.get_running_loop().time() - started_at) * 1000),
                        error=error,
                    ),
                )
            except Exception:
                logger.exception("Failed to record assistant message", extra={"request_id": request_id})


def _log_completion(event: TurnFinished) -> None:
    """
    The one place a finished turn is announced.

    It used to be written twice — once by the SSE encoder when it happened to
    see an event named "done", once by the JSON path in its own words.
    """
    logger.info("Chat message sent to user", extra={"usage": event.usage.model_dump()})
    if get_settings().log_chat_content:
        logger.debug("Chat message content sent to user", extra={"reply": event.reply})
