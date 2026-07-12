from config import ResolvedArea
from crosscheck import find_cross_area_duplicates, find_cross_area_slug_conflicts, find_overlapping_areas
from scanner import scan_memory_files

from .conftest import DEFAULT_RULES, write_memory_file


def test_slug_conflict_identical_content_is_info(tmp_path):
    area_a = tmp_path / "a"
    area_b = tmp_path / "b"
    area_a.mkdir()
    area_b.mkdir()
    write_memory_file(area_a, "x.md", "shared-slug", "desc", "user", "identical body content")
    write_memory_file(area_b, "x.md", "shared-slug", "desc", "user", "identical body content")

    area_files = {"a": scan_memory_files(area_a), "b": scan_memory_files(area_b)}
    findings = find_cross_area_slug_conflicts(area_files)

    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert "identical content" in findings[0].message


def test_slug_conflict_differing_content_is_critical(tmp_path):
    area_a = tmp_path / "a"
    area_b = tmp_path / "b"
    area_a.mkdir()
    area_b.mkdir()
    write_memory_file(area_a, "x.md", "shared-slug", "desc", "user", "version one of the content")
    write_memory_file(area_b, "x.md", "shared-slug", "desc", "user", "a totally different version two")

    area_files = {"a": scan_memory_files(area_a), "b": scan_memory_files(area_b)}
    findings = find_cross_area_slug_conflicts(area_files)

    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert "DIFFERING content" in findings[0].message
    assert findings[0].area_a == "a"
    assert findings[0].area_b == "b"


def test_slug_conflict_within_same_area_not_flagged(tmp_path):
    area_a = tmp_path / "a"
    area_a.mkdir()
    write_memory_file(area_a, "x.md", "same-slug", "desc", "user", "body")
    area_files = {"a": scan_memory_files(area_a)}
    assert find_cross_area_slug_conflicts(area_files) == []


def test_slug_conflict_unique_slugs_not_flagged(tmp_path):
    area_a = tmp_path / "a"
    area_b = tmp_path / "b"
    area_a.mkdir()
    area_b.mkdir()
    write_memory_file(area_a, "x.md", "slug-one", "desc", "user", "body one")
    write_memory_file(area_b, "y.md", "slug-two", "desc", "user", "body two")

    area_files = {"a": scan_memory_files(area_a), "b": scan_memory_files(area_b)}
    assert find_cross_area_slug_conflicts(area_files) == []


def test_cross_area_duplicates_flags_near_identical_content(tmp_path):
    area_a = tmp_path / "a"
    area_b = tmp_path / "b"
    area_a.mkdir()
    area_b.mkdir()
    body = "identical repeated content " * 10
    write_memory_file(area_a, "alpha.md", "alpha", "desc a long enough", "user", body)
    write_memory_file(area_b, "beta.md", "beta", "desc b long enough", "user", body)

    area_files = {"a": scan_memory_files(area_a), "b": scan_memory_files(area_b)}
    findings = find_cross_area_duplicates(area_files, DEFAULT_RULES)

    assert any(f.category == "cross_area_duplicate" and "consolidation candidate" in f.message for f in findings)


def test_cross_area_duplicates_not_flagged_within_same_area(tmp_path):
    area_a = tmp_path / "a"
    area_a.mkdir()
    body = "identical repeated content " * 10
    write_memory_file(area_a, "alpha.md", "alpha", "desc a long enough", "user", body)
    write_memory_file(area_a, "beta.md", "beta", "desc b long enough", "user", body)

    area_files = {"a": scan_memory_files(area_a)}
    findings = find_cross_area_duplicates(area_files, DEFAULT_RULES)
    assert findings == []  # within-area duplicates are checks.check_duplicates' job


