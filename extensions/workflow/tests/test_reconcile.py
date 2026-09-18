import copy
import sys
import unittest
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from reconcile import reconcile
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
