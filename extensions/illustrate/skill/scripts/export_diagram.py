#!/usr/bin/env python3
"""Export a Illustrate HTML file to standalone SVG and/or transparent PNG."""

from __future__ import annotations

import argparse
import base64
import hashlib
import math
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import animate_bpmn  # noqa: E402
import animate_export  # noqa: E402
import svg_standalone as safe  # noqa: E402

SVG_RE = re.compile(r"<svg\b[^>]*>.*?</svg>", re.IGNORECASE | re.DOTALL)


DEFAULT_FONT_URL = (
    "https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&"
    "family=Geist+Mono:wght@400;500;600&display=swap"
)
GIF_SCALES = (1, 2, 3)
NETWORK_IDLE_TIMEOUT_MS = 15_000   # a stalled webfont request must not hang the PNG export
FALLBACK_SETTLE_MS = 4_000         # paint time after the stalled load is cancelled
FONTS_READY_TIMEOUT_MS = 5_000
STATIC_FRAME_TIMEOUT_MS = 5_000
PLAYWRIGHT_INSTALL = "pip install playwright\npython -m playwright install chromium"


class ExportError(RuntimeError):
    """A user-actionable export error."""


def font_style(urls: list[str]) -> str:
    """The <style> that loads the figure's web fonts: the page's own Google Fonts (its theme)."""
    imports = "".join(f"@import url('{url}');" for url in urls)
    return f'<style data-illustrate-export-fonts="true">{safe.escape_css_for_xml(imports)}</style>'


def png_scale(value: str) -> float:
    """--scale: a finite number from 1 to 4, fractions included (1.25 gives exact 1.25x pixels)."""
    try:
        scale = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid scale {value!r}: use a number from 1 to 4") from exc
    if not math.isfinite(scale) or not 1 <= scale <= 4:
        raise argparse.ArgumentTypeError(f"invalid scale {value!r}: use a number from 1 to 4")
    return scale


FONT_STYLE = font_style([DEFAULT_FONT_URL])  # the sample HTML default, when the page loads no Google Fonts


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
                        help="Arrow animation for non-BPMN --animated/--gif exports (default: draw)")
    parser.add_argument("--bpmn-route", metavar="NAME", help="Play a named BPMN route in --animated/--gif")
    parser.add_argument("--theme", choices=("light", "dark"), default="light",
                        help="Colour scheme the GIF is rendered in (default: light)")
    parser.add_argument("--fps", type=int, default=15, help="GIF frames per second (default: 15)")
    parser.add_argument("--scale", type=png_scale, default=2.0,
                        help="Pixel density: PNG 1 to 4, fractions allowed (1.25); GIF 1, 2 or 3 (default: 2)")
    parser.add_argument("--system-fonts", action="store_true",
                        help="Offline: no Google Fonts @import in the SVG and no remote requests while "
                             "rasterizing; text uses the installed faces in the theme's font stacks")
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
    try:
        html = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ExportError(f"Cannot read {source}: {exc}") from exc
    try:
        safe.figure_span(html)
    except ValueError:
        raise ExportError(f"No <svg> diagram found in: {source}") from None
    return html


def xml_attributes(svg: str) -> str:
    """HTML allows valueless (`data-motion-item`) and unquoted attributes; a standalone .svg is XML."""
    return safe.xmlify_attributes(svg)


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
    """Split CSS text at `separator` outside quotes, escapes, parentheses and brackets."""
    parts, depth, quote, start, index = [], 0, "", 0, 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
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
        index += 1
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def css_blocks(css: str) -> list[tuple[str, str | None]]:
    """Top-level (prelude, body) pairs; statement at-rules such as @import come back with body None.

    Braces and semicolons inside strings or after a backslash are literal; a stray closing brace
    between rules is skipped and an unclosed last block runs to the end, as browsers recover.
    """
    blocks: list[tuple[str, str | None]] = []
    start, opening, depth, quote, index = 0, -1, 0, "", 0
    while index < len(css):
        char = css[index]
        if char == "\\":
            index += 2
            continue
        if quote:
            quote = "" if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char == "{":
            if depth == 0:
                opening = index
            depth += 1
        elif char == "}":
            if depth == 0:
                start = index + 1
            else:
                depth -= 1
                if depth == 0:
                    blocks.append((css[start:opening].strip(), css[opening + 1 : index]))
                    start = index + 1
        elif char == ";" and depth == 0:
            if css[start:index].strip().startswith("@"):
                blocks.append((css[start:index].strip(), None))
            start = index + 1
        index += 1
    if depth:
        blocks.append((css[start:opening].strip(), css[opening + 1 :]))
    return blocks


