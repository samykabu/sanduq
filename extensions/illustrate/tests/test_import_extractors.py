"""Stdlib unittest suite for the draw.io / Mermaid / Excalidraw import pipeline.

Run from the extension directory:  python -m unittest discover -s tests -v
Source labels in the fixtures are untrusted data; the adversarial cases prove they stay inert.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skill" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"

CASES = {
    "drawio": ("drawio_extract.py", ["sample-architecture.drawio"]),
    "mermaid": (
        "mermaid_extract.py",
        ["sample-flowchart.mmd", "sample-readme-with-mermaid.md", "sample-adversarial.mmd"],
    ),
    "excalidraw": (
        "excalidraw_extract.py",
        ["sample-whiteboard.excalidraw", "sample-adversarial.excalidraw"],
    ),
}


def run(args: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class ExtractorTests(unittest.TestCase):
    def test_every_fixture_digests(self) -> None:
        for kind, (script, fixtures) in CASES.items():
            for fixture in fixtures:
                with self.subTest(kind=kind, fixture=fixture):
                    proc = run([str(SCRIPTS / script), str(FIXTURES / fixture)])
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertIn("budget:", proc.stdout)
                    self.assertIn("### Nodes", proc.stdout)

    def test_json_ir_is_valid(self) -> None:
        for kind, (script, fixtures) in CASES.items():
            with self.subTest(kind=kind):
                proc = run([str(SCRIPTS / script), str(FIXTURES / fixtures[0]), "--json"])
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIsInstance(json.loads(proc.stdout), dict)

    def test_adversarial_labels_stay_inert(self) -> None:
        for script, fixture in (
            ("mermaid_extract.py", "sample-adversarial.mmd"),
            ("excalidraw_extract.py", "sample-adversarial.excalidraw"),
        ):
            with self.subTest(fixture=fixture):
                out = run([str(SCRIPTS / script), str(FIXTURES / fixture)]).stdout
                # Link targets never reach the digest; URLs inside labels are escaped data,
                # so no live Markdown link or raw HTML can form.
                self.assertNotIn("do-not-follow", out)
                self.assertNotIn("](http", out)
                self.assertNotIn("<br", out)
                self.assertNotIn("<script", out.lower())
                self.assertIn("discarded:", out)

    def test_non_source_input_exits_2(self) -> None:
        for kind, (script, _) in CASES.items():
            with self.subTest(kind=kind):
                proc = run([str(SCRIPTS / script), str(FIXTURES.parent / "test_import_extractors.py")])
                self.assertEqual(proc.returncode, 2, proc.stdout)


def drawio_edge(style: str) -> str:
    """A two-node .drawio with one a->b connector carrying `style`."""
    return (
        '<mxfile><diagram name="p" id="p"><mxGraphModel><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        '<mxCell id="a" value="A" vertex="1" parent="1">'
        '<mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>'
        '<mxCell id="b" value="B" vertex="1" parent="1">'
        '<mxGeometry x="200" y="0" width="80" height="40" as="geometry"/></mxCell>'
        f'<mxCell id="e" edge="1" parent="1" source="a" target="b" style="{style}">'
        '<mxGeometry relative="1" as="geometry"/></mxCell>'
        "</root></mxGraphModel></diagram></mxfile>"
    )


class DrawioArrowheadTests(unittest.TestCase):
    """The tail is the semantic source: arrowheads decide direction, not attribute order."""

    CASES = {
        # style: (source, target, bidirectional, undirected, entry_points, terminals)
        "": ("a", "b", False, False, ["A"], ["B"]),
        "startArrow=classic;endArrow=none": ("b", "a", False, False, ["B"], ["A"]),
        "startArrow=classic;endArrow=classic": ("a", "b", True, False, [], []),
        "startArrow=none;endArrow=none": ("a", "b", False, True, [], []),
    }

    def test_arrowheads_normalize_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edge.drawio"
            for style, (src, tgt, bidi, undirected, entries, terminals) in self.CASES.items():
                with self.subTest(style=style or "default"):
                    path.write_text(drawio_edge(style), encoding="utf-8")
                    proc = run([str(SCRIPTS / "drawio_extract.py"), str(path), "--json"])
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    page = json.loads(proc.stdout)["pages"][0]
                    (edge,) = page["edges"]
                    self.assertEqual((edge["source"], edge["target"]), (src, tgt))
                    self.assertEqual(edge["bidirectional"], bidi)
                    self.assertEqual(edge["undirected"], undirected)
                    self.assertEqual(page["analysis"]["entry_points"], entries)
                    self.assertEqual(page["analysis"]["terminals"], terminals)


class VerifierTests(unittest.TestCase):
    """Full structural gates plus upstream's mutation regressions, on an isolated copy."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="illustrate-import-test-")
        self.clone = Path(self._tmp.name) / "illustrate"
        shutil.copytree(ROOT, self.clone, ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def verify(self, kind: str) -> subprocess.CompletedProcess[str]:
        return run([str(self.clone / "tests" / f"verify-{kind}-import.py")], cwd=self.clone)

    def test_verifiers_pass_on_pristine_tree(self) -> None:
        for kind in CASES:
            with self.subTest(kind=kind):
                proc = self.verify(kind)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_stale_slash_command_is_rejected(self) -> None:
        for kind in ("drawio", "excalidraw"):
            with self.subTest(kind=kind):
                ref = self.clone / "skill" / "references" / f"import-{kind}.md"
                text = ref.read_text(encoding="utf-8")
                valid = f"/illustrate:import-{kind}"
                self.assertIn(valid, text)
                ref.write_text(text.replace(valid, "/illustrate:import"), encoding="utf-8")
                proc = self.verify(kind)
                ref.write_text(text, encoding="utf-8")
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("slash command", proc.stderr)

    def test_elbowed_drawio_worked_example_route_is_rejected(self) -> None:
        example = self.clone / "skill" / "assets" / "example-import-drawio.html"
        text = example.read_text(encoding="utf-8")
        direct = 'd="M560,232 H640"'
        self.assertIn(direct, text)
        example.write_text(text.replace(direct, 'd="M560,232 H592 V252 H640"'), encoding="utf-8")
        proc = self.verify("drawio")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("direct horizontal connector", proc.stderr)

    def test_extra_accent_in_excalidraw_example_is_rejected(self) -> None:
        example = self.clone / "skill" / "assets" / "example-import-excalidraw.html"
        text = example.read_text(encoding="utf-8")
        # A resolved theme accent counts the same as the upstream default literal.
        example.write_text(text.replace("</svg>", '<g fill="#2563eb"/>' * 5 + "</svg>", 1), encoding="utf-8")
        proc = self.verify("excalidraw")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("accent", proc.stderr)


if __name__ == "__main__":
    unittest.main()
