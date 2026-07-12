from datetime import datetime, timedelta

import checks
from scanner import parse_index, scan_memory_files

from .conftest import write_index, write_memory_file


def test_check_malformed_files(memory_root):
    (memory_root / "bad.md").write_text("no frontmatter here", encoding="utf-8")
    files = scan_memory_files(memory_root)
    findings = checks.check_malformed_files(files)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_check_missing_frontmatter_fields(memory_root, rules):
    path = memory_root / "incomplete.md"
    path.write_text("---\nname: incomplete\n---\nbody", encoding="utf-8")
    files = scan_memory_files(memory_root)
    findings = checks.check_missing_frontmatter_fields(files, rules)
    assert len(findings) == 1
    assert "description" in findings[0].message
    assert "metadata.type" in findings[0].message


def test_check_missing_frontmatter_fields_disabled(memory_root, rules):
    rules["file_health"]["require_frontmatter"] = False
    path = memory_root / "incomplete.md"
    path.write_text("---\nname: incomplete\n---\nbody", encoding="utf-8")
    files = scan_memory_files(memory_root)
    assert checks.check_missing_frontmatter_fields(files, rules) == []


def test_check_orphans(memory_root):
    write_memory_file(memory_root, "indexed.md", "indexed", "desc", "user", "body")
    write_memory_file(memory_root, "orphan.md", "orphan", "desc", "user", "body")
    write_index(memory_root, ["- [Indexed](indexed.md) — hook"])
    files = scan_memory_files(memory_root)
    entries, _ = parse_index(memory_root)
    findings = checks.check_orphans(memory_root, files, entries)
    assert len(findings) == 1
    assert findings[0].ref == "orphan.md"


def test_check_orphans_nested_file_matches_relative_href(memory_root):
    sub = memory_root / "archive"
    sub.mkdir()
    write_memory_file(sub, "nested.md", "nested", "desc", "user", "body")
    write_index(memory_root, ["- [Nested](archive/nested.md) — hook"])
    files = scan_memory_files(memory_root)
    entries, _ = parse_index(memory_root)
    findings = checks.check_orphans(memory_root, files, entries)
    assert findings == []


def test_check_external_pointers_missing_target(memory_root, rules, tmp_path):
    rules["external_scan"] = {"enabled": True, "workspace_root": str(tmp_path)}
    write_memory_file(memory_root, "a.md", "a", "Pointer only; full details in `projects/X/CLAUDE_MEMORY.md`",
                       "project", "body")
    files = scan_memory_files(memory_root)
    findings = checks.check_external_pointers(files, rules)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_check_external_pointers_existing_target(memory_root, rules, tmp_path):
    target_dir = tmp_path / "projects" / "X"
    target_dir.mkdir(parents=True)
    (target_dir / "CLAUDE_MEMORY.md").write_text("real content", encoding="utf-8")
    rules["external_scan"] = {"enabled": True, "workspace_root": str(tmp_path)}
    write_memory_file(memory_root, "a.md", "a", "Pointer only; full details in `projects/X/CLAUDE_MEMORY.md`",
                       "project", "body")
    files = scan_memory_files(memory_root)
    findings = checks.check_external_pointers(files, rules)
    assert findings == []


def test_check_external_pointers_disabled(memory_root, rules):
    rules["external_scan"] = {"enabled": False}
    write_memory_file(memory_root, "a.md", "a", "full details in `nowhere/missing.md`", "project", "body")
    files = scan_memory_files(memory_root)
    assert checks.check_external_pointers(files, rules) == []


def test_check_dead_links(memory_root):
    write_index(memory_root, ["- [Missing](missing.md) — hook"])
    entries, _ = parse_index(memory_root)
    findings = checks.check_dead_links(memory_root, entries)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_check_broken_wikilinks(memory_root):
    write_memory_file(memory_root, "a.md", "a", "desc a", "user", "see [[b]]")
    write_memory_file(memory_root, "b.md", "b", "desc b", "user", "see [[nonexistent]]")
    files = scan_memory_files(memory_root)
    findings = checks.check_broken_wikilinks(files)
    assert len(findings) == 1
    assert "nonexistent" in findings[0].message


def test_check_slug_hygiene_bad_case(memory_root, rules):
    write_memory_file(memory_root, "a.md", "Not_Kebab", "desc", "user", "body")
    files = scan_memory_files(memory_root)
    findings = checks.check_slug_hygiene(files, rules)
    assert any("kebab-case" in f.message for f in findings)


def test_check_slug_hygiene_mismatched_filename(memory_root, rules):
    write_memory_file(memory_root, "a.md", "different-slug", "desc", "user", "body")
    files = scan_memory_files(memory_root)
    findings = checks.check_slug_hygiene(files, rules)
    assert any("does not match filename" in f.message for f in findings)


