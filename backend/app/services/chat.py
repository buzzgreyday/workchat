import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import async_sessionmaker
from openai.types.chat import ChatCompletionMessageParam, \
    ChatCompletionToolMessageParam, ChatCompletionAssistantMessageParam
from openai.types.chat.chat_completion import Choice

from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall

from app.common.config import LOG_CHAT_CONTENT, MAX_TOOL_ROUNDS, OPENAI_MODEL, SYSTEM_PROMPT
from app.common.context import conversation_id_var, current_request_id, token_sub_var
from app.common.models import ChatRequest, ChatResponse, TokenContext, Usage
from app.services.db import record_assistant_message, record_user_message
from app.services.sse import sse_event
from app.services.tools import ChatToolService, ToolCall, ToolCallFunction
from app.common.logging.logging import logger

class Chat:
    def __init__(
            self,
            client: AsyncOpenAI,
            tools: ChatToolService,
            session_factory: async_sessionmaker | None = None,
            endpoint: str = "/chat",
    ):
        self.client: AsyncOpenAI = client
        self.tools = tools
        self.messages: list[ChatCompletionMessageParam] = []
        self.usage: Usage | None = None

        self.session_factory = session_factory
        self.endpoint = endpoint
        self.token: TokenContext | None = None
        self.conversation_id: uuid.UUID | None = None
        self.request_id: str = current_request_id()

        # Terminal-recorder state. reply lives on the instance rather than in a
        # local so the finally block can read whatever arrived before an abort.
        self._reply: str = ""
        self._tool_names: list[str] = []
        self._tool_calls_count: int = 0
        self._finish_reason: str | None = None
        self._started_at: float = 0.0

    async def prepare(self, request: ChatRequest, token: TokenContext):
        if LOG_CHAT_CONTENT:
            logger.debug(
                "Preparing chat data",
                extra={
                    "user_message": request.message,
                    "history": request.history,
                    "token_details": {
                        "sub": token.sub,
                        "used_queries": token.used_queries,
                        "max_queries": token.max_queries,
                        "remaining_queries": token.remaining_queries,
                    },
                },
            )
        self.token = token
        token_sub_var.set(token.sub)
        self._new_messages(request)
        self.usage = Usage(used=token.used_queries, remaining=token.remaining_queries, max=token.max_queries)

        # Persist the question before the model is called. This commit is the
        # durability guarantee: everything after it is enrichment, and a failure
        # here is swallowed rather than surfaced to the hirer.
        if self.session_factory is not None:
            # Belt as well as braces: the recorder swallows its own failures, but
            # the guarantee is that *nothing* about capturing a transcript can
            # cost the hirer a reply — including a malformed jti reaching UUID().
            try:
                self.conversation_id = await record_user_message(
                    session_factory=self.session_factory,
                    token_id=uuid.UUID(token.jti),
                    conversation_id=request.conversation_id,
                    message=request.message,
                    endpoint=self.endpoint,
                    request_id=self.request_id,
                )
            except Exception:
                logger.exception("Failed to record user message", extra={"request_id": self.request_id})
                self.conversation_id = None
            conversation_id_var.set(str(self.conversation_id) if self.conversation_id else None)

    @asynccontextmanager
    async def _record_turn(self):
        """
        Records the reply however the turn ends — completed, aborted or failed.

        One implementation for both endpoints. The finally block may await, but
        must never yield: yielding from a generator being closed raises
        "async generator ignored GeneratorExit".
        """
        self._started_at = time.monotonic()
        status = "completed"
        error: str | None = None
        try:
            yield
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            # GeneratorExit/CancelledError arrive here when the client goes away
            # mid-stream; anything else is a genuine failure.
            status = "aborted" if isinstance(exc, (GeneratorExit, asyncio.CancelledError)) else "failed"
            if status == "failed":
                error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if self.session_factory is not None and self.token is not None:
                try:
                    await record_assistant_message(
                        session_factory=self.session_factory,
                        token_id=uuid.UUID(self.token.jti),
                        conversation_id=self.conversation_id,
                        reply=self._reply,
                        endpoint=self.endpoint,
                        request_id=self.request_id,
                        status=status,
                        finish_reason=self._finish_reason,
                        tool_names=self._tool_names,
                        tool_calls_count=self._tool_calls_count,
                        model=OPENAI_MODEL,
                        latency_ms=int((time.monotonic() - self._started_at) * 1000),
                        error=error,
                    )
                except Exception:
                    logger.exception(
                        "Failed to record assistant message",
                        extra={"request_id": self.request_id},
                    )

    async def stream_response(self, reply: str = "", max_rounds: int = MAX_TOOL_ROUNDS):
        self._reply = reply
        async with self._record_turn():
            for _ in range(max_rounds):
                response = await self.client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=self.messages,
                    tools=await self.tools.get_tools(),
                    stream=True,
                )

                content = ""
                tool_call_chunks: dict[int, dict] = {}
                finish_reason = None

                async for chunk in response:
                    delta = chunk.choices[0].delta
                    if chunk.choices[0].finish_reason:
                        finish_reason = chunk.choices[0].finish_reason
                        self._finish_reason = finish_reason

                    if delta.content:
                        content += delta.content
                        self._reply += delta.content
                        yield sse_event(event="token", data={"value": delta.content})

                    delta_tool_calls: list[ChoiceDeltaToolCall] | None = delta.tool_calls
                    if delta_tool_calls:
                        for dtc in delta_tool_calls:
                            entry = tool_call_chunks.setdefault(dtc.index, {"id": None, "name": None, "arguments": ""})
                            if dtc.id:
                                entry["id"] = dtc.id
                            if dtc.function and dtc.function.name:
                                entry["name"] = dtc.function.name
                            if dtc.function and dtc.function.arguments:
                                entry["arguments"] += dtc.function.arguments

                if finish_reason != "tool_calls":
                    message: ChatCompletionAssistantMessageParam = {"role": "assistant", "content": content}
                    self.messages.append(message)
                    break

                tool_calls = [
                    ToolCall(id=tcc["id"], function=ToolCallFunction(name=tcc["name"], arguments=tcc["arguments"]))
                    for tcc in tool_call_chunks.values()
                ]
                message = self._assistant_tool_call_message(content, tool_calls)
                self.messages.append(message)
                await self._run_tool_calls(tool_calls)

            yield sse_event(
                event="done",
                data={
                    "reply": self._reply,
                    "history": self._final_history(),
                    "usage": self.usage,
                    "conversation_id": str(self.conversation_id) if self.conversation_id else None,
                },
            )

    @staticmethod
    def _assistant_tool_call_message(content: str, tool_calls: list[ToolCall]) -> ChatCompletionMessageParam | dict:
        return {
            "role": "assistant",
            "content": content or None,
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        }

    async def json_response(self) -> ChatResponse:
        async with self._record_turn():
            reply = await self._get_full_reply() or ""
            self._reply = reply
            usage = self.usage.model_dump()
            # Strip the system prompt before chat resp to user
            history = self._strip_system(self.messages)
            logger.info("Sending chat response to user", extra={"usage": usage})
            if LOG_CHAT_CONTENT:
                logger.debug("Chat response content", extra={"reply": reply, "history": history})
            return ChatResponse(
                type="done",
                reply=reply,
                history=history,
                usage=usage,
                conversation_id=str(self.conversation_id) if self.conversation_id else None,
            )

    def _final_history(self) -> list[ChatCompletionMessageParam]:
        """
        Method used with last server-sent svent in streaming resp (status: "done").
        System prompt stripped from final streaming resp to user.

        stream_response() already appended the assistant reply to self.messages, so
        this only strips — appending the reply again would duplicate it.
        """
        return self._strip_system(self.messages)

    async def _run_tool_calls(self, tool_calls) -> None:
        for tool_call in tool_calls:
            self._tool_calls_count += 1
            name = tool_call.function.name
            if name and name not in self._tool_names:
                self._tool_names.append(name)
            try:
                args = json.loads(tool_call.function.arguments)
                result = await self.tools.run_tool(tool_call.function.name, args)
            except Exception:
                logger.exception("Tool execution failed", extra={"tool": tool_call.function.name})
                result = f"Tool '{tool_call.function.name}' failed to execute."

            message: ChatCompletionToolMessageParam = {"role": "tool", "tool_call_id": tool_call.id, "content": result}
            self.messages.append(message)

    async def _resolve_tool_calls(self) -> Choice:
        response = await self.client.chat.completions.create(
            model=OPENAI_MODEL, messages=self.messages, tools=await self.tools.get_tools()
        )
        choice = response.choices[0]
        self._finish_reason = choice.finish_reason
        self.messages.append(choice.message.model_dump(exclude_none=True))

        if choice.finish_reason == "tool_calls":
            await self._run_tool_calls(choice.message.tool_calls)

        return choice

    async def _get_full_reply(self, max_rounds: int = MAX_TOOL_ROUNDS) -> str | None:
        for _ in range(max_rounds):
            choice = await self._resolve_tool_calls()
            if choice.finish_reason != "tool_calls":
                return choice.message.content

        logger.warning("Tool-call rounds exhausted without a final reply", extra={"max_rounds": max_rounds})
        return None

    @staticmethod
    def _system_content() -> str:
        """
        The system prompt plus today's date.

        Without it the model falls back on its training cutoff — it was telling
        hirers "today is in early 2025" and miscalculating how long Michael had
        been at iEDI. Added here rather than in system-prompt.md because that
        file is gitignored and a hardcoded date would go stale the next day.
        """
        today = datetime.now(timezone.utc)
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"Today's date is {today.strftime('%A, %d %B %Y')}. Use it whenever a "
            f"question depends on the current date — how long he has held a role, "
            f"how recent something is, or whether a date is past or future. Never "
            f"assume the date from your training data."
        )

    def _new_messages(self, req: ChatRequest) -> list[ChatCompletionMessageParam]:
        system_message: ChatCompletionMessageParam | dict = {"role": "system", "content": self._system_content()}
        self.messages = [system_message, *self._strip_system(req.history)]
        user_message: ChatCompletionMessageParam | dict = {"role": "user", "content": req.message}
        self.messages.append(user_message)
        return self.messages

    @staticmethod
    def _strip_system(messages: list[ChatCompletionMessageParam] | None) -> list[ChatCompletionMessageParam]:
        """The system prompt is backend-only: it never leaves the API and is re-added on every request."""
        # If role is not == "system" the message is added in the comprehension list (whether dict or obj)
        return [m for m in (messages or []) if (m.get("role") if isinstance(m, dict) else getattr(m, "role", None)) != "system"]
