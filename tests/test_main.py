import argparse
import copy

import pytest

import main
import registry
from config import ResolvedArea

from .conftest import DEFAULT_RULES, write_index, write_memory_file


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    path = tmp_path / "review_decisions.json"
    monkeypatch.setattr(registry, "REGISTRY_PATH", path)
    monkeypatch.setattr(main, "load_decisions", registry.load_decisions)
    monkeypatch.setattr(main, "record_decision", registry.record_decision)
    monkeypatch.setattr(main, "remove_decision", registry.remove_decision)
    return path


def make_rules(areas: list[ResolvedArea], tmp_path, **overrides) -> dict:
    rules = copy.deepcopy(DEFAULT_RULES)
    rules["areas"] = [{"name": a.name, "root": str(a.root), "mode": a.mode} for a in areas]
    rules["memory_file_patterns"] = ["**/memory/**/*.md"]
    rules["external_scan"] = {"enabled": False}
    rules["automation"] = {"mode": "report_only"}
    rules["reporting"] = {"keep_last_n_reports": 20}
    rules["paths"] = {
        "backup_dir": str(tmp_path / "backups"),
        "report_dir": str(tmp_path / "reports"),
    }
    (tmp_path / "backups").mkdir(exist_ok=True)
    (tmp_path / "reports").mkdir(exist_ok=True)
    rules["_resolved_areas"] = areas
    rules.update(overrides)
    return rules


def ns(**kwargs) -> argparse.Namespace:
    defaults = {"non_interactive": True, "area": None}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---- _select_area ----

def test_select_area_single_no_name(tmp_path):
    areas = [ResolvedArea("only", tmp_path, "full")]
    rules = {"_resolved_areas": areas}
    assert main._select_area(rules, None).name == "only"


def test_select_area_by_name(tmp_path):
    areas = [ResolvedArea("a", tmp_path, "full"), ResolvedArea("b", tmp_path, "full")]
    rules = {"_resolved_areas": areas}
    assert main._select_area(rules, "b").name == "b"


def test_select_area_unknown_name_raises(tmp_path):
    areas = [ResolvedArea("a", tmp_path, "full")]
    rules = {"_resolved_areas": areas}
    with pytest.raises(ValueError, match="no area named"):
        main._select_area(rules, "bogus")


def test_select_area_multiple_no_name_raises(tmp_path):
    areas = [ResolvedArea("a", tmp_path, "full"), ResolvedArea("b", tmp_path, "full")]
    rules = {"_resolved_areas": areas}
    with pytest.raises(ValueError, match="pass --area"):
        main._select_area(rules, None)


def test_select_area_no_areas_raises():
    with pytest.raises(ValueError, match="no areas configured"):
        main._select_area({"_resolved_areas": []}, None)


# ---- cmd_audit ----

def test_cmd_audit_full_mode(memory_root, tmp_path, monkeypatch, capsys):
    write_memory_file(memory_root, "a.md", "a", "a valid description here", "user", "body")
    write_index(memory_root, ["- [A](a.md) — hook"])
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_audit(ns(area=None))
    out = capsys.readouterr().out
    assert "Area: main (full)" in out
    assert "Report written to:" in out
    assert list((tmp_path / "reports").glob("main_*.md"))


def test_cmd_audit_scoped_mode_skips_index_checks(tmp_path, monkeypatch, capsys):
    root = tmp_path / "project"
    mem_dir = root / "memory"
    mem_dir.mkdir(parents=True)
    write_memory_file(mem_dir, "a.md", "a", "a valid description here", "user", "body")
    area = ResolvedArea("proj", root, "scoped")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_audit(ns(area=None))
    out = capsys.readouterr().out
    assert "Area: proj (scoped)" in out
    assert "orphan" not in out  # index-shaped checks don't apply in scoped mode


