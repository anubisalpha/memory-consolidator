from datetime import date, timedelta

from fixer import (
    add_missing_index_entries,
    fix_slug_mismatches,
    mark_stale_files,
    merge_exact_duplicates,
    remove_dead_index_links,
)
from scanner import parse_index, parse_memory_file, scan_memory_files

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


def test_add_missing_index_entries_uses_custom_header_for_new_index(memory_root):
    write_memory_file(memory_root, "a.md", "a", "a memory", "user", "body")
    custom_header = "# Special Area\n\nThis is not auto-loaded — reference manually.\n\n"
    add_missing_index_entries(memory_root, scan_memory_files(memory_root), [], index_header=custom_header)
    content = (memory_root / "MEMORY.md").read_text(encoding="utf-8")
    assert content.startswith("# Special Area")
    assert "not auto-loaded" in content
    assert "- [A](a.md)" in content


def test_add_missing_index_entries_custom_header_gets_trailing_newline(memory_root):
    write_memory_file(memory_root, "a.md", "a", "a memory", "user", "body")
    add_missing_index_entries(memory_root, scan_memory_files(memory_root), [], index_header="# No trailing newline")
    content = (memory_root / "MEMORY.md").read_text(encoding="utf-8")
    assert "# No trailing newline\n- [A]" in content or "# No trailing newline\n\n- [A]" in content


def test_add_missing_index_entries_custom_header_not_used_when_index_already_exists(memory_root):
    write_memory_file(memory_root, "orphan.md", "orphan", "an orphan memory", "user", "body")
    write_index(memory_root, ["# Existing Header", "", "- [Other](other.md) — pre-existing"])
    add_missing_index_entries(memory_root, scan_memory_files(memory_root), [],
                               index_header="# Should Not Appear")
    content = (memory_root / "MEMORY.md").read_text(encoding="utf-8")
    assert "Should Not Appear" not in content
    assert "# Existing Header" in content  # untouched


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


# ---- mark_stale_files ----

def test_mark_stale_files_marks_old_dated_project_memory(memory_root, rules):
    old_date = (date.today() - timedelta(days=200)).isoformat()
    write_memory_file(memory_root, "a.md", "a", "desc", "project", f"decided on {old_date}\n\n**Why:** x\n**How to apply:** y")
    files = scan_memory_files(memory_root)
    actions = mark_stale_files(files, rules)

    assert len(actions) == 1
    reparsed = parse_memory_file(memory_root / "a.md")
    assert reparsed.body.startswith("> ⚠ **Possibly stale**")
    assert reparsed.parse_error is None
    assert reparsed.name == "a"


def test_mark_stale_files_idempotent_on_rerun(memory_root, rules):
    old_date = (date.today() - timedelta(days=200)).isoformat()
    write_memory_file(memory_root, "a.md", "a", "desc", "project", f"decided on {old_date}")
    files = scan_memory_files(memory_root)
    mark_stale_files(files, rules)

    files_again = scan_memory_files(memory_root)
    actions = mark_stale_files(files_again, rules)
    assert actions == []  # already marked — must not stack a second marker

    reparsed = parse_memory_file(memory_root / "a.md")
    assert reparsed.body.count("Possibly stale") == 1


def test_mark_stale_files_skips_recent_dates(memory_root, rules):
    recent_date = (date.today() - timedelta(days=5)).isoformat()
    write_memory_file(memory_root, "a.md", "a", "desc", "project", f"decided on {recent_date}")
    files = scan_memory_files(memory_root)
    assert mark_stale_files(files, rules) == []


def test_mark_stale_files_disabled(memory_root, rules):
    rules["staleness"]["enabled"] = False
    old_date = (date.today() - timedelta(days=200)).isoformat()
    write_memory_file(memory_root, "a.md", "a", "desc", "project", f"decided on {old_date}")
    files = scan_memory_files(memory_root)
    assert mark_stale_files(files, rules) == []


# ---- merge_exact_duplicates ----

def test_merge_exact_duplicates_stubs_the_alphabetically_later_file(memory_root, rules):
    body = "identical content here, long enough to pass the floor " * 3
    write_memory_file(memory_root, "a.md", "a", "desc a", "user", body)
    write_memory_file(memory_root, "z.md", "z", "desc z", "user", body)
    files = scan_memory_files(memory_root)
    actions = merge_exact_duplicates(files, rules)

    assert len(actions) == 1
    assert "z.md -> a.md" in actions[0]

    a_reparsed = parse_memory_file(memory_root / "a.md")
    z_reparsed = parse_memory_file(memory_root / "z.md")
    assert not a_reparsed.body.strip().lower().startswith("pointer only")
    assert z_reparsed.body.strip().lower().startswith("pointer only")
    assert "a.md" in z_reparsed.body
    assert z_reparsed.parse_error is None
    assert z_reparsed.name == "z"  # own identity preserved, only body replaced


