#!/usr/bin/env python3
"""Standalone-SVG safety helpers for export_diagram.py (stdlib only).

Turns the figure cut out of an Illustrate HTML page into an SVG document that parses as XML,
renders the same on its own, and can be inlined next to other exported figures:

- live markup only: the figure and the page styles are found with comments, CDATA, <script>,
  <style>, HTML text elements and inert templates read as opaque;
- XML syntax: valueless/unquoted HTML attributes get quoted values, HTML named and numeric
  character references become XML-safe text (``&#128;`` keeps its HTML meaning, the euro sign),
  CDATA is copied unchanged;
- the root: the SVG namespace is checked (and the xlink namespace declared when used), and the
  viewBox must be four finite numbers with a positive width and height;
- referenceable ``<defs>`` IDs are prefixed with a per-file slug, with every ``url(#id)`` (quoted,
  entity-quoted or CSS-escaped), ``href="#id"`` and ``#id`` selector retargeted, so several
  exported figures can share one host document;
- PowerPoint: ``rgba()``/``transparent`` presentation paint is split into hex paint plus opacity
  where the cascade allows it.

Adapted from diagram-design ``skills/diagram-design/scripts/export_svg.py`` at d74d8c2d
(Cathryn Lavery, MIT License; fixes #235, #348, #411, #414, #417, #423, #426, #432, #486).
Illustrate keeps its own page-style carry-over (ancestor rules move to ``:root``) and motion
handling in export_diagram.py; this module owns parsing and XML safety only.
"""

from __future__ import annotations

import hashlib
import html as html_entities
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Iterator

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

