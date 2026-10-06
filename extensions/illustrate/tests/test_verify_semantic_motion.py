#!/usr/bin/env python3
"""Both-polarity tests for verify-semantic-motion.py.

Usage: python -m unittest discover -s tests -p test_verify_semantic_motion.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "skill"
VERIFIER = ROOT / "scripts/verify-semantic-motion.py"


def load_verifier():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("illustrate_verify_semantic_motion", VERIFIER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifySemanticMotionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_verifier()
        self.tmp = tempfile.TemporaryDirectory(prefix="verify-semantic-motion-")
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_shipped_docs_and_example_pass(self) -> None:
        self.assertEqual(self.module.verify_markdown(), [])
        self.assertEqual(self.module.verify_example(), [])

    def test_animation_missing_mode_is_rejected(self) -> None:
        text = self.module.ANIMATION.read_text(encoding="utf-8").replace("`loop`", "`cycle`")
        self.module.ANIMATION = self.write("animation.md", text)
        self.assertIn("animation.md is missing mode loop", self.module.verify_markdown())

    def test_animation_missing_primitive_is_rejected(self) -> None:
        text = self.module.ANIMATION.read_text(encoding="utf-8").replace("**Audit append**", "Audit append")
        self.module.ANIMATION = self.write("animation.md", text)
        self.assertIn("animation.md is missing primitive Audit append", self.module.verify_markdown())

    def test_pattern_missing_field_is_rejected(self) -> None:
        if not self.module.PATTERNS.exists():
            self.skipTest("semantic-patterns.md not shipped")
        text = self.module.PATTERNS.read_text(encoding="utf-8").replace("**Static fallback:**", "Static fallback:", 1)
        self.module.PATTERNS = self.write("semantic-patterns.md", text)
        self.assertTrue(any("missing required field Static fallback:" in e for e in self.module.verify_markdown()))

    def test_duplicate_id_is_rejected(self) -> None:
        source = self.module.EXAMPLE.read_text(encoding="utf-8")
        start = source.index(' id="') + len(' id="')
        duplicated = source[start:source.index('"', start)]
        cut = source.rindex("</body>")
        broken = self.write("duplicate-id.html", source[:cut] + f'<div id="{duplicated}"></div>' + source[cut:])
        self.assertTrue(any("duplicate HTML/SVG IDs" in e for e in self.module.verify_example(broken)))

    def test_missing_not_reached_state_is_rejected(self) -> None:
        source = self.module.EXAMPLE.read_text(encoding="utf-8")
        broken = self.write("no-not-reached.html", source.replace('data-trace-b-state="not-reached"', "", 1))
        self.assertTrue(any("Trace B needs" in e for e in self.module.verify_example(broken)))


if __name__ == "__main__":
    unittest.main()
