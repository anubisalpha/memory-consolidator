"""Workspace-wide discovery of memory-like files living outside memory_root."""
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATTERNS = [
    "**/MEMORY.md",
    "**/CLAUDE_MEMORY.md",
    "**/*_memory.md",
    "**/memory/**/*.md",
]

IGNORE_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv", "venv"}


@dataclass
class DiscoveredFile:
    path: Path
    matched_pattern: str


def discover_external_memory_files(workspace_root: Path, memory_root: Path,
                                    patterns: list[str] | None = None) -> list[DiscoveredFile]:
    """Find memory-shaped files under workspace_root that are NOT already
    inside memory_root — i.e. the scattered project-level memory files
    (like projects/X/CLAUDE_MEMORY.md) that scan_memory_files() never sees."""
    patterns = patterns or DEFAULT_PATTERNS
    memory_root = memory_root.resolve()
    seen: dict[Path, str] = {}

    for pattern in patterns:
        for p in workspace_root.glob(pattern):
            if not p.is_file():
                continue
            if any(part in IGNORE_DIR_NAMES for part in p.parts):
                continue
            resolved = p.resolve()
            try:
                resolved.relative_to(memory_root)
                continue  # inside memory_root already, not "external"
            except ValueError:
                pass
            if resolved not in seen:
                seen[resolved] = pattern

    return sorted(
        (DiscoveredFile(path=path, matched_pattern=pattern) for path, pattern in seen.items()),
        key=lambda d: str(d.path),
    )
