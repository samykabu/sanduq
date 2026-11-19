# Illustrate

**Purpose:** draw diagrams and charts as editable HTML with inline SVG, in your project's tracked
color and font theme. It supports 51 diagram types and exports SVG and PNG on request, and an animated SVG or GIF for README images, with arrows that draw, flow, pulse or slide chevrons in their direction.

| | |
| --- | --- |
| Lifecycle phase | Any; runs only when you ask |
| Hooks | Post-write diagram check, opt-in (`illustrate.hooks.self_check: true` in `.specify/workflow.yml`) |
| Commands | `generate`, `export`, `theme`, `import` ([reference](../reference/commands.md#illustrate)) |
| Requires | Nothing; Python 3.11 or later for export |
| Required by | Assure, PR, User Manual (Illustrate 2.x) |
| Standalone | Yes |
| License | MIT |

The extension carries its own version-matched copy of the Illustrate skill under
`.specify/extensions/illustrate/skill/`. It does not need a separately installed skill. The copy is
[vendored](../../vendor.lock.json) from [sanduq-skills](https://github.com/samykabu/sanduq-skills).

The catalog now includes Service Blueprint, Steps, Unit Grid, Requirement Traceability,
Event Modeling, Schedule Network and educational SBGN Process Description. It also includes
Architecture Containment, Box Plot, Arc Diagram and BPMN 2.0 as variants.

## Setup

```bash
specify extension add illustrate
```

```text
/speckit-illustrate-theme set cobalt light
```

The theme is stored in `.github/illustration-theme.yml`. Commit it so local runs and CI draw the same
colors and fonts. Cobalt Porcelain, Emerald Mist and Sanduq Classic are built in, each with light and
dark modes.

## Example

```text
/speckit-illustrate-generate Create a state diagram of refund request, approval, rejection and settlement from the real implementation.
/speckit-illustrate-export docs/refund-approval.html --svg-only
/speckit-illustrate-export docs/refund-approval-animated.html --animated
/speckit-illustrate-export docs/refund-approval.html --gif --arrows pulse
/speckit-illustrate-import docs/legacy/order-flow.mmd --size doc-wide --detail balanced
/speckit-illustrate-import docs/legacy/checkout.puml --size doc-wide
/speckit-illustrate-export docs/refund-approval.html --png-only --scale 1.5
```

The [process and theme gallery](../illustrate-examples.md) shows the presets and a custom theme.

## BPMN 2.0 Process diagrams

Ask for BPMN 2.0 explicitly with Illustrate 2.8.0. The Process variant uses one pool with
horizontal role lanes, standard start and end events, generic tasks and User Tasks,
exclusive gateways, and solid sequence flows. SVG and PNG show the complete process.
Use `--bpmn-route <name>` with animated SVG or GIF to play a selected route while all
branches stay visible.

```text
/speckit-illustrate-generate Draw a BPMN 2.0 expense approval process with Employee, Manager and Finance lanes. Name the routes approved and rejected. Save it to docs/expense-approval.html.
/speckit-illustrate-export docs/expense-approval.html --animated --bpmn-route approved
/speckit-illustrate-export docs/expense-approval.html --gif --bpmn-route rejected
```

The [expense approval example](../illustrate-examples.md#bpmn-20-expense-approval) includes
all four styles and a playable approved route. The [authoring guide](../../extensions/illustrate/skill/references/type-bpmn.md)
covers the supported notation, route names, and validation.

## How it runs

![Illustrate sequence: illustrate.theme picks a preset or custom light or dark theme and the agent resolves the project's colors and fonts; illustrate.generate draws the diagram from its purpose and evidence and inspects the HTML; illustrate.export writes the SVG or PNG you asked for, and you review and embed it while the editable source stays.](https://raw.githubusercontent.com/samykabu/sanduq/main/docs/diagrams/extension-illustrate.animated.svg)

You choose the theme, ask for the diagram, and ask for exports. The agent resolves the theme tokens,
applies the diagram type's rules, checks the HTML, and embeds the reviewed output.
[Editable source](../diagrams/extension-illustrate.html).

## Post-write check

Set `illustrate.hooks.self_check: true` in `.specify/workflow.yml` and a `PostToolUse` hook checks every
HTML file the agent writes or edits that contains an inline SVG (on Codex, every file an `apply_patch` adds,
updates or moves): it runs the skill's `self_check.py`, `verify-geometry.py` and `illustration_theme.py
validate` and hands the first failure back to the agent. Spec Kit does not register the hook. The Workflow
installer adds it when the key is true and removes it when the key is false. Without Workflow, run
`python .specify/extensions/illustrate/hooks/self_check_hook.py install --host claude|codex --root .`
yourself, and `uninstall` before you remove the extension. On Codex, approve the hook in `/hooks` once.

## Limits

- PNG and GIF export need Playwright and Chromium; GIF also needs Pillow. SVG and animated SVG export need Python.
- An animated SVG has no script or remote fonts and shows the complete figure to readers who prefer
  reduced motion. A GIF cannot follow that setting, so prefer the SVG where it is allowed.
- Every arrow ends on a straight lead at least its arrowhead long; `verify-arrow-ends.py` checks it.
- The hand-drawn generator needs Node.js and an `npm install` in the skill directory.
- Keep the editable HTML beside every export. Review the rendering before you embed it.
- Old Diagram Design installs must migrate: `specify extension remove diagram-design`, then add `illustrate`.

Package details: [Illustrate README](../../extensions/illustrate/README.md).
