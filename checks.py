"""All programmatic, no-model-inference checks. Each returns a list of Finding."""
import re
from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path

from scanner import IndexEntry, MemoryFile

DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CANONICAL_TYPES = {"user", "feedback", "project", "reference"}
WHY_RE = re.compile(r"\*\*Why:\*\*", re.IGNORECASE)
HOW_RE = re.compile(r"\*\*How to apply:\*\*", re.IGNORECASE)


def _ref(path: Path) -> str:
    """Parent-folder/filename, so files with the same basename in different
    subfolders (common when auditing a whole area) aren't indistinguishable."""
    parts = path.parts
    return "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]


@dataclass
class Finding:
    severity: str   # "info" | "warn" | "critical"
    category: str
    message: str
    ref: str = ""   # file/line reference


def check_malformed_files(files: list[MemoryFile]) -> list[Finding]:
    out = []
    for f in files:
        if f.review_decision == "custom_format":
            continue  # user has already reviewed and approved this file's shape
        if f.parse_error:
            out.append(Finding("critical", "malformed", f.parse_error, ref=_ref(f.path)))
    return out


def check_missing_frontmatter_fields(files: list[MemoryFile], rules: dict) -> list[Finding]:
    if not rules["file_health"]["require_frontmatter"]:
        return []
    out = []
    required = ["name", "description"]
    for f in files:
        if f.parse_error or f.review_decision == "custom_format":
            continue
        missing = [k for k in required if k not in f.frontmatter]
        if "metadata" not in f.frontmatter or "type" not in (f.frontmatter.get("metadata") or {}):
            missing.append("metadata.type")
        if missing:
            out.append(Finding("warn", "frontmatter", f"missing fields: {', '.join(missing)}", ref=_ref(f.path)))
    return out


def check_orphans(memory_root: Path, files: list[MemoryFile], index_entries: list[IndexEntry]) -> list[Finding]:
    indexed_hrefs = {e.href for e in index_entries}
    out = []
    for f in files:
        rel = f.path.relative_to(memory_root).as_posix()
        if rel not in indexed_hrefs and f.path.name not in indexed_hrefs:
            out.append(Finding("warn", "orphan", "file exists but has no MEMORY.md index entry", ref=rel))
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
                out.append(Finding("warn", "broken_wikilink", f"[[{link}]] does not match any memory file's name", ref=_ref(f.path)))
    return out


def check_slug_hygiene(files: list[MemoryFile], rules: dict) -> list[Finding]:
    if not rules.get("spec_conformance", {}).get("require_kebab_case_slug", True):
        return []
    out = []
    for f in files:
        if f.parse_error or f.review_decision == "custom_format":
            continue
        name = f.frontmatter.get("name")
        if not name:
            continue
        if not KEBAB_RE.match(name):
            out.append(Finding("warn", "slug_hygiene", f"name '{name}' is not kebab-case", ref=_ref(f.path)))
        if name != f.path.stem:
            out.append(Finding("warn", "slug_hygiene", f"name '{name}' does not match filename stem '{f.path.stem}'", ref=_ref(f.path)))
    return out


def check_valid_type(files: list[MemoryFile], rules: dict) -> list[Finding]:
    if not rules.get("spec_conformance", {}).get("require_valid_type", True):
        return []
    out = []
    for f in files:
        if f.parse_error or f.review_decision == "custom_format":
            continue
        mem_type = f.mem_type
        if mem_type is None:
            continue  # already caught by check_missing_frontmatter_fields
        if mem_type not in CANONICAL_TYPES:
            out.append(Finding("warn", "invalid_type",
                                f"metadata.type '{mem_type}' is not one of {sorted(CANONICAL_TYPES)}",
                                ref=_ref(f.path)))
    return out


def check_why_how_structure(files: list[MemoryFile], rules: dict) -> list[Finding]:
    """feedback/project memories are spec'd to lead with the rule/fact, then
    explicit **Why:** and **How to apply:** lines."""
    if not rules.get("spec_conformance", {}).get("require_why_how_for_feedback_and_project", True):
        return []
    out = []
    for f in files:
        if f.parse_error or f.mem_type not in ("feedback", "project"):
            continue
        missing = []
        if not WHY_RE.search(f.body):
            missing.append("**Why:**")
        if not HOW_RE.search(f.body):
            missing.append("**How to apply:**")
        if missing:
            out.append(Finding("info", "why_how_structure",
                                f"missing {' and '.join(missing)} section(s) required for type '{f.mem_type}'",
                                ref=_ref(f.path)))
    return out


