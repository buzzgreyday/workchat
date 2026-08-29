"""
Both token versions, side by side.

The v1 half of this file is the point of the branch: those tests describe the
tokens already handed out, and they must keep passing unchanged for as long as
any of those links is still in an inbox.
"""
import os
import uuid

import jwt
import pytest

from app.common.config import ALGORITHM, SECRET_KEY

ADMIN_HEADERS = {"X-Admin-Key": os.environ["ADMIN_KEY"]}


async def issue(client, version=1, **overrides):
    body = {"subject": "test-hire", "company": "Acme", "max_queries": 5, "version": version}
    body.update(overrides)
    resp = await client.post("/admin/issue-token", headers=ADMIN_HEADERS, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def claim_pair(client, claim_token):
    resp = await client.post("/v2/auth/claim", json={"claim_token": claim_token})
    assert resp.status_code == 200, resp.text
    return resp.json()


def decode(token):
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# --- v1: the tokens already in the wild --------------------------------------

async def test_v1_token_shape_is_unchanged(client):
    """The claim set a v1 token carries is the compatibility contract. `ver` must
    stay absent — its absence is the only thing marking these as version 1."""
    body = await issue(client)
    assert body["version"] == 1 and body["kind"] == "access"

    payload = decode(body["token"])
    assert set(payload) == {"sub", "iat", "exp", "jti", "max_queries"}
    assert payload["sub"] == "test-hire"
    assert payload["max_queries"] == 5


async def test_v1_token_still_buys_a_chat(client):
    body = await issue(client)
    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {body['token']}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 200
    assert resp.json()["usage"] == {"used": 1, "remaining": 4, "max": 5}


async def test_v1_token_cannot_be_claimed(client):
    """A v1 token is an access token, not a claim. It has no business at /v2/auth."""
    body = await issue(client)
    resp = await client.post("/v2/auth/claim", json={"claim_token": body["token"]})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not a claim token"


# --- v2: claim -> access + refresh -------------------------------------------

async def test_issue_v2_mints_a_claim_token(client):
    body = await issue(client, version=2)
    assert body["version"] == 2 and body["kind"] == "claim"

    payload = decode(body["token"])
    assert payload["ver"] == 2
    assert payload["typ"] == "claim"
    # The grant lives in `tid` now; `jti` is the claim token's own id.
    assert payload["tid"] != payload["jti"]
    assert "max_queries" not in payload


async def test_claim_returns_a_usable_pair(client):
    claim = await issue(client, version=2)
    pair = await claim_pair(client, claim["token"])

    assert pair["token_type"] == "bearer"
    assert 0 < pair["expires_in"] <= 60 * 15
    assert pair["expires_in"] < pair["refresh_expires_in"]

    access = decode(pair["access_token"])
    assert access["ver"] == 2 and access["typ"] == "access"
    assert access["tid"] == decode(claim["token"])["tid"]
    assert access["sid"] == decode(pair["refresh_token"])["jti"]

    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 200
    assert resp.json()["usage"]["used"] == 1


async def test_claim_costs_no_quota(client):
    """Exchanging a link must not spend one of the hirer's questions."""
    claim = await issue(client, version=2)
    pair = await claim_pair(client, claim["token"])

    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
        json={"message": "hi"},
    )
    assert resp.json()["usage"]["used"] == 1


async def test_claim_is_reusable_and_opens_a_second_session(client):
    """The link is what the hirer was given; reopening it on another device has
    to work, and must not knock the first device offline."""
    claim = await issue(client, version=2)
    laptop = await claim_pair(client, claim["token"])
    phone = await claim_pair(client, claim["token"])

    assert decode(laptop["refresh_token"])["jti"] != decode(phone["refresh_token"])["jti"]

    for pair in (laptop, phone):
        resp = await client.post(
            "/chat",
            headers={"Authorization": f"Bearer {pair['access_token']}"},
            json={"message": "hi"},
        )
        assert resp.status_code == 200
    # One grant, one quota: two devices do not get ten questions between them.
    assert resp.json()["usage"] == {"used": 2, "remaining": 3, "max": 5}


