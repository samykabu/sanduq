# Arc diagram

**Best for:** Dependency spans between nodes ordered along a rail.

**Best for:** pairwise imports among a handful of packages when the *skip* is the story — nodes on one baseline, each edge a rising semicircle whose height is how many seats it jumps. Use it when a ranked dependency graph would bury a skip-layer import inside the hairball: the shipped example lines seven packages left to right, and Checkout still importing Auth is the tallest arc.

Not for: a node with many parents that need rank rows (that is the parent dependency graph); a tree (every node has one parent — use Tree); a cycle that has to be routed around the stack (the parent marks that with one dashed back-edge). An arc diagram has no ranks and no back-edge grammar.

## Layout conventions

- **One rail, left to right.** Nodes are `r=6` dots on a shared baseline at `y=400` inside `0 0 1000 500`, equally spaced (the shipped example uses a 140px pitch from `x=80`). Labels sit under the dots, `text-anchor="middle"`.
- **Node count: 4–9.** Below 4 there is no rail to skip along; above 9 split an overview from a cluster.
- **Rising semicircles only.** Each import is `M x1,y A r,r 0 0 1 x2,y` with `fill="none"`. Sweep 1 rises in SVG coordinates; sweep 0 would draw the import under the seats. `r` is half the endpoint distance, so height equals span × pitch / 2 — a neighbour cannot wear a skip's arc.
- **Span is the seat count.** `data-span` is `|i−j|` on the rail. A five-seat skip is five times a neighbour, not a decorative taller curve.
- **Paint back to front:** longer arcs first, neighbours next, the focal skip last so it is the stroke the eye hits.
- **4px grid** applies to the designed constants — baseline, label baseline, legend rows, node radius. Positions on the rail are pitch-scaled and exempt.

## Colour

- **One accent arc, and one muted treatment for everyone else.** The shipped example accents Checkout → Auth — the skip that will hurt a split — not the package with the most edges.
- **Stroke, not fill.** An arc is a line. Filling it turns a skip into a wedge.
- **The nodes stay ink.** Accent lives on the skip, matching the parent's rule that the cycle is the accent and the nodes it touches are not.

## Honest-data rule

**Arc height is the seat count, on one shared pitch.** `scripts/verify-arc-diagram.py` gates it.

- **One baseline, one pitch.** A node off the rail, or a seat that is a different width from its neighbours, makes two spans of the same count draw at two heights.
- **`data-span` equals `|i−j|`.** Declaring 2 for a five-seat skip, or drawing a neighbour at a skip's radius, is the type's unforgivable error.
- **Endpoints are the named nodes.** A path that names Auth and Checkout but lands on Catalog is a different import.
- **Direction reads off the rail.** Every muted arc runs left to right: its left seat imports its right one, so order the rail by import direction and say so in the caption. The one import against the rail is the accent arc, with a small accent arrowhead on the package it imports. Arrowheads on every arc would pile up at shared seats, where each arc lands vertically.

## Declaring the values

**Every arc is bound to the two nodes it joins and the span it encodes.** `data-span` on a `<path>` is the arc-diagram contract — deliberately not `data-value` on a `<circle>` (beeswarm), `data-size` (bubble), `data-series` (slopegraph) or `data-ranks` (bump), so no sibling checker claims an arc-diagram file and this one claims none of theirs.

```svg
<!-- Seat rail at y=400, pitch 140. Auth is seat 1, Checkout is seat 6. -->
<circle data-name="Auth" cx="220" cy="400" r="6"/>
<circle data-name="Checkout" cx="920" cy="400" r="6"/>
<path data-from="Checkout" data-to="Auth" data-span="5"
      d="M 220,400 A 350,350 0 0 1 920,400"
      fill="none" stroke="{accent}" stroke-width="1.6"/>
```

What each binding buys, and what it costs to omit:

| Binding | Without it |
|---|---|
| `data-span` on the path | A decorative tall arc on a neighbour could not be caught — the drawn radius would be the only statement of the skip. |
| `data-from` / `data-to` | A path that names two packages but lands on two others still looks like their import. |
| `data-name` on the node circle and its label | Two labels exchanged along the rail rename both packages, with every span still correct in isolation. |

`scripts/verify-arc-diagram.py` derives the pitch from the nodes, requires a rising semicircle whose radius matches both the endpoint distance and `pitch · span / 2`, refuses a second accent arc or a muted arc that imports leftward, and checks every bound label against the node it names; `scripts/test-verify-arc-diagram.py` proves each check in both polarities and pins the sibling scope treaty in both directions.

**Nothing may position a mark except its own attributes.** The checker reads raw `cx`/`d`/`x`, so anything applied afterwards invalidates the check that passed. Every carrier is refused — the `transform` attribute, an inline `style="…"`, and a rule in a `<style>` block — on a node, on an arc, on a bound label, or on an ancestor `<g>`/`<svg>`. Bake the offset into the coordinates.

**Nothing may paint or hide a mark except its own attributes.** A `<style>` rule outranks every presentation attribute, so the checker refuses one that sets `stroke` or `fill`, and one that hides or resets (display, visibility, zero opacity, zero stroke width or `all`) the diagram's `<svg>`, anything inside it, or an element around it. A rule for page-only chrome, such as `.footer{display:none}` or a logo, is fine. The accent arc is read as the shipped orange or the active `--color-accent` set by a rule that reaches the diagram. Give each import its own literal `stroke`.

## Anti-patterns

- Drawing a neighbour at a skip's height — the type's one unforgivable error.
- A ranked layout, a cycle routed around the stack, or fan-in badges (those are the parent).
- Filling an arc, or using sweep 0 so the import hangs under the seats.
- Uneven spacing so that height no longer equals span.
- A hue per edge instead of one muted treatment plus a single accent.
- Positioning a mark, a bound label or an ancestor group from CSS.

## Examples
- `assets/example-arc-diagram.html` — minimal light
- `assets/example-arc-diagram-dark.html` — minimal dark
- `assets/example-arc-diagram-full.html` — full editorial
- `assets/example-arc-diagram-hand.html` — hand-drawn from the verified light source