def test_cmd_audit_apply_safe_fixes_adds_missing_index_entries(memory_root, tmp_path, monkeypatch, capsys):
    write_memory_file(memory_root, "orphan.md", "orphan", "an orphan memory", "user", "body")
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules(
        [area], tmp_path,
        automation={"mode": "apply_safe_fixes", "auto_fix_missing_index_entries": True,
                    "auto_fix_broken_links": False},
    )
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_audit(ns(area=None))
    out = capsys.readouterr().out
    assert "Applied 1 fix(es)" in out
    assert "Re-audit after fixes" in out

    from scanner import parse_index
    entries, _ = parse_index(memory_root)
    assert {e.href for e in entries} == {"orphan.md"}


def test_cmd_audit_apply_safe_fixes_removes_dead_links(memory_root, tmp_path, monkeypatch, capsys):
    write_index(memory_root, ["- [Ghost](ghost.md) — points nowhere"])
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules(
        [area], tmp_path,
        automation={"mode": "apply_safe_fixes", "auto_fix_missing_index_entries": False,
                    "auto_fix_broken_links": True},
    )
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_audit(ns(area=None))
    assert "Applied 1 fix(es)" in capsys.readouterr().out

    from scanner import parse_index
    entries, _ = parse_index(memory_root)
    assert entries == []


def test_cmd_audit_apply_safe_fixes_noop_when_nothing_to_fix(memory_root, tmp_path, monkeypatch, capsys):
    write_memory_file(memory_root, "a.md", "a", "a valid description here", "user", "body")
    write_index(memory_root, ["- [A](a.md) — a valid description here"])
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules(
        [area], tmp_path,
        automation={"mode": "apply_safe_fixes", "auto_fix_missing_index_entries": True,
                    "auto_fix_broken_links": True},
    )
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_audit(ns(area=None))
    assert "No auto-fixable issues found" in capsys.readouterr().out


def test_cmd_audit_apply_safe_fixes_skips_scoped_areas(tmp_path, monkeypatch, capsys):
    root = tmp_path / "project"
    mem_dir = root / "memory"
    mem_dir.mkdir(parents=True)
    write_memory_file(mem_dir, "a.md", "a", "a valid description here", "user", "body")
    area = ResolvedArea("proj", root, "scoped")
    rules = make_rules(
        [area], tmp_path,
        automation={"mode": "apply_safe_fixes", "auto_fix_missing_index_entries": True,
                    "auto_fix_broken_links": True},
    )
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_audit(ns(area=None))
    assert "auto-fix only applies to 'full' mode" in capsys.readouterr().out


def test_cmd_audit_write_mode_not_blocked_by_unrelated_conflicting_area(memory_root, tmp_path, monkeypatch, capsys):
    """Regression test: an unrelated area whose backup_dir happens to sit
    inside its own root must not block a write-mode run targeting a
    different, non-conflicting area (config.py used to validate every
    configured area up front regardless of --area filtering)."""
    write_memory_file(memory_root, "orphan.md", "orphan", "an orphan memory", "user", "body")
    good_area = ResolvedArea("good", memory_root, "full")

    conflicting_root = tmp_path / "conflicting_project"
    conflicting_root.mkdir()
    conflicting_area = ResolvedArea("conflicting", conflicting_root, "scoped")

    rules = make_rules(
        [good_area, conflicting_area], tmp_path,
        automation={"mode": "apply_safe_fixes", "auto_fix_missing_index_entries": True,
                    "auto_fix_broken_links": False},
    )
    # simulate the conflicting area's backup_dir actually being nested inside its root
    rules["paths"]["backup_dir"] = str(conflicting_root / "backups")
    (conflicting_root / "backups").mkdir()
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_audit(ns(area="good"))
    out = capsys.readouterr().out
    assert "Applied 1 fix(es)" in out
    assert "ERROR" not in out


