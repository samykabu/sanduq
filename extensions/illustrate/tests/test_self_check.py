"""Adversarial tests for the packaged self_check.py (ported from diagram-design, MIT)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _helpers import ASSETS, baseline, load

self_check = load("self_check.py")

# A minimal static diagram that satisfies the contract; Illustrate's legacy examples predate it.
STATIC = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>T</title>
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400&display=swap" rel="stylesheet">
  <style>body { background: #f5f5f5; }</style>
</head>
<body>
<svg viewBox="0 0 100 50" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="t-title t-desc">
  <title id="t-title">Title</title><desc id="t-desc">Description.</desc>
  <rect x="1" y="1" width="60" height="40" fill="#f5f5f5"/>
</svg>
</body>
</html>
"""
TEMPLATE = ASSETS / "template-motion.html"
ANIMATED = ASSETS / "example-policy-trace-animated.html"


def verify(source: str) -> list[str]:
    with tempfile.TemporaryDirectory() as scratch:
        candidate = Path(scratch) / "candidate.html"
        candidate.write_text(source, encoding="utf-8")
        return self_check.verify(candidate)


class StaticContract(unittest.TestCase):
    def assertRejected(self, source: str, needle: str) -> None:
        errors = verify(source)
        self.assertTrue(any(needle in error for error in errors), f"wanted {needle!r} in {errors}")

    def test_static_passes(self):
        self.assertEqual(verify(STATIC), [])

    def test_css_looking_prose_passes(self):
        self.assertEqual(verify(STATIC.replace("<body>", "<body><p>Document @import and url(x).</p>", 1)), [])

    def test_rejections(self):
        cases = [
            ("<body>", '<body onload="fetch(1)">', "executable attribute"),
            ("<body>", '<body><img src="https://tracker.example/p.gif">', "remote reference"),
            ("</style>", '@import "https://tracker.example/t.css";</style>', "CSS @import"),
            ("</style>", ".t { background: url(https://tracker.example/p.gif); }</style>", "non-fragment CSS url()"),
            ("</style>", '@\\69mport "https://tracker.example/t.css";</style>', "CSS @import"),
            ("</style>", ".t { background: \\75rl(https\\3a //tracker.example/p.gif); }</style>", "non-fragment CSS url()"),
            ("</style>", '.t { background: image-set("https://t.example/p.gif" 1x); }</style>', "CSS image-set()"),
            ("<body>", '<body style="background:url(local.png)">', "non-fragment CSS url()"),
            ("</svg>", '<rect fill="url(https://t.example/p.svg#paint)"></rect></svg>', "non-fragment CSS url()"),
            ("<body>", '<body style="background:url(r.png)" style="background:none">', "non-fragment CSS url()"),
            ("</style>", '.t { content: "/*"; background: url(r.png); --x: "*/"; }</style>', "non-fragment CSS url()"),
            ("https://fonts.googleapis.com/css2", "https://fonts.googleapis.com.evil.tld/css2", "approved Google Fonts"),
            ("<body>", '<body><a href="javascript:alert(1)">x</a>', "executable URL"),
            ("<body>", '<body><a href="data:text/html,x">x</a>', "executable URL"),
            ("<body>", "<body><iframe></iframe>", "not allowed"),
            ("</body>", "<script>alert(1)</script></body>", "canonical data-diagram-controls attribute"),
            ('role="img"', 'role="presentation"', "role=img"),
            ('id="t-title"', 'id="title"', "diagram-prefixed"),
        ]
        for old, new, needle in cases:
            with self.subTest(needle=needle, new=new):
                self.assertRejected(STATIC.replace(old, new, 1), needle)

    def test_css_continuations_normalized(self):
        for newline in ("\n", "\r\n", "\r", "\f"):
            continuation = "\\" + newline
            normalized = self_check.normalize_css_escapes(
                f'url("https:{continuation}/{continuation}/tracker.example/p.gif")'
            )
            self.assertEqual(normalized, 'url("https://tracker.example/p.gif")')

    def test_theme_neutral(self):
        # Applied output (any theme's Google Fonts URL, no Fonts link at all) passes the same contract.
        cobalt = STATIC.replace(
            "css2?family=Geist:wght@400&display=swap", "css2?family=IBM+Plex+Sans:wght@400&display=swap"
        )
        self.assertEqual(verify(cobalt), [])
        self.assertEqual(verify(STATIC.replace(STATIC.splitlines()[5] + "\n", "")), [])


@unittest.skipUnless(TEMPLATE.is_file() and ANIMATED.is_file(), "motion template/example not shipped")
class MotionContract(unittest.TestCase):
    def test_shipped_motion_files_pass(self):
        self.assertEqual(self_check.verify(TEMPLATE), [])
        self.assertEqual(self_check.verify(ANIMATED), [])

    def test_motion_rejections(self):
        animated = ANIMATED.read_text(encoding="utf-8")
        cases = [
            (animated.replace("'motion-ready'", "'motion-ready' /* patched */", 1), "exactly match the controller"),
            (animated.replace("</body>", "<script data-x></script></body>", 1), "at most one script"),
            (
                animated.replace('<g data-motion-item data-step="1"', '<g style="opacity:0" data-motion-item data-step="1"', 1),
                "hidden in source",
            ),
            (animated.replace("<noscript>", "<div>", 1).replace("</noscript>", "</div>", 1), "<noscript>"),
            (animated.replace('data-step-count="5"', 'data-step-count="٥"', 1), "ASCII decimal"),
        ]
        for source, needle in cases:
            with self.subTest(needle=needle):
                errors = verify(source)
                self.assertTrue(any(needle in error for error in errors), f"wanted {needle!r} in {errors}")


class ShippedAssets(unittest.TestCase):
    """Examples and templates pass, except the documented legacy baseline (kept honest both ways)."""

    def test_assets_against_baseline(self):
        known = baseline("self-check-baseline.txt")
        paths = sorted(ASSETS.glob("example-*.html")) + sorted(ASSETS.glob("template*.html"))
        failing = {path.name for path in paths if self_check.verify(path)}
        self.assertEqual(sorted(failing - known), [], "new self_check failures (fix the file)")
        self.assertEqual(sorted(known - failing), [], "stale self-check-baseline.txt entries (remove them)")


if __name__ == "__main__":
    unittest.main()