def check_description_quality(files: list[MemoryFile], rules: dict) -> list[Finding]:
    min_len = rules.get("description_quality", {}).get("min_length", 15)
    out = []
    for f in files:
        if f.parse_error:
            continue
        desc = f.frontmatter.get("description", "")
        if not desc:
            continue  # caught by check_missing_frontmatter_fields
        if len(desc) < min_len:
            out.append(Finding("info", "description_quality", f"description is only {len(desc)} chars — likely too generic", ref=_ref(f.path)))
        if desc.strip().lower() == f.name.strip().lower().replace("-", " "):
            out.append(Finding("info", "description_quality", "description is just a restatement of the name", ref=_ref(f.path)))
    return out


def check_code_derivable(files: list[MemoryFile], rules: dict) -> list[Finding]:
    """Heuristic, low-confidence: flag project/user memories that look like they
    mostly restate things derivable from the codebase (paths, code blocks) rather
    than genuinely non-derivable context — per the 'don't save what git/code
    already shows' exclusion rule."""
    cfg = rules.get("code_derivable_check", {})
    if not cfg.get("enabled", False):
        return []
    threshold = cfg.get("code_line_ratio_threshold", 0.5)
    out = []
    code_block_re = re.compile(r"```.*?```", re.DOTALL)
    path_line_re = re.compile(r"^[\w./\\-]+\.\w{1,5}$")
    for f in files:
        if f.parse_error or f.mem_type not in ("project", "user"):
            continue
        body_no_code = code_block_re.sub("", f.body)
        lines = [l for l in body_no_code.splitlines() if l.strip()]
        if not lines:
            continue
        path_like = sum(1 for l in lines if path_line_re.match(l.strip()))
        code_chars = len(f.body) - len(body_no_code)
        ratio = (path_like / len(lines)) + (code_chars / max(len(f.body), 1))
        if ratio >= threshold:
            out.append(Finding("info", "code_derivable",
                                "body is dominated by file paths/code blocks — verify this isn't derivable from reading the repo",
                                ref=_ref(f.path)))
    return out


def check_duplicates(files: list[MemoryFile], rules: dict) -> list[Finding]:
    cfg = rules["duplicate_detection"]
    if not cfg["enabled"]:
        return []
    out = []
    n = len(files)
    max_pairwise = cfg.get("max_files_for_pairwise", 800)
    if n > max_pairwise:
        return [Finding("info", "duplicate_check_skipped",
                         f"skipped: {n} files exceeds max_files_for_pairwise ({max_pairwise}) — "
                         "pairwise comparison would be too slow for an area-wide scan",
                         ref="")]
    for i in range(n):
        for j in range(i + 1, n):
            a, b = files[i], files[j]
            if a.parse_error or b.parse_error:
                continue
            if not cfg["compare_across_types"] and a.mem_type != b.mem_type:
                continue
            ratio = SequenceMatcher(None, a.body, b.body).ratio()
            if ratio >= cfg["merge_threshold"]:
                out.append(Finding("warn", "duplicate", f"near-identical to '{b.path.name}' (ratio={ratio:.2f}) — merge candidate", ref=_ref(a.path)))
            elif ratio >= cfg["review_threshold"]:
                out.append(Finding("info", "duplicate", f"overlaps with '{b.path.name}' (ratio={ratio:.2f}) — review", ref=_ref(a.path)))
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
        dates_found = []
        for y, m, d in DATE_RE.findall(f.body):
            try:
                dates_found.append(date(int(y), int(m), int(d)))
            except ValueError:
                continue  # matches \d{4}-\d{2}-\d{2} but isn't a real calendar date
                          # (e.g. a version string like 2026-13-40) — not our concern here
        past_dates = [d for d in dates_found if d < today]
        if not past_dates:
            continue
        most_recent = max(past_dates)
        age_days = (today - most_recent).days
        if age_days >= cfg["probably_dead_days"]:
            out.append(Finding("warn", "stale", f"most recent date {most_recent} is {age_days}d old — probably stale/dead", ref=_ref(f.path)))
        elif age_days >= cfg["likely_stale_days"]:
            out.append(Finding("info", "stale", f"most recent date {most_recent} is {age_days}d old — verify still active", ref=_ref(f.path)))

    mtime_days = cfg["mtime_fallback_days"]
    for f in files:
        if f.parse_error:
            continue
        mtime = datetime.fromtimestamp(f.path.stat().st_mtime).date()
        age = (today - mtime).days
        if age >= mtime_days:
            out.append(Finding("info", "stale_mtime", f"not modified in {age}d (low confidence signal)", ref=_ref(f.path)))
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
            out.append(Finding("info", "file_length", f"body is {f.line_count} lines (max {max_lines}) — consider splitting", ref=_ref(f.path)))
    return out


