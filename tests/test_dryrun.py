import pytest

from dryrun import create_dry_run_copy, diff_changed_files, diff_memory_index

from .conftest import write_index, write_memory_file


def test_create_dry_run_copy_rejects_staging_dir_inside_area_root(memory_root):
    write_memory_file(memory_root, "a.md", "a", "desc", "user", "body")
    staging_dir = memory_root / "backups" / "dryrun_x"  # inside area_root
    with pytest.raises(ValueError, match="inside area_root"):
        create_dry_run_copy(memory_root, staging_dir)


def test_create_dry_run_copy_rejects_staging_dir_equal_to_area_root(memory_root):
    with pytest.raises(ValueError, match="inside area_root"):
        create_dry_run_copy(memory_root, memory_root)


def test_create_dry_run_copy_mirrors_content(memory_root, tmp_path):
    write_memory_file(memory_root, "a.md", "a", "desc", "user", "body")
    write_index(memory_root, ["- [A](a.md) — desc"])

    staging = tmp_path / "staging"
    result = create_dry_run_copy(memory_root, staging)

    assert result == staging
    assert (staging / "a.md").exists()
    assert (staging / "MEMORY.md").exists()
    assert (staging / "a.md").read_text(encoding="utf-8") == (memory_root / "a.md").read_text(encoding="utf-8")


def test_create_dry_run_copy_is_independent(memory_root, tmp_path):
    write_memory_file(memory_root, "a.md", "a", "desc", "user", "body")
    staging = create_dry_run_copy(memory_root, tmp_path / "staging")

    (staging / "a.md").write_text("mutated copy", encoding="utf-8")
    assert (memory_root / "a.md").read_text(encoding="utf-8") != "mutated copy"


def test_create_dry_run_copy_overwrites_previous(memory_root, tmp_path):
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    (staging_dir / "stale.md").write_text("leftover from a previous run", encoding="utf-8")

    write_memory_file(memory_root, "a.md", "a", "desc", "user", "body")
    create_dry_run_copy(memory_root, staging_dir)

    assert not (staging_dir / "stale.md").exists()
    assert (staging_dir / "a.md").exists()


def test_diff_memory_index_shows_changes(memory_root, tmp_path):
    write_index(memory_root, ["- [Real](real.md) — a real memory"])
    modified = tmp_path / "modified"
    modified.mkdir()
    write_index(modified, ["- [Real](real.md) — a real memory", "- [New](new.md) — added by fix"])

    diff = diff_memory_index(memory_root, modified)
    diff_text = "".join(diff)
    assert "+- [New](new.md)" in diff_text


def test_diff_memory_index_empty_when_identical(memory_root, tmp_path):
    write_index(memory_root, ["- [Real](real.md) — a real memory"])
    modified = tmp_path / "modified"
    modified.mkdir()
    write_index(modified, ["- [Real](real.md) — a real memory"])

    assert diff_memory_index(memory_root, modified) == []


def test_diff_memory_index_missing_files_handled(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert diff_memory_index(a, b) == []


# ---- diff_changed_files ----

def test_diff_changed_files_reports_modified_body(memory_root, tmp_path):
    write_memory_file(memory_root, "a.md", "a", "desc", "user", "original body")
    modified = tmp_path / "modified"
    create_dry_run_copy(memory_root, modified)
    (modified / "a.md").write_text(
        (modified / "a.md").read_text(encoding="utf-8").replace("original body", "changed body"),
        encoding="utf-8",
    )

    diffs = diff_changed_files(memory_root, modified)
    assert len(diffs) == 1
    rel, diff_lines = diffs[0]
    assert rel == "a.md"
    diff_text = "".join(diff_lines)
    assert "-original body" in diff_text
    assert "+changed body" in diff_text


def test_diff_changed_files_ignores_memory_md(memory_root, tmp_path):
    write_memory_file(memory_root, "a.md", "a", "desc", "user", "body")
    write_index(memory_root, ["- [A](a.md) — desc"])
    modified = tmp_path / "modified"
    create_dry_run_copy(memory_root, modified)
    (modified / "MEMORY.md").write_text("# Changed Index\n", encoding="utf-8")

    assert diff_changed_files(memory_root, modified) == []


def test_diff_changed_files_empty_when_identical(memory_root, tmp_path):
    write_memory_file(memory_root, "a.md", "a", "desc", "user", "body")
    modified = tmp_path / "modified"
    create_dry_run_copy(memory_root, modified)
    assert diff_changed_files(memory_root, modified) == []


def test_diff_changed_files_handles_new_file_with_no_original(memory_root, tmp_path):
    modified = tmp_path / "modified"
    modified.mkdir()
    write_memory_file(modified, "new.md", "new", "desc", "user", "brand new content")

    diffs = diff_changed_files(memory_root, modified)
    assert len(diffs) == 1
    assert diffs[0][0] == "new.md"
