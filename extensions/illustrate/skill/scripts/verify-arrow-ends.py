#!/usr/bin/env python3
"""Verify every arrow is straight for at least its arrowhead's length before each tip.

An SVG marker with orient="auto" / "auto-start-reverse" follows the exact end
tangent of its path, but the eye follows the line arriving at the head. A curve
or rounded corner that is still bending right at the tip therefore looks like
its arrowhead points the wrong way, in HTML, SVG and PNG alike.

The rule (SKILL.md §6): each headed tip needs a straight lead of at least the
arrowhead's length + 4 px (minimum 10 px). Curves put their last control point
on that lead; routed connectors finish their last corner before it.

For every <path>, <line> and <polyline> with marker-end and/or marker-start:

* head length = the marker's extent along the path on the longer side of refX,
  max(refX, markerWidth - refX), mapped through its viewBox, times the
  element's (inherited) stroke-width unless markerUnits="userSpaceOnUse";
* lead = head length + 4 px, at least 10 px;
* bend = the angle between the tip's tangent (what the marker follows) and the
  chord from the point `lead` px back along the path to the tip (what the eye
  follows). A tip fails above 3 degrees. Both tips of a two-headed arrow count.

Arcs (A) are converted to centre form and sampled, so they are judged like any
curve. A <line> is straight and always passes. Transforms are ignored (angles
are invariant under them) and stroke-width set only by a CSS class falls back
to 1, which under-sizes the lead; set the width on the element or a group.

Usage (from the skill directory):
    python scripts/verify-arrow-ends.py --all
    python scripts/verify-arrow-ends.py assets/example-x.html
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = SKILL_ROOT / "assets"

MAX_BEND = 3.0
LEAD_MARGIN = 4.0
MIN_LEAD = 10.0
CURVE_STEPS = 64

NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
TOKEN = re.compile(rf"[MmLlHhVvCcSsQqTtAaZz]|{NUM}")
URL_ID = re.compile(r"url\(\s*['\"]?#([^)'\"\s]+)")
STYLE_WIDTH = re.compile(r"stroke-width\s*:\s*(" + NUM + ")")


# --- path geometry -----------------------------------------------------------

class Segment:
    """One drawn piece of a path: dense sample points plus exact end tangents."""

    __slots__ = ("points", "t0", "t1")

    def __init__(self, points, t0, t1) -> None:
        self.points, self.t0, self.t1 = points, t0, t1

    def reversed(self) -> "Segment":
        flip = lambda t: (-t[0], -t[1])  # noqa: E731
        return Segment(self.points[::-1], flip(self.t1), flip(self.t0))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _nonzero(*vectors):
    for v in vectors:
        if abs(v[0]) > 1e-9 or abs(v[1]) > 1e-9:
            return v
    return (0.0, 0.0)


def _line(a, b) -> Segment:
    t = _sub(b, a)
    return Segment([a, b], t, t)


def _cubic(a, b, c, d) -> Segment:
    def at(t):
        u = 1 - t
        return tuple(u**3 * a[k] + 3 * u * u * t * b[k] + 3 * u * t * t * c[k] + t**3 * d[k] for k in range(2))
    pts = [at(i / CURVE_STEPS) for i in range(CURVE_STEPS + 1)]
    return Segment(pts, _nonzero(_sub(b, a), _sub(c, a), _sub(d, a)), _nonzero(_sub(d, c), _sub(d, b), _sub(d, a)))


def _quad(a, b, c) -> Segment:
    def at(t):
        u = 1 - t
        return tuple(u * u * a[k] + 2 * u * t * b[k] + t * t * c[k] for k in range(2))
    pts = [at(i / CURVE_STEPS) for i in range(CURVE_STEPS + 1)]
    return Segment(pts, _nonzero(_sub(b, a), _sub(c, a)), _nonzero(_sub(c, b), _sub(c, a)))


def _arc(p0, rx, ry, phi_deg, large, sweep, p1) -> Segment:
    """SVG endpoint arc -> centre form (SVG 1.1 implementation notes F.6.5), sampled."""
    rx, ry = abs(rx), abs(ry)
    if rx < 1e-9 or ry < 1e-9 or p0 == p1:
        return _line(p0, p1)
    phi = math.radians(phi_deg % 360)
    cos, sin = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1, y1 = cos * dx + sin * dy, -sin * dx + cos * dy
    scale = x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    root = math.sqrt(max(0.0, num / den)) * (-1 if large == sweep else 1)
    cx1, cy1 = root * rx * y1 / ry, -root * ry * x1 / rx
    cx = cos * cx1 - sin * cy1 + (p0[0] + p1[0]) / 2
    cy = sin * cx1 + cos * cy1 + (p0[1] + p1[1]) / 2

    def angle(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    theta = angle(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    delta = angle((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    def at(t):
        a = theta + delta * t
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        return (cos * ex - sin * ey + cx, sin * ex + cos * ey + cy)

    def tangent(t):
        a = theta + delta * t
        ex, ey = -rx * math.sin(a) * delta, ry * math.cos(a) * delta
        return (cos * ex - sin * ey, sin * ex + cos * ey)

    pts = [at(i / CURVE_STEPS) for i in range(CURVE_STEPS + 1)]
    pts[0], pts[-1] = p0, p1
    return Segment(pts, tangent(0), tangent(1))


def parse_path(d: str) -> list[list[Segment]]:
    """Absolute segments of a path `d`, grouped by subpath (M starts a new one)."""
    tokens = TOKEN.findall(d)
    subpaths: list[list[Segment]] = []
    i, cmd = 0, None
    x = y = sx = sy = 0.0
    last_c = last_q = None

    def num():
        nonlocal i
        value = float(tokens[i])
        i += 1
        return value

    def flag():
        # Arc flags may be packed ("a8 8 0 018 8"): split the raw token if needed.
        nonlocal i
        tok = tokens[i]
        if tok in ("0", "1"):
            i += 1
            return int(tok)
        tokens[i] = tok[1:]
        return int(tok[0])

    def add(seg):
        if not subpaths:
            subpaths.append([])
        subpaths[-1].append(seg)

    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            if cmd in "Zz":
                if (x, y) != (sx, sy):
                    add(_line((x, y), (sx, sy)))
                x, y = sx, sy
                last_c = last_q = None
                continue
        if cmd is None:
            break
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if c == "M":
            x, y = num() + ox, num() + oy
            sx, sy = x, y
            subpaths.append([])
            cmd = "l" if rel else "L"
            last_c = last_q = None
            continue
        p0 = (x, y)
        if c == "L":
            p = (num() + ox, num() + oy)
            add(_line(p0, p))
            last_c = last_q = None
        elif c == "H":
            p = (num() + (x if rel else 0.0), y)
            add(_line(p0, p))
            last_c = last_q = None
        elif c == "V":
            p = (x, num() + (y if rel else 0.0))
            add(_line(p0, p))
            last_c = last_q = None
        elif c in "CS":
            p1 = (2 * x - last_c[0], 2 * y - last_c[1]) if c == "S" and last_c else p0
            if c == "C":
                p1 = (num() + ox, num() + oy)
            p2 = (num() + ox, num() + oy)
            p = (num() + ox, num() + oy)
            add(_cubic(p0, p1, p2, p))
            last_c, last_q = p2, None
        elif c in "QT":
            p1 = (2 * x - last_q[0], 2 * y - last_q[1]) if c == "T" and last_q else p0
            if c == "Q":
                p1 = (num() + ox, num() + oy)
            p = (num() + ox, num() + oy)
            add(_quad(p0, p1, p))
            last_q, last_c = p1, None
        elif c == "A":
            rx, ry, rot = num(), num(), num()
            large, sweep = flag(), flag()
            p = (num() + ox, num() + oy)
            add(_arc(p0, rx, ry, rot, large, sweep, p))
            last_c = last_q = None
        else:
            raise ValueError(f"unsupported path command {cmd!r}")
        x, y = p
    return [s for s in subpaths if s]


def _tip_bend(segments: list[Segment], lead: float) -> float:
    """Degrees between the tip tangent and the chord from `lead` px back (segments run toward the tip)."""
    segments = [s for s in segments if math.dist(s.points[0], s.points[-1]) > 1e-9 or len(s.points) > 2]
    if not segments:
        return 0.0
    tangent = _nonzero(*(s.t1 for s in reversed(segments)))
    tip = segments[-1].points[-1]
    back, travelled = tip, 0.0
    done = False
    for seg in reversed(segments):
        pts = seg.points
        for k in range(len(pts) - 1, 0, -1):
            a, b = pts[k], pts[k - 1]
            step = math.dist(a, b)
            if travelled + step >= lead and step > 0:
                f = (lead - travelled) / step
                back = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
                done = True
                break
            travelled += step
            back = b
        if done:
            break
    chord = _sub(tip, back)
    if math.hypot(*chord) < 1e-9 or math.hypot(*tangent) < 1e-9:
        return 0.0
    diff = math.degrees(math.atan2(tangent[1], tangent[0]) - math.atan2(chord[1], chord[0]))
    return abs((diff + 180) % 360 - 180)


def end_bend(d: str, lead: float) -> float:
    """Bend at the marker-end tip of path `d` (last vertex of the last subpath)."""
    subpaths = parse_path(d)
    return _tip_bend(subpaths[-1], lead) if subpaths else 0.0


def start_bend(d: str, lead: float) -> float:
    """Bend at the marker-start tip of path `d`, judged by traversing the first subpath backwards."""
    subpaths = parse_path(d)
    return _tip_bend([s.reversed() for s in reversed(subpaths[0])], lead) if subpaths else 0.0


# --- markers and documents ---------------------------------------------------

def _float(value, default=None):
    try:
        return float(str(value).strip().removesuffix("px"))
    except (TypeError, ValueError):
        return default


def marker_head_length(marker: dict[str, str], stroke_width: float) -> float:
    """User-space length of a marker's head along the path at its reference point."""
    width = _float(marker.get("markerwidth"), 3.0)
    ref_x = _float(marker.get("refx"), 0.0)
    box = [_float(v, 0.0) for v in re.split(r"[\s,]+", marker.get("viewbox", "").strip()) if v]
    if len(box) == 4 and box[2] > 0:
        ref_x = (ref_x - box[0]) * width / box[2]
    head = max(ref_x, width - ref_x)
    if marker.get("markerunits", "strokeWidth").strip() != "userSpaceOnUse":
        head *= stroke_width
    return head


