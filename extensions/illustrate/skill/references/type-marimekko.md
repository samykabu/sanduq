# Marimekko

A **treemap** variant. The parent's plot frame, squarified layout, fill ramp, label tiers, contrast ceiling and legend rules are in `type-treemap.md`.

**Best for:** a **two-way part-of-whole** where both splits matter and the reader's question is "which cell of the cross-tab dominates?" — CI minutes by pipeline × runner OS, bundle bytes by package × chunk, spend by team × vendor, incidents by service × severity. The treemap (`type-treemap.md`) answers one question (what dominates the whole); a marimekko answers three at once: read across for the category mix, down for the series mix within a category, and by area for the joint share. A stacked bar with equal-width bars shows the within-category mix and throws the category sizes away; a treemap shows the joint sizes and throws the grid away.

Not for: a one-way split (that is the parent treemap, `type-treemap.md`, and a marimekko with one series is a bar chart); more than ~5 series or ~8 categories, past which the small cells become unlabelable slivers in *both* directions; series measured in different units, which cannot share one column; or a comparison of the series' totals across categories, which the height encoding deliberately hides — if that is the reading, the data wants a grouped bar.

## Layout conventions

- **Plot area:** the treemap's — `x` 40 → 956, `y` 40 → 420 inside a `0 0 1000 500` viewBox, legend block at `y=462`/`478`/`488`. Column captions sit under the plot at `y=438`, resolved mono 9px, centred on their column. The shipped example spends 900px of column width across five columns with four 4px gutters.
- **Column width is category share** of the whole, over the sum of column widths. Column edges snap to the 4px grid, so the gutters do; keep the gutter constant — a widened gap reads as a narrower column.
- **Every column is the full plot height**, and its segments tile it top to bottom with no gaps and no gutters, separated by the hairline stroke alone. **Segment height is the series' share within its column**, so the same height means the same within-category share whatever the column's width. Segment boundaries are data and land on whole pixels, exempt from the 4px grid as the waterfall's bar tops are.
- **One series order, top to bottom, in every column** — the order of the series' overall totals, largest at the top. A series absent from a category is omitted from that column, never drawn at zero height; the rows do not align across columns and are not meant to, which is why every segment prints its own share.
- **Column and series budgets:** 3–8 columns, 2–5 series. Widths under ~24px cannot hold a label in either direction and take the treemap's information mark instead.
- **Labels sit inside the segment**, top-left, 16px in, in the treemap's tiers by height (`type-treemap.md` § Layout conventions): 56px and above takes the name in resolved sans 12px 600 with the amount and within-column share in resolved mono 9px on the next line (`2,140 min · 68%`); 32–55px takes the same pair at 11px/9px on a tighter pitch; below that, the mark or nothing. The focal segment may add what its share is *of* (`83% of mobile`) because that is the one number a reader is most likely to misread as a share of the whole. Never shrink or widen a segment to fit a label.
- **Column captions** print the column's name and its share of the whole (`web · 31%`), so the width can be read as a number without a ruler.
- **Hold the 760px canvas on narrow screens.** The SVG keeps `min-width: 760px` so its 9px labels stay readable, and sits inside a local `overflow-x: auto` wrapper (`.diagram-container`) so a phone scrolls the chart, not the page. Check it at 390px wide before shipping: no page-level overflow, no shrunken canvas, and the local scroller present (Illustrate does not ship upstream's render lint).

## Colour

The treemap's fill, stroke, contrast and legend rules (`type-treemap.md` § Layout conventions) hold here with one change: the ramp runs **per series, not per cell**. Every segment of one series takes one `ink` opacity — strongest on the series with the largest overall total (`0.16 → 0.10 → 0.05` on light paper, `0.14 → 0.09 → 0.04` on dark) — so a row reads as one thing across the figure and the legend needs one key per series, not a direction word. One accent segment, marked by its `accent` stroke at 1.5px and the accent tint, on the editorially focal cell. Labels stay `ink` (names) and `muted` (amounts) everywhere, and the top of the ramp stays at the treemap's contrast ceiling for the same reason.

## Honest-data rule

**Width, height and area are three statements of one table, and every one of them is checked.** A column widened to fit its label lies about the category; a segment padded for headroom lies about the series; either lies about the joint share, which is the reading the type exists to give. `scripts/verify-marimekko.py` recomputes all three from the amount every segment declares, as relative error, so the narrow column and the thin segment are held to the same standard as the giants.

- **Never drop a category or a series to tidy the grid.** A marimekko claims to show a whole; a missing column makes every other width a lie, and a missing segment makes every other height in its column one. Merge the tail into a named "Other" column or series instead.
- **A series absent from a category is omitted, not drawn at zero.** A zero-height rect is a cell that claims to exist; an omitted one is a gap the legend can explain.
- **Say what the amounts are** in the source line — the unit, the period, the total — and say when they are illustrative. The checker verifies internal consistency only; a figure wrong by the same factor everywhere is self-consistent.

## Declaring the values

Every segment is one `<rect>` (over its paper mask, as in the parent) carrying the category, the series and the amount. Every visible string is bound to what it describes.

```svg
<rect x="580" y="106" width="216" height="314" rx="2" data-column="mobile" data-segment="macOS" data-amount="1980" fill="rgba(235,108,54,0.16)" stroke="#eb6c36" stroke-width="1.5"/>
<text data-column="mobile" data-segment="macOS" data-role="label" x="596" y="152" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace">1,980 min · 83% of mobile</text>
<text data-column="mobile" data-role="caption" x="688" y="438" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace" text-anchor="middle">mobile · 24%</text>
<text data-segment="macOS" data-role="key" x="344" y="497" fill="#4f5d75" font-size="8.5" font-family="'Geist', sans-serif">macOS</text>
```

`data-amount` is the basis of every geometric check, and `data-segment` on a `<rect>` is this contract's scope key: the parent binds `data-share` on a `<rect>` and reads only files named for it, slopegraph binds `data-series` on a `<line>`, bump `data-ranks` and ridgeline `data-bins` on a `<path>`, bubble `data-size` and beeswarm `data-value` on a `<circle>`. No two gates read one attribute, so no two gates claim one file. A label prints the segment's amount and its within-column share and nothing else numeric; a caption prints its column's name and share of the whole; a key names its series. `scripts/verify-marimekko.py` covers the shared plot, the constant gutter, the width, height and area shares, the tiling, the series order, the accent count, every binding and the marker fit; the extension's `tests/test_verify_marimekko.py` proves each check in both polarities and pins the scope treaty with the parent and the sibling gates. The accent count accepts the upstream default accent literals and the active theme's light and dark `accent` (resolved by `scripts/theme_tokens.py` through `scripts/illustration_theme.py`), so it holds on themed output too.

**No `transform` on any of it**, by any carrier — the `transform` attribute, an inline `style`, or a `<style>` rule — on a segment, a bound label, or an ancestor `<g>`. The checker reads raw coordinates, and a transform moves the rendered mark away from the number that was verified.

## Anti-patterns

- Equal-width columns — that is a 100% stacked bar, and the category sizes are gone.
- Columns of different heights, or a gutter between segments — height stops being a share of anything.
- A series in a different order in one column, or one drawn at zero height where it is absent.
- One hue per series instead of the ink ramp plus a single accent; a legend that names the ramp by tone instead of by series.
- A column widened, or a segment padded, to fit its label.
- A category or series silently dropped from the grid.
- More than 5 series or 8 categories without an "Other".
- A stated total the segments contradict by more than display rounding.

## Examples

- `assets/example-marimekko.html` — marimekko, minimal light
- `assets/example-marimekko-dark.html` — marimekko, minimal dark
- `assets/example-marimekko-full.html` — marimekko, full editorial
- `assets/example-marimekko-hand.html` — marimekko, hand-drawn variant, generated (never hand-edited)

Run `python scripts/verify-marimekko.py --all` (or pass explicit HTML paths) from the skill directory; the extension's regression suite is `python -m unittest tests/test_verify_marimekko.py` from the extension root. The default targets skip generated `-hand` variants: the sketch filter rewrites geometry the gates read as raw coordinates.
