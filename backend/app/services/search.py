"""
Searching the CV.

Nothing here knows an LLM exists. It takes strings and returns records, which is
what lets it be exercised — and its ranking argued about — without a model, a
tool schema or a vendor SDK in the process. The adapter that turns these results
into something a model can read lives in `app/services/chat/tooling.py`.
"""

import asyncio
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import aiofiles

from app.common.config import RESOURCES_DIR
from app.common.logging.logging import logger
from app.services.indexing import scan

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


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One record that matched, and how well."""

    file: str
    title: str
    type: str = ""
    tags: list[str] = field(default_factory=list)
    dates: str | None = None
    summary: str | None = None
    # How many of the query's words this record contains. None when the query
    # was empty — a tag-only browse ranks nothing.
    matched: int | None = None
    of: int | None = None

    @property
    def matched_all(self) -> bool:
        """Carries every word of the query — the record the question is about."""
        return self.matched is not None and self.matched == self.of


class CVSearch:
    """
    The CV index and the markdown behind it.

    Holds no per-conversation state, so one instance is shared across every chat.
    The corpus is scanned into memory once — at startup by `main.py`, lazily on
    first use otherwise — and kept for the life of the process.
    """

    def __init__(self) -> None:
        self._index: list[dict[str, Any]] | None = None
        self._bodies: dict[str, str] = {}

    async def load(self) -> list[dict[str, Any]]:
        """
        Scan the markdown into memory. Called at startup, and lazily if not.

        Warming the bodies in the same pass is free — the scan has already read
        each file to parse its frontmatter — and it buys two things: the first
        search of a running server touches no disk, and a record nobody can read
        surfaces at boot rather than on the one question that needed it.

        An empty corpus stops the process. That is a boot-time assertion rather
        than an invariant of this class: a server with no CV cannot answer
        anything, and failing here means the container never reports healthy, so
        a deploy that shipped a broken resources mount goes red instead of
        quietly going live. `search()` on an empty corpus is still just a miss.

        Cached for the life of the process. The corpus is read at startup, so
        editing a record on a running server needs a restart to be seen.
        """
        records, bodies = await asyncio.to_thread(scan, RESOURCES_DIR)
        if not records:
            raise RuntimeError(f"No CV records found under {RESOURCES_DIR}")
        self._index, self._bodies = records, bodies
        logger.info("Built the CV index", extra={"records": len(records)})
        return records

    async def index(self) -> list[dict[str, Any]]:
        """The corpus, scanned on first use if startup has not already done it."""
        index = self._index
        if index is None:
            index = await self.load()
        return index

    async def tags(self) -> list[str]:
        """Every tag in the corpus, for callers that need to offer a choice."""
        return sorted({t for record in await self.index() for t in record["tags"]})

    async def _body(self, file: str) -> str:
        """
        The lowercased markdown of one record, read once and kept.

        `load` fills these for the whole corpus, so this is the fallback for a
        CVSearch built by hand — a test, mostly — rather than the normal path.
        """
        if file not in self._bodies:
            async with aiofiles.open(RESOURCES_DIR / file, mode="r") as f:
                self._bodies[file] = (await f.read()).lower()
        return self._bodies[file]

    async def search(self, query: str = "", tag: str = "") -> list[SearchHit]:
        """
        Records matching a free-text query and/or a tag, best first.

        Searches the full entry text rather than the summaries, because a
        summary says what a record is about and the answer to a specific
        question is usually in the body.
        """
        logger.info("Searching the CV", extra={"query": query, "tag": tag})

        raw_query = query.strip()
        query_words = [w for w in raw_query.lower().split() if w and w not in STOPWORDS]
        tag_lower = tag.lower()

        # A query of nothing but function words is not a browse — it is a query
        # whose signal we just dropped. Report a miss so the caller searches
        # again, rather than handing back the entire CV.
        if raw_query and not query_words:
            logger.debug("Query was all stopwords", extra={"query": query})
            return []

        hits: list[SearchHit] = []
        for record in await self.index():
            if tag and tag_lower not in [t.lower() for t in record["tags"]]:
                continue

            if not query_words:
                hits.append(self._hit(record))
                continue

            haystack = " ".join(
                [
                    record["title"].lower(),
                    (record.get("summary") or "").lower(),
                    " ".join(record["tags"]).lower(),
                    await self._body(record["file"]),
                ]
            )
            matched = sum(1 for word in query_words if word in haystack)
            if matched:
                hits.append(self._hit(record, matched=matched, of=len(query_words)))

        # Best first. Unranked, every hit looked equally good: a record carrying
        # all three words of "despatch advices iEDI" was indistinguishable from
        # one that merely mentions iEDI, and the model read the list as noise.
        # Stable sort, so records matching equally keep their index order — and
        # sorting on the number itself rather than re-parsing a display string.
        hits.sort(key=lambda h: -(h.matched or 0))
        return hits

    @staticmethod
    def _hit(record: dict[str, Any], matched: int | None = None, of: int | None = None) -> SearchHit:
        return SearchHit(
            file=record["file"],
            title=record["title"],
            type=record.get("type", ""),
            tags=list(record.get("tags", [])),
            dates=record.get("dates"),
            summary=record.get("summary"),
            matched=matched,
            of=of,
        )

    async def entry(self, file: str) -> str | None:
        """
        The full markdown of one record, or None if there is no such record.

        None rather than an error string: what a missing file means is the
        caller's business, and a search service that returns prose for the model
        to read would be deciding it here.
        """
        path = RESOURCES_DIR / file
        if not path.exists():
            # A caller retypes the filename from a search result and sometimes
            # changes its case — "iEDI.md" for "iedi.md". On a case-sensitive
            # filesystem that was a dead end indistinguishable, from where a
            # model sits, from the record not existing: it fell back to the
            # summary and answered from that.
            wanted = file.strip().lower()
            path = next((p for p in RESOURCES_DIR.glob("*.md") if p.name.lower() == wanted), path)
        if not self._within_resources(path):
            logger.warning("Rejected an entry outside the resources directory", extra={"file": file})
            return None
        async with aiofiles.open(path, mode="r") as f:
            return await f.read()

    @staticmethod
    def _within_resources(path: Path) -> bool:
        """Guards the traversal `file` would otherwise allow."""
        return path.exists() and RESOURCES_DIR in path.resolve().parents


@lru_cache
def get_search() -> CVSearch:
    # Built on first call and kept — the index and bodies it caches are what
    # make sharing it worthwhile.
    return CVSearch()