# Strings and escapes consume their comment-looking text before comments do.
CSS_COMMENT_OR_LITERAL_RE = re.compile(
    r'''"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'|\\[\s\S]|/\*.*?\*/''',
    re.DOTALL,
)
XML_OPAQUE_OPEN_RE = re.compile(r"<!--|<!\[CDATA\[")
START_TAG_RE = re.compile(
    r"<([A-Za-z][\w:.-]*)"
    r"((?:\s+[^\s\"'<>/=]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+))?)*)"
    r"(\s*/?)>"
)
TAG_ATTR_RE = re.compile(r"(\s+)([^\s\"'<>/=]+)(?:(\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+))?")
STYLE_BLOCK_RE = re.compile(r"<style\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>(.*?)</style\s*>", re.IGNORECASE | re.DOTALL)
# Opening and closing <svg> tags (quote-aware, not <svg-icon>), balanced so nested icons stay inside.
SVG_TAG_RE = re.compile(r"<svg(?=[\s/>])(?:[^>\"']|\"[^\"]*\"|'[^']*')*>|</svg\s*>", re.IGNORECASE)
# Every tag consumes its quoted attributes before it can change the parsing context.
HTML_TOKEN_RE = re.compile(
    r"<!--.*?(?:-->|$)|<!\[CDATA\[.*?(?:\]\]>|$)|"
    r"<(?P<close>/)?(?P<tag>[A-Za-z][^\s/>]*)"
    r"(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", re.IGNORECASE | re.DOTALL
)
CDATA_SECTION_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
COMMENT_OR_CDATA_RE = re.compile(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>", re.DOTALL)
# Alternatives start on different characters and a comment cannot run past its first "*/",
# so a failed match backtracks linearly.
CSS_RULE_ATOM = r'''(?:/\*(?:[^*]|\*(?!/))*\*/|\\[\s\S]|"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'|/(?!\*)|[^{}"'\\/])'''
RULE_RE = re.compile(rf"({CSS_RULE_ATOM}+)\{{({CSS_RULE_ATOM}*)\}}", re.DOTALL)
RGBA_ATTR_RE = re.compile(
    r'(fill|stroke)="rgba\(\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)"'
)
CSS_URL_ATTRIBUTES = {
    "fill", "stroke", "filter", "clip-path", "mask", "cursor", "marker",
    "marker-start", "marker-mid", "marker-end",
}
DEFS_ID_TAGS = {
    tag.lower() for tag in (
        "marker", "pattern", "linearGradient", "radialGradient", "filter", "clipPath", "mask", "symbol",
        "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "image", "use",
    )
}
GOOGLE_FONTS_URL_RE = re.compile(r"https://fonts\.googleapis\.com/css2\?[A-Za-z0-9+:;@,.&=%_~-]+")


def strip_css_comments(css: str) -> str:
    """Remove CSS comments while keeping quoted and escaped literals (``content:"/* x */"``)."""
    return CSS_COMMENT_OR_LITERAL_RE.sub(lambda token: "" if token.group(0).startswith("/*") else token.group(0), css)


def escape_css_for_xml(css: str) -> str:
    """CSS text as XML character data: ``&``, ``<`` and the ``]]>`` sequence escaped."""
    return css.replace("&", "&amp;").replace("<", "&lt;").replace("]]>", "]]&gt;")


def slug_for(path: Path | None, fallback: str = "") -> str:
    """Stable ID prefix from the source basename, or from the figure text when there is no file."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", path.stem).strip("-") if path is not None else ""
    if not slug:
        slug = "figure-" + hashlib.sha1(fallback.encode("utf-8")).hexdigest()[:8]
    return f"d-{slug}" if slug[0].isdigit() else slug


# ---------------------------------------------------------------- live markup


def html_tokens(source: str) -> Iterator[tuple[re.Match[str], bool, int, int]]:
    """Yield (token, inside-svg, text-body end, token end) for comments, CDATA and tags.

    <script>/<style> (and HTML text elements outside SVG) consume through their end tag without
    their contents being read as markup; SVG title/desc stay integration points. HTML template
    contents are inert, so skip a complete template, including nested ones, as one token.
    """
    contexts: list[str] = []
    template_start = None
    template_depth = 0
    template_contexts: list[str] = []
    pos = 0
    while token := HTML_TOKEN_RE.search(source, pos):
        name = (token.group("tag") or "").lower()
        in_svg = bool(contexts and contexts[-1] == "svg")
        body_end = end = token.end()
        self_closing = token.group(0).endswith("/>")
        text_element = name in {"script", "style"} or (
            not in_svg and name in {"textarea", "title", "xmp", "iframe", "noembed", "noframes", "noscript", "plaintext"}
        )
        if name and not token.group("close") and text_element and not (in_svg and self_closing):
            closing = None if name == "plaintext" else re.compile(
                r"</" + name + r"(?=[\s/>])(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", re.IGNORECASE).search(source, end)
            body_end = closing.start() if closing else len(source)
            end = closing.end() if closing else len(source)
        elif name in {"svg", "foreignobject", "desc", "title"}:
            if token.group("close"):
                for index in range(len(contexts) - 1, -1, -1):
                    if contexts[index] == name:
                        del contexts[index:]
                        break
            elif not self_closing and (name == "svg" or in_svg):
                contexts.append(name)
        if name == "template" and not in_svg:
            if not token.group("close"):
                if not template_depth:
                    template_start = token
                    template_contexts = contexts.copy()
                template_depth += 1
            elif template_depth:
                template_depth -= 1
                if not template_depth and template_start is not None:
                    contexts = template_contexts
                    yield template_start, False, token.start(), end
                    template_start = None
        elif not template_depth:
            yield token, in_svg, body_end, end
        pos = end
    if template_start is not None:
        yield template_start, False, len(source), len(source)


def mask_opaque_html(source: str) -> str:
    """Same-length copy with comments, CDATA, text-element bodies and attribute values blanked."""
    out: list[str] = []
    pos = 0
    for token, _, _, end in html_tokens(source):
        out.append(source[pos:token.start()])
        if not token.group("tag") or end > token.end():
            out.append(" " * (end - token.start()))
        else:
            suffix = "/>" if token.group(0).endswith("/>") else ">"
            attr_start = token.end("tag")
            out.append(source[token.start():attr_start])
            out.append(" " * (token.end() - len(suffix) - attr_start) + suffix)
        pos = end
    out.append(source[pos:])
    return "".join(out)


def figure_span(html: str) -> tuple[int, int]:
    """Start and end of the first live top-level <svg>, nested <svg> icons included."""
    start, depth = None, 0
    for tag in SVG_TAG_RE.finditer(mask_opaque_html(html)):
        if tag.group(0).startswith("</"):
            if start is None:
                continue
            depth -= 1
            if depth == 0:
                return start, tag.end()
        elif not tag.group(0).endswith("/>"):
            if start is None:
                start = tag.start()
            depth += 1
    raise ValueError("No <svg> diagram found in the source HTML.")


def remove_comments(svg: str) -> str:
    """Drop HTML comments (an export has no use for them; "--" inside one is not XML); keep CDATA.

    <!-->, <!---> and --!> end a comment in a browser before the next "-->", so the markup after
    them is live; dropping through "-->" would silently lose it, so those are refused.
    """
    out: list[str] = []
    pos = 0
    while (opener := XML_OPAQUE_OPEN_RE.search(svg, pos)) is not None:
        out.append(svg[pos:opener.start()])
        if opener.group(0) == "<!--":
            close_at = svg.find("-->", opener.end())
            body = svg[opener.end():] if close_at == -1 else svg[opener.end():close_at]
            if body.startswith((">", "->")) or "--!>" in body:
                raise ValueError("The figure has a comment a browser closes early (<!-->, <!---> or --!>); "
                                 "fix the comment in the source.")
            if close_at == -1:
                return "".join(out)
            pos = close_at + 3
        else:
            close_at = svg.find("]]>", opener.end())
            stop = len(svg) if close_at == -1 else close_at + 3
            out.append(svg[opener.start():stop])
            pos = stop
    out.append(svg[pos:])
    return "".join(out)


def page_css(html: str, span: tuple[int, int]) -> str:
    """The live <style> text of the page outside the figure; CDATA in SVG styles is unwrapped."""
    blocks = []
    for token, in_svg, body_end, _ in html_tokens(html):
        if (token.group("tag") or "").lower() != "style" or token.group("close"):
            continue
        if span[0] <= token.start() < span[1]:
            continue
        block = html[token.end():body_end]
        if in_svg:
            block = CDATA_SECTION_RE.sub(lambda match: match.group(1), block)
        blocks.append(block)
    return "\n".join(blocks)


def theme_font_loading(html: str) -> str | None:
    """The font-loading policy stamped on the live HTML by illustration_theme.py."""
    for token, _, _, _ in html_tokens(html):
        if (token.group("tag") or "").lower() != "meta" or token.group("close"):
            continue
        tag = START_TAG_RE.match(token.group(0))
        if tag is None:
            continue
        attrs: dict[str, str] = {}
        for attr in TAG_ATTR_RE.finditer(tag.group(2)):
            raw = attr.group(4) or ""
            value = raw[1:-1] if raw[:1] in ('"', "'") else raw
            attrs.setdefault(attr.group(2).lower(), html_entities.unescape(value))
        if attrs.get("name", "").lower() == "illustration-theme":
            stamp = attrs.get("content", "").split("/")
            if len(stamp) == 3 and stamp[2] in {"remote", "local", "system"}:
                return stamp[2]
    return None


def google_fonts_urls(html: str, span: tuple[int, int]) -> list[str]:
    """Google Fonts css2 URLs the page itself loads (<link href> or @import): the theme's fonts."""
    urls: list[str] = []
    for token, _, _, _ in html_tokens(html):
        if (token.group("tag") or "").lower() != "link" or token.group("close") or span[0] <= token.start() < span[1]:
            continue
        tag = START_TAG_RE.match(token.group(0))
        if tag is None:
            continue
        for attr in TAG_ATTR_RE.finditer(tag.group(2)):
            if attr.group(2).lower() == "href" and attr.group(4):
                raw = attr.group(4)
                urls.append(html_entities.unescape(raw[1:-1] if raw[0] in "\"'" else raw))
    for match in re.finditer(r"@import\s+(?:url\(\s*)?[\"']?([^\"')\s]+)", strip_css_comments(page_css(html, span))):
        urls.append(match.group(1))
    seen: list[str] = []
    for url in urls:
        if GOOGLE_FONTS_URL_RE.fullmatch(url) and url not in seen:
            seen.append(url)
    return seen


# ---------------------------------------------------------------- XML syntax


def rewrite_start_tags(svg: str, transform: Callable[[re.Match[str]], str]) -> str:
    """Apply ``transform`` to real start tags, leaving comments and CDATA untouched."""
    out: list[str] = []
    pos = 0
    while True:
        opener = XML_OPAQUE_OPEN_RE.search(svg, pos)
        text_end = opener.start() if opener else len(svg)
        out.append(START_TAG_RE.sub(transform, svg[pos:text_end]))
        if opener is None:
            break
        closer = "-->" if opener.group(0) == "<!--" else "]]>"
        close_at = svg.find(closer, opener.end())
        stop = len(svg) if close_at == -1 else close_at + len(closer)
        out.append(svg[opener.start():stop])
        pos = stop
        if close_at == -1:
            break
    return "".join(out)


def xmlify_attributes(svg: str) -> str:
    """Valueless (``data-motion-item``) and unquoted (``data-step=1``) attributes become XML."""
    def tag(match: re.Match[str]) -> str:
        def attr(m: re.Match[str]) -> str:
            space, name, equals, value = m.groups()
            if value is None:
                return f'{space}{name}=""'
            return m.group(0) if value[0] in "\"'" else f'{space}{name}{equals}"{value}"'
        name, attrs, end = match.groups()
        return f"<{name}{TAG_ATTR_RE.sub(attr, attrs)}{end}>"
    return rewrite_start_tags(svg, tag)


LEGACY_ENTITY_NAMES = tuple(name for name in html_entities.entities.html5 if not name.endswith(";"))
XML_REFERENCE_RE = re.compile(r"&(?:(amp|lt|gt|quot|apos);|#[0-9]+;?|#[xX][0-9A-Fa-f]+;?)")
XML_NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}


