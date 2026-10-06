"""Per-type verifiers must not claim other types' files.

A file is in a verifier's scope when its stem names the type or it carries the
type's own data-contract marker. Naming another type's shipped example
explicitly must report it as out of scope (exit 0), not fail it as a malformed
instance; the verifier's own example must still be checked and pass, including
under a stem that does not name the type (the marker alone claims it).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _helpers import ASSETS, SCRIPTS

VERIFIERS = (
    "architecture-delta", "axonometric-plan", "exploded", "heatmap",
    "polar", "sankey", "treemap", "waterfall",
)
OTHERS = VERIFIERS + (
    "architecture", "bar", "beeswarm", "bubble", "bump", "flowchart",
    "marimekko", "slopegraph",
)
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def run(kind: str, path: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / f"verify-{kind}.py"), str(path)],
        capture_output=True, text=True, encoding="utf-8", env=ENV,
    )
    return result.returncode, result.stdout + result.stderr


class CrossTypeScope(unittest.TestCase):
    def test_other_types_examples_are_out_of_scope(self):
        for kind in VERIFIERS:
            for other in OTHERS:
                if other == kind:
                    continue
                with self.subTest(verifier=kind, example=other):
                    code, output = run(kind, ASSETS / f"example-{other}.html")
                    self.assertEqual(code, 0, output)
                    self.assertIn("out of scope", output)

    def test_own_example_is_checked_and_passes(self):
        for kind in VERIFIERS:
            with self.subTest(kind=kind):
                code, output = run(kind, ASSETS / f"example-{kind}.html")
                self.assertEqual(code, 0, output)
                self.assertNotIn("out of scope", output)

    def test_marker_claims_file_without_type_stem(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind in VERIFIERS:
                with self.subTest(kind=kind):
                    copy = Path(directory) / "renamed-figure.html"
                    shutil.copyfile(ASSETS / f"example-{kind}.html", copy)
                    code, output = run(kind, copy)
                    self.assertEqual(code, 0, output)
                    self.assertNotIn("out of scope", output)


if __name__ == "__main__":
    unittest.main()


class SankeyProse(unittest.TestCase):
    def test_prose_mentioning_sankey_is_not_claimed(self):
        import subprocess, sys, tempfile
        skill = Path(__file__).resolve().parents[1] / "skill"
        source = (skill / "assets/example-flowchart.html").read_text(encoding="utf-8")
        source = source.replace("</h1>", "</h1><p>The next report is a Sankey diagram.</p>", 1)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "example-flowchart.html"
            target.write_text(source, encoding="utf-8")
            result = subprocess.run([sys.executable, str(skill / "scripts/verify-sankey.py"), str(target)],
                                    capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("out of scope", result.stdout)
