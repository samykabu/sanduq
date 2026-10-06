"""Theme schema (ink-strong) and `apply` behaviour for illustration_theme.py."""

from __future__ import annotations

import copy
import io
from html.parser import HTMLParser
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from _helpers import ASSETS, REPO, SCRIPTS, SKILL_DIR

import illustration_theme as it


def custom_example() -> tuple[str, dict]:
    theme = it.load_yaml(ASSETS / "custom-theme.example.yml")
    return str(theme.pop("name")), theme


def config_for(theme: str, mode: str = "light", font_loading: str = "remote") -> dict:
    config = it.default_config(theme, mode, font_loading)
    name, custom = custom_example()
    config["custom_themes"] = {name: custom}
    return config


def all_theme_names() -> list[str]:
    return list(it.registry()["themes"]) + [custom_example()[0]]


DOC = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>T</title>
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400&display=swap" rel="stylesheet">
  <style>
    :root { --color-paper: #f5f5f5; --font-sans: 'Geist', system-ui, sans-serif; --font-mono: 'Geist Mono', monospace; }
    h1 { font-family: 'Instrument Serif', serif; }
  </style>
</head>
<body>
<svg viewBox="0 0 10 10" role="img" aria-labelledby="t-title t-desc"><title id="t-title">T</title><desc id="t-desc">D</desc>
<rect fill="#F5F5F5" stroke="rgba(45,49,66,0.12)"/><rect fill="rgba(45, 49, 66, 0.40)"/>
<rect fill="rgba(235,108,54,0.85)"/><text fill="#111111" font-family="'Geist Mono', monospace">x</text>
<text font-family="'Geist', sans-serif" fill="#eb6c36">y</text><rect fill="#5e7a9b"/>
</svg>
</body>
</html>
"""


class InkStrong(unittest.TestCase):
    def test_derived_for_every_builtin_and_custom_theme(self):
        for name in all_theme_names():
            for mode in ("light", "dark"):
                with self.subTest(theme=name, mode=mode):
                    colors = it.resolve_for(config_for(name), mode)["colors"]
                    backdrop = it.strong_backdrop(colors)
                    best = max(it.INK_STRONG_CANDIDATES, key=lambda c: it.contrast(c, backdrop))
                    self.assertEqual(colors["ink-strong"], best)
                    self.assertGreaterEqual(it.contrast(colors["ink-strong"], backdrop), 4.5)

    def test_explicit_value_kept_and_validated(self):
        _, theme = custom_example()
        theme["dark"]["ink-strong"] = "#0a0a0a"
        it.validate_theme("x", theme)
        config = config_for("cobalt")
        config["custom_themes"]["x"] = theme
        self.assertEqual(it.resolve_for(config, "dark", "x")["colors"]["ink-strong"], "#0a0a0a")
        theme["dark"]["ink-strong"] = "#f5f7fb"  # light text on a light-blue fill
        with self.assertRaisesRegex(it.ThemeError, "ink-strong contrast"):
            it.validate_theme("x", theme)
        theme["dark"]["ink-strong"] = "black"
        with self.assertRaisesRegex(it.ThemeError, "invalid ink-strong"):
            it.validate_theme("x", theme)
        for falsey in (None, "", False, 0):  # present-but-falsey must not bypass validation
            theme["dark"]["ink-strong"] = falsey
            with self.subTest(value=falsey), self.assertRaisesRegex(it.ThemeError, "invalid ink-strong"):
                it.validate_theme("x", theme)

    def test_existing_project_files_validate_unchanged(self):
        project = REPO / ".github" / "illustration-theme.yml"
        if project.is_file():
            it.validate_config(it.load_yaml(project))
        for path in (REPO / "docs/examples/booking-illustration-theme.yml", ASSETS / "custom-theme.example.yml"):
            if path.is_file():
                theme = it.load_yaml(path)
                it.validate_theme(str(theme.pop("name")), theme)


class Apply(unittest.TestCase):
    def themed(self, theme: str = "cobalt", mode: str = "light", font_loading: str = "remote", source: str = DOC):
        return it.apply_theme(source, it.resolve_for(config_for(theme, mode, font_loading)))

    def test_colors_alpha_and_ink_strong(self):
        colors = it.resolve_for(config_for("cobalt"))["colors"]
        out = self.themed()
        r, g, b = it._hex_rgb(colors["ink"])
        ar, ag, ab = it._hex_rgb(colors["accent"])
        self.assertIn(f'fill="{colors["paper"]}"', out)  # case-insensitive hex
        self.assertIn(f'stroke="{colors["rule"]}"', out)  # role-level rgba maps exactly
        self.assertIn(f"rgba({r},{g},{b},0.40)", out)  # alpha form keeps its alpha
        self.assertIn(f"rgba({ar},{ag},{ab},0.85)", out)
        self.assertIn(f'fill="{colors["ink-strong"]}"', out)
        self.assertIn('fill="#5e7a9b"', out)  # series palette is not a role; untouched
        for literal in ("#f5f5f5", "#2d3142", "#eb6c36", "45,49,66", "235,108,54"):
            self.assertNotIn(literal, out.lower().replace(" ", ""))

    def test_fonts_and_remote_link(self):
        typography = it.resolve_for(config_for("cobalt"))["typography"]
        out = self.themed()
        self.assertNotIn("Geist", out)
        self.assertNotIn("Instrument Serif", out)
        self.assertIn(f"--font-sans: {typography['sans']};", out)
        self.assertIn(f'font-family="{typography["mono"]}"', out)
        self.assertEqual(out.count("fonts.googleapis.com"), 1)
        self.assertIn(typography["remote_css_url"], out)

    def test_font_loading_local_and_system_drop_remote_link(self):
        for loading in ("local", "system"):
            self.assertNotIn("fonts.googleapis.com", self.themed(font_loading=loading))
        # A custom theme with no remote URL drops the link even under `remote`.
        self.assertNotIn("fonts.googleapis.com", self.themed(theme="product-brand"))

    def test_idempotent_and_refuses_rethemed_input(self):
        once = self.themed()
        theme = it.resolve_for(config_for("cobalt"))
        self.assertEqual(it.apply_theme(once, theme), once)
        with self.assertRaisesRegex(it.ThemeError, "already themed as cobalt/light/remote"):
            it.apply_theme(once, it.resolve_for(config_for("emerald")))

    def test_classic_light_is_identity_on_colors(self):
        out = self.themed(theme="classic")
        self.assertIn('fill="#f5f5f5"', out)
        self.assertIn("rgba(45,49,66,0.40)", out)

    def test_dark_mode_uses_dark_table(self):
        colors = it.resolve_for(config_for("emerald", "dark"))["colors"]
        source = DOC.replace("#f5f5f5", "#2d3142").replace('fill="#F5F5F5"', 'fill="#2d3142"')
        out = self.themed("emerald", "dark", source=source)
        self.assertIn(f"--color-paper: {colors['paper']}", out)

    def test_mode_conversion_maps_source_roles_to_output_roles(self):
        roles = ("paper", "ink", "accent")
        for source_name, output_mode in (("example-heatmap.html", "dark"), ("example-heatmap-dark.html", "light")):
            for theme_name in ("cobalt", "emerald", "classic"):
                with self.subTest(source=source_name, theme=theme_name, mode=output_mode):
                    path = ASSETS / source_name
                    theme = it.resolve_for(config_for(theme_name), output_mode, theme_name)
                    out = it.apply_theme(path.read_text(encoding="utf-8"), theme, path)
                    for role in roles:
                        declared = re.search(rf"--color-{role}:\s*(#[0-9a-fA-F]{{6}})", out).group(1)
                        self.assertEqual(declared.lower(), theme["colors"][role].lower(), role)

    def test_cobalt_template_source_is_rethemed(self):
        cobalt = it.registry()["themes"]["cobalt"]
        cobalt_hex = {
            str(v).lower() for mode in ("light", "dark") for v in cobalt[mode].values() if str(v).startswith("#")
        } - set(it.INK_STRONG_CANDIDATES)
        for name in ("template.html", "template-dark.html", "template-full.html", "template-hand.html"):
            for mode in ("light", "dark"):
                with self.subTest(template=name, mode=mode):
                    path = ASSETS / name
                    theme = it.resolve_for(config_for("emerald"), mode, "emerald")
                    out = it.apply_theme(path.read_text(encoding="utf-8"), theme, path)
                    self.assertEqual(sorted(set(re.findall(r"#[0-9a-f]{6}", out.lower())) & cobalt_hex), [])
                    self.assertNotIn("IBM Plex", out)
                    self.assertNotIn("IBM+Plex", out)
                    self.assertIn(theme["typography"]["remote_css_url"], out)
                    self.assertIn('content="emerald/' + mode + '/remote"', out)
                    for role in ("paper", "ink"):
                        found = re.search(rf"--color-{role}:\s*(#[0-9a-fA-F]{{6}})", out)
                        if found:
                            self.assertEqual(found.group(1).lower(), theme["colors"][role].lower())

    def test_double_quoted_font_names(self):
        typography = it.resolve_for(config_for("emerald"), theme="emerald")["typography"]
        source = DOC.replace(
            "--font-sans: 'Geist', system-ui, sans-serif; --font-mono: 'Geist Mono', monospace;",
            '--font-sans: "Geist", system-ui, sans-serif; --font-mono: "Geist Mono", monospace; '
            '--font-serif: "Instrument Serif", serif;',
        ).replace(
            "font-family=\"'Geist Mono', monospace\"", 'font-family="&quot;Geist Mono&quot;, monospace"'
        ).replace(
            "font-family=\"'Geist', sans-serif\"", "font-family='\"IBM Plex Serif\", serif'"
        ) + '<p style="font-family: &quot;Geist&quot;" data-x="#2e5aa8">z</p>'
        out = self.themed("emerald", source=source)
        for role in ("sans", "mono", "serif"):
            self.assertIn(f"--font-{role}: {typography[role]};", out)
        self.assertIn(f'font-family="{typography["mono"]}"', out)
        self.assertIn(f"font-family='{typography['serif'].replace(chr(39), chr(34))}'", out)
        self.assertNotIn("Geist", out)
        self.assertNotIn("Instrument Serif", out)
        self.assertNotIn("IBM Plex", out)
        self.assertIn('data-x="', out)  # a style="..." value never swallows the next attribute

    def test_font_replacement_keeps_attribute_quoting(self):
        class Attrs(HTMLParser):
            def __init__(self):
                super().__init__()
                self.found: dict[str, str] = {}

            def handle_starttag(self, tag, attrs):
                for key, value in attrs:
                    self.found[f"{tag}.{key}"] = value or ""

        stack = it.resolve_for(config_for("emerald"), theme="emerald")["typography"]["sans"]
        first = stack.split(",")[0].strip().strip("'\"")
        for quote, entity in (("'", "&quot;"), ('"', "&quot;"), ("'", ""), ('"', "")):
            name = f"{entity}Geist{entity}" if entity else "Geist"
            body = (
                f"<p title=\"output > input\" style={quote}font-family: {name}; color: #2d3142{quote} data-x=\"1\">z</p>"
                f"<svg><text font-family={quote}{name}, sans-serif{quote} x=\"2\">t</text></svg>"
            )
            with self.subTest(quote=quote, entity=entity):
                out = self.themed("emerald", source=DOC.replace("</body>", body + "</body>"))
                parsed = Attrs()
                parsed.feed(out)
                style = parsed.found["p.style"]
                self.assertIn(first, style)
                self.assertIn("color:", style)
                self.assertEqual(parsed.found["p.data-x"], "1")
                self.assertIn(first, parsed.found["text.font-family"])
                self.assertEqual(parsed.found["text.x"], "2")

    def test_custom_theme_sharing_skin_literals_is_idempotent(self):
        config = config_for("cobalt")
        _, custom = custom_example()
        custom["typography"]["mono"] = "'JetBrains Mono', ui-monospace, monospace"
        custom["dark"]["paper"] = "#0a0a0a"
        config["custom_themes"]["skinlike"] = custom
        theme = it.resolve_for(config, "dark", "skinlike")
        once = it.apply_theme(DOC, theme)
        self.assertIn("JetBrains Mono", once)
        self.assertIn("#0a0a0a", once)
        self.assertEqual(it.apply_theme(once, theme), once)

    def test_refuses_fixed_palettes(self):
        technical = next((ASSETS / "technical-color").rglob("*.html"))
        with self.assertRaisesRegex(it.ThemeError, "technical-color"):
            it.apply_theme(technical.read_text(encoding="utf-8"), it.resolve_for(config_for("cobalt")), technical)
        terminal = ASSETS / "template-terminal.html"
        with self.assertRaisesRegex(it.ThemeError, "terminal"):
            it.apply_theme(terminal.read_text(encoding="utf-8"), it.resolve_for(config_for("cobalt")), terminal)
        # Structure alone identifies the skins, wherever the file lives.
        for skin, label in ((technical, "technical-color"), (terminal, "terminal")):
            with self.assertRaisesRegex(it.ThemeError, label):
                it.apply_theme(skin.read_text(encoding="utf-8"), it.resolve_for(config_for("cobalt")))

    def test_infer_mode(self):
        self.assertEqual(it.infer_mode("", Path("example-bar-dark.html")), "dark")
        self.assertEqual(it.infer_mode("--color-paper: #2d3142;", Path("x.html")), "dark")
        self.assertEqual(it.infer_mode("--paper:#f5f5f5", Path("x.html")), "light")
        self.assertIsNone(it.infer_mode("", Path("x.html")))
        self.assertEqual(it.infer_mode("--color-paper: #101827;", Path("x.html")), "dark")  # cobalt dark
        self.assertEqual(it.infer_mode("--color-paper: #f6f8fc;", Path("x.html")), "light")
        self.assertEqual(it.infer_mode('<meta name="illustration-theme" content="cobalt/dark/remote">'), "dark")

    def test_cli_apply(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "diagram-dark.html"
            source.write_text(DOC, encoding="utf-8")
            run = subprocess.run(
                [sys.executable, str(SCRIPTS / "illustration_theme.py"), "--project-root", scratch,
                 "apply", str(source), "-o", str(root / "out.html")],
                capture_output=True, text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("cobalt/dark", run.stdout)  # no project file: cobalt default, mode from -dark
            self.assertFalse((root / ".github").exists(), "apply must not initialize the project")
            self.assertIn('content="cobalt/dark/remote"', (root / "out.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
