# Illustrate Extension

Install the unified Illustrate skill through Spec Kit and expose it consistently to Claude, Codex,
and other supported integrations. It combines the former Diagram Design, architecture-diagram, and
process-flow-diagram skills.

## Commands

| Command | Claude invocation | Codex invocation |
| --- | --- | --- |
| `speckit.illustrate.generate` | `/speckit-illustrate-generate` | `$speckit-illustrate-generate` |
| `speckit.illustrate.export` | `/speckit-illustrate-export` | `$speckit-illustrate-export` |

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
initialization, annotation primitives, maintenance scripts, and source templates. Architecture and
process-flow requests may instead select the preserved technical-color light/dark templates with
built-in Copy/PNG/PDF controls and their complete example sets.

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
/speckit-illustrate-generate create a sequence diagram for the checkout flow
/speckit-illustrate-export docs/checkout-sequence.html --svg-only
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
