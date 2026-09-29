# Skills Sync — Draft v2 (peer model)

Created: 2026-09-29
Status: DRAFT — brainstormed in session, not yet implemented

## Goal

A Python TUI that centralizes skill management across three **peer** targets.
No single source of truth with authority — each target can be imported from
(import-by-replace) or exported to. All transfers route through a local
**store** that acts as the normalization hub.

Targets:

| Target | Role |
|---|---|
| pi coding agent (`~/.pi/agent/skills/`) | consumer |
| OpenWebUI (skills API) | consumer |
| Obsidian vault (`📍 Guides/ai/skills/`) | consumer / backup |

## Architecture: peer model + normalization hub

- No target is authoritative. "Import-by-replace from A to B" = two operations:
  1. **Import** (target → store): read bundle → normalize → replace in store
  2. **Export** (store → target): read bundle → transform → replace in target
- The store is a working set in canonical form, not an owned SoT.
- v1 semantics: **replace**, always with a diff preview before applying.
  No 3-way merge in v1 (see Merge strategy).
- **Replace = exact mirror**, including the companion set. For an adopted
  skill the target holds no companions (pi = SKILL.md only, Obsidian = one
  md, OWUI = inline), so the mirror is reference-driven: **new store set =
  (source's local companions) ∪ (store companions still referenced by the
  imported SKILL.md)**; unreferenced ones are removed and listed in the diff
  preview. "Fewer" can only arrive via the text (a ref deleted) or OWUI
  marker loss — never via the pi/Obsidian file set. "More" = new local files
  (typically pi-agent-created).
- **No in-TUI undo.** The diff preview is the guard; restore = git
  (user-managed) on the target or store, then re-import/re-export as needed.

### Store

- Location: user-configured (default suggestion: `~/Documents/skill-sync/store`)
- TUI treats it as a **plain directory** — whether it's git-tracked is the
  user's concern, invisible to the TUI
- Layout: `store/skills/<name>/SKILL.md` + companion files — the store holds
  the **complete bundle** (SKILL.md included), in canonical form
- **File modes are preserved** on every companion copy (store in/out) — exec
  bits on scripts must survive
- **Companion enumeration ignores** the config `ignore` patterns (default:
  dotfiles `.*`) — no `.DS_Store` or hidden files become companions
- **Store edits are validated on editor close** (parseable frontmatter,
  `name` present + legal charset); invalid → "fix now / keep as-is" prompt,
  same as import
- Single physical copy of every companion file lives here; all targets
  reference it (the TUI is the streamliner)

### Canonical form (store format)

- Links inside SKILL.md are **relative to the skill directory** (portable)
- Frontmatter: `name`, `description`, … plus **unknown fields pass through**
  (kept, inert — pi ignores unknown YAML fields, Obsidian sees them as plain
  fenced text, OWUI as markdown text). The TUI normalizes structure, not
  vocabulary.
- **Known** target-specific fields are stripped on import (explicit list per
  target), re-added on export from config; everything NOT on the list passes
  through:
  - Obsidian: `tags`, `status` wrapper frontmatter
  - OWUI: export date headers, other export artifacts
  - pi: (explicit list, starts empty — e.g. `disable-model-invocation` would
    be added here only if we decide pi should own it)
- Skill identity = frontmatter `name`

## Companion (supporting) files

Single physical copy lives in the store. SKILL.md clones in targets reference
it; they are regenerable from the canonical source.

| Target | Link strategy |
|---|---|
| pi | SKILL.md copy in the pi skill folder; refs rewritten to **absolute store paths**. Companion files stay in the store (no symlinks, no copies) |
| Obsidian | rewrite relative → **absolute** at export. Files stay in the store, vault md points to them |
| OpenWebUI | **flatten** into the single md (see below). No filesystem access at consumption time |

### Link detection & rewrite

References in SKILL.md are **not uniform** (prose, backticks, markdown links,
code fences…). The TUI does not parse syntax — it searches for known files:

1. The bundle defines the set of companion relative paths.
2. **Export**: for each known relpath (longest-first, token-boundary match),
   replace every occurrence with the absolute store path.
3. **Import**: inverse — replace `<store_root>/<skill>/<relpath>` → `<relpath>`.
   Every import normalizes absolute refs back to relative (the streamlining).
4. Validation from the same scan — run at **scan time** (not only import):
   - store companion **not referenced** by the target's normalized text →
     `~ orphan: <file>` (works for every target — pi/Obsidian paragraph
     edits, OWUI inline-block or guide-section deletion alike). The drop
     itself happens only at import (mirror rule, diff-confirmed); until
     then the file is safe in the store
   - relative-path-looking token with no matching file → warning (broken ref)
   - absolute path with a stale store root → `~ paths-stale` (repoint case)

