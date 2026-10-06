"""SKILL.md frontmatter stays loadable: hosts drop or truncate descriptions over 1024 characters."""

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skill" / "SKILL.md"


class SkillFrontmatter(unittest.TestCase):
    def test_description_is_valid_and_bounded(self):
        text = SKILL.read_text(encoding="utf-8")
        match = re.match(r"---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(match, "SKILL.md must open with a frontmatter block")
        fields = dict(re.findall(r"^(\w+): (.*)$", match.group(1), re.M))
        self.assertEqual(fields.get("name"), "illustrate")
        description = fields.get("description", "")
        if description.startswith('"'):
            self.assertTrue(description.endswith('"'), "quoted description must close its quote")
            description = description[1:-1].replace('\\"', '"')
        else:
            self.assertNotIn(": ", description, "unquoted ': ' breaks YAML; quote the description")
        self.assertLessEqual(len(description), 1024)
        for trigger in ("diagram", "chart", "illustrat", ".drawio", ".excalidraw"):
            self.assertIn(trigger, description)


if __name__ == "__main__":
    unittest.main()
