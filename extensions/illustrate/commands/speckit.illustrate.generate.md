---
description: "Generate the most appropriate technical, product, architecture, or process illustration using the versioned Illustrate skill package."
---

# Generate an Illustration

Use the installed, versioned Illustrate package to create a visual for the user's request.

## User Input

$ARGUMENTS

## Required skill package

1. Read `.specify/extensions/illustrate/skill/SKILL.md` completely before generating anything.
2. Resolve every relative `references/`, `assets/`, and `scripts/` path against
   `.specify/extensions/illustrate/skill/`.
3. Follow the skill's first-run style-guide gate, type-selection guide, complexity budget, relevant
   type reference, selected visual variant, and pre-output taste gate.
4. Never silently substitute another diagram system if the package is missing or unreadable. Report
   the installation problem and stop.

All twenty-seven types are supported: architecture, IT current-state, flowchart, sequence, state
machine, ER/data model, timeline, swimlane, quadrant, radar/spider, loop/flywheel, nested, tree, org
chart, layer stack, venn, pyramid/funnel, bar, line, Gantt, scatter, high-level, process, medallion,
data flow, DP integration, and DP security matrix.

Available visual treatments include minimal light, minimal dark, full editorial, generated
hand-drawn, terminal, consultant quadrant, icon, and annotation variants. Architecture and process
flow also support technical-color light/dark templates with built-in Copy/PNG/PDF controls. Every
core type has a committed `example-<type>-hand.html` reference.

## Output

Write the self-contained HTML to the path requested by the caller. If the caller requests SVG or
PNG, keep the HTML as the source of truth and use the bundled `scripts/export_diagram.py` behavior
documented in `references/export.md`. Report every output path.
