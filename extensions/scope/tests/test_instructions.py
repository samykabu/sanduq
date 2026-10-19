"""Scope instruction text: references resolve, commands that exist, short catalog descriptions (SC1, SC7)."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCOPE = ROOT / 'extensions/scope'
REFERENCES = ROOT / 'extensions/workflow/skills/workflow/references'
TEXT = ([*SCOPE.glob('commands/*.md'), *SCOPE.glob('references/*.md'), *SCOPE.glob('skills/**/*.md'),
         *ROOT.glob('presets/**/*.md')]
        + [REFERENCES / n for n in ('stage-scope.md', 'stage-specify.md', 'stage-clarify.md', 'scope-binding.md')])


class InstructionTests(unittest.TestCase):
    def test_every_named_scope_path_exists(self):
        missing = []
        for path in TEXT:
            for name in re.findall(r'\.specify/extensions/scope/([\w./-]+\.(?:md|py|json))', path.read_text(encoding='utf-8')):
                source = SCOPE / name
                if not (source.is_file() or source.with_name('SKILL.ext.md').is_file() and source.name == 'SKILL.md'):
                    missing.append((path.name, name))
        self.assertEqual(missing, [])

    def test_plan_reads_only_the_plan_reference(self):
        text = (SCOPE / 'commands/plan.md').read_text(encoding='utf-8')
        self.assertNotIn('SKILL.md', text)
        self.assertNotIn('Illustrate skill', text)
        self.assertNotIn('Clarification images', (SCOPE / 'references/illustrate-plan.md').read_text(encoding='utf-8'))

    def test_messages_name_commands_that_exist(self):
        bare = re.compile(r'/speckit-scope(?![\w:-])')
        files = TEXT + [SCOPE / 'scripts/scope.py', SCOPE / 'scripts/clarification.py']
        hits = [(p.name, line.strip()) for p in files for line in p.read_text(encoding='utf-8').splitlines() if bare.search(line)]
        self.assertEqual(hits, [])

    def test_catalog_descriptions_are_short_identical_and_pass_the_benchmark_checks(self):
        sys.path.insert(0, str(ROOT / 'extensions/scripts'))
        try:
            import benchmark_instructions as bench
        except ImportError as error:  # PyYAML missing
            self.skipTest(str(error))
        manifest = (SCOPE / 'extension.yml').read_text(encoding='utf-8')
        entries = re.findall(r'- name: (\S+)\n\s+file: (\S+)\n\s+description: "([^"\n]*)"', manifest)
        self.assertEqual(len(entries), 7)
        self.assertLessEqual(sum(len(d) for _, _, d in entries), 1000)
        for name, file, description in entries:
            front = re.search(r'^description: "([^"\n]*)"', (SCOPE / file).read_text(encoding='utf-8'), re.M)[1]
            self.assertEqual(front, description, name)
            self.assertEqual(bench.failing(bench.describe(description)), [], name)


if __name__ == '__main__':
    unittest.main()
