"""
Shared pytest fixtures.

Test env vars are set at module load, *before* the app is imported, so
config.py picks up the fixture SYSTEM_PROMPT / INDEX paths and doesn't
demand real values for the mandatory ones.
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# --- env setup: must happen before any `from app import ...` below ---
_TEST_RESOURCES = Path(tempfile.mkdtemp(prefix="cv-test-"))
(_TEST_RESOURCES / "system-prompt.md").write_text("test system prompt")
(_TEST_RESOURCES / "index.json").write_text(json.dumps([]))

os.environ["SYSTEM_PROMPT_PATH"] = str(_TEST_RESOURCES / "system-prompt.md")
os.environ["INDEX_PATH"] = str(_TEST_RESOURCES / "index.json")
# setdefault so a caller can override via a real env, but tests default to sane values.
os.environ.setdefault("DEV_MODE", "1")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("TOKEN_HASHING_SECRET", "test-hashing-secret")
os.environ.setdefault("ADMIN_KEY", "test-admin-key")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")

import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.common.db import Base, get_db, get_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.openai.client import get_openai_client  # noqa: E402


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


@pytest.fixture
def openai_mock():
    """Default: one plain assistant reply, no tool calls."""
    mock = MagicMock()
    message = MagicMock()
    message.content = "hi from mock"
    message.tool_calls = None
    message.model_dump = MagicMock(return_value={"role": "assistant", "content": "hi from mock"})
    choice = MagicMock(finish_reason="stop", message=message)
    completion = MagicMock(choices=[choice])
    mock.chat.completions.create = AsyncMock(return_value=completion)
    return mock


@pytest.fixture
async def client(session_maker, openai_mock):
    async def _get_db():
        async with session_maker() as s:
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