def test_check_slug_hygiene_disabled(memory_root, rules):
    rules["spec_conformance"]["require_kebab_case_slug"] = False
    write_memory_file(memory_root, "a.md", "Not_Kebab", "desc", "user", "body")
    files = scan_memory_files(memory_root)
    assert checks.check_slug_hygiene(files, rules) == []


def test_check_valid_type(memory_root, rules):
    write_memory_file(memory_root, "a.md", "a", "desc", "bogus_type", "body")
    files = scan_memory_files(memory_root)
    findings = checks.check_valid_type(files, rules)
    assert len(findings) == 1


def test_check_frontmatter_field_types_flags_non_string_name(memory_root):
    path = memory_root / "date-slug.md"
    path.write_text("---\nname: 2026-01-01\ndescription: desc\nmetadata:\n  type: user\n---\nbody\n",
                     encoding="utf-8")
    files = scan_memory_files(memory_root)
    findings = checks.check_frontmatter_field_types(files)
    assert any(f.category == "frontmatter_type" and "not a string" in f.message for f in findings)


def test_check_frontmatter_field_types_flags_non_dict_metadata(memory_root):
    path = memory_root / "bad-metadata.md"
    path.write_text("---\nname: a\ndescription: desc\nmetadata: sometext\n---\nbody\n", encoding="utf-8")
    files = scan_memory_files(memory_root)
    findings = checks.check_frontmatter_field_types(files)
    assert any(f.category == "frontmatter_type" and "not a mapping" in f.message for f in findings)


def test_check_frontmatter_field_types_clean_file_no_findings(memory_root):
    write_memory_file(memory_root, "a.md", "a", "desc", "user", "body")
    files = scan_memory_files(memory_root)
    assert checks.check_frontmatter_field_types(files) == []


def test_downstream_checks_do_not_crash_on_coerced_name(memory_root, rules):
    path = memory_root / "date-slug.md"
    path.write_text("---\nname: 2026-01-01\ndescription: a valid description here\nmetadata:\n  type: user\n---\nbody\n",
                     encoding="utf-8")
    files = scan_memory_files(memory_root)
    # must not raise TypeError/AttributeError
    checks.check_slug_hygiene(files, rules)
    checks.check_description_quality(files, rules)


def test_downstream_checks_do_not_crash_on_non_dict_metadata(memory_root, rules):
    path = memory_root / "bad-metadata.md"
    path.write_text("---\nname: a\ndescription: a valid description here\nmetadata: sometext\n---\nbody\n",
                     encoding="utf-8")
    files = scan_memory_files(memory_root)
    # must not raise AttributeError
    checks.check_valid_type(files, rules)
    checks.check_staleness(files, rules)
    checks.check_why_how_structure(files, rules)


def test_check_why_how_structure_missing(memory_root, rules):
    write_memory_file(memory_root, "a.md", "a", "desc", "project", "just a fact, no structure")
    files = scan_memory_files(memory_root)
    findings = checks.check_why_how_structure(files, rules)
    assert len(findings) == 1
    assert "Why" in findings[0].message and "How to apply" in findings[0].message


def test_check_why_how_structure_present(memory_root, rules):
    write_memory_file(memory_root, "a.md", "a", "desc", "project",
                       "the rule\n\n**Why:** reasoning\n\n**How to apply:** always")
    files = scan_memory_files(memory_root)
    findings = checks.check_why_how_structure(files, rules)
    assert findings == []


def test_check_why_how_structure_skips_user_and_reference(memory_root, rules):
    write_memory_file(memory_root, "a.md", "a", "desc", "user", "no why how here")
    write_memory_file(memory_root, "b.md", "b", "desc", "reference", "no why how here")
    files = scan_memory_files(memory_root)
    assert checks.check_why_how_structure(files, rules) == []


def test_check_description_quality_too_short(memory_root, rules):
    write_memory_file(memory_root, "a.md", "a", "short", "user", "body")
    files = scan_memory_files(memory_root)
    findings = checks.check_description_quality(files, rules)
    assert len(findings) == 1


def test_check_duplicates_merge_candidate(memory_root, rules):
    body = "identical content " * 30
    write_memory_file(memory_root, "a.md", "a", "desc a long enough", "user", body)
    write_memory_file(memory_root, "b.md", "b", "desc b long enough", "user", body)
    files = scan_memory_files(memory_root)
    findings = checks.check_duplicates(files, rules)
    assert any("merge candidate" in f.message for f in findings)


