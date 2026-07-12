"""CLI entrypoint for the memory consolidator (no model inference — pure heuristics)."""
import argparse
import sys
from pathlib import Path

from backup import create_snapshot, list_snapshots, rollback
from checks import compliance_score, run_all_checks
from config import ResolvedArea, get_config
from discovery import discover_external_memory_files
from report import print_console, write_markdown_report
from scanner import parse_index, scan_memory_files, scan_memory_files_scoped
from templates import bootstrap_memory_folder, scaffold_memory_file


def _select_area(rules: dict, area_name: str | None) -> ResolvedArea:
    areas: list[ResolvedArea] = rules["_resolved_areas"]
    if not areas:
        raise ValueError("no areas configured in rules.md")
    if area_name:
        matches = [a for a in areas if a.name == area_name]
        if not matches:
            names = ", ".join(a.name for a in areas)
            raise ValueError(f"no area named '{area_name}' — configured areas: {names}")
        return matches[0]
    if len(areas) == 1:
        return areas[0]
    names = ", ".join(a.name for a in areas)
    raise ValueError(f"multiple areas configured — pass --area to pick one: {names}")


def cmd_audit(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    areas: list[ResolvedArea] = rules["_resolved_areas"]
    if args.area:
        areas = [a for a in areas if a.name == args.area]
        if not areas:
            print(f"ERROR: no area named '{args.area}'", file=sys.stderr)
            sys.exit(1)

    report_dir = Path(rules["paths"]["report_dir"])

    for area in areas:
        print(f"\n=== Area: {area.name} ({area.mode}) — {area.root} ===")

        if area.mode == "full":
            files = scan_memory_files(area.root)
            index_entries, index_lines = parse_index(area.root)
        else:
            files = scan_memory_files_scoped(area.root, rules.get("memory_file_patterns", []))
            index_entries, index_lines = [], []

        findings = run_all_checks(area.root, files, index_entries, index_lines, rules, mode=area.mode)
        score = compliance_score(findings, len(files))

        print_console(findings, area.root, score=score)

        report_path = write_markdown_report(
            findings, area.root, report_dir, rules["reporting"]["keep_last_n_reports"],
            score=score, report_name_prefix=area.name,
        )
        print(f"Report written to: {report_path}")

        if rules["automation"]["mode"] != "report_only":
            backup_dir = Path(rules["paths"]["backup_dir"])
            snap = create_snapshot(area.root, backup_dir, reason=f"pre-apply ({rules['automation']['mode']}) [{area.name}]")
            print(f"Snapshot created before any apply step: {snap}")
            print("apply_safe_fixes / full_auto logic not yet implemented — audit-only for now.")


def cmd_init(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    actions = bootstrap_memory_folder(area.root)
    if actions:
        print(f"Bootstrap actions taken for area '{area.name}':")
        for a in actions:
            print(f"  - {a}")
    else:
        print(f"Area '{area.name}' already fully set up at {area.root}")


def cmd_new_memory(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    path = scaffold_memory_file(area.root, args.type, args.slug, args.description)
    print(f"Created: {path}")
    print("Remember to add a one-line entry to MEMORY.md's index.")


def cmd_map(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    cfg = rules.get("external_scan", {})
    if not cfg.get("enabled", False) or not cfg.get("workspace_root"):
        print("external_scan is disabled or workspace_root is unset in rules.md — nothing to map.")
        return
    workspace_root = Path(cfg["workspace_root"])
    if not workspace_root.exists():
        print(f"workspace_root does not exist: {workspace_root}")
        return

    patterns = rules.get("memory_file_patterns")
    found = discover_external_memory_files(workspace_root, area.root, patterns)
    if not found:
        print(f"No memory-shaped files found outside {area.root} under {workspace_root}.")
        return

    print(f"Found {len(found)} memory-shaped file(s) outside area '{area.name}':\n")
    for d in found:
        print(f"  {d.path}  (matched: {d.matched_pattern})")
    print("\nThese are not audited by `audit` unless referenced via a pointer path")
    print("(e.g. a description containing `some/path.md` in backticks), or covered")
    print("by a 'scoped' area in rules.md.")


def cmd_snapshot(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    backup_dir = Path(rules["paths"]["backup_dir"])
    snap = create_snapshot(area.root, backup_dir, reason=args.reason or "manual")
    print(f"Snapshot created: {snap}")


def cmd_list_snapshots(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    backup_dir = Path(rules["paths"]["backup_dir"])
    for entry in list_snapshots(backup_dir):
        print(f"{entry['timestamp']}  {entry['zip']}  ({entry['reason']})")


def cmd_rollback(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    backup_dir = Path(rules["paths"]["backup_dir"])
    zip_path = rollback(area.root, backup_dir, which=args.which, force=args.force)
    print(f"Rolled back from: {zip_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory Consolidator — programmatic memory audit tool")
    parser.add_argument("--non-interactive", action="store_true", help="never prompt; fail if config is ambiguous")
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="scan configured area(s) and produce findings + report per area")
    p_audit.add_argument("--area", default=None, help="only audit this area (default: all configured areas)")
    p_audit.set_defaults(func=cmd_audit)

    p_init = sub.add_parser("init", help="bootstrap an area's root (MEMORY.md + MEMORY_RULES.md) on a fresh machine")
    p_init.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_init.set_defaults(func=cmd_init)

    p_new = sub.add_parser("new-memory", help="scaffold a correctly-structured memory file")
    p_new.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_new.add_argument("--type", required=True, choices=["user", "feedback", "project", "reference"])
    p_new.add_argument("--slug", required=True, help="kebab-case name, becomes the filename")
    p_new.add_argument("--description", required=True, help="one-line description")
    p_new.set_defaults(func=cmd_new_memory)

    p_map = sub.add_parser("map", help="discover memory-shaped files scattered outside an area's root")
    p_map.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_map.set_defaults(func=cmd_map)

    p_snap = sub.add_parser("snapshot", help="manually snapshot an area's root")
    p_snap.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_snap.add_argument("--reason", default=None)
    p_snap.set_defaults(func=cmd_snapshot)

    p_list = sub.add_parser("list-snapshots", help="list recorded snapshots")
    p_list.set_defaults(func=cmd_list_snapshots)

    p_roll = sub.add_parser("rollback", help="restore an area's root from a snapshot")
    p_roll.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_roll.add_argument("--which", default="latest", help="timestamp of snapshot, or 'latest'")
    p_roll.add_argument("--force", action="store_true", help="skip confirmation prompt")
    p_roll.set_defaults(func=cmd_rollback)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