SELECTOR_TOKENS = re.compile(
    r"""\\[\s\S]|"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'|[\[\]()]"""
    r"""|::|:(?:before|after|first-line|first-letter|root)(?![\w-])""",
    re.IGNORECASE,
)


def scope_selector(selector: str, root: str) -> str:
    """Constrain a selector's subject to this SVG, without adding specificity."""
    if selector.lower() == ":root":
        return root
    guard = f":where({root},{root} *)"
    parts: list[str] = []
    start = brackets = parentheses = 0
    for match in SELECTOR_TOKENS.finditer(selector):
        token = match[0].lower()
        if token == "[":
            brackets += 1
        elif token == "]":
            brackets -= 1
        elif token == "(":
            parentheses += 1
        elif token == ")":
            parentheses -= 1
        elif token == ":root" and not brackets:
            parts.extend((selector[start:match.start()], root))
            start = match.end()
        elif token.startswith(":") and not brackets and not parentheses:
            # Pseudo-elements follow the guard, which matches their originating element.
            parts.extend((selector[start:match.start()], guard, selector[match.start():]))
            return "".join(parts)
    return "".join((*parts, selector[start:], guard))


def figure_rules(css: str, scope: str | None = None) -> str:
    """The page CSS that styles the figure, rewritten for a standalone SVG document.

    html/body rules keep only tokens and inherited text and paint properties. Ignore @import,
    @font-face, @keyframes and runtime motion rules. When scoped, constrain ordinary rules to
    the exported SVG so it can share a document with other themed figures.
    """
    out = []
    for prelude, body in css_blocks(css):
        if body is None:
            continue
        lowered = prelude.lower()
        if lowered.startswith(BLOCK_AT_RULES):
            inner = figure_rules(body, scope)
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
        if scope is not None:
            root = [scope_selector(selector, scope) for selector in root]
            other = [scope_selector(selector, scope) for selector in other]
        if root and inherited:
            out.append(f"{','.join(root)}{{{';'.join(inherited)}}}")
        if other and declarations:
            out.append(f"{','.join(other)}{{{';'.join(declarations)}}}")
    return "".join(out)


def page_style(html: str, svg_span: tuple[int, int], scope: str | None = None) -> str:
    """The page's own live <style> rules (outside the figure) as a <style> element for the standalone SVG.

    Shapes styled by page classes or custom properties otherwise fall back to the SVG default
    (black fill) once the figure leaves its page. Commented-out styles and style text inside
    <script> or <textarea> are not live and stay behind; CSS comments go, quoted text stays.
    """
    rules = figure_rules(safe.strip_css_comments(safe.page_css(html, svg_span)), scope)
    if not rules:
        return ""
    return f'<style data-illustrate-export-page="true">{safe.escape_css_for_xml(rules)}</style>'


def figure_span(html: str) -> tuple[int, int]:
    """Start and end of the first live top-level <svg>, nested <svg> icons included."""
    try:
        return safe.figure_span(html)
    except ValueError as exc:
        raise ExportError(str(exc)) from None


