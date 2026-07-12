import pytest
import yaml

from templates import bootstrap_memory_folder, scaffold_memory_file, slugify


def test_bootstrap_creates_missing_folder_and_files(tmp_path):
    root = tmp_path / "fresh_memory"
    actions = bootstrap_memory_folder(root)
    assert root.exists()
    assert (root / "MEMORY.md").exists()
    assert (root / "MEMORY_RULES.md").exists()
    assert len(actions) == 3


def test_bootstrap_idempotent(memory_root):
    bootstrap_memory_folder(memory_root)
    actions = bootstrap_memory_folder(memory_root)
    assert actions == []


def test_slugify():
    assert slugify("My Cool Memory!") == "my-cool-memory"
    assert slugify("already-kebab") == "already-kebab"


def test_scaffold_memory_file_project_has_why_how(memory_root):
    path = scaffold_memory_file(memory_root, "project", "My Project", "a description")
    content = path.read_text(encoding="utf-8")
    assert 'name: "my-project"' in content
    assert "**Why:**" in content
    assert "**How to apply:**" in content


def test_scaffold_memory_file_user_has_no_why_how(memory_root):
    path = scaffold_memory_file(memory_root, "user", "user-fact", "a description")
    content = path.read_text(encoding="utf-8")
    assert "**Why:**" not in content


def test_scaffold_memory_file_invalid_type_raises(memory_root):
    with pytest.raises(ValueError):
        scaffold_memory_file(memory_root, "bogus", "slug", "desc")


def test_scaffold_memory_file_existing_raises(memory_root):
    scaffold_memory_file(memory_root, "user", "dup-slug", "desc")
    with pytest.raises(FileExistsError):
        scaffold_memory_file(memory_root, "user", "dup-slug", "desc")


def test_scaffold_memory_file_empty_slug_raises(memory_root):
    with pytest.raises(ValueError, match="empty filename"):
        scaffold_memory_file(memory_root, "user", "!!!...???", "desc")
    assert not any(memory_root.iterdir())


def test_scaffold_memory_file_date_like_slug_stays_a_string(memory_root):
    # a slug like "2026-01-01" is a plausible thing to type; the name: field
    # must be quoted in the generated YAML so it round-trips as a string,
    # not get silently coerced into a datetime.date on the next parse.
    path = scaffold_memory_file(memory_root, "user", "2026-01-01", "a description")
    content = path.read_text(encoding="utf-8")
    frontmatter_text = content.split("---")[1]
    parsed = yaml.safe_load(frontmatter_text)
    assert isinstance(parsed["name"], str)
    assert parsed["name"] == "2026-01-01"
