"""Snapshot/rollback for memory_root, isolated from memory_root itself."""
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


def _manifest_path(backup_dir: Path) -> Path:
    return backup_dir / "manifest.json"


def _load_manifest(backup_dir: Path) -> list[dict]:
    p = _manifest_path(backup_dir)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return []


def _save_manifest(backup_dir: Path, manifest: list[dict]) -> None:
    _manifest_path(backup_dir).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def create_snapshot(memory_root: Path, backup_dir: Path, reason: str, keep_last_n: int | None = None) -> Path:
    base_timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    timestamp = base_timestamp
    suffix = 1
    while (backup_dir / f"{timestamp}.zip").exists():
        suffix += 1
        timestamp = f"{base_timestamp}-{suffix}"
    zip_path = backup_dir / f"{timestamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in memory_root.rglob("*"):
            if f.is_file():
                # as_posix(): zip archives always use forward slashes internally
                # regardless of platform, so a snapshot taken on Windows can be
                # correctly restored on macOS/Linux and vice versa.
                zf.write(f, arcname=f.relative_to(memory_root).as_posix())

    manifest = _load_manifest(backup_dir)
    manifest.append({
        "timestamp": timestamp,
        "zip": zip_path.name,
        "reason": reason,
        "memory_root": str(memory_root),
    })
    _save_manifest(backup_dir, manifest)
    if keep_last_n is not None:
        _prune_old_snapshots(backup_dir, str(memory_root), keep_last_n)
    return zip_path


def create_targeted_snapshot(file_paths: list[Path], root_for_relnames: Path,
                              backup_dir: Path, reason: str, keep_last_n: int | None = None) -> Path:
    """Like create_snapshot but backs up only specific files, not the whole
    tree under root_for_relnames. Confirmed necessary: a 'scoped' area's
    root is a whole project/workspace (potentially many GB, node_modules
    etc.) — a full create_snapshot() there before every write hung
    indefinitely in practice. Callers that only ever touch a small, known
    set of files (like resolve-conflicts) should use this instead."""
    base_timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    timestamp = base_timestamp
    suffix = 1
    while (backup_dir / f"{timestamp}.zip").exists():
        suffix += 1
        timestamp = f"{base_timestamp}-{suffix}"
    zip_path = backup_dir / f"{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in file_paths:
            if f.exists():
                zf.write(f, arcname=f.relative_to(root_for_relnames).as_posix())

    manifest = _load_manifest(backup_dir)
    manifest.append({
        "timestamp": timestamp,
        "zip": zip_path.name,
        "reason": reason,
        "memory_root": str(root_for_relnames),
        "targeted_files": [str(f) for f in file_paths],
    })
    _save_manifest(backup_dir, manifest)
    if keep_last_n is not None:
        _prune_old_snapshots(backup_dir, str(root_for_relnames), keep_last_n)
    return zip_path


def _prune_old_snapshots(backup_dir: Path, memory_root: str, keep_last_n: int) -> None:
    """Deletes the oldest snapshot zips (and their manifest entries) for this
    specific memory_root, keeping only the newest keep_last_n. Scoped by
    memory_root (not global) because backup_dir is shared across all
    configured areas — pruning globally would let one area's frequent
    snapshots evict another area's only backup. Mirrors report.py's
    _prune_old_reports, which prunes per-area via report_name_prefix."""
    manifest = _load_manifest(backup_dir)
    area_entries = [m for m in manifest if m.get("memory_root") == memory_root]
    excess = len(area_entries) - keep_last_n
    if excess <= 0:
        return
    # manifest entries are appended in creation order, so the oldest for
    # this area are simply the earliest matching entries
    to_remove = area_entries[:excess]
    remove_zips = {e["zip"] for e in to_remove}
    for entry in to_remove:
        zip_path = backup_dir / entry["zip"]
        if zip_path.exists():
            zip_path.unlink()
    manifest = [m for m in manifest if m.get("zip") not in remove_zips]
    _save_manifest(backup_dir, manifest)


def list_snapshots(backup_dir: Path) -> list[dict]:
    return _load_manifest(backup_dir)


def rollback(memory_root: Path, backup_dir: Path, which: str = "latest", force: bool = False) -> Path:
    manifest = _load_manifest(backup_dir)
    if not manifest:
        raise FileNotFoundError("No snapshots recorded in manifest.json")

    if which == "latest":
        entry = manifest[-1]
    else:
        matches = [m for m in manifest if m["timestamp"] == which]
        if not matches:
            raise FileNotFoundError(f"No snapshot with timestamp {which}")
        entry = matches[0]

    zip_path = backup_dir / entry["zip"]
    if not zip_path.exists():
        raise FileNotFoundError(f"Snapshot zip missing: {zip_path}")

    if not force:
        confirm = input(f"This will overwrite {memory_root} with snapshot {entry['timestamp']}. Continue? [y/N]: ")
        if confirm.strip().lower() != "y":
            raise RuntimeError("Rollback cancelled by user")

    # Extract to a temp dir first, then swap, so a bad zip can't half-overwrite memory_root
    tmp_dir = backup_dir / f"_restore_tmp_{entry['timestamp']}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmp_dir)

    for item in memory_root.iterdir():
        if item.is_file():
            item.unlink()
        else:
            shutil.rmtree(item)
    for item in tmp_dir.iterdir():
        shutil.move(str(item), str(memory_root / item.name))
    shutil.rmtree(tmp_dir)

    return zip_path
