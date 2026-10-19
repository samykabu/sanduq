# Templates and variants

Routed from SKILL.md §10. Every first-class diagram ships in four core variants (see `assets/`):

| Variant | File pattern | When to use |
|---|---|---|
| **Minimal light** (default) | `template.html`, `example-<type>.html` | Screenshot-ready. Diagram + title. Uses the active project's light palette. |
| **Minimal dark** | `template-dark.html`, `example-<type>-dark.html` | Dark mode sites, slides, high-contrast posts. |
| **Full editorial** | `template-full.html`, `example-<type>-full.html` | Long-form posts where the diagram is the hero. |
| **Hand-drawn** | `template-hand.html`, `example-<type>-hand.html` | Deterministic Rough.js rendering for essays, workshops, and working-sketch presentation. |
| **Consultant special** (quadrant only) | `example-quadrant-consultant.html` | BCG/McKinsey-style 2×2 scenario matrix. Clinical sans-serif, white bg, bold blue double-ended axes, named scenario cells. See [type-quadrant.md](type-quadrant.md#consultant-special-22-scenario-matrix). |
| **Technical-color architecture** | `assets/technical-color/architecture/` | Cloud, infrastructure, security, and topology illustrations with semantic component colors and built-in Copy/PNG/PDF. |
| **Technical-color process flow** | `assets/technical-color/process-flow/` | Approval, automation, runbook, and decision workflows with numbered steps and built-in Copy/PNG/PDF. |

**Hand-drawn generation** — see [primitive-sketchy.md](primitive-sketchy.md). The committed `-hand`
files are generated from every minimal example with Rough.js; do not edit them manually.

**Terminal variant** (optional, replaces any of the above) — see [primitive-terminal.md](primitive-terminal.md).
`template-terminal.html`, `example-<type>-terminal.html`. Charcoal-black CLI-window chrome, monospace
type, one red-orange accent. Good for dev-tool / CLI-product posts and technical social cards; not
brand-tokenized, so skip it for onboarded/brand-matched output.

**Animation** (optional presentation layer) — see [animation.md](animation.md). Modes are `none`
(default), `reveal`, `step`, and `loop`; motion never changes the static meaning or raises the
complexity budget. Start from `assets/template-motion.html` or `-dark.html` only when motion is
requested and keep the controller verbatim. Animated examples ship as `example-<name>-animated.html`
and never get a `-hand` variant.
