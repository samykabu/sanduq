# Illustrate

**Purpose:** draw diagrams and charts as editable HTML with inline SVG, in your project's tracked
color and font theme. It supports 44 diagram types and exports SVG and PNG on request, and an animated SVG or GIF for README images, with arrows that draw, flow, pulse or slide chevrons in their direction.

| | |
| --- | --- |
| Lifecycle phase | Any; runs only when you ask |
| Hooks | None |
| Commands | `generate`, `export`, `theme`, `import` ([reference](../reference/commands.md#illustrate)) |
| Requires | Nothing |
| Required by | Assure, PR, User Manual (Illustrate 2.x) |
| Standalone | Yes |
| License | PolyForm Noncommercial 1.0.0 |

The extension carries its own version-matched copy of the Illustrate skill under
`.specify/extensions/illustrate/skill/`. It does not need a separately installed skill. The copy is
[vendored](../../vendor.lock.json) from [sanduq-skills](https://github.com/samykabu/sanduq-skills).

## Setup

```bash
specify extension add illustrate
```

```text
$speckit-illustrate-theme set cobalt light
```

The theme is stored in `.github/illustration-theme.yml`. Commit it so local runs and CI draw the same
colors and fonts. Cobalt Porcelain, Emerald Mist and Sanduq Classic are built in, each with light and
dark modes.

## Example

```text
$speckit-illustrate-generate Create a state diagram of refund request, approval, rejection and settlement from the real implementation.
$speckit-illustrate-export docs/refund-approval.html --svg-only
$speckit-illustrate-export docs/refund-approval-animated.html --animated
$speckit-illustrate-export docs/refund-approval.html --gif --arrows pulse
$speckit-illustrate-import docs/legacy/order-flow.mmd --size doc-wide --detail balanced
```

The [process and theme gallery](../illustrate-examples.md) shows the presets and a custom theme.

## How it runs

![Illustrate sequence: illustrate.theme picks a preset or custom light or dark theme and the agent resolves the project's colors and fonts; illustrate.generate draws the diagram from its purpose and evidence and inspects the HTML; illustrate.export writes the SVG or PNG you asked for, and you review and embed it while the editable source stays.](../diagrams/extension-illustrate.animated.svg)

You choose the theme, ask for the diagram, and ask for exports. The agent resolves the theme tokens,
applies the diagram type's rules, checks the HTML, and embeds the reviewed output.
[Editable source](../diagrams/extension-illustrate.html).

## Limits

- PNG and GIF export need Playwright and Chromium; GIF also needs Pillow. SVG and animated SVG export need Python.
- An animated SVG has no script or remote fonts and shows the complete figure to readers who prefer
  reduced motion. A GIF cannot follow that setting, so prefer the SVG where it is allowed.
- Every arrow ends on a straight lead at least its arrowhead long; `verify-arrow-ends.py` checks it.
- The hand-drawn generator needs Node.js and an `npm install` in the skill directory.
- Keep the editable HTML beside every export. Review the rendering before you embed it.
- Old Diagram Design installs must migrate: `specify extension remove diagram-design`, then add `illustrate`.

Package details: [Illustrate README](../../extensions/illustrate/README.md).