def test_cross_area_duplicates_disabled(tmp_path):
    import copy
    rules = copy.deepcopy(DEFAULT_RULES)
    rules["duplicate_detection"]["enabled"] = False

    area_a = tmp_path / "a"
    area_b = tmp_path / "b"
    area_a.mkdir()
    area_b.mkdir()
    body = "identical repeated content " * 10
    write_memory_file(area_a, "alpha.md", "alpha", "desc a long enough", "user", body)
    write_memory_file(area_b, "beta.md", "beta", "desc b long enough", "user", body)

    area_files = {"a": scan_memory_files(area_a), "b": scan_memory_files(area_b)}
    assert find_cross_area_duplicates(area_files, rules) == []


def test_cross_area_duplicates_skips_trivially_short_bodies(tmp_path):
    area_a = tmp_path / "a"
    area_b = tmp_path / "b"
    area_a.mkdir()
    area_b.mkdir()
    write_memory_file(area_a, "alpha.md", "alpha", "desc a long enough", "user", "")
    write_memory_file(area_b, "beta.md", "beta", "desc b long enough", "user", "")

    area_files = {"a": scan_memory_files(area_a), "b": scan_memory_files(area_b)}
    assert find_cross_area_duplicates(area_files, DEFAULT_RULES) == []


def test_cross_area_duplicates_respects_max_pairwise(tmp_path):
    import copy
    rules = copy.deepcopy(DEFAULT_RULES)
    rules["duplicate_detection"]["max_files_for_pairwise"] = 1

    area_a = tmp_path / "a"
    area_b = tmp_path / "b"
    area_a.mkdir()
    area_b.mkdir()
    write_memory_file(area_a, "alpha.md", "alpha", "desc a long enough", "user", "some content here")
    write_memory_file(area_b, "beta.md", "beta", "desc b long enough", "user", "some content here")

    area_files = {"a": scan_memory_files(area_a), "b": scan_memory_files(area_b)}
    findings = find_cross_area_duplicates(area_files, rules)
    assert len(findings) == 1
    assert findings[0].category == "cross_area_duplicate_check_skipped"


# ---- find_overlapping_areas ----

def test_find_overlapping_areas_detects_nested_roots(tmp_path):
    outer_root = tmp_path / "outer"
    inner_root = outer_root / "sub" / "memory"
    inner_root.mkdir(parents=True)

    areas = [ResolvedArea("outer", outer_root, "scoped"), ResolvedArea("inner", inner_root, "full")]
    findings = find_overlapping_areas(areas)

    assert len(findings) == 1
    assert findings[0].category == "overlapping_area_roots"
    assert findings[0].area_a == "outer"
    assert findings[0].area_b == "inner"


def test_find_overlapping_areas_no_overlap(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    areas = [ResolvedArea("a", root_a, "full"), ResolvedArea("b", root_b, "full")]
    assert find_overlapping_areas(areas) == []


def test_find_overlapping_areas_detects_regardless_of_order(tmp_path):
    outer_root = tmp_path / "outer"
    inner_root = outer_root / "sub" / "memory"
    inner_root.mkdir(parents=True)

    # inner listed first this time
    areas = [ResolvedArea("inner", inner_root, "full"), ResolvedArea("outer", outer_root, "scoped")]
    findings = find_overlapping_areas(areas)
    assert len(findings) == 1
    assert findings[0].area_a == "outer"
    assert findings[0].area_b == "inner"


# ---- overlapping areas produce no duplicate/slug-conflict noise ----

def test_overlapping_areas_same_physical_file_not_flagged_as_slug_conflict(tmp_path):
    outer_root = tmp_path / "outer"
    inner_root = outer_root / "sub" / "memory"
    inner_root.mkdir(parents=True)
    write_memory_file(inner_root, "shared.md", "shared-slug", "desc", "user", "body")

    # "outer" area's scoped scan would pick up the same physical file that
    # "inner" (a 'full' area nested inside it) already owns
    area_files = {
        "outer": scan_memory_files(inner_root),  # same files, simulating the overlap
        "inner": scan_memory_files(inner_root),
    }
    findings = find_cross_area_slug_conflicts(area_files)
    assert findings == []  # same resolved path on both sides -> deduped, not a real conflict
