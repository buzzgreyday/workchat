from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends
from openai import AsyncOpenAI
from starlette.responses import StreamingResponse

from app.common.config import LOG_CHAT_CONTENT
from app.common.logging.logging import logger
from app.common.models import ChatRequest, TokenContext
from app.common import sse
from app.openai.client import get_openai_client
from app.repositories import get_transcript_repository
from app.repositories.base import TranscriptRepository
from app.services import chat as chat_service
from app.services.auth import auth
from app.services.chat import ChatTooling, TokenProduced, TurnEvent, TurnFailed, TurnFinished
from app.services.chat.tooling import get_tooling

router = APIRouter(tags=["Chat"])


def wire(event: TurnEvent) -> dict[str, Any] | None:
    """
    A domain event as the browser reads it, or None for one it has no use for.

    The mapping lives at the HTTP boundary because that is what it is about.
    `ToolInvoked` and `RoundFinished` are how the recorder learns what a turn
    did; a client has no use for either, so they stop here.
    """
    if isinstance(event, TokenProduced):
        return {"type": "token", "value": event.text}
    if isinstance(event, TurnFinished):
        return {
            "type": "done",
            "reply": event.reply,
            "history": event.history,
            "usage": event.usage.model_dump(),
            "conversation_id": str(event.conversation_id) if event.conversation_id else None,
        }
    if isinstance(event, TurnFailed):
        return {"type": "error", "message": event.message}
    return None


async def frames(events: AsyncIterator[TurnEvent]) -> AsyncIterator[bytes]:
    async for event in events:
        payload = wire(event)
        if payload is not None:
            yield sse.frame(payload)


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    response_model=None,
    summary="Send a message to the AI",
    description="Send a message to the AI with chat history (requires authentication)",
    responses={
        200: {
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
            "description": "Server-Sent Events stream of the AI's reply.",
        }
    },
)
async def chat_stream(
    req: ChatRequest,
    token: TokenContext = Depends(auth.verify_and_consume),
    client: AsyncOpenAI = Depends(get_openai_client),
    tooling: ChatTooling = Depends(get_tooling),
    transcripts: TranscriptRepository = Depends(get_transcript_repository),
) -> StreamingResponse:
    """
    The only chat endpoint.

    Client and tooling arrive as dependencies so they can be swapped in tests
    while staying singletons in production.
    """
    logger.info(
        "Chat message received from user",
        extra={
            "token_details": {
                "sub": token.sub,
                "used_queries": token.used_queries,
                "max_queries": token.max_queries,
                "remaining_queries": token.remaining_queries,
            }
        },
    )
    if LOG_CHAT_CONTENT:
        logger.debug(
            "Chat message content",
            extra={"user_message": req.message, "history": req.history},
        )

    events = chat_service.answer(
        request=req,
        token=token,
        client=client,
        tooling=tooling,
        transcripts=transcripts,
        endpoint="/chat/stream",
    )
    return StreamingResponse(frames(events), media_type="text/event-stream")
