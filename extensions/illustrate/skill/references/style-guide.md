# Style Guide

**The semantic contract for colors, typography, and tokens.** Every diagram uses these roles rather
than treating literals in templates as policy. Built-in values live in
[`../assets/illustration-themes.yml`](../assets/illustration-themes.yml), while the active project
selection and project custom themes live in `.github/illustration-theme.yml`.

The default skin is Cobalt Porcelain. It is designed for high-clarity technical documentation and
uses IBM Plex with Arabic-capable fallbacks. Emerald Mist and Sanduq Classic are also built in. To
initialize, select, or create a theme, see [`theme-initialization.md`](theme-initialization.md).

---

## Tokens

### Semantic roles

Every token is referred to by **semantic role**, not by its hex value. Type references (`type-*.md`) and SKILL.md say `accent`, not `#f7591f`.

| Role | Purpose | Default (light) | Default (dark) |
|---|---|---|---|
| `paper` | Page background, default node fill | `#f6f8fc` | `#101827` |
| `paper-2` | Diagram container bg, secondary fill | `#ffffff` | `#17233a` |
| `ink` | Primary text, primary stroke | `#15233c` | `#f5f7fb` |
| `muted` | Secondary text, default arrow stroke | `#4f6078` | `#b6c2d4` |
| `soft` | Sublabels, boundary labels | `#6b7a90` | `#8796ac` |
| `rule` | Hairline borders | `rgba(21,35,60,0.12)` | `rgba(245,247,251,0.12)` |
| `rule-solid` | Stronger borders, baselines | `#c7d2e2` | `#40506a` |
| `accent` | Focal / 1–2 max per diagram | `#2563eb` | `#6ea0ff` |
| `accent-tint` | Fill for accent-bordered boxes | `rgba(37,99,235,0.09)` | `rgba(110,160,255,0.14)` |
| `link` | HTTP/API calls, external arrows | `#1d4ed8` | `#8ab4ff` |

> **Preset source:** these values are the `cobalt` preset. Do not copy them into a consumer project
> unless defining a custom derivative; selecting `cobalt` is enough.

> **Note:** The pre-baked example HTML files in `assets/` were built under an earlier skin. Regenerating them against the current `style-guide.md` is a v5.1 task. New diagrams the skill produces will use the tokens above.

### Inversion rule (light → dark)

Opacity-based light tokens invert from the active light `ink`/`accent` RGB values to the active dark
`ink`/`accent` RGB values. Keep the same semantic opacity unless contrast requires an adjustment.

### Series palette (multi-series chart types only)

A small set of desaturated, editorial-tone colors for chart types that genuinely need to distinguish multiple overlapping entities (currently: **radar**). The "1-focal" rule still holds — `accent` is reserved for the focal series; the palette below covers the rest.

| Token | Light | Dark | Notes |
|---|---|---|---|
| `series-1` | `#7c8f6f` (sage) | `#9caf8f` | Non-focal series |
| `series-2` | `#5e7a9b` (dusty-blue) | `#82a0c0` | Non-focal series |
| `series-3` | `#b8915a` (mustard) | `#d3ad7a` | Non-focal series |
| `series-4` | `#9c6b50` (rust-brown) | `#b88670` | Non-focal series |
| `series-5` | `#6e6479` (slate) | `#8d8298` | Non-focal series |

Fills sit at `0.18` opacity light, `0.22` dark; strokes use the full color. **Don't backfill these tokens to non-chart types** — architecture, swimlane, etc. continue to use muted-ink variants. The series palette is opt-in for diagrams where overlapping shapes demand distinguishable color, not a license to add color elsewhere.

### Terminal skin (opt-in alternate)

A self-contained palette for the terminal-window primitive (see [primitive-terminal.md](primitive-terminal.md)) — a CLI-chrome register for dev-tool posts and technical social cards. It does not replace the default skin above and isn't affected by onboarding; it's a second, fixed skin you opt into per-diagram.

| Token | Hex | Purpose |
|---|---|---|
| `terminal-page` | `#0a0a0a` | Page background behind the window |
| `terminal-paper` | `#141414` | Window body, node fill |
| `terminal-bar` | `#1b1b1b` | Titlebar strip |
| `terminal-border` | `#2b2b2b` | Window border, hairlines |
| `terminal-ink` | `#f5f5f5` | Primary text, primary stroke (same white-smoke as default `ink`) |
| `terminal-muted` | `#9a9a9a` | Secondary text, sublabels, ring stroke |
| `terminal-soft` | `#5c5c5c` | Tertiary — inactive dots, spokes |
| `terminal-accent` | `#ff5a36` | The one accent — focal station, prompt sign, active dot |
| `terminal-accent-tint` | `rgba(255,90,54,0.12)` | Fill for accent-bordered boxes |