async def test_refresh_rotates_and_retires_the_old_token(client):
    claim = await issue(client, version=2)
    first = await claim_pair(client, claim["token"])

    resp = await client.post("/v2/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert resp.status_code == 200
    second = resp.json()
    assert second["refresh_token"] != first["refresh_token"]

    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {second['access_token']}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 200


async def test_replaying_a_refresh_token_cuts_every_session(client):
    """Nothing can tell a retried request from a stolen token, so a second use
    of the same refresh token takes the whole grant's sessions down."""
    claim = await issue(client, version=2)
    laptop = await claim_pair(client, claim["token"])
    phone = await claim_pair(client, claim["token"])

    rotated = (await client.post(
        "/v2/auth/refresh", json={"refresh_token": laptop["refresh_token"]}
    )).json()

    replay = await client.post("/v2/auth/refresh", json={"refresh_token": laptop["refresh_token"]})
    assert replay.status_code == 401
    assert replay.json()["detail"] == "Refresh token already used"

    # The successor and the untouched phone session both die with the grant's
    # sessions; re-claiming is the way back in.
    for pair in (rotated, phone):
        resp = await client.post(
            "/chat",
            headers={"Authorization": f"Bearer {pair['access_token']}"},
            json={"message": "hi"},
        )
        assert resp.status_code == 401, resp.text

    recovered = await claim_pair(client, claim["token"])
    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {recovered['access_token']}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 200


async def test_rotation_retires_the_previous_access_token(client):
    """An access token dies with the refresh token it was minted alongside, even
    though that one was merely rotated rather than cut. Sparing rotated rows
    would leave an access token from an earlier rotation working after replay
    detection had supposedly cut the grant."""
    claim = await issue(client, version=2)
    first = await claim_pair(client, claim["token"])
    second = (await client.post(
        "/v2/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )).json()

    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {first['access_token']}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Session revoked"

    # The pair the same call handed back is what the client carries on with.
    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {second['access_token']}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 200


# --- v2: what must not be accepted -------------------------------------------

@pytest.mark.parametrize("kind", ["claim_token", "refresh_token"])
async def test_only_access_tokens_buy_a_chat(client, kind):
    """A claim and a refresh token are both validly signed. Signature alone must
    not be enough to reach /chat."""
    claim = await issue(client, version=2)
    pair = await claim_pair(client, claim["token"])
    token = claim["token"] if kind == "claim_token" else pair["refresh_token"]

    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not an access token"


async def test_access_token_cannot_be_used_to_refresh(client):
    claim = await issue(client, version=2)
    pair = await claim_pair(client, claim["token"])

    resp = await client.post("/v2/auth/refresh", json={"refresh_token": pair["access_token"]})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not a refresh token"


async def test_refresh_token_cannot_be_spent_against_another_grant(client):
    """The session belongs to one grant. Pointing its token at a second grant's
    id is the shape of attack that would spend someone else's quota."""
    mine = await issue(client, version=2)
    theirs = await issue(client, version=2, subject="other-hire", company="Globex")

    pair = await claim_pair(client, mine["token"])
    payload = decode(pair["refresh_token"])
    payload["tid"] = decode(theirs["token"])["tid"]
    forged = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    resp = await client.post("/v2/auth/refresh", json={"refresh_token": forged})
    assert resp.status_code == 401


async def test_claim_token_bound_to_its_grant_row(client):
    """A validly signed claim naming a grant it was not minted for is refused —
    the stored hash, not just the signature, decides."""
    mine = await issue(client, version=2)
    theirs = await issue(client, version=2, subject="other-hire", company="Globex")

    payload = decode(mine["token"])
    payload["tid"] = decode(theirs["token"])["tid"]
    forged = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    resp = await client.post("/v2/auth/claim", json={"claim_token": forged})
    assert resp.status_code == 401


async def test_v1_shaped_token_rejected_against_a_v2_grant(client):
    """Belt and braces on the version predicate: a v1-shaped token whose jti is a
    v2 grant must not consume that grant's quota."""
    claim = await issue(client, version=2)
    grant_id = decode(claim["token"])["tid"]
    payload = decode(claim["token"])
    forged = jwt.encode(
        {"sub": payload["sub"], "iat": payload["iat"], "exp": payload["exp"],
         "jti": grant_id, "max_queries": 5},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {forged}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 401

    # And the rejection cost the grant nothing.
    pair = await claim_pair(client, claim["token"])
    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
        json={"message": "hi"},
    )
    assert resp.json()["usage"]["used"] == 1


async def test_unknown_token_version_rejected(client):
    claim = await issue(client, version=2)
    payload = decode(claim["token"])
    payload["ver"] = 99
    forged = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {forged}"},
        json={"message": "hi"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unsupported token version"


async def test_claim_for_an_unknown_grant_rejected(client):
    claim = await issue(client, version=2)
    payload = decode(claim["token"])
    payload["tid"] = str(uuid.uuid4())
    forged = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    resp = await client.post("/v2/auth/claim", json={"claim_token": forged})
    assert resp.status_code == 401


async def test_derived_tokens_never_outlive_the_grant(client):
    """A refresh token minted just before a grant lapses must not keep rotating
    past it — the grant's expiry is the hard end date."""
    claim = await issue(client, version=2, expires_in_seconds=120)
    pair = await claim_pair(client, claim["token"])

    grant_exp = decode(claim["token"])["exp"]
    assert decode(pair["refresh_token"])["exp"] <= grant_exp
    assert decode(pair["access_token"])["exp"] <= grant_exp
    assert pair["refresh_expires_in"] <= 120
