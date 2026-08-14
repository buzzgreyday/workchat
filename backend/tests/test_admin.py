import os


async def test_missing_admin_key_rejected(client):
    resp = await client.post(
        "/admin/issue-token",
        json={"subject": "s", "company": "c"},
    )
    # Header(...) is required — FastAPI returns 422 when it's absent.
    assert resp.status_code == 422


async def test_wrong_admin_key_forbidden(client):
    resp = await client.post(
        "/admin/issue-token",
        headers={"X-Admin-Key": "not-the-real-key"},
        json={"subject": "s", "company": "c"},
    )
    assert resp.status_code == 403


async def test_issue_token_happy_path(client):
    resp = await client.post(
        "/admin/issue-token",
        headers={"X-Admin-Key": os.environ["ADMIN_KEY"]},
        json={"subject": "s", "company": "c", "max_queries": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body.get("token"), str)
    assert body["token"].count(".") == 2  # JWT has three segments


async def test_issue_second_token_for_existing_company(client):
    """Re-issuing for a company already in the DB hits the get_or_create_user
    'user exists' branch — regression test for a logger.info(extra=<ORM obj>)
    bug that raised TypeError on this path."""
    headers = {"X-Admin-Key": os.environ["ADMIN_KEY"]}
    first = await client.post(
        "/admin/issue-token",
        headers=headers,
        json={"subject": "s1", "company": "Acme", "max_queries": 3},
    )
    assert first.status_code == 200

    second = await client.post(
        "/admin/issue-token",
        headers=headers,
        json={"subject": "s2", "company": "Acme", "max_queries": 3},
    )
    assert second.status_code == 200
    assert second.json()["token"] != first.json()["token"]

async def test_admin_conversations_requires_key(client):
    resp = await client.get("/admin/conversations")
    assert resp.status_code == 422  # header missing entirely

    resp = await client.get("/admin/conversations", headers={"X-Admin-Key": "wrong"})
    assert resp.status_code == 403


async def test_admin_conversations_lists_what_was_asked(client, issued_token):
    await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "does he know FastAPI?"},
    )

    resp = await client.get(
        "/admin/conversations", headers={"X-Admin-Key": os.environ["ADMIN_KEY"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["subject"] == "test-hire"
    assert body[0]["company"] == "Acme"
    assert body[0]["message_count"] == 2
    assert body[0]["preview"] == "does he know FastAPI?"


async def test_admin_conversation_detail_returns_transcript(client, issued_token):
    chat = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "what about Pyramid?"},
    )
    conversation_id = chat.json()["conversation_id"]

    resp = await client.get(
        f"/admin/conversations/{conversation_id}",
        headers={"X-Admin-Key": os.environ["ADMIN_KEY"]},
    )
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "what about Pyramid?"
    assert messages[1]["content"] == "hi from mock"


async def test_admin_conversation_detail_404s_for_unknown_id(client):
    import uuid as _uuid

    resp = await client.get(
        f"/admin/conversations/{_uuid.uuid4()}",
        headers={"X-Admin-Key": os.environ["ADMIN_KEY"]},
    )
    assert resp.status_code == 404


async def test_admin_redact_nulls_content_but_keeps_row(client, issued_token):
    chat = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {issued_token}"},
        json={"message": "sensitive question"},
    )
    conversation_id = chat.json()["conversation_id"]

    resp = await client.post(
        f"/admin/conversations/{conversation_id}/redact",
        headers={"X-Admin-Key": os.environ["ADMIN_KEY"]},
    )
    assert resp.status_code == 200
    assert resp.json()["messages_redacted"] == 2

    detail = await client.get(
        f"/admin/conversations/{conversation_id}",
        headers={"X-Admin-Key": os.environ["ADMIN_KEY"]},
    )
    body = detail.json()
    # The record survives; only the text is gone.
    assert body["message_count"] == 2
    assert body["redacted_at"] is not None
    for message in body["messages"]:
        assert message["content"] is None
        assert message["redacted_at"] is not None
        assert message["content_chars"] > 0