Convention (the only one): references must be written as **exact relative
paths from the skill dir** (`scripts/setup.sh`, not `$VAR/…` or bare
`setup.sh`). TUI lints for violations. Bare-filename refs: reported as
candidates with per-occurrence decision (list + context + checkbox, apply
selected) — same find-and-replace engine, confirmation layer only.

**Matching rule**: only *local filesystem* references are rewritten —
skip occurrences in URL/qualified context (preceded by alphanumeric, `/`,
or `:`), so `https://…/scripts/setup.sh` and `git@host:…` are never touched.
External references are out of scope unless a future case demands them.

The link scan re-runs on **every import** — a pulled-in SKILL.md may
reference companions under paths the store doesn't know yet.

### Flatten policy (OWUI export)

| Companion | Small (≤ threshold, e.g. 64 KB) | Large |
|---|---|---|
| text / md / json / sh / csv… | inline raw in `<!-- file:<relpath> -->` … `<!-- /file -->` markers | inline raw |
| binary | embed **base64** in markers (lossless, machine-independent) | **link to store path** + guide text |

- Markers are re-parsed on import → round-trip is lossless
- Markers/sections go at the **end** of the md so humans editing in the OWUI
  UI don't break the head of the skill
- The "attach on demand" guide text applies **only** to non-flattenable
  (large) companions; small ones are always embedded regardless

### Guide text for large companions (per target)

OWUI, `open_terminal: true`:
```
## Companion: assets/logo.png (12 MB)
Available on `<hostname>` at <store-abs-path> —
open it via Open-Terminal.
```

OWUI, `open_terminal: false`:
```
## Companion: assets/logo.png (12 MB)
Not included in this skill. If the task needs it, ask the user to attach
<store-abs-path> (on machine `<hostname>`).
```

pi / Obsidian — no guard text, plain path:
```
Companion file: <store-abs-path>
```

## Keeping links up to date

No separate link registry. Two mechanisms:

1. **Idempotent push**: every export regenerates absolute links from the
   store's current root. A moved store folder self-heals on next push.
2. **Status scan auto-detects staleness**: parse each target's SKILL.md,
   extract embedded absolute paths, compare against expected
   (store root + relpath). Mismatch → flag `~ paths-stale`; one **repoint**
   action fixes it.

## Targets

Targets are **configurable** (named entries in config). v1 ships three built-in
types; no UI to add more, but import/export to the store goes through one
uniform adapter interface, so a new target with the same behavior = one new
adapter type:

```
Adapter:
  scan()   → inventory (name, identity, hash, state)
  get(name) → raw bundle as found in the target
  put(name, bundle) / remove(name)
  format transforms: canonical ↔ target representation
```

### OpenWebUI

- Access: official skills API (`/api/v1/skills/`), **official API key**
  created in OWUI (Settings → Interface → API Keys, `sk-owui-…`),
  `Authorization: Bearer`. No JWT minting.
- **Rigid**: what the API lists *is* the skill inventory — no stray-entry
  problem
- All current OWUI skills are single-file (no inlined-companion migration needed)
- **Markers/guide sections are structural, not text**: stripped before
  comparison, so deleting a guide section is not a content change. Edit
  *inside* a marker block = content edit (imported); block deleted/missing
  = companion dropped (orphan → mirror flow).
- **Marker fragility**: a human editing in the OWUI UI may delete/mangle a
  `<!-- file:… -->` block. Import with missing/unclosed markers:
  - skill text (markers stripped) **identical** to store → companions
    **auto-restored** from the store (nothing was actually lost)
  - skill text **changed** → normal import (replace); companions not
    recovered, **warned in the import preview** (re-export restores them)
- The OWUI model can edit **store files directly via Open-Terminal** (the
  pi-like birth/edit flow); the TUI picks it up on the next scan and normal
  export propagates it. The OWUI DB copy is a cache the model never needs
to touch

### pi

- **scan** (read-only): inventory of `~/.pi/agent/skills/` — name, hash,
  companion list, managed?. Unmanaged originals are **untouched** (never
  written by the TUI) but indexed; they appear in TUI with `+`
- **Rigid**: a folder without SKILL.md is an unimportable candidate —
  flagged, never auto-adopted
- Shape: folder named after the skill, containing SKILL.md. Companion files
  are NOT copied — SKILL.md refs point at the store by absolute path

### Adopt (generic, any target)

Adopt = bringing an unmanaged skill under management. Same four steps for
every target type:

1. read the bundle from the target
2. normalize to canonical form
3. save in the store (now managed)
4. write the normalized version back to that target (the copy becomes
   TUI-generated; drift detection now has a baseline)

