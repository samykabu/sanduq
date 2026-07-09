# Process Flow Diagram Skill

Turn a plain-English description of a workflow into a polished **process flow diagram** rendered as a single self-contained HTML file (inline SVG + embedded CSS). The skill defaults to a light theme and switches to the dark theme when the prompt explicitly asks for it. Best for sequential, step-by-step processes: approval flows, automation pipelines, runbooks, onboarding, and decision trees.

For non-sequential system relationships (components, infrastructure, cloud topology), use the sibling [`architecture-diagram`](../architecture-diagram/) skill instead — same design language, different shape language.

## How the skill works (from the outside)

1. **You describe the process** — an ordered list of steps, who does each one (human vs. system), triggers, outputs, and any decision branches. Paste it, have Claude summarize an existing runbook, or ask for a typical process.
2. **Claude activates the skill** — the `description` in [SKILL.md](SKILL.md) triggers on requests for workflow diagrams, process maps, approval flows, or automation sequences.
3. **Claude picks a theme template** — it starts from [`resources/template.html`](resources/template.html) for light diagrams, or [`resources/template-dark.html`](resources/template-dark.html) when you ask for dark mode. Then it lays out numbered step boxes left-to-right, adds decision diamonds, draws labeled arrows, and fills the summary cards.
4. **You get one `.html` file** — open it in any browser. Use the header toolbar to Copy / export PNG / export PDF.
5. **You iterate in chat** — "add a rejection branch from step 3", "make step 2 automated", "wrap this to a second row" — Claude edits the same file.

## Documentation automation

When called by the `pr-generate-description`, `speckit.pr.generate`, `how-to-test`, or
`speckit.how-to-test.document` workflows, this skill should produce both:

- A source HTML file under the relevant feature documentation assets folder.
- A PNG export beside it, embedded in the generated documentation with a link back to the HTML source.

Only create the diagram when the implementation actually changes or clarifies a user journey,
approval process, automation sequence, validation flow, background job, integration handoff, or error
recovery path.

## How it works internally

The skill is **instructions + a template**, not code. Claude reads the design system and layout math in [SKILL.md](SKILL.md) and applies them while editing the HTML.

### Files

```
process-flow-diagram/
├── SKILL.md               # The design system, layout math + QA checklist Claude follows
├── resources/
│   ├── template.html      # Light/default HTML/SVG scaffold
│   └── template-dark.html # Dark HTML/SVG scaffold
├── examples/              # Reference outputs covering each layout pattern
│   ├── sprint-report-flow.html      # automation flow (manual + AI + integration)
│   ├── sprint-report-flow-light.html
│   ├── ai-governance-workflow.html  # 5 steps + decision + drift loop-back
│   ├── ai-governance-workflow-light.html
│   ├── it-change-management.html    # two-row wrap, 7 steps + 2 decisions
│   ├── it-change-management-light.html
│   ├── inventory-control.html       # cyclical reorder cycle + exception path
│   ├── inventory-control-light.html
│   └── images/            # PNG previews of the examples
└── README.md              # This file
```

### The design system (what SKILL.md encodes)

- **Theme selection** — light is the default; dark is selected only when the prompt asks for dark mode, a dark background, or to match an existing dark output.
- **Semantic color palette** — each step type keeps the same meaning across themes:

  Light/default:

  | Step type | Color | Fill (rgba) | Stroke | Shape/Indicator |
  |-----------|-------|-------------|--------|-----------------|
  | Start/End | Sky | `rgba(14, 165, 233, 0.12)` | `#0284c7` | Pill shape |
  | Manual | Emerald | `rgba(16, 185, 129, 0.12)` | `#059669` | Actor label |
  | Automated | Violet | `rgba(139, 92, 246, 0.12)` | `#7c3aed` | Automated label |
  | Integration/API | Amber | `rgba(245, 158, 11, 0.14)` | `#d97706` | Integration label |
  | Decision | Rose | `rgba(244, 63, 94, 0.12)` | `#e11d48` | Diamond |
  | Prerequisite | Slate | `rgba(100, 116, 139, 0.10)` | `#64748b` | Dashed border |

  Dark:

  | Step type | Color | Fill (rgba) | Stroke | Shape/Indicator |
  |-----------|-------|-------------|--------|-----------------|
  | Start/End | Cyan | `rgba(8, 51, 68, 0.4)` | `#22d3ee` | Pill shape |
  | Manual | Emerald | `rgba(6, 78, 59, 0.4)` | `#34d399` | Actor label |
  | Automated | Violet | `rgba(76, 29, 149, 0.4)` | `#a78bfa` | Automated label |
  | Integration/API | Amber | `rgba(120, 53, 15, 0.3)` | `#fbbf24` | Integration label |
  | Decision | Rose | `rgba(136, 19, 55, 0.4)` | `#fb7185` | Diamond |
  | Prerequisite | Slate | `rgba(30, 41, 59, 0.3)` | `#94a3b8` | Dashed border |

- **Typography** — JetBrains Mono at 11/9/8/10px for step names / descriptions / annotations / step numbers.
- **Canvas** — light uses `#f8fafc` with a subtle `#e2e8f0` grid; dark uses `#020617` with a `#1e293b` grid.
- **Shape language** — rounded step boxes (`rx="8"`, min 140×70px) with a numbered badge circle top-left; pill shapes for start/end; rotated squares for decision diamonds; dashed containers for prerequisites.

