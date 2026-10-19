#!/usr/bin/env python3
"""Self-check a generated diagram HTML file, with no third-party deps.

Ships inside the skill so an installed agent can verify its own output:

    python <skill-dir>/scripts/self_check.py my-diagram.html

Checks the accessible-SVG contract, the single-file safety rules (no remote
assets beyond the approved Google Fonts stylesheet, no executable attributes,
no scripts other than the one canonical motion controller), and — when motion
markup is present — the structural motion contract, plus straight arrow
ends (`verify-arrow-ends.py`, shipped beside this script). This is a distilled
subset of the repository gates (`lint-skin.py`, `verify-motion.py`), which
remain the authority for contributions to the repository itself.

`--strict` adds the mechanical half of the taste gate (references/taste-gate.md):
accent on at most two node-sized shapes, the legend strip below every node and
inside the viewBox, the svg `min-width` equal to the viewBox width, no
`writing-mode`, no `box-shadow`, `rx` at most 10 (full pills excepted), node and
zone rects on the 4px grid (`.5` stroke offsets and data-bound `data-*` rects
excepted), the font role per element class (the terminal variant excepted), no
pure black, and orthogonal connectors (`verify-geometry.py --orthogonal`).
`lint-skin.py` imports the skin checks (pure black, scripts, external assets)
from here. Without `--strict` the run is unchanged.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

SKILL_DIR = Path(__file__).resolve().parent.parent
MOTION_TEMPLATE = SKILL_DIR / "assets" / "template-motion.html"
THEME_REGISTRY = SKILL_DIR / "assets" / "illustration-themes.yml"
MODES = {"none", "reveal", "step", "loop"}
ACTIONS = {"play", "pause", "replay", "prev", "next"}
ASCII_DECIMAL_RE = re.compile(r"^[0-9]+$")
CSS_ESCAPE_RE = re.compile(
    r"\\(?:([0-9a-fA-F]{1,6})[ \t\r\n\f]?|(.))", re.DOTALL
)
CSS_IMPORT_RE = re.compile(r"@import\b", re.IGNORECASE)
CSS_URL_RE = re.compile(r"url\(\s*([^)]+?)\s*\)", re.IGNORECASE)
CSS_IMAGE_SET_RE = re.compile(r"(?:-webkit-)?image-set\s*\(", re.IGNORECASE)
CSS_REMOTE_RE = re.compile(r"(?:https?:)?//", re.IGNORECASE)
CSS_REFERENCE_ATTRS = {
    "style",
    "fill",
    "stroke",
    "filter",
    "clip-path",
    "mask",
    "marker",
    "marker-start",
    "marker-mid",
    "marker-end",
    "cursor",
}
REFERENCE_ATTRS = {
    "src",
    "href",
    "xlink:href",
    "poster",
    "srcset",
    "action",
    "formaction",
}


class DiagramParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.roots: list[dict[str, str]] = []
        self.items: list[dict[str, str]] = []
        self.actions: set[str] = set()
        self.controls = 0
        self.statuses: list[dict[str, str]] = []
        self.statuses_in_controls = 0
        self.scripts: list[dict[str, object]] = []
        self.styles: list[str] = []
        self.css_attributes: list[str] = []
        self.svgs: list[dict[str, object]] = []
        self.unsafe: list[str] = []
        self.references: list[tuple[str, str, str]] = []
        self._svg_depth = 0
        self._current_svg: dict[str, object] | None = None
        self._capture: str | None = None
        self._current_script: dict[str, object] | None = None
        self._in_style = False
        self._element_stack: list[str] = []
        self._motion_root_depth: int | None = None
        self._controls_depth: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        normalized_attrs = [(key.casefold(), value or "") for key, value in attrs]
        data: dict[str, str] = {}
        for key, value in normalized_attrs:
            data.setdefault(key, value)
        if tag in {"base", "embed", "object", "iframe"}:
            self.unsafe.append(f"<{tag}> is not allowed in a diagram file")
        for key, value in normalized_attrs:
            if key.startswith("on"):
                self.unsafe.append(f"executable attribute {key} on <{tag}>")
            if key == "srcdoc":
                self.unsafe.append(f"srcdoc attribute on <{tag}>")
            if key in REFERENCE_ATTRS:
                self.references.append((tag, data.get("rel", ""), value))
            if key in CSS_REFERENCE_ATTRS:
                self.css_attributes.append(value)
        if "data-motion-root" in data:
            self.roots.append(data)
            if self._motion_root_depth is None:
                self._motion_root_depth = len(self._element_stack)
        if self._motion_root_depth is not None:
            if "data-motion-item" in data:
                self.items.append(data)
            if "data-motion-action" in data:
                self.actions.add(data["data-motion-action"])
            if "data-motion-controls" in data:
                self.controls += 1
                if self._controls_depth is None:
                    self._controls_depth = len(self._element_stack)
            if "data-motion-status" in data:
                self.statuses.append(data)
                if self._controls_depth is not None:
                    self.statuses_in_controls += 1
        if tag == "script":
            self._current_script = {
                "attrs": data,
                "attr_names": [name for name, _value in normalized_attrs],
                "body": [],
                "closed": False,
            }
            self.scripts.append(self._current_script)
        if tag == "style":
            self._in_style = True
        self._element_stack.append(tag)
        if tag == "svg" and self._svg_depth == 0:
            self._svg_depth = 1
            self._current_svg = {"attrs": data, "first": None, "title": {}, "desc": {}}
            self.svgs.append(self._current_svg)
            return
        if self._svg_depth:
            self._svg_depth += 1
            assert self._current_svg is not None
            if self._svg_depth == 2 and self._current_svg["first"] is None:
                self._current_svg["first"] = tag
            if self._svg_depth == 2 and tag in {"title", "desc"}:
                self._current_svg[tag] = {"attrs": data, "text": ""}
                self._capture = tag

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "script" and self._current_script is not None:
            self._current_script["closed"] = True
            self._current_script = None
        if tag == "style":
            self._in_style = False
        if self._svg_depth:
            if tag in {"title", "desc"}:
                self._capture = None
            self._svg_depth -= 1
            if self._svg_depth == 0:
                self._current_svg = None
        for index in range(len(self._element_stack) - 1, -1, -1):
            if self._element_stack[index] == tag:
                del self._element_stack[index:]
                break
        if (
            self._motion_root_depth is not None
            and len(self._element_stack) <= self._motion_root_depth
        ):
            self._motion_root_depth = None
        if (
            self._controls_depth is not None
            and len(self._element_stack) <= self._controls_depth
        ):
            self._controls_depth = None

    def handle_data(self, data: str) -> None:
        if self._current_script is not None:
            body = self._current_script["body"]
            assert isinstance(body, list)
            body.append(data)
        if self._in_style:
            self.styles.append(data)
        if self._capture and self._current_svg:
            node = self._current_svg[self._capture]
            assert isinstance(node, dict)
            node["text"] = str(node.get("text", "")) + data


def normalized_controller(body: str) -> str:
    return body.replace("\r\n", "\n").replace("\r", "\n").strip()


def parsed_document(source: str) -> DiagramParser:
    parser = DiagramParser()
    parser.feed(source)
    parser.close()
    return parser


def is_approved_google_fonts_stylesheet(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.casefold() == "fonts.googleapis.com"
        and parsed.port is None
        and parsed.path == "/css2"
        and not parsed.fragment
    )


def reference_error(tag: str, rel: str, value: str) -> str | None:
    stripped = value.strip()
    lowered = stripped.casefold()
    if not stripped or stripped.startswith("#"):
        return None
    if lowered.startswith("javascript:") or lowered.startswith("data:text/html"):
        return f"executable URL on <{tag}>: {stripped[:80]}"
    remote = lowered.startswith(("http://", "https://", "//")) or (
        ":" in stripped.split("/", 1)[0] and not lowered.startswith("data:")
    )
    if not remote:
        if lowered.startswith("data:") and not lowered.startswith("data:image/"):
            return f"non-image data URL on <{tag}>: {stripped[:80]}"
        return None
    if tag == "link" and "stylesheet" in rel.casefold().split():
        if is_approved_google_fonts_stylesheet(stripped):
            return None
        return f"remote stylesheet is not the approved Google Fonts /css2 URL: {stripped[:80]}"
    return f"remote reference on <{tag}>: {stripped[:80]}"


def normalize_css_escapes(source: str) -> str:
    source = source.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")

    def replace(match: re.Match[str]) -> str:
        if match.group(1) is None:
            escaped = match.group(2)
            return "" if escaped == "\n" else escaped
        codepoint = int(match.group(1), 16)
        if codepoint == 0 or codepoint > 0x10FFFF:
            return "\N{REPLACEMENT CHARACTER}"
        return chr(codepoint)

    return CSS_ESCAPE_RE.sub(replace, source)


def check_css_references(parser: DiagramParser, errors: list[str]) -> None:
    # Match the repository linter's fail-closed treatment of CSS loader syntax.
    source = normalize_css_escapes("\n".join(parser.styles + parser.css_attributes))
    found_loader = False
    if CSS_IMPORT_RE.search(source):
        errors.append("CSS @import is not allowed")
        found_loader = True
    for match in CSS_URL_RE.finditer(source):
        value = match.group(1).strip().strip("'\"").strip()
        if not value.startswith("#"):
            errors.append("non-fragment CSS url() is not allowed")
            found_loader = True
    if CSS_IMAGE_SET_RE.search(source):
        errors.append("CSS image-set() is not allowed")
        found_loader = True
    if CSS_REMOTE_RE.search(source) and not found_loader:
        errors.append("remote reference in CSS is not allowed")


def canonical_controller() -> str:
    if not MOTION_TEMPLATE.is_file():
        raise RuntimeError(
            f"cannot find the canonical controller at {MOTION_TEMPLATE}; "
            "run self_check.py from its shipped location inside the skill"
        )
    parser = parsed_document(MOTION_TEMPLATE.read_text(encoding="utf-8"))
    if len(parser.scripts) != 1 or not parser.scripts[0]["closed"]:
        raise RuntimeError("template-motion.html must contain one closed controller")
    body = parser.scripts[0]["body"]
    assert isinstance(body, list)
    return normalized_controller("".join(body))


def check_svgs(parser: DiagramParser, errors: list[str]) -> None:
    checkable = [
        svg
        for svg in parser.svgs
        if isinstance(svg["attrs"], dict)
        and str(svg["attrs"].get("aria-hidden", "")).casefold() != "true"
    ]
    if not checkable:
        errors.append("diagram file needs at least one accessible (non-aria-hidden) SVG")
    for number, svg in enumerate(checkable, 1):
        attrs = svg["attrs"]
        assert isinstance(attrs, dict)
        if attrs.get("role") != "img":
            errors.append(f"svg {number} needs role=img")
        labelled = attrs.get("aria-labelledby", "").split()
        title = svg["title"]
        desc = svg["desc"]
        assert isinstance(title, dict) and isinstance(desc, dict)
        title_attrs = title.get("attrs", {})
        desc_attrs = desc.get("attrs", {})
        assert isinstance(title_attrs, dict) and isinstance(desc_attrs, dict)
        if svg["first"] != "title":
            errors.append(f"svg {number} title must be its first child")
        if not str(title.get("text", "")).strip() or not str(desc.get("text", "")).strip():
            errors.append(f"svg {number} needs non-empty title and desc")
        title_id = title_attrs.get("id", "")
        desc_id = desc_attrs.get("id", "")
        if title_id in {"", "title"} or desc_id in {"", "desc"}:
            errors.append(f"svg {number} title/desc IDs must be diagram-prefixed, never bare")
        if labelled != [title_id, desc_id]:
            errors.append(f"svg {number} aria-labelledby must name title then desc")


def check_scripts(parser: DiagramParser, errors: list[str]) -> None:
    if not parser.scripts:
        return
    if len(parser.scripts) > 1:
        errors.append(f"at most one script is allowed; found {len(parser.scripts)}")
    for number, script in enumerate(parser.scripts, 1):
        attrs = script["attrs"]
        attr_names = script["attr_names"]
        body = script["body"]
        assert isinstance(attrs, dict) and isinstance(attr_names, list) and isinstance(body, list)
        if not script["closed"]:
            errors.append(f"script {number} must have a closing script tag")
        if attr_names != ["data-diagram-controls"] or attrs.get("data-diagram-controls") != "":
            errors.append(f"script {number} must carry only the canonical data-diagram-controls attribute")
            continue
        try:
            if normalized_controller("".join(body)) != canonical_controller():
                errors.append(f"script {number} must exactly match the controller in template-motion.html")
        except RuntimeError as exc:
            errors.append(str(exc))


def check_motion(parser: DiagramParser, source: str, errors: list[str]) -> None:
    has_motion_markup = bool(parser.roots or parser.items or parser.scripts)
    if not has_motion_markup:
        return
    if len(parser.roots) != 1:
        errors.append(f"expected exactly one data-motion-root; found {len(parser.roots)}")
        return
    root = parser.roots[0]
    mode = root.get("data-motion-mode", "")
    if mode not in MODES:
        errors.append(f"data-motion-mode must be one of {sorted(MODES)}; got {mode!r}")
    raw_count = root.get("data-step-count", "")
    if not ASCII_DECIMAL_RE.fullmatch(raw_count):
        count = -1
        errors.append("data-step-count must be an ASCII decimal integer")
    else:
        count = int(raw_count)
    minimum_count = 0 if mode == "none" else 1
    if count < minimum_count or count > 8:
        errors.append(f"semantic step count must be {minimum_count}..8; got {count}")

    if len(parser.items) > 12:
        errors.append(f"motion item budget is 12; found {len(parser.items)}")
    semantic_steps: list[int] = []
    for index, item in enumerate(parser.items, 1):
        raw_step = item.get("data-step", "")
        if not ASCII_DECIMAL_RE.fullmatch(raw_step):
            errors.append(f"motion item {index} has a non-ASCII-decimal data-step")
            continue
        step = int(raw_step)
        decorative = "data-motion-decorative" in item
        if not decorative:
            semantic_steps.append(step)
            if not item.get("aria-label", "").strip():
                errors.append(f"semantic motion item {index} needs a non-color aria-label")
        elif item.get("aria-hidden") != "true" or item.get("focusable") != "false":
            errors.append(f"decorative motion item {index} needs aria-hidden=true and focusable=false")
        inline = item.get("style", "").replace(" ", "").lower()
        if any(token in inline for token in ("display:none", "visibility:hidden", "opacity:0")):
            errors.append(f"motion item {index} is hidden in source; the fallback must be visible")

    expected = set(range(1, count + 1)) if count > 0 else set()
    if set(semantic_steps) != expected:
        errors.append(f"semantic steps must be contiguous 1..{count}; found {sorted(set(semantic_steps))}")
    crowded = {step: n for step, n in Counter(semantic_steps).items() if n > 2}
    if crowded:
        errors.append(f"no more than two semantic items may share a step; found {crowded}")

    if mode in {"none", "loop"} and parser.scripts:
        errors.append(f"{mode} mode must be script-free")
    if mode in {"none", "loop"} and (parser.controls or parser.actions or parser.statuses):
        errors.append(f"{mode} mode must not expose playback controls or live status")
    controlled = mode == "step" or (mode == "reveal" and bool(parser.scripts))
    if controlled:
        if parser.controls != 1:
            errors.append(f"controlled mode needs one in-root control group; found {parser.controls}")
        missing = ACTIONS - parser.actions
        if missing:
            errors.append(f"controlled mode is missing actions: {', '.join(sorted(missing))}")
        if not parser.statuses:
            errors.append("controlled mode needs data-motion-status")
        else:
            status = parser.statuses[0]
            if (
                status.get("role") != "status"
                or status.get("aria-live") != "polite"
                or status.get("aria-atomic") != "true"
            ):
                errors.append("motion status needs role=status, aria-live=polite, aria-atomic=true")
            if parser.statuses_in_controls:
                errors.append("motion status must sit outside data-motion-controls")
        if not parser.scripts:
            errors.append("controlled mode needs the scoped control script")

    style_source = "".join(parser.styles)
    if parser.scripts:
        if re.search(r"prefers-reduced-motion\s*:\s*reduce", style_source, re.IGNORECASE) is None:
            errors.append("missing reduced-motion CSS fallback (prefers-reduced-motion)")
        if re.search(r"@media\s+print\b", style_source, re.IGNORECASE) is None:
            errors.append("missing print CSS fallback (@media print)")
        if "<noscript" not in source.casefold():
            errors.append("motion file needs a <noscript> explanation of the complete static frame")


def _sibling(filename: str):
    """A verifier shipped beside this script, or the error line naming it."""
    script = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py").replace("-", "_"), script)
    if spec is None or spec.loader is None or not script.is_file():
        return f"cannot load {script.name}; run self_check.py from its shipped location inside the skill"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def arrow_end_errors(source: str) -> list[str]:
    module = _sibling("verify-arrow-ends.py")
    return [module] if isinstance(module, str) else module.check_source(source, "arrow")


def orthogonal_errors(source: str) -> list[str]:
    module = _sibling("verify-geometry.py")
    return [module] if isinstance(module, str) else module.orthogonal_findings(source, "connector")


# --- skin checks shared with lint-skin.py --------------------------------------

HEX_RE = re.compile(
    r"(?<![\w-])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
)
BLACK_RGB_RE = re.compile(r"rgb\(\s*0\s*,\s*0\s*,\s*0\s*\)", re.IGNORECASE)
SCRIPT_RE = re.compile(r"<script\b", re.IGNORECASE)
SRC_HTTP_RE = re.compile(r"\bsrc\s*=\s*(['\"])\s*https?://", re.IGNORECASE)
IMPORT_HTTP_RE = re.compile(r"@import\s+(?:url\(\s*)?(?:['\"]\s*)?https?://", re.IGNORECASE)
URL_HTTP_RE = re.compile(r"url\(\s*(?:['\"]\s*)?https?://", re.IGNORECASE)
LINK_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE | re.DOTALL)
HREF_RE = re.compile(r"\bhref\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)


def normalize_hex(value: str) -> str:
    value = value.lower()
    if len(value) == 4:
        return "#" + "".join(character * 2 for character in value[1:])
    return value


def canonical_motion_script(text: str) -> bool:
    """True when the file's only script is the pinned motion controller (template-motion.html)."""
    parser = parsed_document(text)
    errors: list[str] = []
    check_scripts(parser, errors)
    return len(parser.scripts) == 1 and not errors