def test_cmd_audit_write_mode_blocked_for_area_with_own_conflict(tmp_path, monkeypatch, capsys):
    root = tmp_path / "project"
    root.mkdir()
    area = ResolvedArea("proj", root, "full")
    rules = make_rules(
        [area], tmp_path,
        automation={"mode": "apply_safe_fixes", "auto_fix_missing_index_entries": True,
                    "auto_fix_broken_links": False},
    )
    rules["paths"]["backup_dir"] = str(root / "backups")
    (root / "backups").mkdir()
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    with pytest.raises(SystemExit):
        main.cmd_audit(ns(area="proj"))
    assert "resolves inside area 'proj'" in capsys.readouterr().err


# ---- cmd_dry_run ----

def test_cmd_dry_run_previews_without_touching_real_area(memory_root, tmp_path, monkeypatch, capsys):
    write_memory_file(memory_root, "orphan.md", "orphan", "an orphan memory", "user", "body")
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules(
        [area], tmp_path,
        automation={"mode": "report_only", "auto_fix_missing_index_entries": True,
                    "auto_fix_broken_links": False},
    )
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_dry_run(ns())
    out = capsys.readouterr().out
    assert "WOULD be applied" in out
    assert "Score if applied" in out
    assert "MEMORY.md diff" in out

    # the real area must be completely untouched
    from scanner import parse_index
    entries, _ = parse_index(memory_root)
    assert entries == []


def test_cmd_dry_run_creates_inspectable_staging_copy(memory_root, tmp_path, monkeypatch):
    write_memory_file(memory_root, "orphan.md", "orphan", "an orphan memory", "user", "body")
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules(
        [area], tmp_path,
        automation={"mode": "report_only", "auto_fix_missing_index_entries": True,
                    "auto_fix_broken_links": False},
    )
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_dry_run(ns())

    from scanner import parse_index
    staging_dir = tmp_path / "backups" / "dryrun_main"
    entries, _ = parse_index(staging_dir)
    assert {e.href for e in entries} == {"orphan.md"}


def test_cmd_dry_run_noop_when_flags_disabled(memory_root, tmp_path, monkeypatch, capsys):
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)  # both auto_fix_* default False
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_dry_run(ns())
    assert "nothing would change" in capsys.readouterr().out


def test_cmd_dry_run_skips_scoped_areas(tmp_path, monkeypatch, capsys):
    root = tmp_path / "project"
    mem_dir = root / "memory"
    mem_dir.mkdir(parents=True)
    write_memory_file(mem_dir, "a.md", "a", "a valid description here", "user", "body")
    area = ResolvedArea("proj", root, "scoped")
    rules = make_rules(
        [area], tmp_path,
        automation={"mode": "report_only", "auto_fix_missing_index_entries": True,
                    "auto_fix_broken_links": False},
    )
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_dry_run(ns())
    assert "dry-run only applies to 'full' mode" in capsys.readouterr().out


def test_cmd_dry_run_blocked_when_backup_dir_inside_area_root(tmp_path, monkeypatch, capsys):
    """Regression test for a confirmed severe bug: without this guard,
    create_dry_run_copy would copy the area into a staging dir nested
    inside the very area being copied, recursing until the OS refuses
    (hit Windows' path-length limit after ~9 levels of self-nesting in
    manual reproduction)."""
    root = tmp_path / "project"
    root.mkdir()
    write_memory_file(root, "orphan.md", "orphan", "an orphan memory", "user", "body")
    area = ResolvedArea("proj", root, "full")
    rules = make_rules(
        [area], tmp_path,
        automation={"mode": "report_only", "auto_fix_missing_index_entries": True,
                    "auto_fix_broken_links": False},
    )
    rules["paths"]["backup_dir"] = str(root / "backups")
    (root / "backups").mkdir()
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    with pytest.raises(SystemExit):
        main.cmd_dry_run(ns())
    assert "resolves inside area 'proj'" in capsys.readouterr().err


