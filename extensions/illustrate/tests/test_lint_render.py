"""lint-render.py self-test (needs Playwright + Chromium; skipped cleanly when unavailable)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import unittest

from _helpers import SCRIPTS

HAVE_PLAYWRIGHT = importlib.util.find_spec("playwright") is not None


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright not installed (pip install playwright && playwright install chromium)")
class LintRenderSelfTest(unittest.TestCase):
    def test_self_test(self):
        run = subprocess.run(
            [sys.executable, str(SCRIPTS / "lint-render.py"), "--self-test"],
            capture_output=True, text=True, timeout=900,
        )
        if run.returncode == 2 and "Could not launch a browser" in run.stderr and not os.environ.get("CI"):
            self.skipTest("Chromium not installed (playwright install chromium)")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