def skin_findings(text: str) -> list[tuple[int, str, str]]:
    """(offset, category, message) for pure black, stray scripts and external HTTP(S) assets."""
    findings: list[tuple[int, str, str]] = []
    for match in HEX_RE.finditer(text):
        if normalize_hex(match.group()) == "#000000":
            findings.append((match.start(), "pure-black", f"pure black {match.group()} is not allowed"))
    for match in BLACK_RGB_RE.finditer(text):
        findings.append((match.start(), "pure-black", "pure black rgb(0,0,0) is not allowed"))
    if not canonical_motion_script(text):
        for match in SCRIPT_RE.finditer(text):
            findings.append((match.start(), "script", "<script> tags are not allowed (except the pinned motion controller)"))
    for match in SRC_HTTP_RE.finditer(text):
        findings.append((match.start(), "external-asset", "external HTTP(S) src is not allowed"))
    import_spans = []
    for match in IMPORT_HTTP_RE.finditer(text):
        import_spans.append(match.span())
        findings.append((match.start(), "external-asset", "external HTTP(S) @import is not allowed"))
    for match in URL_HTTP_RE.finditer(text):
        if any(start <= match.start() < end for start, end in import_spans):
            continue
        findings.append((match.start(), "external-asset", "external HTTP(S) url() is not allowed"))
    for link_match in LINK_RE.finditer(text):
        href_match = HREF_RE.search(link_match.group())
        if not href_match:
            continue
        href = href_match.group(2).strip()
        if href.lower().startswith("https://fonts.googleapis.com"):
            continue
        if href.lower().startswith(("http://", "https://")):
            findings.append((link_match.start() + href_match.start(2), "external-asset", "external HTTP(S) <link> is not allowed"))
    return findings


