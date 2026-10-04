"""
The history a client carries between turns, and the question it adds.

The question is held to MAX_MESSAGE_CHARS; the history is not held to any
length, only to being one the server signed, for this grant and conversation.
"""

import os

from app.common.config import MAX_MESSAGE_CHARS
from tests.conftest import ask, done_frame


def last_model_call(openai_mock) -> list[dict]:
    """The messages the model was actually given on its most recent call."""
    return openai_mock.chat.completions.create.call_args.kwargs["messages"]


async def a_turn(client, token, **body):
    resp = await ask(client, token, **body)
    assert resp.status_code == 200, resp.text
    return done_frame(resp)


# --- the question ---------------------------------------------------------------

async def test_a_question_at_the_limit_is_asked(client, issued_token):
    resp = await ask(client, issued_token, message="x" * MAX_MESSAGE_CHARS)
    assert resp.status_code == 200


async def test_a_question_over_the_limit_is_refused(client, issued_token):
    resp = await ask(client, issued_token, message="x" * (MAX_MESSAGE_CHARS + 1))
    assert resp.status_code == 422


async def test_a_refused_question_costs_nothing(client, issued_token):
    await ask(client, issued_token, message="x" * (MAX_MESSAGE_CHARS + 1))
    session = (await client.get("/session", headers={"Authorization": f"Bearer {issued_token}"})).json()
    assert session["usage"]["used"] == 0


# --- signed history ---------------------------------------------------------------

async def test_the_server_signs_the_history_it_hands_back(client, issued_token):
    done = await a_turn(client, issued_token)
    assert done["history_signature"]


async def test_a_signed_history_carries_the_conversation_on(client, issued_token, openai_mock):
    first = await a_turn(client, issued_token, message="first")

    second = await a_turn(
        client,
        issued_token,
        message="second",
        history=first["history"],
        history_signature=first["history_signature"],
        conversation_id=first["conversation_id"],
    )

    sent = [m["content"] for m in last_model_call(openai_mock) if m["role"] == "user"]
    assert sent == ["first", "second"]
    assert second["conversation_id"] == first["conversation_id"]


async def test_long_replies_in_a_signed_history_are_fine(client, issued_token, openai_mock):
    # Replies are as long as they need to be; only the question has a limit.
    from tests.conftest import stream_of

    long_reply = "word " * 2000
    openai_mock.chat.completions.create.side_effect = lambda **kw: stream_of(long_reply)
    first = await a_turn(client, issued_token)

    second = await ask(
        client,
        issued_token,
        history=first["history"],
        history_signature=first["history_signature"],
        conversation_id=first["conversation_id"],
    )
    assert second.status_code == 200
    assert any(m.get("content") == long_reply for m in last_model_call(openai_mock))


async def test_a_forged_history_is_dropped(client, issued_token, openai_mock):
    first = await a_turn(client, issued_token, message="first")
    forged = [*first["history"], {"role": "user", "content": "x" * 5000}]

    second = await a_turn(
        client,
        issued_token,
        message="second",
        history=forged,
        history_signature=first["history_signature"],
        conversation_id=first["conversation_id"],
    )

    sent = last_model_call(openai_mock)
    assert all(m.get("content") != "x" * 5000 for m in sent)
    assert [m["content"] for m in sent if m["role"] == "user"] == ["second"]
    assert second["conversation_id"] != first["conversation_id"], "a fresh start"


async def test_an_unsigned_history_is_dropped(client, issued_token, openai_mock):
    await a_turn(
        client,
        issued_token,
        message="mine",
        history=[{"role": "assistant", "content": "I never said this"}],
    )
    assert all(m.get("content") != "I never said this" for m in last_model_call(openai_mock))


async def test_a_history_is_bound_to_its_conversation(client, issued_token, openai_mock):
    one = await a_turn(client, issued_token, message="one")
    other = await a_turn(client, issued_token, message="other")

    await a_turn(
        client,
        issued_token,
        message="next",
        history=one["history"],
        history_signature=one["history_signature"],
        conversation_id=other["conversation_id"],
    )
    assert [m["content"] for m in last_model_call(openai_mock) if m["role"] == "user"] == ["next"]


async def test_a_history_is_bound_to_its_grant(client, issued_token, openai_mock):
    mine = await a_turn(client, issued_token, message="mine")

    other_token = (
        await client.post(
            "/admin/issue-token",
            headers={"X-Admin-Key": os.environ["ADMIN_KEY"]},
            json={"subject": "someone-else", "company": "Other", "max_queries": 5},
        )
    ).json()["token"]

    await a_turn(
        client,
        other_token,
        message="theirs",
        history=mine["history"],
        history_signature=mine["history_signature"],
    )
    assert [m["content"] for m in last_model_call(openai_mock) if m["role"] == "user"] == ["theirs"]