def test_cmd_dry_run_repeated_runs_dont_accumulate(memory_root, tmp_path, monkeypatch):
    write_memory_file(memory_root, "orphan.md", "orphan", "an orphan memory", "user", "body")
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules(
        [area], tmp_path,
        automation={"mode": "report_only", "auto_fix_missing_index_entries": True,
                    "auto_fix_broken_links": False},
    )
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_dry_run(ns())
    main.cmd_dry_run(ns())  # second run should overwrite, not duplicate

    staging_dir = tmp_path / "backups" / "dryrun_main"
    assert sorted(p.name for p in staging_dir.glob("*.md")) == ["MEMORY.md", "orphan.md"]


def test_cmd_audit_unknown_area_exits(memory_root, tmp_path, monkeypatch, capsys):
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    with pytest.raises(SystemExit):
        main.cmd_audit(ns(area="bogus"))
    assert "no area named" in capsys.readouterr().err


# ---- cmd_init / cmd_new_memory ----

def test_cmd_init_bootstraps_fresh_folder(tmp_path, monkeypatch, capsys):
    fresh = tmp_path / "fresh_memory"
    area = ResolvedArea("main", fresh, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_init(ns())
    assert (fresh / "MEMORY.md").exists()
    assert (fresh / "MEMORY_RULES.md").exists()
    assert "Bootstrap actions taken" in capsys.readouterr().out


def test_cmd_new_memory_creates_scaffold(memory_root, tmp_path, monkeypatch, capsys):
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_new_memory(ns(type="feedback", slug="my-new-slug", description="a description"))
    created = memory_root / "my-new-slug.md"
    assert created.exists()
    assert "**Why:**" in created.read_text(encoding="utf-8")
    assert "Created:" in capsys.readouterr().out


# ---- cmd_map ----

def test_cmd_map_disabled(memory_root, tmp_path, monkeypatch, capsys):
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)  # external_scan disabled by make_rules default
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_map(ns())
    assert "disabled" in capsys.readouterr().out


def test_cmd_map_finds_external_files(memory_root, tmp_path, monkeypatch, capsys):
    workspace = tmp_path / "workspace"
    other_mem = workspace / "other_project" / "memory"
    other_mem.mkdir(parents=True)
    write_memory_file(other_mem, "b.md", "b", "a valid description here", "user", "body")

    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path, external_scan={"enabled": True, "workspace_root": str(workspace)})
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_map(ns())
    out = capsys.readouterr().out
    assert "b.md" in out


# ---- cmd_cross_check ----

def test_cmd_cross_check_requires_two_areas(memory_root, tmp_path, monkeypatch, capsys):
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_cross_check(ns())
    assert "Need at least 2 configured areas" in capsys.readouterr().out


