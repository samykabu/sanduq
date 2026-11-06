#!/usr/bin/env python3
"""Print icon snippets from the Illustrate icon set, so a diagram never needs the whole catalog.

    python scripts/icon_lookup.py laptop server     # exact names
    python scripts/icon_lookup.py database          # every icon whose name, group or description has the word

Names are listed in references/primitive-icons.md; the snippets live in scripts/icons.json, which
scripts/build-icons.py generates. A term that matches nothing exits 2 and names the nearest icons.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

ICONS = Path(__file__).resolve().parent / "icons.json"


def lookup(icons: dict[str, dict[str, str]], term: str) -> list[str]:
    """The exact name, or else every icon whose name, group or description contains the term."""
    key = term.strip().casefold()
    if key in icons:
        return [key]
    return [name for name, icon in icons.items()
            if key in name or key in icon["group"].casefold() or key in icon["description"].casefold()]


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__.strip())
        return 0 if argv else 2
    icons = json.loads(ICONS.read_text(encoding="utf-8"))
    status = 0
    for term in argv:
        names = lookup(icons, term)
        if not names:
            near = difflib.get_close_matches(term.casefold(), icons, n=5, cutoff=0.5)
            hint = f"; nearest: {', '.join(near)}" if near else ""
            print(f"no icon matches {term!r}{hint} (names: references/primitive-icons.md)", file=sys.stderr)
            status = 2
        for name in names:
            icon = icons[name]
            print(f"### {name} ({icon['group']}): {icon['description']}\n{icon['svg']}\nSource: {icon['source']}\n")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
