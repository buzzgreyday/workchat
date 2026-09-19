"""
The seam between the model and the CV.

Everything OpenAI-shaped about tools lives here: the schemas, the JSON strings a
`role: "tool"` message has to carry, the dataclasses the streaming parser
assembles, and the prose that steers the model. That prose is not schema — it is
prompt engineering — and it belongs beside the adapter rather than inside the
search service, which should be arguable about on its own terms.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai.types.chat import ChatCompletionFunctionToolParam

from app.common.logging.logging import logger
from app.services.search import CVSearch, SearchHit, get_search


@dataclass(frozen=True, slots=True)
class ToolCallFunction:
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class ToolCall:
    """
    One tool call, assembled from streaming deltas.

    `id` and `name` are optional because a provider sends them across chunks and
    may never complete one. They were typed `str` while being seeded `None`,
    which is how a `tool_call_id: None` could reach the next request.
    """

    id: str | None
    function: ToolCallFunction

    @property
    def is_runnable(self) -> bool:
        return bool(self.id) and bool(self.function.name)


class ChatTooling:
    """What the model may call, and what it gets back."""

    def __init__(self, search: CVSearch) -> None:
        self.search = search
        self._schemas: list[ChatCompletionFunctionToolParam] | None = None

    async def schemas(self) -> list[ChatCompletionFunctionToolParam]:
        """
        The tool definitions, built once.

        Cached for the life of the service: the tag enum comes from the index,
        which only changes on deploy.
        """
        if self._schemas is None:
            all_tags = await self.search.tags()
            self._schemas = [
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
        return self._schemas

    async def run(self, name: str, arguments: str) -> str:
        """
        Run one tool and render its result as the string a tool message carries.

        Never raises: whatever goes wrong, the model gets text it can read and
        act on, because the alternative is a turn that dies on a malformed
        argument the model could have corrected.
        """
        try:
            parsed = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            logger.warning("Model sent unparseable tool arguments", extra={"tool": name})
            return f"Error: the arguments for '{name}' were not valid JSON. Send them again as a JSON object."

        if not isinstance(parsed, dict):
            return f"Error: the arguments for '{name}' must be a JSON object."

        try:
            if name == "search_cv":
                return self._render_search(
                    await self.search.search(
                        query=str(parsed.get("query", "")),
                        tag=str(parsed.get("tag", "")),
                    )
                )
            if name == "get_full_entry":
                entry = await self.search.entry(str(parsed.get("file", "")))
                return entry if entry is not None else f"Error: no such file '{parsed.get('file', '')}'"
        except Exception:
            logger.exception("Tool failed", extra={"tool": name})
            return f"Tool '{name}' failed to execute."

        return f"Unknown tool: {name}"

    @staticmethod
    def _render_search(hits: list[SearchHit]) -> str:
        """
        Search results as the model reads them.

        The `note` is the load-bearing part. A record carrying every word of the
        query is the one the question is about, and answering from its summary —
        which describes the record, not the question — is where the wrong
        answers came from.
        """
        if not hits:
            # Returning every record was indistinguishable from a precise hit:
            # the model got the whole CV, assumed the search had worked, and
            # inferred an answer rather than saying nothing was recorded.
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

        matches: list[dict[str, Any]] = []
        for hit in hits:
            match: dict[str, Any] = {
                "file": hit.file,
                "type": hit.type,
                "title": hit.title,
                "tags": hit.tags,
                "dates": hit.dates,
                "summary": hit.summary,
            }
            if hit.matched is not None:
                match["matched_words"] = f"{hit.matched}/{hit.of}"
            matches.append(match)

        strong = [hit.file for hit in hits if hit.matched_all]
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

        return json.dumps({"count": len(matches), "matches": matches, "note": note}, indent=2)


@lru_cache
def get_tooling() -> ChatTooling:
    """
    Built on first call and kept, like the search it wraps — the schemas it
    caches are identical across every chat.
    """
    return ChatTooling(search=get_search())
