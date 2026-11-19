#!/usr/bin/env python3
"""Verify the semantics of a BPMN 2.0.2 Process diagram drawn as inline SVG.

Scope is the approved subset only: one visible pool (participant) with
horizontal lanes, none start and end events, generic tasks, User Tasks,
exclusive gateways and solid sequence flows. Anything else declared through
`data-bpmn` is reported as outside the subset rather than guessed at.

The model is the SVG's own data attributes; nothing is keyed to the shipped
example's IDs or coordinates:

  <svg data-diagram="bpmn" [data-bpmn-default-route="<route>"]>
  <g data-bpmn="participant" data-bpmn-id data-bpmn-name>
  <g data-bpmn="lane" data-bpmn-id data-bpmn-name data-pool>
  <g data-bpmn="startEvent|endEvent|task|userTask|exclusiveGateway" data-bpmn-id data-lane [data-bpmn-name]>
  <path|line data-bpmn="sequenceFlow" data-bpmn-id data-source data-target [data-bpmn-name] [data-bpmn-routes]>
  <text data-bpmn-label-for="<flow id>">

Each wrapper's first shape child is its canonical primitive (rect, circle or
polygon) and carries its bounds. The outline is that primitive's stroke, or,
in a hand-drawn file, a sibling `path.rough-generated` hugging an unstroked
primitive. BPMN markers (`data-bpmn-marker`) and arrowheads stay canonical in
every variant.

Checks: unique IDs, pool and lane ownership, lane tiling and node placement,
glyphs and markers, flow endpoints and attachment, start/end degrees,
reachability, named and labelled gateway outputs, and declared routes.

Usage: python scripts/verify-bpmn.py <file.html>...   or   --all
Exit: 0 clean, 1 findings, 2 unreadable input.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import svg_standalone as svg_source
from animate_bpmn import route_flows
from svg_layout import css_declarations
from verify_static_svg_visibility import ancestry, hidden, local, number, overlaps, paint_visible, properties, rectangle

ASSETS = Path(__file__).resolve().parent.parent / "assets"
EXAMPLE_SUFFIXES = ("", "-dark", "-full", "-hand")

EVENTS = {"startEvent", "endEvent"}
TASKS = {"task", "userTask"}
NODES = EVENTS | TASKS | {"exclusiveGateway"}
CONTAINERS = {"participant", "lane"}
FLOW = "sequenceFlow"
PRIMITIVES = {"participant": "rect", "lane": "rect", "startEvent": "circle", "endEvent": "circle",
              "task": "rect", "userTask": "rect", "exclusiveGateway": "polygon"}
MARKERS = {"userTask": "user", "exclusiveGateway": "exclusive"}
SHAPE_TAGS = {"rect", "circle", "ellipse", "polygon", "polyline", "path", "line"}

ATTACH_TOLERANCE = 6.0    # a shaft stops short of a thick outline so the arrowhead tip lands on it
PLACE_TOLERANCE = 1.0
OUTLINE_TOLERANCE = 4.0   # how far a hand-drawn outline may wander from its primitive
THICK_RATIO = 2.0         # an end event's line against the start event's
ROUTE_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
PATH_TOKEN = re.compile(r"[A-Za-z]|[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
PATH_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "C": 6}

Box = tuple[float, float, float, float]
Point = tuple[float, float]


def bpmn_fragment(source: str) -> str | None:
    try:
        start, end = svg_source.figure_span(source)
    except ValueError:
        return None
    fragment = source[start:end]
    _, attrs = svg_source.root_attributes(fragment)
    return fragment if svg_source.decode_xml_references(attrs.get("data-diagram") or "") == "bpmn" else None


def in_scope(source: str) -> bool:
    return bpmn_fragment(source) is not None


def printed(element: ET.Element) -> str:
    """The text an element draws, whitespace collapsed."""
    chunks: list[str] = []

    def walk(node: ET.Element, in_text: bool) -> None:
        if hidden(node):
            return
        in_text = in_text or local(node.tag) == "text"
        if in_text and node.text:
            chunks.append(node.text)
        for child in node:
            walk(child, in_text)
            if in_text and child.tail:
                chunks.append(child.tail)

    walk(element, False)
    return " ".join(" ".join(chunks).split())


def same_words(first: str, second: str) -> bool:
    return " ".join(first.split()).casefold() == " ".join(second.split()).casefold()


def route_points(element: ET.Element, closed: bool = False) -> tuple[list[Point], list[Point]] | None:
    """(on-curve points, every point) of a <line> or an absolute M/L/H/V/Q/C path; None when unreadable.

    `closed` reads an outline instead: the path must end in one Z.
    """
    if local(element.tag) == "line":
        ends = [number(element.get(key, "0")) for key in ("x1", "y1", "x2", "y2")]
        if any(math.isnan(value) for value in ends):
            return None
        points = [(ends[0], ends[1]), (ends[2], ends[3])]
        return points, points
    fields = PATH_TOKEN.findall(element.get("d", ""))
    if closed != (fields[-1:] == ["Z"]):
        return None
    fields = fields[:-1] if closed else fields
    if PATH_TOKEN.sub("", element.get("d", "")).strip(" \t\r\n\f,") or not fields or fields[0] != "M":
        return None
    on_curve: list[Point] = []
    every: list[Point] = []
    x = y = math.nan
    index, command = 0, ""
    while index < len(fields):
        if fields[index].isalpha():
            command = fields[index]
            index += 1
            if command not in PATH_ARITY or (command == "M" and on_curve):
                return None
        arity = PATH_ARITY.get(command, 0)
        values = [number(field) for field in fields[index:index + arity]]
        if not arity or len(values) != arity or any(math.isnan(value) for value in values):
            return None
        index += arity
        if command == "H":
            x = values[0]
        elif command == "V":
            y = values[0]
        else:
            every.extend(zip(values[0:-2:2], values[1:-2:2]))
            x, y = values[-2], values[-1]
        if math.isnan(x) or math.isnan(y):
            return None
        on_curve.append((x, y))
        every.append((x, y))
        if command == "M":
            command = "L"
    return (on_curve, every) if len(on_curve) >= 2 else None


def numbers_box(points: list[Point]) -> Box:
    return (min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points), max(y for _, y in points))


def primitive_box(element: ET.Element) -> Box | None:
    tag = local(element.tag)
    if tag == "rect":
        box = rectangle(element)
    elif tag == "circle":
        cx, cy, r = (number(element.get(key, "0")) for key in ("cx", "cy", "r"))
        box = (cx - r, cy - r, cx + r, cy + r)
    elif tag == "polygon":
        points = polygon_points(element)
        if not points:
            return None
        box = numbers_box(points)
    else:
        return None
    if any(math.isnan(value) for value in box) or box[2] <= box[0] or box[3] <= box[1]:
        return None
    return box


def polygon_points(element: ET.Element) -> list[Point]:
    values = [number(field) for field in re.split(r"[\s,]+", element.get("points", "").strip()) if field]
    if len(values) < 6 or len(values) % 2 or any(math.isnan(value) for value in values):
        return []
    return list(zip(values[0::2], values[1::2]))


def within(inner: Box, outer: Box, tolerance: float) -> bool:
    return (inner[0] >= outer[0] - tolerance and inner[1] >= outer[1] - tolerance
            and inner[2] <= outer[2] + tolerance and inner[3] <= outer[3] + tolerance)


def close(first: Box, second: Box, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(first, second))


def boundary_distance(kind: str, box: Box, point: Point) -> float:
    """How far a point sits from the outline of a node's canonical shape."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    half_w, half_h = (box[2] - box[0]) / 2, (box[3] - box[1]) / 2
    dx, dy = abs(point[0] - cx), abs(point[1] - cy)
    if kind in EVENTS:
        return abs(math.hypot(dx, dy) - half_w)
    if kind == "exclusiveGateway":
        return abs(dx / half_w + dy / half_h - 1) * min(half_w, half_h)
    outside = math.hypot(max(dx - half_w, 0), max(dy - half_h, 0))
    return outside if outside else min(half_w - dx, half_h - dy)