# --- strict: the mechanical taste-gate boxes -----------------------------------

SHAPES = {"rect", "circle", "ellipse", "path", "line", "polyline", "polygon"}
NODE_MIN_W, NODE_MIN_H = 60.0, 40.0  # the node heuristic verify-geometry.py uses
MAX_RADIUS = 10.0
NODE_MIN_RADIUS = 20.0
ACCENT_YML_RE = re.compile(r"^\s*accent:\s*['\"]?(#[0-9a-fA-F]{3,8})", re.MULTILINE)
ACCENT_VAR_RE = re.compile(r"--(?:color-)?accent\s*:\s*(#[0-9a-fA-F]{3,8})")
ACCENT_USE_RE = re.compile(r"var\(\s*--(?:color-)?accent\s*\)", re.IGNORECASE)
CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
CSS_FAMILY_RE = re.compile(r"(?:^|[;\s])font(?:-family)?\s*:\s*([^;}]+)", re.IGNORECASE)
CLASS_RE = re.compile(r"\.([\w-]+)")
MIN_WIDTH_RE = re.compile(r"min-width\s*:\s*([\d.]+)px", re.IGNORECASE)
TRANSLATE_RE = re.compile(r"translate\(\s*([-\d.]+)[\s,]*([-\d.]*)\s*\)")
NUMBER_RE = re.compile(r"^-?[\d.]+$")
FONT_ROLES = {"node-name": "sans", "sublabel": "mono", "arrow-label": "mono", "eyebrow": "mono", "callout": "serif"}