### Layout math (the part that prevents clipped diagrams)

The trickiest internal detail is **viewBox sizing** — get it wrong and the right edge clips (and the clipped region won't survive PNG/PDF export). SKILL.md encodes explicit formulas:

- **Step stride is 220px** (160px box + 60px gap for arrow labels).
- `viewBox width = (steps × 220) + 200px padding`, **+120** per inline decision diamond, **+100** for a right-side exit node.
- **Three numbers must stay equal:** the `viewBox` width, `svg { min-width }`, and `.container { max-width } − 48`. The `+48` accounts for the `.diagram-container`'s 24px side padding. If they drift apart you get a horizontal scrollbar and a clipped right edge.
- Default safe canvas: `viewBox="0 0 1300 540"`, `svg { min-width: 1300px }`, `.container { max-width: 1348px }`.

### Layout patterns

- **Horizontal flow (default)** — prerequisites on top, start pill left, steps rightward, end pill right, info cards below.
- **Multi-row wrap** — for >5 steps, wrap to a second row bridged by a dashed slate connector instead of growing the canvas past ~1500px.
- **Cyclical loop-back** — for always-on processes (no start/end pill), a dashed cyan arrow travels over the top of the row from last step back to first.
- **Exception paths** — off-happy-path branches (QC fail, rejection) use a rose dashed stroke *below* the row.

### Built-in QA step

Unlike the architecture skill, SKILL.md tells Claude to **preview and self-correct** after generating: check for right-edge cutoff, overlaps, disconnected arrows, and label collisions, then fix and re-preview. In Claude Code that means asking you to open the file and report issues; with browser tools it screenshots and inspects.

### The export toolbar (the only JavaScript)

Identical to the architecture skill: a collapsible `⋯` header toolbar with **📋 Copy / 🖼️ PNG / 📄 PDF**, all using one [html2canvas](https://html2canvas.hertzen.com/) capture (toolbar excluded, 32px padding) so PDF keeps the selected theme. Two CDN scripts, both **pinned with SRI hashes** and `crossorigin="anonymous"`:

- `html2canvas@1.4.1`
- `jspdf@2.5.2`

> The SRI hashes are exact. Bumping a version requires recomputing the hash, or the script silently won't load.

## How to customize

Edit the **template** to change the default for all future diagrams, or a **generated file** to tweak one. Edit `resources/template.html` for light/default output and `resources/template-dark.html` for dark output. Just ask Claude, or edit by hand:

| I want to… | Do this |
|------------|---------|
| Add / remove / reorder a step | Edit the badge circle + box `<rect>` + text block; renumber badges; re-run the stride math |
| Add a decision branch | Insert a rotated-square diamond and label the outgoing arrows (Yes/No) |
| Change a step's type | Recolor the box + badge to another palette row and swap the actor/indicator |
| Generate dark output | Ask for a dark theme or start from `resources/template-dark.html` |
| Fit more than ~5 steps | Switch to the multi-row wrap pattern (dashed slate connector) |
| Model an always-on process | Drop the start/end pills, add the cyclical loop-back arrow over the top |
| Widen the canvas | Change all three linked numbers together: `viewBox` width, `svg min-width`, `.container max-width` (= viewBox + 48) |
| Change the font | Swap the Google Fonts `<link>` and the CSS `font-family` |
| Update the title / footer / cards | Edit the header, footer, and the three `.card` blocks |
| Remove the export toolbar | Delete the `.toolbar` markup, its CSS, the two CDN `<script>` tags, and the `copyAsImage`/`downloadPNG`/`downloadPDF` functions |
| Higher-resolution export | Bump `scale: 2` → `3` or `4` in the capture calls |

### Constraints to respect

- **Keep output self-contained** — inline SVG, embedded CSS, no external images. The only external requests are Google Fonts and the two SRI-pinned export scripts.
- **Avoid SVG `<foreignObject>`** — renders inconsistently in html2canvas; use plain `<svg>` shapes and `<text>`.
- **Preserve the capture anchors** — `id="report-container"` on the outermost `.container`, the `.toolbar` structure, and the `@media print` rule are what make export work.
- **Keep the three width numbers in sync** — the most common visual bug is a clipped right edge from a viewBox / min-width / max-width mismatch.

## Quick reference: step box pattern

```svg
<!-- Step number badge -->
<circle cx="X" cy="Y" r="12" fill="#ffffff" stroke="STROKE_COLOR" stroke-width="1.5"/>
<text x="X" y="Y+4" fill="#0f172a" font-size="10" font-weight="600" text-anchor="middle">N</text>

<!-- Step box -->
<rect x="X+5" y="Y+5" width="160" height="80" rx="8" fill="FILL_COLOR" stroke="STROKE_COLOR" stroke-width="1.5"/>
<text x="CENTER_X" y="Y+30" fill="#0f172a" font-size="11" font-weight="600" text-anchor="middle">Step Name</text>
<text x="CENTER_X" y="Y+48" fill="#64748b" font-size="9" text-anchor="middle">Description</text>
```

For dark output, use `fill="#1e293b"` for badge circles, `fill="white"` for step titles/badge numbers, and `fill="#94a3b8"` for descriptions.

See [SKILL.md](SKILL.md) for the full design system, layout math, QA checklist, and a worked coordinate example; see [`examples/`](examples/) for finished diagrams covering each pattern.
