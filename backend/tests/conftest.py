"""
Shared fixtures.

Note what is *not* here any more: an env-setup block above the imports, and a
`# noqa: E402` on every import below it. Nothing in `app` reads the environment
at import now — `get_settings()` is called on first use and `create_app()` is
called by `app/main.py` rather than by the factory module — so these imports are
in the ordinary place and the environment is arranged underneath them.
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.common.config import get_settings
from app.common.db import Base, get_db, get_session_factory, transaction
from app.factory import create_app
from app.openai.client import get_openai_client
from app.services.auth import get_auth
from app.services.search import get_search

_TEST_RESOURCES = Path(tempfile.mkdtemp(prefix="cv-test-"))
(_TEST_RESOURCES / "system-prompt.md").write_text("test system prompt")
# One real record rather than an empty corpus. ChatTooling.schemas() builds the
# tag enum from the index and every chat turn calls it, so a corpus with nothing
# in it would 500 each of those tests for a reason that has nothing to do with
# what they assert.
(_TEST_RESOURCES / "iedi.md").write_text(
    "---\n"
    "title: Software Developer @ iEDI\n"
    "type: experience\n"
    "tags: [python]\n"
    'dates: "2025"\n'
    "summary: Backend work.\n"
    "---\n"
    "The main engine is a monolith.\n"
)

os.environ["SYSTEM_PROMPT_PATH"] = str(_TEST_RESOURCES / "system-prompt.md")
os.environ["RESOURCES_DIR"] = str(_TEST_RESOURCES)
# setdefault so a caller can override via a real env, but tests default to sane values.
os.environ.setdefault("DEV_MODE", "1")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("TOKEN_HASHING_SECRET", "test-hashing-secret")
os.environ.setdefault("ADMIN_KEY", "test-admin-key")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")

# Everything the application caches for the life of a process. The suite is one
# process, so a value built against an earlier test's environment would outlive
# it; clearing here is what keeps the settings above authoritative.
for _cache in (get_settings, get_auth, get_search, get_openai_client, get_session_factory):
    _cache.cache_clear()


@pytest.fixture(scope="session")
def app():
    """The application under test.

    A fixture rather than a module global, which is not fussiness: pytest
    imports this file as `conftest`, and a test module writing
    `from tests.conftest import app` imports it *again* as `tests.conftest` —
    two module objects, two `create_app()` calls, two apps. An override
    registered on one would then be invisible to a client driving the other,
    which is exactly as confusing to debug as it sounds. Requesting a fixture
    can only ever yield the one pytest built.
    """
    return create_app()


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_maker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def db_session(session_maker):
    async with session_maker() as session:
        yield session


def stream_of(*tokens: str):
    """
    An OpenAI streaming response carrying these tokens then stopping.

    A fresh generator per call: `create` is awaited once per tool round and a
    generator is consumed once, so a shared one would come back empty on the
    second round.
    """
    async def chunks():
        for token in tokens:
            delta = MagicMock(content=token, tool_calls=None)
            yield MagicMock(choices=[MagicMock(delta=delta, finish_reason=None)])
        delta = MagicMock(content=None, tool_calls=None)
        yield MagicMock(choices=[MagicMock(delta=delta, finish_reason="stop")])

    return chunks()


@pytest.fixture
def openai_mock():
    """Default: one plain assistant reply, streamed, no tool calls."""
    mock = MagicMock()
    mock.chat.completions.create = AsyncMock(
        side_effect=lambda **kwargs: stream_of("hi ", "from ", "mock")
    )
    return mock


@pytest.fixture
async def client(app, session_maker, openai_mock):
    # Bound to the test engine, but through the same `transaction` helper the
    # real get_db uses — so a request here commits and rolls back exactly as it
    # does in production, rather than testing a looser definition of one.
    async def _get_db():
        async with transaction(session_maker) as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    # The transcript recorders open their own sessions from the factory rather
    # than reusing the request's, so the factory needs overriding too — without
    # this they silently swallow a connection error to the real database and
    # every persistence assertion fails for the wrong reason.
    app.dependency_overrides[get_session_factory] = lambda: session_maker
    app.dependency_overrides[get_openai_client] = lambda: openai_mock
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def issued_token(client):
    """A working access token minted via the real /admin/issue-token flow."""
    resp = await client.post(
        "/admin/issue-token",
        headers={"X-Admin-Key": os.environ["ADMIN_KEY"]},
        json={"subject": "test-hire", "company": "Acme", "max_queries": 5},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]

# --- chat streaming helpers ----------------------------------------------
#
# The chat surface is SSE-only. These keep the `data: ` parsing in one place
# rather than in the four tests that used to hand-roll it, and give tests back
# the shape they previously got from the JSON endpoint.

def sse_frames(response) -> list[dict]:
    """Every frame in a completed stream, decoded."""
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def done_frame(response) -> dict:
    """The terminal frame, which carries reply/history/usage/conversation_id."""
    return next(f for f in sse_frames(response) if f["type"] == "done")


async def ask(client, token: str, **body):
    """POST one question to the only chat endpoint."""
    return await client.post(
        "/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "hi", **body},
    )
