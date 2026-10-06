"""Re-skin a ported example from the upstream default literals to a registry theme.

Test fixture only: proves colour checks are theme-aware without depending on
`illustration_theme.py apply`. Maps paper/ink/muted/soft/accent (hex and the
`rgba(r,g,b,` prefix) for the light or dark default palette.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skill" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import illustration_theme  # noqa: E402

DEFAULTS = {
    "light": {"paper": "#f5f5f5", "ink": "#2d3142", "muted": "#4f5d75", "soft": "#7a8399", "accent": "#eb6c36"},
    "dark": {"paper": "#2d3142", "ink": "#f5f5f5", "muted": "#bfc0c0", "soft": "#8e98ac", "accent": "#f08a59"},
}


def _rgb(value: str) -> str:
    return ",".join(str(int(value[i:i + 2], 16)) for i in (1, 3, 5))


def retheme(source: str, mode: str, theme: str = "cobalt") -> str:
    target = illustration_theme.registry()["themes"][theme][mode]
    # Two passes through placeholders so paper/ink swaps never chain.
    for index, (role, old) in enumerate(DEFAULTS[mode].items()):
        for variant in (old, old.upper()):
            source = source.replace(variant, f"@@{index}hex@@")
        source = source.replace(f"rgba({_rgb(old)},", f"@@{index}rgba@@")
    for index, role in enumerate(DEFAULTS[mode]):
        new = target[role].lower()
        source = source.replace(f"@@{index}hex@@", new).replace(f"@@{index}rgba@@", f"rgba({_rgb(new)},")
    return source
