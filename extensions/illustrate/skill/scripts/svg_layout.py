"""Static SVG viewBox and boxed-label checks for Illustrate.

Ported from Diagram Design's self-check (#408, #514, MIT).
These checks skip content whose resolved layout depends on the browser.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterator
from html.parser import HTMLParser
from typing import Callable

from css_property_scan import blank_comments_outside_strings, blank_css_strings, mask_css_data
from svg_scan import Scanner, first_wins

VIEWBOX_TOLERANCE = 2.0
# Width budget from references/style-guide.md: em per character by face; wide and
# full-width characters cost 1em.
SANS_ADVANCE = 0.60
MONO_ADVANCE = 0.62
WIDE_ADVANCE = 1.0
TEXT_FIT_PROPERTIES = ("font-size", "font-family", "text-anchor", "letter-spacing")
# Weight and style move real glyph widths, but the budget already averages over them.
TEXT_FIT_IGNORED = {"font-weight", "font-style"}
PAINT_PROPERTIES = frozenset({"fill", "stroke", "stroke-width", "fill-opacity", "stroke-opacity", "opacity"})
# Bidi, vertical and preserved-space text lays out in ways the left-to-right budget can't place.
TEXT_LAYOUT_PROPERTIES = ("direction", "unicode-bidi", "writing-mode", "white-space", "xml:space")
# Half a narrow glyph. The budget is an average that runs wide of Geist (about 0.52em
# sans, 0.60em mono drawn), so a smaller overshoot is budget error on a label that
# draws inside its box; a whole character past the edge is the real defect.
TEXT_FIT_TOLERANCE_EM = 0.3
SVG_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
SVG_NUMBER_RE = re.compile(SVG_NUMBER)
SVG_PLAIN_NUMBER_RE = re.compile(rf"^\s*{SVG_NUMBER}\s*$")
TRANSLATE_RE = re.compile(rf"^\s*translate\(\s*({SVG_NUMBER})(?:[\s,]+({SVG_NUMBER}))?\s*\)\s*$")
# Their children are not painted where they are declared, or use another coordinate system.
UNPAINTED_TAGS = {
    "defs",
    "symbol",
    "marker",
    "pattern",
    "clippath",
    "mask",
    "foreignobject",
    "title",
    "desc",
    "metadata",
    "svg",
}
# CSS that can move, hide or clip an element, so its painted position is not its attributes.
UNSTATIC_CSS_PROPERTIES = {
    "transform",
    "translate",
    "rotate",
    "scale",
    "display",
    "visibility",
    "content-visibility",
    "opacity",
    "x",
    "y",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "width",
    "height",
}
UNSTATIC_CSS_PREFIXES = ("animation", "offset", "clip", "mask")
CSS_KEYFRAMES_RE = re.compile(
    r"@(?:-[a-z]+-)?keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", re.IGNORECASE
)
CSS_RULE_RE = re.compile(r"([^{};]+)\{([^{}]*)\}")
CSS_PROPERTY_RE = re.compile(r"(?:^|;)\s*([\w-]+)\s*(:)[^;]*")
CSS_PARENS_RE = re.compile(r"\([^()]*\)")
CSS_COMBINATOR_RE = re.compile(r"\s*[>+~]\s*|\s+")
CSS_TAG_RE = re.compile(r"^[a-zA-Z][\w-]*")
CSS_CLASS_RE = re.compile(r"\.([\w-]+)")
CSS_ID_RE = re.compile(r"#([\w-]+)")
CSS_ATTRIBUTE_RE = re.compile(r"\[\s*([\w:-]+)")
CSS_ATTR_BODY_RE = re.compile(r"\[\s*([\w:-]+)[^\]]*\]")
GEOMETRY_ATTRS = {
    "rect": ("x", "y", "width", "height"),
    "line": ("x1", "y1", "x2", "y2"),
    "circle": ("cx", "cy", "r"),
    "ellipse": ("cx", "cy", "rx", "ry"),
    "polygon": ("points",),
    "polyline": ("points",),
    "text": ("x", "y"),
}


class SvgExtent:
    def __init__(self, attrs: dict[str, str]) -> None:
        self.attrs = attrs
        self.points: list[tuple[float, float, str]] = []
        self.rects: list[tuple[float, float, float, float, int, int]] = []


def finite_number(value: str) -> float | None:
    if SVG_PLAIN_NUMBER_RE.fullmatch(value):
        parsed = float(value)
        if math.isfinite(parsed):
            return parsed
    return None


def svg_length(attrs: dict[str, str], name: str, default: float | None = None) -> float | None:
    value = attrs.get(name)
    return default if value is None else finite_number(value.strip().removesuffix("px"))


def viewport(attrs: dict[str, str]) -> tuple[float, float, float, float] | None:
    lengths = [finite_number(value) for value in re.split(r"[\s,]+", attrs.get("viewbox", "").strip())]
    if len(lengths) != 4:
        return None
    left, top, width, height = lengths
    if left is None or top is None or width is None or height is None or width <= 0 or height <= 0:
        return None
    return left, top, width, height


def painted_points(tag: str, attrs: dict[str, str]) -> list[tuple[float, float]]:
    if tag == "rect":
        x, y = svg_length(attrs, "x", 0.0), svg_length(attrs, "y", 0.0)
        width, height = svg_length(attrs, "width"), svg_length(attrs, "height")
        if x is None or y is None or width is None or height is None:
            return []
        if width <= 0 or height <= 0:
            return []
        return [(x, y), (x + width, y + height)]
    if tag == "line":
        ends = [
            (svg_length(attrs, "x1", 0.0), svg_length(attrs, "y1", 0.0)),
            (svg_length(attrs, "x2", 0.0), svg_length(attrs, "y2", 0.0)),
        ]
        return [(x, y) for x, y in ends if x is not None and y is not None]
    if tag in {"circle", "ellipse"}:
        cx, cy = svg_length(attrs, "cx", 0.0), svg_length(attrs, "cy", 0.0)
        rx = svg_length(attrs, "r" if tag == "circle" else "rx")
        ry = svg_length(attrs, "r" if tag == "circle" else "ry")
        if cx is None or cy is None or rx is None or ry is None:
            return []
        if rx <= 0 or ry <= 0:
            return []
        return [(cx - rx, cy - ry), (cx + rx, cy + ry)]
    if tag in {"polygon", "polyline"}:
        numbers = [float(value) for value in SVG_NUMBER_RE.findall(attrs.get("points", ""))]
        if not all(map(math.isfinite, numbers)):
            return []
        return list(zip(numbers[0::2], numbers[1::2]))
    if tag == "text":
        x, y = svg_length(attrs, "x"), svg_length(attrs, "y")
        return [] if x is None or y is None else [(x, y)]
    return []


def css_declarations(css: str) -> Iterator[tuple[str, str]]:
    """Split ordinary declarations without interpreting data inside quoted values."""
    for match in CSS_PROPERTY_RE.finditer(mask_css_data(css)):
        # Preserve the original value, including quotes needed for font families.
        value = blank_comments_outside_strings(css[match.end(2):match.end()]).strip()
        yield match[1].casefold(), re.sub(r"\s*!important\s*$", "", value, flags=re.I)


def changes_static_layout(name: str) -> bool:
    return name in UNSTATIC_CSS_PROPERTIES or name.startswith(UNSTATIC_CSS_PREFIXES)


def selector_subjects(selector: str) -> list[tuple[str, set[str], set[str], set[str]]]:
    """Tag, classes, IDs and attribute names a selector's last compound requires."""
    subjects = []
    selector = CSS_ATTR_BODY_RE.sub(r"[\1]", blank_css_strings(selector))
    for alternative in CSS_PARENS_RE.sub("", selector).split(","):
        parts = [part for part in CSS_COMBINATOR_RE.split(alternative.strip()) if part]
        if not parts:
            continue
        compound = parts[-1].split("::", 1)[0]
        tag = CSS_TAG_RE.match(compound)
        subjects.append((
            tag.group(0).casefold() if tag else "",
            set(CSS_CLASS_RE.findall(compound)),
            set(CSS_ID_RE.findall(compound)),
            {name.casefold() for name in CSS_ATTRIBUTE_RE.findall(compound)},
        ))
    return subjects


