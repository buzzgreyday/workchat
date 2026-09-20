"""
Where the CV corpus comes from.

Reading the markdown is separate from ranking it: `search.py` is about which
record answers a question, and this is about what the records are. The skills
CLI needs the second without the first.

There is no build step and no artifact. The whole corpus is twenty files and
about 46 KB of markdown with no embeddings and no API calls behind it, so
scanning it costs milliseconds — which is why it happens in the process that
serves it rather than in a script someone has to remember to run.
"""

from pathlib import Path
from typing import Any

import frontmatter

from app.common.logging.logging import logger
from app.common.models import Record

# Not a record: it is the instruction given to the model, loaded separately by
# config.py, and indexing it would offer the hirer the prompt as a CV entry.
SYSTEM_PROMPT_NAME = "system-prompt.md"


def scan(resources_dir: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """
    Every record in the corpus, and the text behind each one.

    Takes the directory rather than importing it, so the caller's own
    `RESOURCES_DIR` is what decides — which is what lets a test point one
    consumer at a fixture corpus without moving the module underneath it.

    The bodies are the **whole file**, lowercased, frontmatter included. That is
    not incidental: the summaries, tags and skill_notes are part of what search
    matches on, and iedi.md's scope notes for helm and rancher exist nowhere
    else. Warming these from `post.content` would quietly change what the corpus
    matches and invalidate every ranking measurement taken against it.

    A file that will not parse is skipped rather than fatal. One record with a
    stray colon in its frontmatter should not cost the other nineteen — but the
    name goes in the log, and `CVSearch.load` refuses to start on an empty
    corpus, so a directory that fails wholesale is still loud.

    Order is `rglob`'s and deliberately not sorted: ranking ties break on record
    order, and the skills aggregation takes the first non-empty note it finds.
    Sorting would be defensible on its own, but it is a change to both of those
    and belongs in its own commit.
    """
    records: list[dict[str, Any]] = []
    bodies: dict[str, str] = {}

    for md_file in resources_dir.rglob("*.md"):
        if md_file.name == SYSTEM_PROMPT_NAME:
            continue
        rel_path = str(md_file.relative_to(resources_dir))
        try:
            # Read once: the same text yields the frontmatter and the haystack.
            # Explicit encoding because Path.read_text() would otherwise follow
            # the locale, while frontmatter.load() assumes utf-8 — a difference
            # that only shows up on someone else's machine.
            text = md_file.read_text(encoding="utf-8")
            post = frontmatter.loads(text)
            # model_validate rather than Record(...): frontmatter's `get` is
            # typed as returning `object`, which cannot be passed to a typed
            # field without mypy objecting. Validation is the point anyway —
            # it is what turns a malformed record into a skip.
            record = Record.model_validate(
                {
                    "file": rel_path,
                    "type": post.get("type", "unknown"),
                    "title": post.get("title", md_file.stem),
                    "tags": post.get("tags", []),
                    "dates": post.get("dates"),
                    "summary": post.get("summary"),
                    "skill_notes": post.get("skill_notes", {}),
                }
            )
        except Exception:
            logger.exception("Skipped a CV record that would not parse", extra={"file": rel_path})
            continue

        records.append(record.model_dump())
        bodies[rel_path] = text.lower()

    return records, bodies