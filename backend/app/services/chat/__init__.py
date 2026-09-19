"""
A chat turn, composed.

Three stages, each ignorant of the others: `run_turn` talks to the model,
`recorded` writes the transcript, and the route encodes whatever comes out. This
module only wires them together and decides what a failure looks like from the
outside.
"""

from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.common.context import current_request_id, token_sub_var
from app.common.logging.logging import logger
from app.common.models import ChatRequest, TokenContext, Usage
from app.repositories.base import TranscriptRepository
from app.services.chat.events import (
    RoundFinished,
    TokenProduced,
    ToolInvoked,
    TurnEvent,
    TurnFailed,
    TurnFinished,
)
from app.services.chat.prompt import build_messages
from app.services.chat.recording import record_question, recorded
from app.services.chat.tooling import ChatTooling
from app.services.chat.turn import run_turn

__all__ = [
    "ChatTooling",
    "RoundFinished",
    "TokenProduced",
    "ToolInvoked",
    "TurnEvent",
    "TurnFailed",
    "TurnFinished",
    "answer",
]

# What a hirer is told when a turn breaks. Deliberately fixed: the detail is in the logs.
FAILURE_MESSAGE = "Something went wrong generating that reply. Please try again."


async def answer(
    request: ChatRequest,
    token: TokenContext,
    client: AsyncOpenAI,
    tooling: ChatTooling,
    transcripts: TranscriptRepository | None = None,
    endpoint: str = "/chat/stream",
) -> AsyncIterator[TurnEvent]:
    """
    Everything one question needs, start to finish.

    The question is stored before the model is called, which is what guarantees
    it survives whatever happens next.
    """
    token_sub_var.set(token.sub)
    request_id = current_request_id()

    conversation_id = await record_question(
        transcripts,
        token=token,
        message=request.message,
        conversation_id=request.conversation_id,
        endpoint=endpoint,
        request_id=request_id,
    )

    events = recorded(
        run_turn(
            client=client,
            tooling=tooling,
            messages=build_messages(request.message, request.history),
            usage=Usage(
                used=token.used_queries,
                remaining=token.remaining_queries,
                max=token.max_queries,
            ),
        ),
        transcripts=transcripts,
        token=token,
        conversation_id=conversation_id,
        endpoint=endpoint,
        request_id=request_id,
    )

    try:
        async for event in events:
            yield event
    except GeneratorExit:
        # The client hung up. There is nobody left to read a failure frame, and
        # re-raising is what lets the recorder finalise and store the partial.
        raise
    except Exception:
        # This happened after the 200 was already on the wire, so the only way
        # to say so is in the stream itself. Without it the client sees a reply
        # that simply stops — indistinguishable from a dropped connection.
        # CancelledError is a BaseException and passes through untouched.
        logger.exception("Chat turn failed", extra={"request_id": request_id})
        yield TurnFailed(message=FAILURE_MESSAGE)
