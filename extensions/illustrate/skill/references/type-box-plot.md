# Box plot

**Best for:** Five-number summaries, whiskers, and outliers across groups.

**Best for:** comparing the *shape* of a few distributions when the five-number summary is the story — one box per group on a single shared value axis. Use it when a median would hide the spread, and when drawing every unit (the beeswarm) would hide the comparison: the shipped example plots per-request latency for five services, and the point of the figure is that Checkout's median still looks survivable while its box already runs 80–200 ms.

Not for: two continuous variables (that is the parent scatter); one distribution of individuals (that is the **beeswarm variant**); the silhouette of many distributions (that is the **ridgeline** on Line); a single number per category (that is a bar).

## Layout conventions

- **Orientation:** horizontal only. Rows stack downward and the value axis runs left → right; a vertical box plot forces rotated category labels, which this variant does not.
- **Same plot frame as the parent:** value axis at `y=420` inside `0 0 1000 500`. Category labels take a 160px left margin (right-aligned at `x=148`, `node-name` role 11px 600), so the scale starts at `x=160`. The shipped example uses `x = 160 + 2·ms` on a 0–400 domain.
- **Series count: 3–8.** Below 3 a table says it shorter; above 8 split an overview from per-series detail.
- **One box per series**, height 32px, centred on the row. Paper underlay immediately beneath so gridlines do not show through the translucent fill.
- **Tukey fences, not the theoretical fence:** whiskers run to the last inlier (`data-wlo` / `data-whi`) inside `q1 - 1.5·IQR` and `q3 + 1.5·IQR`, with 16px caps. Outliers are `r=4` dots strictly outside those whiskers and fences, bound with `data-x` on the circle — never `data-value`, which is the beeswarm contract.
- **Median** is a vertical `ink` line through the box at `data-q2`, 1.5px. It is the only mark that may sit on the `ink` token at full strength; the box fill stays a tint.
- **Labels:** the category name at the left of its row, bound with `data-name`. Value-axis ticks are bound with `data-tick="x"` and `data-value`. The category axis has no scale to tick.
- **4px grid** applies to the designed constants — axis rule, gridlines, tick baselines, legend rows, box height, row centres. Positions on the value axis are data-scaled and exempt.

## Colour

- **One accent series, and one muted treatment for everyone else.** The shipped example accents Checkout — the IQR that will page — not the series with the most outliers.
- **Fill weight, not hue, carries the pairing.** Non-focal boxes use `muted @ 0.15` fill + `muted` stroke; the focal box uses `accent @ 0.12` fill + `accent` stroke. Outliers inherit their series' stroke. The median stays `ink` on every row so it does not compete with the focal fill.
- **The value axis is exact and shared.** Crowded boxes mean the summaries really are close; never nudge a box along the value axis to open up space.

## Honest-data rule

**The five-number summary is ordered, and every mark sits on one linear scale.** `scripts/verify-box-plot.py` gates it.

- **`wlo ≤ q1 ≤ q2 ≤ q3 ≤ whi`.** A median outside its box, or a whisker that grows inward, is not a five-number summary.
- **Box left is q1, box right is q3, median is q2, whiskers are wlo/whi.** Width encodes the IQR — never pad a box to fit a label.
- **Outliers sit strictly outside the whiskers and the Tukey fences.** Drawing an inlier as a dot, or parking an outlier on the fence, hides the tail.
- **Linear scale only, from a stated floor.** The shipped example includes zero. A truncated axis inflates every box the same way a truncated bar does.
- **Round once, then draw from the rounded number**, so the declared value and the drawn geometry are two statements of one number.

## Declaring the values

**Every series is bound to the five numbers it encodes.** `data-q1` on a `<g>` is the box-plot contract — deliberately not `data-value` on a `<circle>` (beeswarm), `data-size` (bubble), `data-series` (slopegraph) or `data-ranks` (bump), so no sibling checker claims a box-plot file and this one claims none of theirs.

```svg
<!-- One series. x = 160 + 2·ms. Category y is a label rail. -->
<g data-name="Checkout" data-q1="80" data-q2="120" data-q3="200"
   data-wlo="40" data-whi="280">
  <line data-role="whisker-lo" x1="240" y1="216" x2="320" y2="216"/>
  <line data-role="whisker-hi" x1="560" y1="216" x2="720" y2="216"/>
  <rect data-role="box" x="320" y="200" width="240" height="32" rx="2"
        fill="{accent @ 0.12}" stroke="{accent}" stroke-width="1.2"/>
  <line data-role="median" x1="400" y1="200" x2="400" y2="232"/>
  <circle data-outlier="Checkout" data-x="388" cx="936" cy="216" r="4"/>
</g>
<text data-tick="x" data-value="200" x="560" y="440">200</text>
```

What each binding buys, and what it costs to omit:

| Binding | Without it |
|---|---|
| `data-q1` / `data-q2` / `data-q3` / `data-wlo` / `data-whi` on the group | A nudged box could not be caught — the drawn geometry would be the only statement of the summary. |
| `data-role="box"` / `"median"` / `"whisker-lo"` / `"whisker-hi"` | The checker could not tell a gridline from a whisker, or a paper underlay from the IQR. |
| `data-x` on an outlier circle | `data-value` on a circle is the beeswarm contract; using it here would put every box-plot file inside `verify-beeswarm.py`. |
| `data-name` on the group and its category label | Two labels exchanged between rows rename both series, with every number still correct in isolation. |
| `data-tick` / `data-value` on a tick | The printed axis could be relabelled wholesale — every box honestly placed on a scale the axis lies about. |

`scripts/verify-box-plot.py` derives the value scale from the summaries themselves, requires the five-number order, holds every box, median, whisker and outlier to that scale, refuses an outlier inside the whiskers, caps the accent at one series (read through `var()`, `hsl()` and class, id or attribute selectors), refuses a bound mark hidden by `display`, `visibility` or `opacity` and a bound mark whose own paint draws it nothing (`none`, or a zero `stroke-width`, `stroke-opacity` or `fill-opacity`), and checks every bound tick against the mark it describes; `scripts/test-verify-box-plot.py` proves each check in both polarities and pins the sibling scope treaty in both directions.

**Nothing may position a mark except its own attributes.** The checker reads raw `x`/`width`/`x1`/`cx` and `y`/`cy`, so anything applied afterwards invalidates the check that passed. Every carrier is refused — the `transform` attribute, an inline `style="…"`, and a rule in a `<style>` block — on a series group, on a box, on a bound label or tick, or on an ancestor `<g>`/`<svg>`. Bake the offset into the coordinates.

## Anti-patterns

- Moving a box along the value axis to open up space — the type's one unforgivable error.
- A median outside its box, or whiskers that grow inward.
- Parking an outlier on the fence, or drawing an inlier as a dot.
- A hue per series instead of one muted treatment plus a single accent.
- `data-value` on an outlier circle (that is the beeswarm contract).
- Positioning a mark, a bound label, a tick or an ancestor group from CSS.
- Two series wearing the same `data-name`, or an empty one.
- An unbound visible string: a category label or an axis tick with no attribute stating the same thing.

## Examples
- `assets/example-box-plot.html` — minimal light
- `assets/example-box-plot-dark.html` — minimal dark
- `assets/example-box-plot-full.html` — full editorial
- `assets/example-box-plot-hand.html` — hand-drawn from the verified light source
