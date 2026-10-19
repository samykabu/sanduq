"""Command text: diagram stages follow Illustrate's procedure (AU1), Analyze skips an unchanged rerun (AU3),
the audit is not "fix every finding" (AU2), host-neutral names and a skill-free init (AU7)."""
import re
import unittest
from pathlib import Path

EXTENSION = Path(__file__).resolve().parents[1]
COMMANDS = EXTENSION / 'commands'


def text(name):
    return (COMMANDS / f'speckit.assure.{name}.md').read_text(encoding='utf-8')


class CommandTextTest(unittest.TestCase):
    def test_no_stage_skips_the_illustrate_procedure(self):
        for name in ('analyze', 'document', 'init'):
            with self.subTest(name):
                self.assertNotIn('read `SKILL.md` only when', text(name))
        document = text('document')
        self.assertIn('.specify/extensions/illustrate/skill/SKILL.md', document)
        self.assertIn('§0 theme gate', document)
        self.assertIn('§10', document)
        self.assertIn('.specify/extensions/illustrate/skill/scripts/export_diagram.py', document)
        self.assertNotIn('the installed `scripts/export_diagram.py`', document)

    def test_analyze_checks_status_before_loading_anything(self):
        analyze = text('analyze')
        status = analyze.index('assure_state.py status --kind analyze')
        self.assertLess(status, analyze.index('### 0. Load the QA contract'))
        self.assertIn('report "analysis current"', analyze)

    def test_audit_does_not_demand_fixing_every_finding(self):
        self.assertNotIn('Fix every finding', text('document'))

    def test_host_neutral_names_and_a_skill_free_init(self):
        legacy = re.compile(r'Assure\.(Init|Analyze|Document)\b')
        for path in [*COMMANDS.glob('*.md'), EXTENSION / 'extension.yml', EXTENSION / 'README.md',
                     EXTENSION / 'skills/assure/SKILL.ext.md']:
            with self.subTest(path.name):
                self.assertIsNone(legacy.search(path.read_text(encoding='utf-8')))
        self.assertNotIn('SKILL.md', text('init'))


if __name__ == '__main__':
    unittest.main()
