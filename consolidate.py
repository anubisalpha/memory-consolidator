"""Resolve a cross-area slug conflict by moving the chosen content into a
dedicated 'memory-diverged' area, and turning both original files into
pointer stubs referencing it there.

Why a third area instead of a direct cross-link between the two originals:
a pointer from area A straight to a file in area B breaks the moment B is
moved, renamed, or deleted — which is exactly the kind of thing that
happens to project folders over time. Centralizing the resolved content in
a folder whose only purpose is holding consolidated memories means neither
original area's lifecycle can break the reference."""
import yaml
from pathlib import Path

from scanner import MemoryFile


def write_canonical_file(diverged_root: Path, slug: str, chosen: MemoryFile, note: str) -> Path:
    """Writes the chosen content into the diverged area as the new single
    source of truth for this slug."""
    frontmatter = {
        "name": slug,
        "description": (chosen.frontmatter.get("description") or "").strip() or "consolidated memory",
        "metadata": {"type": chosen.mem_type or "project"},
    }
    fm_text = yaml.safe_dump(frontmatter, default_flow_style=False, sort_keys=False).strip()
    content = f"---\n{fm_text}\n---\n\n{chosen.body.strip()}\n\n**Consolidation note:** {note}\n"
    path = diverged_root / f"{slug}.md"
    path.write_text(content, encoding="utf-8")
    return path


def write_pointer_stub(original: MemoryFile, canonical_path: Path, diverged_area_name: str) -> None:
    """Overwrites the original file's body with a pointer to the canonical
    file, preserving its own name/description/type so it still resolves
    correctly wherever else it's referenced from (e.g. MEMORY.md index
    entries, [[wikilinks]]).

    The pointer text includes the diverged area's folder name as a prefix
    (e.g. `memory-diverged/slug.md`) rather than a bare filename, because
    check_external_pointers (checks.py) resolves this path against
    workspace_root — a bare filename would resolve to workspace_root itself
    and always report as missing."""
    frontmatter = dict(original.frontmatter)
    frontmatter["name"] = original.name  # normalize in case the raw value was YAML-coerced (see scanner.py)
    fm_text = yaml.safe_dump(frontmatter, default_flow_style=False, sort_keys=False).strip()
    body = (
        f"Pointer only; consolidated into the '{diverged_area_name}' area — "
        f"full details in `{diverged_area_name}/{canonical_path.name}`.\n"
    )
    content = f"---\n{fm_text}\n---\n\n{body}"
    original.path.write_text(content, encoding="utf-8")
