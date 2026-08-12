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