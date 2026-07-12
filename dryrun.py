"""Preview apply_safe_fixes changes on a disposable copy of an area's root,
so the real impact can be inspected — and diffed — before anything real is
touched."""
import difflib
import shutil
from pathlib import Path


def create_dry_run_copy(area_root: Path, staging_dir: Path) -> Path:
    """Copies area_root into staging_dir, replacing any previous dry-run
    copy at that path so repeated runs don't accumulate stale copies.

    Defense in depth: refuses if staging_dir is inside area_root. The
    normal caller (main.py's cmd_dry_run) already checks this via
    ensure_backup_safe_for_area before calling here, but this function is
    reusable and shouldn't rely solely on that — copying a directory into
    a subdirectory of itself recurses until the OS refuses (confirmed: hits
    Windows' path-length limit after a few hundred levels of self-nesting)."""
    area_root = area_root.resolve()
    staging_dir = staging_dir.resolve()
    if staging_dir == area_root or staging_dir.is_relative_to(area_root):
        raise ValueError(
            f"staging_dir ({staging_dir}) is inside area_root ({area_root}) — "
            "would recurse copying the folder into itself"
        )

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    shutil.copytree(area_root, staging_dir)
    return staging_dir


def diff_memory_index(original_root: Path, modified_root: Path) -> list[str]:
    """Unified diff of MEMORY.md between the untouched original and the
    fixed-up dry-run copy — the concrete, reviewable result of applying
    auto-fix, without having applied it for real."""
    orig_path = original_root / "MEMORY.md"
    mod_path = modified_root / "MEMORY.md"
    orig_lines = orig_path.read_text(encoding="utf-8").splitlines(keepends=True) if orig_path.exists() else []
    mod_lines = mod_path.read_text(encoding="utf-8").splitlines(keepends=True) if mod_path.exists() else []
    return list(difflib.unified_diff(
        orig_lines, mod_lines, fromfile="MEMORY.md (before)", tofile="MEMORY.md (after)",
    ))


def diff_changed_files(original_root: Path, modified_root: Path) -> list[tuple[str, list[str]]]:
    """Unified diffs for every individual memory file (excluding MEMORY.md,
    covered separately by diff_memory_index) whose content differs between
    original_root and modified_root. Needed for full_auto's two fixes
    (mark_stale_files, merge_exact_duplicates) — unlike apply_safe_fixes,
    those rewrite individual file bodies rather than only MEMORY.md, so
    dry-run has to diff more than the index to show their real impact."""
    out = []
    for mod_path in sorted(modified_root.rglob("*.md")):
        if mod_path.name == "MEMORY.md":
            continue
        rel = mod_path.relative_to(modified_root)
        orig_path = original_root / rel
        mod_text = mod_path.read_text(encoding="utf-8", errors="replace")
        orig_text = orig_path.read_text(encoding="utf-8", errors="replace") if orig_path.exists() else ""
        if mod_text == orig_text:
            continue
        diff = list(difflib.unified_diff(
            orig_text.splitlines(keepends=True), mod_text.splitlines(keepends=True),
            fromfile=f"{rel.as_posix()} (before)", tofile=f"{rel.as_posix()} (after)",
        ))
        out.append((rel.as_posix(), diff))
    return out