def lead_for(head: float) -> float:
    return max(MIN_LEAD, head + LEAD_MARGIN)


class _Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.markers: dict[str, dict[str, str]] = {}
        self.arrows: list[tuple[str, dict[str, str], float, int]] = []
        self._widths: list[tuple[str, float]] = []

    def _width(self, attrs: dict[str, str]) -> float | None:
        match = STYLE_WIDTH.search(attrs.get("style", ""))
        return _float(match.group(1)) if match else _float(attrs.get("stroke-width"))

    def _visit(self, tag: str, raw, closes: bool) -> None:
        attrs = {k.casefold(): (v or "") for k, v in raw}
        inherited = self._widths[-1][1] if self._widths else 1.0
        own = self._width(attrs)
        width = own if own is not None else inherited
        if tag == "marker" and attrs.get("id"):
            self.markers[attrs["id"]] = attrs
        if tag in {"path", "line", "polyline"} and ("marker-end" in attrs or "marker-start" in attrs):
            self.arrows.append((tag, attrs, width, self.getpos()[0]))
        if not closes:
            self._widths.append((tag, width))

    def handle_starttag(self, tag, attrs):
        self._visit(tag.casefold(), attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._visit(tag.casefold(), attrs, True)

    def handle_endtag(self, tag):
        tag = tag.casefold()
        for index in range(len(self._widths) - 1, -1, -1):
            if self._widths[index][0] == tag:
                del self._widths[index:]
                break


def _element_path(tag: str, attrs: dict[str, str]) -> str | None:
    if tag == "path":
        return attrs.get("d")
    if tag == "polyline":
        nums = re.findall(NUM, attrs.get("points", ""))
        if len(nums) < 4:
            return None
        pairs = [f"{nums[k]} {nums[k + 1]}" for k in range(0, len(nums) - 1, 2)]
        return "M " + " L ".join(pairs)
    return None  # <line>: straight by construction


def check_source(source: str, name: str = "<source>") -> list[str]:
    doc = _Document()
    doc.feed(source)
    doc.close()
    findings: list[str] = []
    for tag, attrs, width, line in doc.arrows:
        d = _element_path(tag, attrs)
        if not d:
            continue
        for end in ("marker-end", "marker-start"):
            match = URL_ID.search(attrs.get(end, ""))
            if not match:
                continue
            marker = doc.markers.get(match.group(1))
            if marker is None:
                continue  # an unresolved marker draws nothing
            lead = lead_for(marker_head_length(marker, width))
            try:
                bend = (end_bend if end == "marker-end" else start_bend)(d, lead)
            except (ValueError, IndexError) as exc:
                findings.append(f"{name}:{line}: unreadable <{tag}> path ({exc}): {d[:80]}")
                break
            if bend > MAX_BEND:
                tip = "end" if end == "marker-end" else "start"
                findings.append(
                    f"{name}:{line}: arrow {tip} bends {bend:.1f}deg within its {lead:g}px lead "
                    f"(max {MAX_BEND:g}) - finish the last corner, or put the last control point, "
                    f"at least {lead:g}px before the tip: {d.strip()[:90]}"
                )
    return findings


def check(path: Path) -> list[str]:
    return check_source(path.read_text(encoding="utf-8"), path.name)


def targets(args: argparse.Namespace) -> list[Path]:
    if args.all:
        return sorted(ASSET_DIR.rglob("*.html"))
    return [Path(p) for p in args.files]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", help="HTML or SVG diagrams to check")
    parser.add_argument("--all", action="store_true", help="check every shipped asset (recursively)")
    args = parser.parse_args()

    paths = targets(args)
    if not paths:
        parser.error("pass one or more files, or --all")

    findings: list[str] = []
    for path in paths:
        if not path.exists():
            findings.append(f"{path}: file not found")
            continue
        findings.extend(check(path))

    for finding in findings:
        print(finding)
    print(f"Summary: {len(paths)} file(s) checked, {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
