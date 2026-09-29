# AGENTS.md

## Project

`skillsync` — a Python TUI that centralizes skill management across three peer
targets (pi agent, OpenWebUI, Obsidian vault) through a local store acting as
the normalization hub. No single source of truth; import-by-replace both
directions. Full spec: `skills-sync-project.md` (behavior source of truth).

## DOX Workflow

- **Before editing**: read this file + `CHANGELOG.md` (last entries) + the
  spec sections relevant to the task
- **After editing**: append to `CHANGELOG.md` (Task/Changes format) + update
  the phase table in it
- **Do not rely on memory**: re-read this chain in the current session before
  editing
- Spec changes (new decisions) go into `skills-sync-project.md`, not here

## Root Ownership

- `CHANGELOG.md` — progress log + phase tracker, human + model editable;
  **the `Backlog — gaps vs draft` section is the work queue** (items A–R,
  build order A→B→C→D→E→F then G–K, L–T; check items off as they land).
  **Status: A–R complete (session 9); S–T open (second audit).**
- `AGENTS.md` — this file
- `README.md` — user-facing overview (run, config, TUI keys)
- `skills-sync-project.md` — spec (edit only when a behavior decision changes)

## Build Conventions

- Package `skillsync`, entry point `skillsync`, modular (one module per concern)
- TUI: rich-based, paged screens (style ref: visref-canvas-builder)
- Every validation check must be registered in the spec's Checks suite and
  wired to its triggers (meta-rule from the spec)
- Verify against real targets when possible (OWUI at localhost:30001,
  pi at `~/.pi/agent/skills/`)

## Environment & Dependencies

- **No project/packaging setup** — no pyproject install; the repo root is
  the app. Run: `source venv/bin/activate && python skillsync.py [flags]`
  (root entry script → `src/__main__.main`)
- Venv: `venv/` (Python 3.12); **install with `venv/bin/pip` directly**
  (not `uv pip`) to avoid permission prompts
  (`venv/bin/pip install -r requirements.txt`)
- `requirements.txt` is the dependency record: **regenerate it in the same
  commit that changes dependencies** (`venv/bin/pip freeze | grep -v "^pip" > requirements.txt`)

## Commit Conventions

- **Commit at worthy checkpoints and at every phase boundary** — each
  commit = a restorable state, paired with its CHANGELOG entry
- **Conventional format**: `feat: …` · `fix: …` · `chore: …` ·
  `docs: …` · `refactor: …` — imperative, one line; the CHANGELOG entry
  carries the detail (1:1 mapping, `git log` + changelog tell the same story)
- No commit for trivial in-progress state; a checkpoint is worthy when the
  last logged step is complete and verified

## Modules (src/)

`config` load/generate · `name` kebab-case · `normalize` idempotent text pass ·
`canonical` Bundle + SKILL.md parse/serialize · `checks` the suite + triggers ·
`store` local hub · `filesystem` dir adapter (pi) · `obsidian` vault adapter ·
`openwebui` HTTP adapter · `links` rel↔abs rewrite · `adapter` factory ·
`manifest` sync.json · `status` the join · `sync` import/export ·
`operations` adopt/rename/delete/batch · `tui` rich UI · `__main__` entry

## Verification

- `source venv/bin/activate && python skillsync.py --help` (entry works)
- Config round-trip: generate → load → defaults intact
- No test framework in v1 — verify against the real local targets
