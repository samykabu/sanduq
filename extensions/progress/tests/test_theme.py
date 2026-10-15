import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from sanduq_progress import theme  # noqa: E402

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def run_cli(root, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = theme.cli(list(argv), project_root=root)
    return code, buf.getvalue().strip()


class PresetTests(unittest.TestCase):
    def test_presets_complete_and_valid(self):
        self.assertEqual(set(theme.PRESETS), {"sanduq", "cobalt", "emerald", "classic"})
        for name, modes in theme.PRESETS.items():
            for mode in ("light", "dark"):
                self.assertEqual(set(modes[mode]), set(theme.TOKEN_KEYS), (name, mode))
                for key, val in modes[mode].items():
                    self.assertRegex(val, HEX, (name, mode, key))

    def test_sanduq_matches_legacy_palette(self):
        light = theme.PRESETS["sanduq"]["light"]
        self.assertEqual((light["bg"], light["text"], light["brand"], light["accent"]),
                         ("#f6f7f4", "#1b2a24", "#233c32", "#c65b36"))
        self.assertEqual(theme.PRESETS["sanduq"]["dark"]["bg"], "#121916")

    def test_illustrate_derived_values(self):
        self.assertEqual(theme.PRESETS["cobalt"]["light"]["accent"], "#2563eb")
        self.assertEqual(theme.PRESETS["emerald"]["dark"]["bg"], "#10231e")
        self.assertEqual(theme.PRESETS["classic"]["light"]["accent"], "#eb6c36")


class ValidationTests(unittest.TestCase):
    def bad(self, doc, fragment):
        with self.assertRaises(theme.ThemeError) as cm:
            theme.validate(doc)
        self.assertIn(fragment, str(cm.exception))

    def test_accepts_minimal_and_short_hex(self):
        theme.validate({})
        theme.validate({"v": 1, "preset": "cobalt", "tokens": {"light": {"bg": "#fff"}}})

    def test_rejects_unknown_keys_and_values(self):
        self.bad({"extra": 1}, "unknown key extra")
        self.bad({"preset": "neon"}, "unknown preset")
        self.bad({"density": "huge"}, "density")
        self.bad({"blocks": ["header", "nope"]}, "blocks")
        self.bad({"hidden": ["lanes", "lanes"]}, "hidden")
        self.bad({"tokens": {"sepia": {}}}, "tokens")
        self.bad({"tokens": {"light": {"sparkle": "#fff"}}}, "unknown token")
        self.bad({"tokens": {"light": {"bg": "red"}}}, "#rgb or #rrggbb")
        self.bad({"tokens": {"light": {"bg": "#ggg"}}}, "#rgb or #rrggbb")
        self.bad({"tokens": {"light": {"bg": "rgba(0,0,0,.1)"}}}, "#rgb or #rrggbb")
        self.bad({"font": {"serif": "x"}}, "font")
        self.bad({"font": {"sans": "x;} body{display:none"}}, "font")
        self.bad({"v": 2}, "version")
        self.bad([], "object")

    def test_resolve_overlays_and_orders_blocks(self):
        r = theme.resolve_doc({"preset": "emerald", "blocks": ["events", "header"], "hidden": ["decisions"],
                               "tokens": {"dark": {"accent": "#abc"}}, "density": "compact"})
        self.assertEqual(r["blocks"][:2], ["events", "header"])
        self.assertEqual(set(r["blocks"]), set(theme.BLOCKS))
        self.assertEqual(r["tokens"]["dark"]["accent"], "#abc")
        self.assertEqual(r["tokens"]["light"]["accent"], theme.PRESETS["emerald"]["light"]["accent"])

    def test_resolve_project_default_and_file(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(theme.resolve(d)["preset"], "sanduq")
            p = Path(d, ".specify", "progress")
            p.mkdir(parents=True)
            (p / "theme.json").write_text('{"preset":"classic"}', encoding="utf-8")
            self.assertEqual(theme.resolve(d)["preset"], "classic")
            (p / "theme.json").write_text('{"preset":"classic",', encoding="utf-8")
            with self.assertRaises(theme.ThemeError):
                theme.resolve(d)


class RenderTests(unittest.TestCase):
    def test_css_only_custom_properties(self):
        css = theme.render_css(theme.resolve_doc({"density": "compact"}))
        self.assertIn("prefers-color-scheme:dark", css)
        self.assertIn("--bg:#f6f7f4", css)
        self.assertIn("--bg:#121916", css)
        self.assertIn("--pad:6px", css)
        body = re.sub(r"/\*.*?\*/|@media[^{]*", "", css, flags=re.S)
        for decl in re.findall(r"\{([^{}]*)\}", body):
            for part in filter(None, decl.split(";")):
                self.assertTrue(part.startswith(("--", "color-scheme")), part)

    def test_layout_js(self):
        r = theme.resolve_doc({"blocks": ["events"], "hidden": ["lanes"], "title": "A </script> B"})
        js = theme.render_layout(r)
        self.assertTrue(js.startswith("window.__SANDUQ_PROGRESS_LAYOUT__="))
        self.assertNotIn("</script", js)
        payload = json.loads(js[len("window.__SANDUQ_PROGRESS_LAYOUT__="):].rstrip(";\n").replace("<\\/", "</"))
        self.assertEqual(payload["blocks"][0], "events")
        self.assertNotIn("lanes", payload["blocks"])
        self.assertEqual(payload["hidden"], ["lanes"])
        self.assertEqual(payload["title"], "A </script> B")

    def test_write_assets_atomic(self):
        with tempfile.TemporaryDirectory() as d:
            view = Path(d, "x", ".view")
            theme.write_assets(view, theme.resolve_doc({}))
            self.assertTrue((view / "theme.css").read_text(encoding="utf-8").startswith("/*"))
            self.assertIn("LAYOUT", (view / "layout.js").read_text(encoding="utf-8"))
            self.assertEqual([p.name for p in view.iterdir() if p.suffix == ".tmp"], [])


class IllustrateTests(unittest.TestCase):
    def project(self, d, body):
        gh = Path(d, ".github")
        gh.mkdir()
        (gh / "illustration-theme.yml").write_text(body, encoding="utf-8")

    def test_mapping(self):
        with tempfile.TemporaryDirectory() as d:
            self.project(d, 'schema_version: "1.0"\nactive:\n  theme: "cobalt"  # pin\n  mode: "light"\n  font_loading: "remote"\ncustom_themes: {}\n')
            self.assertEqual(theme.read_illustrate(d), {"theme": "cobalt", "mode": "light"})
            doc = theme.from_illustrate(d)
            light = doc["tokens"]["light"]
            self.assertEqual(light["bg"], "#f6f8fc")
            self.assertEqual(light["surface"], "#ffffff")
            self.assertEqual(light["text"], "#15233c")
            self.assertEqual(light["line"], "#c7d2e2")
            self.assertEqual(light["accent"], "#2563eb")
            self.assertEqual(light["brand"], "#1d4ed8")
            self.assertRegex(light["active"], HEX)
            self.assertNotEqual(light["active"], light["accent"])
            self.assertNotIn("done", light)  # status colours stay with the preset
            theme.validate(doc)

    def test_errors(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(theme.ThemeError):
                theme.from_illustrate(d)
            self.project(d, 'active:\n  theme: "mine"\n')
            with self.assertRaises(theme.ThemeError):
                theme.from_illustrate(d)


class CliTests(unittest.TestCase):
    def test_preset_writes_and_refreshes_views(self):
        with tempfile.TemporaryDirectory() as d:
            view = Path(d, "specs", "001-x", "progress", ".view")
            view.mkdir(parents=True)
            code, out = run_cli(d, "--preset", "emerald")
            self.assertEqual((code, out), (0, "progress: theme emerald"))
            stored = json.loads(Path(d, ".specify", "progress", "theme.json").read_text(encoding="utf-8"))
            self.assertEqual(stored, {"v": 1, "preset": "emerald"})
            self.assertIn("--accent:#0f8a64", (view / "theme.css").read_text(encoding="utf-8"))

    def test_show(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = run_cli(d, "--show")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["preset"], "sanduq")

    def test_file_and_errors(self):
        with tempfile.TemporaryDirectory() as d:
            good = Path(d, "t.json")
            good.write_text(json.dumps({"preset": "classic", "hidden": ["events"]}), encoding="utf-8")
            self.assertEqual(run_cli(d, "--file", str(good)), (0, "progress: theme classic"))
            bad = Path(d, "bad.json")
            bad.write_text(json.dumps({"tokens": {"light": {"bg": "red"}}}), encoding="utf-8")
            code, out = run_cli(d, "--file", str(bad))
            self.assertEqual(code, 2)
            self.assertTrue(out.startswith("progress: error PROGRESS_THEME_INVALID "), out)
            code, out = run_cli(d, "--preset", "neon")
            self.assertEqual(code, 2)
            self.assertTrue(out.startswith("progress: error PROGRESS_THEME_INVALID "))
            code, out = run_cli(d, "--file", str(Path(d, "missing.json")))
            self.assertEqual(code, 2)
            self.assertEqual(run_cli(d)[0], 2)
            # the stored theme was not damaged by failures
            self.assertEqual(theme.resolve(d)["preset"], "classic")

    def test_from_illustrate(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run_cli(d, "--from-illustrate")[0], 2)
            gh = Path(d, ".github")
            gh.mkdir()
            (gh / "illustration-theme.yml").write_text('active:\n  theme: emerald\n  mode: dark\n', encoding="utf-8")
            self.assertEqual(run_cli(d, "--from-illustrate"), (0, "progress: theme emerald"))
            self.assertEqual(theme.resolve(d)["tokens"]["light"]["bg"], "#f4f8f5")


class VerbTests(unittest.TestCase):
    """The progress verbs around theme: init validation and the project-level theme verb."""

    def setUp(self):
        sys.path.insert(0, str(HERE))
        import helpers
        self.helpers = helpers

    def make(self):
        case = self.helpers.Project("setUp")
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def test_init_bad_theme_creates_nothing(self):
        p = self.make()
        code, out = p.cli("init", "--theme", "BAD")
        self.assertEqual(code, 2)
        self.assertEqual(out, "progress: error PROGRESS_THEME_INVALID unknown preset BAD")
        self.assertFalse((p.feature_dir / "progress").exists())
        self.assertFalse((p.root / ".specify" / "progress").exists())

    def test_init_good_theme_prints_one_line(self):
        p = self.make()
        code, out = p.cli("init", "--theme", "cobalt")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 1)
        self.assertTrue(out.startswith("progress: ready "))
        self.assertEqual(theme.resolve(p.root)["preset"], "cobalt")

    def test_theme_verb_without_initialised_feature(self):
        p = self.make()
        self.assertEqual(p.cli("theme", "--preset", "emerald"), (0, "progress: theme emerald"))
        self.assertEqual(json.loads(p.cli("theme", "--show")[1])["preset"], "emerald")
        self.assertFalse((p.feature_dir / "progress").exists())
        code, out = p.cli("theme", "--help")
        self.assertEqual(code, 0)
        self.assertIn("--preset NAME", out)

    def test_theme_verb_refreshes_only_existing_views(self):
        p = self.make()
        p.init()
        other = p.root / "specs" / "002-other"
        other.mkdir()
        self.assertEqual(p.cli("theme", "--preset", "classic")[0], 0)
        self.assertIn("--bg:#f5f5f5", (p.feature_dir / "progress" / ".view" / "theme.css").read_text(encoding="utf-8"))
        self.assertFalse((other / "progress").exists())

    def test_config_has_no_feature_dir_mode_but_old_one_is_read(self):
        p = self.make()
        p.init()
        self.assertNotIn("feature_dir_mode", json.loads(p.ctx.config.read_text(encoding="utf-8")))
        p.ctx.config.write_text(json.dumps({"feature_dir_mode": "auto", "debounce_seconds": 7}), encoding="utf-8")
        self.assertEqual(p.ctx.config_data()["debounce_seconds"], 7)


if __name__ == "__main__":
    unittest.main()
