# Diagram Design Extension

Install the complete Diagram Design skill through Spec Kit and expose it consistently to Claude,
Codex, and other supported integrations.

## Commands

| Command | Claude invocation | Codex invocation |
| --- | --- | --- |
| `speckit.diagram-design.generate` | `/speckit-diagram-design-generate` | `$speckit-diagram-design-generate` |
| `speckit.diagram-design.export` | `/speckit-diagram-design-export` | `$speckit-diagram-design-export` |

## Supported diagram types

- Architecture
- IT current-state
- Flowchart
- Sequence
- State machine
- ER/data model
- Timeline
- Swimlane
- Quadrant
- Radar/spider
- Loop/flywheel
- Nested/containment
- Tree
- Org chart
- Layer stack
- Venn
- Pyramid/funnel
- Bar chart
- Line chart
- Gantt
- Scatter plot
- High-level architecture
- Multi-actor process
- Medallion architecture
- Data flow
- DP integration
- DP security matrix

The package includes minimal light, minimal dark, full editorial, and generated hand-drawn examples
for every core type. It also carries data-lake and high-level-vertical hand examples, the quadrant
consultant treatment, terminal template, icon library, theme onboarding, local design-document
initialization, annotation primitives, maintenance scripts, and source templates.

## Install and update

```bash
specify extension add diagram-design
specify extension update diagram-design
```

Spec Kit records the installed version in `.specify/extensions/.registry`. Extensions that declare
`diagram-design` as a dependency inspect that registry before generating visuals. If it is missing,
disabled, incompatible, or older than the catalog release, they follow the project's dependency
policy before running the standard `add` or `update` command. The default policy asks first;
projects can choose automatic or manual handling in `.specify/extension-dependencies.yml`.

## Use

```text
/speckit-diagram-design-generate create a sequence diagram for the checkout flow
/speckit-diagram-design-export docs/checkout-sequence.html --svg-only
```

The command loads its version-matched skill package from
`.specify/extensions/diagram-design/skill/`; it does not depend on a separately installed global
Claude or Codex skill.
