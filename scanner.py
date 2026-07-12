"""Walk the memory root and parse frontmatter + body from each .md file."""
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([a-zA-Z0-9_\-]+)\]\]")
INDEX_LINE_RE = re.compile(r"^-\s+\[([^\]]+)\]\(([^)]+)\)")


@dataclass
class MemoryFile:
    path: Path
    frontmatter: dict = field(default_factory=dict)
    body: str = ""
    raw: str = ""
    parse_error: str | None = None

    @property
    def name(self) -> str:
        return self.frontmatter.get("name", self.path.stem)

    @property
    def mem_type(self) -> str | None:
        return (self.frontmatter.get("metadata") or {}).get("type")

    @property
    def wikilinks(self) -> list[str]:
        return WIKILINK_RE.findall(self.body)

    @property
    def line_count(self) -> int:
        return len(self.body.splitlines())


@dataclass
class IndexEntry:
    title: str
    href: str
    line: str
    line_no: int


def parse_memory_file(path: Path) -> MemoryFile:
    raw = path.read_text(encoding="utf-8", errors="replace")
    match = FRONTMATTER_RE.match(raw)
    if not match:
        return MemoryFile(path=path, raw=raw, body=raw, parse_error="missing/malformed frontmatter")
    fm_text, body = match.groups()
    try:
        frontmatter = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        return MemoryFile(path=path, raw=raw, body=body, parse_error=f"invalid YAML: {e}")
    return MemoryFile(path=path, frontmatter=frontmatter, body=body.strip(), raw=raw)


FRONTMATTER_PROBE_BYTES = 1024
QUICK_FRONTMATTER_START_RE = re.compile(r"^---\r?\n")
QUICK_NAME_RE = re.compile(r"^name:\s*\S+", re.MULTILINE)
QUICK_TYPE_RE = re.compile(r"^\s*type:\s*\S+", re.MULTILINE)


def quick_is_memory_file(path: Path) -> bool:
    """Cheap prefilter: peek at the first ~1KB instead of reading+parsing the
    whole file. Used for 'scoped' area scans where most path-matched files
    (e.g. a README that happens to sit in a folder named 'memory') are NOT
    actually memory files, so a full read/YAML-parse per candidate would be
    wasted work at scale. A real memory file has a '---' frontmatter block
    near the top containing both 'name:' and 'metadata: { type: ... }' —
    checking for those substrings needs no YAML parsing at all."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(FRONTMATTER_PROBE_BYTES)
    except OSError:
        return False
    if not QUICK_FRONTMATTER_START_RE.match(head):
        return False
    if "\n---" not in head[3:]:
        return False  # frontmatter block doesn't close within the probe window
    return bool(QUICK_NAME_RE.search(head)) and bool(QUICK_TYPE_RE.search(head))


NON_MEMORY_FILES = {"MEMORY.md", "MEMORY_RULES.md"}
IGNORE_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv", "venv", "backups", "reports"}


def scan_memory_files(memory_root: Path) -> list[MemoryFile]:
    """Recursive: picks up *.md nested in subfolders of memory_root, not just the top level."""
    files = []
    for p in sorted(memory_root.rglob("*.md")):
        if p.name in NON_MEMORY_FILES:
            continue
        if any(part in IGNORE_DIR_NAMES for part in p.relative_to(memory_root).parts[:-1]):
            continue
        files.append(parse_memory_file(p))
    return files


def scan_memory_files_scoped(root: Path, patterns: list[str]) -> list[MemoryFile]:
    """For 'scoped' areas (a whole project/workspace, not a dedicated memory
    folder): path patterns alone (e.g. '**/memory/**/*.md') are too broad —
    they also match things like a plugin's README.md that just happens to
    live under a folder named "memory". quick_is_memory_file() prefilters on
    a cheap byte-range peek before paying for a full parse, and files that
    fail the peek are silently skipped rather than reported as "malformed"
    (they were never real memory candidates in the first place)."""
    seen: dict[Path, MemoryFile] = {}
    for pattern in patterns:
        for p in root.glob(pattern):
            if not p.is_file() or p.name in NON_MEMORY_FILES:
                continue
            if any(part in IGNORE_DIR_NAMES for part in p.relative_to(root).parts[:-1]):
                continue
            resolved = p.resolve()
            if resolved in seen:
                continue
            if not quick_is_memory_file(p):
                continue
            seen[resolved] = parse_memory_file(p)
    return sorted(seen.values(), key=lambda f: str(f.path))


def parse_index(memory_root: Path) -> tuple[list[IndexEntry], list[str]]:
    """Parse MEMORY.md into structured entries + raw lines (for length checks etc.)."""
    index_path = memory_root / "MEMORY.md"
    entries = []
    lines = []
    if not index_path.exists():
        return entries, lines
    lines = index_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines, start=1):
        m = INDEX_LINE_RE.match(line)
        if m:
            entries.append(IndexEntry(title=m.group(1), href=m.group(2), line=line, line_no=i))
    return entries, lines
