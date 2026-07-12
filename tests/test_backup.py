import zipfile

import pytest

from backup import create_snapshot, create_targeted_snapshot, list_snapshots, restore_single_file, rollback


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


# ---- create_targeted_snapshot ----

def test_create_targeted_snapshot_backs_up_only_specified_files(memory_root, backup_dir):
    (memory_root / "a.md").write_text("content a", encoding="utf-8")
    (memory_root / "b.md").write_text("content b", encoding="utf-8")
    (memory_root / "untouched.md").write_text("should not be backed up", encoding="utf-8")

    zip_path = create_targeted_snapshot(
        [memory_root / "a.md", memory_root / "b.md"], memory_root, backup_dir, reason="targeted test",
    )
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert names == {"a.md", "b.md"}
    assert "untouched.md" not in names


def test_create_targeted_snapshot_records_manifest(memory_root, backup_dir):
    (memory_root / "a.md").write_text("content", encoding="utf-8")
    create_targeted_snapshot([memory_root / "a.md"], memory_root, backup_dir, reason="test reason")

    snapshots = list_snapshots(backup_dir)
    assert len(snapshots) == 1
    assert snapshots[0]["reason"] == "test reason"
    assert str(memory_root / "a.md") in snapshots[0]["targeted_files"]


def test_create_targeted_snapshot_skips_missing_files(memory_root, backup_dir):
    (memory_root / "a.md").write_text("content", encoding="utf-8")
    zip_path = create_targeted_snapshot(
        [memory_root / "a.md", memory_root / "does_not_exist.md"], memory_root, backup_dir, reason="test",
    )
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == ["a.md"]


def test_create_targeted_snapshot_ignores_untouched_files_when_huge(memory_root, backup_dir):
    # simulates the real-world case: a scoped area has many files, but only
    # the specific conflicting ones should ever be backed up
    for i in range(50):
        (memory_root / f"file_{i}.md").write_text(f"content {i}", encoding="utf-8")
    target = memory_root / "file_0.md"

    zip_path = create_targeted_snapshot([target], memory_root, backup_dir, reason="test")
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == ["file_0.md"]


# ---- backup_retention pruning ----

def test_create_snapshot_prunes_older_snapshots_beyond_keep_last_n(memory_root, backup_dir):
    for i in range(5):
        (memory_root / "a.md").write_text(f"v{i}", encoding="utf-8")
        create_snapshot(memory_root, backup_dir, reason=f"v{i}", keep_last_n=3)

    snapshots = list_snapshots(backup_dir)
    assert len(snapshots) == 3
    assert [s["reason"] for s in snapshots] == ["v2", "v3", "v4"]
    # pruned zips must actually be deleted from disk, not just the manifest
    assert len(list(backup_dir.glob("*.zip"))) == 3


def test_create_snapshot_no_pruning_when_keep_last_n_none(memory_root, backup_dir):
    for i in range(5):
        (memory_root / "a.md").write_text(f"v{i}", encoding="utf-8")
        create_snapshot(memory_root, backup_dir, reason=f"v{i}")

    assert len(list_snapshots(backup_dir)) == 5


def test_create_snapshot_prunes_only_own_area(memory_root, backup_dir, tmp_path):
    other_root = tmp_path / "other_area"
    other_root.mkdir()

    for i in range(4):
        (memory_root / "a.md").write_text(f"v{i}", encoding="utf-8")
        create_snapshot(memory_root, backup_dir, reason=f"area-a-v{i}", keep_last_n=2)
    (other_root / "b.md").write_text("only version", encoding="utf-8")
    create_snapshot(other_root, backup_dir, reason="area-b-only", keep_last_n=2)

    snapshots = list_snapshots(backup_dir)
    reasons = [s["reason"] for s in snapshots]
    # area-a should be pruned down to its last 2, area-b's single snapshot untouched
    assert reasons == ["area-a-v2", "area-a-v3", "area-b-only"]


def test_create_targeted_snapshot_prunes_older_snapshots(memory_root, backup_dir):
    for i in range(4):
        (memory_root / "a.md").write_text(f"v{i}", encoding="utf-8")
        create_targeted_snapshot([memory_root / "a.md"], memory_root, backup_dir,
                                  reason=f"v{i}", keep_last_n=2)

    snapshots = list_snapshots(backup_dir)
    assert len(snapshots) == 2
    assert [s["reason"] for s in snapshots] == ["v2", "v3"]


# ---- restore_single_file ----

def test_restore_single_file_restores_only_that_file(memory_root, backup_dir):
    (memory_root / "a.md").write_text("original a", encoding="utf-8")
    (memory_root / "b.md").write_text("original b", encoding="utf-8")
    create_snapshot(memory_root, backup_dir, reason="before changes")

    (memory_root / "a.md").write_text("mutated a", encoding="utf-8")
    (memory_root / "b.md").write_text("mutated b", encoding="utf-8")

    restored = restore_single_file(memory_root, backup_dir, "a.md")

    assert restored == memory_root / "a.md"
    assert (memory_root / "a.md").read_text(encoding="utf-8") == "original a"
    assert (memory_root / "b.md").read_text(encoding="utf-8") == "mutated b"  # untouched


def test_restore_single_file_by_specific_timestamp(memory_root, backup_dir):
    (memory_root / "a.md").write_text("v1", encoding="utf-8")
    create_snapshot(memory_root, backup_dir, reason="v1")
    first_ts = list_snapshots(backup_dir)[0]["timestamp"]

    (memory_root / "a.md").write_text("v2", encoding="utf-8")
    create_snapshot(memory_root, backup_dir, reason="v2")
    (memory_root / "a.md").write_text("v3 (unwanted)", encoding="utf-8")

    restore_single_file(memory_root, backup_dir, "a.md", which=first_ts)
    assert (memory_root / "a.md").read_text(encoding="utf-8") == "v1"


def test_restore_single_file_no_snapshots_raises(memory_root, backup_dir):
    with pytest.raises(FileNotFoundError):
        restore_single_file(memory_root, backup_dir, "a.md")


def test_restore_single_file_unknown_timestamp_raises(memory_root, backup_dir):
    (memory_root / "a.md").write_text("v1", encoding="utf-8")
    create_snapshot(memory_root, backup_dir, reason="v1")
    with pytest.raises(FileNotFoundError):
        restore_single_file(memory_root, backup_dir, "a.md", which="2000-01-01_000000")


def test_restore_single_file_missing_from_targeted_snapshot_raises(memory_root, backup_dir):
    (memory_root / "a.md").write_text("content", encoding="utf-8")
    (memory_root / "untouched.md").write_text("not backed up", encoding="utf-8")
    create_targeted_snapshot([memory_root / "a.md"], memory_root, backup_dir, reason="targeted")

    with pytest.raises(FileNotFoundError):
        restore_single_file(memory_root, backup_dir, "untouched.md")


def test_restore_single_file_only_considers_matching_memory_root(memory_root, backup_dir, tmp_path):
    other_root = tmp_path / "other_area"
    other_root.mkdir()
    (other_root / "a.md").write_text("other area content", encoding="utf-8")
    create_snapshot(other_root, backup_dir, reason="other area snapshot")

    with pytest.raises(FileNotFoundError):
        restore_single_file(memory_root, backup_dir, "a.md")
