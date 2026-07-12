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


NON_MEMORY_FILES = {"MEMORY.md", "MEMORY_RULES.md"}


def scan_memory_files(memory_root: Path) -> list[MemoryFile]:
    """Recursive: picks up *.md nested in subfolders of memory_root, not just the top level."""
    files = []
    for p in sorted(memory_root.rglob("*.md")):
        if p.name in NON_MEMORY_FILES:
            continue
        files.append(parse_memory_file(p))
    return files


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
