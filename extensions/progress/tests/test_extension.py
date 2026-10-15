"""Extension-owned checks. The Progress code, docs and UI are vendored from the sanduq-skills `progress-report` skill
(see vendor.lock.json) and are tested there; these tests cover only what this extension adds: the hook command
templates, the host-agnostic skill entry point and the layout Workflow's progress_bridge relies on."""
import re
import unittest
from pathlib import Path

EXT = Path(__file__).resolve().parents[1]
HOOKS = ('post-tool-use', 'pre-tool-use', 'session-end', 'session-start', 'stop')


class ExtensionLayout(unittest.TestCase):
    def test_hook_commands_use_the_fast_entry(self):
        files = sorted((EXT / 'commands').glob('hook-*.md'))
        self.assertEqual([f.stem for f in files], ['hook-' + name for name in HOOKS])
        for path in files:
            self.assertIn('scripts/hook.py ', path.read_text(encoding='utf-8'), path.name)

    def test_every_manifest_command_has_a_file(self):
        manifest = (EXT / 'extension.yml').read_text(encoding='utf-8')
        for rel in re.findall(r'^\s+file:\s*"?([^"\n]+)"?\s*$', manifest, re.M):
            self.assertTrue((EXT / rel).is_file(), rel)

    def test_stable_paths_for_workflow_and_docs(self):
        for rel in ('scripts/progress.py', 'scripts/hook.py', 'scripts/sanduq_progress/hooks_install.py',
                    'scripts/sanduq_progress/collect/plan.py', 'assets/ui/index.html',
                    'skills/progress/references/verbs.md', 'docs/commands.md'):
            self.assertTrue((EXT / rel).is_file(), rel)

    def test_skill_entry_is_short_and_deterministic(self):
        text = (EXT / 'skills/progress/SKILL.ext.md').read_text(encoding='utf-8')
        self.assertLessEqual(len(text.splitlines()), 60)
        self.assertIn('Reporting is a deterministic projection. Never spawn, retain, message or poll an agent solely to '
                      'maintain it.', text)


if __name__ == '__main__':
    unittest.main()
