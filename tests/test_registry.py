import json

import pytest

import registry


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    """Point registry.REGISTRY_PATH at a scratch file so tests never touch
    the real review_decisions.json."""
    path = tmp_path / "review_decisions.json"
    monkeypatch.setattr(registry, "REGISTRY_PATH", path)
    finding_path = tmp_path / "finding_review_decisions.json"
    monkeypatch.setattr(registry, "FINDING_REGISTRY_PATH", finding_path)
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


# ---- FindingDecision (near-duplicate / staleness review) ----

def test_record_and_load_finding_decision():
    registry.record_finding_decision("area1", "a.md::b.md", "duplicate", "dismissed", "not actually a duplicate")
    decisions = registry.load_finding_decisions("area1")
    assert len(decisions) == 1
    assert decisions[0].key == "a.md::b.md"
    assert decisions[0].category == "duplicate"
    assert decisions[0].decision == "dismissed"


def test_record_finding_decision_invalid_decision_raises():
    with pytest.raises(ValueError):
        registry.record_finding_decision("area1", "a.md", "stale", "bogus", "note")


def test_record_finding_decision_invalid_category_raises():
    with pytest.raises(ValueError):
        registry.record_finding_decision("area1", "a.md", "bogus_category", "dismissed", "note")


def test_finding_decision_map_scoped_to_area_and_category():
    registry.record_finding_decision("area1", "a.md", "stale", "dismissed", "still active")
    registry.record_finding_decision("area1", "a.md::b.md", "duplicate", "dismissed", "not a dup")
    registry.record_finding_decision("area2", "a.md", "stale", "dismissed", "different area")

    stale_map = registry.finding_decision_map("area1", "stale")
    dup_map = registry.finding_decision_map("area1", "duplicate")
    assert set(stale_map) == {"a.md"}
    assert set(dup_map) == {"a.md::b.md"}
    assert set(registry.finding_decision_map("area2", "stale")) == {"a.md"}


def test_record_finding_decision_overwrites_previous():
    registry.record_finding_decision("area1", "a.md", "stale", "dismissed", "first")
    registry.record_finding_decision("area1", "a.md", "stale", "dismissed", "second")
    decisions = registry.load_finding_decisions("area1", "stale")
    assert len(decisions) == 1
    assert decisions[0].note == "second"


def test_remove_finding_decision():
    registry.record_finding_decision("area1", "a.md", "stale", "dismissed", "note")
    removed = registry.remove_finding_decision("area1", "a.md", "stale")
    assert removed is True
    assert registry.load_finding_decisions("area1") == []


def test_remove_finding_decision_not_found():
    assert registry.remove_finding_decision("area1", "nonexistent.md", "stale") is False


def test_finding_registry_persists_to_disk(isolated_registry):
    registry.record_finding_decision("area1", "a.md", "stale", "dismissed", "note")
    finding_path = isolated_registry.parent / "finding_review_decisions.json"
    raw = json.loads(finding_path.read_text(encoding="utf-8"))
    assert raw["decisions"][0]["key"] == "a.md"


def test_finding_decisions_isolated_from_regular_decisions(isolated_registry):
    registry.record_decision("area1", "a.md", "ignore", "note")
    registry.record_finding_decision("area1", "a.md", "stale", "dismissed", "note")
    assert len(registry.load_decisions("area1")) == 1
    assert len(registry.load_finding_decisions("area1")) == 1
