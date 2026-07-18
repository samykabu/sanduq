---
description: "Export a Diagram Design HTML file to standalone SVG and/or transparent PNG using the version-matched bundled exporter."
---

# Export a Diagram

Export a generated Diagram Design HTML file without modifying its source.

## User input

$ARGUMENTS

## Instructions

1. Read `.specify/extensions/diagram-design/skill/references/export.md` before exporting.
2. Resolve the exporter at
   `.specify/extensions/diagram-design/skill/scripts/export_diagram.py`.
3. If no source is supplied, ask which HTML file to export. Do not guess.
4. Translate the requested options to the exporter CLI:
   - default: SVG and PNG;
   - `--svg-only` or `--png-only`;
   - `--scale=1|2|3` for PNG;
   - `--output=<path>` for an alternate output base.
5. Run the bundled exporter once. Do not recreate its implementation in a temporary script and do
   not auto-install Playwright or Chromium.
6. Report every output path and size. If PNG support is unavailable, preserve any requested SVG
   result and surface the install instruction emitted by the exporter.

The exporter must refuse the gallery, reject missing SVG/viewBox inputs, leave the HTML unchanged,
and export only the first diagram SVG rather than the surrounding editorial page.
