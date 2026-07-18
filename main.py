"""CLI entrypoint for the memory consolidator (no model inference — pure heuristics)."""
import argparse
import sys
from datetime import date
from pathlib import Path

from backup import create_snapshot, create_targeted_snapshot, list_snapshots, restore_single_file, rollback
from checks import compliance_score, find_duplicate_review_candidates, find_stale_review_candidates, run_all_checks
from config import ResolvedArea, ensure_backup_safe_for_area, get_config
from consolidate import write_canonical_file, write_pointer_stub
from crosscheck import find_cross_area_duplicates, find_cross_area_slug_conflicts, find_overlapping_areas
from discovery import discover_external_memory_files
from dryrun import create_dry_run_copy, diff_changed_files, diff_memory_index
from fixer import add_missing_index_entries, mark_stale_files, merge_exact_duplicates, remove_dead_index_links
from registry import (
    finding_decision_map,
    load_decisions,
    load_finding_decisions,
    record_decision,
    record_finding_decision,
    remove_decision,
    remove_finding_decision,
)
from report import print_console, print_cross_area_console, write_cross_area_report, write_markdown_report
from reviewer import find_review_candidates
from scanner import parse_index, scan_memory_files, scan_memory_files_scoped
from templates import bootstrap_memory_folder, scaffold_memory_file


def _apply_fixes(root: Path, files, index_entries, index_lines, rules: dict,
                  index_header: str | None = None) -> list[str]:
    """Shared by cmd_audit (applies for real) and cmd_dry_run (applies to a
    disposable copy) so the two paths can never drift apart."""
    auto_cfg = rules["automation"]
    actions = []
    if auto_cfg.get("auto_fix_broken_links", False):
        actions += remove_dead_index_links(root, index_entries, index_lines)
        index_entries, index_lines = parse_index(root)
    if auto_cfg.get("auto_fix_missing_index_entries", False):
        actions += add_missing_index_entries(root, files, index_entries, index_header=index_header)

    if auto_cfg.get("mode") == "full_auto":
        if auto_cfg.get("auto_fix_mark_stale", False):
            actions += mark_stale_files(files, rules)
        if auto_cfg.get("auto_fix_merge_exact_duplicates", False):
            actions += merge_exact_duplicates(files, rules)
    return actions


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
        print(f"\n=== Area: {area.name} ({area.mode}) — {area.root} ===", flush=True)

        if area.mode == "full":
            files = scan_memory_files(area.root, area_name=area.name)
            index_entries, index_lines = parse_index(area.root)
        else:
            files = scan_memory_files_scoped(area.root, rules.get("memory_file_patterns", []), area_name=area.name)
            index_entries, index_lines = [], []

        dismissed_duplicates = {k for k, d in finding_decision_map(area.name, "duplicate").items()
                                 if d.decision == "dismissed"}
        dismissed_stale = {k for k, d in finding_decision_map(area.name, "stale").items()
                            if d.decision == "dismissed"}
        findings = run_all_checks(area.root, files, index_entries, index_lines, rules, mode=area.mode,
                                   dismissed_duplicates=dismissed_duplicates, dismissed_stale=dismissed_stale)
        score = compliance_score(findings, len(files))

        print_console(findings, area.root, score=score)

        report_path = write_markdown_report(
            findings, area.root, report_dir, rules["reporting"]["keep_last_n_reports"],
            score=score, report_name_prefix=area.name,
        )
        print(f"Report written to: {report_path}")

        if rules["automation"]["mode"] != "report_only":
            if area.mode != "full":
                print(f"Area '{area.name}' is 'scoped' — auto-fix only applies to 'full' mode "
                      "areas (there's no single MEMORY.md index to fix here). Skipping snapshot "
                      "too: a scoped area's root can be an entire workspace (many GB, node_modules, "
                      ".git, etc.) and a full-tree snapshot there is both unnecessary — nothing here "
                      "ever gets written to — and previously caused multi-minute-plus silent stalls.")
                continue

            backup_dir = Path(rules["paths"]["backup_dir"])
            ensure_backup_safe_for_area(area, backup_dir)
            print(f"Creating pre-apply snapshot of '{area.name}' ({area.root})...", flush=True)
            snap = create_snapshot(area.root, backup_dir, reason=f"pre-apply ({rules['automation']['mode']}) [{area.name}]",
                                    keep_last_n=rules.get("backup_retention", {}).get("keep_last_n"))
            print(f"Snapshot created before any apply step: {snap}", flush=True)

            actions = _apply_fixes(area.root, files, index_entries, index_lines, rules,
                                    index_header=area.index_header)

            if not actions:
                print("No auto-fixable issues found (or auto_fix_* flags are disabled in rules.md).")
                continue

            print(f"Applied {len(actions)} fix(es):")
            for a in actions:
                print(f"  - {a}")

            files = scan_memory_files(area.root, area_name=area.name)
            index_entries, index_lines = parse_index(area.root)
            new_findings = run_all_checks(area.root, files, index_entries, index_lines, rules, mode=area.mode,
                                           dismissed_duplicates=dismissed_duplicates, dismissed_stale=dismissed_stale)
            new_score = compliance_score(new_findings, len(files))
            print(f"\nRe-audit after fixes — score: {score:.1f} -> {new_score:.1f}/100 "
                  f"({len(findings)} -> {len(new_findings)} findings)")


