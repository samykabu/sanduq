import copy
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
    def test_reconcile_roundtrip_preserves_unrelated_entries(self):
        path = self.root / '.specify/extensions.yml'
        original = {'hooks': {'after_tasks': [{'extension':'project','command':'speckit.project.sync','optional':False}], 'before_specify':[{'extension':'scope','command':'speckit.scope.guard','optional':False}], 'after_implement':[{'extension':'custom','command':'custom.check','optional':True}]}, 'other':{'keep':True}}
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
