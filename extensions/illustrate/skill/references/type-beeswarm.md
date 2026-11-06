# Beeswarm

A **scatter plot** variant. The shared plot frame, gridlines, point pattern and the other variant are in `type-scatter.md`.

**Best for:** a full distribution where every unit deserves its own mark — one dot per item on a single shared value axis, dodged perpendicular so nothing overlaps. Use when the *shape* of the crowd and its outliers are the story a summary number would hide: the shipped example plots 138 per-request latency samples for one endpoint, and the point of the figure is that a healthy median and an ugly p99 are the same dataset.

Not for: two variables (that is the parent scatter, `type-scatter.md`); comparing distributions across many groups (facet, or reach for a ridgeline, `type-ridgeline.md`); more than ~300 items (the packing outgrows the band — bin into a histogram); or a handful of values (below 20 there is no distribution to swarm, and a table says it shorter).

## Layout conventions

- **One value axis, horizontal, at the parent's baseline** (`y=420` inside `0 0 1000 500`, plot margins left 80, right 40), with 4–6 bound ticks at equal intervals in resolved mono 8px and **vertical gridlines only** — the swarm axis has no scale to grid, and a horizontal rule through the band would invite reading the packing offsets as values.
- **Dot count: 20–300**, one dot per item, all at one radius (the shipped example uses `r=4`). Both ends of the budget are enforced by `scripts/verify-beeswarm.py`.
- **Greedy dodge around a midline** (`y=230` in the shipped example): each dot takes the first free slot alternating above/below at a fixed pitch of `2r+2`. The dodge is packing, not data — any collision-free arrangement is legitimate, and the algorithm is not part of the contract.
- **Labels: the focal dot plus the outliers a reader will look for, at most 6.** resolved mono 8px small-caps on a paper mask, one tier per label, alternating sides of the band, each tied to its dot by an unbound hairline leader and bound to it with `data-name`.
- **4px grid** applies to the designed constants — the axis rule, gridlines, tick baselines, legend rows. Dot positions are data-scaled on the value axis and packing-scaled on the swarm axis, and both are exempt; snapping them would move the data.

## Colour

- **One ink fill for every non-focal dot** (`ink` at 0.55 in the shipped example) plus a `muted` stroke for the mark's edge, and **at most one accent dot**. Density must read as swarm *thickness*, never as tone: opacity as a value encoding while also dodging says one thing twice in two different lies, so `verify-beeswarm.py` requires the non-focal fill to be literally identical across the swarm.
- **The accent marks the editorially focal item** — in the shipped example the single slowest request, the one the title is about — never a hue per group. Groups are a facet decision, not a palette decision.
- **The focal dot keeps the shared radius.** Its cues are the accent fill and stroke, its label, and the legend naming it in words; a bigger focal dot is a second encoding and breaks the packing.

## Honest-data rule

**The value axis is exact and shared; the swarm axis carries no meaning — and says so.** The legend or source line states that the vertical spread is packing, states the axis bounds, and counts anything omitted. `scripts/verify-beeswarm.py` gates the geometry half.

- **No dot is dropped, binned, or jittered off its true value.** One dot = one item at exactly its value on one linear scale derived from the set itself (Theil-Sen, leave-one-out, so one dishonest dot cannot drag the line it is measured against).
- **Overlap is resolved by the perpendicular dodge, never by moving a dot along the value axis.** Two items with one value share a position and dodge apart; crowding is data, and the honest rendering of a crowd is thickness.
- **No two dots overprint.** A dot painted over another turns density into darkness, which the eye reads as a value nobody declared.
- **Linear scale only in the shipped grammar.** A log axis needs its own declaration before the checker could hold it to anything, so it is refused rather than half-trusted; if the spread demands log, say so in the source line and expect the gate to disagree until the grammar grows the declaration.

## Declaring the values

**Every dot is bound to the value it encodes.** `data-value` on a `<circle>` is the beeswarm contract — deliberately not `data-series` (slopegraph), `data-ranks` (bump) or `data-size` (bubble), so no sibling checker claims a beeswarm file and this one claims none of theirs. Detection is element-scoped: `data-value` also appears on `<text>` axis ticks in the bubble contract, so only a `<circle>` binding it puts a file inside this gate. The paper underlay beneath each dot is scenery and carries nothing.