def cmd_dry_run(args) -> None:
    """Preview apply_safe_fixes/full_auto on a disposable copy of the area —
    never touches the real area, regardless of automation.mode."""
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)

    if area.mode != "full":
        print(f"Area '{area.name}' is 'scoped' — dry-run only applies to 'full' mode areas "
              "(there's no single MEMORY.md index to fix here).")
        return

    auto_cfg = rules["automation"]
    mode = auto_cfg.get("mode")
    flag_names = ["auto_fix_missing_index_entries", "auto_fix_broken_links"]
    if mode == "full_auto":
        flag_names += ["auto_fix_mark_stale", "auto_fix_merge_exact_duplicates"]
    if not any(auto_cfg.get(f, False) for f in flag_names):
        print(f"No auto_fix_* flag applicable to automation.mode '{mode}' is enabled in rules.md — "
              "nothing would change. Enable at least one to preview its effect.")
        return

    backup_dir = Path(rules["paths"]["backup_dir"])
    ensure_backup_safe_for_area(area, backup_dir)
    staging_dir = backup_dir / f"dryrun_{area.name}"
    create_dry_run_copy(area.root, staging_dir)
    print(f"Copied area '{area.name}' ({area.root}) to disposable staging copy:\n  {staging_dir}\n")

    files = scan_memory_files(staging_dir, area_name=area.name)
    index_entries, index_lines = parse_index(staging_dir)
    actions = _apply_fixes(staging_dir, files, index_entries, index_lines, rules,
                            index_header=area.index_header)

    if not actions:
        print("Dry run: no auto-fixable issues found — nothing would change.")
        return

    print(f"Dry run: {len(actions)} fix(es) WOULD be applied:")
    for a in actions:
        print(f"  - {a}")

    diff_lines = diff_memory_index(area.root, staging_dir)
    if diff_lines:
        print("\nMEMORY.md diff (before -> after):\n")
        print("".join(diff_lines))

    file_diffs = diff_changed_files(area.root, staging_dir)
    if file_diffs:
        print(f"\n{len(file_diffs)} individual file(s) would be modified "
              "(full_auto's body-touching fixes):\n")
        for _, diff in file_diffs:
            print("".join(diff))

    orig_files = scan_memory_files(area.root, area_name=area.name)
    orig_entries, orig_lines = parse_index(area.root)
    orig_findings = run_all_checks(area.root, orig_files, orig_entries, orig_lines, rules, mode="full")
    orig_score = compliance_score(orig_findings, len(orig_files))

    new_files = scan_memory_files(staging_dir, area_name=area.name)
    new_entries, new_lines = parse_index(staging_dir)
    new_findings = run_all_checks(staging_dir, new_files, new_entries, new_lines, rules, mode="full")
    new_score = compliance_score(new_findings, len(new_files))

    print(f"\nScore if applied: {orig_score:.1f} -> {new_score:.1f}/100 "
          f"({len(orig_findings)} -> {len(new_findings)} findings)")
    print(f"\nStaging copy left at {staging_dir} for inspection — the real area is untouched.")
    print(f"Satisfied? Confirm automation.mode: {mode} in rules.md and run "
          f"`audit --area {area.name}` to apply for real.")


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


