# Export to PNG / SVG

Convert a generated diagram HTML file into a portable `.svg` and/or `.png` next to it. **Manual only — never run unprompted.**

## Trigger

A normal export needs only `python scripts/export_diagram.py` and the flags in SKILL.md §12. Read this file
when the exporter exits non-zero, when the request needs the animation options below, or when no exporter
can run (the procedures further down are the fallback contract). The requests it covers:

- The user invokes an export command (such as Sanduq's `speckit.illustrate.export`) with an HTML file.
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
python scripts/export_diagram.py path/to/diagram.html --png-only --scale 1.25      # exact 1.25x pixels
python scripts/export_diagram.py path/to/diagram.html --system-fonts              # offline: no font fetches
python scripts/export_diagram.py path/to/diagram.html --output path/to/output-base
```

The script validates the source, refuses the gallery, extracts a standalone SVG, checks Playwright
before PNG export, and reports every written file. Output names never change: `<base>.svg`,
`<base>.png`, `<base>.animated.svg`, `<base>.gif`. When the SVG is written but the PNG fails
(no Playwright, no Chromium, a motion figure that never reaches its static frame), the exit code
is 2, the SVG is still listed, and the error names what to fix.

| Flag | Values |
| --- | --- |
| `--scale` | PNG: any finite number from 1 to 4, fractions included (`1.25`); GIF: 1, 2 or 3. Default 2. |
| `--system-fonts` | SVG without the Google Fonts `@import`; PNG captured with remote requests blocked. Text falls through the theme's font stacks to installed faces. |
| `--svg-only` / `--png-only` | One format. |
| `--output <base>` | Output base; the extension is appended. | The procedure below is the behavioral contract
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
2. Extract the first live SVG element and its nested SVG icons. Ignore comments, raw-text elements and inert templates. Gallery files remain a separate case.
3. Make it standalone:
   - Ensure the opening tag has `xmlns="http://www.w3.org/2000/svg"`. Add it if missing; refuse any
     other value. Declare `xmlns:xlink` when the figure uses `xlink:href`.
   - Ensure the root `viewBox` is four finite numbers with a positive width and height. The skill's
     templates always include one; refuse rather than guess when it is absent or invalid.
   - Drop HTML comments (refuse `<!-->`, `<!--->` and `--!>`, which a browser closes early), quote
     valueless and unquoted attributes, and turn HTML character references into XML text once
     (`&nbsp;`, `&rarr;`; numeric ones keep their HTML meaning, so `&#128;` is the euro sign).
     CDATA and `<style>`/`<script>` bodies are copied unchanged.
   - Inject the page's own Google Fonts as an `@import` so the SVG renders with the applied theme's
     typography in a browser. The source `<link>` supplies the font profile. A sample with no link or theme stamp uses the bundled default:
     ```svg
     <defs>
       <style>@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&amp;family=Geist:wght@400;500;600&amp;family=Geist+Mono:wght@400;500;600&amp;display=swap');</style>
     </defs>
     ```
     Only `https://fonts.googleapis.com/css2?` URLs are carried. Local and system theme stamps and `--system-fonts` omit the remote font import.
     If the SVG already contains a `<defs>` block, **merge** the `<style>` into it (don't add a second
     `<defs>`); a new `<defs>` goes after the leading `<title>` and `<desc>`, which stay first.
   - Carry the page's live `<style>` rules (not commented-out styles, not style text inside `<script>`
     or `<textarea>`; CDATA in an SVG style is unwrapped). Scope the carried selectors to the exported
     SVG so inline figures keep separate theme tokens. `html` and `body` rules pass only tokens and
     inherited text and paint properties. `@media` (print included), `@supports`
     and `@layer` keep their conditions, so print-only paint stays print-only; `@import`,
     `@font-face`, `@keyframes`, animation and transition declarations and motion runtime selectors
     stay behind. CSS comments go; quoted text that looks like a comment, and escaped selector
     characters, stay.
   - Prefix every referenceable `<defs>` ID with the file slug (`flow.html`: `arrow` becomes
     `flow-arrow`) and retarget `url(#id)` (quoted, `&quot;`-quoted and CSS-escaped forms),
     `href`/`xlink:href="#id"`, SMIL paint values and `#id` selectors, so two exported figures inlined
     in one page cannot resolve each other's markers or gradients. IDs that already carry the prefix
     and IDs outside `<defs>` (title, desc) are unchanged.
   - For PowerPoint, which paints `rgba(...)` and `transparent` opaque black: split `fill`/`stroke`
     presentation attributes into hex paint plus `fill-opacity`/`stroke-opacity` (`transparent`
     becomes `none`), clamping channels and alpha, and combining an existing local opacity. Keep the
     rgba when CSS, an inherited opacity or a descendant's own paint makes the split unsafe.
4. Prepend `<?xml version="1.0" encoding="UTF-8"?>\n` and parse the result: refuse to write an SVG
   that is not well-formed XML.
5. Write to `<basename>.svg` next to the source (e.g. `example-architecture.html` → `example-architecture.svg`). Honour an explicit output path if the user provides one.

### Caveat to surface to the user

Tools that don't fetch remote fonts at import time (offline Illustrator, some Figma import paths, older SVG viewers) will substitute typography. The SVG renders correctly in any modern browser. For pixel-perfect portability, recommend the PNG export. For an offline or air-gapped destination, `--system-fonts` leaves the `@import` out so nothing is fetched and text uses installed faces from the theme's font stacks.

## PNG export procedure