def style_rules(source: str, styles: list[str] | None) -> list[tuple[str, set[str]]]:
    """Read static rule names, leaving out keyframes, comments and quoted strings."""
    if styles is None:
        styles = [css.body for css in Scanner(source, (), lambda _: None).styles]
    sheet = CSS_KEYFRAMES_RE.sub("", mask_css_data("\n".join(styles)))
    return [(selector, {name for name, _ in css_declarations(body)})
            for selector, body in CSS_RULE_RE.findall(sheet)]


def declaring_css_subjects(
    rules: list[tuple[str, set[str]]], declares: Callable[[str], bool]
) -> list[tuple[str, set[str], set[str], set[str]]]:
    """Selector subjects of stylesheet rules declaring a property that matters to a check.

    Matching keeps only the last compound and drops pseudo-classes, so it can match more
    elements than the browser does. That only skips checks; it never adds a finding.
    """
    subjects = []
    for selector, names in rules:
        if any(declares(name) for name in names):
            subjects.extend(selector_subjects(selector))
    return subjects


def matches_subject(
    tag: str, attrs: dict[str, str], subject: tuple[str, set[str], set[str], set[str]]
) -> bool:
    subject_tag, classes, ids, attribute_names = subject
    if subject_tag not in {"", "*", tag}:
        return False
    if not classes <= set(attrs.get("class", "").split()):
        return False
    if not ids <= {attrs.get("id", "")}:
        return False
    return attribute_names <= set(attrs)


