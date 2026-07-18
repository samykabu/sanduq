# Changelog

## [2.0.0] - 2026-07-18

### Changed

- Replaced the renamed `diagram-design` dependency with `illustrate >=1.0.0,<2.0.0` and updated
  readiness, generation, and export paths to the unified skill package.

All notable changes to the How-To-Test extension.

## [1.6.0] - 2026-07-18

### Changed

- Expanded readiness and documentation coverage to all twenty-seven Diagram Design v2 types.
- Routed diagram PNG generation through Diagram Design's bundled deterministic exporter.

## [1.5.0] - 2026-07-18

### Added

- Versioned `diagram-design >=1.0.0,<2.0.0` dependency checks with prompt, auto, and manual update
  policies backed by the Spec Kit extension registry.
- Readiness and documentation support for all fourteen Diagram Design types.

### Changed

- Replaced the architecture/process-only illustration path with Diagram Design type selection,
  version tracking, and cached catalog update checks.

## [1.4.1] - 2026-07-09

### Changed

- Aligned repository metadata and release catalog links with the sanduq marketplace.

## [1.4.0] - 2026-07-04

### Added

- `/speckit-how-to-test-analyze` now creates or refreshes `.github/memory/project-memory.md` before
  task coverage analysis.
- Added a reusable `Frontend Project Inventory` memory section that records implemented web/mobile
  frontends, planned/spec-only frontend paths, screenshot runners, How-To-Test roots, commands, and
  evidence source paths.

### Changed

- Aligned `/speckit-how-to-test-document` with the same project-memory schema so manual generation
  reuses and verifies the analyze command's frontend discovery.

## [1.3.2] - 2026-07-04

### Fixed

- Renamed internal Spec Kit command IDs to the valid `speckit.how-to-test.*` namespace required by
  the `specify` extension validator.
- Updated the documented slash commands to `/speckit-how-to-test-document` and
  `/speckit-how-to-test-analyze`.

## [1.3.0] - 2026-07-04

### Added

- Architecture and process-flow diagram generation for How-To-Test manuals when a completed feature
  changes architecture, integrations, UI/user journeys, validations, jobs, or error recovery flows.
- Diagram readiness checks in `/speckit-how-to-test-analyze` so missing HTML + PNG diagram
  asset tasks are added before implementation when the plan requires them.
- Diagram source HTML and exported PNG conventions for generated manual assets.

## [1.2.0] - 2026-07-04

### Changed

- Renamed the manual command to `speckit.how-to-test.document`
  (`/speckit-how-to-test-document`).
- Renamed the readiness audit command to `speckit.how-to-test.analyze`
  (`/speckit-how-to-test-analyze`) and fixed the spelling to `analyze`.

## [1.1.0] - 2026-07-04

### Added

- Manual generation command to generate or update QA-facing How-To-Test manuals for completed Spec
  Kit features.
- Optional `after_implement` lifecycle hook for manual generation after implementation completion
  validation and before PR handoff or human QA review.

### Changed

- Split the readiness audit from the manual generator so the main How-To-Test command maps to the
  actual manual generation workflow.

## [1.0.0] - 2026-07-04

### Added

- Initial readiness audit for missing E2E, screenshot-capture, API sample, and
  documentation-readiness tasks.
- Optional `after_tasks` lifecycle hook, recommended because task generation is complete and
  implementation has not started.
- Idempotent task-update rules for adding coverage tasks without duplicating existing work.
