"""Find .md files that don't cleanly fit the canonical memory-file spec, so
a human can review and record a decision (registry.py) rather than the tool
silently guessing."""
from pathlib import Path

from checks import CANONICAL_TYPES
from registry import decision_map
from scanner import IGNORE_DIR_NAMES, NON_MEMORY_FILES, parse_memory_file, quick_is_memory_file


def _candidate_paths(root: Path, mode: str, patterns: list[str]) -> list[Path]:
    if mode == "full":
        paths = sorted(root.rglob("*.md"))
    else:
        seen = set()
        for pattern in patterns:
            for p in root.glob(pattern):
                if p.is_file():
                    seen.add(p.resolve())
        paths = sorted(seen)

    out = []
    for p in paths:
        if p.name in NON_MEMORY_FILES:
            continue
        rel_parts = p.relative_to(root).parts[:-1]
        if any(part in IGNORE_DIR_NAMES for part in rel_parts):
            continue
        out.append(p)
    return out


def find_review_candidates(area_name: str, root: Path, mode: str,
                            patterns: list[str]) -> list[tuple[Path, str]]:
    """Returns [(path, reason)] for files not yet decided that don't cleanly
    fit the canonical spec — either they fail the quick shape check (scoped
    areas only) or a full parse reveals malformed/non-canonical content."""
    decided = decision_map(area_name)
    out = []
    for p in _candidate_paths(root, mode, patterns):
        rel = p.relative_to(root).as_posix()
        if rel in decided:
            continue

        if mode == "scoped" and not quick_is_memory_file(p):
            out.append((p, "does not match canonical frontmatter shape (no name:/type: near top)"))
            continue

        mf = parse_memory_file(p)
        if mf.parse_error:
            out.append((p, mf.parse_error))
        elif mf.mem_type is not None and mf.mem_type not in CANONICAL_TYPES:
            out.append((p, f"metadata.type '{mf.mem_type}' is not canonical"))
    return out