def test_cmd_cross_check_finds_slug_conflict(tmp_path, monkeypatch, capsys):
    root_a = tmp_path / "area_a"
    root_b = tmp_path / "area_b"
    root_a.mkdir()
    root_b.mkdir()
    write_memory_file(root_a, "x.md", "shared-slug", "desc", "user", "version one")
    write_memory_file(root_b, "x.md", "shared-slug", "desc", "user", "a different version two")

    areas = [ResolvedArea("area_a", root_a, "full"), ResolvedArea("area_b", root_b, "full")]
    rules = make_rules(areas, tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_cross_check(ns())
    out = capsys.readouterr().out
    assert "cross_area_slug_conflict" in out
    assert "DIFFERING content" in out
    assert "Report written to:" in out
    assert list((tmp_path / "reports").glob("cross-check_*.md"))


def test_cmd_cross_check_no_conflicts(tmp_path, monkeypatch, capsys):
    root_a = tmp_path / "area_a"
    root_b = tmp_path / "area_b"
    root_a.mkdir()
    root_b.mkdir()
    write_memory_file(root_a, "x.md", "slug-a", "desc", "user", "unrelated content")
    write_memory_file(root_b, "y.md", "slug-b", "desc", "user", "totally unrelated other content")

    areas = [ResolvedArea("area_a", root_a, "full"), ResolvedArea("area_b", root_b, "full")]
    rules = make_rules(areas, tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_cross_check(ns())
    out = capsys.readouterr().out
    assert "No cross-area duplicates or slug conflicts found" in out


def test_cmd_cross_check_scoped_area_uses_scoped_scan(tmp_path, monkeypatch, capsys):
    root_a = tmp_path / "area_a"
    mem_dir = root_a / "memory"
    mem_dir.mkdir(parents=True)
    write_memory_file(mem_dir, "x.md", "shared-slug", "desc", "user", "version one")

    root_b = tmp_path / "area_b"
    root_b.mkdir()
    write_memory_file(root_b, "x.md", "shared-slug", "desc", "user", "version two differs")

    areas = [ResolvedArea("area_a", root_a, "scoped"), ResolvedArea("area_b", root_b, "full")]
    rules = make_rules(areas, tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_cross_check(ns())
    out = capsys.readouterr().out
    assert "cross_area_slug_conflict" in out


# ---- cmd_resolve_conflicts ----

def test_cmd_resolve_conflicts_missing_diverged_area_exits(tmp_path, monkeypatch, capsys):
    root_a = tmp_path / "area_a"
    root_b = tmp_path / "area_b"
    root_a.mkdir()
    root_b.mkdir()
    areas = [ResolvedArea("area_a", root_a, "full"), ResolvedArea("area_b", root_b, "full")]
    rules = make_rules(areas, tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    with pytest.raises(SystemExit):
        main.cmd_resolve_conflicts(ns(diverged_area=None))
    assert "no area named 'memory-diverged'" in capsys.readouterr().err


def test_cmd_resolve_conflicts_diverged_area_must_be_full_mode(tmp_path, monkeypatch, capsys):
    root_a = tmp_path / "area_a"
    root_b = tmp_path / "area_b"
    diverged_root = tmp_path / "diverged"
    root_a.mkdir()
    root_b.mkdir()
    diverged_root.mkdir()
    areas = [
        ResolvedArea("area_a", root_a, "full"),
        ResolvedArea("area_b", root_b, "full"),
        ResolvedArea("memory-diverged", diverged_root, "scoped"),
    ]
    rules = make_rules(areas, tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    with pytest.raises(SystemExit):
        main.cmd_resolve_conflicts(ns(diverged_area=None))
    assert "must be mode: full" in capsys.readouterr().err


def test_cmd_resolve_conflicts_non_interactive_lists_only(tmp_path, monkeypatch, capsys):
    root_a = tmp_path / "area_a"
    root_b = tmp_path / "area_b"
    diverged_root = tmp_path / "diverged"
    root_a.mkdir()
    root_b.mkdir()
    diverged_root.mkdir()
    write_memory_file(root_a, "x.md", "shared-slug", "desc", "user", "version one")
    write_memory_file(root_b, "x.md", "shared-slug", "desc", "user", "a differing version two")

    areas = [
        ResolvedArea("area_a", root_a, "full"),
        ResolvedArea("area_b", root_b, "full"),
        ResolvedArea("memory-diverged", diverged_root, "full"),
    ]
    rules = make_rules(areas, tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_resolve_conflicts(ns(diverged_area=None))
    out = capsys.readouterr().out
    assert "1 diverged conflict(s) need resolution" in out
    # non-interactive must never write anything
    assert not any(diverged_root.iterdir())
    assert (root_a / "x.md").read_text(encoding="utf-8") == (root_a / "x.md").read_text(encoding="utf-8")


def test_cmd_resolve_conflicts_no_conflicts(tmp_path, monkeypatch, capsys):
    root_a = tmp_path / "area_a"
    root_b = tmp_path / "area_b"
    diverged_root = tmp_path / "diverged"
    root_a.mkdir()
    root_b.mkdir()
    diverged_root.mkdir()
    write_memory_file(root_a, "x.md", "slug-a", "desc", "user", "content a")
    write_memory_file(root_b, "y.md", "slug-b", "desc", "user", "content b")

    areas = [
        ResolvedArea("area_a", root_a, "full"),
        ResolvedArea("area_b", root_b, "full"),
        ResolvedArea("memory-diverged", diverged_root, "full"),
    ]
    rules = make_rules(areas, tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_resolve_conflicts(ns(diverged_area=None))
    assert "No diverged" in capsys.readouterr().out


def test_cmd_resolve_conflicts_interactive_keeps_chosen_version(tmp_path, monkeypatch, capsys):
    root_a = tmp_path / "area_a"
    root_b = tmp_path / "area_b"
    diverged_root = tmp_path / "diverged"
    root_a.mkdir()
    root_b.mkdir()
    diverged_root.mkdir()
    write_memory_file(root_a, "x.md", "shared-slug", "desc", "user", "the version worth keeping")
    write_memory_file(root_b, "x.md", "shared-slug", "desc", "user", "a stale, differing version")

    areas = [
        ResolvedArea("area_a", root_a, "full"),
        ResolvedArea("area_b", root_b, "full"),
        ResolvedArea("memory-diverged", diverged_root, "full"),
    ]
    rules = make_rules(areas, tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)
    monkeypatch.setattr("builtins.input", lambda _: "a")  # keep area_a's version

    main.cmd_resolve_conflicts(ns(non_interactive=False, diverged_area=None))
    out = capsys.readouterr().out
    assert "Resolved 1/1 conflict(s)" in out

    canonical = diverged_root / "shared-slug.md"
    assert canonical.exists()
    assert "the version worth keeping" in canonical.read_text(encoding="utf-8")

    stub_a = (root_a / "x.md").read_text(encoding="utf-8")
    stub_b = (root_b / "x.md").read_text(encoding="utf-8")
    assert "Pointer only" in stub_a
    assert "Pointer only" in stub_b
    assert "the version worth keeping" not in stub_a  # body was replaced, not appended to


def test_cmd_resolve_conflicts_skip_leaves_files_untouched(tmp_path, monkeypatch, capsys):
    root_a = tmp_path / "area_a"
    root_b = tmp_path / "area_b"
    diverged_root = tmp_path / "diverged"
    root_a.mkdir()
    root_b.mkdir()
    diverged_root.mkdir()
    write_memory_file(root_a, "x.md", "shared-slug", "desc", "user", "version one")
    write_memory_file(root_b, "x.md", "shared-slug", "desc", "user", "a differing version two")

    areas = [
        ResolvedArea("area_a", root_a, "full"),
        ResolvedArea("area_b", root_b, "full"),
        ResolvedArea("memory-diverged", diverged_root, "full"),
    ]
    rules = make_rules(areas, tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)
    monkeypatch.setattr("builtins.input", lambda _: "s")  # skip

    main.cmd_resolve_conflicts(ns(non_interactive=False, diverged_area=None))
    out = capsys.readouterr().out
    assert "Resolved 0/1 conflict(s)" in out
    assert "version one" in (root_a / "x.md").read_text(encoding="utf-8")
    assert not any(diverged_root.iterdir())


def test_cmd_resolve_conflicts_custom_diverged_area_name(tmp_path, monkeypatch, capsys):
    root_a = tmp_path / "area_a"
    root_b = tmp_path / "area_b"
    custom_diverged = tmp_path / "custom"
    root_a.mkdir()
    root_b.mkdir()
    custom_diverged.mkdir()
    write_memory_file(root_a, "x.md", "shared-slug", "desc", "user", "version one")
    write_memory_file(root_b, "x.md", "shared-slug", "desc", "user", "a differing version two")

    areas = [
        ResolvedArea("area_a", root_a, "full"),
        ResolvedArea("area_b", root_b, "full"),
        ResolvedArea("my-custom-name", custom_diverged, "full"),
    ]
    rules = make_rules(areas, tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)
    monkeypatch.setattr("builtins.input", lambda _: "a")

    main.cmd_resolve_conflicts(ns(non_interactive=False, diverged_area="my-custom-name"))
    assert (custom_diverged / "shared-slug.md").exists()


# ---- cmd_review / review_list / review_forget ----

def test_cmd_review_non_interactive_lists_candidates(memory_root, tmp_path, monkeypatch, capsys):
    (memory_root / "bad.md").write_text("no frontmatter", encoding="utf-8")
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_review(ns())
    out = capsys.readouterr().out
    assert "bad.md" in out
    assert "need review" in out


def test_cmd_review_no_candidates(memory_root, tmp_path, monkeypatch, capsys):
    write_memory_file(memory_root, "a.md", "a", "a valid description here", "user", "body")
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_review(ns())
    assert "No unreviewed" in capsys.readouterr().out


def test_cmd_review_interactive_records_ignore_decision(memory_root, tmp_path, monkeypatch, capsys):
    (memory_root / "bad.md").write_text("no frontmatter", encoding="utf-8")
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    responses = iter(["i", "not a memory file"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))

    main.cmd_review(ns(non_interactive=False))
    decisions = registry.load_decisions("main")
    assert len(decisions) == 1
    assert decisions[0].decision == "ignore"
    assert decisions[0].rel_path == "bad.md"


def test_cmd_review_interactive_quit_stops_early(memory_root, tmp_path, monkeypatch):
    (memory_root / "bad1.md").write_text("no frontmatter", encoding="utf-8")
    (memory_root / "bad2.md").write_text("no frontmatter", encoding="utf-8")
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    monkeypatch.setattr("builtins.input", lambda _: "q")
    main.cmd_review(ns(non_interactive=False))
    assert registry.load_decisions("main") == []


def test_cmd_review_list_and_forget(memory_root, tmp_path, monkeypatch, capsys):
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    registry.record_decision("main", "x.md", "ignore", "test note")
    main.cmd_review_list(ns())
    assert "x.md" in capsys.readouterr().out

    main.cmd_review_forget(ns(rel_path="x.md"))
    assert "Removed decision" in capsys.readouterr().out
    assert registry.load_decisions("main") == []


def test_cmd_review_forget_not_found(memory_root, tmp_path, monkeypatch, capsys):
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_review_forget(ns(rel_path="nonexistent.md"))
    assert "No decision found" in capsys.readouterr().out


# ---- cmd_snapshot / list_snapshots / rollback ----

def test_cmd_snapshot_and_list(memory_root, tmp_path, monkeypatch, capsys):
    (memory_root / "a.md").write_text("content", encoding="utf-8")
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_snapshot(ns(reason="test snapshot"))
    assert "Snapshot created" in capsys.readouterr().out

    main.cmd_list_snapshots(ns())
    assert "test snapshot" in capsys.readouterr().out


def test_cmd_rollback_restores(memory_root, tmp_path, monkeypatch, capsys):
    (memory_root / "a.md").write_text("original", encoding="utf-8")
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)

    main.cmd_snapshot(ns(reason="backup"))
    (memory_root / "a.md").write_text("mutated", encoding="utf-8")

    main.cmd_rollback(ns(which="latest", force=True))
    assert (memory_root / "a.md").read_text(encoding="utf-8") == "original"
    assert "Rolled back from" in capsys.readouterr().out


# ---- main() argument parsing / dispatch ----

def test_main_dispatches_unknown_area_error_exits(memory_root, tmp_path, monkeypatch, capsys):
    area = ResolvedArea("main", memory_root, "full")
    rules = make_rules([area], tmp_path)
    monkeypatch.setattr(main, "get_config", lambda **kw: rules)
    monkeypatch.setattr("sys.argv", ["main.py", "--non-interactive", "init", "--area", "bogus"])

    with pytest.raises(SystemExit) as exc_info:
        main.main()
    assert exc_info.value.code == 1
    assert "no area named" in capsys.readouterr().err


def test_main_requires_a_subcommand(monkeypatch):
    monkeypatch.setattr("sys.argv", ["main.py"])
    with pytest.raises(SystemExit):
        main.main()