```svg
<!-- A dot: position on the shared value scale, x = 80 + 2·ms. The cy is
     packing only. -->
<circle data-value="90" cx="260" cy="250" r="4" fill="rgba(45,49,66,0.55)" stroke="#4f5d75" stroke-width="0.75"/>

<!-- The focal dot — named, accented, same radius as everyone -->
<circle data-value="431" data-name="req-4c1f" cx="942" cy="230" r="4" fill="rgba(235,108,54,0.55)" stroke="#eb6c36" stroke-width="1.2"/>

<!-- Its label, bound to the dot it names -->
<text data-name="req-4c1f" data-role="label" x="942" y="120" fill="#2d3142" font-size="8" font-family="'Geist Mono', monospace" text-anchor="middle" letter-spacing="0.06em">REQ-4C1F</text>

<!-- An axis tick, bound to the number it prints -->
<text data-tick="x" data-value="200" x="480" y="440" fill="#4f5d75" font-size="8" font-family="'Geist Mono', monospace" text-anchor="middle">200</text>
```

What each binding buys, and what it costs to omit:

| Binding | Without it |
|---|---|
| `data-value` on the circle | A dot nudged along the value axis could not be caught — the drawn position would be the only statement of the value. |
| `data-name` on the focal/outlier circles | An unnamed outlier cannot be labelled or cross-checked, and two swapped labels rename both dots silently. The name must be non-empty and unique to one dot: two dots sharing a name collapse into one entry, so a single label satisfies both. |
| `data-name` on a label | The label floats free — it could name a dot that is not there, or drift to a neighbour. |
| `data-tick` / `data-value` on a tick | The printed axis could be relabelled wholesale — every dot honestly placed on a scale the axis lies about. |

`scripts/verify-beeswarm.py` derives the value scale from the dots themselves, requires dots sharing a value to share a position, refuses any overprinted pair, holds every dot to one radius and every non-focal dot to one fill, caps the accent at one dot and the labels at six, requires every `data-name` to be non-empty and unique, and checks every bound label and tick against the mark it describes; `scripts/test-verify-beeswarm.py` proves each check in both polarities and pins the sibling scope treaty in both directions.

**Nothing may position a mark except its own attributes.** The checker reads raw `cx`/`cy`/`r` and `x`/`y`, so anything applied afterwards invalidates the check that passed. Every carrier is refused — the `transform` attribute, an inline `style="…"`, and a rule in a `<style>` block — on a dot, on a bound label or tick, or on an ancestor `<g>`/`<svg>`. So is every positioning property, not just `transform`: the Level 2 individual properties `translate`/`rotate`/`scale`, the SVG geometry properties `cx`/`cy`/`r`/`x`/`y` (CSS beats the presentation attribute), and CSS motion path. Bake the offset into the coordinates. `line-height`, `color` and font declarations are untouched — they do not move anything.

## Anti-patterns

- Moving a dot along the value axis to open up space — the type's one unforgivable error.
- Binning or averaging before plotting (that is a histogram wearing a costume), or quietly dropping the inconvenient outlier.
- Dot size as a second encoding (that is the **bubble variant**, `type-bubble.md`), or opacity as a value encoding while also dodging.
- Meaning smuggled into the swarm axis: sorting the dodge by a second variable, or a midline drawn as if it were a scale.
- A hue per group instead of one ink plus a single accent.
- Labelling more than the focal dot and a handful of outliers.
- Positioning a dot, a bound label, a tick or an ancestor group from CSS — `transform`, `translate`, `rotate`, `scale`, a geometry property (`cx`/`cy`/`r`/`x`/`y`) or a motion path — whether as an attribute, an inline `style`, or a rule in a `<style>` block.
- Two dots wearing the same `data-name`, or an empty one: a name that identifies two marks identifies neither.
- An unbound visible string: a label or an axis tick with no attribute stating the same thing.

## Examples

- `assets/example-beeswarm.html` — beeswarm, minimal light
- `assets/example-beeswarm-dark.html` — beeswarm, minimal dark
- `assets/example-beeswarm-full.html` — beeswarm, full editorial
