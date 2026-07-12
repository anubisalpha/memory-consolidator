# Memory Consolidator

A portable, deterministic Python tool that audits a folder of Claude memory
files (frontmatter + `MEMORY.md` index) and reports consolidation
opportunities — duplicates, stale entries, broken links, index drift.

No model inference — all checks are programmatic (string/heuristic based),
so it runs the same way every time and costs nothing to run.

## Areas

`rules.md` defines a list of **areas** — each one an independent root the
tool audits separately, with its own report and its own compliance score.
Two modes per area:

- **`full`** — the root IS a dedicated memory folder (like `.claude/.../memory`).
  Every `*.md` under it is a memory-file candidate; missing frontmatter is a
  real finding.
- **`scoped`** — the root is a whole project or workspace, not a memory
  folder. Only files matching `memory_file_patterns` (`MEMORY.md`,
  `CLAUDE_MEMORY.md`, `*_memory.md`, anything under a `memory/` folder) are
  even considered, and a cheap peek at the first ~1KB (`quick_is_memory_file`
  in `scanner.py`) filters out path-matched files that aren't really memory
  files (e.g. a plugin's `README.md` that happens to live in a folder named
  `memory`) before paying for a full parse. This keeps `scoped` audits fast
  and free of false "malformed" findings on ordinary docs.

## Usage

```bash
pip install pyyaml

python main.py audit                     # audit every configured area, one report each
python main.py audit --area claudecore-project   # audit just one area
python main.py snapshot --area <name>            # manually back up an area's root
python main.py list-snapshots                    # list recorded snapshots (all areas)
python main.py rollback --area <name> --which latest   # restore an area from a snapshot
python main.py init --area <name>                # bootstrap MEMORY.md + reference card on a fresh machine
python main.py new-memory --area <name> --type feedback --slug my-slug --description "..."
python main.py map --area <name>                 # find memory-shaped files scattered outside an area's root
```

`--area` is optional whenever only one area is configured, or for `audit`
(which then runs all of them). Any area with `root: null` in `rules.md`
auto-detects/prompts on first run and saves the confirmed path to
`config.local.json` (gitignored, machine-specific, keyed per area name) so
it isn't asked again. See [`config.local.example.json`](config.local.example.json)
for the format if you want to set it up manually instead.

## Configuration

All thresholds (duplicate similarity, staleness windows, index size limits,
automation mode) and the area list itself live in [`rules.md`](rules.md) —
edit the YAML block there, no code changes needed.

## Safety

- Default mode (`report_only`) never writes to any area's root.
- Backups and reports are written to `backups/` and `reports/` inside this
  project. If an area's root happens to contain this project (e.g. auditing
  your whole workspace root), that's flagged as a warning in `report_only`
  mode and a hard error in any write mode, since a snapshot could otherwise
  try to back up itself mid-write.
- Any future auto-fix mode always snapshots the area's root first.

## Project layout

| File | Purpose |
|---|---|
| `main.py` | CLI entrypoint, loops over configured areas |
| `config.py` | Resolve each area's root, load `rules.md` |
| `scanner.py` | Parse frontmatter + `MEMORY.md` index; `quick_is_memory_file` prefilter for scoped areas |
| `discovery.py` | Workspace-wide discovery of memory-shaped files for `map` |
| `checks.py` | All audit checks + compliance score |
| `templates.py` | Fresh-machine bootstrap + compliant file scaffolding |
| `backup.py` | Snapshot/rollback, isolated from area roots |
| `report.py` | Console + markdown report rendering, one report per area |
| `rules.md` | Area list, user-tunable thresholds, automation mode |
| `tests/` | pytest suite — all tests run against `tmp_path`, never your real memory folder |

## Tests

```bash
pip install pytest
python -m pytest tests/ -q
```
