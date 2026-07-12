from discovery import discover_external_memory_files


def test_discover_finds_external_claude_memory(tmp_path):
    memory_root = tmp_path / "memory"
    memory_root.mkdir()

    project_dir = tmp_path / "projects" / "Foo"
    project_dir.mkdir(parents=True)
    (project_dir / "CLAUDE_MEMORY.md").write_text("content", encoding="utf-8")

    found = discover_external_memory_files(tmp_path, memory_root)
    paths = {d.path.name for d in found}
    assert "CLAUDE_MEMORY.md" in paths


def test_discover_excludes_files_inside_memory_root(tmp_path):
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    (memory_root / "MEMORY.md").write_text("index", encoding="utf-8")

    found = discover_external_memory_files(tmp_path, memory_root)
    assert found == []


def test_discover_ignores_git_and_node_modules(tmp_path):
    memory_root = tmp_path / "memory"
    memory_root.mkdir()

    ignored = tmp_path / "node_modules" / "somepkg"
    ignored.mkdir(parents=True)
    (ignored / "MEMORY.md").write_text("noise", encoding="utf-8")

    found = discover_external_memory_files(tmp_path, memory_root)
    assert found == []


def test_discover_matches_underscore_memory_suffix(tmp_path):
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    other = tmp_path / "notes"
    other.mkdir()
    (other / "simcity_sim_memory.md").write_text("content", encoding="utf-8")

    found = discover_external_memory_files(tmp_path, memory_root)
    paths = {d.path.name for d in found}
    assert "simcity_sim_memory.md" in paths
