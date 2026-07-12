import pytest

from config import ResolvedArea, backup_dir_conflicts_with_area, ensure_backup_safe_for_area


def test_backup_dir_conflicts_when_nested(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    backup_dir = root / "sub" / "backups"
    area = ResolvedArea("proj", root, "scoped")
    assert backup_dir_conflicts_with_area(area, backup_dir) is True


def test_backup_dir_conflicts_when_equal(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    area = ResolvedArea("proj", root, "scoped")
    assert backup_dir_conflicts_with_area(area, root) is True


def test_backup_dir_no_conflict_when_sibling(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    backup_dir = tmp_path / "elsewhere" / "backups"
    area = ResolvedArea("proj", root, "scoped")
    assert backup_dir_conflicts_with_area(area, backup_dir) is False


def test_ensure_backup_safe_for_area_exits_on_conflict(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    backup_dir = root / "backups"
    area = ResolvedArea("proj", root, "scoped")
    with pytest.raises(SystemExit):
        ensure_backup_safe_for_area(area, backup_dir)


def test_ensure_backup_safe_for_area_passes_when_safe(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    backup_dir = tmp_path / "elsewhere"
    area = ResolvedArea("proj", root, "scoped")
    ensure_backup_safe_for_area(area, backup_dir)  # should not raise
