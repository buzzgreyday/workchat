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
         "tags": ["philosophy"], "dates": None, "summary": "Who he is.", "skill_notes": {}},
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