def standalone_svg(html: str, source: Path | None = None, system_fonts: bool = False) -> str:
    """The figure as a standalone SVG document.

    `source` names the file the defs-ID prefix is derived from (unique per exported figure);
    `system_fonts` leaves out the Google Fonts @import (offline use, and the animated export).
    Use the authored theme's font-loading policy. Unthemed sources without an explicit font
    import get the sample default.
    """
    span = figure_span(html)
    try:
        svg = safe.remove_comments(html[span[0] : span[1]])
        svg = safe.normalize_html_entities(safe.xmlify_attributes(svg))
        safe.ensure_viewbox(svg)
        svg = safe.ensure_namespaces(svg)
        offline = system_fonts or safe.theme_font_loading(html) in {"local", "system"}
        fonts = "" if offline else font_style(safe.google_fonts_urls(html, span) or [DEFAULT_FONT_URL])
        styles = page_style(html, span)
        svg = safe.insert_into_defs(svg, fonts + styles)
        prefix = safe.slug_for(source, svg)
        svg = safe.normalize_rgba_paint(svg)
        if styles:
            # Analyze the original selectors for PowerPoint paint before adding the scope.
            # Include the HTML rather than just the SVG or basename: styles can differ even
            # when those are the same, and in-memory callers may supply no filename at all.
            key = hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]
            scope = f'[data-illustrate-export="{key}"]'
            svg = safe.set_export_scope(svg.replace(styles, page_style(html, span, scope), 1), key)
        svg = safe.namespace_defs_ids(svg, prefix)
        document = '<?xml version="1.0" encoding="UTF-8"?>\n' + svg + "\n"
        safe.check_well_formed(document)
    except ValueError as exc:
        raise ExportError(str(exc)) from None
    return document


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


def animated_svg(html: str, arrows: str = "draw", source: Path | None = None, *,
                 bpmn_route: str | None = None) -> str:
    """The standalone SVG with CSS motion, without script or remote fonts.

    GitHub and other Markdown hosts render an SVG image in a sandbox that runs CSS animation but
    no script and no external fetches. BPMN figures loop one start-to-end route with a static hold.
    In other figures, every step is revealed once, in data-step order, with the
    figure's own --motion-hold/--motion-step clock, only under prefers-reduced-motion:
    no-preference. The end state, and the reduced-motion state, is the complete static figure.
    The reveal animates opacity only: a CSS transform would override the elements' own transform
    attributes (axonometric and rotated parts) and move them.
    Decorative overlays depend on the HTML page's CSS and are left out.
    """
    return animated_figure(html, arrows, source, bpmn_route=bpmn_route)[0]


def _is_bpmn_svg(standalone: str) -> bool:
    _, attrs = safe.root_attributes(standalone.partition("\n")[2])
    return safe.decode_xml_references(attrs.get("data-diagram") or "") == "bpmn"


def animated_figure(html: str, arrows: str = "draw", source: Path | None = None, *,
                    bpmn_route: str | None = None) -> tuple[str, int]:
    """Return the animated SVG and intro length (full loop duration for BPMN), in ms."""
    svg = standalone_svg(html, source, system_fonts=True)
    if _is_bpmn_svg(svg):
        try:
            svg, css, duration = animate_bpmn.animate_route(svg, bpmn_route, MAX_TOTAL_MS)
        except ValueError as exc:
            raise ExportError(str(exc)) from exc
        style = f'<style data-illustrate-animation="true">{css}</style>'
        return insert_style(svg, style), duration
    if bpmn_route is not None:
        raise ExportError("--bpmn-route requires a BPMN diagram (data-diagram=\"bpmn\" on the SVG).")
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
    """Put a <style> first in the figure's <defs> (a new <defs> goes after the leading title/desc)."""
    head, sep, body = svg.partition("\n") if svg.startswith("<?xml") else ("", "", svg)
    return head + sep + safe.insert_into_defs(body, style)


def write_text(destination: Path, text: str) -> None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise ExportError(f"Cannot write {destination}: {exc}") from exc