**1-accent rule still holds.** Everything that isn't `terminal-ink` or `terminal-muted`/`terminal-soft` should be `terminal-accent` — never introduce a second hue.

---

## Typography

| Role | Family | Size | Weight | Usage |
|---|---|---|---|---|
| `title` | Resolved `serif` | 1.75rem | 400 | Page H1 |
| `node-name` | Resolved `sans` | 12px | 600 | Human-readable labels |
| `sublabel` | Resolved `mono` | 9px | 400 | Port, protocol, URL, field type |
| `eyebrow` | Resolved `mono` | 7–8px | 500, tracked 0.18em, uppercase | Type tags, axis labels |
| `arrow-label` | Resolved `mono` | 8px | 400, tracked 0.06em | Arrow annotations |
| `callout` | Resolved `serif` *italic* | 14px | 400 | Editorial asides only |

### Font stack

```html
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:ital,wght@0,400;1,400&family=Noto+Naskh+Arabic:wght@400;500;600&family=Noto+Sans+Arabic:wght@400;500;600&display=swap" rel="stylesheet">
```

**Load-bearing rule:** Mono is for *technical* content (ports, commands, URLs, field types). Names use
the resolved sans stack. Page titles and italic callouts use the resolved serif stack. Built-in
stacks include Arabic fallbacks. Respect `font_loading`: import `remote_css_url` only for `remote`.

---

## Stroke, radius, spacing

| Token | Value | Use |
|---|---|---|
| `stroke-thin` | `0.8` | Tag-box outlines, leaf nodes |
| `stroke-default` | `1` | Most strokes |
| `stroke-strong` | `1.2` | Emphasis strokes |
| `radius-sm` | `4` | Small tags |
| `radius-md` | `6` | Node boxes |
| `radius-lg` | `8` | Containers, rings |
| `grid` | `4` | Every coord, size, and gap is divisible by 4 (hard rule) |

---

## Node type → treatment

Semantic role combinations — reference these by name in type specs.

| Type | Fill | Stroke |
|---|---|---|
| `focal` (1–2 max) | `accent-tint` | `accent` |
| `backend` | `#ffffff` (white) | `ink` |
| `store` | `ink @ 0.05` | `muted` |
| `external` | `ink @ 0.03` | `ink @ 0.30` |
| `input` | `muted @ 0.10` | `soft` |
| `optional` | `ink @ 0.02` | `ink @ 0.20` dashed `4,3` |
| `security` | `accent @ 0.05` | `accent @ 0.50` dashed `4,4` |

---

## Customizing the skin

Three options:

1. **Select a preset** — initialize or set Cobalt, Emerald, or Classic in the project YAML.
2. **Create a project theme** — use `illustration_theme.py create` for complete light/dark colors and fonts.
3. **Run onboarding** — extract tokens from a URL, installed skill, local folder, or design document, then import the approved theme into the project YAML.

### Constraints (don't break these)

- **Contrast**: `ink` must hit WCAG AA on `paper`. `muted` must hit AA on `paper` for 11px+ text.
- **One accent**: pick one color for `accent`. Two accents erases the focal signal.
- **No rainbow palette**: if your brand ships 8 colors, pick 3 (paper, ink, accent). The rest become `muted` variants.
- **Serif + sans + mono**: define no more than three role stacks. Each stack may include Arabic and system fallbacks.
- **Paper is warm-neutral, not pure white**: pure white turns the design sterile. Pick a cream, bone, or light grey with a hint of warmth.
- **Dot pattern is optional, not default**: the 22×22 dot pattern is an opt-in "dotted paper" variant (good for long-form editorial hero diagrams). The default background is a clean `paper` fill, no pattern. When the pattern is enabled, it should sit at ~10% opacity of `ink` on `paper` — visible but quiet.
- **Container is clean by default**: the diagram sits directly on the page paper, no secondary container background or border. A framed variant (`paper-2` bg + `rule` border + 8px radius + padding) is available as an opt-in for card-heavy layouts, but don't reach for it by default — the extra chrome fights the figure.
