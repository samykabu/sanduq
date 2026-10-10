#!/usr/bin/env python3
"""Export a Illustrate HTML file to standalone SVG and/or transparent PNG."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SVG_RE = re.compile(r"<svg\b[^>]*>.*?</svg>", re.IGNORECASE | re.DOTALL)
OPENING_SVG_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE | re.DOTALL)
DEFS_RE = re.compile(r"<defs\b[^>]*>", re.IGNORECASE | re.DOTALL)
FONT_STYLE = (
    "<style data-illustrate-export-fonts=\"true\">"
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Instrument+Serif:ital@0;1&amp;family=Geist:wght@400;500;600&amp;"
    "family=Geist+Mono:wght@400;500;600&amp;display=swap');"
    "</style>"
)


class ExportError(RuntimeError):
    """A user-actionable export error."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Illustrate HTML source")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--svg-only", action="store_true", help="Export only SVG")
    mode.add_argument("--png-only", action="store_true", help="Export only PNG")
    mode.add_argument(
        "--animated",
        action="store_true",
        help="Export <name>.animated.svg: the motion reveal as CSS inside the SVG (no script), for README images",
    )
    parser.add_argument("--scale", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--output", type=Path, help="Output base path; extension is appended")
    return parser.parse_args()


def output_base(source: Path, requested: Path | None) -> Path:
    base = requested if requested is not None else source.with_suffix("")
    if base.suffix.lower() in {".html", ".svg", ".png"}:
        return base.with_suffix("")
    return base


def read_source(source: Path) -> str:
    if not source.is_file():
        raise ExportError(f"Source HTML does not exist: {source}")
    if source.name.lower() == "index.html" and source.parent.name.lower() == "assets":
        raise ExportError("The gallery contains multiple diagrams; choose a specific example HTML file.")
    html = source.read_text(encoding="utf-8")
    if not SVG_RE.search(html):
        raise ExportError(f"No <svg> diagram found in: {source}")
    return html


TAG_RE = re.compile(r"<([a-zA-Z][\w:.-]*)((?:\s+[^\s=/>]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?)*)\s*(/?)>")
EMPTY_VALUE = '=""'
ATTRIBUTE_RE = re.compile(r"\s+([^\s=/>]+)(\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?")


def xml_attributes(svg: str) -> str:
    """HTML allows valueless attributes (`data-motion-item`); a standalone .svg is XML and needs a value."""
    def tag(match: re.Match) -> str:
        attributes = ATTRIBUTE_RE.sub(lambda a: " " + a.group(1) + (a.group(2) or EMPTY_VALUE), match.group(2))
        return f"<{match.group(1)}{attributes}{'/' if match.group(3) else ''}>"
    return TAG_RE.sub(tag, svg)


def standalone_svg(html: str) -> str:
    match = SVG_RE.search(html)
    if match is None:
        raise ExportError("No <svg> diagram found in the source HTML.")
    svg = match.group(0)
    opening_match = OPENING_SVG_RE.match(svg)
    if opening_match is None:
        raise ExportError("The first SVG has an invalid opening tag.")
    opening = opening_match.group(0)
    if not re.search(r"\bviewBox\s*=", opening, re.IGNORECASE):
        raise ExportError("The diagram SVG has no viewBox; refusing to guess export dimensions.")
    if not re.search(r"\bxmlns\s*=", opening, re.IGNORECASE):
        updated_opening = opening[:-1] + ' xmlns="http://www.w3.org/2000/svg">'
        svg = updated_opening + svg[len(opening) :]

    defs_match = DEFS_RE.search(svg)
    if defs_match:
        svg = svg[: defs_match.end()] + FONT_STYLE + svg[defs_match.end() :]
    else:
        opening_match = OPENING_SVG_RE.match(svg)
        assert opening_match is not None
        svg = svg[: opening_match.end()] + f"<defs>{FONT_STYLE}</defs>" + svg[opening_match.end() :]
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_attributes(svg) + "\n"


STEP_RE = re.compile(r"\bdata-step\s*=\s*\"(\d+)\"")
DECORATIVE_RE = re.compile(
    r"<(?P<tag>[a-zA-Z][\w:-]*)\b[^>]*\bdata-motion-decorative\b[^>]*?"
    r"(?:/>|>.*?</(?P=tag)\s*>)",
    re.DOTALL,
)
MOTION_MS_RE = r"--motion-{name}\s*:\s*(\d+)ms"
MAX_TOTAL_MS = 8000


def motion_ms(html: str, name: str, default: int) -> int:
    match = re.search(MOTION_MS_RE.format(name=name), html)
    return int(match.group(1)) if match else default


def animated_svg(html: str) -> str:
    """The standalone SVG plus the figure's reveal as scoped CSS: no script, no remote fonts.

    GitHub and other Markdown hosts render an SVG image in a sandbox that runs CSS animation but
    no script and no external fetches. Every step is revealed once, in data-step order, with the
    figure's own --motion-hold/--motion-step clock, only under prefers-reduced-motion:
    no-preference. The end state, and the reduced-motion state, is the complete static figure.
    The reveal animates opacity only: a CSS transform would override the elements' own transform
    attributes (axonometric and rotated parts) and move them.
    Decorative overlays depend on the HTML page's CSS and are left out.
    """
    svg = standalone_svg(html).replace(FONT_STYLE, "")
    svg = DECORATIVE_RE.sub("", svg)
    if "data-motion-decorative" in svg:
        raise ExportError("A decorative motion overlay could not be removed; keep it on one element.")
    steps = sorted({int(step) for step in STEP_RE.findall(svg)})
    if not steps or "data-motion-item" not in svg:
        raise ExportError(
            "No data-motion-item/data-step markup in the SVG; build the figure from "
            "assets/template-motion.html first (references/animation.md)."
        )
    hold, step = motion_ms(html, "hold", 720), motion_ms(html, "step", 480)
    total = (len(steps) - 1) * hold + step
    if total > MAX_TOTAL_MS:
        raise ExportError(f"The reveal takes {total}ms; the motion budget is {MAX_TOTAL_MS}ms.")
    delays = "".join(
        f'[data-step="{value}"]{{animation-delay:{index * hold}ms}}' for index, value in enumerate(steps)
    )
    style = (
        "<style data-illustrate-animation=\"true\">"
        "@keyframes illustrate-reveal{from{opacity:0}to{opacity:1}}"
        "@media (prefers-reduced-motion: no-preference){"
        f"[data-motion-item]{{animation:illustrate-reveal {step}ms cubic-bezier(.2,.8,.2,1) backwards}}"
        f"{delays}}}"
        "</style>"
    )
    defs_match = DEFS_RE.search(svg)
    if defs_match:
        return svg[: defs_match.end()] + style + svg[defs_match.end() :]
    opening_match = OPENING_SVG_RE.search(svg)
    assert opening_match is not None
    return svg[: opening_match.end()] + f"<defs>{style}</defs>" + svg[opening_match.end() :]


def write_svg(html: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(standalone_svg(html), encoding="utf-8", newline="\n")


def write_png(source: Path, destination: Path, scale: int) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ExportError(
            "Playwright isn't installed. To enable PNG export, run:\n"
            "pip install playwright\nplaywright install chromium"
        ) from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(device_scale_factor=scale)
            page.goto(source.resolve().as_uri())
            page.wait_for_load_state("networkidle")
            locator = page.locator("svg").first
            if locator.count() == 0:
                raise ExportError("No SVG diagram was found after rendering the source HTML.")
            # Release every clipping ancestor (local scroller, overflow:hidden chrome) so an SVG
            # wider than its frame (min-width = viewBox width) is captured whole.
            locator.evaluate(
                "el => { for (let a = el.parentElement; a; a = a.parentElement)"
                " a.style.setProperty('overflow', 'visible', 'important'); }"
            )
            locator.screenshot(path=str(destination), omit_background=True)
        finally:
            browser.close()


def main() -> int:
    args = parse_args()
    outputs: list[Path] = []
    try:
        source = args.source.resolve()
        html = read_source(source)
        base = output_base(source, args.output)
        if args.animated:
            animated_path = base.with_name(base.name + ".animated.svg")
            animated_path.parent.mkdir(parents=True, exist_ok=True)
            animated_path.write_text(animated_svg(html), encoding="utf-8", newline="\n")
            outputs.append(animated_path)
        elif not args.png_only:
            svg_path = base.with_suffix(".svg")
            write_svg(html, svg_path)
            outputs.append(svg_path)
        if not (args.svg_only or args.animated):
            png_path = base.with_suffix(".png")
            write_png(source, png_path, args.scale)
            outputs.append(png_path)
        for output in outputs:
            print(f"{output.resolve()} ({output.stat().st_size} bytes)")
        return 0
    except ExportError as exc:
        for output in outputs:
            if output.is_file():
                print(f"{output.resolve()} ({output.stat().st_size} bytes)")
        print(f"export error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
