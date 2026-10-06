"""Theme matrix: `apply` every editorial example under every built-in theme plus the custom example.

Glob-driven over assets/example-*.html (minus -hand, -terminal, consultant), so new diagram types
are covered automatically, plus the Cobalt-literal templates (template.html, -dark, -full). Each file is applied in its own mode (inferred: -dark suffix or paper
literal, else light), so the light and dark tables are both exercised.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from _helpers import ASSETS, core_examples, load

import illustration_theme as it

self_check = load("self_check.py")
geometry = load("verify-geometry.py")
lint_skin = load("lint-skin.py")

GENERIC_FONTS = {"system-ui", "sans-serif", "serif", "monospace", "ui-monospace", "inherit", "initial", "unset"}
FONT_VALUE_RE = re.compile(
    r"font-family\s*=\s*([\"'])(.*?)\1|(?:font-family|--font-[\w-]+)\s*:\s*([^;}\"<>]+)", re.IGNORECASE | re.DOTALL
)


def families(stack: str) -> set[str]:
    return {f.strip().strip("'\"").strip().casefold() for f in stack.split(",") if f.strip()}


TEMPLATES = ("template.html", "template-dark.html", "template-full.html")


def default_literals() -> tuple[set[str], set[tuple[int, ...]]]:
    """Every recognized source literal (upstream defaults and Cobalt), minus generic #ffffff/#111111."""
    hexes, triples = set(), set()
    for table in it.source_palettes().values():
        for value in table.values():
            if value.startswith("#") and value.lower() not in it.INK_STRONG_CANDIDATES:
                hexes.add(value)
                triples.add(it._hex_rgb(value))
    return hexes, triples


def colors_in(text: str) -> tuple[set[str], set[tuple[int, ...]]]:
    hexes = {m.group(0).lower() for m in it.HEX6_RE.finditer(text)}
    triples = {tuple(int(m.group(i)) for i in (1, 2, 3)) for m in it.RGBA_RE.finditer(text)}
    return hexes, triples


class ThemeMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        custom = it.load_yaml(Path(it.REGISTRY).parent / "custom-theme.example.yml")
        cls.custom_name = str(custom.pop("name"))
        cls.config = it.default_config("cobalt", "light", "remote")
        cls.config["custom_themes"] = {cls.custom_name: custom}
        cls.themes = list(it.registry()["themes"]) + [cls.custom_name]
        # lint-skin reads custom themes from a project file, exactly as in a consumer project.
        cls.project = tempfile.TemporaryDirectory()
        it.write_yaml(it.project_config(cls.project.name), cls.config)
        cls.lint_colors = lint_skin.allowed_colors(cls.project.name)
        cls.lint_fonts = lint_skin.allowed_fonts(cls.project.name)
        cls.examples = core_examples() + [ASSETS / name for name in TEMPLATES]

    @classmethod
    def tearDownClass(cls):
        cls.project.cleanup()

    def lint(self, text: str) -> list:
        return [f for f in lint_skin.lint_text(text, *self.lint_colors, self.lint_fonts) if f[2] in ("color", "font-family")]

    def test_examples_found(self):
        self.assertGreaterEqual(len(self.examples), 8)
        for required in ("architecture", "flowchart", "bar", "sequence"):
            for suffix in ("", "-dark"):
                self.assertIn(f"example-{required}{suffix}.html", {p.name for p in self.examples})

    def test_terminal_template_refused(self):
        terminal = ASSETS / "template-terminal.html"
        with self.assertRaisesRegex(it.ThemeError, "terminal"):
            it.apply_theme(terminal.read_text(encoding="utf-8"), it.resolve_for(self.config, "dark", "emerald"), terminal)

    def test_matrix(self):
        default_hex, default_rgb = default_literals()
        for path in self.examples:
            source = path.read_text(encoding="utf-8")
            mode = it.infer_mode(source, path) or "light"
            base_self = set(self_check.verify(path))
            base_geometry = len(geometry.check(path))
            base_lint_clean = not self.lint(source)
            for name in self.themes:
                with self.subTest(example=path.name, theme=name, mode=mode):
                    theme = it.resolve_for(self.config, mode, name)
                    out = it.apply_theme(source, theme, path)
                    colors = theme["colors"]
                    it.validate_palette(name, mode, colors)

                    resolved_hex = {str(v).lower() for v in colors.values() if str(v).startswith("#")}
                    resolved_rgb = {it._hex_rgb(v) for v in resolved_hex}
                    hexes, triples = colors_in(out)
                    self.assertEqual(sorted((hexes & default_hex) - resolved_hex), [], "leftover default hex")
                    self.assertEqual(sorted((triples & default_rgb) - resolved_rgb), [], "leftover default rgba")

                    allowed = GENERIC_FONTS | {
                        f for key in ("sans", "serif", "mono") for f in families(theme["typography"][key])
                    }
                    used = set()
                    for match in FONT_VALUE_RE.finditer(out):
                        used |= {f for f in families(match.group(2) or match.group(3)) if not f.startswith("var(")}
                    self.assertEqual(sorted(used - allowed), [], "unresolved font family")
                    url = theme["typography"]["remote_css_url"]
                    self.assertEqual(out.count("fonts.googleapis.com"), 1 if url else 0)

                    self.assertEqual(it.apply_theme(out, theme, path), out, "apply is not idempotent")
                    with tempfile.TemporaryDirectory() as scratch:
                        applied = Path(scratch) / path.name
                        applied.write_text(out, encoding="utf-8")
                        self.assertLessEqual(set(self_check.verify(applied)), base_self, "apply broke self_check")
                        self.assertEqual(len(geometry.check(applied)), base_geometry)
                    if base_lint_clean:
                        self.assertEqual(self.lint(out), [], "apply introduced lint-skin colour/font findings")


if __name__ == "__main__":
    unittest.main()