def cmd_cross_check(args) -> None:
    """Scan every configured area together and find the same slug or
    near-duplicate content living in more than one — the consolidation
    signal for picking a single source of truth. Report-only: never writes
    anything, so no ensure_backup_safe_for_area guard is needed here."""
    rules = get_config(non_interactive=args.non_interactive)
    areas: list[ResolvedArea] = rules["_resolved_areas"]
    if len(areas) < 2:
        print("Need at least 2 configured areas to cross-check — nothing to compare.")
        return

    area_files = {}
    for area in areas:
        if area.mode == "full":
            area_files[area.name] = scan_memory_files(area.root, area_name=area.name)
        else:
            area_files[area.name] = scan_memory_files_scoped(
                area.root, rules.get("memory_file_patterns", []), area_name=area.name)

    findings = find_overlapping_areas(areas)
    findings += find_cross_area_slug_conflicts(area_files)
    findings += find_cross_area_duplicates(area_files, rules)

    print_cross_area_console(findings)

    report_dir = Path(rules["paths"]["report_dir"])
    report_path = write_cross_area_report(findings, report_dir, rules["reporting"]["keep_last_n_reports"])
    print(f"\nReport written to: {report_path}")


def cmd_resolve_conflicts(args) -> None:
    """Interactively resolve cross-area slug conflicts with genuinely
    diverged content (the 'critical' findings from cross-check). For each,
    the user picks which version to keep; the chosen content is written into
    a dedicated 'memory-diverged' area, and BOTH original files become
    pointer stubs referencing it there — never a direct cross-link between
    the two original areas, so moving/deleting either one later can't break
    the reference (see consolidate.py)."""
    rules = get_config(non_interactive=args.non_interactive)
    areas: list[ResolvedArea] = rules["_resolved_areas"]

    diverged_name = args.diverged_area or "memory-diverged"
    diverged_matches = [a for a in areas if a.name == diverged_name]
    if not diverged_matches:
        print(f"ERROR: no area named '{diverged_name}' is configured. Add a 'mode: full' area "
              f"named '{diverged_name}' to rules.md to hold consolidated content, then re-run "
              f"(or pass --diverged-area to use a different name).", file=sys.stderr)
        sys.exit(1)
    diverged_area = diverged_matches[0]
    if diverged_area.mode != "full":
        print(f"ERROR: area '{diverged_name}' must be mode: full (it needs to be a plain memory "
              "folder, not a whole-project scope).", file=sys.stderr)
        sys.exit(1)

    other_areas = [a for a in areas if a.name != diverged_name]
    if len(other_areas) < 2:
        print("Need at least 2 non-diverged areas configured to compare — nothing to resolve.")
        return

    area_files = {}
    for area in other_areas:
        if area.mode == "full":
            area_files[area.name] = scan_memory_files(area.root, area_name=area.name)
        else:
            area_files[area.name] = scan_memory_files_scoped(
                area.root, rules.get("memory_file_patterns", []), area_name=area.name)

    conflicts = find_cross_area_slug_conflicts(area_files)
    critical = [f for f in conflicts if f.severity == "critical"]

    if not critical:
        print("No diverged (differing-content) cross-area slug conflicts to resolve.")
        return

    if args.non_interactive:
        print(f"{len(critical)} diverged conflict(s) need resolution "
              "(run without --non-interactive to resolve):")
        for f in critical:
            print(f"  {f.message}")
            print(f"    [{f.area_a}] {f.ref_a}")
            print(f"    [{f.area_b}] {f.ref_b}")
        return

    backup_dir = Path(rules["paths"]["backup_dir"])
    involved_names = {f.area_a for f in critical} | {f.area_b for f in critical} | {diverged_name}
    involved = [a for a in areas if a.name in involved_names]
    for area in involved:
        ensure_backup_safe_for_area(area, backup_dir)

    # Targeted, not whole-area: a 'scoped' area's root is a whole
    # project/workspace (potentially huge) — resolve-conflicts only ever
    # touches the specific files involved in a conflict, so back up just
    # those rather than the entire tree (see create_targeted_snapshot).
    area_touched_files: dict[str, set[Path]] = {}
    for finding in critical:
        area_touched_files.setdefault(finding.area_a, set()).add(Path(finding.ref_a))
        area_touched_files.setdefault(finding.area_b, set()).add(Path(finding.ref_b))
    for area in involved:
        touched = sorted(area_touched_files.get(area.name, set()))
        if touched:
            create_targeted_snapshot(touched, area.root, backup_dir,
                                      reason=f"pre-resolve-conflicts [{area.name}]",
                                      keep_last_n=rules.get("backup_retention", {}).get("keep_last_n"))
    print(f"Snapshotted {len(involved)} area(s) before resolving: {', '.join(a.name for a in involved)}\n")

    file_lookup = {}
    for area_name, files in area_files.items():
        for f in files:
            file_lookup[(area_name, str(f.path))] = f

    resolved_count = 0
    for finding in critical:
        fa = file_lookup.get((finding.area_a, finding.ref_a))
        fb = file_lookup.get((finding.area_b, finding.ref_b))
        if fa is None or fb is None:
            continue
        slug = fa.name

        print(f"--- slug '{slug}' ---")
        print(f"[a] {finding.area_a}: {finding.ref_a}")
        print(fa.body.strip()[:400])
        print(f"\n[b] {finding.area_b}: {finding.ref_b}")
        print(fb.body.strip()[:400])

        answer = input("\nKeep [a], keep [b], or [s]kip: ").strip().lower()
        if answer not in ("a", "b"):
            print("Skipped.\n")
            continue

        chosen, area_choice = (fa, finding.area_a) if answer == "a" else (fb, finding.area_b)
        note = f"kept the '{area_choice}' version on {date.today().isoformat()}, resolving a divergence with '{finding.area_b if answer == 'a' else finding.area_a}'"
        canonical_path = write_canonical_file(diverged_area.root, slug, chosen, note)
        write_pointer_stub(fa, canonical_path, diverged_name)
        write_pointer_stub(fb, canonical_path, diverged_name)
        print(f"Consolidated '{slug}' -> {canonical_path}\n")
        resolved_count += 1

    print(f"Resolved {resolved_count}/{len(critical)} conflict(s).")


