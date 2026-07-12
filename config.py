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

DEFAULT_GUESS_CANDIDATES = [
    Path.home() / ".claude" / "projects" / "C--Users-marca-claudecore" / "memory",
    PROJECT_DIR.parent.parent / "memory",
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
    for candidate in DEFAULT_GUESS_CANDIDATES:
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


def get_config(non_interactive: bool = False) -> dict:
    rules = load_rules()
    areas = resolve_areas(rules, non_interactive=non_interactive)

    rules["paths"]["backup_dir"] = str((PROJECT_DIR / rules["paths"]["backup_dir"]).resolve())
    rules["paths"]["report_dir"] = str((PROJECT_DIR / rules["paths"]["report_dir"]).resolve())
    backup_dir = Path(rules["paths"]["backup_dir"])
    report_dir = Path(rules["paths"]["report_dir"])

    for area in areas:
        backup_inside_root = str(backup_dir).startswith(str(area.root) + str(Path("/"))) \
            or str(backup_dir) == str(area.root)
        if backup_inside_root:
            if rules["automation"]["mode"] != "report_only":
                print(f"ERROR: backup_dir resolves inside area '{area.name}' root and "
                      "automation.mode writes to it — refusing to continue (a snapshot "
                      "could try to back up itself mid-write).", file=sys.stderr)
                sys.exit(1)
            print(f"WARNING: backup_dir ({backup_dir}) is inside area '{area.name}' root "
                  f"({area.root}). Harmless in report_only mode, but snapshot/rollback "
                  "would be unsafe here.", file=sys.stderr)

    backup_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    rules["_resolved_areas"] = areas
    return rules