def normalize_html_entities(svg: str) -> str:
    """HTML character references (``&nbsp;``, ``&rarr;``, ``&#128;``) as XML-safe text, decoded once.

    Comments, CDATA and <style>/<script> bodies are left untouched.
    """
    opaque = re.compile(
        r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|"
        r"(?P<opening><(?P<tag>style|script)\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>)"
        r".*?</(?P=tag)\s*>", re.DOTALL | re.IGNORECASE,
    )
    references = re.compile(
        r"&(?:(?P<numeric>#[xX][0-9A-Fa-f]+;?|#[0-9]+;?)|[A-Za-z][A-Za-z0-9]+;|(?P<legacy>"
        + "|".join(sorted((re.escape(name) for name in LEGACY_ENTITY_NAMES), key=len, reverse=True))
        + r"))"
    )
    tag = re.compile(r"<[A-Za-z/!?](?:[^>\"']|\"[^\"]*\"|'[^']*')*>")

    def replace_entity(match: re.Match[str], in_attribute: bool = False) -> str:
        original = match.group(0)
        if original in ("&amp;", "&lt;", "&gt;", "&apos;", "&quot;"):
            return original
        if match.group("numeric") is not None:
            number = original[2:].rstrip(";")
            hexadecimal = number.startswith(("x", "X"))
            digits = (number[1:] if hexadecimal else number).lstrip("0") or "0"
            codepoint = int(digits, 16 if hexadecimal else 10) if len(digits) <= 8 else 0x110000
            if codepoint == 0 or 0xD800 <= codepoint <= 0xDFFF or codepoint > 0x10FFFF:
                decoded = "\ufffd"
            elif 0x80 <= codepoint <= 0x9F:
                decoded = html_entities.unescape(f"&#{codepoint};")  # windows-1252, as HTML reads it
            else:
                decoded = chr(codepoint)
        elif match.group("legacy") is not None:
            following = match.string[match.end():match.end() + 1]
            if in_attribute and (following == "=" or following.isalnum()):
                return original  # HTML leaves these undecoded inside attribute values
            decoded = html_entities.entities.html5[match.group("legacy")]
        else:
            decoded = html_entities.entities.html5.get(original[1:])
        if decoded is None:
            return original
        return (html_entities.escape(decoded, quote=True)
                .replace("\t", "&#9;").replace("\n", "&#10;").replace("\r", "&#13;"))

    def normalize_region(region: str) -> str:
        parts: list[str] = []
        cursor = 0
        for token in tag.finditer(region):
            parts.append(references.sub(replace_entity, region[cursor:token.start()]))
            parts.append(references.sub(lambda m: replace_entity(m, True), token.group(0)))
            cursor = token.end()
        parts.append(references.sub(replace_entity, region[cursor:]))
        return "".join(parts)

    out: list[str] = []
    pos = 0
    for match in opaque.finditer(svg):
        out.append(normalize_region(svg[pos:match.start()]))
        opening = match.group("opening")
        if opening is not None:
            out.append(references.sub(lambda m: replace_entity(m, True), opening) + match.group(0)[len(opening):])
        else:
            out.append(match.group(0))
        pos = match.end()
    out.append(normalize_region(svg[pos:]))
    return "".join(out)


