# Changelog — skillsync

Build log + phase tracker. **Read this before working; append after every meaningful step.**
Spec: `skills-sync-project.md` (behavior source of truth). Workflow: `AGENTS.md`.

**Log entry format** (append, never overwrite user entries):

```
## [YYYY-MM-DD] — Session N
**Task**: <what was requested>
**Changes**:
- <file> — <what changed>
**Lessons**: <reusable insight, if any>
```

## Phases

| # | Phase | Status | Notes |
|---|---|---|---|
| 0 | Scaffold | ✅ | package `skillsync`, entry point, config (load/generate/onboarding) |
| 1 | Core domain | ⬜ | canonical form, name normalization, normalization pass, Checks suite |
| 2 | Store | ⬜ | layout, integrity, browser (view/edit/create + post-edit checks) |
| 3 | Adapters | ⬜ | pi, obsidian, openwebui — scan/get/put/remove per spec |
| 4 | Manifest + status | ⬜ | last-synced blobs, status table, drift detection, target-down states |
| 5 | Import / Export | ⬜ | mirror rule, diff preview, link rewrite, OWUI flatten/markers |
| 6 | Adopt / Repoint / Delete / Batch | ⬜ | ownership transfer, repoint, both deletes, batch apply |
| 7 | TUI assembly | ⬜ | rich-based paged screens, modular package, help text (Import vs Adopt) |

Status legend: ⬜ not started · 🔨 in progress · ✅ done

## Log

## [2026-09-29] — Session 1
**Task**: Bootstrap the build system
**Changes**:
- `CHANGELOG.md` — created (phase table + this log)
- `AGENTS.md` — created (DOX workflow, build conventions, verification)
- Spec finalized (`skills-sync-project.md`) after 5 sweep rounds; OWUI API verified live against v0.11.4
- OWUI API key created (`sk-` + 32 hex, Settings → Account → API keys); admin global toggle enabled
- Phase plan established above

## [2026-09-29] — Session 2
**Task**: P0 — scaffold package, entry point, config
**Changes**:
- `pyproject.toml` — project metadata, `skillsync` entry point, rich dependency
- `skillsync/__init__.py`, `skillsync/__main__.py` — package + entry point (`--version`, `--config`, `--generate-config`)
- `skillsync/config.py` — defaults (from spec), deep-merge load, auto-generate on first run, generate-config text with descriptions
- `requirements.txt` — first real deps (rich 15.0.0 + transitive); editable self-ref filtered out
- `AGENTS.md` — uniform commit format `P<N>: <task>`; freeze command updated
**Lessons**:
- Config file = `config.json` in the store dir (spec left filename open); explicit `--config` overrides
- Onboarding prompt flow (target fill-in) deferred to Phase 7 with the TUI; Phase 0 auto-generates defaults

## [2026-09-29] — Session 3
**Task**: Restructure to bare-minimum layout + commit format change
**Changes**:
- Flat layout: `src/**` modules (no nested package), root-level `__init__.py`, generated `config.json` at project root
- `pyproject.toml` — entry point `src.__main__:main`, packages find `src*`
- `src/__main__.py` — version from importlib.metadata (no cross-package import)
- `src/config.py` — default config path = project root (was store dir; spec updated)
- `AGENTS.md` — conventional commit format (`feat:/fix:/chore:/docs:/refactor:`); install via `venv/bin/pip` directly (not `uv pip`)
- `.gitignore` — fixed (venv/, *.egg-info/, __pycache__/, config.json — config holds the API key)
**Lessons**:
- Appending to .gitignore without a trailing newline corrupts the previous line — check after manual user edits
- `config.json` gitignored: generated artifact + secret; fresh clone auto-generates it

## [2026-09-29] — Session 4
**Task**: Drop project/packaging setup — plain venv + `python -m src`
**Changes**:
- Removed `pyproject.toml` + editable install (kills `skillsync.egg-info` at the source)
- `requirements.txt` — plain deps only (rich + transitive), no `-e` refs
- `skillsync.py` — root entry script; run = `source venv/bin/activate && python skillsync.py [flags]`
- `AGENTS.md` — run/install lines updated
**Lessons**:
- `pip uninstall` needs `-y` in non-tty shells (prompts → EOFError)
- `python -m src` works off the PEP 420 namespace package — no `src/__init__.py` needed
- Version now reports `0.0.0+local` (importlib.metadata fallback, no installed dist) — acceptable
