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

- `CHANGELOG.md` — progress log + phase tracker, human + model editable
- `AGENTS.md` — this file
- `skills-sync-project.md` — spec (edit only when a behavior decision changes)

## Build Conventions

- Package `skillsync`, entry point `skillsync`, modular (one module per concern)
- TUI: rich-based, paged screens (style ref: visref-canvas-builder)
- Every validation check must be registered in the spec's Checks suite and
  wired to its triggers (meta-rule from the spec)
- Verify against real targets when possible (OWUI at localhost:30001,
  pi at `~/.pi/agent/skills/`)

## Verification

- `python -m skillsync --help` (entry point works)
- Config round-trip: generate → load → defaults intact
- No test framework in v1 — verify against the real local targets
