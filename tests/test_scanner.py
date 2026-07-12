from scanner import parse_index, parse_memory_file, scan_memory_files

from .conftest import write_index, write_memory_file


def test_parse_memory_file_valid(memory_root):
    path = write_memory_file(memory_root, "foo.md", "foo", "a test memory",
                              "project", "**Why:** because\n\n**How to apply:** always")
    mf = parse_memory_file(path)
    assert mf.parse_error is None
    assert mf.name == "foo"
    assert mf.mem_type == "project"
    assert "Why" in mf.body


def test_parse_memory_file_missing_frontmatter(memory_root):
    path = memory_root / "bad.md"
    path.write_text("just some text, no frontmatter", encoding="utf-8")
    mf = parse_memory_file(path)
    assert mf.parse_error is not None


def test_parse_memory_file_invalid_yaml(memory_root):
    path = memory_root / "bad.md"
    path.write_text("---\nname: [unterminated\n---\nbody", encoding="utf-8")
    mf = parse_memory_file(path)
    assert mf.parse_error is not None


def test_scan_excludes_index_and_rules_files(memory_root):
    write_memory_file(memory_root, "a.md", "a", "desc a", "user", "body")
    write_index(memory_root, ["- [A](a.md) — hook"])
    (memory_root / "MEMORY_RULES.md").write_text("# rules", encoding="utf-8")

    files = scan_memory_files(memory_root)
    names = {f.path.name for f in files}
    assert names == {"a.md"}


def test_wikilinks_extracted(memory_root):
    path = write_memory_file(memory_root, "a.md", "a", "desc a", "user", "see [[b]] and [[c]]")
    mf = parse_memory_file(path)
    assert mf.wikilinks == ["b", "c"]


def test_parse_index(memory_root):
    write_index(memory_root, [
        "- [Title One](one.md) — hook one",
        "not an index line",
        "- [Title Two](two.md) — hook two",
    ])
    entries, lines = parse_index(memory_root)
    assert len(entries) == 2
    assert entries[0].title == "Title One"
    assert entries[0].href == "one.md"
    assert len(lines) == 5  # header + blank + 3 body lines


def test_parse_index_missing_file(memory_root):
    entries, lines = parse_index(memory_root)
    assert entries == []
    assert lines == []


def test_scan_recurses_into_subfolders(memory_root):
    write_memory_file(memory_root, "top.md", "top", "top level memory", "user", "body")
    sub = memory_root / "archive"
    sub.mkdir()
    write_memory_file(sub, "nested.md", "nested", "nested memory", "user", "body")

    files = scan_memory_files(memory_root)
    names = {f.path.name for f in files}
    assert names == {"top.md", "nested.md"}

