"""Progress as an optional selected extension: install/upgrade offer it, reconcile never disables it."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import install as installer  # noqa: E402
import reconcile as reconciler  # noqa: E402
import upgrade as upgrader  # noqa: E402
import workflow as w  # noqa: E402
import test_install as base  # noqa: E402
import test_workflow as fixture  # noqa: E402

PROGRESS_MANIFEST = Path(__file__).resolve().parents[2] / 'progress' / 'extension.yml'


class OptionalProgressInstall(unittest.TestCase):
    setUp = base.InstallTests.setUp
    configure = fixture.WorkflowTests.configure

    def names(self, result):
        return [op['extension'] for op in result['extensions']]

    def test_dependencies_offer_progress_at_the_version_in_its_manifest(self):
        lock = w.read(Path(__file__).resolve().parents[1] / 'dependencies.json')
        manifest = yaml.safe_load(PROGRESS_MANIFEST.read_text(encoding='utf-8'))['extension']
        self.assertEqual(lock['optional'], {'progress': str(manifest['version'])})
        self.assertNotIn('progress', lock['required'])
        self.assertTrue(all('progress' not in group for group in lock['selected'].values()))

    def test_a_default_install_does_not_add_progress(self):
        result = installer.install(self.root, package_root=self.package)
        self.assertNotIn('progress', self.names(result))
        self.assertEqual(result['optional_extensions'], [])

    def test_with_progress_adds_one_release_install_after_the_required_set(self):
        result = installer.install(self.root, package_root=self.package, with_optional=['progress'])
        names = self.names(result)
        self.assertEqual(names[-1], 'progress')
        operation = result['extensions'][-1]
        self.assertEqual(operation['version'], '1.0.1')
        self.assertEqual(operation['args'][:3], ['specify', 'extension', 'add'])
        self.assertIn('--from', operation['args'])
        self.assertIn('progress-v1.0.1/progress.zip', ' '.join(operation['args']))
        self.assertEqual(result['optional_extensions'], ['progress'])

    def test_an_unknown_optional_name_is_refused(self):
        with self.assertRaisesRegex(w.WorkflowError, 'UNKNOWN_OPTIONAL_EXTENSION: banana'):
            installer.install(self.root, package_root=self.package, with_optional=['banana'])

    def test_an_installed_progress_is_kept_in_step_without_asking_again(self):
        registry = w.registry(self.root)
        registry['progress'] = {'version': '0.9.0', 'enabled': True}
        w.write(self.root / '.specify/extensions/.registry', {'extensions': registry})
        manifest = self.root / '.specify/extensions/progress/extension.yml'
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(yaml.safe_dump({'extension': {'id': 'progress', 'version': '0.9.0',
                                                           'repository': 'https://github.com/samykabu/sanduq'}}), encoding='utf-8')
        result = installer.install(self.root, package_root=self.package)
        self.assertIn('progress', self.names(result))
        self.assertEqual(result['optional_extensions'], ['progress'])

    def test_upgrade_passes_optional_selection_to_the_new_installer(self):
        calls = []

        def runner(root, args, log):
            calls.append(args)
            log.append({'stdout': '{}'})

        current = '1.10.0'
        registry = w.registry(self.root)
        registry['workflow'] = {'version': current, 'enabled': True}
        w.write(self.root / '.specify/extensions/.registry', {'extensions': registry})
        meta = self.root / '.specify/extensions/workflow/extension.yml'
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(yaml.safe_dump({'extension': {'id': 'workflow', 'version': current,
                                                       'repository': 'https://github.com/samykabu/sanduq'}}), encoding='utf-8')
        with patch.object(upgrader, 'delegation_preflight'), patch.object(upgrader, 'snapshot', return_value={}), \
             patch.object(upgrader, 'managed_files', return_value={}):
            try:
                upgrader.upgrade(self.root, current, apply=True, runner=runner, with_optional=['progress'])
            except Exception:
                pass  # the real check follows the installer; only the forwarded flags matter here
        installs = [args for args in calls if any(str(part).endswith('install.py') for part in args)]
        self.assertTrue(installs, calls)
        self.assertIn('--with', installs[0])
        self.assertEqual(installs[0][installs[0].index('--with') + 1], 'progress')


class ReconcileKeepsProgress(unittest.TestCase):
    setUp = fixture.WorkflowTests.setUp
    configure = fixture.WorkflowTests.configure

    def test_progress_hooks_and_events_are_left_enabled_and_byte_identical(self):
        path = self.root / '.specify/extensions.yml'
        document = {
            'hooks': {
                'after_tasks': [{'extension': 'project', 'command': 'speckit.project.sync', 'optional': False},
                                {'extension': 'progress', 'command': 'speckit.progress.init', 'optional': True, 'enabled': True}],
                'after_implement': [{'extension': 'progress', 'command': 'speckit.progress.refresh', 'optional': True, 'enabled': True}]},
            'events': {name: {'extension': 'progress', 'command': 'speckit.progress.hook-' + name.replace('_', '-'), 'enabled': True}
                       for name in ('session_start', 'pre_tool_use', 'post_tool_use', 'stop', 'session_end')}}
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding='utf-8')
        report = reconciler.reconcile(self.root, apply=True)
        self.assertEqual([c['hook'] for c in report['changes']], ['after_tasks:speckit.project.sync'])
        after = yaml.safe_load(path.read_text(encoding='utf-8'))
        self.assertEqual(after['events'], document['events'])
        self.assertEqual(after['hooks']['after_implement'], document['hooks']['after_implement'])
        self.assertEqual(after['hooks']['after_tasks'][1], document['hooks']['after_tasks'][1])
        backup = json.loads((self.root / '.specify/workflow/integration-backup.json').read_text(encoding='utf-8'))
        self.assertFalse([key for key in backup['entries'] if 'progress' in key])
        reconciler.reconcile(self.root, apply=True, restore=True)
        self.assertEqual(yaml.safe_load(path.read_text(encoding='utf-8')), document)


if __name__ == '__main__':
    unittest.main()
