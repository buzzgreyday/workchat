"""
Both token versions, side by side.

The v1 half of this file is the point of the branch: those tests describe the
tokens already handed out, and they must keep passing unchanged for as long as
any of those links is still in an inbox.
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select, update

from app.common.config import ALGORITHM, REFRESH_COOKIE_NAME, SECRET_KEY
from app.common.schemas import DatabaseRefreshToken, DatabaseToken

ADMIN_HEADERS = {"X-Admin-Key": os.environ["ADMIN_KEY"]}


async def issue(client, version=1, **overrides):
    body = {"subject": "test-hire", "company": "Acme", "max_queries": 5, "version": version}
    body.update(overrides)
    resp = await client.post("/admin/issue-token", headers=ADMIN_HEADERS, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def claim_session(client, claim_token):
    """Exchange a claim link. The refresh token arrives as a cookie, so it is
    read off the jar rather than out of the body — the body never carries it."""
    resp = await client.post("/v2/auth/claim", json={"claim_token": claim_token})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    body["refresh_token"] = client.cookies.get(REFRESH_COOKIE_NAME)
    return body


async def refresh_via_cookie(client):
    """What a browser does: the jar carries the token, nothing is in the body."""
    resp = await client.post("/v2/auth/refresh")
    if resp.status_code == 200:
        body = resp.json()
        body["refresh_token"] = client.cookies.get(REFRESH_COOKIE_NAME)
        return resp, body
    return resp, None


async def refresh_with(client, raw_token):
    """Present a specific token via the body. The jar is cleared first because
    the cookie wins when both are present, which would defeat the point."""
    client.cookies.clear()
    return await client.post("/v2/auth/refresh", json={"refresh_token": raw_token})


async def chat(client, access_token, message="hi"):
    return await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"message": message},
    )


def decode(token):
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


@pytest.fixture
def notifications(monkeypatch):
    """Records what the operator would have been told."""
    sent = []

    class Recorder:
        async def claim_link_reused(self, token_id, subject, company):
            sent.append(("claim_reuse", str(token_id), subject))

        async def sessions_cut(self, token_id, subject, company, reason):
            sent.append(("sessions_cut", str(token_id), subject))

    monkeypatch.setattr("app.services.auth.notifier", Recorder())
    return sent


async def backdate_rotation(session_maker, minutes=10):
    """Push every rotation stamp into the past so the grace window has lapsed and
    the next presentation counts as a genuine replay."""
    async with session_maker() as db:
        await db.execute(
            update(DatabaseRefreshToken)
            .where(DatabaseRefreshToken.revoked_at.is_not(None))
            .values(revoked_at=datetime.now(timezone.utc) - timedelta(minutes=minutes))
            .execution_options(synchronize_session=False)
        )
        await db.commit()


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
    resp = await chat(client, body["token"])
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


async def test_refresh_token_never_appears_in_a_response_body(client):
    """The whole reason for the cookie: script on the page must not be able to
    read the long-lived half of the pair."""
    claim = await issue(client, version=2)
    resp = await client.post("/v2/auth/claim", json={"claim_token": claim["token"]})

    assert "refresh_token" not in resp.json()
    assert "refresh_token" not in resp.text

    set_cookie = resp.headers["set-cookie"]
    assert REFRESH_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie.replace("samesite=strict", "SameSite=strict")


async def test_claim_returns_a_usable_session(client):
    claim = await issue(client, version=2)
    session = await claim_session(client, claim["token"])

    assert session["token_type"] == "bearer"
    assert 0 < session["expires_in"] <= 60 * 15
    assert session["expires_in"] < session["refresh_expires_in"]

    access = decode(session["access_token"])
    assert access["ver"] == 2 and access["typ"] == "access"
    assert access["tid"] == decode(claim["token"])["tid"]
    assert access["sid"] == decode(session["refresh_token"])["jti"]

    resp = await chat(client, session["access_token"])
    assert resp.status_code == 200
    assert resp.json()["usage"]["used"] == 1


async def test_claim_costs_no_quota(client):
    """Exchanging a link must not spend one of the hirer's questions."""
    claim = await issue(client, version=2)
    session = await claim_session(client, claim["token"])

    resp = await chat(client, session["access_token"])
    assert resp.json()["usage"]["used"] == 1


