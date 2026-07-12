import pytest

from backup import create_snapshot, list_snapshots, rollback


@pytest.fixture
def backup_dir(tmp_path):
    d = tmp_path / "backups"
    d.mkdir()
    return d


def test_create_snapshot_captures_files(memory_root, backup_dir):
    (memory_root / "a.md").write_text("content a", encoding="utf-8")
    (memory_root / "b.md").write_text("content b", encoding="utf-8")

    zip_path = create_snapshot(memory_root, backup_dir, reason="test")
    assert zip_path.exists()

    snapshots = list_snapshots(backup_dir)
    assert len(snapshots) == 1
    assert snapshots[0]["reason"] == "test"
    assert snapshots[0]["zip"] == zip_path.name


def test_create_snapshot_appends_manifest(memory_root, backup_dir):
    (memory_root / "a.md").write_text("v1", encoding="utf-8")
    create_snapshot(memory_root, backup_dir, reason="first")
    (memory_root / "a.md").write_text("v2", encoding="utf-8")
    create_snapshot(memory_root, backup_dir, reason="second")

    snapshots = list_snapshots(backup_dir)
    assert len(snapshots) == 2
    assert [s["reason"] for s in snapshots] == ["first", "second"]


def test_rollback_restores_content(memory_root, backup_dir):
    (memory_root / "a.md").write_text("original", encoding="utf-8")
    create_snapshot(memory_root, backup_dir, reason="before change")

    (memory_root / "a.md").write_text("mutated", encoding="utf-8")
    (memory_root / "b.md").write_text("new file added after snapshot", encoding="utf-8")

    rollback(memory_root, backup_dir, which="latest", force=True)

    assert (memory_root / "a.md").read_text(encoding="utf-8") == "original"
    assert not (memory_root / "b.md").exists()


def test_rollback_by_specific_timestamp(memory_root, backup_dir):
    (memory_root / "a.md").write_text("v1", encoding="utf-8")
    create_snapshot(memory_root, backup_dir, reason="v1")
    first_ts = list_snapshots(backup_dir)[0]["timestamp"]

    (memory_root / "a.md").write_text("v2", encoding="utf-8")
    create_snapshot(memory_root, backup_dir, reason="v2")

    rollback(memory_root, backup_dir, which=first_ts, force=True)
    assert (memory_root / "a.md").read_text(encoding="utf-8") == "v1"


def test_rollback_no_snapshots_raises(memory_root, backup_dir):
    with pytest.raises(FileNotFoundError):
        rollback(memory_root, backup_dir, which="latest", force=True)


def test_rollback_unknown_timestamp_raises(memory_root, backup_dir):
    (memory_root / "a.md").write_text("v1", encoding="utf-8")
    create_snapshot(memory_root, backup_dir, reason="v1")
    with pytest.raises(FileNotFoundError):
        rollback(memory_root, backup_dir, which="2000-01-01_000000", force=True)


def test_rollback_without_force_requires_confirmation(memory_root, backup_dir, monkeypatch):
    (memory_root / "a.md").write_text("v1", encoding="utf-8")
    create_snapshot(memory_root, backup_dir, reason="v1")
    (memory_root / "a.md").write_text("v2", encoding="utf-8")

    monkeypatch.setattr("builtins.input", lambda _: "n")
    with pytest.raises(RuntimeError):
        rollback(memory_root, backup_dir, which="latest", force=False)
    assert (memory_root / "a.md").read_text(encoding="utf-8") == "v2"
