"""CLI entrypoint for the memory consolidator (no model inference — pure heuristics)."""
import argparse
import sys
from pathlib import Path

from backup import create_snapshot, list_snapshots, rollback
from checks import run_all_checks
from config import get_config
from report import print_console, write_markdown_report
from scanner import parse_index, scan_memory_files


def cmd_audit(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    memory_root = Path(rules["memory_root"])

    files = scan_memory_files(memory_root)
    index_entries, index_lines = parse_index(memory_root)
    findings = run_all_checks(memory_root, files, index_entries, index_lines, rules)

    print_console(findings, memory_root)

    report_dir = Path(rules["paths"]["report_dir"])
    report_path = write_markdown_report(
        findings, memory_root, report_dir, rules["reporting"]["keep_last_n_reports"]
    )
    print(f"\nReport written to: {report_path}")

    if rules["automation"]["mode"] != "report_only":
        backup_dir = Path(rules["paths"]["backup_dir"])
        snap = create_snapshot(memory_root, backup_dir, reason=f"pre-apply ({rules['automation']['mode']})")
        print(f"Snapshot created before any apply step: {snap}")
        print("apply_safe_fixes / full_auto logic not yet implemented — audit-only for now.")


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
