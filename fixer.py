"""Safe auto-fixes for 'full' mode areas, applied only under
automation.mode: apply_safe_fixes / full_auto, and only after a snapshot
(see main.py's cmd_audit). 'Safe' here means additive-or-strictly-corrective:
these functions only add missing lines or remove lines that are already
broken — they never rewrite or reinterpret existing valid content, and they
never touch individual memory files' bodies, only MEMORY.md itself."""
from pathlib import Path

from scanner import IndexEntry, MemoryFile


def add_missing_index_entries(area_root: Path, files: list[MemoryFile],
                               index_entries: list[IndexEntry]) -> list[str]:
    """Appends one line per orphan file (a real memory file with no MEMORY.md
    entry) to the index. Only ever appends — never rewrites existing lines."""
    indexed_hrefs = {e.href for e in index_entries}
    orphans = []
    for f in files:
        if f.parse_error:
            continue  # can't build a sensible index line from a malformed file
        rel = f.path.relative_to(area_root).as_posix()
        if rel in indexed_hrefs or f.path.name in indexed_hrefs:
            continue
        orphans.append((rel, f))

    if not orphans:
        return []

    index_path = area_root / "MEMORY.md"
    if not index_path.exists():
        index_path.write_text("# Memory Index\n\n", encoding="utf-8")

    actions = []
    with index_path.open("a", encoding="utf-8") as fh:
        for rel, f in orphans:
            title = f.name.replace("-", " ").replace("_", " ").strip().title() or f.path.stem
            desc = (f.frontmatter.get("description") or "").strip() or "no description"
            fh.write(f"- [{title}]({rel}) — {desc}\n")
            actions.append(f"added index entry for {rel}")
    return actions


def remove_dead_index_links(area_root: Path, index_entries: list[IndexEntry],
                             index_lines: list[str]) -> list[str]:
    """Removes MEMORY.md lines whose href doesn't exist on disk. Only ever
    removes lines that are already broken/unusable — every other line is
    left byte-for-byte untouched."""
    dead_line_nos = {e.line_no for e in index_entries if not (area_root / e.href).exists()}
    if not dead_line_nos:
        return []

    kept_lines = [line for i, line in enumerate(index_lines, start=1) if i not in dead_line_nos]
    index_path = area_root / "MEMORY.md"
    index_path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")
    return [f"removed dead index line {i} (href no longer exists)" for i in sorted(dead_line_nos)]
