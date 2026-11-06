#!/usr/bin/env python3
"""Arrow animation for animated SVG export, and animated GIF rendering. Used by export_diagram.py.

Everything here is CSS inside the SVG (no script, no remote fetches), so the result plays where
Markdown shows SVG images. All motion sits under prefers-reduced-motion: no-preference; overlays
are invisible by default, so reduced motion shows the static figure. In the finishing styles the
real arrow (with its markers) reappears when its draw ends, so the last frame is the static figure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ARROW_STYLES = ("draw", "flow", "pulse", "draw-flow", "chevrons")
FINISHING = {"draw"}           # styles that end on the static figure
DRAW_MS = 600                  # one arrow's draw
LOOP_MS = 2400                 # pulse / chevron travel period
MARCH_MS = 1000                # dash flow period
DEFAULT_ACCENT = "#f97316"

TAG_RE = re.compile(r"<(/?)([a-zA-Z][\w:.-]*)((?:\s+[^\s=/>]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?)*)\s*(/?)>")
ATTR_RE = re.compile(r"([^\s=/>]+)\s*=\s*(\"[^\"]*\"|'[^']*')")
ARROW_TAGS = {"path", "line", "polyline"}


@dataclass
class Arrow:
    index: int
    start: int           # offset of the element's opening tag in the SVG text
    end: int             # offset just past the element (self-closing tag or closing tag)
    tag: str
    attrs: dict
    d: str
    forward: bool        # has marker-end
    backward: bool       # has marker-start
    step: int | None     # data-step of the nearest enclosing motion item, if any
    begin_ms: int = 0
    extras: list = field(default_factory=list)


def attributes(text: str) -> dict:
    return {name: value[1:-1] for name, value in ATTR_RE.findall(text)}


def geometry(tag: str, attrs: dict) -> str | None:
    if tag == "path":
        return attrs.get("d")
    if tag == "line":
        return f"M {attrs.get('x1', 0)} {attrs.get('y1', 0)} L {attrs.get('x2', 0)} {attrs.get('y2', 0)}"
    points = re.findall(r"-?\d*\.?\d+(?:e-?\d+)?", attrs.get("points", ""))
    pairs = [f"{points[i]} {points[i + 1]}" for i in range(0, len(points) - 1, 2)]
    return ("M " + " L ".join(pairs)) if len(pairs) >= 2 else None


def find_arrows(svg: str) -> list[Arrow]:
    """Elements carrying marker-end/marker-start, with the data-step of their enclosing motion item."""
    arrows, stack = [], []
    for match in TAG_RE.finditer(svg):
        closing, tag, raw, selfclosing = match.groups()
        if closing:
            while stack:
                if stack.pop()[0] == tag:
                    break
            continue
        attrs = attributes(raw)
        own_step = attrs.get("data-step") if "data-motion-item" in attrs else None
        if tag in ARROW_TAGS and ("marker-end" in attrs or "marker-start" in attrs):
            d = geometry(tag, attrs)
            if d:
                end = match.end()
                if not selfclosing:
                    close = svg.find(f"</{tag}>", end)
                    end = close + len(tag) + 3 if close != -1 else end
                enclosing = next((s for _, s in reversed(stack) if s is not None), None)
                step = int(own_step) if own_step else (int(enclosing) if enclosing else None)
                arrows.append(Arrow(len(arrows), match.start(), end, tag, attrs, d,
                                    "marker-end" in attrs and attrs["marker-end"] != "none",
                                    "marker-start" in attrs and attrs["marker-start"] != "none", step))
        if not selfclosing and tag not in ("br", "img", "meta", "link"):
            stack.append((tag, own_step))
    return [a for a in arrows if a.forward or a.backward]


def accent_color(html: str) -> str:
    match = re.search(r"--(?:accent|color-accent|accent-color)\s*:\s*(#[0-9a-fA-F]{3,8})", html)
    return match.group(1) if match else DEFAULT_ACCENT


def schedule(arrows: list[Arrow], step_delay: dict[int, int], budget_ms: int) -> int:
    """Set each arrow's begin time; return when the last draw ends."""
    loose = [a for a in arrows if a.step is None or a.step not in step_delay]
    gap = min(450, max(120, (budget_ms - DRAW_MS) // max(1, len(loose))))
    for order, arrow in enumerate(loose):
        arrow.begin_ms = order * gap
    for arrow in arrows:
        if arrow.step is not None and arrow.step in step_delay:
            arrow.begin_ms = step_delay[arrow.step]
    return max((a.begin_ms + DRAW_MS for a in arrows), default=0)


def overlay(arrow: Arrow, cls: str, unit_length: bool = True, **overrides: str) -> str:
    """A marker-free copy of the arrow's stroke for drawing effects (attribute overrides allowed)."""
    keep = {k: v for k, v in arrow.attrs.items()
            if k not in ("marker-end", "marker-start", "marker-mid", "id", "class", "data-motion-item", "data-step",
                         "pathLength", "aria-label", "role")}
    keep.update({k.replace("_", "-"): v for k, v in overrides.items()})
    rendered = " ".join(f'{k}="{v}"' for k, v in keep.items())
    length = ' pathLength="1"' if unit_length else ""
    return f'<{arrow.tag} {rendered} class="{cls}"{length} aria-hidden="true"/>'


def travellers(arrow: Arrow, cls: str, shape: str, count: int, accent: str) -> str:
    """Dots or chevrons riding the arrow's own path (offset-path) in its direction(s)."""
    transform = arrow.attrs.get("transform")
    path = arrow.d.replace("'", "")
    items = []
    directions = (["fwd"] if arrow.forward else []) + (["rev"] if arrow.backward else [])
    per = max(1, count // len(directions)) if len(directions) > 1 else count
    for direction in directions:
        for k in range(per):
            phase = -int(k * LOOP_MS / per)
            body = ('<circle r="4.5"' if shape == "dot" else '<polygon points="-6,-6 4,0 -6,6 -2,0"')
            items.append(f'{body} class="{cls} ia-{direction}" fill="{accent}" aria-hidden="true" '
                         f'style="offset-path:path(\'{path}\');animation-delay:{phase}ms"/>')
    group = "".join(items)
    return f'<g transform="{transform}">{group}</g>' if transform else group


def animate_arrows(svg: str, html: str, style: str, step_delay: dict[int, int], budget_ms: int = 4000) -> tuple[str, str, int]:
    """Return (svg with arrow overlays, CSS rules, intro end in ms)."""
    if style not in ARROW_STYLES:
        raise ValueError(f"Unknown arrow style {style!r}; choose one of {', '.join(ARROW_STYLES)}.")
    arrows = find_arrows(svg)
    if not arrows:
        return svg, "", 0
    intro = schedule(arrows, step_delay, budget_ms) if style in ("draw", "draw-flow") else 0
    accent = accent_color(html)
    css = []
    out, cursor = [], 0
    for arrow in arrows:
        a = f"ia-a{arrow.index}"
        element = svg[arrow.start:arrow.end]
        # Tag the real arrow so CSS can address it (keep any existing class).
        tagged = re.sub(r"^<(\w[\w:.-]*)", lambda m: f'<{m.group(1)} data-ia="{arrow.index}"', element, count=1)
        additions = ""
        if style in ("draw", "draw-flow"):
            if arrow.forward and arrow.backward:
                keyframes = "ia-draw-both"
            elif arrow.forward:
                keyframes = "ia-draw-fwd"
            else:
                keyframes = "ia-draw-rev"
            additions += overlay(arrow, f"ia-draw {a}")
            css.append(f".ia-draw.{a}{{animation:{keyframes} {DRAW_MS}ms ease-out {arrow.begin_ms}ms backwards}}"
                       f'[data-ia="{arrow.index}"]{{animation:ia-hidden {arrow.begin_ms + DRAW_MS}ms}}')
        if style == "draw-flow":
            width = float(re.match(r"[\d.]+", arrow.attrs.get("stroke-width", "1.5")).group() or 1.5)
            additions += overlay(arrow, f"ia-flow {a}", unit_length=False, stroke=accent, stroke_width=f"{width + 1:g}")
            direction = "normal" if arrow.forward else "reverse"
            alternate = " alternate" if arrow.forward and arrow.backward else ""
            css.append(f".ia-flow.{a}{{animation:ia-show 300ms {intro}ms both,"
                       f"ia-march {MARCH_MS * 2}ms linear {intro}ms infinite {direction}{alternate}}}")
        if style == "flow":
            direction = "reverse" if (arrow.backward and not arrow.forward) else "normal"
            alternate = " alternate" if arrow.forward and arrow.backward else ""
            css.append(f'[data-ia="{arrow.index}"]{{stroke-dasharray:10 7 !important;'
                       f"animation:ia-march-px {MARCH_MS}ms linear infinite {direction}{alternate}}}")
        if style in ("pulse", "chevrons"):
            additions += travellers(arrow, "ia-dot" if style == "pulse" else "ia-chev",
                                    "dot" if style == "pulse" else "chevron", 2 if style == "pulse" else 3, accent)
        out.append(svg[cursor:arrow.start] + tagged + additions)
        cursor = arrow.end
    out.append(svg[cursor:])
    base = (".ia-draw,.ia-flow{opacity:0;fill:none}.ia-flow{stroke-dasharray:3 14;stroke-linecap:round}"
            ".ia-dot,.ia-chev{display:none}")
    motion = "".join(css) + (
        ".ia-dot{display:inline;offset-rotate:0deg;animation:ia-travel %dms ease-in-out infinite}"
        ".ia-chev{display:inline;offset-rotate:auto;animation:ia-travel %dms linear infinite}"
        ".ia-rev{animation-direction:reverse}.ia-chev.ia-rev{offset-rotate:auto 180deg}" % (LOOP_MS, LOOP_MS))
    keyframes = (
        "@keyframes ia-draw-fwd{0%{opacity:1;stroke-dasharray:1 1;stroke-dashoffset:1}99.9%{opacity:1;stroke-dasharray:1 1;stroke-dashoffset:0}100%{opacity:0}}"
        "@keyframes ia-draw-rev{0%{opacity:1;stroke-dasharray:1 1;stroke-dashoffset:-1}99.9%{opacity:1;stroke-dasharray:1 1;stroke-dashoffset:0}100%{opacity:0}}"
        "@keyframes ia-draw-both{0%{opacity:1;stroke-dasharray:0 1;stroke-dashoffset:-.5}99.9%{opacity:1;stroke-dasharray:1 1;stroke-dashoffset:0}100%{opacity:0}}"
        "@keyframes ia-hidden{0%,100%{opacity:0}}"
        "@keyframes ia-show{from{opacity:0}to{opacity:.9}}"
        "@keyframes ia-march{to{stroke-dashoffset:-17}}"
        "@keyframes ia-march-px{to{stroke-dashoffset:-17}}"
        "@keyframes ia-travel{0%{offset-distance:0%;opacity:0}10%{opacity:1}90%{opacity:1}100%{offset-distance:100%;opacity:0}}")
    rules = base + keyframes + "@media (prefers-reduced-motion: no-preference){" + motion + "}"
    return "".join(out), rules, intro


def timeline(style: str, intro_ms: int) -> tuple[int, int]:
    """(capture length, final-frame hold) for a GIF of this arrow style."""
    if style == "draw":
        return intro_ms + 200, 2500
    if style == "draw-flow":
        return intro_ms + 2 * MARCH_MS * 2, 0
    period = LOOP_MS if style in ("pulse", "chevrons") else MARCH_MS
    return intro_ms + period, 0


def render_gif(svg_text: str, destination, total_ms: int, hold_ms: int, fps: int = 15, scale: int = 1,
               theme: str = "light") -> int:
    """Render svg_text frame by frame in Chromium (time set through the Web Animations API) into a GIF."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright isn't installed. Run: pip install playwright && playwright install chromium") from exc
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow isn't installed. Run: pip install pillow") from exc
    import io
    import tempfile
    from pathlib import Path

    frame_ms = max(20, round(1000 / fps))
    times = list(range(0, max(total_ms, frame_ms), frame_ms))
    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "figure.svg"
        path.write_text(svg_text, encoding="utf-8")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(color_scheme=theme, reduced_motion="no-preference", device_scale_factor=scale)
                page.goto(path.as_uri())
                size = page.evaluate("(() => { const s = document.documentElement; const b = s.viewBox.baseVal;"
                                     " return [Math.ceil(b.width || s.getBoundingClientRect().width),"
                                     " Math.ceil(b.height || s.getBoundingClientRect().height)]; })()")
                page.set_viewport_size({"width": size[0], "height": size[1]})
                page.evaluate("document.getAnimations().forEach(a => a.pause())")
                for t in times:
                    page.evaluate(f"document.getAnimations().forEach(a => {{ a.currentTime = {t}; }})")
                    frames.append(Image.open(io.BytesIO(page.screenshot())).convert("RGB"))
            finally:
                browser.close()
    # One palette for every frame (from the complete last frame) so colours do not flicker.
    shared = frames[-1].quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palette = [frame.quantize(palette=shared, dither=Image.Dither.NONE) for frame in frames]
    durations = [frame_ms] * len(palette)
    durations[-1] += hold_ms
    destination.parent.mkdir(parents=True, exist_ok=True)
    palette[0].save(destination, save_all=True, append_images=palette[1:], duration=durations, loop=0,
                    disposal=1, optimize=False)
    return len(palette)
