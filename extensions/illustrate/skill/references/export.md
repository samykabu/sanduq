# Export to PNG / SVG

Convert a generated diagram HTML file into a portable `.svg` and/or `.png` next to it. **Manual only — never run unprompted.**

## Trigger

Load this file when:

- The user invokes the packaged export command with an HTML file.
- The user asks in natural language to export, save, rasterize, convert, or download a diagram in `.svg` or `.png` form. Typical phrasings:
  - "export this as PNG"
  - "save as SVG"
  - "give me a PNG of that diagram"
  - "rasterize it"
  - "convert to png and svg"

The command is a thin wrapper around `scripts/export_diagram.py`; natural-language requests use the
same exporter.

## Preferred invocation

Run the bundled exporter from the skill root:

```bash
python scripts/export_diagram.py path/to/diagram.html
python scripts/export_diagram.py path/to/diagram.html --svg-only
python scripts/export_diagram.py path/to/diagram.html --png-only --scale 3
python scripts/export_diagram.py path/to/diagram.html --output path/to/output-base
```

The script validates the source, refuses the gallery, extracts a standalone SVG, checks Playwright
before PNG export, and reports every written file. The procedure below is the behavioral contract
and fallback reference; do not rewrite it into a temporary script when the bundled exporter is
available.

## Animated SVG and GIF for READMEs

`--animated` writes `<name>.animated.svg`; `--gif` writes `<name>.gif` with the same animation.
Both work for any diagram whose connectors carry arrowheads (markers), and for motion figures
(built from `assets/template-motion.html`, with `data-motion-item data-step="N"` groups).

```bash
python scripts/export_diagram.py path/to/diagram.html --animated                    # arrows draw on
python scripts/export_diagram.py path/to/diagram.html --animated --arrows pulse
python scripts/export_diagram.py path/to/diagram.html --gif --arrows chevrons --theme dark
```

Arrow styles (`--arrows`, default `draw`), each moving in the arrow's direction: start to tip,
tip-to-start for start-only heads, and from the middle out for two-headed arrows.

| Style | What moves | Ends |
| --- | --- | --- |
| `draw` | Each arrow draws from its source to its tip, then its arrowhead appears | On the complete figure |
| `flow` | The arrow becomes dashes that keep moving toward the tip | Loops |
| `pulse` | A dot travels along each arrow | Loops |
| `draw-flow` | Draws on like `draw`, then a slow accent dash flow continues | Loops after the draw |
| `chevrons` | Small chevrons slide along each arrow | Loops |

- Motion figures reveal each step once, in `data-step` order, on the figure's own
  `--motion-hold` and `--motion-step` clock (opacity only), and their arrows animate with their step.
  Other diagrams draw their arrows one after another.
- The `.animated.svg` has no script and no remote fonts: image sandboxes block both. Text uses the
  font stack's local fallbacks.
- `prefers-reduced-motion: reduce` shows the complete figure with no animation. With `draw`, the last
  animated frame is that same complete figure.
- Decorative overlays (`data-motion-decorative`) depend on the HTML page and are left out.
- The exporter refuses a figure with neither steps nor arrows, or a reveal longer than 8 seconds.
- `--gif` renders the animation frame by frame in Chromium (Playwright) and needs Pillow
  (`pip install pillow`). `--theme light|dark` picks the colour scheme, `--fps` (1–30, default 15)
  the frame rate, `--scale` the pixel density. A `draw` GIF holds its final frame for 2.5 seconds
  before repeating; looping styles loop seamlessly. A GIF cannot follow the reader's reduced-motion
  setting, so prefer the `.animated.svg` where SVG images are allowed.

Embed either like any image, with alt text that describes the complete figure, and keep the HTML
source beside it.

## Scope

Both formats are **diagram-only** — just the `<svg>` node. Editorial wrappers (header, summary cards, footer in `-full` variants) are intentionally dropped: the export deliverable is the diagram itself, suitable for Figma, slides, social cards, or blog images.

If the user explicitly asks for "a screenshot of the whole page including the cards", that's a different request — fall back to a normal full-page screenshot via the user's OS or browser.

## Theme first