def child_offset(
    tag: str,
    attrs: dict[str, str],
    parent: tuple[float, float] | None,
    css_subjects: list[tuple[str, set[str], set[str], set[str]]],
) -> tuple[float, float] | None:
    """Offset of an element in viewBox units, or None when its paint is not static."""
    if parent is None or tag in UNPAINTED_TAGS:
        return None
    if any(changes_static_layout(name) for name, _ in css_declarations(attrs.get("style", ""))):
        return None
    if "hidden" in attrs or zero_alpha(attrs.get("opacity", "1")):
        return None
    if attrs.get("display", "").strip().casefold() == "none":
        return None
    if attrs.get("visibility", "").strip().casefold() in {"hidden", "collapse"}:
        return None
    if attrs.get("clip-path", "none").strip().casefold() != "none":
        return None
    if attrs.get("mask", "none").strip().casefold() != "none":
        return None
    if any(matches_subject(tag, attrs, subject) for subject in css_subjects):
        return None
    transform = attrs.get("transform")
    if transform is None:
        return parent
    match = TRANSLATE_RE.match(transform)
    if match is None:
        return None
    dx, dy = finite_number(match[1]), finite_number(match[2] or "0")
    if dx is None or dy is None:
        return None
    return parent[0] + dx, parent[1] + dy