class StrictParser(HTMLParser):
    """Elements of the first accessible SVG with their line, defs ancestry and translate-y offset."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.svg_attrs: dict[str, str] | None = None
        self.elements: list[dict[str, object]] = []
        self.legend_at: int | None = None  # index into elements where the legend strip begins
        self.styles: list[str] = []
        self._stack: list[tuple[str, float, bool]] = []  # (tag, translate-y, aria-hidden or decorative)
        self._done = False
        self._in_style = False
        self._text_target: dict[str, object] | None = None

    def _start(self, tag: str, raw, closes: bool) -> None:
        tag = tag.casefold()
        attrs = {k.casefold(): (v or "") for k, v in raw}
        if tag == "style":
            self._in_style = True
        if self._done:
            return
        if self.svg_attrs is None:
            if tag == "svg" and attrs.get("aria-hidden", "").casefold() != "true":
                self.svg_attrs = attrs
                self._stack = [("svg", 0.0, False)]
            return
        ty = self._stack[-1][1] if self._stack else 0.0
        hidden = (self._stack[-1][2] if self._stack else False) or attrs.get("aria-hidden", "").casefold() == "true"
        hidden = hidden or "data-motion-decorative" in attrs
        match = TRANSLATE_RE.search(attrs.get("transform", ""))
        if match and match.group(2):
            ty += float(match.group(2))
        tags = [entry[0] for entry in self._stack]
        element: dict[str, object] = {
            "tag": tag, "attrs": attrs, "line": self.getpos()[0], "ty": ty,
            "in_defs": "defs" in tags or "marker" in tags, "hidden": hidden, "text": "",
        }
        self.elements.append(element)
        if tag == "text":
            self._text_target = element
        ident = (attrs.get("class", "") + " " + attrs.get("id", "")).casefold()
        if self.legend_at is None and "legend" in ident:
            self.legend_at = len(self.elements) - 1
        if not closes:
            self._stack.append((tag, ty, hidden))

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, True)

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if tag == "style":
            self._in_style = False
        if tag == "text":
            self._text_target = None
        if self.svg_attrs is None or self._done:
            return
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break
        if tag == "svg" and not self._stack:
            self._done = True

    def handle_comment(self, data):
        if self.svg_attrs is not None and not self._done and self.legend_at is None:
            if data.strip().casefold().startswith("legend"):
                self.legend_at = len(self.elements)

    def handle_data(self, data):
        if self._in_style:
            self.styles.append(data)
        if self._text_target is not None:
            self._text_target["text"] = str(self._text_target["text"]) + data
            if self.legend_at is None and data.strip().casefold() == "legend":
                self.legend_at = self.elements.index(self._text_target)


def _num(value: str) -> float | None:
    value = value.strip().removesuffix("px")
    return float(value) if NUMBER_RE.match(value) else None


def _rect(attrs: dict[str, str]) -> tuple[float, float, float, float] | None:
    values = [_num(attrs.get(key, "")) for key in ("x", "y", "width", "height")]
    if any(v is None for v in values):
        return None
    return values[0], values[1], values[2], values[3]  # type: ignore[return-value]


def family_kind(value: str) -> str | None:
    lowered = value.casefold().replace("sans-serif", "")
    if any(token in lowered for token in ("mono", "code")):
        return "mono"
    if "serif" in lowered:
        return "serif"
    if any(token in lowered for token in ("sans", "system-ui", "geist", "inter", "helvetica", "arial")):
        return "sans"
    return None


def class_families(styles: str) -> dict[str, str]:
    """CSS class -> font family kind, from every rule that sets font or font-family."""
    families: dict[str, str] = {}
    for selector, body in CSS_RULE_RE.findall(styles):
        match = CSS_FAMILY_RE.search(body)
        if not match:
            continue
        kind = family_kind(match.group(1))
        if kind:
            for name in CLASS_RE.findall(selector):
                families[name] = kind
    return families


def accent_literals(styles: str) -> set[str]:
    """Upstream default accents, every preset accent, and the file's own --accent variable."""
    literals = {"#eb6c36", "#f08a59"}
    if THEME_REGISTRY.is_file():
        literals.update(normalize_hex(m) for m in ACCENT_YML_RE.findall(THEME_REGISTRY.read_text(encoding="utf-8")))
    literals.update(normalize_hex(m) for m in ACCENT_VAR_RE.findall(styles))
    return literals


