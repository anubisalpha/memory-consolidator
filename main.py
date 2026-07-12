"""CLI entrypoint for the memory consolidator (no model inference — pure heuristics)."""
import argparse
import sys
from pathlib import Path

from backup import create_snapshot, list_snapshots, rollback
from checks import compliance_score, run_all_checks
from config import get_config
from discovery import discover_external_memory_files
from report import print_console, write_markdown_report
from scanner import parse_index, scan_memory_files
from templates import bootstrap_memory_folder, scaffold_memory_file


def cmd_audit(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    memory_root = Path(rules["memory_root"])

    files = scan_memory_files(memory_root)
    index_entries, index_lines = parse_index(memory_root)
    findings = run_all_checks(memory_root, files, index_entries, index_lines, rules)
    score = compliance_score(findings, len(files))

    print_console(findings, memory_root, score=score)

    report_dir = Path(rules["paths"]["report_dir"])
    report_path = write_markdown_report(
        findings, memory_root, report_dir, rules["reporting"]["keep_last_n_reports"], score=score
    )
    print(f"\nReport written to: {report_path}")

    if rules["automation"]["mode"] != "report_only":
        backup_dir = Path(rules["paths"]["backup_dir"])
        snap = create_snapshot(memory_root, backup_dir, reason=f"pre-apply ({rules['automation']['mode']})")
        print(f"Snapshot created before any apply step: {snap}")
        print("apply_safe_fixes / full_auto logic not yet implemented — audit-only for now.")


def cmd_init(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    memory_root = Path(rules["memory_root"])
    actions = bootstrap_memory_folder(memory_root)
    if actions:
        print("Bootstrap actions taken:")
        for a in actions:
            print(f"  - {a}")
    else:
        print(f"Memory folder already fully set up at {memory_root}")


def cmd_new_memory(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    memory_root = Path(rules["memory_root"])
    path = scaffold_memory_file(memory_root, args.type, args.slug, args.description)
    print(f"Created: {path}")
    print("Remember to add a one-line entry to MEMORY.md's index.")


def cmd_map(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    memory_root = Path(rules["memory_root"])
    cfg = rules.get("external_scan", {})
    if not cfg.get("enabled", False) or not cfg.get("workspace_root"):
        print("external_scan is disabled or workspace_root is unset in rules.md — nothing to map.")
        return
    workspace_root = Path(cfg["workspace_root"])
    if not workspace_root.exists():
        print(f"workspace_root does not exist: {workspace_root}")
        return

    found = discover_external_memory_files(workspace_root, memory_root, cfg.get("map_patterns"))
    if not found:
        print(f"No memory-shaped files found outside {memory_root} under {workspace_root}.")
        return

    print(f"Found {len(found)} memory-shaped file(s) outside memory_root:\n")
    for d in found:
        print(f"  {d.path}  (matched: {d.matched_pattern})")
    print("\nThese are not audited by `audit` unless referenced via a pointer path")
    print("(e.g. a description containing `some/path.md` in backticks).")


def cmd_snapshot(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    memory_root = Path(rules["memory_root"])
    backup_dir = Path(rules["paths"]["backup_dir"])
    snap = create_snapshot(memory_root, backup_dir, reason=args.reason or "manual")
    print(f"Snapshot created: {snap}")


def cmd_list_snapshots(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    backup_dir = Path(rules["paths"]["backup_dir"])
    for entry in list_snapshots(backup_dir):
        print(f"{entry['timestamp']}  {entry['zip']}  ({entry['reason']})")


def cmd_rollback(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    memory_root = Path(rules["memory_root"])
    backup_dir = Path(rules["paths"]["backup_dir"])
    zip_path = rollback(memory_root, backup_dir, which=args.which, force=args.force)
    print(f"Rolled back from: {zip_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory Consolidator — programmatic memory audit tool")
    parser.add_argument("--non-interactive", action="store_true", help="never prompt; fail if config is ambiguous")
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="scan memory_root and produce findings + report")
    p_audit.set_defaults(func=cmd_audit)

    p_init = sub.add_parser("init", help="bootstrap memory_root (MEMORY.md + MEMORY_RULES.md) on a fresh machine")
    p_init.set_defaults(func=cmd_init)

    p_new = sub.add_parser("new-memory", help="scaffold a correctly-structured memory file")
    p_new.add_argument("--type", required=True, choices=["user", "feedback", "project", "reference"])
    p_new.add_argument("--slug", required=True, help="kebab-case name, becomes the filename")
    p_new.add_argument("--description", required=True, help="one-line description")
    p_new.set_defaults(func=cmd_new_memory)

    p_map = sub.add_parser("map", help="discover memory-shaped files scattered outside memory_root")
    p_map.set_defaults(func=cmd_map)

    p_snap = sub.add_parser("snapshot", help="manually snapshot memory_root")
    p_snap.add_argument("--reason", default=None)
    p_snap.set_defaults(func=cmd_snapshot)

    p_list = sub.add_parser("list-snapshots", help="list recorded snapshots")
    p_list.set_defaults(func=cmd_list_snapshots)

    p_roll = sub.add_parser("rollback", help="restore memory_root from a snapshot")
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