def crosses(first: Point, second: Point, box: Box) -> bool:
    """Whether a segment enters the interior of a box (Liang-Barsky clip)."""
    low, high = 0.0, 1.0
    dx, dy = second[0] - first[0], second[1] - first[1]
    for delta, offset in ((-dx, first[0] - box[0]), (dx, box[2] - first[0]), (-dy, first[1] - box[1]), (dy, box[3] - first[1])):
        if delta == 0:
            if offset <= 0:
                return False
            continue
        ratio = offset / delta
        if delta < 0:
            low = max(low, ratio)
        else:
            high = min(high, ratio)
        if low >= high:
            return False
    return True


def segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    def side(p: Point, q: Point, r: Point) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


def dashed(element: ET.Element) -> bool:
    return any(value not in {"", "none", "0"} for value in properties(element, "stroke-dasharray"))


def inherited_property(chain, key: str, default: str) -> str:
    for node in chain:
        values = list(properties(node, key))
        if values:
            return values[-1]
    return default


def painted(element: ET.Element, channel: str, parents: dict) -> bool:
    """Whether the element's own fill or stroke is drawn (inherited from a wrapper counts)."""
    chain = list(ancestry(element, parents))
    value = inherited_property(chain, channel, "none" if channel == "stroke" else "black")
    if value in {"", "none", "transparent"} or not paint_visible(chain, channel):
        return False
    if channel == "stroke":
        width = number(inherited_property(chain, "stroke-width", "1"))
        return width > 0
    return True