def cmd_review(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    patterns = rules.get("memory_file_patterns", [])
    candidates = find_review_candidates(area.name, area.root, area.mode, patterns)

    if not candidates:
        print(f"No unreviewed non-canonical .md files found in area '{area.name}'.")
        return

    if args.non_interactive:
        print(f"{len(candidates)} file(s) need review in area '{area.name}' "
              "(run without --non-interactive to review interactively):")
        for path, reason in candidates:
            print(f"  {path}  — {reason}")
        return

    print(f"{len(candidates)} file(s) to review in area '{area.name}'.\n")
    print("For each: [c]ustom_format (approve, suppress structural findings),")
    print("          [i]gnore (not a memory file, exclude from all future scans),")
    print("          [s]kip (leave undecided, ask again next time),")
    print("          [q]uit review session.\n")

    for path, reason in candidates:
        rel = path.relative_to(area.root).as_posix()
        preview = path.read_text(encoding="utf-8", errors="replace")[:400]
        print(f"\n--- {rel} ---")
        print(f"Reason flagged: {reason}")
        print(f"Preview:\n{preview}\n{'...' if len(preview) == 400 else ''}")

        answer = input("Decision [c/i/s/q]: ").strip().lower()
        if answer == "q":
            print("Stopping review session.")
            break
        if answer == "s" or answer == "":
            continue
        if answer not in ("c", "i"):
            print("Unrecognized input, skipping.")
            continue

        decision = "custom_format" if answer == "c" else "ignore"
        note = input("Note (why this decision — shown in future audits): ").strip()
        record_decision(area.name, rel, decision, note)
        print(f"Recorded: {rel} -> {decision}")


def cmd_review_list(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    decisions = load_decisions(area.name)
    if not decisions:
        print(f"No recorded review decisions for area '{area.name}'.")
        return
    for d in decisions:
        print(f"{d.decision:15} {d.rel_path:50} ({d.reviewed_at})  {d.note}")


def cmd_review_forget(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    removed = remove_decision(area.name, args.rel_path)
    if removed:
        print(f"Removed decision for '{args.rel_path}' in area '{area.name}' — will be reviewed again.")
    else:
        print(f"No decision found for '{args.rel_path}' in area '{area.name}'.")


def cmd_review_findings(args) -> None:
    """Interactive triage for near-duplicate content and stale-but-not-
    auto-marked files — findings that otherwise resurface unchanged in
    every audit report with no way to say 'seen it, not an issue'. Distinct
    from `review` (reviewer.py's find_review_candidates), which is about a
    file's shape not cleanly fitting the canonical spec, not a content
    judgment call about two files or one file's freshness."""
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    if area.mode == "full":
        files = scan_memory_files(area.root, area_name=area.name)
    else:
        files = scan_memory_files_scoped(area.root, rules.get("memory_file_patterns", []), area_name=area.name)

    dup_decided = finding_decision_map(area.name, "duplicate")
    stale_decided = finding_decision_map(area.name, "stale")

    def dup_key(a, b) -> str:
        rel_a = a.path.relative_to(area.root).as_posix()
        rel_b = b.path.relative_to(area.root).as_posix()
        return "::".join(sorted([rel_a, rel_b]))

    dup_pairs = [(a, b, r) for a, b, r in find_duplicate_review_candidates(files, rules)
                 if dup_key(a, b) not in dup_decided]
    stale_files = [(f, reason) for f, reason in find_stale_review_candidates(files, rules)
                   if f.path.relative_to(area.root).as_posix() not in stale_decided]

    total = len(dup_pairs) + len(stale_files)
    if total == 0:
        print(f"No unreviewed duplicate/staleness findings in area '{area.name}'.")
        return

    if args.non_interactive:
        print(f"{total} finding(s) need review in area '{area.name}' "
              "(run without --non-interactive to review interactively):")
        for a, b, ratio in dup_pairs:
            print(f"  [duplicate ratio={ratio:.2f}] {a.path.name} <-> {b.path.name}")
        for f, reason in stale_files:
            print(f"  [stale] {f.path.name} — {reason}")
        return

    print(f"{total} finding(s) to review in area '{area.name}'.\n")
    print("For each: [d]ismiss (not an issue, suppress from future reports),")
    print("          [s]kip (leave undecided, ask again next time),")
    print("          [q]uit review session.\n")

    for a, b, ratio in dup_pairs:
        rel_a = a.path.relative_to(area.root).as_posix()
        rel_b = b.path.relative_to(area.root).as_posix()
        print(f"\n--- duplicate candidate (ratio={ratio:.2f}) ---")
        print(f"  {rel_a}")
        print(f"  {rel_b}")
        answer = input("Decision [d/s/q]: ").strip().lower()
        if answer == "q":
            print("Stopping review session.")
            return
        if answer == "d":
            note = input("Note (why dismissed — shown in future audits): ").strip()
            key = dup_key(a, b)
            record_finding_decision(area.name, key, "duplicate", "dismissed", note)
            print(f"Recorded: {key} -> dismissed")

    for f, reason in stale_files:
        rel = f.path.relative_to(area.root).as_posix()
        print(f"\n--- stale candidate ---")
        print(f"  {rel} — {reason}")
        answer = input("Decision [d/s/q]: ").strip().lower()
        if answer == "q":
            print("Stopping review session.")
            return
        if answer == "d":
            note = input("Note (why dismissed — shown in future audits): ").strip()
            record_finding_decision(area.name, rel, "stale", "dismissed", note)
            print(f"Recorded: {rel} -> dismissed")


def cmd_review_findings_list(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    decisions = load_finding_decisions(area.name)
    if not decisions:
        print(f"No recorded finding-review decisions for area '{area.name}'.")
        return
    for d in decisions:
        print(f"{d.category:10} {d.decision:10} {d.key:60} ({d.reviewed_at})  {d.note}")


def cmd_review_findings_forget(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    removed = remove_finding_decision(area.name, args.key, args.category)
    if removed:
        print(f"Removed decision for '{args.key}' ({args.category}) in area '{area.name}' — will be reviewed again.")
    else:
        print(f"No decision found for '{args.key}' ({args.category}) in area '{area.name}'.")


def cmd_snapshot(args) -> None:
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    backup_dir = Path(rules["paths"]["backup_dir"])
    ensure_backup_safe_for_area(area, backup_dir)
    snap = create_snapshot(area.root, backup_dir, reason=args.reason or "manual",
                            keep_last_n=rules.get("backup_retention", {}).get("keep_last_n"))
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
    ensure_backup_safe_for_area(area, backup_dir)
    zip_path = rollback(area.root, backup_dir, which=args.which, force=args.force)
    print(f"Rolled back from: {zip_path}")


def cmd_restore_file(args) -> None:
    """Undo a single unwanted file-body rewrite (e.g. a full_auto duplicate
    merge or stale marker you disagree with) without a full-area rollback —
    restores just that one file's content from a snapshot, leaving
    everything else in the area exactly as it is now."""
    rules = get_config(non_interactive=args.non_interactive)
    area = _select_area(rules, args.area)
    backup_dir = Path(rules["paths"]["backup_dir"])
    ensure_backup_safe_for_area(area, backup_dir)
    restored = restore_single_file(area.root, backup_dir, args.rel_path, which=args.which)
    print(f"Restored {restored} from snapshot ({args.which}). Other files in the area are untouched.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory Consolidator — programmatic memory audit tool")
    parser.add_argument("--non-interactive", action="store_true", help="never prompt; fail if config is ambiguous")
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="scan configured area(s) and produce findings + report per area")
    p_audit.add_argument("--area", default=None, help="only audit this area (default: all configured areas)")
    p_audit.set_defaults(func=cmd_audit)

    p_dry = sub.add_parser("dry-run", help="preview apply_safe_fixes on a disposable copy — never touches the real area")
    p_dry.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_dry.set_defaults(func=cmd_dry_run)

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

    p_cross = sub.add_parser("cross-check", help="find slug conflicts and near-duplicate content across ALL configured areas")
    p_cross.set_defaults(func=cmd_cross_check)

    p_resolve = sub.add_parser("resolve-conflicts", help="interactively resolve diverged cross-area slug conflicts into a 'memory-diverged' area")
    p_resolve.add_argument("--diverged-area", default=None, help="area name to consolidate into (default: 'memory-diverged')")
    p_resolve.set_defaults(func=cmd_resolve_conflicts)

    p_review = sub.add_parser("review", help="interactively review non-canonical .md files and record a decision")
    p_review.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_review.set_defaults(func=cmd_review)

    p_review_list = sub.add_parser("review-list", help="list recorded review decisions for an area")
    p_review_list.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_review_list.set_defaults(func=cmd_review_list)

    p_review_forget = sub.add_parser("review-forget", help="remove a review decision so the file is reviewed again")
    p_review_forget.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_review_forget.add_argument("rel_path", help="path relative to the area's root, e.g. 'sub/file.md'")
    p_review_forget.set_defaults(func=cmd_review_forget)

    p_review_findings = sub.add_parser("review-findings", help="interactively triage near-duplicate content and stale-but-not-auto-marked files")
    p_review_findings.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_review_findings.set_defaults(func=cmd_review_findings)

    p_review_findings_list = sub.add_parser("review-findings-list", help="list recorded duplicate/staleness review decisions for an area")
    p_review_findings_list.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_review_findings_list.set_defaults(func=cmd_review_findings_list)

    p_review_findings_forget = sub.add_parser("review-findings-forget", help="remove a duplicate/staleness review decision so it's reviewed again")
    p_review_findings_forget.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_review_findings_forget.add_argument("category", choices=["duplicate", "stale"])
    p_review_findings_forget.add_argument("key", help="rel_path for 'stale'; 'a.md::b.md' (sorted) for 'duplicate'")
    p_review_findings_forget.set_defaults(func=cmd_review_findings_forget)

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

    p_restore_file = sub.add_parser("restore-file", help="restore a single file's content from a snapshot, without touching anything else in the area (undo one full_auto body-rewrite)")
    p_restore_file.add_argument("--area", default=None, help="required if multiple areas are configured")
    p_restore_file.add_argument("--which", default="latest", help="timestamp of snapshot, or 'latest'")
    p_restore_file.add_argument("rel_path", help="path relative to the area's root, e.g. 'file.md'")
    p_restore_file.set_defaults(func=cmd_restore_file)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
