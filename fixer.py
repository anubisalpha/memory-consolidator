"""Safe auto-fixes for 'full' mode areas, applied only under
automation.mode: apply_safe_fixes / full_auto, and only after a snapshot
(see main.py's cmd_audit). 'Safe' here means additive-or-strictly-corrective:
apply_safe_fixes-tier functions only add missing lines or remove lines that
are already broken — they never rewrite or reinterpret existing valid
content, and they never touch individual memory files' bodies, only
MEMORY.md itself.

full_auto-tier functions (mark_stale_files, merge_exact_duplicates) are a
deliberate exception to that "never touch file bodies" rule, gated to
full_auto only and each behind its own opt-in flag. Both are still
content-preserving: mark_stale_files only prepends a visible marker (never
removes text), and merge_exact_duplicates only acts on byte-identical
bodies (so nothing distinguishable is lost by pointing one at the other) —
see each function's docstring for the specific safety argument."""
import yaml
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

from checks import DATE_RE
from scanner import IndexEntry, MemoryFile, is_pointer_stub


DEFAULT_INDEX_HEADER = "# Memory Index\n\n"
STALE_MARKER_PREFIX = "> ⚠ **Possibly stale**"


def add_missing_index_entries(area_root: Path, files: list[MemoryFile],
                               index_entries: list[IndexEntry],
                               index_header: str | None = None) -> list[str]:
    """Appends one line per orphan file (a real memory file with no MEMORY.md
    entry) to the index. Only ever appends — never rewrites existing lines.

    index_header is only used when MEMORY.md doesn't exist yet (an existing
    index's header is never touched, appends-only applies there too). Comes
    from the area's `index_header` in rules.md — e.g. a consolidation
    staging area can carry an explanatory note ("not part of Claude's
    auto-loaded memory system") baked in from the very first write, rather
    than relying on someone remembering to add it by hand."""
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
        header = index_header if index_header is not None else DEFAULT_INDEX_HEADER
        if not header.endswith("\n"):
            header += "\n"
        index_path.write_text(header, encoding="utf-8")
    elif index_path.stat().st_size > 0:
        existing = index_path.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            # Appending in "a" mode is a raw byte append — without this, a
            # file saved without a trailing newline would get the new entry
            # concatenated onto the end of the last existing line, silently
            # merging two index entries into one broken line.
            with index_path.open("a", encoding="utf-8") as fh:
                fh.write("\n")

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


def _rewrite_body(f: MemoryFile, new_body: str) -> None:
    """Rewrites a memory file's body while preserving its frontmatter,
    normalizing `name` in case the raw value was YAML-coerced (see
    scanner.py's MemoryFile.name and consolidate.py's write_pointer_stub,
    which does the same normalization)."""
    frontmatter = dict(f.frontmatter)
    frontmatter["name"] = f.name
    fm_text = yaml.safe_dump(frontmatter, default_flow_style=False, sort_keys=False).strip()
    f.path.write_text(f"---\n{fm_text}\n---\n\n{new_body}", encoding="utf-8")


def mark_stale_files(files: list[MemoryFile], rules: dict) -> list[str]:
    """full_auto only. Prepends a visible staleness marker to files flagged
    by the same date-based signal as checks.check_staleness's 'stale'
    category (NOT the low-confidence 'stale_mtime' mtime fallback — that
    signal is too weak to act on automatically). Idempotent: a file that
    already carries the marker is skipped, so re-running doesn't stack
    markers or reset the flagged-on date. Content-preserving: the marker is
    a single prepended line, nothing is removed."""
    cfg = rules["staleness"]
    if not cfg["enabled"]:
        return []
    out = []
    today = date.today()
    for f in files:
        if f.parse_error or f.mem_type not in ("project", "feedback"):
            continue
        if f.body.lstrip().startswith(STALE_MARKER_PREFIX):
            continue
        past_dates = []
        for y, m, d in DATE_RE.findall(f.body):
            try:
                past_dates.append(date(int(y), int(m), int(d)))
            except ValueError:
                continue  # e.g. a version string like 2026-13-40 — not a real date
        past_dates = [d for d in past_dates if d < today]
        if not past_dates:
            continue
        most_recent = max(past_dates)
        age_days = (today - most_recent).days
        if age_days < cfg["likely_stale_days"]:
            continue
        marker = (f"{STALE_MARKER_PREFIX} — flagged {today.isoformat()} "
                  f"(most recent date found: {most_recent}, {age_days}d old). Verify still accurate.\n\n")
        _rewrite_body(f, marker + f.body)
        out.append(f"marked stale: {f.path.name} (most recent date {most_recent}, {age_days}d old)")
    return out


def merge_exact_duplicates(files: list[MemoryFile], rules: dict) -> list[str]:
    """full_auto only. For pairs of files with byte-identical bodies (after
    stripping) and the same metadata.type, rewrites the alphabetically-later
    file into a pointer stub referencing the earlier one as canonical.
    Restricted to exact matches only (ratio == 1.0, not the near-duplicate
    thresholds checks.check_duplicates reports) — anything short of that is
    a judgment call about which version is canonical, which this tool
    deliberately leaves to a human (see resolve-conflicts for the
    cross-area equivalent). Pointer stubs are already excluded from
    duplicate detection (scanner.is_pointer_stub), so this can't cascade
    into re-flagging its own output on the next run."""
    cfg = rules["duplicate_detection"]
    if not cfg["enabled"]:
        return []
    min_body_len = cfg.get("min_body_length_for_comparison", 20)
    candidates = [f for f in files if not f.parse_error and not is_pointer_stub(f.body)
                  and len(f.body.strip()) >= min_body_len]
    candidates.sort(key=lambda f: f.path.name)

    out = []
    merged: set[str] = set()
    n = len(candidates)
    for i in range(n):
        a = candidates[i]
        if a.path.name in merged:
            continue
        for j in range(i + 1, n):
            b = candidates[j]
            if b.path.name in merged:
                continue
            if a.mem_type != b.mem_type:
                continue
            if a.body.strip() != b.body.strip():
                continue
            ratio = SequenceMatcher(None, a.body, b.body).ratio()
            if ratio < 1.0:
                continue  # defensive: strip()-equal strings always give 1.0, but don't assume it
            stub_body = (
                f"Pointer only; exact duplicate of `{a.path.name}` — see that file for full "
                f"content (merged by full_auto's duplicate check on {date.today().isoformat()}).\n"
            )
            _rewrite_body(b, stub_body)
            merged.add(b.path.name)
            out.append(f"merged exact duplicate: {b.path.name} -> {a.path.name}")
    return out
