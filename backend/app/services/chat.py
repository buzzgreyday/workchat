import json

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, \
    ChatCompletionToolMessageParam, ChatCompletionAssistantMessageParam
from openai.types.chat.chat_completion import Choice

from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall

from app.common.config import OPENAI_MODEL, SYSTEM_PROMPT
from app.common.models import ChatRequest, ChatResponse, TokenContext, Usage
from app.services.sse import sse_event
from app.services.tools import ChatToolService, ToolCall, ToolCallFunction
from app.common.logging.logging import logger

class Chat:
    def __init__(self, client: AsyncOpenAI, tools: ChatToolService):
        self.client: AsyncOpenAI = client
        self.tools = tools
        self.messages: list[ChatCompletionMessageParam] = []
        self.usage: Usage | None = None

    async def prepare(self, request: ChatRequest, token: TokenContext):
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
        self._new_messages(request)
        self.usage = Usage(used=token.used_queries, remaining=token.remaining_queries, max=token.max_queries)

    async def stream_response(self, reply: str = "", max_rounds: int = 5):
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

                if delta.content:
                    content += delta.content
                    reply += delta.content
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
            data={"reply": reply, "history": self._final_history(reply), "usage": self.usage},
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
        reply = await self._get_full_reply() or ""
        usage = self.usage.model_dump()
        # Strip the system prompt before chat resp to user
        history = self._strip_system(self.messages)
        logger.info("Sending chat response to user", extra={"usage": usage})
        logger.debug("Chat response content", extra={"reply": reply, "history": history})
        return ChatResponse(type="done", reply=reply, history=history, usage=usage)

    def _final_history(self, reply: str) -> list[ChatCompletionMessageParam]:
        """
        Method used with last server-sent svent in streaming resp (status: "done").
        System prompt stripped from final streaming resp to user
        """
        assistant_message: ChatCompletionAssistantMessageParam = {"role": "assistant", "content": reply}
        return [*self._strip_system(self.messages), assistant_message]

    async def _run_tool_calls(self, tool_calls) -> None:
        for tool_call in tool_calls:
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
        self.messages.append(choice.message.model_dump(exclude_none=True))

        if choice.finish_reason == "tool_calls":
            await self._run_tool_calls(choice.message.tool_calls)

        return choice

    async def _get_full_reply(self) -> str | None:
        while True:
            choice = await self._resolve_tool_calls()
            if choice.finish_reason != "tool_calls":
                return choice.message.content

    def _new_messages(self, req: ChatRequest) -> list[ChatCompletionMessageParam]:
        system_message: ChatCompletionMessageParam | dict = {"role": "system", "content": SYSTEM_PROMPT}
        self.messages = [system_message, *self._strip_system(req.history)]
        user_message: ChatCompletionMessageParam | dict = {"role": "user", "content": req.message}
        self.messages.append(user_message)
        return self.messages

    @staticmethod
    def _strip_system(messages: list[ChatCompletionMessageParam] | None) -> list[ChatCompletionMessageParam]:
        """The system prompt is backend-only: it never leaves the API and is re-added on every request."""
        # If role is not == "system" the message is added in the comprehension list (whether dict or obj)
        return [m for m in (messages or []) if (m.get("role") if isinstance(m, dict) else getattr(m, "role", None)) != "system"]