def test_check_duplicates_respects_type_boundary(memory_root, rules):
    body = "identical content " * 30
    write_memory_file(memory_root, "a.md", "a", "desc a long enough", "user", body)
    write_memory_file(memory_root, "b.md", "b", "desc b long enough", "project", body)
    files = scan_memory_files(memory_root)
    findings = checks.check_duplicates(files, rules)
    assert findings == []


def test_check_duplicates_disabled(memory_root, rules):
    rules["duplicate_detection"]["enabled"] = False
    body = "identical content " * 30
    write_memory_file(memory_root, "a.md", "a", "desc a long enough", "user", body)
    write_memory_file(memory_root, "b.md", "b", "desc b long enough", "user", body)
    files = scan_memory_files(memory_root)
    assert checks.check_duplicates(files, rules) == []


def test_check_staleness_probably_dead(memory_root, rules):
    old_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
    write_memory_file(memory_root, "a.md", "a", "desc a long enough", "project",
                       f"decision made on {old_date}")
    files = scan_memory_files(memory_root)
    findings = checks.check_staleness(files, rules)
    assert any(f.category == "stale" and "probably stale" in f.message for f in findings)


def test_check_staleness_invalid_calendar_date_does_not_crash(memory_root, rules):
    write_memory_file(memory_root, "a.md", "a", "desc a long enough", "project",
                       "Version bumped in build 2026-13-40 for release.")
    files = scan_memory_files(memory_root)
    findings = checks.check_staleness(files, rules)  # must not raise ValueError
    assert not any(f.category == "stale" for f in findings)


def test_check_staleness_recent_not_flagged(memory_root, rules):
    recent_date = datetime.now().strftime("%Y-%m-%d")
    write_memory_file(memory_root, "a.md", "a", "desc a long enough", "project",
                       f"decision made on {recent_date}")
    files = scan_memory_files(memory_root)
    findings = checks.check_staleness(files, rules)
    assert not any(f.category == "stale" for f in findings)


def test_check_index_health_long_lines(memory_root, rules):
    long_line = "- [Title](file.md) — " + ("x" * 200)
    write_index(memory_root, [long_line])
    _, lines = parse_index(memory_root)
    findings = checks.check_index_health(memory_root, lines, rules)
    assert any(f.category == "index_line_length" for f in findings)


def test_check_index_health_critical_size(memory_root, rules):
    lines = [f"- [T{i}](f{i}.md) — hook" for i in range(210)]
    write_index(memory_root, lines)
    _, index_lines = parse_index(memory_root)
    findings = checks.check_index_health(memory_root, index_lines, rules)
    assert any(f.category == "index_size" and f.severity == "critical" for f in findings)


def test_check_file_length(memory_root, rules):
    long_body = "\n".join(f"line {i}" for i in range(200))
    write_memory_file(memory_root, "a.md", "a", "desc a long enough", "user", long_body)
    files = scan_memory_files(memory_root)
    findings = checks.check_file_length(files, rules)
    assert len(findings) == 1


def test_check_duplicate_slugs(memory_root):
    write_memory_file(memory_root, "a.md", "same-slug", "desc a", "user", "content A")
    write_memory_file(memory_root, "b.md", "same-slug", "desc b", "user", "content B different")
    files = scan_memory_files(memory_root)
    findings = checks.check_duplicate_slugs(files)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_check_duplicate_slugs_same_content_not_flagged(memory_root):
    write_memory_file(memory_root, "a.md", "same-slug", "desc a", "user", "identical content")
    write_memory_file(memory_root, "b.md", "same-slug", "desc b", "user", "identical content")
    files = scan_memory_files(memory_root)
    assert checks.check_duplicate_slugs(files) == []


def test_compliance_score_no_findings_is_100():
    assert checks.compliance_score([], total_files=5) == 100.0


def test_compliance_score_zero_files_is_100():
    assert checks.compliance_score([checks.Finding("critical", "x", "y")], total_files=0) == 100.0


def test_compliance_score_decreases_with_severity():
    low = checks.compliance_score([checks.Finding("info", "x", "y")], total_files=1)
    high = checks.compliance_score([checks.Finding("critical", "x", "y")], total_files=1)
    assert high < low


def test_run_all_checks_smoke(memory_root, rules):
    write_memory_file(memory_root, "a.md", "a", "a well described memory entry", "project",
                       "the rule\n\n**Why:** reasoning\n\n**How to apply:** always")
    write_index(memory_root, ["- [A](a.md) — hook"])
    files = scan_memory_files(memory_root)
    entries, lines = parse_index(memory_root)
    findings = checks.run_all_checks(memory_root, files, entries, lines, rules)
    assert findings == []