def _uses_accent(attrs: dict[str, str], literals: set[str], accent_classes: list[set[str]]) -> bool:
    paint = " ".join(attrs.get(key, "") for key in ("fill", "stroke", "style")).casefold()
    if ACCENT_USE_RE.search(paint):
        return True
    if any(normalize_hex(m) in literals for m in HEX_RE.findall(paint)):
        return True
    classes = set(attrs.get("class", "").split())
    return any(compound <= classes for compound in accent_classes)


WRITING_MODE_RE = re.compile(r"writing-mode\s*[:=]", re.IGNORECASE)
BOX_SHADOW_RE = re.compile(r"box-shadow\s*:(?!\s*none\b)", re.IGNORECASE)
TERMINAL_RE = re.compile(r"class\s*=\s*['\"][^'\"]*\bterminal\b", re.IGNORECASE)
SVG_SELECTOR_RE = re.compile(r"(?<![\w-])svg(?![\w-])", re.IGNORECASE)
GRID_EXEMPT_DATA = ("data-motion", "data-step")  # motion hooks are not data; any other data-* marks a data-bound rect


def _node_sized(element: dict[str, object]) -> bool:
    attrs = element["attrs"]
    assert isinstance(attrs, dict)
    if element["tag"] == "rect":
        box = _rect(attrs)
        return box is not None and box[2] >= NODE_MIN_W and box[3] >= NODE_MIN_H
    if element["tag"] in {"circle", "ellipse"}:
        radii = [_num(attrs.get(key, "")) for key in ("r", "rx", "ry")]
        return any(r is not None and r >= NODE_MIN_RADIUS for r in radii)
    return False