def decode_xml_references(value: str) -> str:
    """Decode the references normalize_html_entities leaves (numeric ones with their HTML meaning)."""
    return XML_REFERENCE_RE.sub(
        lambda m: XML_NAMED[m.group(1)] if m.group(1) else html_entities.unescape(m.group(0)), value)


def root_attributes(svg: str) -> tuple[re.Match[str], dict[str, str]]:
    opening = START_TAG_RE.match(svg)
    if opening is None or opening.group(1).lower() != "svg":
        raise ValueError("The first SVG has an invalid opening tag.")
    attrs = {}
    for attr in TAG_ATTR_RE.finditer(opening.group(2)):
        raw = attr.group(4)
        attrs.setdefault(attr.group(2), None if raw is None else raw[1:-1] if raw[0] in "\"'" else raw)
    return opening, attrs


def set_export_scope(svg: str, identity: str) -> str:
    """Set the style scope on the root while preserving its author's id and classes."""
    opening, _ = root_attributes(svg)
    attrs = TAG_ATTR_RE.sub(
        lambda match: "" if match.group(2) == "data-illustrate-export" else match.group(0),
        opening.group(2),
    )
    return (f'<{opening.group(1)} data-illustrate-export="{identity}"{attrs}{opening.group(3)}>'
            + svg[opening.end():])


def ensure_namespaces(svg: str) -> str:
    """Require the SVG namespace on the root (adding it when absent); declare xlink when used."""
    opening, attrs = root_attributes(svg)
    additions = ""
    if "xmlns" in attrs:
        if attrs["xmlns"] is None or decode_xml_references(attrs["xmlns"]) != SVG_NS:
            raise ValueError(f"The diagram SVG's xmlns must be {SVG_NS}.")
    else:
        additions += f' xmlns="{SVG_NS}"'
    if "xmlns:xlink" in attrs:
        if attrs["xmlns:xlink"] is None or decode_xml_references(attrs["xmlns:xlink"]) != XLINK_NS:
            raise ValueError(f"The diagram SVG's xmlns:xlink must be {XLINK_NS}.")
    elif re.search(r"<[A-Za-z][^>]*\sxlink:[\w-]+\s*=", COMMENT_OR_CDATA_RE.sub("", svg)):
        additions += f' xmlns:xlink="{XLINK_NS}"'
    if not additions:
        return svg
    return f"<{opening.group(1)}{additions}{opening.group(2)}{opening.group(3)}>" + svg[opening.end():]


