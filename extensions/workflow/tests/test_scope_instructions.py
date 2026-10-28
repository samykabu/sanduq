"""Scope instruction text: references resolve, commands that exist, short catalog descriptions (SC1, SC7)."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCOPE = ROOT / 'extensions/workflow'  # Scope's commands, references and skills are Workflow's (DEC-03)
REFERENCES = ROOT / 'extensions/workflow/skills/workflow/references'
TEXT = ([*SCOPE.glob('commands/*scope-*.md'), *SCOPE.glob('references/*.md'),
         *SCOPE.glob('skills/scope-analyst/**/*.md'), *SCOPE.glob('skills/github-clarification/**/*.md'),
         *ROOT.glob('presets/**/*.md')]
        + [REFERENCES / n for n in ('stage-scope.md', 'stage-specify.md', 'stage-clarify.md', 'scope-binding.md')])


class InstructionTests(unittest.TestCase):
    def test_every_named_scope_path_exists(self):
        missing = []
        for path in TEXT:
            for name in re.findall(r'\.specify/extensions/workflow/([\w./-]+\.(?:md|py|json))', path.read_text(encoding='utf-8')):
                source = SCOPE / name
                if not (source.is_file() or source.with_name('SKILL.ext.md').is_file() and source.name == 'SKILL.md'):
                    missing.append((path.name, name))
        self.assertEqual(missing, [])

    def test_plan_reads_only_the_plan_reference(self):
        text = (SCOPE / 'commands/scope-plan.md').read_text(encoding='utf-8')
        self.assertNotIn('SKILL.md', text)
        self.assertNotIn('Illustrate skill', text)
        self.assertNotIn('Clarification images', (SCOPE / 'references/illustrate-plan.md').read_text(encoding='utf-8'))

    def test_messages_name_commands_that_exist(self):
        bare = re.compile(r'/speckit-scope(?![\w:-])')
        files = TEXT + [SCOPE / 'scripts/scope/scope.py', SCOPE / 'scripts/scope/clarification.py']
        hits = [(p.name, line.strip()) for p in files for line in p.read_text(encoding='utf-8').splitlines() if bare.search(line)]
        self.assertEqual(hits, [])

    def test_catalog_descriptions_are_short_identical_and_pass_the_benchmark_checks(self):
        sys.path.insert(0, str(ROOT / 'extensions/scripts'))
        try:
            import benchmark_instructions as bench
        except ImportError as error:  # PyYAML missing
            self.skipTest(str(error))
        manifest = (SCOPE / 'extension.yml').read_text(encoding='utf-8')
        entries = [entry for entry in re.findall(r'- name: (\S+)\n\s+file: (\S+)\n\s+description: "([^"\n]*)"', manifest)
                   if entry[0].startswith('speckit.workflow.scope-')]
        # the five hook commands are not skills (OMAR-09)
        self.assertEqual([name for name, _, _ in entries], ['speckit.workflow.scope-run', 'speckit.workflow.scope-plan'])
        hooks = re.findall(r'command: (speckit\.workflow\.scope-\S+)$', manifest, re.M)
        self.assertEqual(sorted(hooks), ['speckit.workflow.scope-after-specify', 'speckit.workflow.scope-bind', 'speckit.workflow.scope-guard',
                                         'speckit.workflow.scope-plan-guard', 'speckit.workflow.scope-reconcile'])
        for hook in hooks:  # found by the event dispatcher through the on-disk file name
            self.assertTrue((SCOPE / 'commands' / (hook + '.md')).is_file(), hook)
            self.assertNotIn(hook, [name for name, _, _ in entries])
        self.assertLessEqual(sum(len(d) for _, _, d in entries), 1000)
        for name, file, description in entries:
            front = re.search(r'^description: "([^"\n]*)"', (SCOPE / file).read_text(encoding='utf-8'), re.M)[1]
            self.assertEqual(front, description, name)
            self.assertEqual(bench.failing(bench.describe(description)), [], name)


def render(command, presets):
    """A command as Spec Kit composes it, top preset first: `prepend` layers stack, a `replace` layer ends the
    stack, and 'UPSTREAM' stands in for the core or extension command under them."""
    import yaml
    parts = []
    for preset in presets:
        manifest = yaml.safe_load((ROOT / 'presets' / preset / 'preset.yml').read_text(encoding='utf-8'))
        entry = next((t for t in manifest['provides']['templates'] if t['name'] == command), None)
        if entry:
            parts.append((ROOT / 'presets' / preset / entry['file']).read_text(encoding='utf-8').split('---', 2)[2])
            if entry['strategy'] == 'replace':
                return '\n'.join(parts)
    return '\n'.join(parts + ['UPSTREAM'])


class RenderedProcedureTests(unittest.TestCase):
    """SC17: unmanaged and managed Clarify and Brainstorm render without upstream text, and the coverage
    categories exist once in the files a Clarify or Brainstorm stage reads."""
    SKILL = SCOPE / 'skills/github-clarification'
    CASES = {('speckit.clarify', 'clarify'): ('scope-gate',),
             ('speckit.superspec.brainstorm', 'brainstorm'): ('scope-brainstorm',)}

    def setUp(self):
        try:
            import yaml  # noqa: F401
        except ImportError as error:
            self.skipTest(str(error))

    def stage_files(self, rendered, managed):
        texts = [rendered, (self.SKILL / 'SKILL.ext.md').read_text(encoding='utf-8')]
        texts += [p.read_text(encoding='utf-8') for p in sorted((self.SKILL / 'references').glob('*.md'))]
        if managed:
            texts.append((REFERENCES / 'stage-clarify.md').read_text(encoding='utf-8'))
        return ' '.join('\n'.join(texts).lower().split())

    def test_rendered_procedures(self):
        for (command, engine), scope_presets in self.CASES.items():
            for managed in (False, True):
                presets = ('workflow',) + scope_presets if managed else scope_presets
                text = render(command, presets)
                with self.subTest(command=command, managed=managed):
                    self.assertNotIn('UPSTREAM', text)
                    self.assertIn('.specify/extensions/workflow/skills/github-clarification/SKILL.md', text)
                    self.assertIn(f'`engine: {engine}`', text)
                    self.assertIn('STOP', text)
                    self.assertNotIn('Managed workflow precedence', text)
                    self.assertLess(len(text.encode('utf-8')), 1700)
                    if managed:
                        self.assertIn('#managed-overlay-contract', text)
                        self.assertIn('stage-clarify.md', text)
                    files = self.stage_files(text, managed)
                    for phrase in ('identity and uniqueness', 'edge-of-range input', 'open questions table'):
                        self.assertEqual(files.count(phrase), 1, phrase)


if __name__ == '__main__':
    unittest.main()