async def test_claim_is_single_use(client, notifications):
    """One link, one session. A second presentation is refused and the operator
    is told, because only they can issue a replacement."""
    claim = await issue(client, version=2)
    await claim_session(client, claim["token"])

    resp = await client.post("/v2/auth/claim", json={"claim_token": claim["token"]})
    assert resp.status_code == 409
    assert "already been used" in resp.json()["detail"]

    assert [event for event, _, _ in notifications] == ["claim_reuse"]
    assert notifications[0][2] == "test-hire"


async def test_repeated_claim_reuse_notifies_once(client, notifications):
    """A dead link hit in a loop is one thing worth hearing about, not five."""
    claim = await issue(client, version=2)
    await claim_session(client, claim["token"])

    for _ in range(5):
        resp = await client.post("/v2/auth/claim", json={"claim_token": claim["token"]})
        assert resp.status_code == 409

    assert len(notifications) == 1


async def test_racing_claims_open_exactly_one_session(client):
    """Two requests arriving together cannot both pass the claimed_at gate."""
    claim = await issue(client, version=2)
    results = await asyncio.gather(*[
        client.post("/v2/auth/claim", json={"claim_token": claim["token"]})
        for _ in range(4)
    ])
    assert sorted(r.status_code for r in results) == [200, 409, 409, 409]


async def test_refresh_rotates_and_retires_the_old_token(client):
    claim = await issue(client, version=2)
    first = await claim_session(client, claim["token"])

    resp, second = await refresh_via_cookie(client)
    assert resp.status_code == 200
    assert second["refresh_token"] != first["refresh_token"]

    assert (await chat(client, second["access_token"])).status_code == 200


async def test_rotation_retires_the_previous_access_token(client):
    """An access token dies with the refresh token it was minted alongside, even
    though that one was merely rotated rather than cut."""
    claim = await issue(client, version=2)
    first = await claim_session(client, claim["token"])
    _, second = await refresh_via_cookie(client)

    resp = await chat(client, first["access_token"])
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Session revoked"

    assert (await chat(client, second["access_token"])).status_code == 200


# --- the rotation grace window -----------------------------------------------

async def test_concurrent_refresh_does_not_lock_the_hirer_out(client):
    """
    The failure this window exists for.

    Three chat requests expiring at once and each retrying a refresh used to be
    read as two replays, which cut the grant and logged the hirer out of the tab
    they were sitting in. Now the losers get a soft 409 and the winner's session
    is untouched.
    """
    claim = await issue(client, version=2)
    session = await claim_session(client, claim["token"])
    raw = session["refresh_token"]

    # Cleared so all three present the same token via the body; the cookie would
    # otherwise win and each request would carry whatever the jar last saw.
    client.cookies.clear()
    results = await asyncio.gather(*[
        client.post("/v2/auth/refresh", json={"refresh_token": raw})
        for _ in range(3)
    ])
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409, 409], [r.json() for r in results]

    winner = next(r for r in results if r.status_code == 200)
    loser = next(r for r in results if r.status_code == 409)
    assert "retry with the newest token" in loser.json()["detail"]

    # The winner's brand new access token still works — that is the whole point.
    assert (await chat(client, winner.json()["access_token"])).status_code == 200


async def test_replay_outside_the_grace_window_cuts_every_session(
    client, session_maker, notifications
):
    """Past the window, a re-presented token is a genuine replay: the grant's
    sessions are cut and the operator is told the hirer needs a new link."""
    claim = await issue(client, version=2)
    session = await claim_session(client, claim["token"])
    raw = session["refresh_token"]

    resp, rotated = await refresh_via_cookie(client)
    assert resp.status_code == 200

    await backdate_rotation(session_maker)

    replay = await refresh_with(client, raw)
    assert replay.status_code == 401
    assert replay.json()["detail"] == "Refresh token already used"
    assert [event for event, _, _ in notifications] == ["sessions_cut"]

    # The successor dies with the rest, and a single-use claim offers no way back.
    assert (await chat(client, rotated["access_token"])).status_code == 401
    assert (await client.post(
        "/v2/auth/claim", json={"claim_token": claim["token"]}
    )).status_code == 409


