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
3. Resolve `.github/illustration-theme.yml` with the packaged `scripts/illustration_theme.py`.
   Initialize Cobalt Light when the file is missing and the run is non-interactive; otherwise offer
   Cobalt, Emerald, Classic, or a custom light/dark theme and font set.
4. Follow the skill's project-theme gate, type-selection guide, complexity budget, relevant
   type reference, selected visual variant, and pre-output taste gate.
5. Never silently substitute another diagram system if the package is missing or unreadable. Report
   the installation problem and stop.

All forty-four types are supported: architecture, architecture delta, IT current-state, flowchart,
sequence, state machine, ER/data model, database schema, UML class, timeline, swimlane, quadrant,
radar/spider, polar, loop/flywheel, nested, tree, org chart, layer stack, exploded axonometric,
axonometric plan, venn, pyramid/funnel, bar, waterfall, treemap, heatmap, line, Gantt, scatter,
high-level, process, medallion, data flow, DP integration, DP security matrix, Sankey, fishbone,
Wardley map, kanban, user journey, deployment, dependency graph, and story map. Variants include
slopegraph, ridgeline, streamgraph, bump, bubble, beeswarm, dumbbell, marimekko, lifecycle phase
maps, and block decomposition trees. Semantic patterns route behavior-heavy requests to a type.

Available visual treatments include minimal light, minimal dark, full editorial, generated
hand-drawn, terminal, consultant quadrant, icon, and annotation variants. Architecture and process
flow also support technical-color light/dark templates with built-in Copy/PNG/PDF controls. Every
core type has a committed `example-<type>-hand.html` reference. Optional motion (reveal, step,
loop) is available from `assets/template-motion*.html` when explicitly requested. Editorial output
is themed with `scripts/illustration_theme.py apply` and checked with `scripts/self_check.py`.

## Output

Write the self-contained HTML to the path requested by the caller. If the caller requests SVG or
PNG, keep the HTML as the source of truth and use the bundled `scripts/export_diagram.py` behavior
documented in `references/export.md`. Report every output path.
