"""lint-skin.py stays theme-aware (project custom themes, upstream literals) and keeps its baseline."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest

from _helpers import ASSETS, SCRIPTS, load

import illustration_theme as it

lint_skin = load("lint-skin.py")


def categories(text: str, project_root: str = ".") -> set[str]:
    colors, triplets = lint_skin.allowed_colors(project_root)
    return {f[2] for f in lint_skin.lint_text(text, colors, triplets, lint_skin.allowed_fonts(project_root))}


class ThemeAware(unittest.TestCase):
    def test_upstream_literals_and_ink_strong_default(self):
        self.assertEqual(categories('<rect fill="#111111"/><rect fill="rgba(240,138,89,0.10)"/>'), set())

    def test_project_custom_theme_colors_and_fonts(self):
        custom = it.load_yaml(ASSETS / "custom-theme.example.yml")
        name = str(custom.pop("name"))
        text = (
            f'<rect fill="{custom["light"]["accent"]}"/><rect fill="rgba(21,87,201,0.4)"/>'
            f'<text font-family="{custom["typography"]["sans"]}">x</text>'
        )
        self.assertTrue({"color", "font-family"} <= categories(text, tempfile.gettempdir() + "/no-such-project"))
        with tempfile.TemporaryDirectory() as root:
            config = it.default_config(name)
            config["custom_themes"] = {name: custom}
            it.write_yaml(it.project_config(root), config)
            self.assertEqual(categories(text, root), set())

    def test_scripts(self):
        self.assertIn("script", categories("<script>alert(1)</script>"))
        animated = ASSETS / "example-policy-trace-animated.html"
        if animated.is_file():
            self.assertNotIn("script", categories(animated.read_text(encoding="utf-8")))


class Baseline(unittest.TestCase):
    def test_all_with_baseline_is_clean(self):
        run = subprocess.run(
            [sys.executable, str(SCRIPTS / "lint-skin.py"), "--all", "--baseline", "--quiet"],
            capture_output=True, text=True,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
