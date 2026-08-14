import json
from functools import lru_cache
from typing import Literal

import aiofiles
from openai.types.chat import ChatCompletionFunctionToolParam
from dataclasses import dataclass

from app.common.config import INDEX_PATH, RESOURCES_DIR
from app.common.logging.logging import logger


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
                        "description": "Fetch the full markdown content for one CV record given its file path from search_cv results.",
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
        query_words = [w for w in query.lower().split() if w]
        tag_lower = tag.lower()
        logger.debug("Parsed search_cv query", extra={"query_words": query_words, "tag": tag_lower})

        results = []
        for r in records:
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
            if any(word in haystack for word in query_words):
                results.append(r)

        if (query_words or tag) and not results:
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

        return json.dumps({"count": len(results), "matches": results}, indent=2)

    async def get_full_entry(self, file: str) -> str:
        """Tool available to the AI: what does this specific entry actually say?"""
        path = RESOURCES_DIR / file
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