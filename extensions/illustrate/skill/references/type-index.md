# Type index

One line per diagram type and variant: what it shows, then the reference to load. Pick one, then read
only that `type-*.md`. When behaviour, state, enforcement or risk carries the meaning, choose a
pattern in [semantic-patterns.md](semantic-patterns.md) first and use its nearest type for layout.
For the technical-color families, load [technical-color-architecture.md](technical-color-architecture.md)
or [technical-color-process-flow.md](technical-color-process-flow.md) instead. The drawing
procedure is in [`../SKILL.md`](../SKILL.md).

## Systems and structure

- **Architecture**: components and connections in one system snapshot. [type-architecture.md](type-architecture.md)
- **Architecture delta**: structural change between synchronized Before / After topologies, with a Changes ledger. [type-architecture-delta.md](type-architecture-delta.md)
- **IT current-state**: legacy landscape by phase or department, the *before* state of a modernization. [type-it-state.md](type-it-state.md)
- **High-Level**: end-to-end data stack on a container cluster. [type-high-level.md](type-high-level.md)
- **Deployment**: where software runs: zones, hosts, artifacts, replicas, ports. [type-deployment.md](type-deployment.md)
- **Dependency graph**: what depends on what, with fan-in and cycles a tree cannot express. [type-dependency.md](type-dependency.md)
- **DP integration**: data-platform integration topology, sources to core to consumers. [type-dp-integration.md](type-dp-integration.md)
- **Medallion**: multi-tier data storage with quality levels and access policies. [type-medallion.md](type-medallion.md)
- **DP security matrix**: per-role or per-component access permissions. [type-dp-security-matrix.md](type-dp-security-matrix.md)
- **Layer stack**: stacked abstraction levels. [type-layers.md](type-layers.md)
- **Nested**: hierarchy through containment or scope. [type-nested.md](type-nested.md)
- **Tree**: parent to children relationships. [type-tree.md](type-tree.md)
- **Org chart**: human, agent or team ownership, reporting, routing, escalation. [type-org-chart.md](type-org-chart.md)
- **Exploded axonometric**: parts of one object pulled apart along one axis (teardown, assembly order). [type-exploded.md](type-exploded.md)
- **Axonometric plan**: one floor or site seen from above at an angle, rooms or buildings by phase. [type-axonometric-plan.md](type-axonometric-plan.md)
- **ER / data model**: entities, fields and relationships. [type-er.md](type-er.md)
- **Database schema**: physical tables with SQL types, constraints, indexes, column-level FKs. [type-db-schema.md](type-db-schema.md)
- **UML class**: classes with operations, inheritance, composition. [type-uml-class.md](type-uml-class.md)

## Behaviour, process and planning

- **Flowchart**: decision logic with branches. [type-flowchart.md](type-flowchart.md)
- **Sequence**: time-ordered messages between actors. [type-sequence.md](type-sequence.md)
- **State machine**: states, transitions and guards. [type-state.md](type-state.md)
- **Swimlane**: cross-functional process with handoffs. [type-swimlane.md](type-swimlane.md)
- **Process**: multi-actor sequential process with data handoffs. [type-process.md](type-process.md)
- **Data flow**: role-scoped data flow, who does what at each pipeline step. [type-data-flow.md](type-data-flow.md)
- **Loop**: reinforcing cycle or flywheel where the last step feeds the first. [type-loop.md](type-loop.md)
- **Timeline**: events positioned in time. [type-timeline.md](type-timeline.md)
- **Gantt**: tasks and phases on a timeline. [type-gantt.md](type-gantt.md)
- **User journey**: what a person does across stages of an experience, and how it feels. [type-journey.md](type-journey.md)
- **Kanban**: work in progress by state, with WIP limits and blocked items. [type-kanban.md](type-kanban.md)
- **Story map**: narrative backbone sliced into releases, with the cut line. [type-story-map.md](type-story-map.md)
- **Fishbone**: causes of one observed effect, grouped by category. [type-fishbone.md](type-fishbone.md)
- **Wardley map**: value chain against evolution: build, buy, and what is moving. [type-wardley.md](type-wardley.md)

## Positioning and sets

- **Quadrant**: two-axis positioning or prioritization; the consultant 2x2 scenario matrix is in the same file. [type-quadrant.md](type-quadrant.md)
- **Venn**: overlap between sets. [type-venn.md](type-venn.md)
- **Pyramid / funnel**: ranked hierarchy or conversion drop-off. [type-pyramid.md](type-pyramid.md)

## Charts

- **Bar chart**: quantities across categories; grouped and stacked bars are in the same file. [type-bar.md](type-bar.md)
- **Dumbbell** (bar variant): two values per category where the gap is the message. [type-dumbbell.md](type-dumbbell.md)
- **Waterfall**: a start total bridged to an end total by signed contributions. [type-waterfall.md](type-waterfall.md)
- **Treemap**: part-of-whole where the relative sizes are the story. [type-treemap.md](type-treemap.md)
- **Marimekko** (treemap variant): two-way part-of-whole, column width times segment height. [type-marimekko.md](type-marimekko.md)
- **Heatmap**: cross-tabulated data, fill encodes the value per cell. [type-heatmap.md](type-heatmap.md)
- **Line chart**: continuous trends over time or a sequential index. [type-line.md](type-line.md)
- **Slopegraph** (line variant): change between exactly two states across several series. [type-slopegraph.md](type-slopegraph.md)
- **Ridgeline** (line variant): one distribution per series, stacked, shapes compared. [type-ridgeline.md](type-ridgeline.md)
- **Streamgraph** (line variant): a total and its composition across many periods. [type-streamgraph.md](type-streamgraph.md)
- **Bump chart** (line variant): rank movement across 3 to 6 ordered snapshots. [type-bump.md](type-bump.md)
- **Scatter plot**: correlation or distribution of two variables. [type-scatter.md](type-scatter.md)
- **Bubble** (scatter variant): three quantities per item, area as the third. [type-bubble.md](type-bubble.md)
- **Beeswarm** (scatter variant): one value axis, one dot per item, the full distribution. [type-beeswarm.md](type-beeswarm.md)
- **Radar / spider**: several entities scored across 3 to 5 quantitative criteria. [type-radar.md](type-radar.md)
- **Polar chart**: one series across cyclic categories; angle is the category, radius the magnitude. [type-polar.md](type-polar.md)
- **Sankey**: a quantity splitting and merging across stages, band width is the amount. [type-sankey.md](type-sankey.md)
