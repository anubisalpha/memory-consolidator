from pathlib import Path

import pytest

import config
from config import (
    ResolvedArea,
    backup_dir_conflicts_with_area,
    derive_workspace_root,
    ensure_backup_safe_for_area,
    get_config,
    resolve_areas,
)


def test_backup_dir_conflicts_when_nested(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    backup_dir = root / "sub" / "backups"
    area = ResolvedArea("proj", root, "scoped")
    assert backup_dir_conflicts_with_area(area, backup_dir) is True


def test_backup_dir_conflicts_when_equal(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    area = ResolvedArea("proj", root, "scoped")
    assert backup_dir_conflicts_with_area(area, root) is True


def test_backup_dir_no_conflict_when_sibling(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    backup_dir = tmp_path / "elsewhere" / "backups"
    area = ResolvedArea("proj", root, "scoped")
    assert backup_dir_conflicts_with_area(area, backup_dir) is False


def test_ensure_backup_safe_for_area_exits_on_conflict(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    backup_dir = root / "backups"
    area = ResolvedArea("proj", root, "scoped")
    with pytest.raises(SystemExit):
        ensure_backup_safe_for_area(area, backup_dir)


def test_ensure_backup_safe_for_area_passes_when_safe(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    backup_dir = tmp_path / "elsewhere"
    area = ResolvedArea("proj", root, "scoped")
    ensure_backup_safe_for_area(area, backup_dir)  # should not raise


# ---- derive_workspace_root ----

def test_derive_workspace_root_single_scoped_area(tmp_path):
    scoped_root = tmp_path / "project_a"
    full_root = tmp_path / "elsewhere" / "memory"
    scoped_root.mkdir(parents=True)
    full_root.mkdir(parents=True)
    areas = [ResolvedArea("a", scoped_root, "scoped"), ResolvedArea("b", full_root, "full")]

    # the deep 'full' area must NOT drag the result up to a shared ancestor —
    # only the single scoped area's own root is used
    assert derive_workspace_root(areas) == scoped_root


def test_derive_workspace_root_no_scoped_areas_returns_none(tmp_path):
    root = tmp_path / "only"
    root.mkdir()
    assert derive_workspace_root([ResolvedArea("only", root, "full")]) is None


def test_derive_workspace_root_multiple_scoped_areas_ambiguous_returns_none(tmp_path):
    root_a = tmp_path / "project_a"
    root_b = tmp_path / "project_b"
    root_a.mkdir()
    root_b.mkdir()
    areas = [ResolvedArea("a", root_a, "scoped"), ResolvedArea("b", root_b, "scoped")]
    assert derive_workspace_root(areas) is None


def test_derive_workspace_root_empty_areas_returns_none():
    assert derive_workspace_root([]) is None


# ---- get_config wiring of external_scan.workspace_root ----

RULES_TEMPLATE = """# Rules

```yaml
paths:
  backup_dir: "{backup_dir}"
  report_dir: "{report_dir}"

areas:
  - name: a
    root: "{root_a}"
    mode: scoped
  - name: b
    root: "{root_b}"
    mode: full

memory_file_patterns:
  - "**/memory/**/*.md"

duplicate_detection:
  enabled: true
  merge_threshold: 0.9
  review_threshold: 0.7
  compare_across_types: false
  max_files_for_pairwise: 800

staleness:
  enabled: true
  likely_stale_days: 90
  probably_dead_days: 180
  mtime_fallback_days: 365

index_health:
  max_line_length: 150
  warn_line_count: 160
  critical_line_count: 200

file_health:
  max_body_lines: 150
  require_frontmatter: true

spec_conformance:
  require_why_how_for_feedback_and_project: true
  require_valid_type: true
  require_kebab_case_slug: true

description_quality:
  min_length: 15

code_derivable_check:
  enabled: false
  code_line_ratio_threshold: 0.5

external_scan:
  enabled: true
  workspace_root: {workspace_root}

automation:
  mode: "report_only"
  auto_fix_missing_index_entries: false
  auto_fix_broken_links: false
  require_backup_before_apply: true

reporting:
  keep_last_n_reports: 20
```
"""


def _write_scratch_rules(tmp_path, root_a, root_b, workspace_root_yaml="null"):
    rules_path = tmp_path / "rules.md"
    rules_path.write_text(RULES_TEMPLATE.format(
        backup_dir=(tmp_path / "backups").as_posix(),
        report_dir=(tmp_path / "reports").as_posix(),
        root_a=root_a.as_posix(),
        root_b=root_b.as_posix(),
        workspace_root=workspace_root_yaml,
    ), encoding="utf-8")
    return rules_path


def test_get_config_derives_workspace_root_when_unset(tmp_path, monkeypatch):
    # area "a" (scoped) and "b" (full) in RULES_TEMPLATE -> exactly one
    # scoped area, so its own root is used directly (see
    # derive_workspace_root's deliberately-narrow rule).
    root_a = tmp_path / "workspace" / "project_a"
    root_b = tmp_path / "elsewhere" / "project_b" / "memory"
    root_a.mkdir(parents=True)
    root_b.mkdir(parents=True)

    rules_path = _write_scratch_rules(tmp_path, root_a, root_b)
    monkeypatch.setattr(config, "RULES_PATH", rules_path)
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.local.json")

    rules = get_config(non_interactive=True)
    assert rules["external_scan"]["workspace_root"] == str(root_a)


def test_get_config_respects_explicit_workspace_root_override(tmp_path, monkeypatch):
    root_a = tmp_path / "workspace" / "project_a"
    root_b = tmp_path / "workspace" / "project_b" / "memory"
    root_a.mkdir(parents=True)
    root_b.mkdir(parents=True)
    override_dir = tmp_path / "custom_override"
    override_dir.mkdir()

    rules_path = _write_scratch_rules(tmp_path, root_a, root_b,
                                       workspace_root_yaml=f'"{override_dir.as_posix()}"')
    monkeypatch.setattr(config, "RULES_PATH", rules_path)
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.local.json")

    rules = get_config(non_interactive=True)
    assert Path(rules["external_scan"]["workspace_root"]) == override_dir


# ---- duplicate area names ----

def test_resolve_areas_rejects_duplicate_names(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    rules = {
        "areas": [
            {"name": "dup", "root": str(root_a), "mode": "full"},
            {"name": "dup", "root": str(root_b), "mode": "scoped"},
        ]
    }
    with pytest.raises(ValueError, match="duplicate area name"):
        resolve_areas(rules, non_interactive=True)


def test_resolve_areas_allows_unique_names(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    rules = {
        "areas": [
            {"name": "one", "root": str(root_a), "mode": "full"},
            {"name": "two", "root": str(root_b), "mode": "scoped"},
        ]
    }
    areas = resolve_areas(rules, non_interactive=True)
    assert [a.name for a in areas] == ["one", "two"]
