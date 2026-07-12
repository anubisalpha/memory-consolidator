import pytest

import registry
from reviewer import find_review_candidates

from .conftest import write_memory_file


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    path = tmp_path / "review_decisions.json"
    monkeypatch.setattr(registry, "REGISTRY_PATH", path)
    return path


def test_full_mode_flags_malformed_file(memory_root):
    (memory_root / "bad.md").write_text("no frontmatter at all", encoding="utf-8")
    candidates = find_review_candidates("area1", memory_root, "full", [])
    assert len(candidates) == 1
    assert candidates[0][0].name == "bad.md"


def test_full_mode_flags_invalid_type(memory_root):
    write_memory_file(memory_root, "a.md", "a", "a valid description here", "credentials", "body")
    candidates = find_review_candidates("area1", memory_root, "full", [])
    assert len(candidates) == 1
    assert "credentials" in candidates[0][1]


def test_full_mode_skips_canonical_files(memory_root):
    write_memory_file(memory_root, "a.md", "a", "a valid description here", "user", "body")
    candidates = find_review_candidates("area1", memory_root, "full", [])
    assert candidates == []


def test_scoped_mode_flags_non_frontmatter_matches(tmp_path):
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    (mem_dir / "README.md").write_text("# no frontmatter\n", encoding="utf-8")
    candidates = find_review_candidates("area1", tmp_path, "scoped", ["**/memory/**/*.md"])
    assert len(candidates) == 1
    assert candidates[0][0].name == "README.md"


def test_already_decided_files_excluded(memory_root):
    (memory_root / "bad.md").write_text("no frontmatter at all", encoding="utf-8")
    registry.record_decision("area1", "bad.md", "ignore", "not a memory file")
    candidates = find_review_candidates("area1", memory_root, "full", [])
    assert candidates == []
