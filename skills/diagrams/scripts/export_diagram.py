#!/usr/bin/env python3
"""Export a Diagram Design HTML file to standalone SVG and/or transparent PNG."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SVG_RE = re.compile(r"<svg\b[^>]*>.*?</svg>", re.IGNORECASE | re.DOTALL)
OPENING_SVG_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE | re.DOTALL)
DEFS_RE = re.compile(r"<defs\b[^>]*>", re.IGNORECASE | re.DOTALL)
FONT_STYLE = (
    "<style data-diagram-design-export-fonts=\"true\">"
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Instrument+Serif:ital@0;1&amp;family=Geist:wght@400;500;600&amp;"
    "family=Geist+Mono:wght@400;500;600&amp;display=swap');"
    "</style>"
)


class ExportError(RuntimeError):
    """A user-actionable export error."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Diagram Design HTML source")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--svg-only", action="store_true", help="Export only SVG")
    mode.add_argument("--png-only", action="store_true", help="Export only PNG")
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
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + svg + "\n"


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
        if not args.png_only:
            svg_path = base.with_suffix(".svg")
            write_svg(html, svg_path)
            outputs.append(svg_path)
        if not args.svg_only:
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
