# Memory Consolidator — Rules

Edit the values below to tune behavior. This file is parsed at runtime — keep the
YAML block valid. Comments (`#`) explain each rule. Nothing here is loaded into
any AI context window; it is only read by `main.py`.

```yaml
paths:
  backup_dir: "./backups"    # relative to this rules.md — must never be inside any area's root
  report_dir: "./reports"    # relative to this rules.md

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
    root: "C:/Users/marca/claudecore"
    mode: scoped
  - name: dot-claude
    root: "C:/Users/marca/.claude"
    mode: scoped

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
  workspace_root: "C:/Users/marca/claudecore"   # root searched for pointer targets

automation:
  mode: "report_only"        # report_only | apply_safe_fixes | full_auto
  auto_fix_missing_index_entries: false   # only used in apply_safe_fixes / full_auto
  auto_fix_broken_links: false            # only used in apply_safe_fixes / full_auto
  require_backup_before_apply: true       # hardcoded safety net, not actually togglable in code

reporting:
  keep_last_n_reports: 20    # older reports auto-pruned (reports only, never backups)
```

## Notes

- `automation.mode` is the master switch:
  - `report_only` — default. Never writes to `memory_root`.
  - `apply_safe_fixes` — may auto-fix index entries / broken links, always preceded by a backup.
  - `full_auto` — reserved for future use (acting on duplicates/staleness too). Still always backed up.
- Backups and reports live in this project folder, never inside `memory_root`, so they
  can never be picked up by anything that loads `MEMORY.md` into context.
