"""Preview apply_safe_fixes changes on a disposable copy of an area's root,
so the real impact can be inspected — and diffed — before anything real is
touched."""
import difflib
import shutil
from pathlib import Path


def create_dry_run_copy(area_root: Path, staging_dir: Path) -> Path:
    """Copies area_root into staging_dir, replacing any previous dry-run
    copy at that path so repeated runs don't accumulate stale copies."""
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
