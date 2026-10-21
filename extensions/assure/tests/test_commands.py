"""Command text: diagram stages follow Illustrate's procedure (AU1), Analyze skips an unchanged rerun (AU3),
the audit is not "fix every finding" (AU2), host-neutral names and a skill-free init (AU7)."""
import re
import unittest
from pathlib import Path

EXTENSION = Path(__file__).resolve().parents[1]
COMMANDS = EXTENSION / 'commands'

# Spec Kit 8147943 `rewrite_project_relative_paths` (src/specify_cli/agents.py:219-243), applied to every
# rendered command: a bare scripts/, memory/ or templates/ token becomes this extension's folder.
SPEC_KIT_REWRITE = re.compile(r"""(?:(?<![.\w])(?P<parent>(?:\.\./){2,})|(?P<boundary>^|[\s`"'(\[{<=])"""
                              r"""(?P<rel>\.specify/|(?:\.?/))?)(?P<target>scripts|memory|templates)/""")


def rewritten(source):
    """Tokens Spec Kit would rewrite (an already `.specify/` path is left alone)."""
    return [m.group(0) for m in SPEC_KIT_REWRITE.finditer(source) if m.group('rel') != '.specify/']


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

    def test_spec_kit_rendering_rewrites_no_path(self):
        # AU13a: "Its `scripts/` are under ..." rendered as Assure's own scripts folder.
        for path in COMMANDS.glob('*.md'):
            with self.subTest(path.name):
                self.assertEqual(rewritten(path.read_text(encoding='utf-8')), [])
        self.assertEqual(rewritten('Its `scripts/` are under'), ['`scripts/'])

    def test_dependency_handling_is_one_sentence(self):
        # AU17: deps.py prints the next step itself; the commands carry no per-policy prose.
        for name in ('analyze', 'document'):
            with self.subTest(name):
                self.assertNotIn('--approve', text(name))
                self.assertIn('report its line verbatim, follow it', text(name))

    def test_skill_carries_rules_with_installed_paths(self):
        # AU18: no routing section; script paths resolve from the repository root.
        skill = (EXTENSION / 'skills/assure/SKILL.ext.md').read_text(encoding='utf-8')
        self.assertNotIn('## Route the request', skill)
        for source in (skill, (EXTENSION / 'skills/assure/references/documentation.md').read_text(encoding='utf-8')):
            self.assertIsNone(re.search(r'(?<![/\w])scripts/', source))

    def test_analyze_reads_the_inventory_rows_only(self):
        analyze = text('analyze')
        self.assertIn('assure_scan.py --check\n', analyze)
        self.assertNotIn('--show-block', analyze)


if __name__ == '__main__':
    unittest.main()
