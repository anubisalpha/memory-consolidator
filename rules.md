# Memory Consolidator — Rules

Edit the values below to tune behavior. This file is parsed at runtime — keep the
YAML block valid. Comments (`#`) explain each rule. Nothing here is loaded into
any AI context window; it is only read by `main.py`.

```yaml
paths:
  memory_root: null          # null = prompt/auto-detect on first run, then saved to config.json
  backup_dir: "./backups"    # relative to this rules.md — must never be inside memory_root
  report_dir: "./reports"    # relative to this rules.md

duplicate_detection:
  enabled: true
  merge_threshold: 0.90      # SequenceMatcher ratio >= this => "merge candidate"
  review_threshold: 0.70     # ratio >= this (and < merge_threshold) => "review candidate"
  compare_across_types: false   # if false, only compare files with the same metadata.type

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
