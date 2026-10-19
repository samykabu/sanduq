"""Command text: Update draws with Illustrate's procedure (AU1), handles a current state from one
manual_impact.py call (AU3), and no command names a host-specific form (AU7)."""
import unittest
from pathlib import Path

EXTENSION = Path(__file__).resolve().parents[1]


def text(name):
    return (EXTENSION / f'commands/speckit.user-manual.{name}.md').read_text(encoding='utf-8')


class CommandTextTest(unittest.TestCase):
    def test_diagram_stages_follow_the_illustrate_procedure(self):
        for name in ('analyze', 'update'):
            with self.subTest(name):
                self.assertNotIn('read `SKILL.md` only when', text(name))
        update = text('update')
        self.assertIn('.specify/extensions/illustrate/skill/SKILL.md', update)
        self.assertIn('§0 theme gate', update)
        self.assertIn('§10', update)

    def test_update_computes_status_once_and_handles_current(self):
        update = text('update')
        self.assertNotIn('manual_state.py status', update)
        self.assertEqual(update.count('manual_impact.py --feature'), 1)
        self.assertIn('- `current`: nothing changed since the last record', update)

    def test_host_neutral_names(self):
        for path in [*(EXTENSION / 'commands').glob('*.md'), EXTENSION / 'skills/user-manual/SKILL.ext.md']:
            with self.subTest(path.name):
                self.assertNotIn('UserManual.', path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
