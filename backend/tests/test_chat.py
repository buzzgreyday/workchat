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