#!/usr/bin/env python3
"""Colour tokens the ported data verifiers accept.

Shipped examples keep upstream's literal palette (accent #eb6c36 light,
#f08a59 dark); a project figure carries its active Illustrate theme instead.
Checkers accept both: the upstream defaults plus the active theme's light and
dark palettes, resolved through illustration_theme.py from the project's
.github/illustration-theme.yml (current directory), or the registry default
theme when the project has none.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import illustration_theme as it  # noqa: E402

DEFAULT_ACCENTS = ("#eb6c36", "#f08a59")


def active_palettes(root: Path | None = None) -> dict:
    """{"light": colors, "dark": colors} for the active theme; {} if unresolvable."""
    try:
        path = it.project_config(root or Path.cwd())
        if path.is_file():
            config = it.load_yaml(path)
        else:
            config = it.default_config(str(it.registry().get("default_theme", "cobalt")))
        theme = it.all_themes(config)[str(config["active"]["theme"])]
        return {mode: dict(theme[mode]) for mode in ("light", "dark") if isinstance(theme.get(mode), dict)}
    except (it.ThemeError, KeyError, OSError, ValueError) as error:
        # ponytail: a broken theme file is `illustration_theme.py validate`'s finding;
        # here it only narrows acceptance to the upstream defaults.
        sys.stderr.write("note: active theme unresolved (%s); accepting default tokens only\n" % error)
        return {}


def accent_hexes() -> frozenset:
    found = {str(p.get("accent", "")).lower() for p in active_palettes().values()}
    return frozenset(DEFAULT_ACCENTS) | {h for h in found if re.fullmatch(r"#[0-9a-f]{6}", h)}


def accent_re() -> re.Pattern:
    """Any accepted accent, as hex or as an rgba() of the same channels."""
    parts = []
    for value in sorted(accent_hexes()):
        red, green, blue = (int(value[i:i + 2], 16) for i in (1, 3, 5))
        parts.append(re.escape(value) + r"\b")
        parts.append(r"rgba\(\s*%d\s*,\s*%d\s*,\s*%d\b" % (red, green, blue))
    return re.compile("|".join(parts), re.IGNORECASE)


if __name__ == "__main__":
    assert accent_re().search('stroke="#EB6C36"') and accent_re().search("rgba(240, 138, 89,0.4)")
    assert not accent_re().search('stroke="#2d3142"')
    print("accepted accents:", ", ".join(sorted(accent_hexes())))
