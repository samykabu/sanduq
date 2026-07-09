# Architecture Diagram Skill

Turn a plain-English description of a system into a polished **architecture diagram** rendered as a single self-contained HTML file (inline SVG + embedded CSS). The skill defaults to a light theme and switches to the dark theme when the prompt explicitly asks for it. Best for non-sequential relationships: system components, infrastructure, cloud topology, security zones, and network layouts.

For step-by-step workflows that unfold in time (approval flows, runbooks, automation pipelines), use the sibling [`process-flow-diagram`](../process-flow-diagram/) skill instead — same design language, different shape language.

## How the skill works (from the outside)

1. **You describe the system** — components, how they connect, technologies, cloud services, security boundaries. Either paste a description, point Claude at a codebase, or ask for a typical architecture.
2. **Claude activates the skill** — the `description` in [SKILL.md](SKILL.md) triggers on requests for system / infrastructure / cloud / security / network diagrams.
3. **Claude picks a theme template** — it starts from [`resources/template.html`](resources/template.html) for light diagrams, or [`resources/template-dark.html`](resources/template-dark.html) when you ask for dark mode. Then it places component boxes, draws connection arrows, groups security/region boundaries, and fills the summary cards.
4. **You get one `.html` file** — open it in any browser. No build step, no server, no external images. Use the header toolbar to Copy / export PNG / export PDF.
5. **You iterate in chat** — "add a Redis cache", "move auth into its own security group", "make the API tier wider" — Claude edits the same file.

## Documentation automation

When called by the `pr-generate-description`, `speckit.pr.generate`, `how-to-test`, or
`speckit.how-to-test.document` workflows, this skill should produce both:

- A source HTML file under the relevant feature documentation assets folder.
- A PNG export beside it, embedded in the generated documentation with a link back to the HTML source.

Only create the diagram when the implementation actually changes or clarifies architecture,
infrastructure, service boundaries, data flow, integrations, security boundaries, deployment shape, or
component ownership.

## How it works internally

The skill is **instructions + a template**, not code. Claude reads the design system rules in [SKILL.md](SKILL.md) and applies them while editing the HTML.

### Files

```
architecture-diagram/
├── SKILL.md               # The design system + rules Claude follows
├── resources/
│   ├── template.html      # Light/default HTML/SVG scaffold
│   └── template-dark.html # Dark HTML/SVG scaffold
├── examples/              # Reference outputs (see them rendered)
│   ├── web-app.html
│   ├── web-app-light.html
│   ├── aws-serverless.html
│   ├── aws-serverless-light.html
│   ├── microservices.html
│   ├── microservices-light.html
│   └── images/            # PNG previews of the examples
└── README.md              # This file
```

### The design system (what SKILL.md encodes)

- **Theme selection** — light is the default; dark is selected only when the prompt asks for dark mode, a dark background, or to match an existing dark output.
- **Semantic color palette** — each component type keeps the same meaning across themes:

  Light/default:

  | Type | Color | Fill (rgba) | Stroke |
  |------|-------|-------------|--------|
  | Frontend | Sky | `rgba(14, 165, 233, 0.12)` | `#0284c7` |
  | Backend | Emerald | `rgba(16, 185, 129, 0.12)` | `#059669` |
  | Database | Violet | `rgba(139, 92, 246, 0.12)` | `#7c3aed` |
  | AWS/Cloud | Amber | `rgba(245, 158, 11, 0.14)` | `#d97706` |
  | Security | Rose | `rgba(244, 63, 94, 0.12)` | `#e11d48` |
  | Message Bus | Orange | `rgba(249, 115, 22, 0.12)` | `#ea580c` |
  | External/Generic | Slate | `rgba(100, 116, 139, 0.10)` | `#64748b` |

  Dark:

  | Type | Color | Fill (rgba) | Stroke |
  |------|-------|-------------|--------|
  | Frontend | Cyan | `rgba(8, 51, 68, 0.4)` | `#22d3ee` |
  | Backend | Emerald | `rgba(6, 78, 59, 0.4)` | `#34d399` |
  | Database | Violet | `rgba(76, 29, 149, 0.4)` | `#a78bfa` |
  | AWS/Cloud | Amber | `rgba(120, 53, 15, 0.3)` | `#fbbf24` |
  | Security | Rose | `rgba(136, 19, 55, 0.4)` | `#fb7185` |
  | Message Bus | Orange | `rgba(251, 146, 60, 0.3)` | `#fb923c` |
  | External/Generic | Slate | `rgba(30, 41, 59, 0.5)` | `#94a3b8` |

