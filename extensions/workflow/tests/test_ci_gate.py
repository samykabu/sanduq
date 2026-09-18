import copy
import subprocess
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import ci_gate as c
import workflow as w
import test_workflow as fixture

class CIGateTests(unittest.TestCase):
    setUp=fixture.WorkflowTests.setUp
    configure=fixture.WorkflowTests.configure
    usage=fixture.WorkflowTests.usage
    receipt=fixture.WorkflowTests.receipt

    def ready(self):
        self.policy=w.default_policy(False,False);self.configure()
        run=w.Run(self.root,self.feature);run.start('acme/app#10')
        w.write(run.feature/'scope-source.json',{'repo':'acme/app','issue':10})
        (run.feature/'tasks.md').write_text('- [x] T001 Done behavior',encoding='utf-8')
        w.write(run.feature/'workflow/task-issues.json',{'repo':'acme/app','parent':10,'feature':self.feature,'tasks':{'T001':{'number':11,'linked':True}}})
        for stage in w.stages(self.policy):
            if stage=='pr':break
            claim=run.claim(self.usage());run.complete(claim['token'],self.receipt(stage))
        return run

    def test_core_only_does_not_require_unselected_docs(self):
        self.ready();self.assertTrue(c.check(self.root,self.feature,self.policy)['passed'])

    def test_missing_or_deleted_evidence_and_incomplete_tasks_fail(self):
        run=self.ready();evidence=run.feature/'evidence/verify.txt';before=evidence.read_bytes();evidence.unlink()
        with self.assertRaisesRegex(w.WorkflowError,'STALE_RECEIPT'):c.check(self.root,self.feature,self.policy)
        evidence.write_bytes(before);(run.feature/'tasks.md').write_text('- [ ] T001 Done behavior')
        with self.assertRaisesRegex(w.WorkflowError,'INCOMPLETE_TASKS'):c.check(self.root,self.feature,self.policy)

    def test_wrong_native_mapping_and_unresolved_clarification_fail(self):
        run=self.ready();mapping=w.read(run.feature/'workflow/task-issues.json');mapping['parent']=99;w.write(run.feature/'workflow/task-issues.json',mapping)
        with self.assertRaisesRegex(w.WorkflowError,'MAPPING_IDENTITY|STALE_RECEIPT'):c.check(self.root,self.feature,self.policy)
        state=run.load();state['receipts']['clarify']['unresolved']=1;run.save(state)
        with self.assertRaisesRegex(w.WorkflowError,'CLARIFICATION_UNRESOLVED'):c.check(self.root,self.feature,self.policy)

    def test_source_only_change_requires_explicit_feature(self):
        base=w.git(self.root,'rev-parse','HEAD');(self.root/'source.txt').write_text('Changed')
        subprocess.run(['git','add','.'],cwd=self.root,check=True);subprocess.run(['git','commit','-qm','Source'],cwd=self.root,check=True)
        with self.assertRaisesRegex(w.WorkflowError,'FEATURE_MAPPING_REQUIRED'):c.resolve_features(self.root,base,[])
        self.assertEqual(c.resolve_features(self.root,base,[self.feature]),[self.feature])

    def test_multi_feature_pr_resolves_all_changed_features(self):
        base=w.git(self.root,'rev-parse','HEAD')
        for feature in ('specs/001-a','specs/002-b'):
            p=self.root/feature/'spec.md';p.parent.mkdir(parents=True);p.write_text('Feature')
        subprocess.run(['git','add','.'],cwd=self.root,check=True);subprocess.run(['git','commit','-qm','Features'],cwd=self.root,check=True)
        self.assertEqual(c.resolve_features(self.root,base,[]),['specs/001-a','specs/002-b'])
        self.assertEqual(c.resolve_features(self.root,base,['specs/001-a']),['specs/001-a','specs/002-b'])

    def test_new_source_invalidates_verification_even_when_agent_omitted_it(self):
        run = self.ready()
        (self.root / 'new-source.py').write_text('print("new behavior")', encoding='utf-8')
        self.assertEqual(run.next(run.load())['stage'], 'verify')
        with self.assertRaisesRegex(w.WorkflowError, 'STALE_RECEIPT: verify'):
            c.check(self.root, self.feature, self.policy)

    def test_changed_pr_feature_mapping_is_consumed(self):
        base = w.git(self.root, 'rev-parse', 'HEAD')
        w.write(self.root / '.specify/workflow/pr-features.json', {'features': [self.feature]})
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'Feature mapping'], cwd=self.root, check=True)
        self.assertEqual(c.resolve_features(self.root, base, []), [self.feature])
