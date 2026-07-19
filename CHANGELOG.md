# Changelog

All notable changes to sanduq extensions/plugins are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/). Extensions are versioned
independently via `<extension>-vX.Y.Z` tags.

## assure — 2.0.0 — 2026-07-19

### Changed

- Renamed the `qa` extension and command namespace to `assure` as an immediate breaking rename;
  the `qa` id conflicted with an existing Spec Kit community extension and broke installation.
- Updated the `pr` extension's optional dependency to `assure >=2.0.0,<3.0.0`.

## sanduq — licensing and standalone manuals — 2026-07-18

### Added

- Added a standalone `dev-tools` plugin with five independently installable `npx skills` modules
  for complete manuals, API docs, release docs, UI screenshots, and preview publishing.
- Added a comprehensive README with real-life usage examples for every skill and Spec Kit extension.
- Added a repository workflow illustration in editable HTML and exported SVG/PNG formats.
- Consolidated required upstream notices in `THIRD_PARTY_NOTICES.md`.

### Changed

- Changed current and future sanduq original contributions to PolyForm Noncommercial 1.0.0;
  previously released MIT copies retain their original terms.
- Bumped the license-breaking extension releases to `project` 2.0.0, `pr` 4.0.0, and `illustrate`
  2.0.0, and bumped `illustration-tools` to 3.0.0.

## user-manual — 1.0.0 — 2026-07-18

### Added

- Added the modular User Manual extension for three navigable editions: End User,
  Administrator/Operator, and Technical Reference.
- Added bilingual-ready English/Arabic and RTL-aware MkDocs Material scaffolding, audience-specific
  HTML and PDF builds, API/reference, release, migration, tutorial, and screenshot workflows.
- Added approved module-map governance in `User-Manual/manual.yml`, full system and module ER
  documentation rules, synthetic-data screenshot policy, incremental freshness checks, and private
  PR preview artifacts.

## qa — 1.0.0 — 2026-07-18

### Changed

- Replaced the former `how-to-test` extension and command namespace with `qa` as an immediate
  breaking rename.
- Added `speckit.qa.init` to choose integrated or manual QA lifecycle policy.
- Added feature-scoped freshness gates so integrated projects require QA analysis before
  implementation and current QA documentation before PR creation.

## pr — 3.1.0 — 2026-07-18

### Changed

- Added pre-PR freshness checks for installed QA and User Manual extensions, with automatic
  documentation refresh before creating or updating a pull request.

## illustrate — 1.0.4 — 2026-07-18

### Changed

- Updated integration references for the QA and User Manual documentation lifecycles.

## illustration-tools — 2.0.3 — 2026-07-18

### Changed

- Updated bundled Illustrate references for QA and User Manual consumers.

## illustration-tools — 2.0.2 — 2026-07-18

### Added

- Added two modern, responsive Illustrate gallery alternatives: an Atlas sidebar and a Canvas Deck
  filmstrip workspace.
- Kept every editorial and technical-color family selectable in both layouts, with restrained
  preview transitions, keyboard navigation, and reduced-motion support.

## illustration-tools — 2.0.1 — 2026-07-18

### Fixed

- Added first-class Architecture technical-color and Process Flow technical-color selectors to the
  Illustrate gallery, covering all imported light and dark examples.
- Made the former `architecture-diagram` and `process-flow-diagram` capabilities explicit in the
  unified skill description and generation guidance.

## illustration-tools — 2.0.0 — 2026-07-18

### Changed

- Consolidated `diagram-design`, `architecture-diagram`, and `process-flow-diagram` into one
  `illustrate` skill under the `illustration-tools` plugin.
- Renamed the Spec Kit extension and commands to `illustrate` while preserving editorial,
  hand-drawn, technical-color, and export capabilities.

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
