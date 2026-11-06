#!/usr/bin/env python3
"""Export a Illustrate HTML file to standalone SVG and/or transparent PNG."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import animate_export  # noqa: E402

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
        help="Export <name>.animated.svg: steps and arrows animated with CSS inside the SVG (no script), for README images",
    )
    mode.add_argument("--gif", action="store_true", help="Export <name>.gif: the same animation as an animated GIF")
    parser.add_argument("--arrows", choices=animate_export.ARROW_STYLES, default="draw",
                        help="Arrow animation for --animated/--gif (default: draw)")
    parser.add_argument("--theme", choices=("light", "dark"), default="light",
                        help="Colour scheme the GIF is rendered in (default: light)")
    parser.add_argument("--fps", type=int, default=15, help="GIF frames per second (default: 15)")
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


STYLE_RE = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.IGNORECASE | re.DOTALL)
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
# A compound that stands for the page itself (the html/body ancestors or the diagram's own <svg>).
ROOT_COMPOUND_RE = re.compile(r"^(?:html|body|:root|svg)(?![\w-])", re.IGNORECASE)
# What a page-level rule may pass down to the figure: tokens and inherited text/paint properties, not layout.
INHERITED_RE = re.compile(
    r"^(?:--|color$|color-scheme$|font|letter-spacing$|word-spacing$|line-height$|text-|fill|stroke|paint-order$"
    r"|dominant-baseline$|shape-rendering$|-webkit-font-smoothing$)", re.IGNORECASE)
# The exporter owns motion: page animations and the page's motion runtime hooks stay behind.
MOTION_PROPERTY_RE = re.compile(r"^(?:animation|transition)", re.IGNORECASE)
BLOCK_AT_RULES = ("@media", "@supports", "@layer")


def split_top(text: str, separator: str) -> list[str]:
    """Split CSS text at `separator` outside quotes, parentheses and brackets."""
    parts, depth, quote, start = [], 0, "", 0
    for index, char in enumerate(text):
        if quote:
            quote = "" if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == separator and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def css_blocks(css: str) -> list[tuple[str, str]]:
    """Top-level (prelude, body) pairs; statement at-rules such as @import come back with body None."""
    blocks, index, length = [], 0, len(css)
    while index < length:
        brace, semicolon = css.find("{", index), css.find(";", index)
        if brace == -1:
            break
        if css[index:].lstrip().startswith("@") and semicolon != -1 and semicolon < brace:
            blocks.append((css[index:semicolon].strip(), None))
            index = semicolon + 1
            continue
        depth, end, quote = 0, brace, ""
        for end in range(brace, length):
            char = css[end]
            if quote:
                quote = "" if char == quote else quote
            elif char in "\"'":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    break
        blocks.append((css[index:brace].strip(), css[brace + 1 : end]))
        index = end + 1
    return blocks


def figure_rules(css: str) -> str:
    """The page CSS that styles the figure, rewritten for a standalone SVG document.

    html/body rules move to :root (the <svg> in its own file) keeping only tokens and inherited
    text and paint properties; @import, @font-face, @keyframes and motion runtime rules are dropped.
    """
    out = []
    for prelude, body in css_blocks(css):
        if body is None:
            continue
        lowered = prelude.lower()
        if lowered.startswith(BLOCK_AT_RULES):
            inner = figure_rules(body)
            if inner:
                out.append(f"{prelude}{{{inner}}}")
            continue
        if lowered.startswith("@"):
            continue
        declarations = [d for d in split_top(body, ";") if not MOTION_PROPERTY_RE.match(d.split(":", 1)[0].strip())]
        root, other = [], []
        for selector in split_top(prelude, ","):
            if "data-motion" in selector or "motion-ready" in selector:
                continue
            selector = re.sub(r"^(?:html|body)(?![\w-])", ":root", selector, flags=re.IGNORECASE)
            group = root if ROOT_COMPOUND_RE.match(selector) and not re.search(r"[\s>+~]", selector) else other
            if selector not in group:
                group.append(selector)
        inherited = [d for d in declarations if INHERITED_RE.match(d.split(":", 1)[0].strip())]
        if root and inherited:
            out.append(f"{','.join(root)}{{{';'.join(inherited)}}}")
        if other and declarations:
            out.append(f"{','.join(other)}{{{';'.join(declarations)}}}")
    return "".join(out)


def page_style(html: str, svg_span: tuple[int, int]) -> str:
    """The page's own <style> rules (outside the figure) as a <style> element for the standalone SVG.

    Shapes styled by page classes or custom properties otherwise fall back to the SVG default
    (black fill) once the figure leaves its page.
    """
    outside = html[: svg_span[0]] + html[svg_span[1] :]
    css = CSS_COMMENT_RE.sub("", "".join(STYLE_RE.findall(outside)))
    rules = figure_rules(css)
    if not rules:
        return ""
    rules = rules.replace("&", "&amp;").replace("<", "&lt;")
    return f'<style data-illustrate-export-page="true">{rules}</style>'


SVG_TAG_RE = re.compile(r"<(/?)svg\b[^>]*?(/?)>", re.IGNORECASE)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def figure_span(html: str) -> tuple[int, int]:
    """Start and end of the first top-level <svg>, nested <svg> icons included."""
    depth, start = 0, None
    for tag in SVG_TAG_RE.finditer(html):
        if tag.group(1):
            depth -= 1
            if depth == 0 and start is not None:
                return start, tag.end()
        elif not tag.group(2):
            if depth == 0:
                start = tag.start()
            depth += 1
    raise ExportError("No <svg> diagram found in the source HTML.")


def standalone_svg(html: str) -> str:
    span = figure_span(html)
    # HTML comments may hold "--", which XML forbids; an export has no use for them.
    svg = COMMENT_RE.sub("", html[span[0] : span[1]])
    figure_style = FONT_STYLE + page_style(html, span)
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
        svg = svg[: defs_match.end()] + figure_style + svg[defs_match.end() :]
    else:
        opening_match = OPENING_SVG_RE.match(svg)
        assert opening_match is not None
        svg = svg[: opening_match.end()] + f"<defs>{figure_style}</defs>" + svg[opening_match.end() :]
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


def animated_svg(html: str, arrows: str = "draw") -> str:
    """The standalone SVG plus the figure's reveal as scoped CSS: no script, no remote fonts.

    GitHub and other Markdown hosts render an SVG image in a sandbox that runs CSS animation but
    no script and no external fetches. Every step is revealed once, in data-step order, with the
    figure's own --motion-hold/--motion-step clock, only under prefers-reduced-motion:
    no-preference. The end state, and the reduced-motion state, is the complete static figure.
    The reveal animates opacity only: a CSS transform would override the elements' own transform
    attributes (axonometric and rotated parts) and move them.
    Decorative overlays depend on the HTML page's CSS and are left out.
    """
    return animated_figure(html, arrows)[0]


def animated_figure(html: str, arrows: str = "draw") -> tuple[str, int]:
    """(animated SVG text, intro length in ms): the step reveal plus the chosen arrow animation."""
    svg = standalone_svg(html).replace(FONT_STYLE, "")
    svg = DECORATIVE_RE.sub("", svg)
    if "data-motion-decorative" in svg:
        raise ExportError("A decorative motion overlay could not be removed; keep it on one element.")
    steps = sorted({int(step) for step in STEP_RE.findall(svg)}) if "data-motion-item" in svg else []
    hold, step = motion_ms(html, "hold", 720), motion_ms(html, "step", 480)
    reveal_ms = (len(steps) - 1) * hold + step if steps else 0
    if reveal_ms > MAX_TOTAL_MS:
        raise ExportError(f"The reveal takes {reveal_ms}ms; the motion budget is {MAX_TOTAL_MS}ms.")
    step_delay = {value: index * hold for index, value in enumerate(steps)}
    try:
        svg, arrow_css, arrows_ms = animate_export.animate_arrows(svg, html, arrows, step_delay)
    except ValueError as exc:
        raise ExportError(str(exc)) from exc
    if not steps and not arrow_css:
        raise ExportError(
            "Nothing to animate: no data-motion-item/data-step steps and no arrows with markers. Build "
            "the figure from assets/template-motion.html (references/animation.md) or draw marked connectors."
        )
    delays = "".join(f'[data-step="{value}"]{{animation-delay:{delay}ms}}' for value, delay in step_delay.items())
    reveal = (
        "@keyframes illustrate-reveal{from{opacity:0}to{opacity:1}}"
        "@media (prefers-reduced-motion: no-preference){"
        f"[data-motion-item]{{animation:illustrate-reveal {step}ms cubic-bezier(.2,.8,.2,1) backwards}}"
        f"{delays}}}"
    ) if steps else ""
    style = f'<style data-illustrate-animation="true">{reveal}{arrow_css}</style>'
    return insert_style(svg, style), max(reveal_ms, arrows_ms)


def insert_style(svg: str, style: str) -> str:
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
            animated_path.write_text(animated_svg(html, args.arrows), encoding="utf-8", newline="\n")
            outputs.append(animated_path)
        elif args.gif:
            if not 1 <= args.fps <= 30:
                raise ExportError("--fps must be between 1 and 30.")
            figure, intro_ms = animated_figure(html, args.arrows)
            total_ms, hold_ms = animate_export.timeline(args.arrows, intro_ms)
            gif_path = base.with_suffix(".gif")
            try:
                animate_export.render_gif(figure, gif_path, total_ms, hold_ms, args.fps, args.scale, args.theme)
            except RuntimeError as exc:
                raise ExportError(str(exc)) from exc
            outputs.append(gif_path)
        elif not args.png_only:
            svg_path = base.with_suffix(".svg")
            write_svg(html, svg_path)
            outputs.append(svg_path)
        if not (args.svg_only or args.animated or args.gif):
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
