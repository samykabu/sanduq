# Streamgraph

A **line chart** variant. The shared plot frame (`0 0 1000 500`, margins, legend rhythm), the plain-line rules and the other variants are in `type-line.md`; the slopegraph, ridgeline, streamgraph and bump chart share one binding contract, specified in full in `type-slopegraph.md`.

**Best for:** how a total and its composition breathe across many periods — build minutes by pipeline, traffic by service, error budget by subsystem. The symmetric baseline makes the envelope the hero: the stream's height at any period *is* the total, and each layer keeps its share inside it. No other line form gives both at once — a plain multi-series line loses the total, a 100%-stacked area loses it on purpose.

Not for: exact per-period values (the reader gets shape, not numbers — use a **bar chart** or print a table); two or three periods (that is the parent line chart, `type-line.md`, or a **slopegraph**, `type-slopegraph.md`); a single series (the parent chart's area fill already does this against a zero baseline); or ranking stories (a bump chart, `type-bump.md`, reads rank, a stream reads volume).

## Layout conventions

- **Period columns** evenly spaced across the plot, `x` 80 → 960 inside the `0 0 1000 500` viewBox — the parent chart's margins. The shipped example runs 12 weekly columns at 80px pitch. Budget: **3–24 periods, 2–6 layers**. Below 3 periods there is no flow to show; above 6 layers the ramp runs out of distinguishable tones.
- **Symmetric baseline at `y=230`**, the vertical middle of the 40 → 420 plot. Each period's stack is centred on it: envelope top and bottom always average back to the midline, so the silhouette is the total mirrored about a constant axis. The baseline is a *derived* line, not a drawn one — do not paint it.
- **One shared linear scale** for every layer at every period. The shipped example uses 1.25px per build-minute; state the scale or the bucket size in the source line so the reader can calibrate the envelope.
- **Boundaries are Catmull-Rom smoothed, control points at 1/6 chord, vertices on true values.** Smoothing bends only the *drawing between* periods; every on-curve vertex sits exactly where the stacked value puts it, which is what lets `scripts/verify-streamgraph.py` read the geometry back. Between-vertex overshoot near a sharp change is the honest cost of smoothing — never move a vertex to tame it.
- **Stack order is fixed for the whole figure, largest totals innermost** — the two biggest layers hug the midline, smaller ones ride the outer edges where the curvature is. Order never changes per period.
- **Layer boundaries get a 1px `paper` hairline** so adjacent tones separate where they run thin.
- **Period captions** in resolved mono 8px, centred under each column at `y=440`, tracked `0.08em`.
- **No y-axis ticks and no gridlines.** The form is about the shape of the envelope; per-layer totals are printed in the legend, and a tick grid would invite reading precise values off a curve that cannot deliver them.
- **Annotate at most one landmark period** — a short hairline above the envelope and a mono label, as the shipped example marks the week the focal layer becomes the largest. More than one and the shape stops being the hero.
- **Legend keys are 16×8 rects** (area fills, like the parent chart), one entry per layer **with its total** — `Unit · 789 min`. The legend is where the numbers live. House rhythm as everywhere: rule at `y=462`, `LEGEND` at `478`, keys at `488` with text at `496`.
- **4px grid** applies to the designed constants — columns, caption baselines, legend rows. Boundary `y` values are data-scaled and exempt.

## Colour

- **One accent layer — the editorially focal series — and an `ink` opacity ramp for the rest**, never the series palette. Layers are named in the legend, so hue would re-encode what the labels already say. The shipped ramp runs 0.78 → 0.30, **strongest tone on the largest layer**; adjacent tones in the stack need at least ~0.15 of separation or the hairline is doing all the work.
- Fills may run lighter than a line could: these are areas bounded by `paper` hairlines with no text on them, so the 3:1 stroke floor that binds the slopegraph ramp does not bind here. What does bind: every fill must still be `ink` at opacity (or `accent`), and no text ever sits on a layer.
- **Legend wording must be skin-neutral** — "strongest tone", never "darkest". The ramp inverts on dark paper.
- **Layer names must not contain digits.** The legend prints one number per entry (the total) and the checker refuses a label carrying two numeric tokens — `E2E` fails, `End-to-end` passes.

## Honest-data rule

**The envelope is a claim about the total, and the layers are a claim about its parts.** Both are enforced by `scripts/verify-streamgraph.py` against the values each layer declares.

- **Zero-sum baseline, stated.** Every period centres on one midline — baseline = −total/2, the classic silhouette. Say so in the source line. A baseline that drifts per period to minimise wiggle re-orders what the eye reads as growth; a baseline pinned to the bottom is a stacked area wearing a costume. Neither is this type.
- **One scale, every layer, every period.** A layer drawn at its own scale makes its share a lie while the envelope stays plausible.
- **Zero periods stay in the domain — the pinch IS data.** The shipped docs pipeline runs nothing in weeks five and six, so its band pinches to zero thickness and reopens. Never bridge, resample, or drop a zero to prettify the flow.
- **No layer dropped silently.** Every drawn layer appears in the legend with its total, and every legend entry has a drawn layer. A stream that quietly loses a small series overstates every share that remains.
- **State the bucket size** (weekly, daily, per release) in the source line. Resampling to a coarser bucket smooths the story; the reader deserves to know which story they got.
- **Totals are sums, not typed numbers.** The legend total must equal the sum of the layer's declared per-period values — one number, three statements (values, geometry, print), zero chances to disagree.

## Declaring the values

**Each layer's path declares its per-period values, and the drawn geometry must put every vertex where those values stack.** Same contract as the slopegraph (`type-slopegraph.md`): every meaningful visible string is bound to an attribute stating the same thing.

```svg
<!-- A layer: closed region, top boundary left-to-right, then bottom back.
     Absolute M/C/L/Z only; on-curve vertices at every period column. -->
<path data-layer="Docs" data-values="8,9,7,6,0,0,5,7,8,8,9,9"
      d="M 80 297.5 C … L 960 403.8 C … Z"
      fill="rgba(45,49,66,0.30)" stroke="#f5f5f5" stroke-width="1"/>

<!-- Period captions: data-index places the column, data-period binds the text -->
<text data-period="W05" data-index="4" x="400" y="440" fill="#4f5d75" font-size="8" font-family="'Geist Mono', monospace" letter-spacing="0.08em" text-anchor="middle">W05</text>

<!-- Legend entries: data-total binds the printed per-layer total -->
<text data-layer="Docs" data-total="76" x="808" y="496" fill="#4f5d75" font-size="8.5" font-family="'Geist', sans-serif">Docs · 76 min · paused</text>
```

What the checker holds against those bindings: every layer's on-curve vertices sit at the shared period columns; per-period thickness matches `data-values` on one shared scale; layers tile with no gap or overlap; the envelope stays centred on one midline; control points sit where Catmull-Rom at 1/6 chord puts them (so the curve between vertices is determined by the vertices, not free to editorialise); each legend entry names its own layer and no other, and its total matches both its printed text and the sum of the declared values; and each period caption sits on its own column reading exactly its `data-period`. Paths must use plain absolute `M`/`C`/`L`/`Z` — anything else is refused rather than half-parsed, and **no `transform`** may touch a layer path, a bound label, or an ancestor group, for the same reason as the slopegraph: the checker reads raw coordinates.

## Anti-patterns

- A wiggle-minimised baseline that reorders layers per period — the legend stops meaning anything.
- A bottom-pinned baseline presented as a streamgraph — that is a stacked area; the symmetric silhouette is the type.
- One hue per layer instead of the ink ramp plus a single accent.
- Y-axis ticks, or reading a precise value off a layer's thickness — totals live in the legend.
- Bridging or dropping zero periods, or resampling to a bucket the source line does not state.
- More than 6 layers (indistinguishable tones) or fewer than 3 periods (no flow to show).
- Text on a layer fill, or a layer name carrying digits.
- Moving a vertex off its true value to tame smoothing overshoot or open room for an annotation.
- A `transform` on a layer path, a bound label, an ancestor group, or in CSS.
- An unbound visible string: a period caption, a legend name or a legend total with no attribute stating the same thing. An entry printing one layer's name above another's `data-layer` satisfies every number in the figure and still hands the reader the wrong band.

## Examples

- `assets/example-streamgraph.html` — streamgraph, minimal light
- `assets/example-streamgraph-dark.html` — streamgraph, minimal dark
- `assets/example-streamgraph-full.html` — streamgraph, full editorial
