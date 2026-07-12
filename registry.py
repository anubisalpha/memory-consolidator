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

# Separate store, separate vocabulary: reviewer.py's decisions are about
# whether a .md file's *shape* is acceptable (custom_format/ignore) — a
# structural, per-file judgment. FindingDecision is about whether a specific
# *finding* (a near-duplicate pair, or a stale file) is actually an issue —
# a content judgment, and for duplicates the key covers a pair of files, not
# one. Conflating the two vocabularies would make "ignore" ambiguous (skip
# scanning this file entirely, vs. this one duplicate pairing isn't real).
FINDING_REGISTRY_PATH = Path(__file__).resolve().parent / "finding_review_decisions.json"

VALID_FINDING_DECISIONS = {"dismissed"}
VALID_FINDING_CATEGORIES = {"duplicate", "stale"}


def _normalize_rel_path(rel_path: str) -> str:
    """Registry keys are always POSIX (forward-slash), but a user typing a
    path by hand on Windows naturally uses backslashes (e.g. copy-pasted
    from Explorer or tab-completed in cmd.exe) — normalize so that still
    matches."""
    return rel_path.replace("\\", "/")


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
    rel_path = _normalize_rel_path(rel_path)
    raw = _load_raw()
    raw = [d for d in raw if not (d["area"] == area and d["rel_path"] == rel_path)]
    raw.append(asdict(Decision(
        area=area, rel_path=rel_path, decision=decision, note=note,
        reviewed_at=datetime.now().isoformat(timespec="seconds"),
    )))
    _save_raw(raw)


def remove_decision(area: str, rel_path: str) -> bool:
    rel_path = _normalize_rel_path(rel_path)
    raw = _load_raw()
    filtered = [d for d in raw if not (d["area"] == area and d["rel_path"] == rel_path)]
    changed = len(filtered) != len(raw)
    if changed:
        _save_raw(filtered)
    return changed


@dataclass
class FindingDecision:
    area: str
    key: str              # rel_path for 'stale'; "a.md::b.md" (sorted) for 'duplicate'
    category: str          # "duplicate" | "stale"
    decision: str          # "dismissed"
    note: str
    reviewed_at: str


def _load_finding_raw() -> list[dict]:
    if FINDING_REGISTRY_PATH.exists():
        return json.loads(FINDING_REGISTRY_PATH.read_text(encoding="utf-8")).get("decisions", [])
    return []


def _save_finding_raw(decisions: list[dict]) -> None:
    FINDING_REGISTRY_PATH.write_text(json.dumps({"decisions": decisions}, indent=2), encoding="utf-8")


def load_finding_decisions(area_name: str | None = None, category: str | None = None) -> list[FindingDecision]:
    raw = _load_finding_raw()
    decisions = [FindingDecision(**d) for d in raw]
    if area_name:
        decisions = [d for d in decisions if d.area == area_name]
    if category:
        decisions = [d for d in decisions if d.category == category]
    return decisions


def finding_decision_map(area_name: str, category: str) -> dict[str, FindingDecision]:
    """key -> FindingDecision, for the given area and category only."""
    return {d.key: d for d in load_finding_decisions(area_name, category)}


def record_finding_decision(area: str, key: str, category: str, decision: str, note: str) -> None:
    if decision not in VALID_FINDING_DECISIONS:
        raise ValueError(f"invalid decision '{decision}', must be one of {VALID_FINDING_DECISIONS}")
    if category not in VALID_FINDING_CATEGORIES:
        raise ValueError(f"invalid category '{category}', must be one of {VALID_FINDING_CATEGORIES}")
    key = _normalize_rel_path(key)
    raw = _load_finding_raw()
    raw = [d for d in raw if not (d["area"] == area and d["key"] == key and d["category"] == category)]
    raw.append(asdict(FindingDecision(
        area=area, key=key, category=category, decision=decision, note=note,
        reviewed_at=datetime.now().isoformat(timespec="seconds"),
    )))
    _save_finding_raw(raw)


def remove_finding_decision(area: str, key: str, category: str) -> bool:
    key = _normalize_rel_path(key)
    raw = _load_finding_raw()
    filtered = [d for d in raw if not (d["area"] == area and d["key"] == key and d["category"] == category)]
    changed = len(filtered) != len(raw)
    if changed:
        _save_finding_raw(filtered)
    return changed
