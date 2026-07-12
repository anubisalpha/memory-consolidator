"""Cross-area consolidation checks: find the same or near-duplicate memory
content living in more than one configured area, so a user can pick one
area as the single source of truth and retire the rest. Within-area
duplicates/slug conflicts are already covered by checks.py — this module
only looks ACROSS areas."""
from dataclasses import dataclass
from difflib import SequenceMatcher

from scanner import MemoryFile


@dataclass
class CrossAreaFinding:
    severity: str
    category: str
    message: str
    area_a: str
    ref_a: str
    area_b: str
    ref_b: str


def find_overlapping_areas(areas: list) -> list[CrossAreaFinding]:
    """One-time notice (not per-file noise) when one area's root is nested
    inside another's — e.g. a 'scoped' area covering a whole workspace that
    happens to also contain a 'full' area's dedicated memory folder. This is
    the root cause of "same file counted twice" false positives that the
    per-file dedup in find_cross_area_slug_conflicts/find_cross_area_duplicates
    silently filters out; surfacing it once explains why some files never
    show up as cross-area candidates even though they're scanned by both."""
    out = []
    for i in range(len(areas)):
        for j in range(i + 1, len(areas)):
            a, b = areas[i], areas[j]
            root_a, root_b = a.root.resolve(), b.root.resolve()
            if root_a == root_b:
                continue
            if root_b.is_relative_to(root_a):
                outer, inner = a, b
            elif root_a.is_relative_to(root_b):
                outer, inner = b, a
            else:
                continue
            out.append(CrossAreaFinding(
                "info", "overlapping_area_roots",
                f"area '{inner.name}' root is nested inside area '{outer.name}' root — "
                "files under the inner area get scanned by both, but are deduped as the "
                "same physical file rather than reported as cross-area duplicates",
                outer.name, str(outer.root), inner.name, str(inner.root),
            ))
    return out


def find_cross_area_slug_conflicts(area_files: dict[str, list[MemoryFile]]) -> list[CrossAreaFinding]:
    """Same `name:` slug used in more than one area. If content differs,
    that's two independent, drifted sources of truth for the same concept —
    exactly the fragmentation `cross-check` exists to surface."""
    by_name: dict[str, list[tuple[str, MemoryFile]]] = {}
    for area_name, files in area_files.items():
        for f in files:
            if f.parse_error:
                continue
            by_name.setdefault(f.name, []).append((area_name, f))

    out = []
    for name, entries in by_name.items():
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                area_a, fa = entries[i]
                area_b, fb = entries[j]
                if area_a == area_b:
                    continue  # within-area conflicts: checks.check_duplicate_slugs
                if fa.path.resolve() == fb.path.resolve():
                    continue  # same physical file, seen twice because area roots overlap/nest
                same_content = fa.body.strip() == fb.body.strip()
                if same_content:
                    severity, verdict = "info", "identical content — safe to keep just one"
                else:
                    severity, verdict = "critical", "DIFFERING content — these have diverged, pick one as canonical"
                out.append(CrossAreaFinding(
                    severity, "cross_area_slug_conflict",
                    f"slug '{name}' exists in both areas with {verdict}",
                    area_a, str(fa.path), area_b, str(fb.path),
                ))
    return out


def find_cross_area_duplicates(area_files: dict[str, list[MemoryFile]], rules: dict) -> list[CrossAreaFinding]:
    """Near-duplicate content across areas by body similarity, even when
    slugs differ entirely — the same information saved twice under two
    different names in two different areas. Reuses duplicate_detection's
    thresholds from rules.md so the two commands stay consistent."""
    cfg = rules.get("duplicate_detection", {})
    if not cfg.get("enabled", True):
        return []
    merge_threshold = cfg.get("merge_threshold", 0.90)
    review_threshold = cfg.get("review_threshold", 0.70)
    min_body_len = cfg.get("min_body_length_for_comparison", 20)
    compare_across_types = cfg.get("compare_across_types", False)
    max_pairwise = cfg.get("max_files_for_pairwise", 800)

    flat: list[tuple[str, MemoryFile]] = [
        (area_name, f) for area_name, files in area_files.items() for f in files if not f.parse_error
    ]
    n = len(flat)
    if n > max_pairwise:
        return [CrossAreaFinding(
            "info", "cross_area_duplicate_check_skipped",
            f"skipped: {n} files across all areas exceeds max_files_for_pairwise ({max_pairwise}) — "
            "pairwise comparison would be too slow",
            "", "", "", "",
        )]

    out = []
    for i in range(n):
        for j in range(i + 1, n):
            area_a, fa = flat[i]
            area_b, fb = flat[j]
            if area_a == area_b:
                continue  # within-area duplicates: checks.check_duplicates
            if fa.path.resolve() == fb.path.resolve():
                continue  # same physical file, seen twice because area roots overlap/nest
            if not compare_across_types and fa.mem_type != fb.mem_type:
                continue
            if len(fa.body.strip()) < min_body_len or len(fb.body.strip()) < min_body_len:
                continue
            ratio = SequenceMatcher(None, fa.body, fb.body).ratio()
            if ratio >= merge_threshold:
                out.append(CrossAreaFinding(
                    "warn", "cross_area_duplicate", f"near-identical content (ratio={ratio:.2f}) — consolidation candidate",
                    area_a, str(fa.path), area_b, str(fb.path),
                ))
            elif ratio >= review_threshold:
                out.append(CrossAreaFinding(
                    "info", "cross_area_duplicate", f"overlapping content (ratio={ratio:.2f}) — review",
                    area_a, str(fa.path), area_b, str(fb.path),
                ))
    return out
