"""
The seam between the model and the CV.

What the search finds is `test_search.py`'s business; this is about what the
model is handed and told, which is the part that steered it wrong before.
"""
import json

import pytest

from app.services import search as search_module
from app.services.chat.tooling import ChatTooling
from app.services.search import CVSearch


@pytest.fixture
def tooling(tmp_path, monkeypatch):
    (tmp_path / "iedi.md").write_text(
        "---\ntitle: iEDI\ntype: experience\ntags: [monolith]\n"
        'dates: "2025"\nsummary: Backend work.\n---\n'
        "A monolith, not microservices.\n"
    )
    (tmp_path / "bio.md").write_text(
        "---\ntitle: Bio\ntype: bio\ntags: [philosophy]\nsummary: Background.\n---\n"
        "Background in philosophy.\n"
    )
    monkeypatch.setattr(search_module, "RESOURCES_DIR", tmp_path)
    return ChatTooling(search=CVSearch())


async def test_search_renders_count_and_matches(tooling):
    out = json.loads(await tooling.run("search_cv", '{"query": "monolith"}'))
    assert out["count"] == 1
    assert out["matches"][0]["file"] == "iedi.md"


async def test_a_miss_says_so_rather_than_returning_everything(tooling):
    """
    The regression that mattered: returning the whole CV was indistinguishable
    from a precise hit, so the model inferred an answer instead of saying
    nothing was recorded.
    """
    out = json.loads(await tooling.run("search_cv", '{"query": "terraform"}'))
    assert out["count"] == 0
    assert out["matches"] == []
    assert "no cv record mentions this" in out["note"].lower()


async def test_matched_words_is_rendered_for_the_model(tooling):
    out = json.loads(await tooling.run("search_cv", '{"query": "monolith microservices philosophy"}'))
    assert out["matches"][0]["matched_words"] == "2/3"
    assert out["matches"][1]["matched_words"] == "1/3"


async def test_a_whole_query_match_is_named_in_the_note(tooling):
    """A record carrying every word is the one the question is about."""
    out = json.loads(await tooling.run("search_cv", '{"query": "monolith microservices"}'))
    assert "iedi.md" in out["note"]
    assert "get_full_entry" in out["note"]


async def test_partial_hits_are_told_apart_from_whole_ones(tooling):
    out = json.loads(await tooling.run("search_cv", '{"query": "monolith philosophy"}'))
    assert "nothing matched the whole query" in out["note"].lower()


async def test_full_entry_returns_the_markdown(tooling):
    assert "monolith" in await tooling.run("get_full_entry", '{"file": "iedi.md"}')


async def test_full_entry_reports_a_missing_record_to_the_model(tooling):
    out = await tooling.run("get_full_entry", '{"file": "nope.md"}')
    assert out.startswith("Error:")


async def test_unparseable_arguments_tell_the_model_what_to_fix(tooling):
    """
    It used to get "failed to execute" for a malformed argument, which is
    indistinguishable from the tool being broken — so it retried identically
    and burned a round.
    """
    out = await tooling.run("search_cv", "{not json")
    assert "valid JSON" in out


async def test_unknown_tool_is_named(tooling):
    assert await tooling.run("teleport", "{}") == "Unknown tool: teleport"


async def test_schemas_offer_the_corpus_tags(tooling):
    schemas = await tooling.schemas()
    names = [s["function"]["name"] for s in schemas]
    assert names == ["search_cv", "get_full_entry"]
    tags = schemas[0]["function"]["parameters"]["properties"]["tag"]["enum"]
    assert tags == ["monolith", "philosophy"]
