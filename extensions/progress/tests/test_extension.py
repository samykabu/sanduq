"""Extension-owned checks. The Progress code, docs and UI are vendored from the sanduq-skills `progress-report` skill
(see vendor.lock.json) and are tested there; these tests cover only what this extension adds: the hook command
template, the command descriptions, the host-agnostic skill entry point and the layout Workflow's progress_bridge relies on."""
import importlib.util
import re
import tempfile
import unittest
import zipfile
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
        # One interpreter per event: the dispatcher runs scripts/hook.py, which reads the event from the payload.
        self.assertIn('py: scripts/hook.py', text)
        self.assertTrue((EXT / 'scripts/hook.py').is_file())
        self.assertFalse((EXT / 'hooks').exists())

    def test_command_descriptions_are_catalog_entries_and_match_the_manifest(self):
        """Spec Kit renders the command file's description into each host's skill list; extension.yml carries the same."""
        manifest = (EXT / 'extension.yml').read_text(encoding='utf-8')
        entries = re.findall(r'- name: (\S+)\n\s+file: (\S+)\n\s+description: "(.*)"', manifest)
        self.assertEqual(len(entries), 5)
        for name, rel, described in entries:
            front = (EXT / rel).read_text(encoding='utf-8').split('---', 2)[1]
            self.assertEqual(re.search(r'^description: "(.*)"$', front, re.M).group(1), described, name)
            self.assertLess(len(described), 1024, name)
            self.assertRegex(described, r'^[A-Z][a-z]+s\b', name + ': third person, not imperative')
            self.assertIn('Use when', described, name)
            self.assertRegex(described, r"'[^']{4,}'", name + ': a quoted trigger phrase')

    def test_only_init_loads_the_skill(self):
        for path in sorted((EXT / 'commands').glob('*.md')):
            loads = 'skills/progress/SKILL.md' in path.read_text(encoding='utf-8')
            self.assertEqual(loads, path.name == 'init.md', path.name)

    def test_package_leaves_the_screenshots_and_the_unused_skill_copy_out(self):
        spec = importlib.util.spec_from_file_location('package', EXT.parent / 'scripts' / 'package.py')
        package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(package)
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'progress.zip'
            package.package('progress', archive)
            names = zipfile.ZipFile(archive).namelist()
        self.assertNotIn('progress/docs/commands.md', names)  # docs are for maintainers; the package ships what runs
        self.assertFalse([n for n in names if n.startswith(('progress/docs/assets/', 'progress/assets/skill/'))])
        self.assertNotIn('docs/assets/', (EXT / 'README.md').read_text(encoding='utf-8').replace('/progress/docs/assets/', ''))

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
        self.assertIn('deterministic projection', text)
        self.assertRegex(text, r'Never spawn[^.]*agent solely to maintain it')


if __name__ == '__main__':
    unittest.main()