def ensure_viewbox(svg: str) -> tuple[float, float, float, float]:
    """The root viewBox as four finite numbers with a positive width and height."""
    _, attrs = root_attributes(svg)
    raw = attrs.get("viewBox")
    if raw is None:
        raise ValueError("The diagram SVG has no viewBox; refusing to guess export dimensions.")
    value = decode_xml_references(raw).strip(" \t\r\n")
    number = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
    separator = r"(?:[ \t\r\n]*,[ \t\r\n]*|[ \t\r\n]+)"
    parsed = re.fullmatch(separator.join([f"({number})"] * 4), value)
    if parsed is None:
        raise ValueError(f"The diagram SVG's viewBox {raw!r} must be four numbers.")
    box = tuple(float(token) for token in parsed.groups())
    if not all(math.isfinite(token) for token in box) or min(box[2:]) <= 0:
        raise ValueError(f"The diagram SVG's viewBox {raw!r} needs a finite, positive width and height.")
    return box  # type: ignore[return-value]


# ---------------------------------------------------------------- insertion


def leading_accessibility_end(svg: str, pos: int) -> int:
    """Offset after the leading <title>/<desc> children, so inserted <defs> come after them."""
    token = re.compile(r"<!--.*?-->|<title\b[^>]*>|<desc\b[^>]*>", re.DOTALL | re.IGNORECASE)
    while True:
        next_pos = pos + re.match(r"\s*", svg[pos:]).end()  # type: ignore[union-attr]
        opening = token.match(svg, next_pos)
        if opening is None:
            return pos
        if opening.group(0).startswith("<!--"):
            pos = opening.end()
            continue
        name = "title" if opening.group(0).lower().startswith("<title") else "desc"
        endings = re.compile(rf"<!\[CDATA\[.*?\]\]>|</{name}\s*>", re.DOTALL | re.IGNORECASE)
        close = next((m for m in endings.finditer(svg, opening.end()) if m.group(0).startswith("</")), None)
        if close is None:
            return pos
        pos = close.end()


def insert_into_defs(svg: str, markup: str) -> str:
    """Put ``markup`` first in the first live <defs>, or in a new <defs> after the leading title/desc."""
    live = mask_opaque_html(svg)
    defs = re.search(r"<defs\b[^>]*?(?<!/)>", live, re.IGNORECASE)
    if defs:
        return svg[:defs.end()] + markup + svg[defs.end():]
    opening = START_TAG_RE.match(svg)
    assert opening is not None
    at = leading_accessibility_end(svg, opening.end())
    return svg[:at] + f"<defs>{markup}</defs>" + svg[at:]


# ---------------------------------------------------------------- defs IDs


def css_escape(text: str, pos: int) -> tuple[str, int] | None:
    """Read one CSS escape at ``pos`` (a backslash), with its optional hex terminator."""
    end = pos + 1
    if end == len(text) or text[end] in "\n\r\f":
        return None
    start = end
    while end < min(start + 6, len(text)) and text[end] in "0123456789abcdefABCDEF":
        end += 1
    if end == start:
        return text[end], end + 1
    code = int(text[start:end], 16)
    value = chr(code) if 0 < code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF else "\ufffd"
    if end < len(text) and text[end] in " \t\n\r\f":
        end += 2 if text[end:end + 2] == "\r\n" else 1
    return value, end


def decoded_css_url_fragment(fragment: str) -> str:
    decoded: list[str] = []
    pos = 0
    while pos < len(fragment):
        if fragment[pos] == "\\":
            escaped = css_escape(fragment, pos)
            if escaped is None:
                return fragment
            value, pos = escaped
            decoded.append(value)
        else:
            decoded.append(fragment[pos])
            pos += 1
    return "".join(decoded)


def css_id_token(text: str, pos: int) -> tuple[str, int] | None:
    """Read a whole CSS identifier at ``pos``, decoding escapes."""
    def starts_name(index: int) -> bool:
        char = text[index:index + 1]
        return bool(char) and (char.isascii() and (char.isalpha() or char == "_") or ord(char) >= 128
                               or (char == "\\" and css_escape(text, index) is not None))

    if not starts_name(pos) and not (text[pos:pos + 1] == "-"
                                     and (starts_name(pos + 1) or text[pos + 1:pos + 2] == "-")):
        return None
    out: list[str] = []
    while pos < len(text):
        char = text[pos]
        if char == "\\":
            escaped = css_escape(text, pos)
            if escaped is None:
                break
            value, pos = escaped
            out.append(value)
        elif (char.isascii() and (char.isalnum() or char in "_-")) or ord(char) >= 128:
            out.append(char)
            pos += 1
        else:
            break
    return "".join(out), pos


