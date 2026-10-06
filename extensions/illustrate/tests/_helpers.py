"""Shared paths and loaders for the Illustrate skill tests (stdlib only)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

EXT_DIR = Path(__file__).resolve().parent.parent
SKILL_DIR = EXT_DIR / "skill"
SCRIPTS = SKILL_DIR / "scripts"
ASSETS = SKILL_DIR / "assets"
REPO = EXT_DIR.parent.parent

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(filename: str):
    """Import a script by file name (hyphenated names included)."""
    name = filename.removesuffix(".py").replace("-", "_")
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def baseline(filename: str) -> set[str]:
    path = SCRIPTS / filename
    if not path.is_file():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def core_examples() -> list[Path]:
    """Editorial examples `apply` must handle: every example except hand, terminal and consultant."""
    return [
        path
        for path in sorted(ASSETS.glob("example-*.html"))
        if not any(token in path.stem for token in ("-hand", "-terminal", "consultant"))
    ]