def stroke_width(element: ET.Element, parents: dict) -> float:
    return number(inherited_property(ancestry(element, parents), "stroke-width", "1"))


class Diagram:
    def __init__(self, svg: ET.Element):
        self.svg = svg
        self.parents = {child: parent for parent in svg.iter() for child in parent}
        self.errors: list[str] = []
        self.elements: dict[str, ET.Element] = {}   # data-bpmn-id -> element, first declaration wins
        self.boxes: dict[str, Box] = {}             # id -> canonical primitive bounds
        self.widths: dict[str, float] = {}          # id -> outline stroke width

    def fail(self, subject: str, message: str) -> None:
        self.errors.append(f"{subject}: {message}")

    def kind(self, bpmn_id: str) -> str:
        return self.elements[bpmn_id].get("data-bpmn", "")

    def of_kind(self, *kinds: str) -> list[str]:
        return [bpmn_id for bpmn_id, element in self.elements.items() if element.get("data-bpmn") in kinds]

    # -- declarations ---------------------------------------------------------

    def collect(self) -> None:
        for element in self.svg.iter():
            kind = element.get("data-bpmn")
            if kind is None:
                continue
            bpmn_id = element.get("data-bpmn-id", "").strip()
            subject = bpmn_id or f"<{local(element.tag)} data-bpmn={kind!r}>"
            if kind not in NODES | CONTAINERS | {FLOW}:
                self.fail(subject, f"data-bpmn={kind!r} is outside the approved subset")
                continue
            if not bpmn_id:
                self.fail(subject, "missing data-bpmn-id")
                continue
            if bpmn_id in self.elements:
                self.fail(bpmn_id, "duplicate data-bpmn-id")
                continue
            expected = ("path", "line") if kind == FLOW else ("g",)
            if local(element.tag) not in expected:
                self.fail(bpmn_id, f"{kind} must be drawn as <{'> or <'.join(expected)}>")
                continue
            chain = list(ancestry(element, self.parents))
            if any(node.get("data-bpmn") is not None for node in chain[1:]):
                self.fail(bpmn_id, "BPMN elements must not nest inside one another")
                continue
            if any(hidden(node) for node in chain):
                self.fail(bpmn_id, "is hidden; every BPMN element stays visible")
                continue
            if any("transform" in node.attrib or any(properties(node, "transform")) for node in chain):
                self.fail(bpmn_id, "must not be moved by a transform; geometry is read from its attributes")
                continue
            self.elements[bpmn_id] = element

    def shape(self, bpmn_id: str) -> ET.Element | None:
        """The wrapper's canonical primitive, with its bounds and a visible solid outline recorded."""
        element, kind = self.elements[bpmn_id], self.kind(bpmn_id)
        shapes = [child for child in element if local(child.tag) in SHAPE_TAGS and "data-bpmn-marker" not in child.attrib]
        want = PRIMITIVES[kind]
        if not shapes or local(shapes[0].tag) != want or primitive_box(shapes[0]) is None:
            self.fail(bpmn_id, f"{kind} must start with its <{want}> shape, sized above zero")
            return None
        primitive, box = shapes[0], primitive_box(shapes[0])
        outline = primitive
        if not painted(primitive, "stroke", self.parents):
            outline = None
            for candidate in shapes[1:]:
                points = route_points(candidate, closed=True) if local(candidate.tag) == "path" else None
                if ("rough-generated" in candidate.get("class", "").split() and points is not None
                        and painted(candidate, "stroke", self.parents)
                        and close(numbers_box(points[1]), box, OUTLINE_TOLERANCE)):
                    outline = candidate
                    break
            if outline is None:
                self.fail(bpmn_id, f"{kind} has no visible outline on its <{want}>")
                return None
        if dashed(outline):
            self.fail(bpmn_id, f"{kind} outline must be a solid line")
        self.boxes[bpmn_id] = box
        self.widths[bpmn_id] = stroke_width(outline, self.parents)
        return primitive

    def named(self, bpmn_id: str, required: bool) -> None:
        element = self.elements[bpmn_id]
        name = element.get("data-bpmn-name", "").strip()
        if not name:
            if required:
                self.fail(bpmn_id, f"{self.kind(bpmn_id)} needs a data-bpmn-name")
            return
        text = printed(element)
        if not (same_words(text, name) or name.casefold() in " ".join(text.split()).casefold()):
            self.fail(bpmn_id, f"name {name!r} is not printed on the {self.kind(bpmn_id)}")

    # -- pool and lanes -------------------------------------------------------

    def containers(self) -> None:
        pools = self.of_kind("participant")
        if len(pools) != 1:
            self.fail("diagram", f"expected exactly one visible pool (participant), found {len(pools)}")
        for bpmn_id in pools + self.of_kind("lane"):
            primitive = self.shape(bpmn_id)
            if primitive is not None and number(primitive.get("rx", "0")) > 0:
                self.fail(bpmn_id, f"{self.kind(bpmn_id)} corners must be square")
            self.named(bpmn_id, required=True)
        lanes = self.of_kind("lane")
        if not lanes:
            self.fail("diagram", "the pool needs at least one lane")
        for lane in lanes:
            if self.elements[lane].get("data-pool", "") not in pools:
                self.fail(lane, f"data-pool {self.elements[lane].get('data-pool', '')!r} is not the pool")
        if len(pools) != 1 or pools[0] not in self.boxes or any(lane not in self.boxes for lane in lanes) or not lanes:
            return
        pool = self.boxes[pools[0]]
        placed = sorted(lanes, key=lambda lane: self.boxes[lane][1])
        for lane in placed:
            box = self.boxes[lane]
            if not within(box, pool, PLACE_TOLERANCE):
                self.fail(lane, "lane lies outside its pool")
            if abs(box[2] - pool[2]) > PLACE_TOLERANCE or box[0] <= pool[0] + PLACE_TOLERANCE:
                self.fail(lane, "a horizontal lane runs from the pool's name band to the pool's right edge")
            if any(abs(box[edge] - self.boxes[placed[0]][edge]) > PLACE_TOLERANCE for edge in (0, 2)):
                self.fail(lane, "lanes must share one left and right edge")
        edges = [pool[1], *(edge for lane in placed for edge in self.boxes[lane][1::2]), pool[3]]
        if any(abs(first - second) > PLACE_TOLERANCE for first, second in zip(edges[0::2], edges[1::2])):
            self.fail(pools[0], "lanes must stack top to bottom and fill the pool without gaps or overlap")

    # -- flow nodes -----------------------------------------------------------

    def markers(self, bpmn_id: str, box: Box) -> None:
        element, kind = self.elements[bpmn_id], self.kind(bpmn_id)
        found = [node for node in element.iter() if "data-bpmn-marker" in node.attrib]
        want = MARKERS.get(kind)
        for marker in found:
            if marker.get("data-bpmn-marker") != want:
                self.fail(bpmn_id, f"marker {marker.get('data-bpmn-marker')!r} does not belong on a {kind}")
        mine = [marker for marker in found if marker.get("data-bpmn-marker") == want]
        if want is None:
            return
        if len(mine) != 1:
            self.fail(bpmn_id, f"{kind} needs exactly one {want} marker")
            return
        marker = mine[0]
        drawn = [node for node in marker.iter() if local(node.tag) in SHAPE_TAGS]
        if not drawn or not all(painted(node, "stroke", self.parents) or painted(node, "fill", self.parents) for node in drawn):
            self.fail(bpmn_id, f"{want} marker is not visible")
            return
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        if want == "user":
            heads = [primitive_box(node) for node in drawn if local(node.tag) == "circle"]
            bodies = [node for node in drawn if local(node.tag) == "path"]
            if len(heads) != 1 or heads[0] is None or len(bodies) != 1:
                self.fail(bpmn_id, "user marker is a head circle over one shoulders path")
            elif not within(heads[0], (box[0], box[1], cx, cy), 0):
                self.fail(bpmn_id, "user marker belongs in the task's upper left corner")
            return
        subpaths = re.findall(r"M[^M]*", marker.get("d", "")) if local(marker.tag) == "path" else []
        ends = [route_points(ET.Element("path", {"d": subpath})) for subpath in subpaths]
        if len(ends) != 2 or any(end is None or len(end[0]) != 2 for end in ends):
            self.fail(bpmn_id, "exclusive marker is an X: two straight strokes")
            return
        (a, b), (c, d) = ends[0][0], ends[1][0]
        if not segments_cross(a, b, c, d) or not all(boundary_distance(kind, box, point) > 0 and within((*point, *point), box, 0) for point in (a, b, c, d)):
            self.fail(bpmn_id, "exclusive marker strokes must cross inside the diamond")
        elif math.dist(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), (cx, cy)) > 1 or math.dist(((c[0] + d[0]) / 2, (c[1] + d[1]) / 2), (cx, cy)) > 1:
            self.fail(bpmn_id, "exclusive marker must sit at the diamond's centre")

    def nodes(self) -> None:
        lanes = self.of_kind("lane")
        for bpmn_id in self.of_kind(*NODES):
            kind, element = self.kind(bpmn_id), self.elements[bpmn_id]
            self.named(bpmn_id, required=kind in TASKS)
            lane = element.get("data-lane", "")
            if lane not in lanes:
                self.fail(bpmn_id, f"data-lane {lane!r} is not a lane")
            primitive = self.shape(bpmn_id)
            if primitive is None:
                continue
            box = self.boxes[bpmn_id]
            if lane in self.boxes and not within(box, self.boxes[lane], 0):
                self.fail(bpmn_id, f"{kind} is drawn outside its lane {lane!r}")
            if kind in TASKS and not number(primitive.get("rx", "0")) > 0:
                self.fail(bpmn_id, "a task is a rounded rectangle (rx above zero)")
            if kind == "exclusiveGateway":
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                corners = [(cx, box[1]), (box[2], cy), (cx, box[3]), (box[0], cy)]
                points = polygon_points(primitive)
                if len(points) != 4 or any(min(math.dist(corner, point) for point in points) > 0.5 for corner in corners):
                    self.fail(bpmn_id, "a gateway is a diamond: four points at the middle of each side")
            if kind in EVENTS:
                extra = [child for child in element if local(child.tag) in SHAPE_TAGS and child is not primitive
                         and "rough-generated" not in child.get("class", "").split()]
                if extra:
                    self.fail(bpmn_id, "a none event is an empty circle; other event types are outside the approved subset")
            self.markers(bpmn_id, box)
        starts, ends = self.of_kind("startEvent"), self.of_kind("endEvent")
        thin = max((self.widths[start] for start in starts if start in self.widths), default=None)
        for end in ends:
            if thin is not None and end in self.widths and not self.widths[end] >= THICK_RATIO * thin:
                self.fail(end, "an end event is a thick circle, at least twice the start event's line")
        drawn = [bpmn_id for bpmn_id in self.of_kind(*NODES) if bpmn_id in self.boxes]
        for index, first in enumerate(drawn):
            for second in drawn[index + 1:]:
                if overlaps(self.boxes[first], self.boxes[second]):
                    self.fail(first, f"overlaps {second}")

    # -- sequence flows -------------------------------------------------------

    def arrowhead(self, flow: str) -> None:
        element = self.elements[flow]
        if not painted(element, "stroke", self.parents):
            self.fail(flow, "sequence flow has no visible stroke")
        if dashed(element):
            self.fail(flow, "a sequence flow is a solid line")
        if local(element.tag) == "path" and inherited_property(ancestry(element, self.parents), "fill", "black") != "none":
            self.fail(flow, "a sequence flow path must set fill=none")
        for other in ("marker-start", "marker-mid"):
            if any(value != "none" for value in properties(element, other)):
                self.fail(flow, f"a sequence flow carries no {other}")
        value = element.get("marker-end", "")
        for name, override in css_declarations(element.get("style", "")):
            if name == "marker-end":
                value = override
        value = value.strip()
        match = svg_source.URL_REF_RE.fullmatch(value)
        marker_id = svg_source.decoded_css_url_fragment(match["ident"]) if match else None
        marker = next((node for node in self.svg.iter() if marker_id and local(node.tag) == "marker" and node.get("id") == marker_id), None)
        if marker is None:
            self.fail(flow, "needs marker-end pointing at an arrowhead <marker> in this SVG")
            return
        heads = [node for node in marker if local(node.tag) in {"polygon", "path"}
                 and painted(node, "fill", {node: marker})]
        if not heads or marker.get("orient") not in {"auto", "auto-start-reverse"}:
            self.fail(flow, "arrowhead marker must be a solid filled head with orient=auto")

    def flows(self) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """Check every sequence flow; returns the outgoing and incoming flow IDs per node."""
        nodes = self.of_kind(*NODES)
        outgoing: dict[str, list[str]] = {node: [] for node in nodes}
        incoming: dict[str, list[str]] = {node: [] for node in nodes}
        pool = next((self.boxes[pool] for pool in self.of_kind("participant") if pool in self.boxes), None)
        pairs: set[tuple[str, str]] = set()
        for flow in self.of_kind(FLOW):
            element = self.elements[flow]
            source, target = element.get("data-source", ""), element.get("data-target", "")
            self.arrowhead(flow)
            missing = [f"data-{end} {value!r}" for end, value in (("source", source), ("target", target)) if value not in outgoing]
            if missing:
                self.fail(flow, f"{' and '.join(missing)} must name a flow node (event, task or gateway)")
                continue
            if source == target or (source, target) in pairs:
                self.fail(flow, "connects a node to itself" if source == target else f"duplicates the flow {source} -> {target}")
                continue
            pairs.add((source, target))
            outgoing[source].append(flow)
            incoming[target].append(flow)
            points = route_points(element)
            if points is None:
                self.fail(flow, "geometry must be a <line> or an absolute M/L/H/V/Q/C path")
                continue
            on_curve, every = points
            if pool is not None and not within(numbers_box(every), pool, PLACE_TOLERANCE):
                self.fail(flow, "a sequence flow may not leave the pool")
            for end, node, point in (("starts", source, on_curve[0]), ("ends", target, on_curve[-1])):
                if node in self.boxes and boundary_distance(self.kind(node), self.boxes[node], point) > ATTACH_TOLERANCE:
                    self.fail(flow, f"{end} away from the outline of {node}")
            for other in nodes:
                if other in (source, target) or other not in self.boxes:
                    continue
                box = self.boxes[other]
                inner = (box[0] + 2, box[1] + 2, box[2] - 2, box[3] - 2)
                if any(crosses(first, second, inner) for first, second in zip(on_curve, on_curve[1:])):
                    self.fail(flow, f"runs through {other}")
        return outgoing, incoming

    def degrees(self, outgoing: dict[str, list[str]], incoming: dict[str, list[str]]) -> None:
        if len(self.of_kind("startEvent")) != 1:
            self.fail("diagram", "needs exactly one start event")
        if not self.of_kind("endEvent"):
            self.fail("diagram", "needs an end event")
        for node in outgoing:
            kind, outs, ins = self.kind(node), len(outgoing[node]), len(incoming[node])
            if kind == "startEvent" and (ins or outs != 1):
                self.fail(node, f"a start event has no incoming and exactly one outgoing flow (found {ins} in, {outs} out)")
            elif kind == "endEvent" and (outs or not ins):
                self.fail(node, f"an end event has incoming and no outgoing flow (found {ins} in, {outs} out)")
            elif kind in TASKS and (not ins or outs != 1):
                self.fail(node, f"a task has incoming and exactly one outgoing flow (found {ins} in, {outs} out); split with a gateway")
            elif kind == "exclusiveGateway" and (not ins or not outs or ins + outs < 3):
                self.fail(node, f"an exclusive gateway splits or merges (found {ins} in, {outs} out)")

    def reachability(self, outgoing: dict[str, list[str]], incoming: dict[str, list[str]]) -> None:
        def sweep(seeds: list[str], edges: dict[str, list[str]], end: str) -> set[str]:
            seen, queue = set(seeds), list(seeds)
            while queue:
                for flow in edges[queue.pop()]:
                    node = self.elements[flow].get(end, "")
                    if node not in seen:
                        seen.add(node)
                        queue.append(node)
            return seen

        from_start = sweep(self.of_kind("startEvent"), outgoing, "data-target")
        to_end = sweep(self.of_kind("endEvent"), incoming, "data-source")
        for node in outgoing:
            if node not in from_start:
                self.fail(node, "cannot be reached from a start event")
            elif node not in to_end:
                self.fail(node, "cannot reach an end event")

    def conditions(self, outgoing: dict[str, list[str]]) -> None:
        flows = self.of_kind(FLOW)
        labels: dict[str, list[ET.Element]] = {}
        for text in self.svg.iter():
            target = text.get("data-bpmn-label-for")
            if target is None:
                continue
            if target not in flows or local(text.tag) != "text":
                self.fail(target or "label", "data-bpmn-label-for must sit on a <text> and name a sequence flow")
                continue
            labels.setdefault(target, []).append(text)
        conditional = {flow for node, outs in outgoing.items()
                       if self.kind(node) == "exclusiveGateway" and len(outs) > 1 for flow in outs}
        for node, outs in outgoing.items():
            names = [self.elements[flow].get("data-bpmn-name", "").strip().casefold() for flow in outs if flow in conditional]
            if len(names) != len(set(names)):
                self.fail(node, "gateway outputs must carry distinct condition names")
        for flow in flows:
            name = self.elements[flow].get("data-bpmn-name", "").strip()
            found = labels.get(flow, [])
            if flow in conditional and not name:
                self.fail(flow, "an exclusive gateway output needs its condition in data-bpmn-name")
            if len(found) > 1 or (flow in conditional and not found):
                self.fail(flow, f"expected one visible data-bpmn-label-for label, found {len(found)}")
            for text in found:
                if not printed(text) or not painted(text, "fill", self.parents):
                    self.fail(flow, "condition label is not visible")
                elif not same_words(printed(text), name):
                    self.fail(flow, f"label {printed(text)!r} does not match data-bpmn-name {name!r}")

    def routes(self) -> None:
        names = set()
        default = self.svg.get("data-bpmn-default-route")
        for flow in self.of_kind(FLOW):
            value = self.elements[flow].get("data-bpmn-routes")
            if value is None:
                continue
            tokens = value.split()
            if not tokens or len(tokens) != len(set(tokens)) or not all(ROUTE_RE.fullmatch(token) for token in tokens):
                self.fail(flow, "data-bpmn-routes lists one or more distinct lower-case route names")
                continue
            names.update(tokens)
        if default is not None and default not in names:
            self.fail("diagram", f"data-bpmn-default-route {default!r} is not a declared route")
        for route in sorted(names):
            try:
                route_flows(self.svg, route)
            except ValueError as error:
                self.fail(f"route {route!r}", str(error))

    def check(self) -> list[str]:
        if not printed_named(self.svg, "title") or not printed_named(self.svg, "desc"):
            self.fail("diagram", "the SVG needs a <title> and a <desc>")
        self.collect()
        self.containers()
        self.nodes()
        outgoing, incoming = self.flows()
        self.degrees(outgoing, incoming)
        self.reachability(outgoing, incoming)
        self.conditions(outgoing)
        self.routes()
        return self.errors


