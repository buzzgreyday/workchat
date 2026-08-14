"""
search_cv's contract.

The no-match case is the interesting one. It used to return every record, which
the model could not distinguish from a precise hit — so asked about something
absent it received the whole CV and inferred an answer instead of saying nothing
was recorded.
"""
import json

import pytest

from app.services import tools as tools_module
from app.services.tools import ChatToolService


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

    monkeypatch.setattr(tools_module, "INDEX_PATH", index_path)
    monkeypatch.setattr(tools_module, "RESOURCES_DIR", tmp_path)
    return ChatToolService()


async def test_search_returns_count_and_matches(cv):
    out = json.loads(await cv.search_cv(query="monolith"))
    assert out["count"] == 1
    assert out["matches"][0]["file"] == "iedi.md"


async def test_search_reads_body_not_just_summary(cv):
    """"microservices" appears only in the body — the whole point of full-text search."""
    out = json.loads(await cv.search_cv(query="microservices"))
    assert out["count"] == 1
    assert out["matches"][0]["title"] == "Software Developer @ iEDI"


async def test_no_match_reports_zero_instead_of_everything(cv):
    """The regression that mattered: a miss must not look like a hit."""
    out = json.loads(await cv.search_cv(query="terraform"))
    assert out["count"] == 0
    assert out["matches"] == []
    assert "no cv record mentions this" in out["note"].lower()


async def test_matches_are_ranked_by_how_much_of_the_query_they_carry(cv):
    """
    Unranked, every hit looked equally good: the record carrying all three words
    sat below one that merely shares a common term, and the model read the list
    as noise and answered from the wrong summary.
    """
    out = json.loads(await cv.search_cv(query="monolith microservices philosophy"))
    assert [m["file"] for m in out["matches"]] == ["iedi.md", "bio.md"]
    assert out["matches"][0]["matched_words"] == "2/3"
    assert out["matches"][1]["matched_words"] == "1/3"


async def test_common_words_do_not_decide_the_result(cv):
    """
    Matching is OR'd and substring-based, so "at" alone used to match every
    record — it is inside "integrations". One function word dragged the whole CV
    into any query containing it.
    """
    out = json.loads(await cv.search_cv(query="the monolith at work"))
    assert out["count"] == 1
    assert out["matches"][0]["file"] == "iedi.md"


async def test_query_of_only_common_words_is_a_miss_not_a_browse(cv):
    """Dropping every word of a query leaves no query — that is a miss to retry, not the whole CV."""
    out = json.loads(await cv.search_cv(query="what about that"))
    assert out["count"] == 0


async def test_unmatched_tag_also_reports_zero(cv):
    out = json.loads(await cv.search_cv(tag="kubernetes"))
    assert out["count"] == 0


async def test_tag_filter_narrows(cv):
    out = json.loads(await cv.search_cv(tag="philosophy"))
    assert out["count"] == 1
    assert out["matches"][0]["file"] == "bio.md"


async def test_empty_query_returns_everything(cv):
    """No query is a browse, not a miss — it should still hand back the corpus."""
    out = json.loads(await cv.search_cv())
    assert out["count"] == 2