def write_svg(html: str, destination: Path, source: Path | None = None, system_fonts: bool = False) -> None:
    write_text(destination, standalone_svg(html, source, system_fonts))


# Fix the capture size to one CSS pixel per viewBox unit, so the PNG is exactly viewBox x scale.
EXACT_SIZE_JS = """el => {
    const box = el.viewBox && el.viewBox.baseVal;
    if (!box || ![box.width, box.height].every(n => Number.isFinite(n) && n > 0))
        throw new Error('PNG export needs a viewBox with a finite, positive width and height');
    for (const [axis, size] of [['width', box.width], ['height', box.height]])
        for (const prefix of ['', 'min-', 'max-'])
            el.style.setProperty(prefix + axis, size + 'px', 'important');
    // Snap the figure onto the device-pixel grid (a sub-pixel nudge in place, so what is behind it
    // stays the same); a fractional offset would round the capture one pixel larger.
    const k = window.devicePixelRatio, r = el.getBoundingClientRect();
    const snap = v => (Math.round(v * k) - v * k) / k;
    el.style.setProperty('translate', `${snap(r.left + scrollX)}px ${snap(r.top + scrollY)}px`, 'important');
    return [box.width, box.height];
}"""
# Release every clipping ancestor (local scroller, overflow:hidden chrome) so a wide SVG is whole.
RELEASE_OVERFLOW_JS = (
    "el => { for (let a = el.parentElement; a; a = a.parentElement)"
    " a.style.setProperty('overflow', 'visible', 'important'); }"
)
STATIC_FRAME_JS = "[...document.querySelectorAll('[data-motion-root]')].every(r => r.dataset.frame === 'static')"


def capture_exact_png(page, locator, scale: float, size: tuple[int, int]) -> bytes:
    png = locator.screenshot(omit_background=True)
    if struct.unpack_from(">II", png, 16) == size:
        return png

    # Locator screenshots enclose subpixel element bounds in whole CSS pixels
    # before scaling. Clip directly in page coordinates if that adds pixels.
    origin = locator.evaluate("""el => {
        const bounds = el.getBoundingClientRect();
        return {x: bounds.x + window.scrollX, y: bounds.y + window.scrollY};
    }""")
    session = page.context.new_cdp_session(page)
    try:
        session.send("Emulation.setDefaultBackgroundColorOverride", {
            "color": {"r": 0, "g": 0, "b": 0, "a": 0},
        })
        result = session.send("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": True,
            "clip": {**origin, "width": size[0] / scale, "height": size[1] / scale, "scale": scale},
        })
    finally:
        session.detach()
    png = base64.b64decode(result["data"])
    if struct.unpack_from(">II", png, 16) != size:
        raise ExportError(f"PNG capture did not produce the requested {size[0]} × {size[1]} pixels.")
    return png


