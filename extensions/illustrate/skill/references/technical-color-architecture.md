# Technical-Color Architecture Family

Create professional technical architecture diagrams as self-contained HTML files with inline SVG graphics and CSS styling. Default to the light theme. Use the dark theme only when the user prompt explicitly asks for dark mode, a dark background, or a dark-themed output.

Use this optional Illustrate family for system, infrastructure, cloud, security, and network-topology diagrams when semantic component colors or the built-in browser Copy/PNG/PDF toolbar are desired.

## Contents

- [Design system](#design-system)
- [Template](#template)
- [Output](#output)
- [Documentation integration](#documentation-integration)

## Design System

### Theme Selection

- **Default:** use the light theme from `../assets/technical-color/architecture/templates/template.html`.
- **Dark requested:** use `../assets/technical-color/architecture/templates/template-dark.html` when the prompt says "dark", "dark mode", "dark theme", "black background", "slate background", or asks to match an existing technical-color output.
- **Generated filenames:** include `-dark` only for dark variants when helpful for disambiguation. Light diagrams do not need a suffix unless both themes are generated side by side.
- **Do not mix themes:** keep the selected theme consistent across CSS, SVG fills/strokes, text colors, arrow masks, grid lines, summary cards, and export `backgroundColor`.

### Color Palette

Use these semantic colors for component types. The hue family stays consistent between themes, while fill opacity and stroke values shift for contrast.

**Light theme (default):**

| Component Type | Fill (rgba) | Stroke |
|---------------|-------------|--------|
| Frontend | `rgba(14, 165, 233, 0.12)` | `#0284c7` (sky-600) |
| Backend | `rgba(16, 185, 129, 0.12)` | `#059669` (emerald-600) |
| Database | `rgba(139, 92, 246, 0.12)` | `#7c3aed` (violet-600) |
| AWS/Cloud | `rgba(245, 158, 11, 0.14)` | `#d97706` (amber-600) |
| Security | `rgba(244, 63, 94, 0.12)` | `#e11d48` (rose-600) |
| Message Bus | `rgba(249, 115, 22, 0.12)` | `#ea580c` (orange-600) |
| External/Generic | `rgba(100, 116, 139, 0.10)` | `#64748b` (slate-500) |

**Dark theme:**

| Component Type | Fill (rgba) | Stroke |
|---------------|-------------|--------|
| Frontend | `rgba(8, 51, 68, 0.4)` | `#22d3ee` (cyan-400) |
| Backend | `rgba(6, 78, 59, 0.4)` | `#34d399` (emerald-400) |
| Database | `rgba(76, 29, 149, 0.4)` | `#a78bfa` (violet-400) |
| AWS/Cloud | `rgba(120, 53, 15, 0.3)` | `#fbbf24` (amber-400) |
| Security | `rgba(136, 19, 55, 0.4)` | `#fb7185` (rose-400) |
| Message Bus | `rgba(251, 146, 60, 0.3)` | `#fb923c` (orange-400) |
| External/Generic | `rgba(30, 41, 59, 0.5)` | `#94a3b8` (slate-400) |

### Typography

Use JetBrains Mono for all text (monospace, technical aesthetic):
```html
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
```

Font sizes: 12px for component names, 9px for sublabels, 8px for annotations, 7px for tiny labels.

### Visual Elements

**Background:**

- Light: `#f8fafc` (slate-50) with `#e2e8f0` grid lines.
- Dark: `#020617` (slate-950) with `#1e293b` grid lines.

Light grid pattern:
```svg
<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#e2e8f0" stroke-width="0.5"/>
</pattern>
```

Dark grid pattern:
```svg
<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.5"/>
</pattern>
```

**Component boxes:** Rounded rectangles (`rx="6"`) with 1.5px stroke, semi-transparent fills.

**Security groups:** Dashed stroke (`stroke-dasharray="4,4"`), transparent fill, rose color.

**Region boundaries:** Larger dashed stroke (`stroke-dasharray="8,4"`), amber color, `rx="12"`.

**Arrows:** Use SVG marker for arrowheads:
```svg
<marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
  <polygon points="0 0, 10 3.5, 0 7" fill="#64748b" />
</marker>
```

**Arrow z-order:** Draw connection arrows early in the SVG (after the background grid) so they render behind component boxes. SVG elements are painted in document order, so arrows drawn first will appear behind shapes drawn later.

**Masking arrows behind transparent fills:** Since component boxes use semi-transparent fills, arrows behind them will show through. To fully mask arrows, draw an opaque background rect at the same position before drawing the semi-transparent styled rect on top. Use `fill="#ffffff"` for light theme and `fill="#0f172a"` for dark theme:
```svg
<!-- Opaque background to mask arrows -->
<rect x="X" y="Y" width="W" height="H" rx="6" fill="#ffffff"/>
<!-- Styled component on top -->
<rect x="X" y="Y" width="W" height="H" rx="6" fill="rgba(139, 92, 246, 0.12)" stroke="#7c3aed" stroke-width="1.5"/>
```

**Auth/security flows:** Dashed lines in rose color (`#e11d48` light, `#fb7185` dark).

**Message buses / Event buses:** Small connector elements between services. Use orange color (`#ea580c` light, `#fb923c` dark):
```svg
<rect x="X" y="Y" width="120" height="20" rx="4" fill="rgba(249, 115, 22, 0.12)" stroke="#ea580c" stroke-width="1"/>
<text x="CENTER_X" y="Y+14" fill="#ea580c" font-size="7" text-anchor="middle">Kafka / RabbitMQ</text>
```

### Spacing Rules

**CRITICAL:** When stacking components vertically, ensure proper spacing to avoid overlaps:

- **Standard component height:** 60px for services, 80-120px for larger components
- **Minimum vertical gap between components:** 40px
- **Inline connectors (message buses):** Place IN the gap between components, not overlapping

**Example vertical layout:**
```
Component A: y=70,  height=60  → ends at y=130
Gap:         y=130 to y=170   → 40px gap, place bus at y=140 (20px tall)
Component B: y=170, height=60  → ends at y=230
```

**Wrong:** Placing a message bus at y=160 when Component B starts at y=170 (causes overlap)
**Right:** Placing a message bus at y=140, centered in the 40px gap (y=130 to y=170)

### Legend Placement

**CRITICAL:** Place legends OUTSIDE all boundary boxes (region boundaries, cluster boundaries, security groups).

- Calculate where all boundaries end (y position + height)
- Place legend at least 20px below the lowest boundary
- Expand SVG viewBox height if needed to accommodate

**Example:**
```
Kubernetes Cluster: y=30, height=460 → ends at y=490
Legend should start at: y=510 or below
SVG viewBox height: at least 560 to fit legend
```

**Wrong:** Legend at y=470 inside a cluster boundary that ends at y=490
**Right:** Legend at y=510, below the cluster boundary, with viewBox height extended

### Layout Structure

1. **Header** - Title with pulsing dot indicator, subtitle, and export toolbar
2. **Main SVG diagram** - Contained in rounded border card
3. **Summary cards** - Grid of 3 cards below diagram with key details
4. **Footer** - Minimal metadata line

### Export Toolbar (built-in)

Every diagram ships with a single unobtrusive `⋯` toggle in the header. Click it to reveal three buttons — 📋 Copy (high-DPI PNG to clipboard, scale: 2), 🖼️ PNG (high-DPI PNG download), 📄 PDF (PNG embedded in a one-page PDF via jsPDF). The toolbar collapses back to the icon by default so it doesn't clutter the diagram. All three formats use the same html2canvas capture (with the toolbar excluded and 32px padding around the content), so PDF preserves the selected light or dark theme without going through the browser's print dialog.

When generating a new diagram, keep these intact in the template:
- The two CDN scripts in `<head>` (pinned versions, with Subresource Integrity hashes and `crossorigin="anonymous"`):
  - `https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js` — `integrity="sha384-ZZ1pncU3bQe8y31yfZdMFdSpttDoPmOZg2wguVK9almUodir1PghgT0eY7Mrty8H"`
  - `https://cdn.jsdelivr.net/npm/jspdf@2.5.2/dist/jspdf.umd.min.js` — `integrity="sha384-en/ztfPSRkGfME4KIm05joYXynqzUgbsG5nMrj/xEFAHXkeZfO3yMK8QQ+mP7p1/"`
  - SRI ensures generated diagrams are tamper-resistant against CDN compromise. Do not modify the hashes; if the version is bumped, the new hash must be computed fresh.
- `id="report-container"` on the outermost `.container` div (this is what gets captured)
- `.toolbar` markup with `.toolbar-actions` (collapsed by default) and `.toolbar-toggle` (the `⋯` button)
- `.toolbar` CSS + `@media print { .toolbar { display: none !important; } }`
- `copyAsImage()`, `downloadPNG()`, and `downloadPDF()` script before `</body>`, all using `getBoundingClientRect()` + `html2canvas(document.body, { x, y, width, height, ignoreElements })` to capture a precise rect with breathing room and no toolbar

Caveats: clipboard API needs a user gesture and a secure context (https/file/localhost). SVG `<foreignObject>` renders inconsistently in html2canvas — stick to plain `<svg>` shapes and `<text>`. Bump `scale: 2` to `3` or `4` for higher-res output.

### Component Box Pattern

```svg
<rect x="X" y="Y" width="W" height="H" rx="6" fill="FILL_COLOR" stroke="STROKE_COLOR" stroke-width="1.5"/>
<text x="CENTER_X" y="Y+20" fill="#0f172a" font-size="11" font-weight="600" text-anchor="middle">LABEL</text>
<text x="CENTER_X" y="Y+36" fill="#475569" font-size="9" text-anchor="middle">sublabel</text>
```

For dark diagrams, use `fill="white"` for labels and `fill="#94a3b8"` for sublabels.

### Info Card Pattern

```html
<div class="card">
  <div class="card-header">
    <div class="card-dot COLOR"></div>
    <h3>Title</h3>
  </div>
  <ul>
    <li>• Item one</li>
    <li>• Item two</li>
  </ul>
</div>
```

## Template

Copy and customize the selected theme template:

- Light/default: `../assets/technical-color/architecture/templates/template.html`
- Dark: `../assets/technical-color/architecture/templates/template-dark.html`

Key customization points:

1. Update the `<title>` and header text
2. Modify SVG viewBox dimensions if needed (default: `1000 x 680`)
3. Add/remove/reposition component boxes
4. Draw connection arrows between components
5. Update the three summary cards
6. Update footer metadata

## Output

Always produce a single self-contained `.html` file with:
- Embedded CSS (no external stylesheets except Google Fonts)
- Inline SVG (no external images)
- The built-in export JavaScript preserved from the selected template

The file should render correctly when opened directly in any modern browser. The export toolbar uses two CDN scripts (html2canvas and jsPDF) — no other JavaScript dependencies.

## Documentation Integration

When Illustrate is invoked by `speckit.pr.generate`, `how-to-test`, or
`speckit.how-to-test.document`, generate both a source HTML
diagram and an exported PNG image:

- **Source HTML:** write to the feature documentation assets folder, for example
  `docs/<feature-slug>/assets/diagrams/<feature-slug>-architecture.html` or
  `<how-to-test-root>/assets/<parent-feature>/<feature-slug>-architecture.html`.
- **PNG export:** render the HTML and export a PNG beside the source, for example
  `<feature-slug>-architecture.png`. Use the built-in html2canvas export path when running in a
  browser, or automate an equivalent screenshot of `#report-container` with Playwright/Puppeteer
  when available.
- **Embedding:** generated Markdown or HTML docs must embed the PNG and link to the HTML source for
  inspection/export. Use descriptive alt text that names the feature and architecture boundary.
- **Grounding:** only generate this diagram when the feature changes or clarifies architecture,
  infrastructure, service boundaries, data flow, integrations, security zones, deployment topology,
  or major component responsibilities. If no architecture impact is found, explicitly omit the
  diagram instead of inventing one.
- **Fallback:** if PNG export tooling is unavailable, keep the HTML source, add a clear note in the
  generated documentation that the PNG export is pending, and report the follow-up. Do not silently
  embed a broken image.