def printed_named(svg: ET.Element, tag: str) -> bool:
    return any(local(child.tag) == tag and "".join(child.itertext()).strip() for child in svg)


def check_source(source: str) -> list[str]:
    try:
        fragment = bpmn_fragment(source)
        if fragment is None:
            return ['diagram: the first SVG must declare data-diagram="bpmn"']
        fragment = svg_source.remove_comments(fragment)
        fragment = svg_source.normalize_html_entities(svg_source.xmlify_attributes(fragment))
        svg = ET.fromstring(svg_source.ensure_namespaces(fragment))
    except (ET.ParseError, ValueError) as exc:
        return [f"diagram: invalid SVG: {exc}"]
    return Diagram(svg).check()


def check(path: Path) -> list[str]:
    return check_source(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="*", type=Path, help="HTML files to check")
    parser.add_argument("--all", action="store_true", help="check every shipped BPMN example")
    args = parser.parse_args()
    if args.all and args.paths:
        parser.error("use --all or explicit paths, not both")
    paths = [ASSETS / f"example-bpmn{suffix}.html" for suffix in EXAMPLE_SUFFIXES] if args.all else args.paths
    if not paths:
        parser.error("provide files or --all")
    checked = findings = 0
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            print(f"error: cannot read {path}: {error}", file=sys.stderr)
            return 2
        checked += 1
        errors = check_source(source)
        findings += len(errors)
        for error in errors:
            print(f"{path}: {error}", file=sys.stderr)
        if not errors:
            print(f"OK {path}")
    print(f"Summary: {checked} BPMN file(s) checked, {findings} finding(s).")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
