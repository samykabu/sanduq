"""Adversarial tests for verify-geometry.py (ported from diagram-design, MIT)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _helpers import ASSETS, baseline, load

geometry = load("verify-geometry.py")

SVG_HEAD = (
    '<svg viewBox="0 0 400 200" xmlns="http://www.w3.org/2000/svg" role="img" '
    'aria-labelledby="t-title t-desc">'
    '<title id="t-title">T</title><desc id="t-desc">T.</desc>'
)
NODE = '<rect x="100" y="60" width="160" height="64" rx="6" fill="#f5f5f5"/>'
BADGE = '<rect x="108" y="68" width="32" height="12" rx="2" fill="#f5f5f5"/>'
ZONE = '<rect x="80" y="40" width="240" height="120" rx="8" fill="#eee"/>'


def mask(x: int, width: int = 48, height: int = 12, y: int = 80, fill: str = "#f5f5f5") -> str:
    return f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="2" fill="{fill}"/>'


def findings(body: str) -> list[str]:
    with tempfile.TemporaryDirectory() as scratch:
        candidate = Path(scratch) / "candidate.html"
        candidate.write_text(f"<!DOCTYPE html><html><body>{SVG_HEAD}{body}</svg></body></html>", encoding="utf-8")
        return geometry.check(candidate)


class GeometryCases(unittest.TestCase):
    def assertFindings(self, body: str, expected: int) -> None:
        result = findings(body)
        self.assertEqual(len(result), expected, result)

    def test_mask_clipped_by_later_node(self):
        self.assertFindings(mask(240) + NODE, 1)

    def test_mask_over_earlier_node_is_legal(self):
        self.assertFindings(NODE + mask(240), 0)

    def test_badge_inside_node(self):
        self.assertFindings(BADGE + NODE, 0)

    def test_zone_eyebrow(self):
        self.assertFindings(ZONE + mask(160, width=60, y=34), 0)

    def test_mask_clear_of_nodes(self):
        self.assertFindings(mask(10, y=10) + NODE, 0)

    def test_mask_abutting_node_edge(self):
        self.assertFindings(mask(52) + NODE, 0)

    def test_wide_mono_mask_clipped(self):
        self.assertFindings(mask(180, width=128) + NODE, 1)

    def test_wide_mono_mask_over_earlier_node(self):
        self.assertFindings(NODE + mask(180, width=128), 0)

    def test_header_bar_is_not_a_mask(self):
        self.assertFindings(mask(80, width=188, height=16, fill="#eee") + NODE, 0)

    def test_theme_neutral(self):
        # Geometry ignores colour: an applied (cobalt dark) mask is judged exactly like a default one.
        self.assertFindings(mask(240, fill="#101827") + NODE.replace("#f5f5f5", "#101827"), 1)
        self.assertFindings(NODE.replace("#f5f5f5", "#101827") + mask(240, fill="#101827"), 0)


class ShippedAssets(unittest.TestCase):
    """Every shipped asset passes, except the documented legacy baseline (kept honest both ways)."""

    def test_assets_against_baseline(self):
        known = baseline("verify-geometry-baseline.txt")
        failing = {path.name for path in sorted(ASSETS.glob("*.html")) if geometry.check(path)}
        self.assertEqual(sorted(failing - known), [], "new geometry failures (fix the example)")
        self.assertEqual(sorted(known - failing), [],"stale verify-geometry-baseline.txt entries (remove them)")


if __name__ == "__main__":
    unittest.main()
