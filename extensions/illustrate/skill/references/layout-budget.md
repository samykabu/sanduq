# Layout grid, per-type budgets, page layout, and summary cards

Routed from SKILL.md §7 and §8. SKILL.md keeps the grid rule in one line, the universal complexity limits, and the split rule. This file holds the full grid table, every per-type budget row, the page layout, and the summary card pattern.

## Layout & Spacing

### 4px grid

**Structural geometry, divisible by 4:** node origins, widths, heights, gaps, padding, and x / y coordinates of boxes. Non-negotiable. Off-grid by design: type sizes (role ramp in [`output-spec.md`](output-spec.md)), radii, data-derived positions, text baselines, arrow markers, `.5` offsets that keep 1px strokes crisp, stroke widths (0.8, 1, 1.2), opacity values, and the 22×22 dot-pattern.

| Category | Allowed values |
|---|---|
| Node width / height | 80, 96, 112, 120, 128, 140, 144, 160, 180, 200, 240, 320 |
| x / y coordinates (boxes, zones) | multiples of 4 |
| Gap between nodes | 20, 24, 32, 40, 48 |
| Padding inside boxes | 8, 12, 16 |
| Border radius | 4, 6, 8 |

Quick check: if a structural coordinate ends in 1, 2, 3, 5, 6, 7, 9 — fix it.

### Complexity budget (per diagram)

These are the per-type limits. The universal rows in SKILL.md §7 (9 nodes, 12 arrows or transitions, 2 accent elements, 2 annotation callouts) apply to every type on top of these, and a semantic pattern's own budget in [semantic-patterns.md](semantic-patterns.md) can only tighten them.

| Limit | Rule |
|---|---|
| Max lifelines (sequence) | 5 |
| Max lanes (swimlane) | 5 |
| Max items (quadrant) | 12 |
| Max entities (ER) | 8 |
| Max nesting levels (nested) | 6 |
| Max tree depth | 4 |
| Max org chart depth | 4 |
| Max org chart nodes | 12 |
| Max layers (layer stack) | 6 |
| Max circles (venn) | 3 |
| Max layers (pyramid) | 6 |
| Max radar axes | 5 |
| Max radar series | 5 |
| Max focal radar series | 1 |
| Max bars (bar chart) | 8 |
| Max series (line chart) | 5 |
| Max tasks (Gantt) | 12 |
| Max points (scatter plot) | 30 |
| Max unique components / relationships / ledger entries (architecture delta) | 8 / 10 / 8 |
| Max zones / nodes / paths (deployment) | 3 / 6 / 8, 9 artifacts |
| Max nodes / edges (dependency) | 9 / 14, 4 ranks, 1 cycle |
| Max classes / relationships (UML class) | 7 / 8, 5 members per compartment |
| Max tables / FK edges (database schema) | 5 / 6, 8 column rows per table |
| Max polar categories / series / focal categories | 8 / 1 / 1 |
| Max cells (treemap) | 8 |
| Max columns / series (marimekko) | 8 / 5 |
| Max columns / cards (kanban) | 5 / 12 total, 4 per column |
| Max stages / rows (user journey) | 6 / 3, 2 pain markers |
| Max activities / slices / cards (story map) | 5 / 3 / 12 |
| Max bars (waterfall) | 8 incl. totals, 1 subtotal |
| Max rows × cols (heatmap) | 7 × 8, 1 focal cell |
| Max stages / nodes / flows (sankey) | 3 / 8 / 12 |
| Max categories (fishbone) | 5 bones, 3 sub-causes each |
| Max components / links (wardley) | 9 / 12, 2 movement arrows |
| Max parts / levels / focal parts (exploded axonometric) | 5 / 5 / 1, three detail levels |
| Max tagged rooms or buildings / boxes / focal (axonometric plan) | 8 / 40 / 1 |
| Max motion (optional) | 8 steps, 12 marked items, 2 simultaneous items |

If you exceed, split into two diagrams (overview + detail).

### Page layout

1. **Header** — eyebrow (resolved mono), title (resolved serif), optional subtitle (resolved sans + muted).
2. **Diagram container** — default: **clean, borderless**, no background — the SVG sits directly on the page paper. Optional *framed* variant (for card-heavy layouts or hero placements): `paper-2` bg + 1px `rule` border + 8px radius + `1.5rem` padding + `overflow-x: auto`. Either way the SVG sits in a local `overflow-x: auto` wrapper with `min-width` equal to its viewBox width (see [output-spec.md § Holding the canvas on a narrow screen](output-spec.md#holding-the-canvas-on-a-narrow-screen)).
3. **Summary cards** — 2–3 col grid with *varied* widths (e.g., `1.1fr 1fr 0.9fr`).
4. **Footer** — colophon in resolved mono, muted, hairline top border.

## Summary Card Pattern

Don't use 3 identical generic cards. Vary the treatment:

```html
<div class="card">
  <p class="eyebrow">SECTION LABEL</p>
  <div class="card-header">
    <span class="card-dot accent"></span>
    <h3>Card Title</h3>
  </div>
  <ul><li>Item</li></ul>
</div>
```

Rules:

- `background: #ffffff` (not paper — slight lift without shadow)
- `border: 1px solid rgba(45,49,66,0.12)` (resolved `rule`)
- `border-radius: 6px`, `padding: 1.25rem`
- **No `box-shadow`**
- Card dots: 7px, `border-radius: 50%` — ink / muted / accent / link / soft variants
