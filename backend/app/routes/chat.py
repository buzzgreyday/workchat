from fastapi import APIRouter, Depends
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.responses import StreamingResponse

from app.common.config import LOG_CHAT_CONTENT
from app.common.db import get_session_factory
from app.services.auth import verify_and_consume
from app.common.models import ChatRequest, TokenContext, ChatResponse
from app.common.logging.logging import logger
from app.services.chat import Chat
from app.openai.client import get_openai_client
from app.services.tools import get_chat_tool, ChatToolService

router = APIRouter(tags=["Chat"])

# Unversioned endpoints

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
    }
)
async def chat_stream(
    req: ChatRequest,
    token: TokenContext = Depends(verify_and_consume),
    client: AsyncOpenAI = Depends(get_openai_client),
    tools: ChatToolService = Depends(get_chat_tool),
    session_factory: async_sessionmaker = Depends(get_session_factory),
) -> StreamingResponse:
    """
    Getting client and tools as dependencies (with lru_cache) will make this easy to test and still ensure that
    client and tools are singletons.
    """
    logger.info(
        "Chat message received from user",
        extra={
            "token_details": {
                "sub": token.sub,
                "used_queries": token.used_queries,
                "max_queries": token.max_queries,
                "remaining_queries": token.remaining_queries}
        }
    )
    if LOG_CHAT_CONTENT:
        logger.debug(
            "Chat message content",
            extra={"user_message": req.message, "history": req.history}
        )

    chat = Chat(client, tools=tools, session_factory=session_factory, endpoint="/chat/stream")
    await chat.prepare(req, token)

    return StreamingResponse(
        chat.stream_response(),
        media_type="text/event-stream",
    )


@router.post(
    "/chat",
    summary="Send a message to the AI",
    description="Send a message to the AI with chat history (requires authentication)",
    response_model=ChatResponse
)
async def chat(
    req: ChatRequest,
    token: TokenContext = Depends(verify_and_consume),
    client: AsyncOpenAI = Depends(get_openai_client),
    tools: ChatToolService = Depends(get_chat_tool),
    session_factory: async_sessionmaker = Depends(get_session_factory),
) -> ChatResponse:
    """
    Getting client and tools as dependencies (with lru_cache) will make this easy to test and still ensure that
    client and tools are singletons.
    """
    logger.info(
        "Chat message received from user",
        extra={
            "token_details": {
                "sub": token.sub,
                "used_queries": token.used_queries,
                "max_queries": token.max_queries,
                "remaining_queries": token.remaining_queries}
        }
    )

    chat = Chat(client, tools=tools, session_factory=session_factory, endpoint="/chat")
    await chat.prepare(req, token)

    return await chat.json_response()