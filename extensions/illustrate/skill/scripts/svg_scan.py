#!/usr/bin/env python3
"""SVG scanning helpers the data verifiers share.

The verifiers load this module the way they load theme_tokens.py. Each verifier
keeps its own transform contract (`transform_carrier`) and number reader
(`number`) and passes them in: those differ per chart on purpose.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

GROUP_TAGS = ("g", "svg")                     # the only ancestors whose transform is inherited
BODY_TAGS = ("text", "title", "desc", "style")  # elements whose character data is read

# The COMPLETE numeric token an author may print: sign, comma-grouped
# thousands, decimals, leading-dot decimals, exponents. Matching only the
# first fragment is how "512,000" once agreed with metadata that said 512.
NUMBER_RE = re.compile(
    r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
)
DIGIT_RE = re.compile(r"\d")


class Element:
    """One start tag a checker cares about, as the browser tokenized it."""

    __slots__ = ("tag", "attrs", "offset", "line", "body", "ancestor")

    def __init__(self, tag, attrs, offset, line, ancestor):
        self.tag = tag
        self.attrs = attrs          # first-wins dict, names lower-cased, values unescaped
        self.offset = offset        # offset of `<` in the source, for ordering
        self.line = line
        self.body = ""              # character data up to the matching end tag
        self.ancestor = ancestor    # how the nearest transformed <g>/<svg> moves it, or None


def first_wins(attrs) -> dict:
    """Attributes as the browser keeps them: on a repeat, the FIRST wins.

    HTML parsing drops a duplicate attribute rather than overwriting the one
    already on the token, so a second `r` on a circle is not merely ignored -
    it is not in the document at all. A dict comprehension does the opposite,
    and that gap is a fail-open every caller inherits: a mark carrying a
    dishonest first value and an honest second renders the dishonest one
    while a last-wins reader checks, and passes, bytes the browser threw away.
    A present-but-valueless attribute is an empty string, not an absent one.
    """
    seen = {}
    for name, value in attrs:
        seen.setdefault(name, "" if value is None else value)
    return seen


class Scanner(HTMLParser):
    """Collect the mark tags, texts, title/desc and style elements with ancestry.

    Each tag in `marks` is collected in the attribute named for its plural
    (`circle` in `circles`, `line` in `lines`). `transform_carrier(attrs)` is the
    verifier's own test for a style transform on a <g>/<svg>.

    HTMLParser already lowercases tag and attribute names, tolerates unquoted
    values and whitespace around `=`, unescapes entities, keeps a quoted `>`
    inside the value it belongs to, and never invokes handle_starttag for
    tag-like text inside a comment or inside <script>/<style> raw text - each
    of those is exactly a case a regex tag matcher mishandles. Ancestry is
    tracked for <g>/<svg> only, the elements whose transform a child inherits.
    """

    def __init__(self, source: str, marks, transform_carrier):
        super().__init__(convert_charrefs=True)
        self.marks = tuple(marks)
        self.transform_carrier = transform_carrier
        for tag in self.marks:
            setattr(self, tag + "s", [])
        self.texts: list = []
        self.named: list = []      # <title> and <desc>
        self.styles: list = []
        self.error = None
        self._groups: list = []    # (tag, how) per open <g>/<svg>
        self._open: list = []      # (tag, Element) per open body element
        self._line_starts = [0]
        for index, char in enumerate(source):
            if char == "\n":
                self._line_starts.append(index + 1)
        try:
            self.feed(source)
            self.close()
        except Exception as exc:  # noqa: BLE001 - any parser failure fails closed
            self.error = "%s: %s" % (type(exc).__name__, exc)

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_starts[line - 1] + column

    def _ancestor(self):
        for _tag, how in reversed(self._groups):
            if how is not None:
                return how
        return None

    def handle_starttag(self, tag, attrs):
        self._start(tag, first_wins(attrs), closes=False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, first_wins(attrs), closes=True)

    def _start(self, tag, attrs, closes):
        if tag in GROUP_TAGS:
            if not closes:
                how = None
                if "transform" in attrs:
                    how = "an ancestor <g>/<svg> transform"
                elif self.transform_carrier(attrs) is not None:
                    how = "an ancestor <g>/<svg> style transform"
                self._groups.append((tag, how))
            return
        if tag not in self.marks and tag not in BODY_TAGS:
            return
        element = Element(tag, attrs, self._offset(), self.getpos()[0], self._ancestor())
        if tag in self.marks:
            getattr(self, tag + "s").append(element)
            return
        if tag == "text":
            self.texts.append(element)
        elif tag == "style":
            self.styles.append(element)
        else:
            self.named.append(element)
        if not closes:
            self._open.append((tag, element))

    def handle_endtag(self, tag):
        stack = self._groups if tag in GROUP_TAGS else self._open if tag in BODY_TAGS else None
        if stack is None:
            return
        # Pop back to the matching open tag - an unclosed inner element ends
        # with its parent, as it does in the browser's tree.
        for index in range(len(stack) - 1, -1, -1):
            if stack[index][0] == tag:
                del stack[index:]
                return

    def handle_data(self, data):
        if self._open:
            # Innermost only: a <title> tooltip inside a <text> is not part of
            # the rendered label, and the browser does not draw it either.
            self._open[-1][1].body += data


def attrs_of(raw: str) -> dict:
    """First-wins attributes of one tag's raw attribute text, via the parser."""

    class _One(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.attrs = {}

        def handle_starttag(self, tag, attrs):
            self.attrs = first_wins(attrs)

        handle_startendtag = handle_starttag

    scanner = _One()
    scanner.feed("<x " + raw + ">")
    scanner.close()
    return scanner.attrs


def printed_number(body: str, number):
    """(value, reason) for a label's visible text, read with the verifier's `number`.

    Returns a value only when the text carries exactly one complete numeric
    token. Trailing units are fine ("500ms"); a second number, or digits the
    token did not consume, is ambiguous and reported rather than guessed at.
    """
    match = NUMBER_RE.search(body)
    if match is None:
        return None, "prints no number"
    outside = body[:match.start()] + body[match.end():]
    if DIGIT_RE.search(outside):
        return None, "prints more than one numeric token"
    value = number(match.group())
    if value is None:
        return None, "prints a number this checker cannot read"
    return value, None


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def median(values: list) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def is_hand_variant(path: Path, source: str) -> bool:
    """A generate-hand-variants.cjs output: a `-hand` stem or rough.js redraw markup."""
    # ponytail: rough.js redraws drop the data contract, so they are never in scope.
    return path.stem.endswith("-hand") or 'class="rough-shape"' in source
