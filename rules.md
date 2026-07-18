# Memory Consolidator — Rules

Edit the values below to tune behavior. This file is parsed at runtime — keep the
YAML block valid. Comments (`#`) explain each rule. Nothing here is loaded into
any AI context window; it is only read by `main.py`.

```yaml
paths:
  # Outside claudecore entirely — claudecore-project's root IS the whole
  # claudecore tree, so anything under "./backups" (relative to this
  # rules.md, which lives inside claudecore) always conflicted with that
  # area's write safety check. Moved out once so apply_safe_fixes/
  # resolve-conflicts/rollback can actually run against claudecore-project.
  # "~" expands to the current user's home dir on any machine — do not
  # hardcode an absolute per-user path here (this file is checked into git).
  backup_dir: "~/.memory-consolidator-data/backups"
  report_dir: "~/.memory-consolidator-data/reports"

areas:
  # Each area is one root the tool audits independently (its own report, its
  # own findings). Two modes:
  #   full — this root IS a dedicated memory folder; every *.md under it
  #          (recursively) is treated as a memory file candidate.
  #   scoped — this root is a broader area (a whole project or workspace);
  #            only files matching memory_file_patterns are treated as
  #            memory candidates, everything else (READMEs, docs, session
  #            files, etc.) is ignored rather than misclassified.
  - name: claude-auto-memory
    root: null              # null = auto-detect on first run, then saved to config.local.json
    mode: full
  - name: claudecore-project
    root: "../.."      # this project lives at claudecore/projects/memory-consolidator, so "../.." is claudecore's root
    mode: scoped
  - name: dot-claude
    root: "~/.claude"
    mode: scoped
  - name: memory-diverged
    root: "../../memory-diverged"    # i.e. claudecore/memory-diverged
    mode: full
    index_header: |
      # Memory Index — Consolidation Staging Area

      This folder holds content consolidated from diverged cross-area memories
      (see `projects/memory-consolidator/`, `resolve-conflicts` command). It is
      NOT part of Claude's auto-loaded memory system — nothing here is read
      automatically by any session. Reference these files manually/explicitly
      if you need the full history behind a consolidation decision.

memory_file_patterns:
  # Used by `mode: scoped` areas and by `map`, to decide what counts as a
  # memory file candidate outside a dedicated memory folder.
  - "**/MEMORY.md"
  - "**/CLAUDE_MEMORY.md"
  - "**/*_memory.md"
  - "**/memory/**/*.md"

duplicate_detection:
  enabled: true
  merge_threshold: 0.90      # SequenceMatcher ratio >= this => "merge candidate"
  review_threshold: 0.70     # ratio >= this (and < merge_threshold) => "review candidate"
  compare_across_types: false   # if false, only compare files with the same metadata.type
  max_files_for_pairwise: 800   # above this file count, skip pairwise comparison (O(n^2), too slow for area-wide scans)
  min_body_length_for_comparison: 20   # bodies shorter than this (after stripping) are skipped — two trivially
                                        # short/empty bodies are "100% similar" by pure string ratio without being
                                        # meaningfully duplicate content

staleness:
  enabled: true
  likely_stale_days: 90      # absolute past date found in body, no corroborating recent memory
  probably_dead_days: 180    # absolute past date found in body, stronger flag
  mtime_fallback_days: 365   # filesystem mtime fallback signal, lower confidence

index_health:
  max_line_length: 150       # MEMORY.md index lines longer than this get flagged
  warn_line_count: 160       # index line count warning threshold
  critical_line_count: 200   # lines beyond this are truncated per project convention

file_health:
  max_body_lines: 150        # memory files longer than this may need splitting
  require_frontmatter: true  # flag files missing name/description/metadata.type

spec_conformance:
  # Enforces the actual memory-authoring spec (four types, Why/How structure,
  # kebab-case slugs) rather than just index/link hygiene.
  require_why_how_for_feedback_and_project: true   # see check_why_how_structure
  require_valid_type: true                         # metadata.type must be user|feedback|project|reference
  require_kebab_case_slug: true                     # name: must be kebab-case and match filename

description_quality:
  min_length: 15              # descriptions shorter than this are flagged as too generic

code_derivable_check:
  enabled: false               # off by default: heuristic-only, prone to false positives
  code_line_ratio_threshold: 0.5   # fraction of body that looks like paths/code before flagging

external_scan:
  # For "pointer only" memories whose description/body says
  # "full details in `some/path.md`" — that target usually lives in a
  # different area's root, so the normal dead-link check can't see it.
  enabled: true
  # null = auto-derive from `areas`, but ONLY when exactly one area has
  # mode: scoped (its root is used directly — see derive_workspace_root in
  # config.py). With zero or multiple scoped areas — as here, we have two
  # (claudecore-project, dot-claude) — it's ambiguous which one should be
  # "the workspace", so an explicit override is required; leaving this null
  # in that case disables map/pointer-target checking rather than guessing
  # something overly broad (e.g. never the common ancestor across areas —
  # that can balloon to the whole home directory and turn `map` into an
  # accidental full-disk walk).
  workspace_root: "../.."    # i.e. claudecore's root — kept explicit since we have two scoped areas (ambiguous for auto-derive)

automation:
  mode: "full_auto"        # report_only | apply_safe_fixes | full_auto
  # These two flags take effect in 'full' mode areas (a 'scoped' area has no
  # single MEMORY.md index to fix) under apply_safe_fixes/full_auto. Opt in
  # per flag.
  auto_fix_missing_index_entries: true   # append an index line for each orphan file (never rewrites existing lines)
  auto_fix_broken_links: false            # remove MEMORY.md lines whose href no longer exists (never touches valid lines)
  # These three flags ONLY take effect under full_auto (never apply_safe_fixes)
  # — see fixer.py's module docstring for why they're allowed to touch
  # individual file bodies where the two flags above never do.
  auto_fix_mark_stale: true                # prepend a visible staleness marker to flagged files (never removes content)
  auto_fix_merge_exact_duplicates: true    # turn byte-identical duplicate files into pointer stubs (exact matches only)
  auto_fix_slug_mismatch: true             # rename file / normalize frontmatter name so both agree on one kebab-case slug (skips on collision)
  require_backup_before_apply: true       # hardcoded safety net, not actually togglable in code

reporting:
  keep_last_n_reports: 20    # older reports auto-pruned (reports only, never backups)

backup_retention:
  keep_last_n: 3             # per-area: newest snapshot + 2 older ones kept, rest auto-pruned after each new snapshot
```

