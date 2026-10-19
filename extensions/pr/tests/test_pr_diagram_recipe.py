"""PR4: the diagram recipe names only Illustrate files that exist, lists no diagram types (IL3), and
the command loads it instead of the whole Illustrate skill."""
import re
import unittest
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
SKILL = PR.parent / 'illustrate' / 'skill'
RECIPE = (PR / 'references/pr-diagram-recipe.md').read_text(encoding='utf-8')
COMMAND = (PR / 'commands/speckit.pr.generate.md').read_text(encoding='utf-8')


class RecipeTests(unittest.TestCase):
    def test_every_named_skill_file_exists(self):
        named = set(re.findall(r'<skill>/((?:references|scripts)/[\w.-]+\.(?:md|py))', RECIPE))
        self.assertIn('references/type-index.md', named)
        # shortcut: type-index.md arrives with the upstream IL3 vendor drop; check it once it is vendored
        missing = [n for n in named if not (SKILL / n).is_file() and not (n == 'references/type-index.md')]
        self.assertEqual(missing, [])

    def test_recipe_lists_no_types_and_the_command_loads_it(self):
        self.assertNotRegex(RECIPE, r'type-(?!index)[\w-]+\.md')
        self.assertIn('pr-diagram-recipe.md', COMMAND)
        self.assertNotIn('skill/SKILL.md', COMMAND)
        self.assertNotIn('**Sequence**', COMMAND)
        self.assertLess(len(RECIPE.encode('utf-8')), 2500)


if __name__ == '__main__':
    unittest.main()
