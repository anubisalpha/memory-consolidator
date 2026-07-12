"""Locate and persist the memory root folder, and load rules.md."""
import json
import re
import sys
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parent
RULES_PATH = PROJECT_DIR / "rules.md"
CONFIG_PATH = PROJECT_DIR / "config.local.json"

DEFAULT_GUESS_CANDIDATES = [
    Path.home() / ".claude" / "projects" / "C--Users-marca-claudecore" / "memory",
    PROJECT_DIR.parent.parent / "memory",
]


def load_rules() -> dict:
    text = RULES_PATH.read_text(encoding="utf-8")
    match = re.search(r"```yaml\n(.*?)\n```", text, re.DOTALL)
    if not match:
        raise ValueError(f"No yaml block found in {RULES_PATH}")
    return yaml.safe_load(match.group(1))


def _resolve_relative(base: Path, rules: dict) -> dict:
    rules["paths"]["backup_dir"] = str((base / rules["paths"]["backup_dir"]).resolve())
    rules["paths"]["report_dir"] = str((base / rules["paths"]["report_dir"]).resolve())
    return rules


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


def resolve_memory_root(rules: dict, non_interactive: bool = False) -> Path:
    """Determine memory_root: rules.md override > saved local config > guess+confirm."""
    if rules["paths"].get("memory_root"):
        return Path(rules["paths"]["memory_root"]).expanduser().resolve()

    local_cfg = load_local_config()
    if "memory_root" in local_cfg:
        path = Path(local_cfg["memory_root"])
        if path.exists():
            return path
        print(f"Saved memory_root no longer exists: {path}")

    guess = guess_memory_root()
    if guess is None:
        if non_interactive:
            raise FileNotFoundError("Could not auto-detect memory_root and none configured.")
        entered = input("Could not auto-detect memory folder. Enter path: ").strip()
        path = Path(entered).expanduser().resolve()
    else:
        if non_interactive:
            path = guess
        else:
            answer = input(f"Use memory folder: {guess} ? [Y/n/path]: ").strip()
            if answer == "" or answer.lower() == "y":
                path = guess
            elif answer.lower() == "n":
                entered = input("Enter path: ").strip()
                path = Path(entered).expanduser().resolve()
            else:
                path = Path(answer).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(f"Memory folder does not exist: {path}")

    local_cfg["memory_root"] = str(path)
    save_local_config(local_cfg)
    return path


def get_config(non_interactive: bool = False) -> dict:
    rules = load_rules()
    memory_root = resolve_memory_root(rules, non_interactive=non_interactive)
    rules = _resolve_relative(PROJECT_DIR, rules)

    backup_dir = Path(rules["paths"]["backup_dir"])
    report_dir = Path(rules["paths"]["report_dir"])

    try:
        memory_root.relative_to(backup_dir)
        raise ValueError("backup_dir cannot be inside memory_root")
    except ValueError:
        pass
    if str(backup_dir).startswith(str(memory_root)):
        print("ERROR: backup_dir resolves inside memory_root — refusing to continue.", file=sys.stderr)
        sys.exit(1)

    backup_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    rules["memory_root"] = str(memory_root)
    return rules
