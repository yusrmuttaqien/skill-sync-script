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
| 5 | Import / Export | ✅ | check-gated pull/push, diff preview, link rewrite, OWUI inline flatten |
| 6 | Adopt / Rename / Delete / Batch | ✅ | adopt (write-back), rename (+cross-skill mentions), delete (synced-target report), batch, repoint |
| 7 | TUI assembly | ✅ | page-based flow, arrow-key select_menu (visref style), $EDITOR + post-edit loop, onboarding, Esc cancels everywhere |

Status legend: ⬜ not started · 🔨 in progress · ✅ done

## Backlog — gaps vs draft v2 (audit 2026-09-29)

Checked `skills-sync-project.md` against the implementation. Suggested build order:
A → B → C → D → E → F, then G–K (target fixes), then L–T (TUI/polish).

**A. ✅ Manifest last-synced hash + blob** — per skill × target: hash+blob of SKILL.md
   and each companion (= merge base). Powers drift detection, status states,
   repoint detection. (manifest.py, sync.py, status.py)
**B. ✅ Diff preview before apply** — the v1 guard (no in-TUI undo). Import/export/
   adopt show the would-be replacement diff and require confirm. (`f628525`)
**C. ✅ Exact-mirror companion set on import** — new store set = (source companions)
   ∪ (store companions still referenced by imported SKILL.md); unreferenced
   removed + listed in the diff. store.save must also drop stale files. (`20dbb72`)
**D. ✅ Link rewrite engine** — export: relative refs → absolute store paths (pi,
   Obsidian); import: abs → rel (the streamlining). Longest-first,
   token-boundary, skip URL/qualified contexts. Companions stay single-copy in
   the store; pi/Obsidian refs point at it (stop copying companions there). (`4433687`)
**E. ✅ OWUI flatten** — small companions in `<!-- file:<relpath> -->…<!-- /file -->`
   markers (base64 for binary; large → link + guide text via `hostname` /
   `open_terminal` templates), markers at end of md, re-parsed on import
   (lossless), markers structural-not-text (stripped before compare; missing
   markers + identical text → auto-restore companions). (`cbc79bc`, `fe558c0`)
**F. ✅ Adopt write-back** — adopt = import + write normalized version back to the
   target (store becomes single physical copy). Currently flag-only. (`cd7bf1e`)

**G. ✅ Obsidian wrapper pass-through** — preserve existing wrapper frontmatter
   (`status: fix`, extra fields) on export; only replace fenced content.
   Currently regenerated from config tags (loses `status`). (`543b169`)
**H. ✅ OWUI put semantics** — id new/changed (rename) → recreate (POST /create +
   DELETE /old); duplicate normalized names in target → flag both, disambiguate
   by id, user picks (list_skills keeps last today); `is_active` in scan.
   (`fe558c0`)
**I. ✅ pi scan details** — folders without SKILL.md flagged as unimportable
   candidates; unmanaged originals indexed with `+`. (`ba968b4`)
**J. ✅ Obsidian validity rule** — skill iff last top-level fence starts with
   frontmatter (today: any `*.md`). (`ba968b4`)
**K. ✅ Status states** — `+ to-add / ~ changed / ! offline / ! error` live;
   `~ paths-stale` live via D; `~ orphan` via the scan wiring (R). Text states
   + legend in the table (`ff387c9`, `52d34b9`).

**L. ✅ Repoint action** — `p` in TUI: rel→abs rewrite to current store path; status `~ paths-stale` (text differs only in store prefix).
**M. ✅ Batch in TUI** — `b`: Batch Import/Export; multi-select (space toggle,
   Enter confirm, Esc cancel); managed-only sources (unmanaged shown dimmed,
   "adopt first"); one confirm with count.
**N. ✅ Store browser** — `v` in TUI: pick skill → pick file → view.
**O. ✅ Nameless import prompt** — inline "set it" prompt; store name follows the override.
**P. ✅ Bare-filename candidates** — per-occurrence decision (list + context +
   create/rewrite/ignore menu) in scan + post-edit. (`c1e6b35`)
**Q. ✅ Onboarding** — first run: panel + $EDITOR on the generated config, then reload.
**R. ✅ Minor** — symlink-flattened warning in post_edit; `! offline`/`! error`
   cells; duplicate names flagged in scan. (duplicate_names check itself stays
   store-level; target dups surfaced via list_skills_full in scan.)

**Second audit (2026-09-29, post A–R):**
**S. ✅ Target-copy-only delete** — `d` → "Delete from target": pick skill →
pick target (synced copies only) → confirm → adapter delete. Store + other
targets untouched (cell → `exportable`).
**T. ✅ Import vs Adopt visibility** — menu descriptions: Import "target →
store · target copy untouched"; Adopt "import + take over target copy
(write-back)".

## Log

## [2026-09-29] — Session 10: store move support
**Task**: How to move the store location
**Changes**:
- `links.py` — `to_relative` accepts extra prefixes; `old_skill_prefix` extracts the embedded store skill-dir from a target text
- `status.py` — `paths-stale` now fires when the target (vs the synced blob) embeds an old store root, not only on blob-vs-target prefix mismatch
- `tui.py` — repoint strips the old root (from target text or blob) before re-anchoring at the current root
- Flow: `mv` the store dir → update `store.path` in config → status shows `paths-stale` → `p` Repoint — **one skill** or **all skills × targets** (batched)
- **Ref ignores are remembered** — "ignore" persists per skill in the manifest (`ignored_refs`); the same token won't resurface
**Lessons**: staleness is a property of the *target text vs the current root*, not just target-vs-blob — both can be stale together (identical) after a move