Render **the original HTML** (not the extracted SVG) and screenshot only the `<svg>` element's bounding box. This keeps font loading reliable (already wired in the source HTML) while satisfying the "diagram only" rule. The PNG has a **transparent background** (`omit_background=True`) wherever the page itself paints none, so it can be placed on any slide or doc colour without a white halo.

The PNG is exactly the viewBox size times `--scale` (rounded to whole pixels): the SVG is pinned to
one CSS pixel per viewBox unit. Capture rounds each dimension to a whole pixel, even at fractional page positions. Waits are
bounded: if the page never goes network-idle within 15 s (a stalled font or stylesheet behind a
proxy), the exporter cancels the load with `window.stop()`, captures with fallback typography and
prints a warning to stderr (pass it on); font readiness is awaited for at most 5 s. Motion figures
load with `?motion=static` under reduced motion, and every `[data-motion-root]` must reach
`data-frame="static"` (the complete figure) or the PNG is refused.

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
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
import math, pathlib, sys

src, out = pathlib.Path(sys.argv[1]), sys.argv[2]
scale = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
if not math.isfinite(scale) or not 1 <= scale <= 4:
    sys.exit("scale must be a number from 1 to 4")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(device_scale_factor=scale, reduced_motion="reduce")
    page.goto(src.resolve().as_uri() + "?motion=static", wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        # A stalled webfont request: cancel it and capture with fallback typography.
        page.evaluate("window.stop()")
        page.wait_for_timeout(4_000)
        print("warning: captured with fallback typography", file=sys.stderr)
    page.evaluate("Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 5000))])")
    page.wait_for_function("[...document.querySelectorAll('[data-motion-root]')]"
                           ".every(r => r.dataset.frame === 'static')", timeout=5_000)
    svg = page.locator("svg").first
    # Release every clipping ancestor (local scroller, overflow:hidden chrome)
    # so an SVG wider than its frame is captured whole.
    svg.evaluate("el => { for (let a = el.parentElement; a; a = a.parentElement) a.style.setProperty('overflow', 'visible', 'important'); }")
    # One CSS pixel per viewBox unit, snapped to the device-pixel grid: exact viewBox x scale pixels.
    svg.evaluate("""el => {
        const box = el.viewBox.baseVal;
        if (![box.width, box.height].every(n => Number.isFinite(n) && n > 0))
            throw new Error('PNG export needs a finite, positive viewBox');
        for (const [axis, size] of [['width', box.width], ['height', box.height]])
            for (const prefix of ['', 'min-', 'max-'])
                el.style.setProperty(prefix + axis, size + 'px', 'important');
        const k = devicePixelRatio, r = el.getBoundingClientRect();
        const snap = v => (Math.round(v * k) - v * k) / k;
        el.style.setProperty('translate', `${snap(r.left + scrollX)}px ${snap(r.top + scrollY)}px`, 'important');
    }""")
    svg.screenshot(path=out, omit_background=True)
    browser.close()
```

The overflow release matters for the wide presets in [`output-spec.md`](output-spec.md): `min-width`
equals the viewBox width, so a 1280-wide SVG inside a 1200px frame is clipped on screen by its
scroller, and without the release the PNG comes out full size with a blank right edge.
`scripts/lint-render.py --self-test` runs this snippet against a wide fixture to keep it honest.

Default `device_scale_factor=2` for crisp output. Accept `1` for compact assets, `3` or `4` for print/retina hero use, or a fraction such as `1.25` for an exact pixel size, passed as a third CLI arg. Never go past 4: redraw at a larger size preset instead. `--gif` keeps its own scales 1, 2 and 3.

### Output naming

`example-architecture.html` → `example-architecture.png`, written next to the source. Honour explicit user-provided paths.

## Edge cases

- **No source path given**: ask which `.html` file to export. Don't guess.
- **`--scale` not a finite number from 1 to 4** (or, with `--gif`, not 1, 2 or 3): reject it and name the valid values.
- **A file name with `#` or `%`**: fine; the source is opened as a percent-encoded `file://` URI.
- **Two exported SVGs inlined in one page**: fine; defs IDs carry each file's slug.
- **Block metadata requested** (`--registry`, a Traceable block decomposition): follow [`export-registry.md`](export-registry.md); the sidecar is `<name>.registry.json`.
- **Source is `assets/index.html`** (the gallery, multiple SVGs in one file): refuse the export and ask the user which specific diagram file they meant. Don't guess.
- **No `<svg>` block found**: the source isn't a diagram file. Tell the user; don't write anything.
- **Surrounding HTML matters to the user**: they want cards/header in the image. Tell them this skill exports diagrams only, and recommend a browser-based full-page screenshot (or a separate PDF print).
- **A stalled font request**: the PNG is captured with fallback typography after 15 s and a warning; retry on a working network, or use `--system-fonts` to capture with installed faces at once.
- **Source is missing fonts at runtime**: Playwright will substitute, the screenshot will look off. Check that the source HTML has the `<link href="...fonts.googleapis.com...">` tag in `<head>`. If absent, the file isn't from a current template — fix the source rather than working around it in export.

## What this command never does

- Modifies the source HTML.
- Adds export buttons or `<script>` tags to generated diagrams (the "no JS in deliverables" rule in SKILL.md §12 still stands).
- Auto-emits `.svg` or `.png` alongside HTML generation. Manual on every call.
- Embeds an HTML wrapper (cards, headers) into the SVG via `foreignObject`. Too fragile across renderers.

After producing the outputs, report the file paths and sizes back to the user.