def retarget_id_selector(selector: str, old: str, new_css: str) -> str:
    """Replace whole decoded ``#old`` tokens with ``#new_css``, keeping strings and escapes."""
    out: list[str] = []
    quote = ""
    pos = 0
    while pos < len(selector):
        char = selector[pos]
        if char == "\\":
            escaped = css_escape(selector, pos)
            end = escaped[1] if escaped else pos + 1
            out.append(selector[pos:end])
            pos = end
            continue
        if quote:
            out.append(char)
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
            out.append(char)
        elif char == "#" and (token := css_id_token(selector, pos + 1)):
            value, end = token
            out.append(f"#{new_css}" if value == old else selector[pos:end])
            pos = end
            continue
        else:
            out.append(char)
        pos += 1
    return "".join(out)


REFERENCE_REGION_RE = re.compile(
    r"(?P<skip><!\[CDATA\[.*?\]\]>|<script\b.*?</script\s*>|<!--.*?-->)"
    r"|<style\b[^>]*>.*?</style\s*>"
    r"|<[A-Za-z/?!](?:[^>\"']|\"[^\"]*\"|'[^']*')*>",
    re.IGNORECASE | re.DOTALL,
)
URL_REF_RE = re.compile(
    r"(?<![A-Za-z0-9_\\\-\u0080-\U0010ffff])(?i:url)\(\s*(?P<quote>[\"']|&quot;|&apos;|)\s*#\s*"
    r"(?P<ident>.*?)\s*(?P=quote)\s*\)", re.DOTALL,
)
RAW_URL_REF_RE = re.compile(
    r"(?<![A-Za-z0-9_\\\-\u0080-\U0010ffff])(?i:url)\(\s*(?P<quote>[\"']|)\s*#\s*(?P<ident>.*?)\s*(?P=quote)\s*\)",
    re.DOTALL,
)
CSS_STRING_RE = re.compile(r'''(?:"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*')''', re.DOTALL)


def defs_ids(svg: str) -> set[str]:
    """IDs of referenceable elements under a live <defs>, decoded once."""
    live = COMMENT_OR_CDATA_RE.sub("", svg)
    found: set[str] = set()
    for block in re.findall(r"<defs\b[^>]*>(.*?)</defs\s*>", live, re.IGNORECASE | re.DOTALL):
        for tag in START_TAG_RE.finditer(block):
            if tag.group(1).lower() not in DEFS_ID_TAGS:
                continue
            for attr in TAG_ATTR_RE.finditer(tag.group(2)):
                if attr.group(2) == "id" and attr.group(4) and attr.group(4)[0] in "\"'":
                    found.add(decode_xml_references(attr.group(4)[1:-1]))
    return found


