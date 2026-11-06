# Changelog

## [2.7.3] - 2026-10-28

- `requires.tools` lists Python `>=3.11` as optional (the export and verify scripts), the floor every Sanduq extension now states.

## [2.7.2] - 2026-10-26

- License: this package is MIT; versions before this one were PolyForm Noncommercial 1.0.0. The archive now ships its LICENSE and a THIRD_PARTY_NOTICES.md for the vendored illustration-tools material.

## [2.7.1] - 2026-10-21

Vendors illustration-tools 3.7.1.

- The data verifiers share `skill/scripts/svg_scan.py` (the SVG scanner and its helpers). Diagrams and verifier output
  are unchanged. A verifier copied out of the skill needs `svg_scan.py` beside it.

## [2.7.0] - 2026-10-21

Optimization release. No renames.

- Fixed: the opt-in post-write check no longer passes silently when the hook's Python has no PyYAML. It reads
  `illustrate.hooks.self_check` in block or flow form without PyYAML. When it cannot read the setting (invalid YAML,
  or anchors, aliases, tags or merge keys without PyYAML), a written diagram fails with a message that says how to
  fix it. A write that is not a diagram never reads the setting, and loads neither PyYAML nor `subprocess`.
- Fixed: `speckit.illustrate.import` runs the SKILL.md step 7 checks on the redrawn diagram: `verify-geometry.py`,
  `self_check.py --strict` (technical-color: `--profile technical-color`) and the type's verifier.
- `speckit.illustrate.theme` reads `theme-initialization.md` only for `create` or a theme from a design source (about
  1.2 KB read instead of 9 KB for `init`, `set`, `list`, `resolve` and `validate`; measured proxy: command
  `instruction_bytes`, 9,017 to 1,200, recorded on 2026-10-27). `speckit.illustrate.generate`
  points to SKILL.md §12 for export, which reads `export.md` only on failure.

### Migration

- With `self_check: true`, a `.specify/workflow.yml` that the hook cannot read now blocks written diagrams with a
  message. Install PyYAML for the hook's Python, write the key as plain block lines, or set it to false.

## [2.6.0] - 2026-10-20

Optimization release. Vendors illustration-tools 3.6.0.

- The post-write check is registered only when `illustrate.hooks.self_check` is true: `hooks/self_check_hook.py install|uninstall|status --host claude|codex --root <project>` writes native entries (Workflow's installer runs it on every apply). 2.5.0 registered the hook for everyone, costing about 223 ms per Write or Edit even with the key off and never firing on Codex. The command is inert if the extension is removed without uninstall. Codex `apply_patch` payloads are understood; technical-color diagrams are checked with their profile.
- Every shipped template and example passes the check the procedure requires (274 of 296 strict, all 18 technical-color files under `--profile technical-color`). `icon_lookup.py` replaces reading the 82 KB icon catalog. Export reads `export.md` only on failure.
- The package leaves out preview images and gallery variants nothing uses (3.62 to 2.77 MB).

## [2.5.0] - 2026-10-19

Optimization release.

- Vendors illustration-tools 3.5.0. SKILL.md is procedure-first, 11.7 KB instead of 34.7 KB, with `references/type-index.md` (one line per type and variant), `taste-gate.md` and `variants.md`. Four oversize type references are split into eight variant files. `self_check.py --strict` and `verify-geometry.py --orthogonal` add the mechanical checks. One diagram's minimal read is about 29 KB instead of 52 KB.
- The commands use the type index; `generate.md` no longer repeats the type list and `theme.md` no longer restates the script's dialogue.
- Opt-in post-write check: with `illustrate.hooks.self_check: true` in `.specify/workflow.yml`, a PostToolUse hook runs the three checks on written diagram HTML and returns the first failure. It is off by default.
- One description per command.

## [2.4.2] - 2026-10-17

- Vendors illustration-tools 3.4.2. Render verification pauses JavaScript clocks between captures and restores SVG and ancestor styles exactly after capture.

## [2.4.1] - 2026-10-11

- Vendors illustration-tools 3.4.1. Exports carry the page's CSS (theme tokens, classes and
  `prefers-color-scheme` blocks) into the SVG, so shapes styled outside the `<svg>` no longer fall
  back to black (29 shipped examples). Diagrams with nested icon SVGs are exported whole, and HTML
  comments are stripped so the SVG stays valid XML. Fonts, page motion and `@import` stay out.

## [2.4.0] - 2026-10-10

- Vendors illustration-tools 3.4.0: `export --arrows=draw|flow|pulse|draw-flow|chevrons` animates arrows
  in their direction (default `draw`), `export --gif` writes an animated GIF, and every arrow now ends
  on a straight lead (65 shipped arrows fixed; `scripts/verify-arrow-ends.py` checks it).

## [2.3.0] - 2026-10-10

- Vendors illustration-tools 3.3.0: `export --animated` writes a self-playing `<name>.animated.svg` from a
  motion figure (opacity-only reveal as CSS inside the SVG; no script or remote fonts; reduced motion
  shows the complete figure).
- Exported SVGs are now valid XML (valueless HTML attributes get an empty value).

## [2.2.1] - 2026-10-10

- Neutral example footers in the process-flow templates; no behavior change.
- The skill is vendored from samykabu/sanduq-skills (illustration-tools 3.2.1). Its SKILL.md is
  marked `metadata.internal` so it is not offered as a separate install from this repository.
- README lists all four commands, including `import`, and all 44 diagram types, and links to the new
  extension page and command reference.

## [2.2.0] - 2026-10-06

### Added

- Seventeen diagram types ported from upstream diagram-design 2.6.59: architecture delta,
  deployment, dependency graph, database schema, UML class, fishbone, Sankey, Wardley map,
  heatmap, waterfall, treemap (with marimekko), polar, user journey, kanban, story map,
  exploded axonometric, and axonometric plan (44 types total).
- Variants in existing types: slopegraph, ridgeline, streamgraph, bump, bubble, beeswarm,
  dumbbell, lifecycle phase map, traceable block decomposition, and OAuth sequence.
- Semantic patterns (`references/semantic-patterns.md`) chosen before the visual type.
- draw.io, Mermaid, and Excalidraw import with extractors, adversarial fixtures, and the
  `speckit.illustrate.import` command; redraws use the active project theme.
- Optional motion layer (`references/animation.md`, light and dark motion templates).
- `illustration_theme.py apply`: deterministic mapping of default literals and fonts to the
  active project theme; optional `ink-strong` role derived by contrast when omitted.
- Verification: `self_check.py`, `verify-geometry.py`, `lint-render.py`, per-type verifiers, and
  a theme-matrix test across every built-in preset and mode.
- Output spec (size presets, type ramp, detail and audience dials), connector rule 6, the
  accessible SVG contract, and a confirm-before-drawing step.

### Changed

- SKILL.md is a router; long-form primitives and budgets moved to `references/primitives-core.md`
  and `references/layout-budget.md`.
- Theme files, presets, custom themes, hand-drawn, terminal, consultant, and technical-color
  variants are unchanged.

## [2.1.3] - 2026-10-06

- Link setup and complete usage examples from the package README; links work in installed copies.

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
