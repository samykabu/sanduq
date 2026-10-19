#!/usr/bin/env python3
"""Verify no diagram label mask is clipped by a node painted after it.

SKILL.md §6 keeps an arrow label 6-10px clear of its connector, and primitives-core.md fixes the
paint order as background -> zones -> arrows -> labels -> nodes. Nothing keeps a
label mask off a *node*, so a label whose mask lands partly inside a node
rectangle that is painted later gets covered by the node fill: the text renders
as a fragment sitting on the node border.

Paint order is what makes this a defect rather than a stylistic choice:

* A mask overlapping a zone container is fine - zones are painted before labels,
  so the label stays on top. Zone eyebrows rely on this.
* A mask overlapping a node declared *later* in the document is clipped by that
  node. That is the failure this check reports.

Shape heuristics follow the shipped templates:

* A node is a `<rect>` at least 60x40 - large enough for a title and sublabel.
* A label mask is a `<rect>` 20-200 wide and 8-14 tall - the masking plate that
  SKILL.md §6 prescribes (markup in references/primitives-core.md) for arrow
  labels and zone eyebrows. The width cap covers the long mono plates shipped
  in example-sequence-oauth.html (128px) and the wider plates CJK labels need
  at the same glyph count.
* A mask fully contained in a node is a badge chip (`EXT`, `EDGE`, `ORIG`) and
  is legal.

The check reads geometry only, never colour, so it is theme-neutral: it gives the
same answer on upstream-literal examples and on `illustration_theme.py apply` output.

`--orthogonal` adds connector rule 1 (orthogonal only): every arrow (a `<path>`,
`<polyline>` or `<line>` carrying a marker) is built from horizontal and vertical
runs joined by quarter turns. A straight piece must run within 1 degree of an
axis; a curved piece (A, Q, C) must leave and arrive along an axis and turn by
90 degrees, so a rounded elbow passes and a diagonal or an S-curve fails; a
half-turn hop at most 24px wide over a crossing (rule 3) also passes. Path
parsing is shared with verify-arrow-ends.py. `self_check.py --strict` runs it too.

Usage (from the skill directory):
    python scripts/verify-geometry.py --all --baseline
    python scripts/verify-geometry.py assets/example-x.html
    python scripts/verify-geometry.py --orthogonal assets/example-x.html

Ported from diagram-design (MIT). `--baseline` skips the legacy files listed in
scripts/verify-geometry-baseline.txt, like lint-skin.py.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = SKILL_ROOT / "assets"
BASELINE = SKILL_ROOT / "scripts/verify-geometry-baseline.txt"

RECT_RE = re.compile(
    r"<rect\b[^>]*?"
    r'\bx="(?P<x>-?[\d.]+)"\s+'
    r'y="(?P<y>-?[\d.]+)"\s+'
    r'width="(?P<w>[\d.]+)"\s+'
    r'height="(?P<h>[\d.]+)"',
    re.IGNORECASE,
)

NODE_MIN_W = 60.0
NODE_MIN_H = 40.0
MASK_MIN_W = 20.0
MASK_MAX_W = 200.0
MASK_MIN_H = 8.0
MASK_MAX_H = 14.0
EPSILON = 0.5
AXIS_TOLERANCE = math.tan(math.radians(1.0))  # a run within 1 degree of an axis counts as axis-aligned
MAX_HOP = 24.0  # a bridge/hop over a crossing (connector rule 3) is a half turn at most this wide


class Rect:
    __slots__ = ("x", "y", "w", "h", "line", "offset")

    def __init__(self, x, y, w, h, line, offset) -> None:
        self.x, self.y, self.w, self.h = x, y, w, h
        self.line, self.offset = line, offset

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def __repr__(self) -> str:
        return f"({self.x:g},{self.y:g} {self.w:g}x{self.h:g})"


def parse_rects(source: str) -> list[Rect]:
    rects: list[Rect] = []
    for match in RECT_RE.finditer(source):
        rects.append(
            Rect(
                float(match.group("x")),
                float(match.group("y")),
                float(match.group("w")),
                float(match.group("h")),
                source.count("\n", 0, match.start()) + 1,
                match.start(),
            )
        )
    return rects


def overlap(a: Rect, b: Rect) -> tuple[float, float]:
    return (
        min(a.right, b.right) - max(a.x, b.x),
        min(a.bottom, b.bottom) - max(a.y, b.y),
    )


def contained(inner: Rect, outer: Rect) -> bool:
    return (
        inner.x >= outer.x - EPSILON
        and inner.y >= outer.y - EPSILON
        and inner.right <= outer.right + EPSILON
        and inner.bottom <= outer.bottom + EPSILON
    )


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    rects = parse_rects(source)
    nodes = [r for r in rects if r.w >= NODE_MIN_W and r.h >= NODE_MIN_H]
    masks = [
        r
        for r in rects
        if MASK_MIN_W <= r.w <= MASK_MAX_W and MASK_MIN_H <= r.h <= MASK_MAX_H
    ]

    findings: list[str] = []
    for mask in masks:
        for node in nodes:
            if node.offset <= mask.offset:
                continue  # painted before the label; the label stays on top
            dx, dy = overlap(mask, node)
            if dx <= 1.0 or dy <= 1.0 or contained(mask, node):
                continue
            findings.append(
                f"{path.name}:{mask.line}: label mask {mask} is clipped by node "
                f"{node} declared later at line {node.line} (overlap {dx:g}x{dy:g}px)"
                f" - move the label onto a free segment of its connector"
            )
            break
    return findings


def _arrow_ends():
    script = Path(__file__).resolve().parent / "verify-arrow-ends.py"
    spec = importlib.util.spec_from_file_location("verify_arrow_ends", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _axis(vector: tuple[float, float]) -> str | None:
    """'h' or 'v' when the vector runs along an axis, None for a diagonal or a zero vector."""
    dx, dy = abs(vector[0]), abs(vector[1])
    if dx < 1e-9 and dy < 1e-9:
        return None
    if dy <= dx * AXIS_TOLERANCE:
        return "h"
    if dx <= dy * AXIS_TOLERANCE:
        return "v"
    return None


def orthogonal_findings(source: str, name: str = "<source>") -> list[str]:
    """Connector rule 1: arrows are axis-aligned runs joined by quarter turns."""
    arrows = _arrow_ends()
    doc = arrows._Document()
    doc.feed(source)
    doc.close()
    findings: list[str] = []
    for tag, attrs, _width, line in doc.arrows:
        if tag == "line":
            try:
                chord = (float(attrs.get("x2", 0)) - float(attrs.get("x1", 0)), float(attrs.get("y2", 0)) - float(attrs.get("y1", 0)))
            except ValueError:
                continue
            if _axis(chord) is None and chord != (0.0, 0.0):
                findings.append(f"{name}:{line}: diagonal <line> arrow - use an r=8 elbow (connector rule 1)")
            continue
        d = arrows._element_path(tag, attrs)
        if not d:
            continue
        try:
            subpaths = arrows.parse_path(d)
        except (ValueError, IndexError) as exc:
            findings.append(f"{name}:{line}: unreadable <{tag}> path ({exc}): {d[:80]}")
            continue
        for segment in (s for subpath in subpaths for s in subpath):
            start, end = _axis(segment.t0), _axis(segment.t1)
            if len(segment.points) == 2:
                ok = start is not None or segment.points[0] == segment.points[1]
            else:
                chord = (segment.points[-1][0] - segment.points[0][0], segment.points[-1][1] - segment.points[0][1])
                hop = start is not None and start == end and _axis(chord) not in (None, start) and math.hypot(*chord) <= MAX_HOP
                ok = hop or (start is not None and end is not None and start != end)
            if not ok:
                findings.append(
                    f"{name}:{line}: arrow is not orthogonal near ({segment.points[-1][0]:g},{segment.points[-1][1]:g})"
                    f" - route it as horizontal and vertical runs joined by r=8 quarter turns (connector rule 1): {d.strip()[:90]}"
                )
                break
    return findings


def load_baseline(path: Path = BASELINE) -> set[str]:
    if not path.is_file():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def targets(args: argparse.Namespace) -> list[Path]:
    if args.all:
        skip = load_baseline() if args.baseline else set()
        return [p for p in sorted(ASSET_DIR.glob("*.html")) if p.name not in skip]
    return [Path(p) for p in args.files]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="HTML diagrams to check")
    parser.add_argument("--all", action="store_true", help="check every shipped asset")
    parser.add_argument(
        "--baseline", action="store_true", help="under --all, skip files in verify-geometry-baseline.txt"
    )
    parser.add_argument(
        "--orthogonal", action="store_true", help="also check connector rule 1: arrows are orthogonal runs and quarter turns"
    )
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
        if args.orthogonal:
            findings.extend(orthogonal_findings(path.read_text(encoding="utf-8"), path.name))

    for finding in findings:
        print(finding)
    print(f"Summary: {len(paths)} file(s) checked, {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