def test_merge_exact_duplicates_ignores_non_identical(memory_root, rules):
    write_memory_file(memory_root, "a.md", "a", "desc a", "user", "content one, long enough to pass the floor here")
    write_memory_file(memory_root, "b.md", "b", "desc b", "user", "content two, long enough to pass the floor here")
    files = scan_memory_files(memory_root)
    assert merge_exact_duplicates(files, rules) == []


def test_merge_exact_duplicates_respects_type_boundary(memory_root, rules):
    body = "identical content here, long enough to pass the floor " * 3
    write_memory_file(memory_root, "a.md", "a", "desc a", "user", body)
    write_memory_file(memory_root, "b.md", "b", "desc b", "project", body)
    files = scan_memory_files(memory_root)
    assert merge_exact_duplicates(files, rules) == []


def test_merge_exact_duplicates_skips_existing_pointer_stubs(memory_root, rules):
    stub_body = "Pointer only; consolidated into the 'memory-diverged' area — full details in `memory-diverged/x.md`.\n"
    write_memory_file(memory_root, "a.md", "a", "desc a", "project", stub_body)
    write_memory_file(memory_root, "b.md", "b", "desc b", "project", stub_body)
    files = scan_memory_files(memory_root)
    assert merge_exact_duplicates(files, rules) == []


def test_merge_exact_duplicates_disabled(memory_root, rules):
    rules["duplicate_detection"]["enabled"] = False
    body = "identical content here, long enough to pass the floor " * 3
    write_memory_file(memory_root, "a.md", "a", "desc a", "user", body)
    write_memory_file(memory_root, "z.md", "z", "desc z", "user", body)
    files = scan_memory_files(memory_root)
    assert merge_exact_duplicates(files, rules) == []


# ---- fix_slug_mismatches ----

def test_fix_slug_mismatches_renames_file_to_match_kebab_name(memory_root, rules):
    write_memory_file(memory_root, "aity_brand_website.md", "aity-brand-website", "desc", "project", "body")
    write_index(memory_root, ["- [Aity](aity_brand_website.md) — desc"])
    files = scan_memory_files(memory_root)

    actions = fix_slug_mismatches(memory_root, files, rules)

    assert len(actions) == 1
    assert "aity_brand_website.md -> aity-brand-website.md" in actions[0]
    assert not (memory_root / "aity_brand_website.md").exists()
    assert (memory_root / "aity-brand-website.md").exists()
    _, index_lines = parse_index(memory_root)
    assert any("aity-brand-website.md" in line for line in index_lines)
    assert not any("aity_brand_website.md" in line for line in index_lines)


def test_fix_slug_mismatches_normalizes_non_kebab_name_and_renames(memory_root, rules):
    write_memory_file(memory_root, "tournament_dashboard_project.md",
                       "tournament_dashboard_project", "desc", "project", "body")
    files = scan_memory_files(memory_root)

    actions = fix_slug_mismatches(memory_root, files, rules)

    assert any("renamed tournament_dashboard_project.md -> tournament-dashboard-project.md" in a for a in actions)
    new_path = memory_root / "tournament-dashboard-project.md"
    assert new_path.exists()
    reparsed = parse_memory_file(new_path)
    assert reparsed.frontmatter["name"] == "tournament-dashboard-project"


def test_fix_slug_mismatches_skips_on_collision(memory_root, rules):
    write_memory_file(memory_root, "a_b.md", "a-b", "desc", "user", "body one")
    write_memory_file(memory_root, "a-b.md", "a-b", "desc", "user", "body two")
    files = scan_memory_files(memory_root)

    actions = fix_slug_mismatches(memory_root, files, rules)

    assert any("skipped slug fix for a_b.md" in a for a in actions)
    assert (memory_root / "a_b.md").exists()  # left alone, not overwritten or deleted
    assert (memory_root / "a-b.md").exists()


def test_fix_slug_mismatches_noop_when_already_matching(memory_root, rules):
    write_memory_file(memory_root, "already-kebab.md", "already-kebab", "desc", "user", "body")
    files = scan_memory_files(memory_root)
    assert fix_slug_mismatches(memory_root, files, rules) == []


def test_fix_slug_mismatches_disabled_via_rules(memory_root, rules):
    rules["spec_conformance"]["require_kebab_case_slug"] = False
    write_memory_file(memory_root, "aity_brand_website.md", "aity-brand-website", "desc", "project", "body")
    files = scan_memory_files(memory_root)
    assert fix_slug_mismatches(memory_root, files, rules) == []
    assert (memory_root / "aity_brand_website.md").exists()