# --- admin revocation --------------------------------------------------------

async def test_admin_can_revoke_a_grant(client):
    claim = await issue(client, version=2)
    session = await claim_session(client, claim["token"])
    grant_id = decode(claim["token"])["tid"]

    assert (await chat(client, session["access_token"])).status_code == 200

    resp = await client.post(f"/admin/tokens/{grant_id}/revoke", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["already_revoked"] is False
    assert resp.json()["sessions_cut"] == 1

    assert (await chat(client, session["access_token"])).status_code == 401
    assert (await refresh_via_cookie(client))[0].status_code == 401


async def test_revoking_a_grant_stops_a_v1_token_too(client):
    """The kill switch has to work on the links already handed out, which are
    the ones most likely to need it."""
    body = await issue(client)
    grant_id = decode(body["token"])["jti"]
    assert (await chat(client, body["token"])).status_code == 200

    resp = await client.post(f"/admin/tokens/{grant_id}/revoke", headers=ADMIN_HEADERS)
    assert resp.status_code == 200

    resp = await chat(client, body["token"])
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Token revoked"


async def test_revoke_is_idempotent_and_guards_its_inputs(client):
    claim = await issue(client, version=2)
    grant_id = decode(claim["token"])["tid"]

    first = await client.post(f"/admin/tokens/{grant_id}/revoke", headers=ADMIN_HEADERS)
    second = await client.post(f"/admin/tokens/{grant_id}/revoke", headers=ADMIN_HEADERS)
    assert first.json()["already_revoked"] is False
    assert second.json()["already_revoked"] is True

    assert (await client.post(
        f"/admin/tokens/{uuid.uuid4()}/revoke", headers=ADMIN_HEADERS
    )).status_code == 404
    assert (await client.post(f"/admin/tokens/{grant_id}/revoke")).status_code == 422
    assert (await client.post(
        f"/admin/tokens/{grant_id}/revoke", headers={"X-Admin-Key": "wrong"}
    )).status_code == 403


async def test_revoked_grant_cannot_be_claimed(client):
    """Revocation has to beat the claim link, or anyone holding the URL just
    opens a fresh session and the kill switch means nothing."""
    claim = await issue(client, version=2)
    grant_id = decode(claim["token"])["tid"]

    await client.post(f"/admin/tokens/{grant_id}/revoke", headers=ADMIN_HEADERS)

    resp = await client.post("/v2/auth/claim", json={"claim_token": claim["token"]})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Token revoked"


# --- v2: what must not be accepted -------------------------------------------

@pytest.mark.parametrize("kind", ["claim", "refresh"])
async def test_only_access_tokens_buy_a_chat(client, kind):
    """A claim and a refresh token are both validly signed. Signature alone must
    not be enough to reach /chat."""
    claim = await issue(client, version=2)
    session = await claim_session(client, claim["token"])
    token = claim["token"] if kind == "claim" else session["refresh_token"]

    resp = await chat(client, token)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not an access token"


async def test_access_token_cannot_be_used_to_refresh(client):
    claim = await issue(client, version=2)
    session = await claim_session(client, claim["token"])

    resp = await refresh_with(client, session["access_token"])
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not a refresh token"


async def test_refresh_without_a_token_at_all(client):
    assert (await client.post("/v2/auth/refresh")).status_code == 401


async def test_refresh_token_cannot_be_spent_against_another_grant(client):
    """The session belongs to one grant. Pointing its token at a second grant's
    id is the shape of attack that would spend someone else's quota."""
    mine = await issue(client, version=2)
    theirs = await issue(client, version=2, subject="other-hire", company="Globex")

    session = await claim_session(client, mine["token"])
    payload = decode(session["refresh_token"])
    payload["tid"] = decode(theirs["token"])["tid"]
    forged = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    assert (await refresh_with(client, forged)).status_code == 401


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
    payload = decode(claim["token"])
    forged = jwt.encode(
        {"sub": payload["sub"], "iat": payload["iat"], "exp": payload["exp"],
         "jti": payload["tid"], "max_queries": 5},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    assert (await chat(client, forged)).status_code == 401

    # And the rejection cost the grant nothing.
    session = await claim_session(client, claim["token"])
    assert (await chat(client, session["access_token"])).json()["usage"]["used"] == 1


async def test_unknown_token_version_rejected(client):
    claim = await issue(client, version=2)
    payload = decode(claim["token"])
    payload["ver"] = 99
    forged = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    resp = await chat(client, forged)
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
    session = await claim_session(client, claim["token"])

    grant_exp = decode(claim["token"])["exp"]
    assert decode(session["refresh_token"])["exp"] <= grant_exp
    assert decode(session["access_token"])["exp"] <= grant_exp
    assert session["refresh_expires_in"] <= 120


async def test_claimed_at_is_stamped_once(client, session_maker):
    claim = await issue(client, version=2)
    await claim_session(client, claim["token"])

    async with session_maker() as db:
        grant = (await db.execute(
            select(DatabaseToken).where(DatabaseToken.id == uuid.UUID(decode(claim["token"])["tid"]))
        )).scalar_one()
        assert grant.claimed_at is not None
        assert grant.version == 2


# --- GET /session ------------------------------------------------------------

async def test_session_reports_usage_before_any_question_v1(client):
    """The point of the endpoint: the allowance is knowable on load, not only as
    a side effect of having already spent one."""
    body = await issue(client)

    resp = await client.get("/session", headers={"Authorization": f"Bearer {body['token']}"})
    assert resp.status_code == 200
    info = resp.json()
    assert info["subject"] == "test-hire"
    assert info["version"] == 1
    assert info["usage"] == {"used": 0, "remaining": 5, "max": 5}
    assert info["session_id"] is None
    assert info["expires_at"]


async def test_session_reports_usage_for_v2(client):
    claim = await issue(client, version=2)
    session = await claim_session(client, claim["token"])

    resp = await client.get(
        "/session", headers={"Authorization": f"Bearer {session['access_token']}"}
    )
    assert resp.status_code == 200
    info = resp.json()
    assert info["version"] == 2
    assert info["usage"] == {"used": 0, "remaining": 5, "max": 5}
    # Which device this is, so a session can be told apart in the admin log.
    assert info["session_id"] == decode(session["refresh_token"])["jti"]


async def test_session_spends_nothing(client):
    """Reading the meter must not move it — otherwise polling it would cost the
    hirer the very questions it is reporting on."""
    body = await issue(client)
    headers = {"Authorization": f"Bearer {body['token']}"}

    for _ in range(5):
        assert (await client.get("/session", headers=headers)).json()["usage"]["used"] == 0

    await chat(client, body["token"])
    assert (await client.get("/session", headers=headers)).json()["usage"] == {
        "used": 1, "remaining": 4, "max": 5,
    }


async def test_session_reports_zero_rather_than_refusing(client):
    """An exhausted grant is a state to display, not an error. A hirer with none
    left is exactly the person who needs to be told how many they have."""
    body = await issue(client, max_queries=1)
    headers = {"Authorization": f"Bearer {body['token']}"}

    assert (await chat(client, body["token"])).status_code == 200
    # The next question is refused...
    assert (await chat(client, body["token"])).status_code == 429
    # ...but the meter still reads.
    resp = await client.get("/session", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["usage"] == {"used": 1, "remaining": 0, "max": 1}


async def test_session_rejects_what_chat_rejects(client):
    """The two must agree on what a valid token is: reporting a usable session
    that the next request then refuses would be worse than no endpoint."""
    assert (await client.get("/session")).status_code == 401

    claim = await issue(client, version=2)
    # A claim token is validly signed but is not an access token.
    resp = await client.get("/session", headers={"Authorization": f"Bearer {claim['token']}"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not an access token"


async def test_session_dies_with_a_revoked_grant(client):
    claim = await issue(client, version=2)
    session = await claim_session(client, claim["token"])
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    assert (await client.get("/session", headers=headers)).status_code == 200

    grant_id = decode(claim["token"])["tid"]
    await client.post(f"/admin/tokens/{grant_id}/revoke", headers=ADMIN_HEADERS)

    resp = await client.get("/session", headers=headers)
    assert resp.status_code == 401
    assert resp.json()["detail"] in {"Token revoked", "Session revoked"}
