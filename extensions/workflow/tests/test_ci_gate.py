import copy
import subprocess
import sys
import tempfile
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

    def test_index_preflight_rejects_local_only_and_unstaged_evidence(self):
        run = self.ready()
        with self.assertRaisesRegex(w.WorkflowError, 'EVIDENCE_NOT_PORTABLE'):
            c.check_index(self.root, self.feature)
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        self.assertGreater(c.check_index(self.root, self.feature)['indexed_paths'], 0)
        (run.feature / 'evidence/verify.txt').write_text('changed after staging')
        with self.assertRaisesRegex(w.WorkflowError, 'unstaged.*verify.txt'):
            c.check_index(self.root, self.feature)

    def test_source_drift_reports_paths_without_contents(self):
        self.ready()
        (self.root / 'new-build.props').write_text('private contents')
        with self.assertRaisesRegex(w.WorkflowError, 'STALE_RECEIPT: verify.*new-build.props') as failure:
            c.check(self.root, self.feature, self.policy)
        self.assertNotIn('private contents', str(failure.exception))

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

    def divergent_branches(self):
        """A target-only feature must not be attributed to the PR branch."""
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'Shared setup'], cwd=self.root, check=True)
        branch = w.git(self.root, 'branch', '--show-current')
        subprocess.run(['git', 'checkout', '-qb', 'target'], cwd=self.root, check=True)
        target_feature = self.root / 'specs/002-target-only/spec.md'
        target_feature.parent.mkdir(parents=True)
        target_feature.write_text('Unrelated target feature', encoding='utf-8')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'Target progress'], cwd=self.root, check=True)
        target = w.git(self.root, 'rev-parse', 'HEAD')
        subprocess.run(['git', 'checkout', '-q', branch], cwd=self.root, check=True)
        feature = self.root / self.feature / 'spec.md'
        feature.parent.mkdir(parents=True)
        feature.write_text('PR feature', encoding='utf-8')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'PR progress'], cwd=self.root, check=True)
        return target, branch

    def test_diverged_target_and_detached_merge_resolve_only_pr_features(self):
        target, branch = self.divergent_branches()
        self.assertEqual(c.resolve_features(self.root, target, []), [self.feature])
        subprocess.run(['git', 'merge', '--no-ff', '-qm', 'Synthetic PR merge', target], cwd=self.root, check=True)
        subprocess.run(['git', 'checkout', '--detach', '-q'], cwd=self.root, check=True)
        self.assertEqual(c.resolve_features(self.root, target, []), [self.feature])

    def test_shallow_history_blocks_until_common_ancestor_is_fetched(self):
        target, branch = self.divergent_branches()
        with tempfile.TemporaryDirectory() as folder:
            clone = Path(folder).resolve() / 'shallow'
            subprocess.run(['git', 'clone', '-q', '--depth', '1', '--branch', branch,
                            self.root.as_uri(), str(clone)], check=True, capture_output=True)
            self.assertEqual(w.git(clone, 'rev-parse', '--is-shallow-repository'), 'true')
            with self.assertRaisesRegex(w.WorkflowError, 'BASE_HISTORY_UNAVAILABLE'):
                c.resolve_features(clone, target, [self.feature])
            subprocess.run(['git', 'fetch', '-q', '--depth', '1', 'origin', 'target'], cwd=clone, check=True)
            with self.assertRaisesRegex(w.WorkflowError, 'BASE_HISTORY_UNAVAILABLE'):
                c.resolve_features(clone, target, [])
            subprocess.run(['git', 'fetch', '-q', '--unshallow', 'origin', branch, 'target'], cwd=clone, check=True)
            self.assertEqual(c.resolve_features(clone, target, []), [self.feature])
