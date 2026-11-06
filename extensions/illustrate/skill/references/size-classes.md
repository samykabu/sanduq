# Size classes: canvas, type ramp and safe areas

The second half of [output-spec.md](output-spec.md) §2 Size: the preset table stays there; this file holds what a
preset changes. Read it when the size is not the default `doc-inline`, when the diagram must hold on a narrow
screen, or when deriving `fit`.

## Holding the canvas on a narrow screen

The SVG keeps its readable width on a phone instead of shrinking into it, so
`min-width` is **the viewBox width of the preset in use** — not a fixed number.
Pin it lower and the whole drawing scales down and takes the type ramp with it:
a 12px node name on a `doc-wide` 1280 viewBox pinned at 900 draws at 8.4px,
under every floor this spec sets, and nothing on screen says so.

A canvas that wide has to scroll somewhere. Put it in a wrapper that scrolls on
its own, or the document scrolls sideways and the right-hand nodes are gone
unless the reader thinks to look for them:

```html
<div class="diagram-container">
  <svg viewBox="0 0 960 600" …> … </svg>
</div>
```

```css
.diagram-container { width: 100%; overflow-x: auto; }
svg { width: 100%; min-width: 960px; display: block; }
```

Two shapes need extra care. A centred grid or flex item sizes itself to the
SVG's max-content width, so the wrapper's `width: 100%` resolves against the
wide item and never scrolls — give that item `max-width: 100%; min-width: 0`.
And when an ancestor is `overflow: hidden` (window chrome, a clipped card), the
SVG is cut off instead of scrolled: no scrollbar, no page overflow, and a
page-overflow check reports the file clean because the content was destroyed
rather than spilled. The wrapper has to sit **inside** that ancestor.

Paper has no scrollbar, so on a sheet the same wrapper clips instead of
scrolls. Release both in print and let the drawing scale to fit — smaller but
whole beats sharp but cut off. The rule has to come **after** the `svg` rule,
because a media query adds no specificity and a later plain rule would win:

```css
@media print {
  .diagram-container { overflow-x: visible; }
  svg { min-width: 0; }
}
```

## Deriving `fit`

Round the content bounding box **up** to the next multiple of 4, then add the fixed chrome: 40px outer margin on every side, plus 60px at the bottom for the legend strip. Never let the content touch the viewBox edge.

## Type ramp per size class

Node names shrink relative to the canvas as it grows — resist that. Scale the ramp with the preset so a projected slide stays readable from the back row.

| Role | standard | presentation | print |
|---|---|---|---|
| Title (resolved serif) | 28 | 40 | 32 |
| Node name (resolved sans 600) | 12 | 16 | 12 |
| Sublabel (resolved mono) | 9 | 12 | 9 |
| Arrow label (resolved mono) | 8 | 12 | 8 |
| Eyebrow / tag (resolved mono) | 8 | 8 | 8 |
| Node box min height | 48 | 64 | 48 |
| Min gap between nodes | 24 | 40 | 24 |

Every `font-size` is one of the role values above for the preset in use, or one of these named exceptions:

| Exception | Font | Sizes |
|---|---|---|
| Dense annotation: legend keys, axis ticks, chart data labels, source lines, in-box tags | resolved mono or resolved sans regular | 7 to 11, half steps allowed |
| Chart series or row name: bar category, line or bump series, gantt row, matrix header | resolved sans 600 | 10 to 11 |
| Group or entity heading | resolved sans 600 | 14 |
| Decorative watermark numerals at or under 0.08 opacity | any | any |

An exception is bound to the font beside it, weight included: the resolved sans at 600 or heavier is the node-name voice, lighter sans is annotation. So a sans 600 node name cannot borrow the dense-annotation range down to 7, and a mono tick cannot borrow the 14 reserved for headings. A chart row carries a name in the same sans 600 voice at a rank the ramp has no row for, which is why it has an exception of its own rather than a licence to shrink: `type-bar.md`, `type-gantt.md` and `type-line.md` all set that name at 10 or 11.

Anything else is a bug in the diagram, not a new size. The editorial callout (resolved serif italic, 14px) and the 1.75rem HTML page title outside the SVG are part of the style-guide typography table, not exceptions.

## Shipped examples that predate the ramp

Some committed `assets/example-*.html` files were drawn under the older all-sizes-on-the-4px-grid rule and may carry sizes outside this ramp (for example 5 to 6px chip text, 13px cell names). They are not precedent: new diagrams follow the ramp. Bringing a shipped example onto the ramp is a visual change and belongs in its own PR.

Presentation ramp implies fewer nodes — 16px names in 64px boxes eat the canvas. If a `slide-16x9` layout won't fit, that's the size dial telling you the detail dial is set too high; drop a level rather than shrinking the type.

## Safe areas

- **All presets:** 40px outer margin; legend strip is the bottom 60px and nothing else lives there.
- **`social-og`:** keep the outer 64px clear on every side — link-card crops are unpredictable across platforms.
- **`slide-*`:** keep the bottom 80px clear if the deck template has a footer bar; ask if unsure.
