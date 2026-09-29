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
| 0 | Scaffold | ⬜ | package `skillsync`, entry point, config (load/generate/onboarding) |
| 1 | Core domain | ⬜ | canonical form, name normalization, normalization pass, Checks suite |
| 2 | Store | ⬜ | layout, integrity, browser (view/edit/create + post-edit checks) |
| 3 | Adapters | ⬜ | pi, obsidian, openwebui — scan/get/put/remove per spec |
| 4 | Manifest + status | ⬜ | last-synced blobs, status table, drift detection, target-down states |
| 5 | Import / Export | ⬜ | mirror rule, diff preview, link rewrite, OWUI flatten/markers |
| 6 | Adopt / Repoint / Delete / Batch | ⬜ | ownership transfer, repoint, both deletes, batch apply |
| 7 | TUI assembly | ⬜ | rich-based paged screens, modular package, help text (Import vs Adopt) |

Status legend: ⬜ not started · 🔨 in progress · ✅ done

## Log

## [2026-07-09] — Session 1
**Task**: Bootstrap the build system
**Changes**:
- `CHANGELOG.md` — created (phase table + this log)
- `AGENTS.md` — created (DOX workflow, build conventions, verification)
- Spec finalized (`skills-sync-project.md`) after 5 sweep rounds; OWUI API verified live against v0.11.4
- OWUI API key created (`sk-` + 32 hex, Settings → Account → API keys); admin global toggle enabled
- Phase plan established above
