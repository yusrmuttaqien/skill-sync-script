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
| 1 | Core domain | ✅ | canonical form, name normalization, normalization pass, Checks suite |
| 2 | Store | ✅ | layout, integrity, template create, post-edit checks, companion modes |
| 3 | Adapters | ✅ | filesystem (pi/obsidian) + openwebui HTTP — list/read/write/delete/create |
| 4 | Manifest + status | ✅ | sync.json source of truth, status join, target-down resilience |
| 5 | Import / Export | ✅ | check-gated pull/push; **deferred**: diff preview, link rewrite, OWUI inline flatten |
| 6 | Adopt / Rename / Delete / Batch | ✅ | adopt, rename (+cross-skill mentions), delete (synced-target report), batch; **deferred**: repoint |
| 7 | TUI assembly | ✅ | rich status view, key-driven actions, $EDITOR + post-edit prompt loop; **deferred**: paged screens, onboarding prompts |

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

## [2026-09-29] — Session 5
**Task**: P1 — core domain (canonical form, name, normalization, Checks suite)
**Changes**:
- `src/name.py` — kebab-case normalization (Unicode letters kept), legal charset check
- `src/normalize.py` — idempotent pass: LF, BOM strip, single trailing \n, `./`-strip at path-token starts
- `src/canonical.py` — Bundle (frontmatter+body+companions), parse/serialize SKILL.md (PyYAML), name/description-first key order
- `src/checks.py` — canonical suite: 7 checks registered with triggers (post_edit/import/scan/rename_delete), `run_checks(trigger, ctx)`
- `requirements.txt` — + PyYAML
**Lessons**:
- `_` is a `\w` char — token split needs `[^\w]+|_+` to kebab-ize `Cool_Skill`
- Normalization guarantees exactly one trailing \n (test expectations must include it)
- Checks take a `Context` dataclass — triggers select which checks run; issues are data, prompts are the TUI's job (Phase 7)

## [2026-09-29] — Session 6
**Task**: P2–P7 — Store, Adapters, Manifest+Status, Import/Export, Operations, TUI
**Changes**:
- `src/store.py` — store layout, companion enumeration (ignore patterns, symlink flatten, modes), template create, post-edit checks, `context_for`
- `src/filesystem.py` — generic directory adapter (pi/obsidian); `src/openwebui.py` — HTTP adapter (official /v1/skills, b64 files, 409→id create, status)
- `src/adapter.py` — type-based `make_adapter` from config
- `src/manifest.py` — sync.json load/save + accessors (single source of truth)
- `src/status.py` — store × targets × manifest join; per-target failure isolation
- `src/sync.py` — import (normalize + import checks, strict gate) / export (canonical write, auto-create)
- `src/operations.py` — adopt, rename (dir + frontmatter + cross-skill mentions), delete (reports synced targets), batch
- `src/tui.py` — rich status table, key-driven actions (i/e/a/r/d/c/s/q), $EDITOR launch + edit-until-clean prompt loop
- `src/__main__.py` — default run = TUI
- `src/checks.py` — fixes: `None` description, `store_integrity` compares frontmatter name
- `src/normalize.py` — `./` strip only when a path char follows (quoted `./` survives)
**Lessons**:
- `str(None)` = `"None"` (truthy) — empty YAML values need explicit `None` handling
- Integrity checks must compare against frontmatter, not the bundle name (which may have been set to the dir name)
- Adapter reads return bytes; sync layer tolerates str (test fakes + leniency)
- One unreachable target must not crash status — isolate `list_skills()` failures per target
- Template example refs must not look like real paths (`scripts/<file>.sh`) or the ref scan flags the template itself
