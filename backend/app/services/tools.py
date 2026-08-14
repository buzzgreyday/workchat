import json
from functools import lru_cache
from typing import Literal

import aiofiles
from openai.types.chat import ChatCompletionFunctionToolParam
from dataclasses import dataclass

from app.common.config import INDEX_PATH, RESOURCES_DIR
from app.common.logging.logging import logger

# Matching is OR'd and substring-based, so a single function word decides the
# whole result: "at" alone matches every record in the CV, because it sits inside
# "integrations", "database" and "creating". Filtering by an explicit list rather
# than by length, since go, ci, ai, qa and js are short and meaningful.
STOPWORDS = frozenset(
    """a about all also an and any are as at be been but by can did do does doing done
    for from had has have he her him his how i if in into is it its me more most much my
    no not of on or our she so some that the their them then there these they this those
    to too us was we were what when where which who whom whose why will with would you
    your ever""".split()
)


@dataclass
class ToolCallFunction:
    name: str
    arguments: str


@dataclass
class ToolCall:
    id: str
    function: ToolCallFunction

class ChatToolService:
    """
    Singleton: owns the CV index and tool-schema cache, both of which are
    identical across every chat and safe to share/reuse. Holds no
    per-conversation state.
    """

    def __init__(self):
        self._tools_cache: list[ChatCompletionFunctionToolParam] | None = None

    async def _load_index(self) -> list[dict]:
        """Read the index file containing markdown references."""
        async with aiofiles.open(INDEX_PATH, mode="r") as f:
            index_ = await f.read()
        logger.debug(f"Loaded {INDEX_PATH} for markdown references", extra={"index": index_})
        return json.loads(index_)

    async def get_tools(self) -> list[ChatCompletionFunctionToolParam]:
        """
        Builds the AI tools schema. Cached once for the lifetime of this
        service — shared across all chats, since the index only changes on
        deploy, not per-request.
        """
        if self._tools_cache is None:
            index = await self._load_index()
            all_tags = sorted({t for r in index for t in r["tags"]})
            self._tools_cache = [
                {
                    "type": "function",
                    "function": {
                        "name": "search_cv",
                        "description": (
                            "Search CV records by free-text query and/or tag. Searches full entry content, "
                            "not just title/summary. Returns {count, matches}, where each match is a "
                            "lightweight summary (file, title, tags, dates, summary), not full content — "
                            "call get_full_entry for the detail behind a promising summary. "
                            "Matches are ordered best first, and 'matched_words' says how many of the "
                            "query's words that record contains: trust a 3/3 far more than a 1/3, which "
                            "is often just a common word. Very common words are ignored in the query. "
                            "A count of 0 means nothing in the CV mentions it: say so rather than inferring."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Free-text search over the full entry content"},
                                "tag": {"type": "string", "description": "Filter by a specific tag", "enum": all_tags},
                            },
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_full_entry",
                        "description": (
                            "Fetch the full markdown content for one CV record given its file path from "
                            "search_cv results. Call it whenever a record matched every word of the query, "
                            "and whenever the question asks for depth rather than existence — 'tell me more', "
                            "'go into detail', 'why', 'elaborate', or any specific fact about a record. "
                            "Search results carry a summary of what each record is about, which is not the "
                            "same as what it says."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {"file": {"type": "string"}},
                            "required": ["file"],
                        },
                    },
                },
            ]
        return self._tools_cache

    async def search_cv(self, query: str = "", tag: str = "") -> str:
        """Tool available to the AI: which markdown entries are relevant?"""
        logger.info("AI called tool to search for relevant markdowns", extra={"query": query, "tag": tag})

        records = await self._load_index()
        raw_query = query.strip()
        query_words = [w for w in raw_query.lower().split() if w and w not in STOPWORDS]
        tag_lower = tag.lower()
        # A query of nothing but function words is not a browse — it is a query
        # whose signal we just dropped. Skip the loop so it reports a miss and the
        # model searches again, rather than handing back the entire CV.
        degenerate = bool(raw_query) and not query_words
        logger.debug("Parsed search_cv query", extra={"query_words": query_words, "tag": tag_lower})

        results = []
        strong: list[str] = []
        for r in records:
            if degenerate:
                break
            if tag and tag_lower not in [t.lower() for t in r["tags"]]:
                continue
            if not query_words:
                results.append(r)
                continue

            async with aiofiles.open(RESOURCES_DIR / r["file"], mode="r") as f:
                full_text = (await f.read()).lower()

            haystack = " ".join(
                [r["title"].lower(), (r.get("summary") or "").lower(), " ".join(r["tags"]).lower(), full_text]
            )
            matched = sum(1 for word in query_words if word in haystack)
            if matched:
                results.append({**r, "matched_words": f"{matched}/{len(query_words)}"})
                if matched == len(query_words):
                    strong.append(r["file"])

        # Best first. Unranked, every hit looked equally good: a record carrying
        # all three words of "despatch advices iEDI" was indistinguishable from
        # one that merely mentions iEDI, and the model read the list as noise.
        # Stable sort, so records matching equally keep their index order.
        results.sort(key=lambda r: -int(str(r.get("matched_words", "0/1")).split("/")[0]))

        if (raw_query or tag) and not results:
            # Previously this returned every record, which is indistinguishable
            # from a precise hit: the model got the whole CV, assumed the search
            # had worked, and inferred an answer rather than saying nothing was
            # recorded. Report the miss instead.
            logger.info(
                "search_cv found no matching records",
                extra={"query": query, "tag": tag},
            )
            return json.dumps(
                {
                    "count": 0,
                    "matches": [],
                    "note": (
                        "No CV record mentions this. Say so plainly rather than "
                        "inferring an answer — but you may search again with "
                        "different wording if the term has a common synonym."
                    ),
                },
                indent=2,
            )

        # The score is only worth computing if it changes what happens next. A
        # record carrying every word of the query is the one the question is
        # about, and answering from its summary — which describes the record, not
        # the question — is where the wrong answers came from.
        if strong:
            note = (
                f"Contains every word of this query: {', '.join(strong)}. "
                "Call get_full_entry on these before answering. A summary says "
                "what a record is about; the answer to a specific question is in "
                "the entry."
            )
        else:
            note = (
                "Nothing matched the whole query — these are partial hits, best "
                "first. Open the top ones with get_full_entry rather than "
                "concluding anything from a summary."
            )
        note += (
            " If the question asks for depth — 'tell us more', 'go into detail', "
            "'why', 'elaborate' — a summary cannot answer it at all: fetch the "
            "entry and answer from what it actually says."
        )

        return json.dumps({"count": len(results), "matches": results, "note": note}, indent=2)

    async def get_full_entry(self, file: str) -> str:
        """Tool available to the AI: what does this specific entry actually say?"""
        path = RESOURCES_DIR / file
        if not path.exists():
            # The model retypes the filename from the search result and sometimes
            # changes its case — "iEDI.md" for "iedi.md". On a case-sensitive
            # filesystem that was a dead end indistinguishable, from where the
            # model sits, from the record not existing: it fell back to the
            # summary and answered from that. Only names inside the resources
            # directory are considered, so the traversal guard below still holds.
            wanted = file.strip().lower()
            path = next((p for p in RESOURCES_DIR.glob("*.md") if p.name.lower() == wanted), path)
        if not path.exists() or RESOURCES_DIR not in path.resolve().parents:
            return f"Error: no such file '{file}'"
        async with aiofiles.open(path, mode="r") as f:
            return await f.read()

    async def run_tool(self, name: str, tool_input: dict) -> str:
        """We currently only have two tools for the AI to call."""
        if name == "search_cv":
            return await self.search_cv(**tool_input)
        if name == "get_full_entry":
            return await self.get_full_entry(**tool_input)
        return f"Unknown tool: {name}"


@lru_cache
def get_chat_tool() -> ChatToolService:
    # Created once at import time — this is the actual singleton.
    return ChatToolService()