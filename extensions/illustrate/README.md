# Illustrate Extension

For setup and a worked example, see [Install by host](https://github.com/samykabu/sanduq/blob/main/docs/start/install-by-host.md)
and the [Illustrate page](https://github.com/samykabu/sanduq/blob/main/docs/extensions/illustrate.md).
Every command and its example is in the [command reference](https://github.com/samykabu/sanduq/blob/main/docs/reference/commands.md#illustrate).


Install the unified Illustrate skill through Spec Kit and expose it consistently to Claude, Codex,
and other supported integrations. It combines the former Diagram Design, architecture-diagram, and
process-flow-diagram skills.

## Commands

| Command | Claude invocation | Codex invocation |
| --- | --- | --- |
| `speckit.illustrate.generate` | `/speckit-illustrate-generate` | `$speckit-illustrate-generate` |
| `speckit.illustrate.export` | `/speckit-illustrate-export` | `$speckit-illustrate-export` |
| `speckit.illustrate.theme` | `/speckit-illustrate-theme` | `$speckit-illustrate-theme` |
| `speckit.illustrate.import` | `/speckit-illustrate-import` | `$speckit-illustrate-import` |

`import` redraws an existing draw.io, Mermaid or Excalidraw source as an Illustrate diagram in the
active project theme, and records what it kept and changed in a fidelity ledger.

## Supported diagram types

Illustrate supports 44 diagram types. The skill's selection guide in
[`skill/SKILL.md`](skill/SKILL.md) says when to use each one.

- Architecture
- Architecture delta
- IT current-state
- Flowchart
- Sequence
- State machine
- ER / data model
- Timeline
- Swimlane
- Quadrant
- Radar / Spider
- Polar chart
- Loop
- Nested
- Tree
- Org chart
- Layer stack
- Exploded axonometric
- Axonometric plan
- Venn
- Pyramid / funnel
- Bar chart
- Waterfall
- Treemap
- Heatmap
- Line chart
- Gantt
- Scatter plot
- High-Level
- Process
- Medallion
- Data flow
- DP integration
- DP security matrix
- Sankey
- Fishbone
- Wardley map
- Kanban
- User journey
- Deployment
- Dependency graph
- UML class
- Story map
- Database schema

The package includes minimal light, minimal dark, full editorial, and generated hand-drawn examples
for every core type. It also carries data-lake and high-level-vertical hand examples, the quadrant
consultant treatment, terminal template, icon library, theme onboarding, local design-document
initialization, annotation primitives, maintenance scripts, and source templates. Architecture and
process-flow requests may instead select the preserved technical-color light/dark templates with
built-in Copy/PNG/PDF controls and their complete example sets.

## Project themes

Illustrate stores the selected colors, light/dark mode, font-loading policy, and project custom
themes in `.github/illustration-theme.yml`. Cobalt Porcelain Light is the default. Emerald Mist and
Sanduq Classic are built in, and every preset includes a dark mode and English/Arabic font fallbacks.

```text
/speckit-illustrate-theme initialize
/speckit-illustrate-theme set emerald light
/speckit-illustrate-theme create product-brand
/speckit-illustrate-theme validate
```

Custom themes define both light and dark semantic palettes plus sans, serif, and mono stacks. Font
loading can be `remote`, `local`, or `system`. Commit the YAML so local runs and CI generate the same
visual identity.

## Install and update

```bash
specify extension add illustrate
specify extension update illustrate
```

Spec Kit records the installed version in `.specify/extensions/.registry`. Extensions that declare
`illustrate` as a dependency inspect that registry before generating visuals. If it is missing,
disabled, incompatible, or older than the catalog release, they follow the project's dependency
policy before running the standard `add` or `update` command. The default policy asks first;
projects can choose automatic or manual handling in `.specify/extension-dependencies.yml`.

## Use

```text
/speckit-illustrate-generate create a sequence diagram for refund approval
/speckit-illustrate-export docs/refund-approval.html --svg-only
/speckit-illustrate-theme set cobalt dark
/speckit-illustrate-import docs/legacy/order-flow.mmd --size doc-wide --detail balanced
```

The command loads its version-matched skill package from
`.specify/extensions/illustrate/skill/`; it does not depend on a separately installed global
Claude or Codex skill.

## Migrate from Diagram Design

The extension ID and command namespace changed. Existing projects should run:

```bash
specify extension remove diagram-design
specify extension add illustrate
```

Restart the Claude or Codex conversation after installation so the newly generated command skills
are discovered.
