"""Load rules.md and resolve each configured area's root folder."""
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parent
RULES_PATH = PROJECT_DIR / "rules.md"
CONFIG_PATH = PROJECT_DIR / "config.local.json"


def _claude_project_slug(path: Path) -> str:
    """Best-effort reconstruction of Claude Code's session-storage folder
    naming convention: a project's absolute path with separators (and the
    drive letter's colon, on Windows) replaced by dashes. Works for any
    user/home directory on any OS — this is only ever used as a guess with
    an interactive prompt as the fallback, so it doesn't need to be exact."""
    resolved = str(path.resolve())
    return resolved.replace(":", "").replace("\\", "-").replace("/", "-")


def _default_guess_candidates() -> list[Path]:
    claudecore_root = PROJECT_DIR.parent.parent  # projects/memory-consolidator -> claudecore
    slug = _claude_project_slug(claudecore_root)
    return [
        Path.home() / ".claude" / "projects" / slug / "memory",
        claudecore_root / "memory",
    ]


@dataclass
class ResolvedArea:
    name: str
    root: Path
    mode: str  # "full" | "scoped"


def load_rules() -> dict:
    text = RULES_PATH.read_text(encoding="utf-8")
    match = re.search(r"```yaml\n(.*?)\n```", text, re.DOTALL)
    if not match:
        raise ValueError(f"No yaml block found in {RULES_PATH}")
    return yaml.safe_load(match.group(1))


def load_local_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def save_local_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def guess_memory_root() -> Path | None:
    for candidate in _default_guess_candidates():
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _resolve_null_root(area_name: str, non_interactive: bool) -> Path:
    """For areas with root: null — auto-detect/prompt/confirm, same as the
    original single-memory-root behavior, keyed by area name in config.local.json
    so multiple null-root areas don't collide."""
    local_cfg = load_local_config()
    cache_key = f"area_root::{area_name}"
    if cache_key in local_cfg:
        path = Path(local_cfg[cache_key])
        if path.exists():
            return path
        print(f"Saved root for area '{area_name}' no longer exists: {path}")

    guess = guess_memory_root()
    if guess is None:
        if non_interactive:
            raise FileNotFoundError(f"Could not auto-detect root for area '{area_name}' and none configured.")
        entered = input(f"Could not auto-detect folder for area '{area_name}'. Enter path: ").strip()
        path = Path(entered).expanduser().resolve()
    else:
        if non_interactive:
            path = guess
        else:
            answer = input(f"Area '{area_name}': use folder {guess} ? [Y/n/path]: ").strip()
            if answer == "" or answer.lower() == "y":
                path = guess
            elif answer.lower() == "n":
                entered = input("Enter path: ").strip()
                path = Path(entered).expanduser().resolve()
            else:
                path = Path(answer).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(f"Area '{area_name}' folder does not exist: {path}")

    local_cfg[cache_key] = str(path)
    save_local_config(local_cfg)
    return path


def resolve_areas(rules: dict, non_interactive: bool = False) -> list[ResolvedArea]:
    areas_cfg = rules.get("areas") or []
    resolved = []
    for entry in areas_cfg:
        name = entry["name"]
        mode = entry.get("mode", "full")
        if mode not in ("full", "scoped"):
            raise ValueError(f"area '{name}': invalid mode '{mode}' (must be 'full' or 'scoped')")

        root_cfg = entry.get("root")
        if root_cfg:
            root = Path(root_cfg).expanduser().resolve()
            if not root.exists():
                raise FileNotFoundError(f"area '{name}': root does not exist: {root}")
        else:
            root = _resolve_null_root(name, non_interactive)

        resolved.append(ResolvedArea(name=name, root=root, mode=mode))
    return resolved


def derive_workspace_root(areas: list[ResolvedArea]) -> Path | None:
    """Best-effort root for `map` and external-pointer resolution, derived
    from the configured `areas` instead of a hand-maintained separate value.

    Deliberately narrow: only auto-derives when there's exactly one 'scoped'
    area, using its root directly. Taking the common ancestor across ALL
    areas is tempting but dangerous — a 'full' mode area often lives deep
    under something like ~/.claude/projects/.../memory, so its common
    ancestor with a 'scoped' area can balloon to the entire home directory,
    turning a targeted search into an accidental full-disk walk. With zero
    or multiple scoped areas there's no single unambiguous choice, so this
    returns None and callers fall back to requiring an explicit
    workspace_root override in rules.md."""
    scoped = [a for a in areas if a.mode == "scoped"]
    if len(scoped) == 1:
        return scoped[0].root
    return None


def backup_dir_conflicts_with_area(area: ResolvedArea, backup_dir: Path) -> bool:
    return backup_dir == area.root or backup_dir.is_relative_to(area.root)


def ensure_backup_safe_for_area(area: ResolvedArea, backup_dir: Path) -> None:
    """Hard-stop before any write (snapshot/rollback/auto-fix) that would
    target this specific area, if backup_dir sits inside its root — a
    snapshot could otherwise try to back up itself mid-write, and rollback's
    delete-then-restore could delete the very backup it's restoring from.
    Deliberately NOT called for every configured area up front (get_config
    used to do this and would block a --area-scoped run over an unrelated
    area's misconfiguration) — call this only for the area actually being
    written to."""
    if backup_dir_conflicts_with_area(area, backup_dir):
        print(f"ERROR: backup_dir ({backup_dir}) resolves inside area '{area.name}' root "
              f"({area.root}) — refusing to write (a snapshot/rollback here could corrupt "
              "itself mid-operation).", file=sys.stderr)
        sys.exit(1)


def get_config(non_interactive: bool = False) -> dict:
    rules = load_rules()
    areas = resolve_areas(rules, non_interactive=non_interactive)

    rules["paths"]["backup_dir"] = str((PROJECT_DIR / rules["paths"]["backup_dir"]).resolve())
    rules["paths"]["report_dir"] = str((PROJECT_DIR / rules["paths"]["report_dir"]).resolve())
    backup_dir = Path(rules["paths"]["backup_dir"])
    report_dir = Path(rules["paths"]["report_dir"])

    for area in areas:
        if backup_dir_conflicts_with_area(area, backup_dir):
            print(f"WARNING: backup_dir ({backup_dir}) is inside area '{area.name}' root "
                  f"({area.root}). Any write operation targeting this area (auto-fix, "
                  "manual snapshot, rollback) will refuse to run until this is fixed.",
                  file=sys.stderr)

    backup_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    ext_cfg = rules.get("external_scan") or {}
    if ext_cfg.get("enabled", False) and not ext_cfg.get("workspace_root"):
        derived = derive_workspace_root(areas)
        if derived:
            ext_cfg["workspace_root"] = str(derived)
    rules["external_scan"] = ext_cfg

    rules["_resolved_areas"] = areas
    return rules