## [2026-09-29] — Session 9: backlog A–R sweep
**Task**: Close the draft-vs-implementation gaps (A–R)
**Changes**:
- **A+K** manifest blobs (SKILL.md + base64 companions) → drift detection; status states `in-sync/changed/unmanaged/to-add/offline/error/absent` → TUI ✓ ~ + ! —
- **B** diff preview before apply (import/export; unified diff + companion delta; no in-TUI undo — the diff is the guard)
- **C** exact-mirror companion set: referenced store companions kept, stale dropped (`store.save` mirrors the bundle)
- **D** link rewrite engine (`links.py`): rel→abs on export, abs→rel on import; token-boundary, URL/qualified skip
- **E** OWUI inline flatten: `<!-- file:<rel> [encoding:base64] [ref:external] -->` markers, lossless round-trip, large → hostname/path guide
- **F** adopt write-back: normalized store version becomes the target copy
- **G** obsidian wrapper pass-through (keeps `status: fix` etc.)
- **H** OWUI put semantics: `list_skills_full` (dups/inactive), rename = recreate (POST /create + DELETE /old)
- **I+J** unimportable folders flagged; obsidian skill = last top-level fence starts with frontmatter
- **L** repoint action + `~ paths-stale` state (store moved)
- **N** store browser (`v`); **O** nameless import prompt; **Q** first-run onboarding; **R** symlink warning, dup names in scan
- **K** status table: text states (colored) + legend (`ff387c9`); `to-add` → `exportable` label (`52d34b9`)
- **Esc** cancels at every flow step — escapable `ask_text`/`ask_confirm` (raw Esc, piped fallback), delete confirms before acting (`be94546`)
- **M** batch import/export — multi-select (space toggle), managed-only sources (`83c20d8`)
- **P** ref candidates — per-occurrence create/rewrite/ignore in scan + post-edit (`c1e6b35`)
- **All A–R items complete.**
- **S** target-copy-only delete (`d` → "Delete from target"); **T** Import/Adopt menu descriptions explicit
- **README** — user-facing overview (`a95070d`); second audit: module list + phase notes fixed (`10a8cb0`)
**Lessons**: read returns bytes / write took str — normalized at adapter boundary; store.save mirror-drop must skip SKILL.md; token regex must not absorb trailing `.` (prose "data/b.txt.")

## [2026-09-29] — Session 8: drift detection (backlog A + K)
**Task**: Audit vs draft; build A (manifest blobs) + K (status states)
**Changes**:
- `manifest.py` — targets store `blobs` (SKILL.md text + base64 companions); `set_target(..., blobs=)`, `get_blobs`, `blob_hash`
- `sync.py` — import/export record synced blobs (merge base)
- `status.py` — states `in-sync / changed / unmanaged / to-add / offline / error / absent`; drift = normalize-then-exact-compare vs blobs
- `tui.py` — cells render ✓ / ~ / + / ! / —
- `filesystem.py`, `openwebui.py` — `write_skill` accepts bytes (read/write symmetry)
- `CHANGELOG.md` — `Backlog — gaps vs draft v2` (A–R) is the work queue
**Lessons**: pre-A manifest entries have no blobs → show `+` until re-synced; ref-scan flags prose tokens that look like paths (conservative, known noise)

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

## [2026-09-29] — Session 7
**Task**: Live-target verification + TUI restyle (visref-canvas-builder reference)
**Changes (TUI)**:
- `src/tui.py` — rewritten page-based: status table + arrow-key `select_menu` (ported from visref: `▸` cursor, dim details, hint line, Esc back, non-TTY fallback), actions as menu steps (import/export/adopt/rename/delete/create/scan)
**Lessons (TUI)**:
- Page-based flow (render → select_menu → action → back) reads far better than a bare key-prompt loop

**Changes (Obsidian format)**:
- `src/obsidian.py` — `ObsidianAdapter`: note = own frontmatter (`tags:` from config `default_tags`) + entire skill (frontmatter+body) inside an adaptive backtick fence `max(3, longest_run+1)`; unwrap on read
- `src/adapter.py` — obsidian → `ObsidianAdapter`
**Lessons (Obsidian)**:
- Fence length must adapt to the content's own fences (start 3, +1 per nest) or the skill's code blocks leak
- Verified against the real `context-restore` note in the vault

**Task (orig)**: Live-target verification — fix OWUI + Obsidian scanning
**Changes**:
- `src/openwebui.py` — rewritten to the real API (spec was right, code had drifted): `/api/v1/skills/...` routes, client-provided `id` (required in SkillForm), POST update (not PUT), no `files` field (content-only skills)
- `src/filesystem.py` — `layout` param: `dir` (pi) vs `flat` (obsidian: one `<name>.md` per skill, no companions)
- `src/adapter.py` — obsidian → flat layout
- `src/tui.py` — target columns show target presence (was: presence AND manifest, so nothing showed pre-sync)
**Lessons**:
- Verify against the live API before trusting the implementation — the spec had been verified in Session 1, but the Phase 3 code re-guessed the routes from memory
- Obsidian skills are flat `.md` files, not `<name>/SKILL.md` dirs — layout is a per-target property, not a constant
- OWUI has no companion-file concept in this API; inline-flatten (deferred) is the only bridge for companions