POINTER_CONTEXT_RE = re.compile(
    r"(?:pointer only|full details? (?:is |are )?in|see `)[^`\n]*`([^`]+\.(?:md|txt|json|yaml|yml))`",
    re.IGNORECASE,
)


def check_external_pointers(files: list[MemoryFile], rules: dict) -> list[Finding]:
    """Some memories are deliberately 'pointer only' — e.g. description says
    'full details in `projects/X/CLAUDE_MEMORY.md`'. That target lives outside
    memory_root, so the normal dead-link check can't see it. This resolves
    any backtick-quoted path in frontmatter/body against workspace_root and
    flags ones that don't exist."""
    cfg = rules.get("external_scan", {})
    if not cfg.get("enabled", False):
        return []
    workspace_root = cfg.get("workspace_root")
    if not workspace_root:
        return []
    workspace_root = Path(workspace_root)
    if not workspace_root.exists():
        return [Finding("warn", "external_pointer",
                         f"configured workspace_root does not exist: {workspace_root}", ref="rules.md")]

    out = []
    for f in files:
        if f.parse_error:
            continue
        text = f"{f.frontmatter.get('description', '')}\n{f.body}"
        for candidate in POINTER_CONTEXT_RE.findall(text):
            resolved = (workspace_root / candidate)
            if not resolved.exists():
                out.append(Finding("critical", "external_pointer",
                                    f"references '{candidate}' which does not exist under {workspace_root}",
                                    ref=_ref(f.path)))
    return out


def check_duplicate_slugs(files: list[MemoryFile]) -> list[Finding]:
    """Cross-machine drift detector: same name slug, different content — the
    kind of conflict that shows up when memory/ is synced between computers."""
    out = []
    by_name: dict[str, list[MemoryFile]] = {}
    for f in files:
        if f.parse_error:
            continue
        by_name.setdefault(f.name, []).append(f)
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        bodies = {g.body for g in group}
        if len(bodies) > 1:
            paths = ", ".join(g.path.name for g in group)
            out.append(Finding("critical", "duplicate_slug",
                                f"name '{name}' used by multiple files with differing content: {paths}",
                                ref=name))
    return out


def compliance_score(findings: list["Finding"], total_files: int) -> float:
    """Rough 0-100 conformance score: penalize by severity, floor at 0."""
    if total_files == 0:
        return 100.0
    weight = {"critical": 10, "warn": 4, "info": 1}
    penalty = sum(weight.get(f.severity, 1) for f in findings)
    return max(0.0, 100.0 - (penalty / total_files) * 5)


def run_all_checks(memory_root: Path, files: list[MemoryFile], index_entries: list[IndexEntry],
                    index_lines: list[str], rules: dict, mode: str = "full") -> list[Finding]:
    """mode='scoped' areas have no single MEMORY.md index to speak of (they're
    a whole project/workspace, not a dedicated memory folder), so index-shaped
    checks (orphans, dead links, index size) don't apply there."""
    findings = []
    findings += check_malformed_files(files)
    findings += check_missing_frontmatter_fields(files, rules)
    if mode == "full":
        findings += check_orphans(memory_root, files, index_entries)
        findings += check_dead_links(memory_root, index_entries)
        findings += check_index_health(memory_root, index_lines, rules)
    findings += check_broken_wikilinks(files)
    findings += check_slug_hygiene(files, rules)
    findings += check_valid_type(files, rules)
    findings += check_why_how_structure(files, rules)
    findings += check_description_quality(files, rules)
    findings += check_code_derivable(files, rules)
    findings += check_external_pointers(files, rules)
    findings += check_duplicate_slugs(files)
    findings += check_duplicates(files, rules)
    findings += check_staleness(files, rules)
    findings += check_file_length(files, rules)
    return findings
