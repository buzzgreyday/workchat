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