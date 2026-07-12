"""Persistent, user-approved decisions about non-canonical .md files.

Tracked in git (unlike config.local.json) because these are real judgment
calls about the workspace's content, not machine-specific paths — they
should travel with the repo so a second machine doesn't have to re-review
the same files.
"""
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent / "review_decisions.json"

VALID_DECISIONS = {"custom_format", "ignore"}


@dataclass
class Decision:
    area: str
    rel_path: str       # posix path relative to the area's root
    decision: str        # "custom_format" | "ignore"
    note: str
    reviewed_at: str


def _load_raw() -> list[dict]:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8")).get("decisions", [])
    return []


def _save_raw(decisions: list[dict]) -> None:
    REGISTRY_PATH.write_text(json.dumps({"decisions": decisions}, indent=2), encoding="utf-8")


def load_decisions(area_name: str | None = None) -> list[Decision]:
    raw = _load_raw()
    decisions = [Decision(**d) for d in raw]
    if area_name:
        decisions = [d for d in decisions if d.area == area_name]
    return decisions


def decision_map(area_name: str) -> dict[str, Decision]:
    """rel_path -> Decision, for the given area only."""
    return {d.rel_path: d for d in load_decisions(area_name)}


def record_decision(area: str, rel_path: str, decision: str, note: str) -> None:
    if decision not in VALID_DECISIONS:
        raise ValueError(f"invalid decision '{decision}', must be one of {VALID_DECISIONS}")
    raw = _load_raw()
    raw = [d for d in raw if not (d["area"] == area and d["rel_path"] == rel_path)]
    raw.append(asdict(Decision(
        area=area, rel_path=rel_path, decision=decision, note=note,
        reviewed_at=datetime.now().isoformat(timespec="seconds"),
    )))
    _save_raw(raw)


def remove_decision(area: str, rel_path: str) -> bool:
    raw = _load_raw()
    filtered = [d for d in raw if not (d["area"] == area and d["rel_path"] == rel_path)]
    changed = len(filtered) != len(raw)
    if changed:
        _save_raw(filtered)
    return changed
