import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

DEFAULT_RULES = {
    "duplicate_detection": {
        "enabled": True,
        "merge_threshold": 0.90,
        "review_threshold": 0.70,
        "compare_across_types": False,
    },
    "staleness": {
        "enabled": True,
        "likely_stale_days": 90,
        "probably_dead_days": 180,
        "mtime_fallback_days": 365,
    },
    "index_health": {
        "max_line_length": 150,
        "warn_line_count": 160,
        "critical_line_count": 200,
    },
    "file_health": {
        "max_body_lines": 150,
        "require_frontmatter": True,
    },
    "spec_conformance": {
        "require_why_how_for_feedback_and_project": True,
        "require_valid_type": True,
        "require_kebab_case_slug": True,
    },
    "description_quality": {
        "min_length": 15,
    },
    "code_derivable_check": {
        "enabled": False,
        "code_line_ratio_threshold": 0.5,
    },
}


@pytest.fixture
def rules():
    import copy
    return copy.deepcopy(DEFAULT_RULES)


@pytest.fixture
def memory_root(tmp_path):
    root = tmp_path / "memory"
    root.mkdir()
    return root


def write_memory_file(root: Path, filename: str, name: str, description: str,
                       mem_type: str, body: str) -> Path:
    content = f"""---
name: {name}
description: {description}
metadata:
  type: {mem_type}
---

{body}
"""
    path = root / filename
    path.write_text(content, encoding="utf-8")
    return path


def write_index(root: Path, lines: list[str]) -> Path:
    path = root / "MEMORY.md"
    path.write_text("# Memory Index\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return path
