"""The command texts keep the skill's required steps."""

import re
import unittest
from pathlib import Path

EXT_DIR = Path(__file__).resolve().parent.parent


class ImportCommand(unittest.TestCase):
    def test_import_runs_the_skill_step_7_checks(self):
        # SKILL.md step 7 is required for every new diagram, and an imported diagram is new HTML.
        skill = (EXT_DIR / "skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(skill, r"7\. \*\*Verify\.\*\* `python scripts/verify-geometry\.py <file>`, "
                                r"`python scripts/self_check\.py --strict <file>`")
        text = (EXT_DIR / "commands" / "speckit.illustrate.import.md").read_text(encoding="utf-8")
        for check in ("verify-geometry.py <output.html>", "self_check.py --strict <output.html>",
                      "--profile technical-color"):
            self.assertIn(check, re.sub(r"\s+", " ", text))


if __name__ == "__main__":
    unittest.main()
