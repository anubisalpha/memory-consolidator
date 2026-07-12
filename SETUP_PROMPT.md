# Setup prompt — Memory Consolidator on a new machine

Copy everything below into Claude Code (or hand it to any coding agent) on
the new computer.

---

I want to set up the `memory-consolidator` tool on this machine — a
deterministic (no model inference), Python-based audit tool for Claude
memory files. Please do the following:

**1. Check prerequisites:**
- Python 3.10+ (the code uses `X | None` union-type syntax, which requires
  it) — check with `python --version` or `python3 --version`.
- `pip` available for that interpreter.
- `git`, and SSH access configured for GitHub if cloning over SSH.
- No other services/databases needed — it's pure stdlib + `pyyaml`.

If Python is missing or older than 3.10, install/upgrade it first (e.g. via
the official installer, `pyenv`, or the OS package manager) before
continuing.

**2. Clone the repo:**
```bash
git clone git@github.com:anubisalpha/memory-consolidator.git
cd memory-consolidator
```
(Use the HTTPS URL instead if SSH isn't set up:
`https://github.com/anubisalpha/memory-consolidator.git`)

**3. Install dependencies:**
```bash
pip install -r requirements-dev.txt
```
Or use the convenience script: `scripts/setup.sh` (macOS/Linux) /
`scripts\setup.bat` (Windows) — these probe `python3`/`python`/`py` so you
don't have to guess which one is on PATH.

**4. Run the test suite to confirm the environment is healthy:**
```bash
python -m pytest -q
```
All tests should pass with no setup beyond step 3 — the suite doesn't touch
any real memory folders.

**5. Configure areas in `rules.md`:**
Open `rules.md` and edit the `areas:` list under the YAML block. At
minimum, add:
- One `mode: full` area — your dedicated Claude memory folder (e.g.
  `~/.claude/projects/<slug>/memory`). Leave `root: null` to auto-detect
  this on first run (it'll prompt and cache the answer in
  `config.local.json`), or set an explicit path.
- Optionally, one or more `mode: scoped` areas — broader project/workspace
  roots you want visibility into (memory-shaped files only, not every
  file).

If this machine is a clone of an existing setup (i.e. `rules.md` already
has areas configured from another machine), you mostly just need to let
`root: null` areas re-resolve locally — see step 6.

Also check/set:
- `paths.backup_dir` / `paths.report_dir` — must be **outside** every
  configured area's root (a hard error otherwise).
- `automation.mode` — leave as `report_only` until you've reviewed a first
  audit; see the Recommended Workflow in `README.md` before flipping to
  `apply_safe_fixes` or `full_auto`.

**6. Bootstrap and first audit:**
```bash
python main.py init --area <name>     # creates MEMORY.md + reference card if missing
python main.py audit --area <name>    # first audit — expect some noise
```
If `root: null` areas prompt for a path, confirm the auto-detected guess or
enter the correct one — it's cached in `config.local.json` (gitignored,
machine-specific) so you won't be asked again.

**7. Follow the Recommended Workflow in `README.md`** from there (audit →
review non-canonical files → re-audit → cross-check across areas if
multiple are configured). Don't enable `automation.mode: apply_safe_fixes`
or `full_auto` until you've read the "Auto-fix" section of `README.md` and
previewed the impact with `python main.py dry-run --area <name>`.

**Report back:** which areas you configured, the first audit's finding
count/compliance score per area, and anything that failed or needed a
workaround (e.g. Python version issues, path resolution problems).

---
