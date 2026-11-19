# BPMN 2.0 Process

Use this editorial Process variant when the request explicitly calls for BPMN, BPMN 2.0,
or a BPM standard diagram. For a general process map or swimlane diagram, use the existing
[Process](type-process.md) or [Swimlane](type-swimlane.md) reference.

The supported drawing uses one visible pool, horizontal role lanes, plain start and end events,
generic tasks, User Tasks, diverging exclusive gateways, and solid sequence flows. The SVG uses
BPMN 2.0.2 notation. Multi-pool collaboration, message flows, other gateway and event types,
and editable BPMN XML are outside this variant's first release.
[OMG BPMN 2.0.2 specification](https://www.omg.org/spec/BPMN/2.0.2/PDF)

## Author the process

1. List the participant, lanes, nodes and ordered handoffs. Assign each node to one lane.
2. Give the pool, every lane, every node and every sequence flow a stable, unique ID.
3. Begin with one start event. Use a generic task where the implementation is unspecified.
   Use the person marker in the upper-left corner for a software-assisted human User Task.
4. Give each exclusive gateway output a distinct, visible condition label. Model the outcomes
   as separate edges. Keep the complete graph visible when illustrating one outcome.
5. For motion, name one or more start-to-end routes and assign their names to the sequence flows
   they traverse. A named route must have a single next edge at each step and end at an end event.

## Draw the diagram

| Element | Notation |
| --- | --- |
| Pool | Square-corner rectangle with a solid outline. Separate the participant label from the process with a single line. |
| Lane | Square-corner partition spanning the pool, with a role label inside it. |
| Start and end | Empty circles. Use a thin single outline for the start and a thick single outline for the end. |
| Task | Rounded rectangle with a single thin outline. Add the standard person marker for a User Task. |
| Exclusive gateway | Diamond with a centered X. Place the question beside it and the outcomes beside their outgoing edges. |
| Sequence flow | Solid single line with a filled end arrowhead. It can cross lanes inside the pool. |

Lay out the main sequence left to right and route the branches through clear orthogonal corridors.
Paint the pool and lanes before the flows and labels. Allow space at the arrowheads and use the
[arrow label rules](primitives-core.md#mandatory-connector-rules). Put any legend outside the pool.
Use the project's colors and fonts. Preserve standard glyph and marker geometry in handwritten
styling, including the difference in outline weight between start and end events.

The normal diagram budget of 9 nodes and 12 flows applies. Use an overview with smaller detail
diagrams for larger processes and make event and task responsibilities explicit.

## SVG authoring contract

Set `data-diagram="bpmn"` on the first SVG. Use a group for each pool, lane and node. Give
each declared element a `data-bpmn-id` and one of these `data-bpmn` kinds.

| Kind | Extra attributes |
| --- | --- |
| `participant` | `data-bpmn-name` |
| `lane` | `data-pool` pointing to the participant and `data-bpmn-name` for the role |
| `startEvent`, `endEvent`, `task`, `userTask`, `exclusiveGateway` | `data-lane` pointing to the lane. Mark the User Task and X glyphs with `data-bpmn-marker="user"` and `data-bpmn-marker="exclusive"`, respectively. |
| `sequenceFlow` on a path or line | `data-source` and `data-target` pointing to nodes, a filled `marker-end`, and `data-bpmn-name` on exclusive gateway outputs. Mark the matching visible text with `data-bpmn-label-for="<flow-id>"`. |

For route playback, set `data-bpmn-routes` on each participating flow with a space-separated
list of lowercase names using letters, digits and hyphens. The expense example marks shared flows `approved rejected` and each branch
with its own route name. An optional SVG-level `data-bpmn-default-route` selects the route
for export when the caller gives no route. When a prompt requests motion and several outcomes
are possible, use the outcome the user specifies or an authored default. If neither is known,
ask which route to play. A linear diagram plays without route attributes.

## Worked example

> Draw the expense approval BPMN 2.0 process. Use Employee, Manager and Finance lanes.
> The employee opens and fills out a claim, and the manager reviews it and chooses whether to approve.
> A rejected claim ends with Request denied in Employee. Finance processes an approved claim
> and ends with Payment completed. Animate the approved route.

Start from [expense approval](../assets/example-bpmn.html) or the
[dark](../assets/example-bpmn-dark.html), [full](../assets/example-bpmn-full.html),
or [handwritten](../assets/example-bpmn-hand.html) version. Run these from the skill folder.

```bash
python scripts/verify-bpmn.py expense-approval.html
python scripts/export_diagram.py expense-approval.html --system-fonts --scale 1.25
python scripts/export_diagram.py expense-approval.html --animated --bpmn-route approved --output expense-approved
python scripts/export_diagram.py expense-approval.html --gif --bpmn-route rejected --output expense-rejected
```

The semantic verifier checks geometry, the graph, and SVG presentation attributes and inline styles.
Run the standard strict, geometry and render checks for the finished page. Animated SVG and GIF
follow the same ordered route. The static figure keeps both outcomes, and animated SVG honors reduced motion.