class ViewBoxParser(HTMLParser):
    def __init__(self, source: str, *, styles: list[str] | None = None, rectangles_only: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.svgs: list[SvgExtent] = []
        self._css_subjects = declaring_css_subjects(style_rules(source, styles), changes_static_layout)
        self._frames: list[tuple[str, tuple[float, float] | None]] = []
        self._rectangles_only = rectangles_only
        self.feed(source)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        data = first_wins(attrs)
        if not self._frames:
            if tag == "svg":
                self.svgs.append(SvgExtent(data))
                # The viewBox starts a new coordinate system. Layout rules for the root
                # viewport do not change local coordinates in that system.
                hidden = data.get("aria-hidden", "").casefold() == "true"
                self._frames.append((tag, None if hidden else (0.0, 0.0)))
            return
        offset = child_offset(tag, data, self._frames[-1][1], self._css_subjects)
        self._frames.append((tag, offset))
        if offset is None:
            return
        if self._rectangles_only:
            if tag == "rect" and (bounds := painted_points(tag, data)):
                (left, top), (right, bottom) = bounds
                line, column = self.getpos()
                self.svgs[-1].rects.append(
                    (left + offset[0], top + offset[1], right - left, bottom - top, line, column)
                )
            return
        label = " ".join(
            [f"<{tag}"]
            + [f'{name}="{data[name]}"' for name in GEOMETRY_ATTRS.get(tag, ()) if name in data]
        ) + ">"
        for x, y in painted_points(tag, data):
            self.svgs[-1].points.append((x + offset[0], y + offset[1], label))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        for index in range(len(self._frames) - 1, -1, -1):
            if self._frames[index][0] == tag:
                del self._frames[index:]
                return


def check_viewbox(source: str, errors: list[str], *, styles: list[str] | None = None) -> None:
    parser = ViewBoxParser(source, styles=styles)
    checkable = [
        svg for svg in parser.svgs if svg.attrs.get("aria-hidden", "").casefold() != "true"
    ]
    for number, svg in enumerate(checkable, 1):
        box = viewport(svg.attrs)
        if box is None:
            continue
        left, top, width, height = box
        worst: dict[str, tuple[float, str]] = {}
        for x, y, label in svg.points:
            for side, overshoot in (
                ("left", left - x),
                ("top", top - y),
                ("right", x - (left + width)),
                ("bottom", y - (top + height)),
            ):
                if overshoot > VIEWBOX_TOLERANCE and overshoot > worst.get(side, (0.0, ""))[0]:
                    worst[side] = (overshoot, label)
        for side, (overshoot, label) in worst.items():
            errors.append(
                f"svg {number}: {label} paints {overshoot:g}px past the viewBox {side} edge "
                "and is clipped; grow the viewBox or move the content inside it"
            )


def inline_paint(attrs: dict[str, str]) -> dict[str, str]:
    values = {name: attrs[name].strip().casefold() for name in PAINT_PROPERTIES if name in attrs}
    for name, value in css_declarations(attrs.get("style", "")):
        if name in PAINT_PROPERTIES:
            values[name] = value.strip().casefold()
    return values


def inline_text_style(attrs: dict[str, str]) -> dict[str, str]:
    values = {name: attrs[name] for name in TEXT_FIT_PROPERTIES if name in attrs}
    values.update({name: "" for name in TEXT_LAYOUT_PROPERTIES if name in attrs})
    for name, value in css_declarations(attrs.get("style", "")):
        if restyles_text_width(name):
            values[name] = value.strip() if name in TEXT_FIT_PROPERTIES else ""
    return values


def restyles_text_width(name: str) -> bool:
    if name in TEXT_FIT_IGNORED:
        return False
    return (
        name.startswith(("font", "letter-spacing", "word-spacing"))
        or name == "text-anchor"
        or name in TEXT_LAYOUT_PROPERTIES
    )


def zero_alpha(value: str) -> bool | None:
    """True for an opacity or colour that paints nothing; None when it can't be read."""
    value = value.strip().casefold()
    if value in {"none", "transparent"}:
        return True
    number = re.fullmatch(rf"({SVG_NUMBER})(%?)", value)
    if number:
        return float(number.group(1)) <= 0
    if re.fullmatch(r"#[0-9a-f]{4}|#[0-9a-f]{8}", value):
        return int(value[4] if len(value) == 5 else value[7:], 16) == 0
    function = re.fullmatch(r"(?:rgba?|hsla?)\((.*)\)", value)
    if function:
        parts = [part for part in re.split(r"[\s,/]+", function.group(1).strip()) if part]
        return zero_alpha(parts[3]) if len(parts) == 4 else False
    return False if value.startswith("#") or value.isalpha() else None


def text_advance(text: str, mono: bool) -> float:
    """Text advance in em under the style-guide width budget."""
    narrow = MONO_ADVANCE if mono else SANS_ADVANCE
    advance = 0.0
    for char in text:
        if unicodedata.category(char) in {"Mn", "Me"}:
            continue
        advance += WIDE_ADVANCE if unicodedata.east_asian_width(char) in {"W", "F"} else narrow
    return advance


def font_size_px(style: dict[str, str]) -> float | None:
    match = re.fullmatch(rf"\s*({SVG_NUMBER})\s*(?:px)?\s*", style.get("font-size", ""))
    return finite_number(match[1]) if match else None


def text_run_width(text: str, style: dict[str, str]) -> float | None:
    """Estimated width in px of one run, or None when its style cannot be read statically."""
    size = font_size_px(style)
    if size is None:
        return None
    spacing = style.get("letter-spacing", "normal").strip().casefold()
    spacing_match = re.fullmatch(rf"({SVG_NUMBER})\s*(em|px)?", spacing)
    if spacing == "normal":
        tracking = 0.0
    elif spacing_match is None:
        return None
    else:
        tracking = float(spacing_match.group(1)) * (size if spacing_match.group(2) == "em" else 1)
    glyphs = sum(1 for char in text if unicodedata.category(char) not in {"Mn", "Me"})
    mono = "mono" in style.get("font-family", "").casefold()
    return text_advance(text, mono) * size + tracking * glyphs


class TextFitParser(HTMLParser):
    """Collects static rects and text lines per top-level SVG, in paint order."""

    def __init__(self, source: str, styles: list[str] | None) -> None:
        super().__init__(convert_charrefs=True)
        self.svgs: list[dict[str, object]] = []
        rules = style_rules(source, styles)
        self._css_subjects = declaring_css_subjects(rules, changes_static_layout)
        self._text_subjects = declaring_css_subjects(rules, restyles_text_width)
        self._paint_subjects = declaring_css_subjects(rules, PAINT_PROPERTIES.__contains__)
        # (tag, offset, inherited text style, inherited paint); a style or paint is None
        # once a stylesheet rule can change it, since its value is then unknown here.
        self._frames: list[
            tuple[str, tuple[float, float] | None, dict[str, str] | None, dict[str, str] | None]
        ] = []
        self._text: dict[str, object] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        data = first_wins(attrs)
        if not self._frames:
            if tag == "svg":
                self.svgs.append({"attrs": data, "rects": [], "lines": [], "papers": set(), "viewport": viewport(data)})
                style, paint = self._inherit(tag, data, {}, {})
                self._frames.append((tag, (0.0, 0.0), style, paint))
            return
        _parent_tag, parent_offset, parent_style, parent_paint = self._frames[-1]
        offset = child_offset(tag, data, parent_offset, self._css_subjects)
        style, paint = self._inherit(tag, data, parent_style, parent_paint)
        self._frames.append((tag, offset, style, paint))
        svg = self.svgs[-1]
        if offset is None:
            if tag in {"text", "tspan"} and self._text is not None:
                self._text["static"] = False
            return
        if tag == "rect" and self._text is None:
            fill: str | None = None
            stroked = False
            if paint is not None:
                fill = paint.get("fill", "black")
                stroke = paint.get("stroke", "none")
                stroked = stroke not in {"none", "transparent"} and paint.get("stroke-width") != "0"
                faded = [
                    zero_alpha(value) for value in (
                        paint["opacity"], fill, paint.get("fill-opacity", "1"),
                        stroke, paint.get("stroke-opacity", "1"),
                    )
                ]
                if None in faded:
                    fill, stroked = None, False
                else:
                    if faded[0] or faded[1] or faded[2]:
                        fill = "none"
                    stroked = stroked and not (faded[0] or faded[3] or faded[4])
            points = painted_points(tag, data)
            paper = data.get("width", "").strip() == "100%" and data.get("height", "").strip() == "100%"
            if points:
                (x0, y0), (x1, y1) = points
                paper |= (x0 + offset[0], y0 + offset[1], x1 - x0, y1 - y0) == svg["viewport"]
            if paper and not stroked and fill is not None:
                papers = svg["papers"]
                assert isinstance(papers, set)
                papers.add(fill)
            if points and (fill not in {"none", "transparent"} or stroked):
                (x0, y0), (x1, y1) = points
                rects = svg["rects"]
                assert isinstance(rects, list)
                rects.append(
                    (x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1], fill, stroked)
                )
        elif tag == "text" and self._text is None:
            x, y = svg_length(data, "x"), svg_length(data, "y")
            shifted = any(name in data for name in ("dx", "dy", "rotate", "textlength"))
            self._text = {"static": x is not None and y is not None and not shifted, "lines": []}
            if x is not None and y is not None:
                self._start_line(x + offset[0], y + offset[1], style)
        elif tag == "tspan" and self._text is not None:
            if any(name in data for name in ("dx", "rotate", "textlength")):
                self._text["static"] = False
            x = svg_length(data, "x")
            lines = self._text["lines"]
            assert isinstance(lines, list)
            if "x" in data:
                if x is None:
                    self._text["static"] = False
                    return
                dy = svg_length(data, "dy", 0.0)
                y = svg_length(data, "y")
                previous_y = lines[-1]["y"] if lines else 0.0
                line_y = (y + offset[1]) if y is not None else previous_y + (dy or 0.0)
                self._start_line(x + offset[0], line_y, style)
            elif "y" in data or "dy" in data:
                self._text["static"] = False

    def _inherit(
        self,
        tag: str,
        data: dict[str, str],
        parent_style: dict[str, str] | None,
        parent_paint: dict[str, str] | None,
    ) -> tuple[dict[str, str] | None, dict[str, str] | None]:
        style: dict[str, str] | None = None
        if parent_style is not None and not any(
            matches_subject(tag, data, subject) for subject in self._text_subjects
        ):
            own = inline_text_style(data)
            style = None if "" in own.values() else {**parent_style, **own}
        paint: dict[str, str] | None = None
        if parent_paint is not None and not any(
            matches_subject(tag, data, subject) for subject in self._paint_subjects
        ):
            own = inline_paint(data)
            hidden = parent_paint.get("opacity") == "0" or zero_alpha(own.get("opacity", "1"))
            paint = {**parent_paint, **own, "opacity": "0" if hidden else "1"}
            if hidden is None:
                paint = None
        return style, paint

    def _start_line(self, x: float, y: float, style: dict[str, str] | None) -> None:
        assert self._text is not None
        lines = self._text["lines"]
        assert isinstance(lines, list)
        rects = self.svgs[-1]["rects"]
        assert isinstance(rects, list)
        anchor = (style or {}).get("text-anchor", "start").strip().casefold()
        lines.append({"x": x, "y": y, "anchor": anchor, "runs": [], "rects": len(rects)})

    def handle_data(self, data: str) -> None:
        if self._text is None or not self._frames:
            return
        lines = self._text["lines"]
        assert isinstance(lines, list)
        if not lines:
            return
        style = self._frames[-1][2]
        if style is None:
            self._text["static"] = False
            return
        lines[-1]["runs"].append((data, style))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        for index in range(len(self._frames) - 1, -1, -1):
            if self._frames[index][0] == tag:
                del self._frames[index:]
                break
        if tag == "text" and self._text is not None:
            if self._text["static"] and self.svgs:
                svg_lines = self.svgs[-1]["lines"]
                assert isinstance(svg_lines, list)
                svg_lines.extend(self._text["lines"])
            self._text = None


