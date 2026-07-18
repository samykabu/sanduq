# Illustration Tools

Generate polished technical diagrams as **self-contained HTML files** (inline SVG + embedded CSS) straight from a plain-English description. Diagrams default to light theme and can switch to dark theme from the prompt. Each diagram opens in any browser and ships with built-in **Copy / PNG / PDF** export — no build step, no server, no external images.

## Included Skills

| Skill                   | Use it for                                                                                                      | Docs |
| ----------------------- | -------------------------------------------------------------------------------------------------------------- | ---- |
| `architecture-diagram`  | Non-sequential system relationships — components, infrastructure, cloud topology, security zones, network maps; light by default, dark on request | [README](skills/architecture-diagram/README.md) |
| `process-flow-diagram`  | Sequential workflows — approval flows, automation pipelines, runbooks, onboarding, decision trees; light by default, dark on request | [README](skills/process-flow-diagram/README.md) |

They share one design language (JetBrains Mono, semantic color palette, the same export toolbar) but differ in shape language: architecture uses component boxes and free-form connections; process-flow uses numbered steps, decision diamonds, and ordered arrows.

## Usage

Install from the sanduq marketplace:

```
/plugin marketplace add samykabu/sanduq
/plugin install illustration-tools@sanduq
```

Then just describe what you want — the skills trigger automatically:

```
/illustration-tools:architecture-diagram   # then describe your system
/illustration-tools:process-flow-diagram    # then describe your workflow
```

Or in plain language:

- *"Draw an architecture diagram for a React frontend, Node API, Postgres, and Redis on AWS."* → `architecture-diagram`
- *"Make a process flow for our expense-approval workflow with a manager decision step."* → `process-flow-diagram`

Iterate in chat — "add a Redis cache", "add a rejection branch from step 3", "wrap this to a second row" — and Claude edits the same HTML file.

## What you get

- **A single `.html` file** — inline SVG, embedded CSS, works offline in any browser.
- **Built-in export toolbar** — a collapsible `⋯` menu with 📋 Copy (PNG to clipboard), 🖼️ PNG download, and 📄 PDF (theme-preserving). Powered by `html2canvas@1.4.1` and `jspdf@2.5.2`, both pinned with Subresource Integrity hashes.
- **Consistent, professional styling** — semantic colors so every diagram reads the same way across the team.

## Documentation automation

The Spec Kit PR and How-To-Test workflows now use the broader `diagram-design` extension. This
plugin remains available as a focused standalone Claude workflow for architecture and process-flow
illustrations outside Spec Kit.

## How it works

Each skill is **instructions + a template**, not a program. Claude reads the design system in the skill's `SKILL.md`, copies the selected `resources/` template, and customizes it for your description. Reference outputs live under each skill's `examples/`. For the internals and customization guide, see the per-skill READMEs linked above.

## Structure

```
illustration-tools/
├── .claude-plugin/
│   └── plugin.json
├── README.md
└── skills/
    ├── architecture-diagram/
    │   ├── SKILL.md
    │   ├── README.md
    │   ├── resources/template.html
    │   ├── resources/template-dark.html
    │   └── examples/
    └── process-flow-diagram/
        ├── SKILL.md
        ├── README.md
        ├── resources/template.html
        ├── resources/template-dark.html
        └── examples/
```

## License

MIT.
