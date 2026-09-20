"""
Regenerates the skills list inside resources/skills.md.

Run it after editing any CV record: `python -m app.build_skills` (from backend/).
skills.md is tracked, so the output is committed like any other source — the
server never runs this and never writes to resources/.

It used to also write resources/index.json, which the backend read at startup.
That file is gone: the corpus is scanned in the process that serves it, so there
is nothing to build and nothing to forget to build.
"""
import re
from collections import defaultdict

from app.common.config import get_settings
from app.services.indexing import scan

# How much each source type contributes to a skill's ranking.
# Experience counts more than side/hobby projects.
TYPE_WEIGHT = {"experience": 3, "project": 1}

START_MARKER = "<!-- AUTO-GENERATED-SKILLS-START: do not hand-edit below this line, run `python -m app.build_skills` (from backend/) instead -->"
END_MARKER = "<!-- AUTO-GENERATED-SKILLS-END -->"

# Matched loosely on purpose. The previous pattern was re.escape(START_MARKER),
# so renaming the module changed the constant, the constant stopped matching the
# text already in skills.md, and the splice became a silent no-op that printed
# "Markers not found" and exited zero. Only the marker names have to agree now,
# not the sentence around them.
BLOCK = re.compile(
    r"<!-- AUTO-GENERATED-SKILLS-START.*?-->.*?<!-- AUTO-GENERATED-SKILLS-END -->",
    re.DOTALL,
)


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

    # Score descending, then tag name, so equal-scoring tags keep a stable
    # order. Without the tiebreak the order falls back to rglob() insertion
    # order, i.e. filesystem order, and regenerating on another machine
    # reshuffles skills.md for no reason.
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0].lower()))

    lines = ["## Technical Skills", ""]
    for tag, _score in ranked:
        src_list = ", ".join(sorted(sources[tag]))
        lines.append(f"- **{tag}** — {src_list}")
        if tag in notes:
            lines.append(f"  - Scope: {notes[tag]}")
    generated_block = "\n".join(lines)

    skills_path = get_settings().resources_dir / "skills.md"
    if not skills_path.exists():
        print("skills.md not found, skipping auto-skills update")
        return

    content = skills_path.read_text()
    replacement = f"{START_MARKER}\n\n{generated_block}\n\n{END_MARKER}"

    if BLOCK.search(content):
        skills_path.write_text(BLOCK.sub(replacement, content))
        print(f"Updated auto-generated skills section in {skills_path}")
    else:
        print("Markers not found in skills.md, skipping auto-skills update")


if __name__ == "__main__":
    resources_dir = get_settings().resources_dir
    records, _bodies = scan(resources_dir)
    print(f"Scanned {len(records)} records from {resources_dir}")
    update_skills_section(records)