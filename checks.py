"""All programmatic, no-model-inference checks. Each returns a list of Finding."""
import re
from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path

from scanner import IndexEntry, MemoryFile

DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")


@dataclass
class Finding:
    severity: str   # "info" | "warn" | "critical"
    category: str
    message: str
    ref: str = ""   # file/line reference


def check_malformed_files(files: list[MemoryFile]) -> list[Finding]:
    out = []
    for f in files:
        if f.parse_error:
            out.append(Finding("critical", "malformed", f.parse_error, ref=str(f.path.name)))
    return out


def check_missing_frontmatter_fields(files: list[MemoryFile], rules: dict) -> list[Finding]:
    if not rules["file_health"]["require_frontmatter"]:
        return []
    out = []
    required = ["name", "description"]
    for f in files:
        if f.parse_error:
            continue
        missing = [k for k in required if k not in f.frontmatter]
        if "metadata" not in f.frontmatter or "type" not in (f.frontmatter.get("metadata") or {}):
            missing.append("metadata.type")
        if missing:
            out.append(Finding("warn", "frontmatter", f"missing fields: {', '.join(missing)}", ref=str(f.path.name)))
    return out


def check_orphans(files: list[MemoryFile], index_entries: list[IndexEntry]) -> list[Finding]:
    indexed_hrefs = {e.href for e in index_entries}
    out = []
    for f in files:
        if f.path.name not in indexed_hrefs:
            out.append(Finding("warn", "orphan", "file exists but has no MEMORY.md index entry", ref=str(f.path.name)))
    return out


def check_dead_links(memory_root: Path, index_entries: list[IndexEntry]) -> list[Finding]:
    out = []
    for e in index_entries:
        if not (memory_root / e.href).exists():
            out.append(Finding("critical", "dead_link", f"index entry '{e.title}' points to missing file '{e.href}'",
                                ref=f"MEMORY.md:{e.line_no}"))
    return out


def check_broken_wikilinks(files: list[MemoryFile]) -> list[Finding]:
    names = {f.name for f in files}
    out = []
    for f in files:
        for link in f.wikilinks:
            if link not in names:
                out.append(Finding("warn", "broken_wikilink", f"[[{link}]] does not match any memory file's name", ref=str(f.path.name)))
    return out


def check_duplicates(files: list[MemoryFile], rules: dict) -> list[Finding]:
    cfg = rules["duplicate_detection"]
    if not cfg["enabled"]:
        return []
    out = []
    n = len(files)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = files[i], files[j]
            if a.parse_error or b.parse_error:
                continue
            if not cfg["compare_across_types"] and a.mem_type != b.mem_type:
                continue
            ratio = SequenceMatcher(None, a.body, b.body).ratio()
            if ratio >= cfg["merge_threshold"]:
                out.append(Finding("warn", "duplicate", f"near-identical to '{b.path.name}' (ratio={ratio:.2f}) — merge candidate", ref=str(a.path.name)))
            elif ratio >= cfg["review_threshold"]:
                out.append(Finding("info", "duplicate", f"overlaps with '{b.path.name}' (ratio={ratio:.2f}) — review", ref=str(a.path.name)))
    return out


def check_staleness(files: list[MemoryFile], rules: dict) -> list[Finding]:
    cfg = rules["staleness"]
    if not cfg["enabled"]:
        return []
    out = []
    today = date.today()
    for f in files:
        if f.parse_error or f.mem_type not in ("project", "feedback"):
            continue
        dates_found = [date(int(y), int(m), int(d)) for y, m, d in DATE_RE.findall(f.body)]
        past_dates = [d for d in dates_found if d < today]
        if not past_dates:
            continue
        most_recent = max(past_dates)
        age_days = (today - most_recent).days
        if age_days >= cfg["probably_dead_days"]:
            out.append(Finding("warn", "stale", f"most recent date {most_recent} is {age_days}d old — probably stale/dead", ref=str(f.path.name)))
        elif age_days >= cfg["likely_stale_days"]:
            out.append(Finding("info", "stale", f"most recent date {most_recent} is {age_days}d old — verify still active", ref=str(f.path.name)))

    mtime_days = cfg["mtime_fallback_days"]
    for f in files:
        if f.parse_error:
            continue
        mtime = datetime.fromtimestamp(f.path.stat().st_mtime).date()
        age = (today - mtime).days
        if age >= mtime_days:
            out.append(Finding("info", "stale_mtime", f"not modified in {age}d (low confidence signal)", ref=str(f.path.name)))
    return out


def check_index_health(memory_root: Path, index_lines: list[str], rules: dict) -> list[Finding]:
    cfg = rules["index_health"]
    out = []
    for i, line in enumerate(index_lines, start=1):
        if len(line) > cfg["max_line_length"]:
            out.append(Finding("warn", "index_line_length", f"line is {len(line)} chars (max {cfg['max_line_length']})", ref=f"MEMORY.md:{i}"))
    n = len(index_lines)
    if n >= cfg["critical_line_count"]:
        out.append(Finding("critical", "index_size", f"MEMORY.md has {n} lines — beyond truncation threshold {cfg['critical_line_count']}", ref="MEMORY.md"))
    elif n >= cfg["warn_line_count"]:
        out.append(Finding("warn", "index_size", f"MEMORY.md has {n} lines — approaching truncation threshold {cfg['critical_line_count']}", ref="MEMORY.md"))
    return out


def check_file_length(files: list[MemoryFile], rules: dict) -> list[Finding]:
    max_lines = rules["file_health"]["max_body_lines"]
    out = []
    for f in files:
        if f.parse_error:
            continue
        if f.line_count > max_lines:
            out.append(Finding("info", "file_length", f"body is {f.line_count} lines (max {max_lines}) — consider splitting", ref=str(f.path.name)))
    return out


def run_all_checks(memory_root: Path, files: list[MemoryFile], index_entries: list[IndexEntry],
                    index_lines: list[str], rules: dict) -> list[Finding]:
    findings = []
    findings += check_malformed_files(files)
    findings += check_missing_frontmatter_fields(files, rules)
    findings += check_orphans(files, index_entries)
    findings += check_dead_links(memory_root, index_entries)
    findings += check_broken_wikilinks(files)
    findings += check_duplicates(files, rules)
    findings += check_staleness(files, rules)
    findings += check_index_health(memory_root, index_lines, rules)
    findings += check_file_length(files, rules)
    return findings