def write_png(source: Path, destination: Path, scale: float, *, system_fonts: bool = False,
              network_idle_timeout_ms: int = NETWORK_IDLE_TIMEOUT_MS,
              fallback_settle_ms: int = FALLBACK_SETTLE_MS) -> tuple[int, int]:
    """Rasterize the source HTML's figure: transparent, viewBox x scale pixels, complete static frame.

    Waits are bounded: a load that never goes network-idle (a stalled webfont behind a proxy) is
    cancelled with window.stop() and captured with fallback typography, with a warning on stderr;
    font readiness is awaited for at most FONTS_READY_TIMEOUT_MS. Motion figures load with
    ?motion=static under reduced motion and must reach data-frame="static". Returns the PNG size.
    """
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ExportError("Playwright isn't installed. To enable PNG export, run:\n" + PLAYWRIGHT_INSTALL) from exc

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportError(f"Cannot write {destination}: {exc}") from exc
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(device_scale_factor=scale, reduced_motion="reduce")
                if system_fonts:
                    page.route(re.compile(r"^https?://"), lambda route: route.abort())
                page.goto(source.resolve().as_uri() + "?motion=static", wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=network_idle_timeout_ms)
                except PlaywrightTimeoutError:
                    page.evaluate("window.stop()")
                    page.wait_for_timeout(fallback_settle_ms)
                    print("warning: a webfont or stylesheet request stalled - captured with fallback "
                          "typography; the PNG may not match the intended fonts", file=sys.stderr)
                page.evaluate("ms => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, ms))])",
                              FONTS_READY_TIMEOUT_MS)
                try:
                    page.wait_for_function(STATIC_FRAME_JS, timeout=STATIC_FRAME_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    raise ExportError("The motion figure did not reach its complete static frame "
                                      '(data-frame="static"); check its motion runtime.') from None
                locator = page.locator("svg").first
                if locator.count() == 0:
                    raise ExportError("No SVG diagram was found after rendering the source HTML.")
                locator.evaluate(RELEASE_OVERFLOW_JS)
                width, height = locator.evaluate(EXACT_SIZE_JS)
                size = (round(width * scale), round(height * scale))
                if min(size) < 1:
                    raise ExportError("The scaled viewBox must be at least one pixel in each dimension.")
                png = capture_exact_png(page, locator, scale, size)
            finally:
                browser.close()
    except PlaywrightError as exc:
        text = str(exc).strip()
        message = text.splitlines()[0] if text else type(exc).__name__
        if "Executable doesn't exist" in text or "playwright install" in text:
            message = "Chromium for Playwright isn't installed. Run:\npython -m playwright install chromium"
        raise ExportError(f"PNG export failed: {message}") from None
    try:
        destination.write_bytes(png)
    except OSError as exc:
        raise ExportError(f"Cannot write {destination}: {exc}") from exc
    return size


def main() -> int:
    args = parse_args()
    outputs: list[Path] = []
    try:
        if args.bpmn_route is not None and not (args.animated or args.gif):
            raise ExportError("--bpmn-route requires --animated or --gif.")
        source = args.source.resolve()
        html = read_source(source)
        base = output_base(source, args.output)
        if args.animated:
            animated_path = base.with_name(base.name + ".animated.svg")
            write_text(animated_path, animated_svg(html, args.arrows, source, bpmn_route=args.bpmn_route))
            outputs.append(animated_path)
        elif args.gif:
            if not 1 <= args.fps <= 30:
                raise ExportError("--fps must be between 1 and 30.")
            if args.scale not in GIF_SCALES:
                raise ExportError(f"--gif renders at --scale 1, 2 or 3 (got {args.scale:g}).")
            figure, intro_ms = animated_figure(html, args.arrows, source, bpmn_route=args.bpmn_route)
            is_bpmn = _is_bpmn_svg(figure)
            total_ms, hold_ms = (intro_ms, 0) if is_bpmn else animate_export.timeline(args.arrows, intro_ms)
            gif_path = base.with_suffix(".gif")
            try:
                animate_export.render_gif(figure, gif_path, total_ms, hold_ms, args.fps, int(args.scale), args.theme,
                                          include_motion_colors=is_bpmn)
            except RuntimeError as exc:
                raise ExportError(str(exc)) from exc
            outputs.append(gif_path)
        elif not args.png_only:
            svg_path = base.with_suffix(".svg")
            write_svg(html, svg_path, source, args.system_fonts)
            outputs.append(svg_path)
        if not (args.svg_only or args.animated or args.gif):
            png_path = base.with_suffix(".png")
            write_png(source, png_path, args.scale, system_fonts=args.system_fonts)
            outputs.append(png_path)
        for output in outputs:
            print(f"{output.resolve()} ({output.stat().st_size} bytes)")
        return 0
    except ExportError as exc:
        written = [output for output in outputs if output.is_file()]
        for output in written:
            print(f"{output.resolve()} ({output.stat().st_size} bytes)")
        print(f"export error: {exc}", file=sys.stderr)
        if written:
            print("The files listed above were written; only the failed format is missing.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
