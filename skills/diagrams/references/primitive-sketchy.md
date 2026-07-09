# Rough Hand Variant

Optional Rough.js-based conversion that turns every minimal example into a hand-drawn "editorial" register without changing layout. Use when the diagram accompanies an essay, sketch, workshop note, or planning doc rather than precision technical docs.

Copyable gallery examples live beside each type as `assets/example-<type>-hand.html`, with `assets/template-hand.html` as the starter template. They show rough boxes, rough arrows, solid lines, dashed lines, label masks, and crisp text using the same layouts as the minimal examples.

## Implementation

The `-hand` files are generated, not manually edited. Run:

```bash
cd skills/diagrams
npm install
npm run generate:hand
```

The generator is [`scripts/generate-hand-variants.cjs`](../scripts/generate-hand-variants.cjs). It follows the same design as `svg2roughjs`: parse the canonical SVG and emit Rough.js-generated SVG paths. We use Rough.js directly instead of runtime `svg2roughjs` so arrows and pointers are controlled by the skill:

- Source `marker-end` arrows become explicit rough arrowhead geometry.
- Filled nodes use inset, jittered `rough-fill-mask` paths plus single-pass rough strokes, so clean source borders, clean fill edges, or double-stroke overlays do not sit underneath the hand-drawn outline.
- Original text and label masks stay crisp and readable.
- Original dashed lines keep `stroke-dasharray` on the generated rough strokes.
- The output remains static HTML. No runtime JavaScript is required.

## Tuning

Tune these constants in `scripts/generate-hand-variants.cjs`:

| Constant | Effect |
|---|---|
| `ROUGHNESS` | Higher values make borders and connectors more irregular. |
| `BOWING` | Higher values make long lines bow more. |
| `FILL_INSET` | Pulls jittered fills inward so only rough strokes define visible borders. |
| `disableMultiStroke: true` | Keeps borders from reading as a clean base line with a rough duplicate over it. |
| `TYPES` | Controls which examples get a `-hand` variant. |
| `seedBase` passed to `convertFile` | Changes the deterministic rough geometry per file. |

## Critical rules

Rough shapes, NOT text. Hand-drawn text becomes illegible fast. The generated files keep text as normal SVG `<text>` nodes.

Keep arrow labels masked with an opaque paper rectangle even in hand examples. The line can wobble; the label should still read cleanly.

Do not use SVG displacement filters for this variant. Filters can make borders, markers, and filled shapes look broken because they distort the final rendering instead of producing real rough geometry.

## When to use
- Essay / blog post / newsletter where the diagram is the hero of a narrative page.
- "Working sketch" register — showing something is mid-thought, not final architecture.

## When not to use
- Technical documentation where geometric precision matters.
- Diagrams with dense labels or tight alignments (filter reads as noise).
- Dark variants unless tested carefully. Rough multi-strokes can read as visual noise on dark paper.
