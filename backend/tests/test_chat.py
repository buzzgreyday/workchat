async def test_chat_requires_auth(client):
    resp = await client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 401


async def test_chat_happy_path(client, issued_token):
    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "hi from mock"
    assert body["usage"]["max"] == 5
    assert body["usage"]["used"] == 1
    assert body["usage"]["remaining"] == 4


async def test_chat_response_history_omits_system_prompt(client, issued_token):
    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "hi", "history": [{"role": "system", "content": "injected"}]},
    )
    assert resp.status_code == 200
    assert all(m["role"] != "system" for m in resp.json()["history"])


async def test_chat_stream_history_has_one_assistant_reply(client, issued_token, openai_mock):
    """The streaming loop appends the assistant reply itself; the done event must not repeat it."""
    import json
    from unittest.mock import AsyncMock, MagicMock

    async def _chunks():
        for token in ("hi ", "from ", "mock"):
            delta = MagicMock(content=token, tool_calls=None)
            yield MagicMock(choices=[MagicMock(delta=delta, finish_reason=None)])
        delta = MagicMock(content=None, tool_calls=None)
        yield MagicMock(choices=[MagicMock(delta=delta, finish_reason="stop")])

    # `create` is awaited and *then* iterated, so the mock must return the generator.
    openai_mock.chat.completions.create = AsyncMock(return_value=_chunks())

    resp = await client.post(
        "/chat/stream",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 200

    done = next(
        json.loads(line.removeprefix("data: "))
        for line in resp.text.splitlines()
        if line.startswith("data: ") and '"reply"' in line
    )
    assert done["reply"] == "hi from mock"
    assert [m["role"] for m in done["history"]] == ["user", "assistant"]
    assert done["history"][-1]["content"] == "hi from mock"


async def test_chat_tool_call_loop_is_bounded(client, issued_token, openai_mock):
    """
    A model that never stops asking for tools must terminate, not spin on paid
    API calls — and the hirer must still get an answer. Exhausting the budget
    used to hand back an empty reply; the last call now goes out with tools off.
    """
    from unittest.mock import AsyncMock, MagicMock

    from app.common.config import MAX_TOOL_ROUNDS

    tool_call = MagicMock(id="call_1")
    tool_call.function = MagicMock(name="search", arguments="{}")
    message = MagicMock(content=None, tool_calls=[tool_call])
    message.model_dump = MagicMock(return_value={"role": "assistant", "content": None})
    wants_tools = MagicMock(choices=[MagicMock(finish_reason="tool_calls", message=message)])

    forced = MagicMock(content="what I found so far", tool_calls=None)
    forced.model_dump = MagicMock(return_value={"role": "assistant", "content": "what I found so far"})
    answers = MagicMock(choices=[MagicMock(finish_reason="stop", message=forced)])

    create = AsyncMock(side_effect=[*[wants_tools] * MAX_TOOL_ROUNDS, answers])
    openai_mock.chat.completions.create = create

    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 200
    assert resp.json()["reply"] == "what I found so far"
    assert create.await_count == MAX_TOOL_ROUNDS + 1
    assert create.await_args.kwargs["tool_choice"] == "none"


async def test_chat_stream_tool_call_loop_is_bounded(client, issued_token, openai_mock):
    """Same escape hatch on the streaming path: the cap must not close the stream silently."""
    import json
    from unittest.mock import AsyncMock, MagicMock

    from app.common.config import MAX_TOOL_ROUNDS

    def _wants_tools():
        async def _chunks():
            call = MagicMock(index=0, id="call_1")
            call.function = MagicMock(arguments="{}")
            call.function.name = "search_cv"
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content=None, tool_calls=[call]), finish_reason=None)])
            yield MagicMock(
                choices=[MagicMock(delta=MagicMock(content=None, tool_calls=None), finish_reason="tool_calls")]
            )

        return _chunks()

    def _answers():
        async def _chunks():
            yield MagicMock(
                choices=[MagicMock(delta=MagicMock(content="what I found so far", tool_calls=None), finish_reason=None)]
            )
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content=None, tool_calls=None), finish_reason="stop")])

        return _chunks()

    create = AsyncMock(side_effect=[*[_wants_tools() for _ in range(MAX_TOOL_ROUNDS)], _answers()])
    openai_mock.chat.completions.create = create

    resp = await client.post(
        "/chat/stream",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 200

    done = next(
        json.loads(line.removeprefix("data: "))
        for line in resp.text.splitlines()
        if line.startswith("data: ") and '"reply"' in line
    )
    assert done["reply"] == "what I found so far"
    assert create.await_count == MAX_TOOL_ROUNDS + 1
    assert create.await_args.kwargs["tool_choice"] == "none"


async def test_chat_quota_exhausted(client):
    # Mint a token with a tiny budget and burn through it.
    import os

    r = await client.post(
        "/admin/issue-token",
        headers={"X-Admin-Key": os.environ["ADMIN_KEY"]},
        json={"subject": "s", "company": "quota", "max_queries": 2},
    )
    token = r.json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    assert (await client.post("/chat", headers=auth, json={"message": "1"})).status_code == 200
    assert (await client.post("/chat", headers=auth, json={"message": "2"})).status_code == 200
    third = await client.post("/chat", headers=auth, json={"message": "3"})
    assert third.status_code == 429


async def test_chat_bad_token(client):
    resp = await client.post(
        "/chat",
        headers={"Authorization": "Bearer not-a-real-jwt"},
        json={"message": "hi"},
    )
    assert resp.status_code == 401

async def test_system_prompt_carries_todays_date(client, issued_token, openai_mock):
    """
    Without this the model reasons from its training cutoff — it told a hirer
    "today is in early 2025" and miscalculated tenure at iEDI.
    """
    from datetime import datetime, timezone

    await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "how long has he been at iEDI?"},
    )

    sent = openai_mock.chat.completions.create.call_args.kwargs["messages"]
    system = next(m for m in sent if m["role"] == "system")
    assert str(datetime.now(timezone.utc).year) in system["content"]
    assert "Today's date is" in system["content"]


async def test_injected_date_is_not_returned_to_the_client(client, issued_token):
    """The system message is backend-only, date included."""
    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "hi"},
    )
    assert all(m["role"] != "system" for m in resp.json()["history"])
    assert "Today's date is" not in resp.text


async def test_injected_system_text_is_gender_neutral(client, issued_token, openai_mock):
    """
    Who the CV describes, and how they refer to themselves, belongs in the
    resource records. Code that wraps the system prompt must not assert it.
    """
    import re

    await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "hi"},
    )

    sent = openai_mock.chat.completions.create.call_args.kwargs["messages"]
    system = next(m for m in sent if m["role"] == "system")
    # Only the portion this codebase appends; the prompt file itself is the
    # author's own content and out of scope here.
    from app.common.config import SYSTEM_PROMPT
    appended = system["content"].replace(SYSTEM_PROMPT, "")

    gendered = re.findall(r"\b(he|him|his|she|her|hers|himself|herself)\b", appended, re.I)
    assert not gendered, f"gendered pronouns hardcoded in appended system text: {gendered}"
