"""Play one BPMN route over the preserved SVG sequence flows."""

from __future__ import annotations

import re
from collections import defaultdict
from xml.etree import ElementTree as ET
from xml.sax.saxutils import quoteattr

from animate_export import ARROW_TAGS, geometry

FLOW_MS = 680
END_HOLD_MS = 1000
PATH_DATA = re.compile(r"[Mm] *[+\-.0-9][MmLlHhVvCcSsQqTtAaZzEe0-9+., -]*")


def route_flows(root: ET.Element, requested: str | None) -> list[ET.Element]:
    """Resolve the selected sequence flows in process order, from start to end."""
    nodes, flows = {}, {}
    for element in root.iter():
        kind = element.get("data-bpmn")
        if kind == "sequenceFlow":
            destination = flows
        elif element.get("data-lane"):
            destination = nodes
        else:
            continue
        identifier = element.get("data-bpmn-id", "")
        if not identifier.strip():
            raise ValueError("BPMN route playback requires data-bpmn-id on each node and sequence flow.")
        if identifier in nodes or identifier in flows:
            raise ValueError(f"Duplicate BPMN node or sequence flow ID {identifier!r}.")
        destination[identifier] = element

    starts = [identifier for identifier, node in nodes.items() if node.get("data-bpmn") == "startEvent"]
    if len(starts) != 1:
        raise ValueError("BPMN route playback requires exactly one startEvent.")

    route = requested if requested is not None else root.get("data-bpmn-default-route")
    routes = {
        identifier: flow.get("data-bpmn-routes", "").split() for identifier, flow in flows.items()
    }
    names = sorted({name for memberships in routes.values() for name in memberships})
    available = f" Available routes: {', '.join(names)}." if names else ""
    selected = {
        identifier: flow for identifier, flow in flows.items()
        if route is None or route in routes[identifier]
    }
    if route is not None and not selected:
        raise ValueError(f"Unknown BPMN route {route!r}.{available}")

    outgoing = defaultdict(list)
    for identifier, flow in selected.items():
        source, target = flow.get("data-source"), flow.get("data-target")
        if source not in nodes or target not in nodes:
            raise ValueError(f"BPMN sequence flow {identifier!r} must link two nodes by ID.")
        outgoing[source].append(flow)

    current = starts[0]
    visited = {current}
    ordered = []
    while nodes[current].get("data-bpmn") != "endEvent":
        choices = outgoing[current]
        if len(choices) > 1:
            if route is None:
                raise ValueError("BPMN playback at a branch requires --bpmn-route or "
                                 f"data-bpmn-default-route on the SVG.{available}")
            raise ValueError(f"BPMN route {route!r} is ambiguous at node {current!r}.")
        if not choices:
            raise ValueError(f"BPMN playback stops at {current!r} before reaching an endEvent.")
        flow = choices[0]
        current = flow.attrib["data-target"]
        if current in visited:
            raise ValueError(f"BPMN route playback contains a cycle at {current!r}.")
        visited.add(current)
        ordered.append(flow)
    if len(ordered) != len(selected):
        raise ValueError("BPMN playback has selected sequence flows outside the start-to-end path.")
    return ordered


def animate_route(svg: str, route: str | None, budget_ms: int) -> tuple[str, str, int]:
    """Return SVG with motion tokens, CSS, and the full looping timeline duration."""
    root = ET.fromstring(svg)
    flows = route_flows(root, route)
    # Leave a complete static frame at the end of each loop for playback and GIF capture.
    flow_ms = min(FLOW_MS, (budget_ms - END_HOLD_MS) / len(flows))
    duration = min(budget_ms, len(flows) * FLOW_MS + END_HOLD_MS)
    parents = {child: parent for parent in root.iter() for child in parent}
    tokens, rules = [], []
    for index, flow in enumerate(flows):
        identifier = flow.attrib["data-bpmn-id"]
        tag = flow.tag.rsplit("}", 1)[-1]
        path = geometry(tag, flow.attrib) if tag in ARROW_TAGS else None
        # Geometry becomes a CSS path() string. Accept only SVG path commands and numeric operands.
        if not path or not PATH_DATA.fullmatch(path := " ".join(path.split())):
            raise ValueError(f"BPMN sequence flow {identifier!r} needs SVG path, line or polyline geometry.")

        name = f"illustrate-bpmn-flow-{len(flows)}-{duration}-{index}"
        style = quoteattr(f"offset-path:path('{path}');offset-rotate:0deg")
        token = (f'<circle class="{name}" data-for-flow={quoteattr(identifier)} r="5" opacity="0" '
                 f'fill="var(--accent,var(--color-accent,var(--accent-color,#f97316)))" '
                 f'stroke="white" stroke-width="1.5" style={style}/>')
        element = flow
        while element is not root:
            if transform := element.get("transform"):
                token = f"<g transform={quoteattr(transform)}>{token}</g>"
            element = parents[element]
        tokens.append(token)

        start = index * flow_ms / duration * 100
        finish = (index + 1) * flow_ms / duration * 100
        fade = min(.01, (finish - start) / 4)
        entry = (f'0%,{start:.6f}%{{opacity:0;offset-distance:0%}}'
                 f'{start + fade:.6f}%{{opacity:1;offset-distance:0%}}'
                 if index else '0%{opacity:1;offset-distance:0%}')
        rules.append(f'[data-bpmn-playback] .{name}{{animation:{name} {duration}ms linear infinite}}'
                     f'@keyframes {name}{{'
                     f'{entry}'
                     f'{finish - fade:.6f}%{{opacity:1;offset-distance:100%}}'
                     f'{finish:.6f}%,100%{{opacity:0;offset-distance:100%}}}}')
    closing = re.search(r"</svg\s*>\s*\Z", svg)
    if closing is None:
        raise ValueError("BPMN playback requires a complete SVG root.")
    overlay = '<g aria-hidden="true" data-bpmn-playback="true">' + "".join(tokens) + "</g>"
    css = "@media (prefers-reduced-motion: no-preference){" + "".join(rules) + "}"
    return svg[:closing.start()] + overlay + svg[closing.start():], css, duration