- **Typography** — JetBrains Mono (loaded from Google Fonts) at 12/9/8/7px for names/sublabels/annotations/tiny labels.
- **Canvas** — light uses `#f8fafc` with a subtle `#e2e8f0` grid; dark uses `#020617` with a `#1e293b` grid.
- **Shape language** — rounded rectangles (`rx="6"`) for components, dashed boxes for security groups (`stroke-dasharray="4,4"`) and region boundaries (`stroke-dasharray="8,4"`, `rx="12"`).
- **Layering rules** — arrows are drawn **early** in the SVG (right after the grid) so they sit *behind* component boxes. Because component fills are semi-transparent, an **opaque background rect** is drawn under each styled box to mask the arrows that would otherwise show through (`#ffffff` for light, `#0f172a` for dark).
- **Spacing & legend guardrails** — minimum 40px vertical gaps between stacked components, message buses placed *in* the gap, and legends placed **outside** all boundary boxes with the viewBox height expanded to fit.

### The export toolbar (the only JavaScript)

Every generated diagram ships with a collapsible `⋯` toolbar in the header offering three actions:

- **📋 Copy** — high-DPI PNG to clipboard (`scale: 2`)
- **🖼️ PNG** — high-DPI PNG download
- **📄 PDF** — PNG embedded in a one-page PDF

All three use the same [html2canvas](https://html2canvas.hertzen.com/) capture with the toolbar excluded and 32px padding, so the PDF keeps the selected theme (no browser print dialog). Two CDN scripts power this, both **pinned with Subresource Integrity (SRI) hashes** and `crossorigin="anonymous"` so a compromised CDN can't inject tampered code:

- `html2canvas@1.4.1`
- `jspdf@2.5.2`

> The SRI hashes are exact. If you bump a version, recompute the hash — a mismatch will silently block the script from loading.

## How to customize

Because there's no build system, "customizing" means editing either the **template** (to change the default look for all future diagrams) or a **generated file** (to tweak one diagram). Edit `resources/template.html` for light/default output and `resources/template-dark.html` for dark output. Just ask Claude, or edit by hand:

| I want to… | Do this |
|------------|---------|
| Add / remove / move a component | Edit the `<rect>` + `<text>` block; keep the opaque mask rect + styled rect pair |
| Recolor a component type | Change its fill/stroke to another palette row (keep fills semi-transparent) |
| Add a new component category | Pick a new fill/stroke pair and add a legend entry |
| Generate dark output | Ask for a dark theme or start from `resources/template-dark.html` |
| Resize the canvas | Change the SVG `viewBox` (default `1000 × 680`) and the container width |
| Change the font | Swap the Google Fonts `<link>` and the `font-family` in the CSS |
| Change the title / subtitle / footer | Edit the header and footer text nodes |
| Update the summary cards | Edit the three `.card` blocks below the diagram |
| Remove the export toolbar | Delete the `.toolbar` markup, its CSS, the two CDN `<script>` tags, and the `copyAsImage`/`downloadPNG`/`downloadPDF` functions |
| Higher-resolution export | Bump `scale: 2` → `3` or `4` in the capture calls |

### Constraints to respect

- **Keep output self-contained** — inline SVG, embedded CSS, no external images. The only external requests are Google Fonts and the two SRI-pinned export scripts.
- **Avoid SVG `<foreignObject>`** — it renders inconsistently in html2canvas. Stick to plain `<svg>` shapes and `<text>`.
- **Preserve the capture anchors** — `id="report-container"` on the outermost `.container`, the `.toolbar` structure, and the `@media print { .toolbar { display: none } }` rule are what make export work.

## Quick reference: component box pattern

```svg
<!-- Opaque background to mask arrows behind the transparent fill -->
<rect x="X" y="Y" width="W" height="H" rx="6" fill="#ffffff"/>
<!-- Styled component on top -->
<rect x="X" y="Y" width="W" height="H" rx="6"
      fill="rgba(139, 92, 246, 0.12)" stroke="#7c3aed" stroke-width="1.5"/>
<text x="CENTER_X" y="Y+20" fill="#0f172a" font-size="11" font-weight="600" text-anchor="middle">LABEL</text>
<text x="CENTER_X" y="Y+36" fill="#475569" font-size="9" text-anchor="middle">sublabel</text>
```

For dark output, use the same structure with the dark palette, `fill="#0f172a"` for the opaque mask, white labels, and `#94a3b8` sublabels.

See [SKILL.md](SKILL.md) for the full design system and [`examples/`](examples/) for finished diagrams.
