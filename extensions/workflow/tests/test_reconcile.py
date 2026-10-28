import copy
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from reconcile import reconcile, managed_hook
import test_workflow as fixture
import workflow as w

class ReconcileTests(unittest.TestCase):
    setUp = fixture.WorkflowTests.setUp
    configure = fixture.WorkflowTests.configure

    def metadata_drift(self, originally_enabled=True):
        hook = {'extension': 'project', 'command': 'speckit.project.sync', 'enabled': originally_enabled,
                'optional': False, 'condition': 'feature_exists', 'priority': 10,
                'prompt': 'Old prompt', 'description': 'Old description'}
        unrelated = {'extension': 'custom', 'command': 'custom.check', 'enabled': True}
        self._hooks({'hooks': {'after_tasks': [hook], 'after_implement': [unrelated]}})
        reconcile(self.root, apply=True)
        current = self._hooks()
        current['hooks']['after_tasks'][0].update(prompt='Current prompt', description='Current description')
        self._hooks(current)
        self.manifest_path = self.root / '.specify/extensions/project/extension.yml'
        manifest_hook = {k: v for k, v in current['hooks']['after_tasks'][0].items() if k not in ('extension', 'enabled')}
        self.manifest_path.write_text(yaml.safe_dump({'extension': {'id': 'project', 'version': '2.6.1'},
                                                    'hooks': {'after_tasks': manifest_hook}}), encoding='utf-8')
        return hook, unrelated

    def test_disabled_manifest_metadata_preview_apply_audit_idempotence_and_restore(self):
        for originally_enabled in (True, False):
            with self.subTest(originally_enabled=originally_enabled):
                original, unrelated = self.metadata_drift(originally_enabled)
                backup = self.root / '.specify/workflow/integration-backup.json'
                config = self.root / '.specify/extensions.yml'
                before = config.read_bytes(), backup.read_bytes()
                preview = reconcile(self.root)
                self.assertEqual(before, (config.read_bytes(), backup.read_bytes()))
                self.assertIn('metadata_refresh', preview['changes'][0])
                report = reconcile(self.root, apply=True)
                record = w.read(backup)['entries']['after_tasks:speckit.project.sync']
                audit, = record['metadata_refreshes']
                self.assertEqual('Old prompt', audit['before']['prompt'])
                self.assertEqual('Current prompt', audit['after']['prompt'])
                self.assertIs(record['original']['enabled'], originally_enabled)
                self.assertFalse(record['managed']['enabled'])
                self.assertEqual(unrelated, self._hooks()['hooks']['after_implement'][0])
                journal_bytes = backup.read_bytes()
                self.assertEqual([], reconcile(self.root, apply=True)['changes'])
                self.assertEqual(journal_bytes, backup.read_bytes())
                self.assertEqual(record, w.read(backup)['entries']['after_tasks:speckit.project.sync'])
                reconcile(self.root, apply=True, restore=True)
                restored = self._hooks()['hooks']['after_tasks'][0]
                self.assertEqual({**original, 'prompt': 'Current prompt', 'description': 'Current description'}, restored)
                self.assertFalse(backup.exists())

    def test_disabled_metadata_refresh_rejects_operational_edits_and_untrusted_manifests(self):
        self.metadata_drift()
        good = self._hooks()
        manifest = self.manifest_path.read_bytes()
        backup = self.root / '.specify/workflow/integration-backup.json'
        for key, value in [('optional', True), ('condition', 'other'), ('priority', 99),
                           ('extension', 'assure'), ('extension', 'custom'),
                           ('command', 'speckit.project.other'), ('unknown', 'value'), ('prompt', 'User text')]:
            with self.subTest(field=key):
                changed = copy.deepcopy(good)
                changed['hooks']['after_tasks'][0][key] = value
                self._hooks(changed)
                before = (self.root / '.specify/extensions.yml').read_bytes(), backup.read_bytes()
                for restore in (False, True):
                    with self.assertRaisesRegex(w.WorkflowError, 'HOOK_CHANGED_SINCE_RECONCILE'):
                        reconcile(self.root, apply=True, restore=restore)
                    self.assertEqual(before, ((self.root / '.specify/extensions.yml').read_bytes(), backup.read_bytes()))
        self._hooks(good)
        journal = w.read(backup)
        journal['entries']['after_tasks:speckit.project.sync']['original']['priority'] = 99
        w.write(backup, journal)
        with self.assertRaisesRegex(w.WorkflowError, 'HOOK_CHANGED_SINCE_RECONCILE'):
            reconcile(self.root, apply=True)
        journal['entries']['after_tasks:speckit.project.sync']['original']['priority'] = 10
        w.write(backup, journal)
        metadata = yaml.safe_load(manifest)
        for content in (None, b'extension: {id: other}\n', b'not: a manifest\n',
                        yaml.safe_dump({**metadata, 'hooks': {'after_tasks': [metadata['hooks']['after_tasks']] * 2}}).encode()):
            with self.subTest(manifest=content):
                if content is None:
                    self.manifest_path.unlink(missing_ok=True)
                else:
                    self.manifest_path.write_bytes(content)
                with self.assertRaisesRegex(w.WorkflowError, 'HOOK_CHANGED_SINCE_RECONCILE'):
                    reconcile(self.root, apply=True)

    def test_packaged_public_cli_repairs_metadata_for_original_restore(self):
        self.metadata_drift(originally_enabled=False)
        package = Path(os.environ.get('SANDUQ_WORKFLOW_TEST_PACKAGE', Path(__file__).resolve().parents[1]))
        argv = [sys.executable, str(package / 'scripts/reconcile.py'), '--root', str(self.root)]
        config = self.root / '.specify/extensions.yml'
        backup = self.root / '.specify/workflow/integration-backup.json'
        before = config.read_bytes(), backup.read_bytes()
        preview = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(0, preview.returncode, preview.stdout + preview.stderr)
        self.assertFalse(json.loads(preview.stdout)['applied'])
        self.assertEqual(before, (config.read_bytes(), backup.read_bytes()))
        applied = subprocess.run([*argv, '--apply'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(0, applied.returncode, applied.stdout + applied.stderr)
        self.assertTrue(json.loads(applied.stdout)['applied'])
        # An older upgrader's unchanged restore guard now sees exactly its managed record.
        record = w.read(backup)['entries']['after_tasks:speckit.project.sync']
        self.assertEqual(self._hooks()['hooks']['after_tasks'][0], record['managed'])
        restored = subprocess.run([*argv, '--apply', '--restore'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(0, restored.returncode, restored.stdout + restored.stderr)
        self.assertFalse(self._hooks()['hooks']['after_tasks'][0]['enabled'])
    def test_reconcile_roundtrip_preserves_unrelated_entries(self):
        path = self.root / '.specify/extensions.yml'
        original = {'hooks': {'after_tasks': [{'extension':'project','command':'speckit.project.sync','optional':False}], 'before_specify':[{'extension':'scope','command':'speckit.workflow.scope-guard','optional':False}], 'after_implement':[{'extension':'custom','command':'custom.check','optional':True}]}, 'other':{'keep':True}}
        path.write_text(yaml.safe_dump(original), encoding='utf-8')
        self.assertEqual(len(reconcile(self.root)['changes']),1)
        self.assertEqual(yaml.safe_load(path.read_text()),original)
        reconcile(self.root,apply=True)
        self.assertEqual(reconcile(self.root,apply=True)['changes'],[])
        reconcile(self.root,apply=True,restore=True)
        self.assertEqual(yaml.safe_load(path.read_text()),original)

    def test_reconcile_refuses_to_overwrite_later_user_hook_edit(self):
        path=self.root / '.specify/extensions.yml'
        path.write_text('hooks:\n  after_tasks:\n    - extension: project\n      command: speckit.project.sync\n')
        reconcile(self.root,apply=True)
        doc=yaml.safe_load(path.read_text());doc['hooks']['after_tasks'][0]['prompt']='user edit'
        path.write_text(yaml.safe_dump(doc))
        with self.assertRaisesRegex(w.WorkflowError, 'HOOK_CHANGED'):
            reconcile(self.root,apply=True,restore=True)

    def _hooks(self, doc=None):
        path = self.root / '.specify/extensions.yml'
        if doc is not None:
            path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding='utf-8')
        return yaml.safe_load(path.read_text(encoding='utf-8'))

    def registered(self):
        """What Spec Kit's register_hooks writes on extension add/update: enabled entries."""
        return {'hooks': {'after_tasks': [{'extension': 'project', 'command': 'speckit.project.sync',
                                           'enabled': True, 'optional': False}],
                          'before_specify': [{'extension': 'memory', 'command': 'speckit.memory.session',
                                              'enabled': True, 'optional': False},
                                             {'extension': 'memory', 'command': 'speckit.memory.impact',
                                              'enabled': True, 'optional': True}],
                          'after_implement': [{'extension': 'memory', 'command': 'speckit.memory.prepare',
                                               'enabled': True, 'optional': False}]}}

    def test_reregistration_after_reconcile_is_disabled_again(self):
        # W10: an extension update re-creates its hooks enabled; that is not a user edit.
        self._hooks(self.registered())
        reconcile(self.root, apply=True)
        self._hooks(self.registered())
        result = reconcile(self.root, apply=True)
        self.assertEqual({c['hook'] for c in result['changes']},
                         {'after_tasks:speckit.project.sync', 'before_specify:speckit.memory.session',
                          'after_implement:speckit.memory.prepare'})
        hooks = self._hooks()['hooks']
        self.assertIs(hooks['after_tasks'][0]['enabled'], False)
        self.assertIs(hooks['before_specify'][0]['enabled'], False)
        self.assertIs(hooks['before_specify'][1]['enabled'], True)  # impact stays a Memory hook
        self.assertIs(hooks['after_implement'][0]['enabled'], False)
        reconcile(self.root, apply=True, restore=True)
        self.assertEqual(self._hooks(), self.registered())

    def test_restore_keeps_a_fresh_registration(self):
        self._hooks(self.registered())
        reconcile(self.root, apply=True)
        changed = self.registered()
        changed['hooks']['after_tasks'][0]['description'] = 'new release text'
        self._hooks(changed)
        reconcile(self.root, apply=True, restore=True)
        self.assertEqual(self._hooks(), changed)
        self.assertFalse((self.root / '.specify/workflow/integration-backup.json').exists())

    def test_update_with_new_manifest_text_is_a_fresh_registration(self):
        # `specify extension update project` after Project changed its hook description (round 4, D1).
        self._hooks(self.registered())
        reconcile(self.root, apply=True)
        updated = self.registered()
        updated['hooks']['after_tasks'][0]['description'] = 'Move the parent issue to the ready column'
        self._hooks(updated)
        reconcile(self.root, apply=True)
        hook = self._hooks()['hooks']['after_tasks'][0]
        self.assertEqual((hook['enabled'], hook['description']), (False, 'Move the parent issue to the ready column'))
        reconcile(self.root, apply=True, restore=True)
        self.assertEqual(self._hooks(), updated)

    def test_edited_disabled_entry_is_still_refused_by_apply_and_restore(self):
        self._hooks(self.registered())
        reconcile(self.root, apply=True)
        doc = self._hooks()
        doc['hooks']['after_tasks'][0]['prompt'] = 'user edit'
        self._hooks(doc)
        for restore in (False, True):
            with self.assertRaisesRegex(w.WorkflowError, 'HOOK_CHANGED_SINCE_RECONCILE: after_tasks'):
                reconcile(self.root, apply=True, restore=restore)

    def test_doctor_and_reconcile_share_one_ownership_rule(self):
        # W13: every hook the shipped manifests declare gets the same decision from both callers.
        root = Path(__file__).resolve().parents[2]
        for manifest in sorted(root.glob('*/extension.yml')):
            doc = yaml.safe_load(manifest.read_text(encoding='utf-8')) or {}
            ext = doc.get('extension', {}).get('id')
            for event, entry in (doc.get('hooks') or {}).items():
                for hook in entry if isinstance(entry, list) else [entry]:
                    item = {'extension': ext, 'command': hook.get('command'), 'enabled': True}
                    self._hooks({'hooks': {event: [item]}})
                    errors = [e for e in w.doctor(self.root, self.policy if hasattr(self, 'policy') else w.load_policy(self.root))['errors']
                              if e.startswith('DUPLICATE_STAGE_OWNER')]
                    self.assertEqual(bool(errors), managed_hook(event, item), (event, item))
        self.assertTrue(managed_hook('before_specify', {'extension': 'memory', 'command': 'speckit.memory.session'}))
        self.assertTrue(managed_hook('after_implement', {'extension': 'memory', 'command': 'speckit.memory.prepare'}))
        self.assertFalse(managed_hook('before_specify', {'extension': 'memory', 'command': 'speckit.memory.impact'}))
