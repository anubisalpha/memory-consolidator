from scanner import (
    parse_index,
    parse_memory_file,
    quick_is_memory_file,
    scan_memory_files,
    scan_memory_files_scoped,
)

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


def test_name_falls_back_to_stem_when_yaml_coerces_to_date(memory_root):
    # unquoted `name: 2026-01-01` parses as datetime.date, not a string
    path = memory_root / "date-slug.md"
    path.write_text("---\nname: 2026-01-01\ndescription: desc\nmetadata:\n  type: user\n---\nbody\n",
                     encoding="utf-8")
    mf = parse_memory_file(path)
    assert isinstance(mf.frontmatter.get("name"), object)  # confirms YAML did coerce it
    assert mf.name == "date-slug"  # .name property still returns a usable string


def test_name_falls_back_to_stem_when_yaml_coerces_to_int(memory_root):
    path = memory_root / "numeric-slug.md"
    path.write_text("---\nname: 2026\ndescription: desc\nmetadata:\n  type: user\n---\nbody\n",
                     encoding="utf-8")
    mf = parse_memory_file(path)
    assert isinstance(mf.frontmatter.get("name"), int)
    assert mf.name == "numeric-slug"


def test_mem_type_none_when_metadata_not_a_mapping(memory_root):
    path = memory_root / "bad-metadata.md"
    path.write_text("---\nname: a\ndescription: desc\nmetadata: sometext\n---\nbody\n", encoding="utf-8")
    mf = parse_memory_file(path)
    assert mf.mem_type is None  # must not raise


def test_mem_type_none_when_type_value_not_a_string(memory_root):
    path = memory_root / "bad-type.md"
    path.write_text("---\nname: a\ndescription: desc\nmetadata:\n  type: 123\n---\nbody\n", encoding="utf-8")
    mf = parse_memory_file(path)
    assert mf.mem_type is None


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


def test_quick_is_memory_file_true_for_real_memory(memory_root):
    path = write_memory_file(memory_root, "a.md", "a", "desc", "user", "body")
    assert quick_is_memory_file(path) is True


def test_quick_is_memory_file_false_for_plain_readme(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("# My Project\n\nJust a normal readme, no frontmatter.\n", encoding="utf-8")
    assert quick_is_memory_file(path) is False


def test_quick_is_memory_file_false_for_unrelated_frontmatter(tmp_path):
    path = tmp_path / "post.md"
    path.write_text("---\ntitle: My Blog Post\ndate: 2026-01-01\n---\nbody\n", encoding="utf-8")
    assert quick_is_memory_file(path) is False


def test_scan_scoped_skips_non_memory_files_silently(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    write_memory_file(memory_dir, "real.md", "real", "a real memory entry", "user", "body")
    (memory_dir / "README.md").write_text("# just docs, no frontmatter\n", encoding="utf-8")

    files = scan_memory_files_scoped(tmp_path, ["**/memory/**/*.md"])
    names = {f.path.name for f in files}
    assert names == {"real.md"}