## Notes

- `automation.mode` is the master switch:
  - `report_only` — default. Never writes to any area's root.
  - `apply_safe_fixes` — for `full` mode areas only, gated per-flag by
    `auto_fix_missing_index_entries` / `auto_fix_broken_links`, always
    preceded by a snapshot. Both fixes are additive-or-strictly-corrective
    (see `fixer.py`): missing-index-entries only *appends* lines, and
    broken-links only *removes* lines whose target no longer exists —
    neither ever rewrites or reinterprets existing valid content, and
    neither touches individual memory files, only `MEMORY.md` itself.
  - `full_auto` — runs everything `apply_safe_fixes` does, plus three more
    fixes gated by `auto_fix_mark_stale` / `auto_fix_merge_exact_duplicates` /
    `auto_fix_slug_mismatch`. Unlike the two `apply_safe_fixes` fixes, these
    touch individual memory files' bodies, not just `MEMORY.md` — but each is
    scoped to stay content-preserving or narrowly bounded: `mark_stale_files`
    only prepends a visible marker (never removes text) to files matching
    `check_staleness`'s date-based 'stale' signal (not the low-confidence
    mtime fallback), `merge_exact_duplicates` only rewrites a file into a
    pointer stub when its body is byte-identical to another file's
    (ratio == 1.0) — anything short of an exact match (the near-duplicate
    thresholds `check_duplicates` reports) is left as a judgment call for a
    human, same as cross-area conflicts are left to `resolve-conflicts` —
    and `fix_slug_mismatches` only renames a file / normalizes its `name:`
    field so both agree on one kebab-case slug, skipping (not forcing) any
    case where the target filename would collide with another real file.
    Only applies to `full` mode areas (a `scoped` area's root can be an
    entire workspace, and never gets any snapshot/write at all — see
    `main.py`'s `cmd_audit`). Still always backed up first.
- Backups and reports live in this project folder, never inside any area's
  root, so they can never be picked up by anything that loads `MEMORY.md`
  into context.
- `backup_retention.keep_last_n` prunes snapshots per-area (by each entry's
  `memory_root` in `manifest.json`), the same way `reporting.keep_last_n_reports`
  prunes reports per-area. Applied after every `create_snapshot`/
  `create_targeted_snapshot` call, so it also covers manual `backup` runs.
