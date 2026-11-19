# Architecture containment

**Best for:** Hierarchy across nested administrative and traffic scopes.

Use this section when **the network hierarchy itself carries the meaning** — the reader must see what sits inside which scope, and a flattened zone label (`VNET · SNET-APP`) would lie about that hierarchy. Connectors stay Architecture; containment geometry comes from Nested (consistent insets, eyebrow per level, fills stepping up inward). This is a variant of Architecture, not a new type and not a provider-specific grammar.

Two scope kinds, never interchangeable:

| Kind | What it is | Shape | `data-scope-kind` |
|---|---|---|---|
| **Administrative** | Billing, permissions, lifecycle. Holds no traffic. | Horizontal **band** — a full-width containment rect with a 24px header | `admin` |
| **Traffic** | A boundary packets do not cross without an explicit rule. | **Box** — the existing zone rect (`rx=8`) | `traffic` |

Provider-neutral metadata (no vendor prefix):

- `data-grammar="architecture-containment"` on the root `<svg>` — files without it are ordinary Architecture and this contract does not apply.
- `data-scope-id` + `data-scope-kind` on every scope's bounds rect (`data-role="bounds"`). Bounds are always a `<rect>`, for scopes and nodes alike.
- `data-parent` on every nested scope and every node, naming the innermost enclosing `data-scope-id`. Only the outermost scope, which no other scope encloses, may omit it.
- Nodes: `data-node-id`, `data-kind` of `compute` (workloads inside a traffic scope), `endpoint` (private endpoint inside a traffic scope), or `managed` (PaaS that belongs to an administrative scope).
- An `endpoint` carries `data-target` naming the `managed` node it reaches.
- A peering path carries `data-peering`, `data-from`, and `data-to` naming the two traffic scopes it joins.

**PaaS placement (normative).** A managed service is never inside a traffic scope. It sits in the administrative band that owns it. What lives in the subnet is its private endpoint. Drawing a database inside a subnet tells the reader it sits behind that subnet's security rules, which it does not. `scripts/verify-architecture-containment.py` fails a `managed` node whose bounds fall inside any `traffic` scope, and an `endpoint` that is not inside one.

**Sibling axis.** Sibling traffic scopes at one level share one axis. Directly under an administrative band the parent's aspect chooses it: wider than tall (or square) → a row sharing one `y`; taller than wide → a column sharing one `x`. Nested children take the perpendicular axis: siblings inside a traffic scope that sits in a row form a column, and their own children form a row again. Do not mix axes at one level.

**Budget** (tightens Architecture's flat 3-zone cap; see `layout-budget.md`): ≤2 administrative bands, ≤4 traffic scopes, ≤8 nodes, 2 accent elements. Split per subscription when a figure exceeds that.

**Draw scopes in place.** Containment is read from each bounds rect's own `x`, `y`, `width`, and `height`. Do not position a scope or node with a `transform` attribute, a moving inline style (`transform`, `translate`, `x`, `y`, `position`, `margin`, and similar), a nested `<svg>`, a `<style>` rule, or an animation, on the element or any group around it. The checker fails each of those. It does not evaluate external stylesheets or script, so keep containment geometry out of both.

`scripts/verify-architecture-containment.py` checks unique IDs, resolving innermost parents, geometric containment, `<rect>` bounds, the admin-band vs traffic-box shapes (with `stroke-dasharray` resolved as rendered, so `none` or all-zero dashes count as solid), PaaS placement, endpoint targets, sibling axes, declared peerings, and the moved-geometry rule above. Files without `data-grammar="architecture-containment"` are skipped.

## Examples
- `assets/example-architecture-containment.html` — minimal light
- `assets/example-architecture-containment-dark.html` — minimal dark
- `assets/example-architecture-containment-full.html` — full editorial
- `assets/example-architecture-containment-hand.html` — hand-drawn from the verified light source
