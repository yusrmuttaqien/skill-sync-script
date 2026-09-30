# skillsync

A Python TUI that centralizes **skill management** across three peer targets —
**pi agent**, **OpenWebUI**, and an **Obsidian vault** — through a local
**store** acting as the normalization hub.

No single source of truth: every sync is an explicit **import** (target → store)
or **export** (store → target), with a diff preview and a confirm before
anything is replaced.

```
pi skills dir ─┐
OpenWebUI ─────┼──▶  STORE (canonical bundles)  ◀── import / export / adopt
Obsidian ──────┘
```

## Requirements

- Python 3.12+
- Dependencies: `rich`, `PyYAML` (see `requirements.txt`)

## Run

```bash
python -m venv venv
source venv/bin/activate
venv/bin/pip install -r requirements.txt

python skillsync.py                # TUI
python skillsync.py --generate-config   # emit all config keys with defaults
python skillsync.py --config /path/to/config.json
python skillsync.py --version
```

First run opens **onboarding**: a panel plus your `$EDITOR` on the generated
`config.json`, then the config is reloaded and the first status page renders.

## Config

`config.json` (project root by default):

| Key | Meaning |
|---|---|
| `store.path` | Store directory (canonical bundles live here) |
| `targets.<name>.type` | Adapter type: `pi` \| `openwebui` \| `obsidian` |
| `targets.pi.skills_dir` | pi agent skills directory |
| `targets.openwebui.url` | OpenWebUI base URL |
| `targets.openwebui.api_key` | Personal API key (`sk-` + 32 hex) |
| `targets.obsidian.skills_dir` | Obsidian skills folder |
| `targets.obsidian.default_tags` | Wrapper tags for newly exported skills |
| `ignore` | Globs ignored during companion enumeration (dotfiles by default) |
| `export.inline_threshold_bytes` | Companion size threshold for OWUI inline flatten |
| `system.hostname` / `system.open_terminal` | Used in large-companion guide text |

## TUI

The main page is a **status table**: one row per skill, one column per target,
plus a store column. States (with legend under the table):

| State | Meaning |
|---|---|
| `in-sync` | target matches last sync |
| `changed` | target edited outside the tool |
| `paths-stale` | store moved — absolute refs need repoint |
| `unmanaged` | present on target, not tracked in the manifest |
| `exportable` | in store, ready to export to this target |
| `offline` | target unreachable |
| `error` | read failed |
| `absent` | nowhere |

Menu (arrow keys / keys, **Esc cancels every step**):

| Key | Action |
|---|---|
| `i` | **Import** — target → store (target copy untouched; diff preview, check-gated) |
| `e` | **Export** — store → target |
| `a` | **Adopt** — import + take over the target copy (normalized write-back) |
| `b` | **Batch** — import/export a multi-selected set (managed-only sources) |
| `r` | **Rename** — store skill (cross-skill mentions updated) |
| `p` | **Repoint** — fix stale absolute store paths (one skill, or all at once after a store move) |
| `d` | **Delete** — from store (asks about synced targets first) or from a single target (copy only) |
| `c` | **Create** — new skill (template + `$EDITOR`) |
| `s` | **Scan** — run the checks suite on the store |
| `v` | **View** — store browser (skill → file, edit SKILL.md) |
| `q` | Quit |

After editing, a **post-edit check loop** runs the canonical suite
(frontmatter, description, companion ref scan, normalization, …). Companion
ref candidates get a per-occurrence menu: **create / rewrite / ignore**.

## What the store does for you

- **Canonical bundles** — `SKILL.md` + companion files; frontmatter
  `name`/`description` required; text normalization (LF, no BOM, trailing
  newline, `./` cleanup)
- **Link rewrite** — export rewrites relative refs to absolute store paths;
  import streamlines them back (token-boundary, URL/qualified contexts
  skipped)
- **OWUI flatten** — small companions inline into the prompt as
  `<!-- file:<rel> -->` markers (base64 for binary); large companions become a
  hostname/path guide; lossless round-trip
- **Drift detection** — per skill × target hash + blob of every file, so the
  status table tells you exactly what changed where
- **Exact-mirror companions** — import keeps referenced store companions,
  drops stale ones (listed in the diff)

## Docs

- `skills-sync-project.md` — the spec (behavior source of truth)
- `AGENTS.md` — workflow + conventions for contributors (human or agent)
- `CHANGELOG.md` — build log, phase tracker, and the draft-gap backlog
