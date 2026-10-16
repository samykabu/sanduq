"""Extension-owned checks. The Progress code, docs and UI are vendored from the sanduq-skills `progress-report` skill
(see vendor.lock.json) and are tested there; these tests cover only what this extension adds: the hook command
template, the host-agnostic skill entry point and the layout Workflow's progress_bridge relies on."""
import importlib.util
import re
import unittest
from pathlib import Path

EXT = Path(__file__).resolve().parents[1]


class ExtensionLayout(unittest.TestCase):
    def test_one_internal_hook_command_outside_the_skill_list(self):
        """Spec Kit registers every `provides.commands` entry as an agent skill; the hook command is found by its file
        name instead (events/__init__.py, `_find_command_template` step 2), so it must not be listed."""
        manifest = (EXT / 'extension.yml').read_text(encoding='utf-8')
        self.assertNotIn('speckit.progress.hook', re.findall(r'^\s+- name: (\S+)', manifest, re.M))
        self.assertEqual(sorted(p.name for p in (EXT / 'commands').glob('speckit.progress.hook*.md')),
                         ['speckit.progress.hook.md'])
        self.assertEqual(set(re.findall(r'^\s+command: (speckit\.progress\.hook\S*)\s*$', manifest, re.M)),
                         {'speckit.progress.hook'})
        self.assertEqual(len(re.findall(r'^  (?:session_start|pre_tool_use|post_tool_use|stop|session_end):', manifest, re.M)), 5)
        text = (EXT / 'commands/speckit.progress.hook.md').read_text(encoding='utf-8')
        self.assertIn('py: hooks/dispatch.py', text)
        self.assertTrue((EXT / 'hooks/dispatch.py').is_file())

    def test_dispatch_reads_the_event_from_the_payload(self):
        spec = importlib.util.spec_from_file_location('dispatch', EXT / 'hooks/dispatch.py')
        dispatch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dispatch)
        for name, event in (('SessionStart', 'session_start'), ('PreToolUse', 'pre_tool_use'),
                            ('PostToolUse', 'post_tool_use'), ('Stop', 'stop'), ('SessionEnd', 'session_end'),
                            ('post_tool_use', 'post_tool_use'), ('Unknown', '')):
            self.assertEqual(dispatch.event_name('{"session_id": "s", "hook_event_name": "%s"}' % name), event)
        self.assertEqual(dispatch.event_name('{}'), '')
        self.assertEqual(dispatch.event_name(''), '')

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
