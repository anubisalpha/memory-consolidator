# Memory Consolidator

[![tests](https://github.com/anubisalpha/memory-consolidator/actions/workflows/tests.yml/badge.svg)](https://github.com/anubisalpha/memory-consolidator/actions/workflows/tests.yml)
[MIT licensed](LICENSE)

A portable, deterministic Python tool that audits a folder of Claude memory
files (frontmatter + `MEMORY.md` index) and reports consolidation
opportunities — duplicates, stale entries, broken links, index drift.

No model inference — all checks are programmatic (string/heuristic based),
so it runs the same way every time and costs nothing to run. Everything is
pure `pathlib`/stdlib and works identically on Windows, macOS, and Linux —
snapshot zip archives use portable (forward-slash) paths internally so a
backup taken on one OS restores correctly on another, and `rules.md` paths
accept forward slashes everywhere including Windows.

## Recommended workflow

The most value comes from running these roughly in order — later steps
depend on the noise earlier steps clear out of the way.

1. **Configure your areas** in [`rules.md`](rules.md) — at minimum your
   dedicated memory folder (`mode: full`). Add `mode: scoped` areas for any
   broader project/workspace roots you also want visibility into.
2. **First audit, per area**, starting with your dedicated memory folder:
   ```bash
   python main.py audit --area <your-full-mode-area>
   ```
   This is the ground truth — spec conformance, duplicates, broken links,
   stale entries. Fix what's cheap to fix by hand before moving on.
3. **Audit your scoped areas** and expect noise the first time:
   ```bash
   python main.py audit --area <your-scoped-area>
   ```
4. **Run the review queue** on each scoped area to clear that noise for
   good, rather than re-reading the same false positives every audit:
   ```bash
   python main.py review --area <your-scoped-area>
   ```
   Mark real-but-differently-shaped memory files `custom_format` and
   everything else `ignore`. This is a one-time cost per file — it's
   remembered from here on, in every area and on every machine that
   shares this repo.
5. **Re-audit** the scoped area — the score should jump once review
   decisions suppress the noise (in testing this went from 47 findings /
   51.9 down to 14 findings / 68.6 on one real workspace). Anything left is
   genuinely worth fixing.
6. **`map`** periodically to catch memory-shaped files that exist outside
   any configured area entirely — new projects you haven't added to
   `rules.md` yet:
   ```bash
   python main.py map --area <any-area>
   ```
7. **Re-run `audit` regularly** (weekly, or whenever memory files pile up)
   as your steady-state check — by now it should be low-noise, high-signal.
8. **If you have more than one area, run `cross-check`** to find where the
   same information has fragmented across them — that's your consolidation
   list. For the genuinely diverged ones, `resolve-conflicts` walks you
   through picking a canonical version (needs a `memory-diverged` area
   configured first).
9. **New machine?** Run `python main.py init --area <name>` once to
   bootstrap an empty memory folder, then `python main.py new-memory` to
   scaffold new entries correctly from the start. Review decisions and
   thresholds already travel with the repo via git, so a second machine
   starts from the first machine's cleared-out baseline, not from zero.

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

## Cross-check: finding a single source of truth

`audit` only looks *within* one area at a time. `python main.py cross-check`
scans every configured area together and compares them *against each
other*, which is what you need when the same information has drifted into
more than one place:

- **Slug conflicts** — the same `name:` slug used in two different areas.
  Identical content is flagged `info` ("safe to keep just one"); differing
  content is flagged `critical` ("these have diverged, pick one as
  canonical") — that's the actionable case worth acting on.
- **Cross-area duplicates** — near-identical body content across areas even
  when the slugs differ, using the same `duplicate_detection` thresholds
  `audit` uses, so the two stay consistent.
- **Overlapping area roots** — a one-time notice when one area's root is
  nested inside another's (e.g. a `scoped` area covering a whole workspace
  that happens to also contain a `full` area's dedicated memory folder).
  Files under the inner area get scanned by both, but are correctly deduped
  as the *same physical file* rather than reported as false "duplicates" —
  this notice explains why, instead of leaving it a mystery.

`cross-check` itself is report-only — it never writes anything, so there's
no `--area` flag (it needs at least two areas to compare) and no snapshot
step. It gives you the concrete evidence; `resolve-conflicts` (below) is
what acts on it.

### Resolving diverged conflicts

For the genuinely actionable case — `critical` slug conflicts where content
has diverged — `python main.py resolve-conflicts` walks each one
interactively and lets you pick which version to keep:

```bash
python main.py resolve-conflicts
python main.py resolve-conflicts --diverged-area my-custom-name   # default: "memory-diverged"
```

This requires a **dedicated `mode: full` area named `memory-diverged`**
configured in `rules.md` (or pass `--diverged-area` for a different name).
For each diverged conflict, both versions are shown side by side; picking
one:

1. Writes the chosen content into the `memory-diverged` area as the new
   single source of truth, with a dated consolidation note.
2. Rewrites **both** original files as pointer stubs referencing it there —
   preserving each file's own `name:`/`description:`/`metadata.type` so it
   still resolves correctly wherever else it's referenced (index entries,
   `[[wikilinks]]`).

Deliberately **not** a direct cross-link between the two original areas: a
pointer from area A straight into area B breaks the moment B is moved,
renamed, or deleted later. Centralizing resolved content in a folder whose
only purpose is holding consolidated memories means neither original
area's lifecycle can break the reference. Every involved area (both
originals plus `memory-diverged`) is snapshotted before anything is
written; `--non-interactive` only lists what needs resolving and never
writes. Pointer stubs are automatically excluded from future `cross-check`
runs, so a resolved conflict doesn't get re-flagged as still diverged.

## Review queue

Not every non-canonical `.md` file is noise, and the tool shouldn't guess —
some are a legitimately different (but valid) memory format from another
project; some genuinely aren't memory files at all. `python main.py review`
walks candidates one at a time (malformed files, invalid `metadata.type`,
or — for `scoped` areas — files that fail the quick shape check) and lets
you record a decision:

- **`custom_format`** — approved; future audits stop flagging its
  structure as malformed/non-canonical, but it's still scanned.
- **`ignore`** — not a memory file; excluded from all future scans entirely.

Decisions are stored in [`review_decisions.json`](review_decisions.json),
keyed by area + path relative to that area's root, and **committed to git**
(unlike `config.local.json`) since they're real judgment calls about the
workspace's content, not machine-specific paths — a second machine doesn't
have to re-review the same files.

```bash
python main.py review --area <name>          # interactive review session
python main.py review-list --area <name>     # show recorded decisions
python main.py review-forget --area <name> <rel/path.md>   # undo a decision
```

## Usage

```bash
pip install -r requirements.txt

python main.py audit                     # audit every configured area, one report each
python main.py audit --area claudecore-project   # audit just one area
python main.py snapshot --area <name>            # manually back up an area's root
python main.py list-snapshots                    # list recorded snapshots (all areas)
python main.py rollback --area <name> --which latest   # restore an area from a snapshot
python main.py init --area <name>                # bootstrap MEMORY.md + reference card on a fresh machine
python main.py new-memory --area <name> --type feedback --slug my-slug --description "..."
python main.py map --area <name>                 # find memory-shaped files scattered outside an area's root
python main.py cross-check                       # find consolidation candidates ACROSS all configured areas
python main.py resolve-conflicts                 # interactively resolve diverged conflicts into 'memory-diverged'
```

`--area` is optional whenever only one area is configured, or for `audit`
(which then runs all of them). Any area with `root: null` in `rules.md`
auto-detects/prompts on first run and saves the confirmed path to
`config.local.json` (gitignored, machine-specific, keyed per area name) so
it isn't asked again. See [`config.local.example.json`](config.local.example.json)
for the format if you want to set it up manually instead.

### Convenience scripts

[`scripts/`](scripts/) wraps the common commands for macOS/Linux (`.sh`) and
Windows (`.bat`) — same behavior either way, no `python`/`python3` guessing
required (each `.sh` probes `python3`, `python`, then `py` and uses whichever
actually runs, not just whichever is first on `PATH`):

```bash
scripts/setup.sh                 # scripts\setup.bat    — pip install deps
scripts/audit.sh [area]          # scripts\audit.bat [area]   — omit area for all
scripts/review.sh <area>         # scripts\review.bat <area> — interactive
scripts/map.sh <area>            # scripts\map.bat <area>
scripts/cross-check.sh           # scripts\cross-check.bat
scripts/resolve-conflicts.sh     # scripts\resolve-conflicts.bat
scripts/test.sh                  # scripts\test.bat     — run the pytest suite
```

The `.sh` scripts are `cd`-independent (they resolve their own location and
`cd` into the project root first), so they can be run from anywhere or
symlinked onto `PATH`.

## Configuration

All thresholds (duplicate similarity, staleness windows, index size limits,
automation mode) and the area list itself live in [`rules.md`](rules.md) —
edit the YAML block there, no code changes needed.

`external_scan.workspace_root` (used by `map` and pointer-target checking)
auto-derives from `areas` when left `null` — but only when exactly one area
has `mode: scoped`, since its root is the unambiguous choice. With zero or
multiple scoped areas it's genuinely ambiguous which one is "the workspace"
(and naively taking the common ancestor across all areas can balloon to your
entire home directory if a `full` mode area lives deep under something like
`~/.claude/projects/...`), so an explicit path is required in that case —
`rules.md` documents this inline.

## Auto-fix (`apply_safe_fixes` / `full_auto`)

Set `automation.mode: apply_safe_fixes` in `rules.md` (default is
`report_only`, which never writes anything) to let `audit` fix two specific
things automatically, in `full` mode areas only — a `scoped` area has no
single `MEMORY.md` to fix:

- `auto_fix_missing_index_entries` — appends an index line for every orphan
  file. Only ever *appends*; existing lines are never rewritten.
- `auto_fix_broken_links` — removes `MEMORY.md` lines whose target file no
  longer exists. Only ever *removes* lines that are already broken; every
  valid line is left untouched.

Both are off by default — opt in per flag. Every apply is preceded by a
snapshot (see [`backup.py`](backup.py)), and `audit` re-runs the checks
afterward in the same pass so you see the before/after score immediately.
Neither fix ever touches an individual memory file's body — only
`MEMORY.md` itself.

An area can also set `index_header` in `rules.md` — used only when
`auto_fix_missing_index_entries` creates a brand-new `MEMORY.md` (an
existing index's own header is never touched). Useful for a folder like
`memory-diverged` that should document its own purpose from the very
first automated write — see the real example in this repo's own
`rules.md`.

### Preview first with `dry-run`

Before flipping `automation.mode` to `apply_safe_fixes` for real, preview
the exact impact:

```bash
python main.py dry-run --area <name>
```

This copies the area's root to a disposable staging folder under
`backups/dryrun_<area>/` (see [`dryrun.py`](dryrun.py)), applies whichever
`auto_fix_*` flags are enabled to *that copy only*, and shows:

- the list of fixes that would apply
- a unified diff of `MEMORY.md` (before vs. after)
- the compliance score before vs. after, projected

The real area is never touched — `dry-run` works regardless of
`automation.mode`. The staging copy is left in place afterward so you can
inspect it directly (a second `dry-run` for the same area overwrites it
rather than accumulating copies). Once you're satisfied, set
`automation.mode: apply_safe_fixes` and run `audit --area <name>` for real.

## Safety

- Default mode (`report_only`) never writes to any area's root.
- Backups and reports are written to `backups/` and `reports/` inside this
  project. If a *specific area being written to* (auto-fix, manual snapshot,
  or rollback) has a root that contains this project's `backup_dir`, that
  write is refused with a hard error — a snapshot could otherwise try to
  back up itself mid-write, or rollback's delete-then-restore could delete
  the very backup it's restoring from. This check is scoped to the area
  actually being touched, not every configured area, so an unrelated area's
  misconfiguration never blocks a `--area`-targeted run.
- In `report_only` mode this same condition is only a warning, since nothing
  is written.

## Project layout

| File | Purpose |
|---|---|
| `main.py` | CLI entrypoint, loops over configured areas |
| `config.py` | Resolve each area's root, load `rules.md` |
| `scanner.py` | Parse frontmatter + `MEMORY.md` index; `quick_is_memory_file` prefilter for scoped areas |
| `discovery.py` | Workspace-wide discovery of memory-shaped files for `map` |
| `crosscheck.py` | `cross-check`: slug conflicts, duplicates, and overlap detection across all areas |
| `consolidate.py` | `resolve-conflicts`: writes the canonical file + rewrites originals as pointer stubs |
| `reviewer.py` | Finds non-canonical files needing a user decision |
| `registry.py` | Persists review decisions (`review_decisions.json`, committed to git) |
| `checks.py` | All audit checks + compliance score |
| `fixer.py` | Auto-fix logic for `apply_safe_fixes`/`full_auto` (additive-or-strictly-corrective only) |
| `dryrun.py` | `dry-run` command: preview fixes on a disposable copy + diff, never touches the real area |
| `templates.py` | Fresh-machine bootstrap + compliant file scaffolding |
| `backup.py` | Snapshot/rollback, isolated from area roots |
| `report.py` | Console + markdown report rendering, one report per area |
| `rules.md` | Area list, user-tunable thresholds, automation mode |
| `tests/` | pytest suite (incl. CLI-level `main.py` coverage) — all tests run against `tmp_path`, never your real memory folder |
| `.github/workflows/tests.yml` | CI: runs the suite on push/PR across Ubuntu/Windows/macOS × Python 3.11/3.12 |

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```
