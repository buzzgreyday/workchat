"""
Guest trials: a few questions for a visitor with no link, earned with a
proof-of-work, one per address per day, within a ceiling per day.

Each test drives the real endpoints. The proof-of-work is solved here the way a
browser solves it — by trying numbers — at the cheap difficulty conftest sets.
"""

import base64
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import httpx
import jwt
import pytest
from httpx import ASGITransport
from sqlalchemy import func, select

from app.common.config import ALGORITHM, REFRESH_COOKIE_NAME, get_settings
from app.common.schemas import DatabaseToken, DatabaseTrialBudget, DatabaseTrialRequest
from app.services.trial import keys, pow
from tests.conftest import ask


def solve(challenge: dict) -> str:
    """Find the number, as the browser's worker does, and pack the answer."""
    for number in range(challenge["maxnumber"] + 1):
        digest = hashlib.sha256(f"{challenge['salt']}{number}".encode()).hexdigest()
        if digest == challenge["challenge"]:
            return base64.b64encode(json.dumps({**challenge, "number": number}).encode()).decode()
    raise AssertionError("challenge has no solution")


async def solution(client) -> str:
    resp = await client.get("/v2/auth/trial/challenge")
    assert resp.status_code == 200, resp.text
    return solve(resp.json())


async def start(client, payload: str | None = None):
    return await client.post("/v2/auth/trial", json={"solution": payload or await solution(client)})


@asynccontextmanager
async def visitor(app, ip: str):
    """A client arriving from this address — the socket peer, which is what the
    backend believes while TRUST_PROXY_HEADERS is off, as it is in tests."""
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app, client=(ip, 4321)), base_url="http://test"
    ) as c:
        yield c


def claims(access_token: str) -> dict:
    return jwt.decode(access_token, get_settings().secret_key, algorithms=[ALGORITHM])


@pytest.fixture
def settings_with(monkeypatch):
    """Run a test against settings other than the suite's, then put them back."""
    def apply(**changes):
        changed = replace(get_settings(), **changes)
        monkeypatch.setattr("app.routes.auth.get_settings", lambda: changed)
        return changed
    return apply


# --- the happy path ------------------------------------------------------------

async def test_a_trial_opens_a_session_like_a_claim(client, session_maker):
    resp = await start(client)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert client.cookies.get(REFRESH_COOKIE_NAME), "the refresh token rides in a cookie"
    assert "refresh_token" not in body

    token = claims(body["access_token"])
    assert token["sub"] == "Guest"
    assert token["knd"] == "trial"

    async with session_maker() as s:
        grant = (await s.execute(select(DatabaseToken))).scalar_one()
    assert grant.kind == "trial"
    assert grant.max_queries == get_settings().trial_max_queries
    assert grant.claimed_at is not None, "a trial is its own session from the start"


async def test_a_trial_has_its_few_questions_and_no_more(client):
    access = (await start(client)).json()["access_token"]

    for _ in range(get_settings().trial_max_queries):
        assert (await ask(client, access)).status_code == 200

    spent = await ask(client, access)
    assert spent.status_code == 429
    assert spent.json()["detail"] == "Query limit reached"


async def test_a_trial_session_refreshes_like_any_other(client):
    await start(client)

    resp = await client.post("/v2/auth/refresh")
    assert resp.status_code == 200, resp.text
    assert claims(resp.json()["access_token"])["knd"] == "trial"


# --- one per address per day -----------------------------------------------------

async def test_one_trial_per_address_per_day(app, client):
    async with visitor(app, "203.0.113.7") as first, visitor(app, "203.0.113.7") as again:
        assert (await start(first)).status_code == 200
        refused = await start(again)

    assert refused.status_code == 429
    assert refused.json()["detail"] == "Trial already used today"


async def test_another_address_gets_its_own(app, client):
    async with visitor(app, "203.0.113.7") as one, visitor(app, "198.51.100.9") as other:
        assert (await start(one)).status_code == 200
        assert (await start(other)).status_code == 200


async def test_one_household_on_ipv6_is_one_address(app, client):
    # A home is handed a whole /64; rotating within it is not a new visitor.
    async with visitor(app, "2001:db8:1:2::1") as one, visitor(app, "2001:db8:1:2:ffff::9") as same:
        assert (await start(one)).status_code == 200
        assert (await start(same)).status_code == 429


async def test_the_address_is_never_stored(app, client, session_maker):
    async with visitor(app, "203.0.113.7") as v:
        await start(v)

    async with session_maker() as s:
        row = (await s.execute(select(DatabaseTrialRequest))).scalar_one()
    assert "203.0.113" not in row.ip_hash
    assert row.ip_hash != hashlib.sha256(b"203.0.113.7").hexdigest(), "keyed, not a guessable plain hash"


def test_an_address_hashes_differently_every_day():
    today = date(2026, 10, 4)
    assert keys.address_hash("s", today, "203.0.113.7") != keys.address_hash(
        "s", today + timedelta(days=1), "203.0.113.7"
    )


