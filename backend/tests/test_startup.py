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
from app.services.search import CVSearch, get_search


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """Point the lifespan's composition at a fixture corpus.

    `get_search` is the composition root for search, and the lifespan calls it
    rather than taking it as an argument — a lifespan has no `Depends` and so
    no `dependency_overrides`. Swapping the provider is the seam that leaves.

    The client is patched for the same reason: shutdown closes a process-wide
    AsyncOpenAI, which left real would hand the next test a closed one.
    """
    def _corpus(**records: str) -> CVSearch:
        for name, text in records.items():
            (tmp_path / f"{name}.md").write_text(text)
        search = CVSearch(resources_dir=tmp_path)
        monkeypatch.setattr("app.main.get_search", lambda: search)
        return search

    get_search.cache_clear()
    monkeypatch.setattr("app.main.get_openai_client", lambda: AsyncMock())
    yield _corpus
    get_search.cache_clear()


async def test_startup_refuses_an_empty_corpus(corpus):
    """The point of building at startup: a server with no CV never reaches the
    port. The container then fails its healthcheck and the deploy goes red,
    rather than the site going live answering nothing."""
    corpus()

    with pytest.raises(RuntimeError, match="No CV records"):
        async with lifespan(app):
            pass


async def test_startup_builds_the_index(corpus):
    """The ordinary case: the corpus is in memory before the first request, so
    nothing has to read it during one."""
    search = corpus(iedi="---\ntitle: iEDI\ntype: experience\ntags: [python]\n---\nA monolith.\n")

    async with lifespan(app):
        hits = await search.search(query="monolith")

    assert [h.file for h in hits] == ["iedi.md"]