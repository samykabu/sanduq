# Illustration Tools

Generate polished technical and product illustrations as **self-contained HTML files** with inline SVG and embedded CSS. The unified `illustrate` skill supports twenty-seven diagram types, editorial and technical-color design families, light/dark/full/hand variants, and SVG/PNG/PDF export paths.

## Included Skill

| Skill | Use it for |
| --- | --- |
| `illustrate` | Architecture, process flows, sequence, state, ER, timelines, swimlanes, charts, data-platform diagrams, and every other supported visual type. |

The former `architecture-diagram`, `process-flow-diagram`, and standalone Diagram Design skills are consolidated here. Their complete templates and examples remain available as editorial or technical-color families selected by the unified skill.

## Usage

Install from the sanduq marketplace:

```
/plugin marketplace add samykabu/sanduq
/plugin install illustration-tools@sanduq
```

Then just describe what you want — the skills trigger automatically:

```
/illustration-tools:illustrate   # then describe the visual you need
```

Or in plain language:

- *"Draw an architecture diagram for a React frontend, Node API, Postgres, and Redis on AWS."*
- *"Make a hand-drawn process flow for our expense-approval workflow with a manager decision step."*

Iterate in chat — "add a Redis cache", "add a rejection branch from step 3", "wrap this to a second row" — and Claude edits the same HTML file.

## Gallery designs

Open any gallery directly from `skills/illustrate/assets/`:

- `index.html` is the original gallery.
- `index-variation-1.html` is a searchable Atlas layout with persistent family, type, and presentation navigation.
- `index-variation-2.html` is a Canvas Deck workspace with compact selectors and a horizontal scroll-snap filmstrip.

Both alternatives expose the complete editorial and technical-color asset matrix, adapt to light and dark system themes, and honor reduced-motion preferences.

## What you get

- **A single `.html` file** — inline SVG, embedded CSS, works offline in any browser.
- **Two visual families** — restrained editorial output for all types, plus technical-color architecture and process-flow templates with a built-in Copy/PNG/PDF toolbar.
- **Deterministic export** — bundled SVG/transparent-PNG exporter, with browser PDF export in technical-color templates.

## Documentation automation

The Spec Kit PR, QA, and User Manual workflows use the matching `illustrate` extension. This plugin
makes the same unified skill available directly to Claude Code.

## How it works

Claude reads `skills/illustrate/SKILL.md`, selects the appropriate type and visual family, loads only
the matching reference, and customizes the closest asset template or example.

## Structure

```
illustration-tools/
├── .claude-plugin/
│   └── plugin.json
├── README.md
└── skills/
    └── illustrate/
        ├── SKILL.md
        ├── references/
        ├── scripts/
        └── assets/
```

## License

Sanduq original contributions are available under the root
[PolyForm Noncommercial License 1.0.0](../../LICENSE). Derived Illustrate code and bundled icons
retain their upstream terms listed in [third-party notices](../../THIRD_PARTY_NOTICES.md).
