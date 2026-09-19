"""
The turn loop, with no transport and no database.

This is what the split bought: the algorithm that decides when to call the
model, when to run a tool and when to stop can be exercised on its own. It used
to be reachable only by driving a full HTTP request.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.common.config import MAX_TOOL_ROUNDS
from app.common.models import Usage
from app.services.chat.events import RoundFinished, TokenProduced, ToolInvoked, TurnFinished
from app.services.chat.turn import run_turn
from tests.conftest import stream_of

USAGE = Usage(used=1, remaining=4, max=5)


class FakeTooling:
    """Enough of the adapter to run the loop, with no OpenAI and no disk."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def schemas(self):
        return []

    async def run(self, name: str, arguments: str) -> str:
        self.calls.append((name, arguments))
        return '{"count": 1}'


def wants_tools():
    """A response asking for one tool call, delivered across chunks."""
    async def chunks():
        call = MagicMock(index=0, id="call_1", type="function")
        call.function = MagicMock(arguments='{"query": "x"}')
        call.function.name = "search_cv"
        yield MagicMock(
            choices=[MagicMock(delta=MagicMock(content=None, tool_calls=[call]), finish_reason=None)]
        )
        yield MagicMock(
            choices=[MagicMock(delta=MagicMock(content=None, tool_calls=None), finish_reason="tool_calls")]
        )

    return chunks()


async def collect(events):
    return [event async for event in events]


async def test_a_plain_reply_streams_then_finishes():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=lambda **kw: stream_of("hi ", "there"))

    events = await collect(run_turn(client, FakeTooling(), [], USAGE))

    assert [e.text for e in events if isinstance(e, TokenProduced)] == ["hi ", "there"]
    finished = events[-1]
    assert isinstance(finished, TurnFinished)
    assert finished.reply == "hi there"
    assert finished.usage == USAGE


async def test_the_turn_carries_no_transport():
    """Not one event is bytes — encoding is somebody else's problem."""
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=lambda **kw: stream_of("hi"))

    events = await collect(run_turn(client, FakeTooling(), [], USAGE))

    assert not any(isinstance(e, (bytes, str)) for e in events)


async def test_a_tool_call_runs_and_is_reported():
    tooling = FakeTooling()
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=[wants_tools(), stream_of("answered")])

    events = await collect(run_turn(client, tooling, [], USAGE))

    assert tooling.calls == [("search_cv", '{"query": "x"}')]
    assert [e.name for e in events if isinstance(e, ToolInvoked)] == ["search_cv"]
    assert events[-1].reply == "answered"


async def test_history_keeps_the_tool_call_pairing():
    """run_eval walks this structure to attribute failures to a retrieval step."""
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=[wants_tools(), stream_of("answered")])

    finished = (await collect(run_turn(client, FakeTooling(), [], USAGE)))[-1]

    assistant = next(m for m in finished.history if m.get("tool_calls"))
    tool = next(m for m in finished.history if m.get("role") == "tool")
    assert assistant["tool_calls"][0]["function"]["name"] == "search_cv"
    assert tool["tool_call_id"] == assistant["tool_calls"][0]["id"]


async def test_the_tool_budget_is_bounded_and_still_answers():
    """
    A model that never stops asking for tools must terminate, not spin on paid
    calls — and the hirer must still get something. The last call goes out with
    tools switched off.
    """
    client = MagicMock()
    create = AsyncMock(
        side_effect=[*(wants_tools() for _ in range(MAX_TOOL_ROUNDS)), stream_of("what I found")]
    )
    client.chat.completions.create = create

    finished = (await collect(run_turn(client, FakeTooling(), [], USAGE)))[-1]

    assert create.await_count == MAX_TOOL_ROUNDS + 1
    assert create.await_args.kwargs["tool_choice"] == "none"
    assert finished.reply == "what I found"


async def test_an_empty_reply_is_not_appended_to_history():
    """
    An empty assistant message used to be stored and echoed back, so the client
    sent a blank turn on its next question.
    """
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=lambda **kw: stream_of())

    finished = (await collect(run_turn(client, FakeTooling(), [], USAGE)))[-1]

    assert finished.history == []


async def test_a_second_turn_starts_clean():
    """
    The state fix, stated as a test. The old class accumulated its reply and
    tool counts on the instance, so a reused one reported the previous turn's.
    """
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=lambda **kw: stream_of("first"))
    first = (await collect(run_turn(client, FakeTooling(), [], USAGE)))[-1]

    client.chat.completions.create = AsyncMock(side_effect=lambda **kw: stream_of("second"))
    second = (await collect(run_turn(client, FakeTooling(), [], USAGE)))[-1]

    assert first.reply == "first"
    assert second.reply == "second", "a turn must not inherit the last one's reply"


async def test_a_round_reports_why_it_stopped():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=lambda **kw: stream_of("hi"))

    events = await collect(run_turn(client, FakeTooling(), [], USAGE))

    assert [e.finish_reason for e in events if isinstance(e, RoundFinished)] == ["stop"]
