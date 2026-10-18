"""E6: validate_skills.py applies the Agent Skills frontmatter rules."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_skills as v


class ValidateSkillsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def skill(self, head, body='Body\n', directory='my-skill', name='SKILL.md'):
        path = self.root / directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('---\n' + head + '---\n' + body, encoding='utf-8')
        return v.check(path)

    def test_valid_skill(self):
        result = self.skill('name: my-skill\ndescription: Does a thing.\nmetadata:\n  author: me\ncompatibility: Any\n')
        self.assertEqual((result['errors'], result['warnings']), ([], []))

    def test_name_rules(self):
        for name in ('My-Skill', '-a', 'a-', 'a--b', 'a_b', 'x' * 65, ''):
            result = self.skill(f'name: "{name}"\ndescription: d\n', directory=name or 'empty')
            self.assertTrue(any('name' in e for e in result['errors']), name)
        self.assertIn("name 'other' does not match its directory 'my-skill'",
                      self.skill('name: other\ndescription: d\n')['errors'][0])

    def test_only_allowlisted_source_folders_may_differ_from_the_name(self):
        ext = self.skill('name: speckit-workflow\ndescription: d\n', directory='workflow', name='SKILL.ext.md')
        self.assertEqual((ext['errors'], ext['warnings']), ([], []))
        vendored = self.skill('name: illustrate\ndescription: d\nmetadata:\n  internal: true\n', directory='skill')
        self.assertEqual(vendored['errors'], [])
        self.assertIn('quote it', vendored['warnings'][0])  # the unquoted boolean
        for head, directory in (('name: sanduq-workflow\ndescription: d\n', 'workflow'),
                                ('name: other\ndescription: d\nmetadata:\n  internal: "true"\n', 'skill')):
            self.assertTrue(self.skill(head, directory=directory, name='SKILL.ext.md')['errors'], head)

    def test_description_compatibility_and_metadata(self):
        self.assertTrue(self.skill('name: my-skill\n')['errors'])
        self.assertTrue(self.skill('name: my-skill\ndescription: "' + 'x' * 1025 + '"\n')['errors'])
        self.assertFalse(self.skill('name: my-skill\ndescription: "' + 'x' * 1024 + '"\n')['errors'])
        self.assertTrue(self.skill('name: my-skill\ndescription: d\ncompatibility: "' + 'x' * 501 + '"\n')['errors'])
        self.assertTrue(self.skill('name: my-skill\ndescription: d\nmetadata: [a]\n')['errors'])
        self.assertTrue(self.skill('name: my-skill\ndescription: d\nmetadata:\n  a: {b: c}\n')['errors'])

    def test_frontmatter_problems_and_long_body(self):
        path = self.root / 'my-skill/SKILL.md'
        path.parent.mkdir()
        for text in ('no frontmatter', '---\nname: a\n', '---\n: [\n---\n', '---\n- a\n---\n'):
            path.write_text(text, encoding='utf-8')
            self.assertTrue(v.check(path)['errors'], text)
        long = self.skill('name: my-skill\ndescription: d\n', body='line\n' * 500)
        self.assertEqual(long['errors'], [])
        self.assertIn('500', long['warnings'][0])

    def test_cli_walks_directories_and_exits_on_errors(self):
        self.skill('name: my-skill\ndescription: d\n')
        (self.root / 'node_modules/x').mkdir(parents=True)
        (self.root / 'node_modules/x/SKILL.md').write_text('broken', encoding='utf-8')
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(v.main([str(self.root)]), 0)
        self.assertIn('1 skill files, 0 errors', out.getvalue())
        self.skill('name: Bad\ndescription: d\n', directory='bad')
        with redirect_stdout(io.StringIO()):
            self.assertEqual(v.main([str(self.root), '--json']), 1)


if __name__ == '__main__':
    unittest.main()