async def test_earlier_days_are_forgotten(app, client, session_maker):
    async with session_maker() as s:
        s.add(DatabaseTrialRequest(day=date(2020, 1, 1), ip_hash="old", challenge_hash="old"))
        await s.commit()

    await start(client)

    async with session_maker() as s:
        days = (await s.execute(select(DatabaseTrialRequest.day))).scalars().all()
    assert date(2020, 1, 1) not in days


async def test_forwarded_for_is_ignored_unless_trusted(app, client, settings_with):
    # Two requests from the same peer, claiming different addresses: believed
    # only behind the proxy that writes the header itself.
    first = await client.post(
        "/v2/auth/trial",
        json={"solution": await solution(client)},
        headers={"X-Forwarded-For": "203.0.113.1"},
    )
    second = await client.post(
        "/v2/auth/trial",
        json={"solution": await solution(client)},
        headers={"X-Forwarded-For": "203.0.113.2"},
    )
    assert first.status_code == 200
    assert second.status_code == 429, "same peer, so same address, whatever the header says"


async def test_forwarded_for_is_believed_behind_the_proxy(app, client, monkeypatch):
    trusted = replace(get_settings(), trust_proxy_headers=True)
    monkeypatch.setattr("app.common.client_ip.get_settings", lambda: trusted)

    async def from_(address):
        return await client.post(
            "/v2/auth/trial",
            json={"solution": await solution(client)},
            # A spoofed first hop and the proxy's own last one: only the last counts.
            headers={"X-Forwarded-For": f"10.0.0.1, {address}"},
        )

    assert (await from_("203.0.113.1")).status_code == 200
    assert (await from_("203.0.113.2")).status_code == 200
    assert (await from_("203.0.113.1")).status_code == 429


# --- the proof-of-work -----------------------------------------------------------

async def test_a_solution_pays_for_one_trial_only(app, client):
    payload = await solution(client)
    async with visitor(app, "203.0.113.7") as one, visitor(app, "198.51.100.9") as other:
        assert (await start(one, payload)).status_code == 200
        replayed = await start(other, payload)

    assert replayed.status_code == 400
    assert replayed.json()["detail"] == "Trial challenge invalid"


async def test_a_wrong_number_is_refused(client):
    challenge = (await client.get("/v2/auth/trial/challenge")).json()
    right = json.loads(base64.b64decode(solve(challenge)))
    wrong = base64.b64encode(json.dumps({**right, "number": right["number"] + 1}).encode()).decode()

    assert (await start(client, wrong)).status_code == 400


async def test_a_made_up_easy_challenge_is_refused(client):
    salt = "x?expires=9999999999"
    forged = {
        "algorithm": "SHA-256",
        "challenge": hashlib.sha256(f"{salt}0".encode()).hexdigest(),
        "number": 0,
        "salt": salt,
        "signature": "0" * 64,
    }
    payload = base64.b64encode(json.dumps(forged).encode()).decode()

    assert (await start(client, payload)).status_code == 400


async def test_garbage_is_refused_not_crashed(client):
    for payload in ["not-base64!", base64.b64encode(b"[1,2]").decode(), base64.b64encode(b"{}").decode()]:
        assert (await start(client, payload)).status_code == 400


def test_an_expired_challenge_is_refused():
    key = b"k"
    issued = pow.create_challenge(key, 10, now=1_000_000)
    for number in range(11):
        payload = base64.b64encode(
            json.dumps({**issued.model_dump(), "number": number}).encode()
        ).decode()
        assert pow.verify_solution(key, payload, now=1_000_000 + pow.CHALLENGE_TTL_SECONDS + 1) is None


# --- the daily ceiling -------------------------------------------------------------

async def test_the_daily_ceiling_holds_for_everyone(app, client, settings_with):
    settings_with(trial_daily_limit=2)

    results = []
    for n in range(3):
        async with visitor(app, f"203.0.113.{n}") as v:
            results.append(await start(v))

    assert [r.status_code for r in results] == [200, 200, 503]
    assert results[-1].json()["detail"] == "Trial budget reached"


async def test_a_refused_trial_spends_none_of_the_budget(app, client, session_maker):
    async with visitor(app, "203.0.113.7") as v:
        await start(v)
        await start(v)  # same address, refused

    async with session_maker() as s:
        issued = (await s.execute(select(func.sum(DatabaseTrialBudget.issued)))).scalar_one()
    assert issued == 1


# --- switched off ----------------------------------------------------------------------

async def test_switched_off_there_is_nothing_there(client, settings_with):
    settings_with(trial_enabled=False)

    assert (await client.get("/v2/auth/trial/challenge")).status_code == 404
    assert (await client.post("/v2/auth/trial", json={"solution": "x"})).status_code == 404


# --- privacy ---------------------------------------------------------------------------

async def test_no_address_reaches_the_logs(app, client, caplog):
    caplog.set_level(logging.DEBUG)
    async with visitor(app, "203.0.113.77") as v:
        await start(v)
        await start(v)

    assert "203.0.113.77" not in caplog.text
