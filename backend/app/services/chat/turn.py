"""
One turn: call the model, run whatever tools it asks for, repeat until it
answers.

The loop exists once. It used to exist twice — once yielding SSE bytes and once
building a JSON body — because the transport was baked into it. Here it yields
domain events and a caller decides what to do with them, which is the whole
reason the duplication is gone.

Everything a turn accumulates lives in locals. There is no instance, so a second
call cannot inherit the first one's tool counts, reply or messages.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionToolMessageParam,
)
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall

from app.common.config import MAX_TOOL_ROUNDS, get_settings
from app.common.logging.logging import logger
from app.common.models import Usage
from app.services.chat.events import (
    ModelCalled,
    RoundFinished,
    TokenProduced,
    ToolInvoked,
    ToolStarted,
    TurnEvent,
    TurnFinished,
)
from app.services.chat.prompt import strip_system
from app.services.chat.tooling import ChatTooling, ToolCall, ToolCallFunction


async def run_turn(
    client: AsyncOpenAI,
    tooling: ChatTooling,
    messages: list[ChatCompletionMessageParam],
    usage: Usage,
    max_rounds: int = MAX_TOOL_ROUNDS,
) -> AsyncIterator[TurnEvent]:
    """
    Yields the reply as it is written, then one TurnFinished.

    `messages` is mutated as the turn proceeds — tool calls and their results
    have to be in the list the next round sends — and handed back on the
    terminal event with the system prompt stripped.
    """
    reply = ""

    for _ in range(max_rounds):
        round_ = _Round()
        async for event in round_.run(client, tooling, messages):
            yield event
        reply += round_.content

        if round_.finish_reason != "tool_calls":
            _append_assistant(messages, round_.content)
            break

        calls = _assemble(round_.pending)
        messages.append(_assistant_tool_call_message(round_.content, calls))
        async for event in _run_tools(tooling, calls, messages):
            yield event
    else:
        # The budget ran out with the model still asking for tools. Ending
        # here would end on whatever had streamed — usually nothing, since a
        # model still calling tools has not written prose yet. One more round
        # with tools switched off turns the cap into a thinner answer built
        # from what was already fetched.
        logger.warning("Tool-call rounds exhausted without a final reply", extra={"max_rounds": max_rounds})
        round_ = _Round()
        async for event in round_.run(client, tooling, messages, tool_choice="none"):
            yield event
        reply += round_.content
        _append_assistant(messages, round_.content)

    yield TurnFinished(
        reply=reply,
        history=cast(list[dict[str, Any]], strip_system(messages)),
        usage=usage,
        finish_reason=round_.finish_reason,
    )


@dataclass(slots=True)
class _Round:
    """
    One model call, and what it said.

    Its events go out as they happen; what the turn needs afterwards — the
    text, why the model stopped, the tool calls it assembled — stays here to
    be read once the stream is done, which an async generator cannot return.
    """

    content: str = ""
    finish_reason: str | None = None
    pending: dict[int, dict[str, Any]] = field(default_factory=dict)

    async def run(
        self,
        client: AsyncOpenAI,
        tooling: ChatTooling,
        messages: list[ChatCompletionMessageParam],
        **options: Any,
    ) -> AsyncIterator[TurnEvent]:
        yield ModelCalled()
        response = await client.chat.completions.create(
            model=get_settings().openai_model,
            messages=messages,
            **_reasoning(),
            tools=await tooling.schemas(),
            stream=True,
            **options,
        )
        async for chunk in response:
            choice = chunk.choices[0]
            if choice.finish_reason:
                self.finish_reason = choice.finish_reason
            if choice.delta.content:
                self.content += choice.delta.content
                yield TokenProduced(text=choice.delta.content)
            _accumulate_tool_calls(choice.delta.tool_calls, self.pending)
        yield RoundFinished(finish_reason=self.finish_reason)


def _reasoning() -> dict[str, Any]:
    """
    `reasoning_effort` for the chat call, when one is configured, and nothing
    otherwise — a model that does not reason rejects the parameter, so it is
    left out rather than sent empty. Set centrally (OPENAI_REASONING_EFFORT,
    Settings.openai_reasoning_effort); every call in a turn uses the same.
    """
    effort = get_settings().openai_reasoning_effort
    return {"reasoning_effort": effort} if effort else {}


def _accumulate_tool_calls(
    deltas: list[ChoiceDeltaToolCall] | None, pending: dict[int, dict[str, Any]]
) -> None:
    """
    Reassemble tool calls arriving a fragment at a time.

    A provider sends the id on one chunk, the name on another and the arguments
    across several, keyed by index — so this is a small parser, kept out of the
    loop above so that loop reads as orchestration.
    """
    for delta in deltas or []:
        # A custom (non-function) tool call has nothing this service can run.
        # The non-streaming path filtered these and warned; the streaming path
        # never looked, and would assemble a nonsense call from one.
        if getattr(delta, "type", "function") not in ("function", None):
            logger.warning("Ignoring a tool call this service cannot run", extra={"type": delta.type})
            continue
        entry = pending.setdefault(delta.index, {"id": None, "name": None, "arguments": ""})
        if delta.id:
            entry["id"] = delta.id
        if delta.function and delta.function.name:
            entry["name"] = delta.function.name
        if delta.function and delta.function.arguments:
            entry["arguments"] += delta.function.arguments


def _assemble(pending: dict[int, dict[str, Any]]) -> list[ToolCall]:
    return [
        ToolCall(id=entry["id"], function=ToolCallFunction(name=entry["name"] or "", arguments=entry["arguments"]))
        for entry in pending.values()
    ]


async def _run_tools(
    tooling: ChatTooling, calls: list[ToolCall], messages: list[ChatCompletionMessageParam]
) -> AsyncIterator[TurnEvent]:
    """Run each call and append its result where the next round will see it."""
    for call in calls:
        if not call.is_runnable:
            # Incomplete across the chunks that carried it. Sending a tool
            # message with a null id is rejected by the next request, so the
            # turn is better off without it.
            logger.warning("Dropping an incomplete tool call", extra={"name": call.function.name})
            continue
        logger.info("Running a tool for the model", extra={"tool": call.function.name})
        yield ToolStarted(name=call.function.name)
        result = await tooling.run(call.function.name, call.function.arguments)
        tool_message: ChatCompletionToolMessageParam = {
            "role": "tool",
            "tool_call_id": cast(str, call.id),
            "content": result,
        }
        messages.append(tool_message)
        yield ToolInvoked(name=call.function.name)


def _append_assistant(messages: list[ChatCompletionMessageParam], content: str) -> None:
    """
    Record what the model said, if it said anything.

    An empty assistant message used to be appended unconditionally, returned in
    the history and sent back by the client on its next turn — a blank entry in
    the transcript that the model then had to read past.
    """
    if not content:
        return
    message: ChatCompletionAssistantMessageParam = {"role": "assistant", "content": content}
    messages.append(message)


def _assistant_tool_call_message(content: str, calls: list[ToolCall]) -> ChatCompletionMessageParam:
    """The assistant turn that asked for tools, in the shape the next round needs."""
    return cast(
        ChatCompletionMessageParam,
        {
            "role": "assistant",
            "content": content or None,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in calls
                if call.is_runnable
            ],
        },
    )
