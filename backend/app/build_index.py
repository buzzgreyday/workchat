"""
Scans /data for .md files, parses YAML frontmatter, and writes index.json.
Run this whenever you add/edit a CV file: `python -m app.build_index` (from backend/)
"""
import json
import re
import frontmatter  # pip install python-frontmatter --break-system-packages
from collections import defaultdict

from app.common.config import INDEX_PATH, RESOURCES_DIR
from app.common.models import Record

SKILLS_PATH = RESOURCES_DIR / "skills.md"

# How much each source type contributes to a skill's ranking.
# Experience counts more than side/hobby projects.
TYPE_WEIGHT = {"experience": 3, "project": 1}

START_MARKER = "<!-- AUTO-GENERATED-SKILLS-START: do not hand-edit below this line, run `python -m app.build_index` (from backend/) instead -->"
END_MARKER = "<!-- AUTO-GENERATED-SKILLS-END -->"


def build_index():
    records = []
    for md_file in RESOURCES_DIR.rglob("*.md"):
        if md_file != RESOURCES_DIR / "system-prompt.md":
            post = frontmatter.load(md_file)
            rel_path = str(md_file.relative_to(RESOURCES_DIR))
            record = Record(
                file=rel_path,
                type=post.get("type", "unknown"),
                title=post.get("title", md_file.stem),
                tags=post.get("tags", []),
                dates=post.get("dates"),
                summary=post.get("summary"),
                skill_notes=post.get("skill_notes", {}),
            )
            records.append(record.model_dump())

    INDEX_PATH.write_text(json.dumps(records, indent=2))
    print(f"Indexed {len(records)} files -> {INDEX_PATH}")

    update_skills_section(records)


def update_skills_section(records):
    """Aggregate tags from experience/project records into a ranked skill
    list, weighting experience higher than projects, and splice it into
    skills.md between the auto-generated markers."""
    scores = defaultdict(int)
    sources = defaultdict(set)
    notes = {}  # tag -> note (first non-empty one found wins; keep it simple)

    for r in records:
        weight = TYPE_WEIGHT.get(r["type"])
        if weight is None:
            continue  # skip bio/contact/education/skills.md itself, etc.
        for tag in r["tags"]:
            scores[tag] += weight
            sources[tag].add(r["title"])
        for tag, note in (r.get("skill_notes") or {}).items():
            if tag not in notes and note:
                notes[tag] = note

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    lines = ["## Technical Skills", ""]
    for tag, _score in ranked:
        src_list = ", ".join(sorted(sources[tag]))
        lines.append(f"- **{tag}** — {src_list}")
        if tag in notes:
            lines.append(f"  - Scope: {notes[tag]}")
    generated_block = "\n".join(lines)

    if not SKILLS_PATH.exists():
        print("skills.md not found, skipping auto-skills update")
        return

    content = SKILLS_PATH.read_text()
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
        re.DOTALL,
    )
    replacement = f"{START_MARKER}\n\n{generated_block}\n\n{END_MARKER}"

    if pattern.search(content):
        content = pattern.sub(replacement, content)
        SKILLS_PATH.write_text(content)
        print(f"Updated auto-generated skills section in {SKILLS_PATH}")
    else:
        print("Markers not found in skills.md, skipping auto-skills update")


if __name__ == "__main__":
    build_index()