Export the **applied** file, never a raw template or example copy. Run
`python scripts/illustration_theme.py --project-root . apply <diagram.html>` first so the SVG and
PNG carry the project's resolved colors and fonts (see
[`theme-initialization.md`](theme-initialization.md#apply-the-theme-to-a-diagram)); `apply` is
idempotent, so running it again before every export is safe.

## SVG export procedure

1. Read the source HTML file.
2. Extract the **first** `<svg ...>...</svg>` block. Use a multiline regex anchored on `<svg` and `</svg>`. Most generated diagrams have only one SVG; if there are multiple, the first is the diagram (gallery files are an exception — see *Edge cases*).
3. Make it standalone:
   - Ensure the opening tag has `xmlns="http://www.w3.org/2000/svg"`. Add it if missing.
   - Ensure a `viewBox` is present. The skill's templates always include one; warn the user if absent rather than guessing.
   - Inject Google Fonts `@import` so the SVG renders with correct typography in a browser:
     ```svg
     <defs>
       <style>@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap');</style>
     </defs>
     ```
     If the SVG already contains a `<defs>` block, **merge** the `<style>` into it (don't add a second `<defs>`).
4. Prepend `<?xml version="1.0" encoding="UTF-8"?>\n` so the file is well-formed XML.
5. Write to `<basename>.svg` next to the source (e.g. `example-architecture.html` → `example-architecture.svg`). Honour an explicit output path if the user provides one.

### Caveat to surface to the user

Tools that don't fetch remote fonts at import time (offline Illustrator, some Figma import paths, older SVG viewers) will substitute typography. The SVG renders correctly in any modern browser. For pixel-perfect portability, recommend the PNG export.

## PNG export procedure

Render **the original HTML** (not the extracted SVG) and screenshot only the `<svg>` element's bounding box. This keeps font loading reliable (already wired in the source HTML) while satisfying the "diagram only" rule. The PNG always has a **transparent background** (`omit_background=True`) so it can be placed on any slide or doc colour without a white halo.

### Detection

Before running anything, verify Playwright is installed:

```
python -c "import playwright" 2>NUL || python -c "import playwright"
```

If the import fails, surface this exact instruction to the user and stop:

> Playwright isn't installed. To enable PNG export, run:
> ```
> pip install playwright
> playwright install chromium
> ```
> Then ask me to export again.

Don't auto-install. The user asked for one feature, not a system change.

### Rasterize

The bundled exporter implements the following Playwright behavior:

```python
from playwright.sync_api import sync_playwright
import sys, pathlib

src, out = sys.argv[1], sys.argv[2]
scale = int(sys.argv[3]) if len(sys.argv) > 3 else 2

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(device_scale_factor=scale)
    page.goto(f"file://{pathlib.Path(src).resolve()}")
    page.wait_for_load_state("networkidle")
    svg = page.locator("svg").first
    # Release every clipping ancestor (local scroller, overflow:hidden chrome)
    # so an SVG wider than its frame is captured whole.
    svg.evaluate("el => { for (let a = el.parentElement; a; a = a.parentElement) a.style.setProperty('overflow', 'visible', 'important'); }")
    svg.screenshot(path=out, omit_background=True)
    browser.close()
```

The overflow release matters for the wide presets in [`output-spec.md`](output-spec.md): `min-width`
equals the viewBox width, so a 1280-wide SVG inside a 1200px frame is clipped on screen by its
scroller, and without the release the PNG comes out full size with a blank right edge.
`scripts/lint-render.py --self-test` runs this snippet against a wide fixture to keep it honest.

Default `device_scale_factor=2` for crisp output. Accept `1` for compact assets or `3` for print/retina hero use, passed as a third CLI arg.

### Output naming

`example-architecture.html` → `example-architecture.png`, written next to the source. Honour explicit user-provided paths.

## Edge cases

- **Source is `assets/index.html`** (the gallery, multiple SVGs in one file): refuse the export and ask the user which specific diagram file they meant. Don't guess.
- **No `<svg>` block found**: the source isn't a diagram file. Tell the user; don't write anything.
- **Surrounding HTML matters to the user**: they want cards/header in the image. Tell them this skill exports diagrams only, and recommend a browser-based full-page screenshot (or a separate PDF print).
- **Source is missing fonts at runtime**: Playwright will substitute, the screenshot will look off. Check that the source HTML has the `<link href="...fonts.googleapis.com...">` tag in `<head>`. If absent, the file isn't from a current template — fix the source rather than working around it in export.

## What this command never does

- Modifies the source HTML.
- Adds export buttons or `<script>` tags to generated diagrams (the "no JS in deliverables" rule in §11 still stands).
- Auto-emits `.svg` or `.png` alongside HTML generation. Manual on every call.
- Embeds an HTML wrapper (cards, headers) into the SVG via `foreignObject`. Too fragile across renderers.
