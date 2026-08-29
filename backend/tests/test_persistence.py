"""
Chat transcript capture.

The operator's whole reason for this feature is being able to read what hirers
asked, so these assert against the rows themselves rather than the response body.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.common.schemas import DatabaseChatMessage, DatabaseConversation, DatabaseToken


async def _messages(db_session, role: str | None = None):
    stmt = select(DatabaseChatMessage).order_by(DatabaseChatMessage.created_at)
    if role:
        stmt = stmt.where(DatabaseChatMessage.role == role)
    return list((await db_session.execute(stmt)).scalars().all())


async def _conversations(db_session):
    return list((await db_session.execute(select(DatabaseConversation))).scalars().all())


def _stream_chunks(tokens=("hi ", "from ", "mock")):
    async def _chunks():
        for token in tokens:
            delta = MagicMock(content=token, tool_calls=None)
            yield MagicMock(choices=[MagicMock(delta=delta, finish_reason=None)])
        delta = MagicMock(content=None, tool_calls=None)
        yield MagicMock(choices=[MagicMock(delta=delta, finish_reason="stop")])
    return _chunks()


async def test_chat_persists_user_and_assistant_rows(client, issued_token, db_session):
    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "what frameworks does he use?"},
    )
    assert resp.status_code == 200

    rows = await _messages(db_session)
    assert [r.role for r in rows] == ["user", "assistant"]

    user, assistant = rows
    assert user.content == "what frameworks does he use?"
    assert user.status == "received"
    assert user.endpoint == "/chat"
    assert assistant.content == "hi from mock"
    assert assistant.status == "completed"
    # Both sides of one turn share the correlation id.
    assert user.request_id == assistant.request_id
    assert len(user.request_id) == 32
    assert assistant.latency_ms is not None

    conversations = await _conversations(db_session)
    assert len(conversations) == 1
    assert conversations[0].message_count == 2
    assert conversations[0].subject == "test-hire"
    assert conversations[0].company == "Acme"


async def test_chat_stream_persists_on_client_abort(
    client, issued_token, db_session, session_maker, openai_mock
):
    """
    The case the design exists for: the client hangs up mid-reply.

    Driven against the generator rather than through the test client, because
    httpx's ASGITransport buffers the whole response — a `break` there never
    closes the generator, so it cannot express an abort at all.

    This fails outright if the recorder reuses the request-scoped session: by the
    time a generator finalises, that session is closed.
    """
    from app.common.models import ChatRequest, TokenContext
    from app.services.chat import Chat
    from app.services.tools import get_chat_tool

    # A real token row, so the FKs resolve.
    token_row = (await db_session.execute(select(DatabaseToken))).scalars().first()
    token = TokenContext(
        sub=token_row.subject, jti=str(token_row.id),
        max_queries=token_row.max_queries, used_queries=1,
        remaining_queries=token_row.max_queries - 1,
        expires_at=token_row.expires_at,
    )

    async def _chunks():
        delta = MagicMock(content="partial ", tool_calls=None)
        yield MagicMock(choices=[MagicMock(delta=delta, finish_reason=None)])
        delta = MagicMock(content="never arrives", tool_calls=None)
        yield MagicMock(choices=[MagicMock(delta=delta, finish_reason="stop")])

    openai_mock.chat.completions.create = AsyncMock(return_value=_chunks())

    chat = Chat(
        openai_mock,
        tools=get_chat_tool(),
        session_factory=session_maker,
        endpoint="/chat/stream",
    )
    await chat.prepare(ChatRequest(message="tell me everything"), token)

    stream = chat.stream_response()
    await stream.__anext__()      # receive one token
    await stream.aclose()         # ...then the client goes away

    user_rows = await _messages(db_session, role="user")
    assert len(user_rows) == 1, "the question must survive regardless"
    assert user_rows[0].content == "tell me everything"

    assistant_rows = await _messages(db_session, role="assistant")
    assert len(assistant_rows) == 1
    assert assistant_rows[0].status == "aborted"
    assert assistant_rows[0].content == "partial ", "the partial reply is the point"


async def test_chat_persists_when_llm_fails(client, issued_token, db_session, openai_mock):
    """Proves the pre-write is the durability guarantee, not the terminal recorder."""
    openai_mock.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await client.post(
            "/chat",
            headers={"Authorization": f"Bearer {issued_token}"},
            json={"message": "does this survive?"},
        )

    user_rows = await _messages(db_session, role="user")
    assert len(user_rows) == 1
    assert user_rows[0].content == "does this survive?"

    assistant_rows = await _messages(db_session, role="assistant")
    assert len(assistant_rows) == 1
    assert assistant_rows[0].status == "failed"
    assert "RuntimeError" in assistant_rows[0].error


async def test_persistence_failure_does_not_break_chat(client, issued_token, monkeypatch):
    """Capturing the transcript is a convenience; it must never cost the hirer a reply."""
    async def _boom(*args, **kwargs):
        raise RuntimeError("database on fire")

    monkeypatch.setattr("app.services.chat.record_user_message", _boom)

    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 200
    assert resp.json()["reply"] == "hi from mock"


async def test_conversation_id_round_trips(client, issued_token, db_session):
    first = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "first"},
    )
    conversation_id = first.json()["conversation_id"]
    assert conversation_id

    second = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "second", "conversation_id": conversation_id},
    )
    assert second.json()["conversation_id"] == conversation_id

    conversations = await _conversations(db_session)
    assert len(conversations) == 1
    assert conversations[0].message_count == 4


async def test_conversation_id_from_another_token_is_ignored(client, db_session):
    """A guessed conversation id must not let one hirer append into another's thread."""
    import os

    async def _mint(subject):
        resp = await client.post(
            "/admin/issue-token",
            headers={"X-Admin-Key": os.environ["ADMIN_KEY"]},
            json={"subject": subject, "company": f"{subject}-co", "max_queries": 5},
        )
        return resp.json()["token"]

    token_a = await _mint("hirer-a")
    token_b = await _mint("hirer-b")

    a_resp = await client.post(
        "/chat", headers={"Authorization": f"Bearer {token_a}"}, json={"message": "from a"}
    )
    a_conversation = a_resp.json()["conversation_id"]

    b_resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"message": "from b", "conversation_id": a_conversation},
    )
    assert b_resp.status_code == 200, "a bad id must not break the chat"
    assert b_resp.json()["conversation_id"] != a_conversation

    conversations = await _conversations(db_session)
    assert len(conversations) == 2
    a_row = next(c for c in conversations if str(c.id) == a_conversation)
    assert a_row.message_count == 2, "A's conversation must be untouched"


async def test_chat_stream_done_event_includes_conversation_id(client, issued_token, openai_mock):
    openai_mock.chat.completions.create = AsyncMock(return_value=_stream_chunks())

    resp = await client.post(
        "/chat/stream",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "hi"},
    )
    done = next(
        json.loads(line.removeprefix("data: "))
        for line in resp.text.splitlines()
        if line.startswith("data: ") and '"reply"' in line
    )
    assert done["conversation_id"]
