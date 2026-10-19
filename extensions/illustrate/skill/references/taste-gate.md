# Taste gate

Read once per diagram, at the end, before you deliver it. Routed from SKILL.md §9 (the gate) and §4
(the anti-patterns); §1 philosophy also lives here.

First run the mechanical half, from the skill directory:

```bash
python scripts/self_check.py --strict <file>
```

Default `self_check.py` covers the accessible-SVG contract, single-file safety, motion basics and
straight arrow ends (connector rule 7). `--strict` adds: accent on at most two node-sized shapes,
the legend strip below every node and inside the `viewBox`, the svg `min-width` equal to the viewBox
width, no `writing-mode`, no `box-shadow`, `rx` at most 10, node and zone rects on the 4px grid, the
font role of every element carrying a role class (`node-name`, `sublabel`, `arrow-label`, `eyebrow`,
`callout`), no pure black, and orthogonal connectors (rule 1, `verify-geometry.py --orthogonal`).
Documented exceptions: full pills, `.5` stroke offsets, data-bound rects carrying `data-*` values,
bridge hops up to 24px, and the terminal variant's mono type. Fix every finding, then answer the
boxes below; they are the judgement the scripts cannot make.

## Philosophy (§1)

**The highest-quality move is usually deletion.** From `.impeccable.md`: *"Confident restraint. Earn
every element. One color accent, two families, a small spacing vocabulary. If removing it wouldn't
hurt the page, remove it."*

- Every node represents a distinct idea. Two nodes that always travel together are one node.
- Every connection carries information. If the relationship is obvious from layout, remove the line.
- The active accent is **editorial, not a flag.** Use it on 1–2 focal nodes per diagram. Using it on 5 nodes erases the signal.
- The schematic isn't done when everything is added. It's done when nothing can be removed.

**Target density: 4/10.** Enough to be technically complete. Not so dense it needs a guide. Above 9
nodes, it's probably two diagrams.

## Universal anti-patterns (§4)

These mark "AI slop" schematics of any type:

| Anti-pattern | Why it fails |
|---|---|
| Dark mode + cyan/purple glow | Looks "technical" without design decisions |
| JetBrains Mono as blanket "dev" font in editorial output | Mono is for *technical* content in the editorial family. The technical-color family intentionally uses JetBrains Mono throughout. |
| Identical boxes for every node | Erases hierarchy |
| Legend floating inside the diagram area | Collides with nodes |
| Arrow labels with no masking rect | Bleeds through the line |
| Vertical `writing-mode` text on arrows | Unreadable |
| 3 equal-width summary cards as default | Generic grid — vary widths |
| Shadow on any element | Shadows are out. Borders are in. |
| `rounded-2xl` on boxes | Max radius 6–10px or none |
| Coral on every "important" node | Coral is 1–2 editorial accents, not a signaling system |
| Any breach of the seven SKILL.md §6 connector rules | Automatic fail: diagonal slants, labels touching their stroke, masks clipped by a later node, overlapping paths, shared attach points, transit behind a non-endpoint box, arrowheads on a bend |

Type-specific anti-patterns live in each `references/type-*.md`.

## Checklist (§9)

**Type fit:**

- [ ] If behavior matters, did I choose one semantic pattern before the visual type and load `semantic-patterns.md`?
- [ ] Right type for what I'm showing? ([type-index.md](type-index.md))
- [ ] Stated family, type, pattern, size preset, and planned cuts before drawing — confirmed, or assumptions noted?
- [ ] Would a table / paragraph do the same job? (If yes — don't draw.)
- [ ] Loaded the matching `references/type-*.md`?

**Remove test:**

- [ ] Can I remove any node? (Would a reader still understand?)
- [ ] Can I merge any two nodes? (Do they always travel together?)
- [ ] Can I remove any arrow? (Is the relationship obvious from layout?)
- [ ] Can I remove any label? (Does color or shape already signal it?)

**Signal:**

- [ ] Do the one or two accented elements actually deserve focal status?
- [ ] Legend covers every type used — and nothing extra?
- [ ] Within the type's complexity budget ([layout-budget.md](layout-budget.md))?

**Technical:**

- [ ] `python scripts/self_check.py --strict <file>` passes, and the type's `scripts/verify-<type>.py` when one exists?
- [ ] `python scripts/verify-geometry.py <file>` passes (rule 6, no label mask under a later node)?
- [ ] Arrows drawn before boxes?
- [ ] **Rule 2:** a visible 6 to 10px gap between every label mask and its connector, and an opaque resolved-`paper` mask behind every arrow label?
- [ ] **Rule 3:** no overlapping or stacked connectors; bridge/hop at crossings?
- [ ] **Rule 4:** a distinct attach point per connector on a shared edge, 12px or more apart, none hiding another?
- [ ] **Rule 5:** no transit behind a non-endpoint box, except the unavoidable case (dashed, label at the visible end)?
- [ ] The svg sits in a local `overflow-x: auto` wrapper; gaps, padding and type sizes follow the grid and the role ramp ([output-spec.md](output-spec.md))?
- [ ] Ran `python scripts/illustration_theme.py --project-root . apply <file>` so no default literals or Geist stacks remain?
- [ ] If animated: complete static/no-JS frame, reduced motion hides/disables playback, controller copied verbatim from `assets/template-motion.html` (or `-dark`), and `python scripts/verify-motion.py <file>` passes after apply?

**Typography:**

- [ ] Human-readable names use the resolved sans family and technical sublabels (ports, commands, URLs) the resolved mono family, including text without a role class?
- [ ] Page title uses the resolved serif family?
- [ ] Annotation callouts use the resolved serif family in italic? (see [primitive-annotation.md](primitive-annotation.md))
- [ ] No blanket JetBrains Mono unless the technical-color family was explicitly selected?
