"""
Searching the CV.

Nothing here imports OpenAI, which is the point of the split: how the corpus is
ranked is arguable on its own terms, without a model or a tool schema involved.
"""
from pathlib import Path

import pytest

from app.services import search as search_module
from app.services.search import CVSearch


@pytest.fixture
def cv(tmp_path, monkeypatch):
    """A two-record corpus on disk. The metadata is frontmatter now rather than
    a separate index.json, because that is where the records come from."""
    (tmp_path / "iedi.md").write_text(
        "---\n"
        "title: Software Developer @ iEDI\n"
        "type: experience\n"
        "tags: [monolith, python]\n"
        # Quoted, or PyYAML hands back an int and the record fails validation —
        # which the scanner would skip rather than raise, losing it silently.
        'dates: "2025"\n'
        "summary: Backend work.\n"
        "---\n"
        "The main engine is a monolith, not microservices.\n"
    )
    (tmp_path / "bio.md").write_text(
        "---\ntitle: Bio\ntype: bio\ntags: [philosophy]\nsummary: Background.\n---\n"
        "Background in philosophy.\n"
    )

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


async def test_the_corpus_is_scanned_once(cv, monkeypatch):
    """Cached for the life of the process: the corpus is read at startup, and a
    change to it needs a restart to be seen."""
    await cv.search(query="monolith")
    monkeypatch.setattr(search_module, "RESOURCES_DIR", gone := Path("/nonexistent"))
    assert await cv.search(query="monolith"), f"a second search must not re-read {gone}"


async def test_frontmatter_is_searchable(cv):
    """The body cached for matching is the whole file, frontmatter included.

    Summaries, tags and skill_notes are part of what a question matches on —
    iedi.md's scope notes for helm and rancher live nowhere else — so warming
    from the parsed content instead would quietly change the ranking.

    "backend" appears only in iedi.md's summary line, never in its body.
    """
    assert [h.file for h in await cv.search(query="backend")] == ["iedi.md"]


async def test_a_record_that_will_not_parse_is_skipped(tmp_path, monkeypatch):
    """One bad file must not cost the rest of the corpus."""
    (tmp_path / "good.md").write_text("---\ntitle: Good\ntype: bio\n---\nFine.\n")
    (tmp_path / "broken.md").write_text("---\ntitle: [unclosed\n---\nBroken.\n")
    monkeypatch.setattr(search_module, "RESOURCES_DIR", tmp_path)

    hits = await CVSearch().search()
    assert [h.file for h in hits] == ["good.md"]


async def test_an_empty_corpus_refuses_to_load(tmp_path, monkeypatch):
    """A server with no CV cannot answer anything, so it does not start."""
    monkeypatch.setattr(search_module, "RESOURCES_DIR", tmp_path)
    with pytest.raises(RuntimeError):
        await CVSearch().load()


async def test_load_warms_every_body(tmp_path, monkeypatch):
    """After load, a search touches no disk — proven by removing the corpus."""
    (tmp_path / "iedi.md").write_text(
        "---\ntitle: iEDI\ntype: experience\ntags: [python]\n---\nA monolith.\n"
    )
    monkeypatch.setattr(search_module, "RESOURCES_DIR", tmp_path)
    cv = CVSearch()
    await cv.load()

    (tmp_path / "iedi.md").unlink()
    assert [h.file for h in await cv.search(query="monolith")] == ["iedi.md"]
