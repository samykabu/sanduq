# Changelog

All notable changes to the Diagram Design extension.

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
