from fixer import add_missing_index_entries, remove_dead_index_links
from scanner import parse_index, scan_memory_files

from .conftest import write_index, write_memory_file


def test_add_missing_index_entries_appends_only(memory_root):
    write_memory_file(memory_root, "indexed.md", "indexed", "already indexed", "user", "body")
    write_memory_file(memory_root, "orphan.md", "orphan-file", "an orphan memory", "user", "body")
    write_index(memory_root, ["- [Indexed](indexed.md) — already indexed"])

    files = scan_memory_files(memory_root)
    index_entries, _ = parse_index(memory_root)
    actions = add_missing_index_entries(memory_root, files, index_entries)

    assert len(actions) == 1
    new_entries, new_lines = parse_index(memory_root)
    hrefs = {e.href for e in new_entries}
    assert hrefs == {"indexed.md", "orphan.md"}
    # original line untouched
    assert any("already indexed" in line for line in new_lines)


def test_add_missing_index_entries_no_trailing_newline_does_not_corrupt(memory_root):
    write_memory_file(memory_root, "orphan.md", "orphan", "an orphan memory", "user", "body")
    # simulate a hand-edited/generated MEMORY.md with no trailing newline
    (memory_root / "MEMORY.md").write_bytes(b"# Memory Index\n\n- [A](a.md) - hook")

    files = scan_memory_files(memory_root)
    index_entries, _ = parse_index(memory_root)
    add_missing_index_entries(memory_root, files, index_entries)

    content = (memory_root / "MEMORY.md").read_text(encoding="utf-8")
    assert "hook- [" not in content  # the two entries must not be merged onto one line
    lines = [line for line in content.splitlines() if line.startswith("- [")]
    assert len(lines) == 2


def test_add_missing_index_entries_skips_malformed(memory_root):
    (memory_root / "bad.md").write_text("no frontmatter", encoding="utf-8")
    files = scan_memory_files(memory_root)
    index_entries, _ = parse_index(memory_root)
    actions = add_missing_index_entries(memory_root, files, index_entries)
    assert actions == []


def test_add_missing_index_entries_creates_index_if_missing(memory_root):
    write_memory_file(memory_root, "a.md", "a", "a memory", "user", "body")
    assert not (memory_root / "MEMORY.md").exists()
    files = scan_memory_files(memory_root)
    actions = add_missing_index_entries(memory_root, files, [])
    assert len(actions) == 1
    assert (memory_root / "MEMORY.md").exists()


def test_add_missing_index_entries_noop_when_all_indexed(memory_root):
    write_memory_file(memory_root, "a.md", "a", "a memory", "user", "body")
    write_index(memory_root, ["- [A](a.md) — a memory"])
    files = scan_memory_files(memory_root)
    index_entries, _ = parse_index(memory_root)
    assert add_missing_index_entries(memory_root, files, index_entries) == []


def test_remove_dead_index_links_removes_only_broken(memory_root):
    write_memory_file(memory_root, "real.md", "real", "a real memory", "user", "body")
    write_index(memory_root, [
        "- [Real](real.md) — a real memory",
        "- [Ghost](ghost.md) — points nowhere",
    ])
    index_entries, index_lines = parse_index(memory_root)
    actions = remove_dead_index_links(memory_root, index_entries, index_lines)

    assert len(actions) == 1
    new_entries, new_lines = parse_index(memory_root)
    assert {e.href for e in new_entries} == {"real.md"}
    assert not any("ghost.md" in line for line in new_lines)
    assert any("real.md" in line for line in new_lines)


def test_remove_dead_index_links_noop_when_all_valid(memory_root):
    write_memory_file(memory_root, "real.md", "real", "a real memory", "user", "body")
    write_index(memory_root, ["- [Real](real.md) — a real memory"])
    index_entries, index_lines = parse_index(memory_root)
    assert remove_dead_index_links(memory_root, index_entries, index_lines) == []
