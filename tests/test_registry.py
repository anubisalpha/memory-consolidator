import json

import pytest

import registry


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    """Point registry.REGISTRY_PATH at a scratch file so tests never touch
    the real review_decisions.json."""
    path = tmp_path / "review_decisions.json"
    monkeypatch.setattr(registry, "REGISTRY_PATH", path)
    return path


def test_record_and_load_decision():
    registry.record_decision("area1", "sub/file.md", "custom_format", "legacy format, approved")
    decisions = registry.load_decisions("area1")
    assert len(decisions) == 1
    assert decisions[0].rel_path == "sub/file.md"
    assert decisions[0].decision == "custom_format"


def test_record_decision_overwrites_previous():
    registry.record_decision("area1", "sub/file.md", "custom_format", "first")
    registry.record_decision("area1", "sub/file.md", "ignore", "changed my mind")
    decisions = registry.load_decisions("area1")
    assert len(decisions) == 1
    assert decisions[0].decision == "ignore"
    assert decisions[0].note == "changed my mind"


def test_record_decision_invalid_raises():
    with pytest.raises(ValueError):
        registry.record_decision("area1", "sub/file.md", "bogus", "note")


def test_decision_map_scoped_to_area():
    registry.record_decision("area1", "a.md", "ignore", "n/a")
    registry.record_decision("area2", "a.md", "custom_format", "different area, different file")
    m1 = registry.decision_map("area1")
    m2 = registry.decision_map("area2")
    assert m1["a.md"].decision == "ignore"
    assert m2["a.md"].decision == "custom_format"


def test_remove_decision():
    registry.record_decision("area1", "a.md", "ignore", "note")
    removed = registry.remove_decision("area1", "a.md")
    assert removed is True
    assert registry.load_decisions("area1") == []


def test_remove_decision_not_found():
    assert registry.remove_decision("area1", "nonexistent.md") is False


def test_registry_persists_to_disk(isolated_registry):
    registry.record_decision("area1", "a.md", "ignore", "note")
    raw = json.loads(isolated_registry.read_text(encoding="utf-8"))
    assert raw["decisions"][0]["rel_path"] == "a.md"


def test_remove_decision_matches_backslash_input(isolated_registry):
    registry.record_decision("area1", "sub/file.md", "ignore", "note")
    removed = registry.remove_decision("area1", r"sub\file.md")
    assert removed is True
    assert registry.load_decisions("area1") == []


def test_record_decision_normalizes_backslash_input(isolated_registry):
    registry.record_decision("area1", r"sub\file.md", "ignore", "note")
    decisions = registry.load_decisions("area1")
    assert decisions[0].rel_path == "sub/file.md"
