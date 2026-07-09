# Changelog

All notable changes to sanduq extensions/plugins are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/). Extensions are versioned
independently via `<extension>-vX.Y.Z` tags.

## sanduq — 0.2.0 — 2026-07-09

### Added
- Resal-style automated extension release pipeline on `main`, with catalog/version commits and
  release ZIP publication.
- Marketplace registration for the `devtools` and `illustration-tools` Claude Code plugins.

### Changed
- Root `catalog.json` is now the public Spec Kit catalog, mirrored to `extensions/catalog.json`.
- Extension and plugin documentation now uses the sanduq install paths and release flow.
- Release-critical scripts and manifests are pinned to LF line endings with `.gitattributes`.
- Bumped extension metadata: `project` 1.0.1, `pr` 1.1.2, `pr-review` 1.0.4,
  `how-to-test` 1.4.1.
- Bumped plugin metadata: `devtools` 1.7.1 and `illustration-tools` 1.3.1.

## illustration-tools — 1.3.0 — 2026-07-09

### Added
- Light theme support for `process-flow-diagram`, now used by default.
- Dark process-flow template preserved as `resources/template-dark.html` for prompts that ask for dark output.
- Matching light reference outputs for every process-flow example: `sprint-report-flow-light.html`, `ai-governance-workflow-light.html`, `it-change-management-light.html`, and `inventory-control-light.html`.

### Changed
- `process-flow-diagram` skill instructions now route theme selection from the prompt and document separate light/dark palettes.

## illustration-tools — 1.2.0 — 2026-07-09

### Added
- Light theme support for `architecture-diagram`, now used by default.
- Dark architecture template preserved as `resources/template-dark.html` for prompts that ask for dark output.
- Matching light reference outputs for every architecture example: `web-app-light.html`, `aws-serverless-light.html`, and `microservices-light.html`.

### Changed
- `architecture-diagram` skill instructions now route theme selection from the prompt and document separate light/dark palettes.

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