def strict_errors(source: str) -> list[str]:
    """The mechanical taste-gate boxes; each finding is one line naming the rule and the fix."""
    errors: list[str] = []
    for _offset, category, message in skin_findings(source):
        if category == "pure-black":  # scripts and external assets: the default run is already stricter
            errors.append(f"{category}: {message}")
    if WRITING_MODE_RE.search(source):
        errors.append("writing-mode is not allowed; stack separate <text> lines instead")
    if BOX_SHADOW_RE.search(source):
        errors.append("box-shadow is not allowed; use a 1px hairline border")

    parser = StrictParser()
    parser.feed(source)
    parser.close()
    if parser.svg_attrs is None:
        return errors
    styles = "\n".join(parser.styles)
    body = [e for e in parser.elements if not e["in_defs"] and not e["hidden"]]
    legend = parser.elements[parser.legend_at:] if parser.legend_at is not None else []
    legend_ids = {id(e) for e in legend}
    drawing = [e for e in body if id(e) not in legend_ids]

    view_box = [_num(v) for v in parser.svg_attrs.get("viewbox", "").replace(",", " ").split()]
    vb_w, vb_h = (view_box[2], view_box[3]) if len(view_box) == 4 and None not in view_box else (None, None)

    def rect_of(element: dict[str, object]) -> tuple[float, float, float, float] | None:
        attrs = element["attrs"]
        assert isinstance(attrs, dict)
        return _rect(attrs) if element["tag"] == "rect" else None

    def is_node(box: tuple[float, float, float, float] | None) -> bool:
        if box is None or box[2] < NODE_MIN_W or box[3] < NODE_MIN_H:
            return False
        return vb_w is None or vb_h is None or box[2] < vb_w or box[3] < vb_h  # the paper background is not a node

    # Accent on at most two node-sized shapes (rects of 60x40 or more, circles and ellipses of radius 20 or
    # more). Connectors (the headline path), series dots, chips, text, markers, legend swatches and
    # aria-hidden or decorative motion shapes do not count.
    literals = accent_literals(styles)
    accent_classes: list[set[str]] = []  # the class compound of each selector's last step, e.g. {station, focal}
    for selector, rule in CSS_RULE_RE.findall(styles):
        if ACCENT_USE_RE.search(rule) or any(normalize_hex(m) in literals for m in HEX_RE.findall(rule)):
            for part in selector.split(","):
                steps = part.split()
                compound = set(CLASS_RE.findall(steps[-1])) if steps else set()
                if compound:
                    accent_classes.append(compound)
    accented = [
        e for e in drawing
        if _node_sized(e) and _uses_accent(e["attrs"], literals, accent_classes)  # type: ignore[arg-type]
    ]
    if len(accented) > 2:
        lines = ", ".join(str(e["line"]) for e in accented[:6])
        errors.append(f"accent is used on {len(accented)} shapes (max 2); lines {lines}")

    # rx <= 10 on every rect (a full pill, rx >= height/2, is a terminator); node and zone rects on the
    # 4px grid, except .5 stroke offsets and data-bound rects (layout-budget.md lists both exceptions).
    for element in drawing:
        if element["tag"] != "rect":
            continue
        box = rect_of(element)
        attrs = element["attrs"]
        assert isinstance(attrs, dict)
        rx = _num(attrs.get("rx", "") or "0")
        if rx is not None and rx > MAX_RADIUS and (box is None or rx * 2 < box[3] - 0.5):
            errors.append(f"line {element['line']}: rx={rx:g} exceeds {MAX_RADIUS:g}")
        if not is_node(box) or any(k.startswith("data-") and not k.startswith(GRID_EXEMPT_DATA) for k in attrs):
            continue
        assert box is not None
        off = [f"{k}={v:g}" for k, v in zip("xywh", box) if v % 4 not in (0.0, 0.5)]
        if off:
            errors.append(f"line {element['line']}: rect off the 4px grid ({', '.join(off)})")

    # min-width on the svg equals the viewBox width; the legend strip sits below every node and inside the viewBox.
    if vb_w is not None:
        svg_css = [chunk for selector, chunk in CSS_RULE_RE.findall(styles) if SVG_SELECTOR_RE.search(selector)]
        svg_css.append(parser.svg_attrs.get("style", ""))
        widths = {float(w) for chunk in svg_css for w in MIN_WIDTH_RE.findall(chunk)}
        if not widths:
            errors.append(f"no min-width on the svg; set min-width: {vb_w:g}px")
        elif vb_w not in widths:
            shown = ", ".join(f"{w:g}" for w in sorted(widths))
            errors.append(f"svg min-width {shown}px does not equal the viewBox width {vb_w:g}")
    if legend:
        tops: list[float] = []
        bottoms: list[float] = []
        for element in legend:
            attrs = element["attrs"]
            assert isinstance(attrs, dict)
            ty = float(element["ty"])  # type: ignore[arg-type]
            for key in ("y", "y1", "y2", "cy"):
                value = _num(attrs.get(key, ""))
                if value is None:
                    continue
                extent = _num(attrs.get("height", "")) if key == "y" else _num(attrs.get("r", "")) if key == "cy" else None
                tops.append(value + ty)
                bottoms.append(value + ty + (extent or 0.0))
        node_bottom = max(
            (box[1] + box[3] + float(e["ty"]) for e in drawing for box in [rect_of(e)] if is_node(box)),  # type: ignore[arg-type]
            default=None,
        )
        if tops and node_bottom is not None and min(tops) < node_bottom:
            errors.append(
                f"legend starts at y={min(tops):g}, above the lowest node bottom y={node_bottom:g}; move it below every node"
            )
        if bottoms and vb_h is not None and max(bottoms) > vb_h:
            errors.append(f"legend reaches y={max(bottoms):g} but the viewBox height is {vb_h:g}; expand the viewBox")

    # Font role per element class (an inline font-family wins over the class rule); the terminal variant is mono by design.
    if TERMINAL_RE.search(source):
        return errors
    families = class_families(styles)
    for element in body:
        attrs = element["attrs"]
        assert isinstance(attrs, dict)
        if element["tag"] not in {"text", "tspan"}:
            continue
        classes = attrs.get("class", "").split()
        role_class = next((c for c in classes if c in FONT_ROLES), None)
        if role_class is None:
            continue
        inline = attrs.get("font-family", "")
        if not inline:
            match = CSS_FAMILY_RE.search(attrs.get("style", ""))
            inline = match.group(1) if match else ""
        kind = family_kind(inline) if inline else next((families[c] for c in classes if c in families), None)
        if kind and kind != FONT_ROLES[role_class]:
            errors.append(f"line {element['line']}: .{role_class} must use the {FONT_ROLES[role_class]} family, not {kind}")
    return errors


def verify(path: Path, strict: bool = False) -> list[str]:
    source = path.read_text(encoding="utf-8")
    parser = parsed_document(source)
    errors: list[str] = []
    errors.extend(parser.unsafe)
    check_css_references(parser, errors)
    for tag, rel, value in parser.references:
        finding = reference_error(tag, rel, value)
        if finding:
            errors.append(finding)
    check_svgs(parser, errors)
    check_scripts(parser, errors)
    check_motion(parser, source, errors)
    errors.extend(arrow_end_errors(source))
    if strict:
        errors.extend(strict_errors(source))
        errors.extend(orthogonal_errors(source))
    return errors


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("files", nargs="+", type=Path)
    argument_parser.add_argument(
        "--strict", action="store_true", help="also run the mechanical taste-gate checks (references/taste-gate.md)"
    )
    args = argument_parser.parse_args()
    failed = False
    for path in args.files:
        try:
            errors = verify(path, strict=args.strict)
        except (OSError, UnicodeError) as exc:
            errors = [str(exc)]
        if errors:
            failed = True
            print(f"FAIL {path}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"OK {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
