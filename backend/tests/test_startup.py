"""
What happens before the socket is bound.

No HTTP-level test reaches this: `conftest` drives the app through
`httpx.ASGITransport`, which has no lifespan support at all, so the index those
tests use is built lazily on first search. The startup contract therefore needs
testing here or nowhere.
"""
from unittest.mock import AsyncMock

import pytest

from app.main import app, lifespan
from app.services import search as search_module
from app.services.search import get_search


@pytest.fixture(autouse=True)
def fresh_search(monkeypatch):
    """`get_search` is lru_cached, so an index built against a tmp_path corpus
    would otherwise leak into every test that ran afterwards."""
    get_search.cache_clear()
    # The shutdown half closes a process-wide AsyncOpenAI client. Left real, a
    # test that runs the lifespan to completion would hand the next one a
    # closed client.
    monkeypatch.setattr("app.main.get_openai_client", lambda: AsyncMock())
    yield
    get_search.cache_clear()


async def test_startup_refuses_an_empty_corpus(tmp_path, monkeypatch):
    """The point of building at startup: a server with no CV never reaches the
    port. The container then fails its healthcheck and the deploy goes red,
    rather than the site going live answering nothing."""
    monkeypatch.setattr(search_module, "RESOURCES_DIR", tmp_path)

    with pytest.raises(RuntimeError, match="No CV records"):
        async with lifespan(app):
            pass


async def test_startup_builds_the_index(tmp_path, monkeypatch):
    """The ordinary case: the corpus is in memory before the first request, so
    nothing has to read it during one."""
    (tmp_path / "iedi.md").write_text(
        "---\ntitle: iEDI\ntype: experience\ntags: [python]\n---\nA monolith.\n"
    )
    monkeypatch.setattr(search_module, "RESOURCES_DIR", tmp_path)

    async with lifespan(app):
        hits = await get_search().search(query="monolith")

    assert [h.file for h in hits] == ["iedi.md"]