# Changelog

All notable changes to sanduq extensions/plugins are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/). Extensions are versioned
independently via `<extension>-vX.Y.Z` tags.

## project — 1.0.0 — 2026-07-09

### Added
- Initial release of the `project` Spec Kit extension: GitHub Project (v2) lifecycle sync.
- Parent feature issue per feature; Status column advances through the Spec Kit lifecycle
  (`open → analysis → engineer-review → ready → in-progress → in-review → done`).
- One native sub-issue per task; sub-issues close as tasks are checked off in `tasks.md`.
- `project init` (PowerShell + bash) — board discovery and hybrid phase→column mapping
  (exact → fuzzy → prompt → optional auto-create of missing columns via GraphQL).
- `project sync` engine (PowerShell + bash) — idempotent, no-regress, self-contained
  In-review via open-PR detection, graceful degradation, committed shared state.
- Spec Kit `catalog.json` entry and Claude Code `marketplace.json` scaffold.
