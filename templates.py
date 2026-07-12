"""Scaffolding for a fresh memory folder and new individual memory files."""
import re
from pathlib import Path

MEMORY_RULES_REFERENCE = """# Memory Authoring Rules (reference card)

This file is a static reference for how to write memory files here. It is
NOT itself a memory entry — do not add it to MEMORY.md's index.

## Types

| Type | Captures | Save when... |
|---|---|---|
| user | Role, goals, expertise | You learn about who the user is |
| feedback | Corrections AND confirmations of approach | User corrects you, or confirms an unusual choice worked |
| project | Ongoing work/decisions not derivable from code/git | You learn who's doing what, why, by when |
| reference | Pointers to external systems | User mentions where info lives outside this project |

## File format

```markdown
---
name: kebab-case-slug          # must match filename stem
description: one-line summary  # used for relevance matching, be specific
metadata:
  type: user|feedback|project|reference
---

Body content. Link related memories with [[other-slug]].
```

For `feedback` and `project` types, structure the body as:

1. The rule or fact itself
2. `**Why:**` — the reasoning/motivation
3. `**How to apply:**` — when this should influence future behavior

## Never save

- Code patterns, architecture, file paths (derivable by reading the repo)
- Git history / who-changed-what (git log/blame is authoritative)
- Debugging fix recipes (the fix lives in the code/commit)
- Anything already documented in a CLAUDE.md
- Ephemeral in-progress task state

## MEMORY.md index

One line per memory, under ~150 chars, no frontmatter:

```
- [Title](file.md) — one-line hook
```
"""

MEMORY_INDEX_TEMPLATE = """# Memory Index

"""


def bootstrap_memory_folder(memory_root: Path) -> list[str]:
    """Create memory_root, MEMORY.md, and MEMORY_RULES.md if missing. Returns list of actions taken."""
    actions = []
    if not memory_root.exists():
        memory_root.mkdir(parents=True)
        actions.append(f"created folder {memory_root}")

    index_path = memory_root / "MEMORY.md"
    if not index_path.exists():
        index_path.write_text(MEMORY_INDEX_TEMPLATE, encoding="utf-8")
        actions.append("created MEMORY.md")

    rules_ref_path = memory_root / "MEMORY_RULES.md"
    if not rules_ref_path.exists():
        rules_ref_path.write_text(MEMORY_RULES_REFERENCE, encoding="utf-8")
        actions.append("created MEMORY_RULES.md (reference card)")

    return actions


WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug


def scaffold_memory_file(memory_root: Path, mem_type: str, slug: str, description: str) -> Path:
    if mem_type not in ("user", "feedback", "project", "reference"):
        raise ValueError(f"invalid type: {mem_type}")

    slug = slugify(slug)
    if not slug:
        raise ValueError("slug produced an empty filename after normalization — use at least one letter or digit")
    if slug in WINDOWS_RESERVED_NAMES:
        # Windows treats these as reserved device names regardless of
        # extension (CON, PRN, AUX, NUL, COM1-9, LPT1-9) — confirmed that
        # writing to e.g. "con.md" does not create a normal file at all, it
        # addresses the actual console device. Rejected unconditionally
        # (not just on win32) so a slug picked on Windows doesn't silently
        # misbehave if the repo is later cloned/used on that OS, and so
        # behavior is identical everywhere regardless of which OS is
        # running this check.
        raise ValueError(
            f"'{slug}' is a Windows-reserved device name (CON/PRN/AUX/NUL/COM1-9/LPT1-9) — "
            "choose a different slug"
        )
    path = memory_root / f"{slug}.md"
    if path.exists():
        raise FileExistsError(f"{path} already exists")

    if mem_type in ("feedback", "project"):
        body = "{{rule or fact}}\n\n**Why:** {{reasoning}}\n\n**How to apply:** {{when this applies}}\n"
    else:
        body = "{{memory content}}\n"

    content = f"""---
name: "{slug}"
description: {description}
metadata:
  type: {mem_type}
---

{body}"""
    path.write_text(content, encoding="utf-8")
    return path