def namespace_defs_ids(svg: str, prefix: str) -> str:
    """Prefix defs IDs and every reference to them: url(#id), href="#id" and #id selectors.

    References compare after one XML decode and one CSS-escape decode, so ``url(&quot;#a&quot;)``,
    ``url('#a')`` and ``url(#\\61)`` all follow ``id="a"``. Visible text is not touched.
    """
    # An ID that already carries the prefix (a figure drawn with namespaced IDs) stays as it is.
    ids = {ident for ident in defs_ids(svg) if not ident.startswith(f"{prefix}-")}
    if not ids:
        return svg
    renamed = {old: f"{prefix}-{old}" for old in ids}

    def rewrite_raw_url(match: re.Match[str]) -> str:
        if decoded_css_url_fragment(match.group("ident")) not in ids:
            return match.group(0)
        return f"url({match.group('quote')}#{prefix}-{match.group('ident')}{match.group('quote')})"

    def rewrite_url(match: re.Match[str]) -> str:
        if decoded_css_url_fragment(decode_xml_references(match.group("ident"))) not in ids:
            return match.group(0)
        return f"url({match.group('quote')}#{prefix}-{match.group('ident')}{match.group('quote')})"

    def rewrite_css_urls(css: str) -> str:
        """Consume strings, comments and whole identifiers before reading url( functions."""
        out: list[str] = []
        pos = 0
        while pos < len(css):
            if css[pos] in "\"'":
                literal = CSS_STRING_RE.match(css, pos)
                end = literal.end() if literal else len(css)
            elif css.startswith("/*", pos):
                closing = css.find("*/", pos + 2)
                end = closing + 2 if closing >= 0 else len(css)
            elif (token := css_id_token(css, pos)) is not None:
                end = token[1]
                if css[pos:end].lower() == "url" and css[end:end + 1] == "(":
                    reference = RAW_URL_REF_RE.match(css, pos)
                    if reference is not None:
                        out.append(rewrite_raw_url(reference))
                        pos = reference.end()
                        continue
            else:
                escaped = css_escape(css, pos) if css[pos] == "\\" else None
                end = escaped[1] if escaped else pos + 1
            out.append(css[pos:end])
            pos = end
        return "".join(out)

    def rewrite_tag(tag: re.Match[str]) -> str:
        # SMIL <set>/<animate> values carry paint for the animated attribute, not their own.
        target = next((decode_xml_references(a.group(4)[1:-1]) for a in TAG_ATTR_RE.finditer(tag.group(2))
                       if a.group(2) == "attributeName" and a.group(4) and a.group(4)[0] in "\"'"), "")
        animated = ({"set": {"to"}, "animate": {"from", "to", "values", "by"}}.get(tag.group(1), set())
                    if target in CSS_URL_ATTRIBUTES else set())

        def css_attribute(raw: str) -> str:
            value = decode_xml_references(re.sub(r"\r\n?|[\n\t]", " ", raw))
            rewritten = rewrite_css_urls(value)
            if rewritten == value:
                return raw
            return (escape_css_for_xml(rewritten).replace('"', "&quot;").replace("'", "&apos;")
                    .replace("\t", "&#9;").replace("\n", "&#10;").replace("\r", "&#13;"))

        def attribute(match: re.Match[str]) -> str:
            space, name, equals, quoted = match.groups()
            if quoted is None or quoted[0] not in "\"'":
                return match.group(0)
            raw = quoted[1:-1]
            value = decode_xml_references(raw)
            if name == "id" and value in ids and tag.group(1).lower() in DEFS_ID_TAGS:
                raw = html_entities.escape(renamed[value], quote=True)
            elif name.lower() in {"href", "xlink:href"} and value.startswith("#") and value[1:] in ids:
                raw = "#" + html_entities.escape(renamed[value[1:]], quote=True)
            elif name.lower() == "style" or name in animated:
                raw = css_attribute(raw)
            elif name.lower() in CSS_URL_ATTRIBUTES:
                raw = URL_REF_RE.sub(rewrite_url, raw)
            return space + name + equals + quoted[0] + raw + quoted[-1]

        return "<" + tag.group(1) + TAG_ATTR_RE.sub(attribute, tag.group(2)) + tag.group(3) + ">"

    def retarget_css(css: str) -> str:
        for old in sorted(ids, key=len, reverse=True):
            new_css = "".join(
                char if char.isalnum() or char in "_-" or ord(char) >= 128
                else f"\\{ord(char):x} " if ord(char) < 32 or ord(char) == 127
                else "\\" + char
                for char in renamed[old]
            )
            css = RULE_RE.sub(lambda rule, old=old, new=new_css: retarget_id_selector(rule.group(1), old, new)
                              + "{" + rule.group(2) + "}", css)
        return rewrite_css_urls(css)

    def rewrite_style(region: str) -> str:
        style = STYLE_BLOCK_RE.fullmatch(region)
        if style is None:
            return URL_REF_RE.sub(rewrite_url, region)
        content, parts, pos = style.group(1), [], 0
        for cdata in CDATA_SECTION_RE.finditer(content):
            parts.append(escape_css_for_xml(retarget_css(decode_xml_references(content[pos:cdata.start()]))))
            parts.append("<![CDATA[" + retarget_css(cdata.group(1)) + "]]>")
            pos = cdata.end()
        parts.append(escape_css_for_xml(retarget_css(decode_xml_references(content[pos:]))))
        opening = START_TAG_RE.match(region)
        head = rewrite_tag(opening) + region[opening.end():style.start(1)] if opening else region[:style.start(1)]
        return head + "".join(parts) + region[style.end(1):]

    def rewrite(region: re.Match[str]) -> str:
        token = region.group(0)
        if region.group("skip"):
            return token
        if token[:6].lower() == "<style":
            return rewrite_style(token)
        tag = START_TAG_RE.fullmatch(token)
        return rewrite_tag(tag) if tag is not None else token

    return REFERENCE_REGION_RE.sub(rewrite, svg)


# ---------------------------------------------------------------- PowerPoint paint


def selector_list_parts(selector: str) -> list[str]:
    """Split selector-list commas only, keeping quoted, bracketed and escaped literals."""
    parts: list[str] = []
    start = depth = pos = 0
    quote = ""
    while pos < len(selector):
        char = selector[pos]
        if char == "\\" and (escaped := css_escape(selector, pos)):
            pos = escaped[1]
            continue
        if quote:
            quote = "" if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(selector[start:pos])
            start = pos + 1
        pos += 1
    parts.append(selector[start:])
    return parts


def _decoded_css_property_text(style: str) -> str:
    style = strip_css_comments(html_entities.unescape(style))

    def escape(match: re.Match[str]) -> str:
        hexadecimal, literal = match.groups()
        if hexadecimal is not None:
            value = int(hexadecimal, 16)
            return chr(value) if 0 < value <= 0x10FFFF and not 0xD800 <= value <= 0xDFFF else "\ufffd"
        return "" if literal in "\r\n\f" else literal

    return re.sub(r"\\(?:([0-9a-fA-F]{1,6})(?:\r\n|[ \t\r\n\f])?|([\s\S]))", escape, style)