def rect_area(rect: tuple) -> float:
    return (rect[2] - rect[0]) * (rect[3] - rect[1])


def check_text_fit(source: str, errors: list[str], *, styles: list[str] | None = None) -> None:
    """Flag text whose budgeted width runs past the rect it sits in.

    A line's box is the smallest rect painted before it that contains the line's
    anchor point; a rect whose opacity, fill and stroke draw nothing is no box.
    Text with no such rect (a free label, a caption), text on a paper-coloured
    mask, bidi, vertical or space-preserving text, and text whose size, spacing,
    layout or position CSS can change are not checked.
    """
    parser = TextFitParser(source, styles)
    parser.feed(source)
    parser.close()
    checkable = [
        svg for svg in parser.svgs
        if isinstance(svg["attrs"], dict) and svg["attrs"].get("aria-hidden", "").casefold() != "true"
    ]
    for number, svg in enumerate(checkable, 1):
        rects, lines, papers = svg["rects"], svg["lines"], svg["papers"]
        assert isinstance(rects, list) and isinstance(lines, list) and isinstance(papers, set)
        for line in lines:
            runs = [(re.sub(r"\s+", " ", run), style) for run, style in line["runs"]]
            text = "".join(run for run, _style in runs)
            if not text.strip():
                continue
            runs[0] = (runs[0][0].lstrip(), runs[0][1])
            runs[-1] = (runs[-1][0].rstrip(), runs[-1][1])
            widths = [text_run_width(run, style) for run, style in runs]
            if any(width is None for width in widths):
                continue
            width = sum(widths)
            size = max(font_size_px(style) or 0.0 for _run, style in runs)
            x, y = line["x"], line["y"]
            behind = [
                rect for rect in rects[: line["rects"]]
                if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]
            ]
            # A paper-coloured mask has no visible edge to overflow; text past it shows
            # only where something crosses behind, which is a collision, not a fit problem.
            # Nodes paint such a mask under their tinted body, so it only decides when it
            # is strictly smaller than every visible rect around the anchor.
            visible = [
                rect for rect in behind
                if rect[5] or (rect[4] is not None and rect[4] not in papers)
            ]
            if not visible:
                continue
            box = min(visible, key=rect_area)
            if min(rect_area(rect) for rect in behind) < rect_area(box) or box[4] is None:
                continue
            left, right = box[0], box[2]
            anchor = line["anchor"]
            start = x - width / 2 if anchor == "middle" else x - width if anchor == "end" else x
            overshoot = max(left - start, start + width - right)
            if overshoot > TEXT_FIT_TOLERANCE_EM * size:
                errors.append(
                    f"svg {number}: text {text.strip()!r} at ({x:g}, {y:g}) is budgeted at "
                    f"{width:.0f}px and overflows its {right - left:g}px box by {overshoot:.0f}px; "
                    "widen the box or shorten the label (budget: 0.60em sans, 0.62em mono per char)"
                )
