# Changelog

All notable changes to the Illustrate extension.

## [2.1.0] - 2026-07-18

### Added

- Added `.github/illustration-theme.yml` as the tracked project-level theme policy.
- Added Cobalt Porcelain as the default, Emerald Mist, and backward-compatible Sanduq Classic
  presets, each with complete light/dark palettes and font families.
- Added `speckit.illustrate.theme` plus a zero-dependency initializer/resolver for listing,
  selecting, validating, and creating custom themes.
- Added remote, local, and system font-loading policies with English/Arabic fallback stacks.

### Changed

- Diagram generation now resolves project colors and typography before selecting or adapting a
  template. Non-interactive first runs initialize Cobalt Light.

## [2.0.0] - 2026-07-18

### Changed

- Changed sanduq original contributions to PolyForm Noncommercial 1.0.0 while preserving all
  upstream MIT/CC0 notices in the repository-level third-party notice file.

## [1.0.4] - 2026-07-18

### Changed

- Updated architecture and process-flow integration guidance for the renamed QA extension and the
  separate User Manual documentation lifecycle.

## [1.0.2] - 2026-07-18

### Added

- Added two responsive gallery alternatives: a searchable Atlas sidebar and a compact Canvas Deck
  with scroll-snap navigation.
- Included the complete editorial, technical architecture, and technical process-flow asset matrix
  in both galleries, with light/dark theme and reduced-motion support.

## [1.0.1] - 2026-07-18

### Fixed

- Exposed the merged Architecture Diagram and Process Flow Diagram families in the HTML gallery,
  including every imported light and dark example.
- Promoted both merged capabilities into the skill description, family-selection guidance,
  references, templates, and generation workflow.

## [1.0.0] - 2026-07-18

### Added

- Renamed the Spec Kit extension and command namespace from `diagram-design` to `illustrate`.
- Consolidated the Diagram Design, architecture-diagram, and process-flow-diagram skills into one
  versioned Illustrate package.
- Preserved the technical-color architecture/process templates, examples, and built-in
  Copy/PNG/PDF toolbar alongside all editorial, dark, full, hand, terminal, and consultant variants.

### Migration

- Remove `diagram-design`, then install `illustrate`; consuming extensions now depend on
  `illustrate >=1.0.0,<2.0.0`.

## [1.1.0] - 2026-07-18

### Added

- Thirteen additional first-class types: bar, data flow, DP integration, DP security matrix, Gantt,
  high-level, IT current-state, line, loop, medallion, process, radar, and scatter.
- Light, dark, full-editorial, and generated hand-drawn examples for all twenty-seven core types,
  plus data-lake and high-level-vertical hand variants.
- Icon and terminal primitives, terminal template, icon gallery, export reference, skin linter,
  icon build pipeline, vendored icon sources, and third-party license notices.
- `speckit.diagram-design.export` with deterministic SVG and transparent-PNG export through the
  bundled `scripts/export_diagram.py` utility.

### Changed

- Upgraded the packaged Diagram Design instructions to upstream v2 while preserving sanduq's local
  Markdown theme initialization and Rough.js hand-variant workflow.

## [1.0.0] - 2026-07-18

### Added

- `speckit.diagram-design.generate` with architecture, flowchart, sequence, state-machine, ER/data
  model, timeline, swimlane, quadrant, nested, tree, org-chart, layer-stack, venn, and
  pyramid/funnel support.
- Versioned skill instructions, type references, templates, examples, themes, onboarding, and
  light, dark, editorial, hand-drawn, and consultant variants.
- Standard Spec Kit registry-based installation and version tracking for consuming extensions.
