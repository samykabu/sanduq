---
description: 'Exports an Illustrate diagram to SVG, transparent PNG, animated SVG or GIF; the HTML stays the source. Use when asked to "export the diagram".'
---

# Export an Illustration

Export a generated Illustrate HTML file without modifying its source.

## User input

$ARGUMENTS

## Instructions

1. Resolve the exporter at
   `.specify/extensions/illustrate/skill/scripts/export_diagram.py`.
2. If no source is supplied, ask which HTML file to export. Do not guess.
3. For `--registry`, follow `.specify/extensions/illustrate/skill/references/export-registry.md` to write the registry separately. For any requested image, pass the other options to the exporter CLI:
   - default: SVG and PNG;
   - `--svg-only` or `--png-only`;
   - `--animated` for a self-playing `<name>.animated.svg` (README images), or `--gif` for the same as
     an animated GIF (`--theme light|dark`, `--fps`);
   - `--arrows=draw|flow|pulse|draw-flow|chevrons` for the arrow animation (default `draw`);
   - `--scale` from 1 to 4 for PNG (fractional values accepted) or 1, 2, or 3 for GIF;
   - `--output=<path>` for an alternate output base.
4. For an image export, run the bundled exporter once. Do not recreate its implementation in a temporary script and do
   not auto-install Playwright or Chromium.
5. Report every output path and size, including any registry. If PNG support is unavailable, preserve any requested SVG
   result and surface the install instruction emitted by the exporter.
6. Read `.specify/extensions/illustrate/skill/references/export.md` only when the exporter exits non-zero
   or the user asks about animation details, then fix the cause and run it once more.

The exporter must refuse the gallery, reject missing SVG/viewBox inputs, leave the HTML unchanged,
and export only the first diagram SVG rather than the surrounding editorial page.