Import vs Adopt: **import = content transfer only** (target untouched —
the right tool for pulling drift from a managed skill). **Adopt = import +
ownership transfer** — the write-back is what makes the store the single
physical copy (e.g. pi folder loses its local companions, refs point at the
store). Importing an unmanaged skill *without* adopting it leaves two
physical companion copies = future drift.

### Obsidian

- Location: the user-configured Obsidian skills folder — it is the **root**
  of the skills area; every `.md` in it is a scan candidate
- **Validity rule**: a file is a skill iff its **last top-level code fence
  (any backtick count) whose content starts with frontmatter** (`---` block)
  exists — the skill block sits at the bottom. Frontmatter-driven, not
  count-driven: inner body fences (any width) are fine as long as they don't
  start with frontmatter. A "Need fix" fence that sits *after* the skill
  fence AND starts with frontmatter would win (accepted ambiguity — a
  formatting choice the user controls). No qualifying fence → flagged
  candidate, never auto-adopted
- Format (confirmed in vault): Obsidian wrapper frontmatter + 4-backtick fence
  around the skill frontmatter+body:
  ```
  ---
  tags:
    - ai-chat
  status: fix   # optional — marks that the skill needs a fix/update
  ---
  ````
  ---
  name: <name>
  description: ...
  ---
  <body>
  ````
  ```
- The TUI is **agnostic** to `status: fix` / "Need fix" (a personal
  notification marker). On export it passes the existing wrapper frontmatter
  through untouched (preserves `status`, `tags`, any other fields) and only
  replaces the fenced content. The TUI never reads, displays, or carries the
  flag.
- Exporting a **new** skill to Obsidian (no existing wrapper): create the
  wrapper with `tags:` from config default (`ai-chat`).

## Merge strategy

- **v1: replace** with diff preview. Always correct, trivially small.
- **v2: 3-way text merge** (SKILL.md only):
  - sync manifest stores the **last-synced blob** per skill × target
    (= merge base; no git dependency)
  - `git merge-file`-style 3-way on the three texts; non-overlapping edits
    auto-resolve, overlapping hunks → manual merge in `$EDITOR`
- Companion-file conflicts (added/removed/renamed between sides): stay
  **replace + confirm** even in v2

## Config

Single centralized config file. Location: `--config <path>` flag; default =
the **store's directory**. **Auto-generated with all defaults** if no config
file is found at that location. `--generate-config` emits all keys with
defaults + descriptions.

**First run (no config)**: onboarding pass — create config + store dir,
prompt to fill in targets, then first scan.

```json
{
  "store":   { "path": "~/Documents/skill-sync/store" },
  "targets": {
    "pi":        { "type": "pi", "skills_dir": "~/.pi/agent/skills" },
    "openwebui": { "type": "openwebui", "url": "http://localhost:30002", "api_key": "" },
    "obsidian":  { "type": "obsidian", "skills_dir": "~/Documents/Obsidian/yusrmuttaqien-obsidian/📍 Guides/ai/skills", "default_tags": ["ai-chat"] }
  },
  "ignore":  [".*"],
  "export":  { "inline_threshold_bytes": 65536 },
  "system":  { "hostname": "macbook-pro", "open_terminal": true }
}
```

- `targets` is a named map; each entry's `type` selects the adapter
  implementation. Adding a target type = new adapter, config just names it
- `system` is **pure user config** — no auto-detection
- `open_terminal` boolean controls which guide-text template OWUI exports use
  (Open-Terminal is a long-running service complementing OWUI)
- **Co-location assumption**: TUI and store live on the same machine /
  filesystem (v1). The script is **filesystem/OS-agnostic** (any OS Python
  runs on); Unix-isms degrade gracefully — exec-bit preservation is a no-op
  on Windows, `$EDITOR` is expected in any terminal

## Sync manifest

Per skill × per target: last-synced **hash + blob** (of SKILL.md and each
companion).
Powers: status table (✓ in-sync / + to-add / ~ changed / ~ paths-stale /
~ orphan / ! offline / ! error), drift detection (see Change sources), v2
merge base, repoint detection.

## TUI scope — v1

1. **Status** — skills × targets table (states above)
2. **Import** — pick target → pick skill → normalize → replace in store (diff preview)
3. **Export** — pick skill → pick target → transform → replace (diff preview)
4. **Adopt** — for unmanaged skills in any target: import into store + write normalized version back (see Adopt)
5. **Repoint** — fix stale absolute paths in a target (auto-suggested by status)
6. **Delete** — target copy (that target only) / store identity (target copies become `+` unmanaged)
7. **Store browser** — list skills, view files, edit SKILL.md via `$EDITOR`. **Create new skill = in the store**: prompt name → TUI writes the template SKILL.md to the store (minimal frontmatter `name`/`description` + body skeleton reminding the relative-ref convention) **before launching the editor** → post-edit checks run on close. Targets never create directly — normal export pushes it out
8. **Config** — generate + edit
9. **Batch** — apply Import/Export to a selected set of skills at once.
   Source eligibility: **managed (synced) skills only** — unmanaged skills
   aren't sources yet (they need Adopt first, which is inherently per-skill
   because of the write-back)

