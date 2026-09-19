"""
Searching the CV.

Nothing here imports OpenAI, which is the point of the split: how the corpus is
ranked is arguable on its own terms, without a model or a tool schema involved.
"""
import json

import pytest

from app.services import search as search_module
from app.services.search import CVSearch


@pytest.fixture
def cv(tmp_path, monkeypatch):
    """A two-record corpus on disk, so full-text search has something to read."""
    (tmp_path / "iedi.md").write_text(
        "---\ntitle: Software Developer @ iEDI\n---\n"
        "The main engine is a monolith, not microservices.\n"
    )
    (tmp_path / "bio.md").write_text("---\ntitle: Bio\n---\nBackground in philosophy.\n")

    index = [
        {"file": "iedi.md", "type": "experience", "title": "Software Developer @ iEDI",
         "tags": ["monolith", "python"], "dates": "2025", "summary": "Backend work.", "skill_notes": {}},
        {"file": "bio.md", "type": "bio", "title": "Bio",
         "tags": ["philosophy"], "dates": None, "summary": "Background.", "skill_notes": {}},
    ]
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(index))

    monkeypatch.setattr(search_module, "INDEX_PATH", index_path)
    monkeypatch.setattr(search_module, "RESOURCES_DIR", tmp_path)
    return CVSearch()


async def test_search_returns_hits(cv):
    hits = await cv.search(query="monolith")
    assert [h.file for h in hits] == ["iedi.md"]


async def test_search_reads_body_not_just_summary(cv):
    """"microservices" appears only in the body — the whole point of full-text search."""
    hits = await cv.search(query="microservices")
    assert [h.title for h in hits] == ["Software Developer @ iEDI"]


async def test_no_match_returns_nothing(cv):
    """The regression that mattered: a miss must not look like a hit."""
    assert await cv.search(query="terraform") == []


async def test_hits_are_ranked_by_how_much_of_the_query_they_carry(cv):
    """
    Unranked, every hit looked equally good: the record carrying all three words
    sat below one that merely shares a common term, and the model read the list
    as noise and answered from the wrong summary.
    """
    hits = await cv.search(query="monolith microservices philosophy")
    assert [h.file for h in hits] == ["iedi.md", "bio.md"]
    assert (hits[0].matched, hits[0].of) == (2, 3)
    assert (hits[1].matched, hits[1].of) == (1, 3)
    assert not hits[0].matched_all


async def test_matched_all_marks_a_record_carrying_the_whole_query(cv):
    hits = await cv.search(query="monolith microservices")
    assert hits[0].matched_all is True


async def test_common_words_do_not_decide_the_result(cv):
    """
    Matching is OR'd and substring-based, so "at" alone used to match every
    record — it is inside "integrations". One function word dragged the whole CV
    into any query containing it.
    """
    hits = await cv.search(query="the monolith at work")
    assert [h.file for h in hits] == ["iedi.md"]


async def test_query_of_only_common_words_is_a_miss_not_a_browse(cv):
    """Dropping every word of a query leaves no query — that is a miss to retry, not the whole CV."""
    assert await cv.search(query="what about that") == []


async def test_entry_tolerates_the_wrong_filename_case(cv):
    """
    The model retypes filenames out of search results and changes their case —
    it asked for "iEDI.md". On a case-sensitive filesystem that read as "no such
    record", so it answered from the summary instead of the entry it asked for.
    """
    entry = await cv.entry("iEDI.md")
    assert entry is not None and "monolith" in entry


async def test_entry_refuses_paths_outside_resources(cv):
    assert await cv.entry("../../../etc/passwd") is None


async def test_entry_returns_none_for_a_missing_record(cv):
    """None, not prose: what a miss means is the caller's decision."""
    assert await cv.entry("nope.md") is None


async def test_unmatched_tag_returns_nothing(cv):
    assert await cv.search(tag="kubernetes") == []


async def test_tag_filter_narrows(cv):
    hits = await cv.search(tag="philosophy")
    assert [h.file for h in hits] == ["bio.md"]


async def test_empty_query_returns_everything(cv):
    """No query is a browse, not a miss — it should still hand back the corpus."""
    assert len(await cv.search()) == 2


async def test_index_is_read_once(cv, monkeypatch):
    """Cached for the life of the process: resources cannot change without a deploy."""
    await cv.search(query="monolith")
    monkeypatch.setattr(search_module, "INDEX_PATH", cv_missing := "/nonexistent/index.json")
    assert await cv.search(query="monolith"), f"a second search must not re-read {cv_missing}"
