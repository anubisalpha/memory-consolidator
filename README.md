# Memory Consolidator

A portable, deterministic Python tool that audits a folder of Claude memory
files (frontmatter + `MEMORY.md` index) and reports consolidation
opportunities — duplicates, stale entries, broken links, index drift.

No model inference — all checks are programmatic (string/heuristic based),
so it runs the same way every time and costs nothing to run.

## Usage

```bash
pip install pyyaml

python main.py audit              # scan, print findings, write reports/audit_*.md
python main.py snapshot           # manually back up the memory folder
python main.py list-snapshots     # list recorded snapshots
python main.py rollback --which latest   # restore from a snapshot
```

On first run it will try to auto-detect your memory folder and ask you to
confirm or override the path. The chosen path is saved to
`config.local.json` (gitignored, machine-specific) so it isn't asked again.
See [`config.local.example.json`](config.local.example.json) for the format
if you want to set it up manually instead.

## Configuration

All thresholds (duplicate similarity, staleness windows, index size limits,
automation mode) live in [`rules.md`](rules.md) — edit the YAML block there,
no code changes needed.

## Safety

- Default mode (`report_only`) never writes to your memory folder.
- Backups and reports are written to `backups/` and `reports/` inside this
  project, never inside the memory folder — so they can't be picked up by
  anything that loads your memory index into an AI context window.
- Any future auto-fix mode always snapshots the memory folder first.

## Project layout

| File | Purpose |
|---|---|
| `main.py` | CLI entrypoint |
| `config.py` | Locate/persist memory root, load `rules.md` |
| `scanner.py` | Parse frontmatter + `MEMORY.md` index |
| `checks.py` | All audit checks |
| `backup.py` | Snapshot/rollback, isolated from memory root |
| `report.py` | Console + markdown report rendering |
| `rules.md` | User-tunable thresholds and automation mode |
