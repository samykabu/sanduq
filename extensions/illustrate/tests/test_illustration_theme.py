"""Sanduq's own theme files validate against the vendored illustration_theme.py (upstream tests the script itself)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

EXT_DIR = Path(__file__).resolve().parent.parent
REPO = EXT_DIR.parent.parent
spec = importlib.util.spec_from_file_location("illustration_theme", EXT_DIR / "skill" / "scripts" / "illustration_theme.py")
it = importlib.util.module_from_spec(spec)
spec.loader.exec_module(it)


class RepositoryThemes(unittest.TestCase):
    def test_project_config_and_documented_example_validate(self):
        it.validate_config(it.load_yaml(REPO / ".github" / "illustration-theme.yml"))
        theme = it.load_yaml(REPO / "docs" / "examples" / "booking-illustration-theme.yml")
        it.validate_theme(str(theme.pop("name")), theme)


if __name__ == "__main__":
    unittest.main()
