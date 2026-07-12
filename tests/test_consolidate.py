import yaml

from consolidate import write_canonical_file, write_pointer_stub
from scanner import parse_memory_file

from .conftest import write_memory_file


def test_write_canonical_file_creates_expected_content(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    path = write_memory_file(source_root, "a.md", "shared-slug", "the original description",
                              "project", "the chosen body content")
    chosen = parse_memory_file(path)

    diverged_root = tmp_path / "diverged"
    diverged_root.mkdir()
    result_path = write_canonical_file(diverged_root, "shared-slug", chosen, "kept the 'area-a' version")

    assert result_path == diverged_root / "shared-slug.md"
    content = result_path.read_text(encoding="utf-8")
    assert "the chosen body content" in content
    assert "kept the 'area-a' version" in content

    frontmatter_text = content.split("---")[1]
    parsed = yaml.safe_load(frontmatter_text)
    assert parsed["name"] == "shared-slug"
    assert parsed["metadata"]["type"] == "project"
    assert isinstance(parsed["name"], str)


def test_write_canonical_file_falls_back_to_project_type(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    # a file with no resolvable mem_type (e.g. missing/invalid metadata)
    path = source_root / "a.md"
    path.write_text("---\nname: a\ndescription: desc\nmetadata: notadict\n---\nbody\n", encoding="utf-8")
    chosen = parse_memory_file(path)
    assert chosen.mem_type is None

    diverged_root = tmp_path / "diverged"
    diverged_root.mkdir()
    result_path = write_canonical_file(diverged_root, "a", chosen, "note")
    parsed = yaml.safe_load(result_path.read_text(encoding="utf-8").split("---")[1])
    assert parsed["metadata"]["type"] == "project"  # fallback


def test_write_pointer_stub_preserves_name_and_type(tmp_path):
    original_path = write_memory_file(tmp_path, "orig.md", "shared-slug", "original desc", "project", "full original content")
    original = parse_memory_file(original_path)

    canonical_path = tmp_path / "diverged" / "shared-slug.md"
    write_pointer_stub(original, canonical_path, "memory-diverged")

    content = original_path.read_text(encoding="utf-8")
    assert "Pointer only" in content
    assert "memory-diverged" in content
    assert "shared-slug.md" in content
    # the pointer target must be prefixed with the diverged area's folder
    # name so check_external_pointers (checks.py) resolves it against
    # workspace_root as `memory-diverged/shared-slug.md`, not a bare
    # filename that would resolve to workspace_root itself
    assert "`memory-diverged/shared-slug.md`" in content

    reparsed = parse_memory_file(original_path)
    assert reparsed.name == "shared-slug"
    assert reparsed.mem_type == "project"
    assert reparsed.parse_error is None


def test_write_pointer_stub_resolves_via_check_external_pointers(tmp_path):
    import checks

    workspace_root = tmp_path
    diverged_root = workspace_root / "memory-diverged"
    diverged_root.mkdir()
    (diverged_root / "shared-slug.md").write_text("canonical content", encoding="utf-8")

    original_path = write_memory_file(workspace_root, "orig.md", "shared-slug", "original desc",
                                       "project", "full original content")
    original = parse_memory_file(original_path)
    canonical_path = diverged_root / "shared-slug.md"
    write_pointer_stub(original, canonical_path, "memory-diverged")

    reparsed = parse_memory_file(original_path)
    rules = {"external_scan": {"enabled": True, "workspace_root": str(workspace_root)}}
    findings = checks.check_external_pointers([reparsed], rules)
    assert findings == []


def test_write_pointer_stub_normalizes_coerced_name(tmp_path):
    # a file whose name: field got YAML-coerced to a non-string (see
    # scanner.py's defense against this) must still produce a valid
    # string name: in the rewritten stub, not the raw coerced value
    original_path = tmp_path / "date-slug.md"
    original_path.write_text("---\nname: 2026-01-01\ndescription: desc\nmetadata:\n  type: user\n---\nbody\n",
                              encoding="utf-8")
    original = parse_memory_file(original_path)
    assert not isinstance(original.frontmatter.get("name"), str)  # confirms it was coerced

    canonical_path = tmp_path / "diverged" / "date-slug.md"
    write_pointer_stub(original, canonical_path, "memory-diverged")

    reparsed = parse_memory_file(original_path)
    assert reparsed.parse_error is None
    assert isinstance(reparsed.frontmatter.get("name"), str)
    assert reparsed.frontmatter.get("name") == "date-slug"