The TUI must make the **Import vs Adopt** difference visible at the point of
choice (action descriptions / help text):
- Import: "pull content into the store — the target's copy is NOT touched"
- Adopt: "pull content AND take over the target's copy (normalized write-back;
  the store becomes the single physical copy)"

TUI-only — no CLI, no API surface. Style reference: visref-canvas-builder
(rich-based, paged screens), but developed as a **modular package** (one
module per concern), not a single file.

## Delete semantics

Two deletes, both explicit:

- **Target copy**: delete the copy in that specific target only. Store and
  other targets are unaffected; the skill can be re-imported from any other
  target that still has it.
- **Store identity**: remove the skill from the store; target copies become
  `+` unmanaged (re-adoptable). (No unmanage/shelf concept.)

## Change sources & drift detection

**Every target is a change source, both directions.** No locks. Drift
detection is **normalize-then-exact-compare**, not fuzzy similarity: the
inter-target differences are exactly the known transforms (Obsidian wrapper,
abs-vs-rel refs, OWUI flatten), so normalizing a target copy into canonical
form cancels them — identical content compares byte-equal, and only real
edits show as a diff. **Line endings are normalized (LF) and trailing
newlines trimmed before compare and before write** — only visible text
changes count. The TUI compares each target's normalized copy against
the store:

- skill not in store → `+` unmanaged — born unnormalized; Import/Adopt are
  available, no drift actions apply
- managed skill, target differs from store → status shows it as **changed**,
  and both moves are available:
  - **Import from** the target — pulls its changes into the store; from
    there they can be pushed to replace the other targets
  - **Export to** the target — overwrites it, i.e. **reverts** the target's
    local changes (diff preview makes this visible before applying)
- any import re-runs the link/reference scan (see Link detection)
- **the store is also a change source** (symmetric): editing SKILL.md in the
  store browser → targets show `~ changed` → export applies the store version
- **Target-down states**: a target that's unreachable (OWUI server off, bad
  API key, missing vault path) shows `! offline` / `! error` per target; one
  failing target never blocks the others

## Checks (canonical suite)

The script's validation checks, in one registerable list. **Meta-rule: when
a new check is added (including during draft sweeps), it is registered here
and wired to its triggers.**

| Check | Post-edit (store) | Import | Scan | Rename / store-delete |
|---|---|---|---|---|
| Frontmatter valid (parseable, `name` present, legal charset) | ✓ | ✓ | — | — |
| Companion ref scan (broken ref / orphan / bare-filename candidates) | ✓ | ✓ | ✓ | — |
| Line-ending normalization (LF, trailing newline) | ✓ | ✓ | ✓ | — |
| Cross-skill name mentions (old name referenced by other skills → warn "X is referenced in Y, Z") | ✓ | — | — | ✓ |

Post-edit (editor close in the store browser) runs the full store-level
suite — it is the convergence point for most checks in the script.

## Identity & rename

Frontmatter `name` is the single identity, wins over any source naming
(folder name, OWUI skill id). Used uniformly for: store dir name, Obsidian
md filename, pi skill folder name (TUI renames folder to match), OWUI skill
name.

**Name normalization**: any input case is accepted; always transformed to
**kebab-case** (`My Cool_Skill!` → `my-cool-skill`). Charset: **letters
(Unicode allowed), digits, hyphen** — confusing symbols (`/ & ^ %` …) are
filtered, Unicode letters are kept.

**Nameless/malformed source**: import detects missing/invalid frontmatter →
TUI prompts "set name (and description) now?" inline, then proceeds.

**v1 rename = delete + import** (no rename action). Changing `name` in the
store = new identity; the TUI warns that the old identity becomes unmanaged
in N targets, **plus any cross-skill references to the old name** (Checks
suite). Old-name target copies are not lost — the next scan detects
them as `+` unmanaged (safety net). Manifest history for the new identity
starts fresh (acceptable: re-export re-baselines it).

## Naming

Package **`skillsync`**, entry point `skillsync`, repo `skill-sync-script`.

## Future edge cases (out of scope v1)

- Managed skill whose target copy was deleted manually (outside the TUI) —
  no defined status state yet
- Backup policy for targets before replace (current setup git-tracks all
  targets + store; TUI provides none)
- Multiple instances per target type (would need per-target instance arrays;
  v1 assumes one instance per target)
- Config holds the OWUI API key in plaintext — permissions/encryption
