"""Generated hand variants are out of scope for every per-type verifier.

generate-hand-variants.cjs redraws marks as rough.js paths, dropping the data
contract. Naming such a file explicitly must report it as out of scope (exit 0)
rather than claim it and fail; the authored example must still pass.
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

TYPES = (
    "architecture-delta", "axonometric-plan", "beeswarm", "bubble", "bump",
    "exploded", "heatmap", "marimekko", "polar", "ridgeline", "sankey",
    "slopegraph", "streamgraph", "treemap", "waterfall",
)
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def run(kind: str, path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / f"verify-{kind}.py"), str(path)],
        capture_output=True, text=True, encoding="utf-8", env=ENV,
    )


class HandVariantScope(unittest.TestCase):
    def test_explicit_hand_variant_is_out_of_scope(self):
        for kind in TYPES:
            with self.subTest(kind=kind):
                result = run(kind, ASSETS / f"example-{kind}-hand.html")
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self.assertIn("out of scope", output)

    def test_rough_markup_is_out_of_scope_without_hand_stem(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind in TYPES:
                with self.subTest(kind=kind):
                    copy = Path(directory) / f"example-{kind}-sketch.html"
                    shutil.copyfile(ASSETS / f"example-{kind}-hand.html", copy)
                    result = run(kind, copy)
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 0, output)
                    self.assertIn("out of scope", output)

    def test_authored_example_still_passes(self):
        for kind in TYPES:
            with self.subTest(kind=kind):
                result = run(kind, ASSETS / f"example-{kind}.html")
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self.assertNotIn("out of scope", output)


if __name__ == "__main__":
    unittest.main()
