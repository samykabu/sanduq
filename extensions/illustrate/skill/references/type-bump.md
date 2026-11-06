# Bump chart

A **line chart** variant. The shared plot frame (`0 0 1000 500`, margins, legend rhythm), the plain-line rules and the other variants are in `type-line.md`; the slopegraph, ridgeline, streamgraph and bump chart share one binding contract, specified in full in `type-slopegraph.md`.

**Best for:** rank movement across **3–6 ordered snapshots** when position, not magnitude, is the story — package popularity by quarter, team standings by sprint, top queries by month. The slopegraph (`type-slopegraph.md`) shows two moments and keeps magnitude; a bump chart trades magnitude away entirely to show *several* moments of pure position. That trade is the type: the vertical axis is rank, every row is one rank apart, and a flat line means "nothing displaced it", not "nothing changed".

Not for: exactly two snapshots (that is the **slopegraph**, `type-slopegraph.md`); magnitude stories — a series whose downloads doubled while its rank held draws a flat line, and if that surprise matters the reader needed a **line chart**, `type-line.md`; fewer than 4 series (a sentence is shorter) or more than 8 (spaghetti with a legend).

## Layout conventions

- **One vertical axis rule per snapshot**, evenly pitched inside the plot, with the label gutters of the slopegraph: names right-aligned ending at `x=272` and first ranks at `x=304` on the left, mirrored from `x=696` (ranks) and `x=728` (names) on the right. The shipped example runs four axes at `x` 320/440/560/680 — the same 360px run as the slopegraph, spent in three segments instead of one.
- **Rank rows on a fixed pitch.** The shipped grid is `y = 88 + 56 × (rank − 1)`. Rank is ordinal, so — unlike the slopegraph, whose endpoint `y` values are data-scaled and grid-exempt — **every vertex lands exactly on the 4px grid**, and `scripts/verify-bump.py` enforces the row placement with no tolerance at all. There is no honest reason for a vertex to sit off its row.
- **Straight segments between adjacent snapshots, dots at every vertex** (`r=3`, focal `r=4`). Never splines: a curve between two quarterly snapshots draws a trajectory nobody measured. The draft this variant came from calls them subway curves and bans them outright.
- **Labels at first and last appearance** — name and rank (`#1`…`#6`, the sigil keeps a rank from reading as a magnitude) at both ends, each on its own series' row **and in the gutter outboard of the end it names**. Both coordinates are required and both are checked: the row says which series a label belongs to, the column says which *end* of it, and neither implies the other. A first-end label slid along its row into the plot prints every rank correctly and reads against the wrong snapshot.
- **Snapshot captions** in resolved mono 9px, centred under each axis, bound with `data-axis` / `data-state` exactly as the slopegraph binds its two.
- **Series count 4–8, snapshots 3–6.** Two snapshots are a slopegraph; past six the columns compress until rank changes cannot be followed.
- **No gridlines.** The dots are the readable positions and the axis rules are the columns.

## Colour

Everything the slopegraph's colour section (`type-slopegraph.md` § Colour) says holds here unchanged: one accent on the editorially focal series, an `ink` opacity ramp (`0.80 → 0.62`, floor 0.53) for the rest — ordered by first-snapshot rank, so the legend can say "strongest tone was highest-ranked", skin-neutrally — focus carried by stroke weight (2.4px against 1.2px) and dot size rather than tone, and labels in `ink`/`muted` on every series including the focal one. The accent marks the series the story is about, never the winner: the shipped example spends it on the package that *fell*.

## Honest-data rule

**State the ranking key and the tie-break in the source line.** Rank hides magnitude by design, so the footnote is where a reader learns what "first" means and why no two series ever share a row. `scripts/verify-bump.py` gates the geometry half: every snapshot's ranks must be a permutation of 1..N — a duplicated rank is a tie the stated tie-break cannot produce, and a skipped rank is an empty row the reader fills with a series that is not there.

- **If the ranking measure changed definition between snapshots, the chart is invalid** — ranks under different measures are not comparable, and no drawing convention repairs that.
- **A series that enters late or leaves early starts or stops.** A real gap is drawn as absence, never interpolated across. The shipped grammar has no way to *declare* a gap yet, so `verify-bump.py` requires every series to visit every snapshot — a series with fewer vertices than columns is a finding until a gap declaration exists, because widening the rule without one would let a truncated series pass as a deliberate exit.
- **Never smooth a tie into a crossing.** The tie-break decides the order; drawing anything else invents a rank.
- **Never nudge a vertex off its row** to dodge a label collision — it reads as a rank between two ranks, and the checker treats it as the lie it is.

## Declaring the values

The binding contract is the slopegraph's (`type-slopegraph.md` § Declaring the values), one level up: the path declares its ranks, and every visible string is bound to what it describes.

```svg
<path data-series="legacy-http" data-ranks="1,2,4,6" d="M320,88 L440,144 L560,256 L680,368" fill="none" stroke="#eb6c36" stroke-width="2.4"/>
<text data-series="legacy-http" data-end="first" data-role="name" x="272" y="91.5" fill="#2d3142" font-size="11" font-weight="600" font-family="'Geist', sans-serif" text-anchor="end">legacy-http</text>
<text data-series="legacy-http" data-end="first" data-role="rank" x="304" y="91.5" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace" text-anchor="end">#1</text>
<text data-axis="0" data-state="Q1" x="320" y="416" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace" letter-spacing="0.14em" text-anchor="middle">Q1</text>
```

`data-ranks` is the basis of every geometric check, so a series whose labels go missing stays in the verified set and the missing label is itself reported. `scripts/verify-bump.py` covers the grid, the permutations, the segments, the dots, the focus pairing, the label bindings, label placement on both axes and the captions; `scripts/test-verify-bump.py` proves each check in both polarities. The gutter x is read off the figure — every label sharing an end and a role must agree on one column — so a resized plot needs no constant changed here.

## Examples

- `assets/example-bump.html` — bump chart, minimal light
- `assets/example-bump-dark.html` — bump chart, minimal dark
- `assets/example-bump-full.html` — bump chart, full editorial