def _css_paint_may_target(selector: str, elements: list[ET.Element]) -> bool:
    """False only for simple selectors that provably miss every element; unknown CSS stays True."""
    for branch in selector_list_parts(selector):
        if "\\" in branch:
            return True
        terminal = re.split(r"[\s>+~]+", branch.strip())[-1]
        if not terminal or not re.fullmatch(r"(?:[A-Za-z][\w-]*|\*)?(?:[.#][\w-]+)*", terminal):
            return True
        tag = re.match(r"^[A-Za-z][\w-]*", terminal)
        classes = re.findall(r"\.([\w-]+)", terminal)
        ids = re.findall(r"#([\w-]+)", terminal)
        for element in elements:
            if tag and element.tag.rsplit("}", 1)[-1] != tag.group(0):
                continue
            if all(name in element.get("class", "").split() for name in classes) and all(
                    name == element.get("id") for name in ids):
                return True
    return False


def normalize_rgba_paint(svg: str) -> str:
    """Split rgba()/transparent fill and stroke attributes for PowerPoint's SVG importer.

    PowerPoint paints ``rgba(...)`` and ``transparent`` opaque black. Each becomes hex paint plus
    ``fill-opacity``/``stroke-opacity`` (or ``none``) only when the alpha survives the cascade: an
    inline, stylesheet, inherited or descendant override keeps the original rgba.
    """
    try:
        elements = list(ET.fromstring(svg).iter())
    except ET.ParseError:
        return svg  # the final well-formedness check reports it
    descendants = {index: list(element.iter())[1:] for index, element in enumerate(elements) if len(element)}
    opacity_counts = {"fill-opacity": 0, "stroke-opacity": 0}
    styles = list(STYLE_BLOCK_RE.findall(svg))

    def collect(match: re.Match[str]) -> str:
        for attr in TAG_ATTR_RE.finditer(match.group(2)):
            if attr.group(2) in opacity_counts:
                opacity_counts[attr.group(2)] += 1
            elif attr.group(2) == "style" and attr.group(4) is not None:
                styles.append(attr.group(4)[1:-1])
        return match.group(0)

    rewrite_start_tags(svg, collect)
    css_opacity = {key for key in opacity_counts if any(
        re.search(rf"(?:^|[;{{])\s*{key}\s*:", _decoded_css_property_text(style), re.IGNORECASE) for style in styles)}
    rules = [rule for style in STYLE_BLOCK_RE.findall(svg) for rule in RULE_RE.finditer(strip_css_comments(style))]
    position = 0

    def normalize(match: re.Match[str]) -> str:
        nonlocal position
        if position >= len(elements):
            return match.group(0)
        children = descendants.get(position, [])
        element = elements[position]
        position += 1
        name, attrs, end = match.groups()
        values = {a.group(2): a.group(4)[1:-1] for a in TAG_ATTR_RE.finditer(attrs) if a.group(4) is not None}
        updates: dict[str, str] = {}
        additions: list[str] = []
        for prop in ("fill", "stroke"):
            value = values.get(prop, "")
            if value == "transparent":
                updates[prop] = "none"
                continue
            rgba = RGBA_ATTR_RE.fullmatch(f'{prop}="{value}"')
            if rgba is None:
                continue
            _, r, g, b, alpha = rgba.groups()
            opacity_name = f"{prop}-opacity"
            declared = rf"(?:^|[;{{])\s*{prop}\s*:"
            inline_paint = re.search(declared, _decoded_css_property_text(element.get("style", "")), re.I)
            descendant_paint = any(prop in child.attrib or re.search(
                declared, _decoded_css_property_text(child.get("style", "")), re.I) for child in children)
            stylesheet_paint = any(re.search(declared, _decoded_css_property_text(rule.group(2)), re.I)
                                   and _css_paint_may_target(rule.group(1), [element] + children) for rule in rules)
            if (inline_paint or descendant_paint or stylesheet_paint or opacity_name in css_opacity
                    or opacity_counts[opacity_name] > int(opacity_name in values)):
                continue
            opacity = alpha if 0 <= float(alpha) <= 1 else "0" if float(alpha) < 0 else "1"
            if opacity_name in values:
                original = values[opacity_name].strip()
                try:
                    amount = float(original.rstrip("%")) / (100 if original.endswith("%") else 1)
                except ValueError:
                    continue
                if not math.isfinite(amount):
                    continue
                updates[opacity_name] = format(min(1, max(0, amount)) * max(0, min(1, float(alpha))), ".12g")
            else:
                additions.append(f' {opacity_name}="{opacity}"')
            updates[prop] = "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(c))) for c in (r, g, b)))

        def replace(attr: re.Match[str]) -> str:
            space, key, _equals, _value = attr.groups()
            return f'{space}{key}="{updates[key]}"' if key in updates else attr.group(0)

        return f"<{name}{TAG_ATTR_RE.sub(replace, attrs)}{''.join(additions)}{end}>"

    return rewrite_start_tags(svg, normalize)


def check_well_formed(document: str) -> None:
    try:
        ET.fromstring(document.encode("utf-8"))
    except ET.ParseError as exc:
        raise ValueError(f"The exported SVG is not well-formed XML ({exc}); check the figure markup.") from exc
