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


def create_snapshot(memory_root: Path, backup_dir: Path, reason: str) -> Path:
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
    return zip_path


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
