"""Command text: Update draws with Illustrate's procedure (AU1), handles a current state from one
manual_impact.py call (AU3), and no command names a host-specific form (AU7)."""
import re
import unittest
from pathlib import Path

EXTENSION = Path(__file__).resolve().parents[1]

# Spec Kit 8147943 `rewrite_project_relative_paths` (src/specify_cli/agents.py:219-243), applied to every
# rendered command: a bare scripts/, memory/ or templates/ token becomes this extension's folder.
SPEC_KIT_REWRITE = re.compile(r"""(?:(?<![.\w])(?P<parent>(?:\.\./){2,})|(?P<boundary>^|[\s`"'(\[{<=])"""
                              r"""(?P<rel>\.specify/|(?:\.?/))?)(?P<target>scripts|memory|templates)/""")


def rewritten(source):
    """Tokens Spec Kit would rewrite (an already `.specify/` path is left alone)."""
    return [m.group(0) for m in SPEC_KIT_REWRITE.finditer(source) if m.group('rel') != '.specify/']


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

    def test_spec_kit_rendering_rewrites_no_path(self):
        # AU13a: "its `scripts/` are under ..." rendered as User Manual's own scripts folder.
        for path in (EXTENSION / 'commands').glob('*.md'):
            with self.subTest(path.name):
                self.assertEqual(rewritten(path.read_text(encoding='utf-8')), [])

    def test_analyze_names_its_task_block(self):
        # AU12: a named block, replaced on rerun; Assure's analyze state ignores it (AU16).
        analyze = text('analyze')
        self.assertIn('`<!-- user-manual-tasks:start -->`', analyze)
        self.assertIn('`<!-- user-manual-tasks:end -->`', analyze)
        self.assertIn('replace that\n   block', analyze)

    def test_update_archives_only_for_a_provider(self):
        # AU14: CI builds its own preview archive; locally only an approved provider publishes one.
        update = text('update')
        self.assertIn('build_manual.py --all` once', update)
        self.assertNotIn('--all --archive', update)
        self.assertIn('approved provider; in that case add `--archive`', update)
        self.assertIn('--archive', text('release'))

    def test_dependency_handling_is_one_sentence(self):
        for name in ('analyze', 'update'):
            with self.subTest(name):
                self.assertNotIn('--approve', text(name))
                self.assertIn('report its line, follow it', text(name))


if __name__ == '__main__':
    unittest.main()
