---
description: 'Draws 44 diagram and chart types (architecture, sequence, ER, Gantt) as themed HTML with inline SVG. Use when asked to "draw a diagram".'
---

# Generate an Illustration

Use the installed, versioned Illustrate package to create a visual for the user's request.

## User Input

$ARGUMENTS

## Required skill package

1. Read `.specify/extensions/illustrate/skill/SKILL.md` completely before generating anything.
2. Resolve every relative `references/`, `assets/`, and `scripts/` path against
   `.specify/extensions/illustrate/skill/`.
3. Resolve `.github/illustration-theme.yml` with the packaged `scripts/illustration_theme.py`.
   Initialize Cobalt Light when the file is missing and the run is non-interactive; otherwise offer
   Cobalt, Emerald, Classic, or a custom light/dark theme and font set.
4. Follow the skill's project-theme gate, complexity budget, the chosen type reference, selected
   visual variant, and pre-output taste gate.
5. Never silently substitute another diagram system if the package is missing or unreadable. Report
   the installation problem and stop.

The types and variants are listed in `references/type-index.md`: choose the type there, then read
its `type-*.md`. Nothing in this command lists them.

## Output

Write the self-contained HTML to the path requested by the caller. If the caller requests SVG or
PNG, keep the HTML as the source of truth and export with the bundled `scripts/export_diagram.py` as
SKILL.md §12 says. Report every output path.
