import copy
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import ci_gate as c
import workflow as w
import waivers
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

    def invoke(self, base):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['ci_gate.py', '--root', str(self.root), '--base-ref', base]), \
             contextlib.redirect_stdout(output):
            code = c.main()
        return code, __import__('json').loads(output.getvalue())

    def source_only_commit(self):
        base = w.git(self.root, 'rev-parse', 'HEAD')
        (self.root / 'bugfix.py').write_text('print("fixed")', encoding='utf-8')
        subprocess.run(['git', 'add', 'bugfix.py'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'Small bug fix'], cwd=self.root, check=True)
        return base

    def test_required_managed_gate_does_not_block_ordinary_bug_fix(self):
        self.policy['ci']['gate']['mode'] = 'required'
        self.configure()
        code, result = self.invoke(self.source_only_commit())
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'not_applicable')
        self.assertEqual(result['features'], [])

    def test_exact_waiver_skips_one_rule_and_reports_it(self):
        self.policy = w.default_policy(False, False)
        self.policy['ci']['gate']['mode'] = 'required'
        self.policy['ci']['gate']['rules']['tasks'] = True
        self.configure()
        def fake_check(root, feature, policy, base, rules):
            if rules['tasks']:
                raise w.WorkflowError('INCOMPLETE_TASKS')
            return {'feature': feature, 'passed': True, 'rules': ['receipts']}
        output = io.StringIO()
        with patch.object(c, 'resolve_features', return_value=[self.feature]), \
             patch.object(c, 'check', side_effect=fake_check), \
             patch.object(waivers, 'verify', return_value={'rule': 'tasks', 'reviewer': 'owner'}), \
             patch.object(sys, 'argv', ['ci_gate.py', '--root', str(self.root),
                                       '--base-ref', 'HEAD', '--pr-number', '7']), \
             contextlib.redirect_stdout(output):
            code = c.main()
        result = __import__('json').loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result['features'][0]['waivers'][0]['rule'], 'tasks')

    def test_candidate_merge_requires_exact_base_and_head_parents(self):
        base_branch = w.git(self.root, 'branch', '--show-current')
        subprocess.run(['git', 'switch', '-qc', 'work'], cwd=self.root, check=True)
        (self.root / 'feature.py').write_text('feature', encoding='utf-8')
        subprocess.run(['git', 'add', 'feature.py'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'feature'], cwd=self.root, check=True)
        head = w.git(self.root, 'rev-parse', 'HEAD')
        subprocess.run(['git', 'switch', '-q', base_branch], cwd=self.root, check=True)
        (self.root / 'base.py').write_text('base', encoding='utf-8')
        subprocess.run(['git', 'add', 'base.py'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'base'], cwd=self.root, check=True)
        base = w.git(self.root, 'rev-parse', 'HEAD')
        subprocess.run(['git', 'merge', '-q', '--no-ff', 'work', '-m', 'candidate'],
                       cwd=self.root, check=True)
        merged = w.git(self.root, 'rev-parse', 'HEAD')
        env = {'GITHUB_REF': 'refs/pull/7/merge', 'GITHUB_SHA': merged,
               'BASE_SHA': base, 'PR_HEAD_SHA': head}
        self.assertEqual(c.check_candidate_merge(self.root, env)['merge_sha'], merged)
        with self.assertRaisesRegex(w.WorkflowError, 'PARENTS_MISMATCH'):
            c.check_candidate_merge(self.root, dict(env, BASE_SHA=head))

    def test_all_prs_scope_keeps_explicit_mapping_requirement(self):
        self.policy['ci']['gate'].update(mode='required', scope='all-prs')
        self.configure()
        code, result = self.invoke(self.source_only_commit())
        self.assertEqual(code, 1)
        self.assertIn('FEATURE_MAPPING_REQUIRED', result['error'])

    def test_disabled_gate_reports_no_check(self):
        self.policy['ci']['gate']['mode'] = 'disabled'
        self.configure()
        code, result = self.invoke(self.source_only_commit())
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'disabled')

    def test_advisory_reports_findings_without_failing_job(self):
        self.policy['ci']['gate']['mode'] = 'advisory'
        self.configure()
        base = w.git(self.root, 'rev-parse', 'HEAD')
        path = self.root / self.feature / 'spec.md'
        path.parent.mkdir(parents=True)
        path.write_text('Feature without evidence', encoding='utf-8')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'Feature'], cwd=self.root, check=True)
        code, result = self.invoke(base)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'advisory_findings')
        self.assertFalse(result['feature_verified'])

    def checkpoint_formats(self, run):
        """The current digest and each legacy format an older checkpoint may carry."""
        current = w.read(run.path)
        snapshot = current['policy']
        without_delegation = {k: v for k, v in snapshot.items() if k != 'delegation'}
        def legacy(version, policy_snapshot, excluded):
            state = copy.deepcopy(current)
            state['policy'] = copy.deepcopy(policy_snapshot)
            state['policy_digest'] = w.digest({k: v for k, v in policy_snapshot.items() if k not in excluded})
            if version is None:
                state.pop('policy_digest_version'); state.pop('ci_policy_digest')
            else:
                state['policy_digest_version'] = version
            return state
        return {'current': current,
                'v2-with-delegation': legacy(2, snapshot, ('ci',)),
                'v2-before-delegation': legacy(2, without_delegation, ('ci',)),
                'full-with-delegation': legacy(None, snapshot, ()),
                'full-before-delegation': legacy(None, without_delegation, ())}

    def test_delegation_route_edit_keeps_ci_gate_current_in_every_digest_format(self):
        run = self.ready()
        self.assertEqual(w.read(run.path)['policy_digest_version'], w.POLICY_DIGEST_VERSION)
        routed = copy.deepcopy(self.policy)
        routed['delegation']['enabled'] = True
        routed['delegation']['models']['codex']['standard'] = 'team-model'
        routed['delegation']['install_scope'] = 'global'
        routed = w.validate_policy(routed)
        semantic = copy.deepcopy(self.policy)
        semantic['execution']['checkpoints'] = 'every-phase'
        semantic = w.validate_policy(semantic)
        for name, state in self.checkpoint_formats(run).items():
            with self.subTest(format=name):
                w.write(run.path, state)
                self.assertTrue(c.check(self.root, self.feature, self.policy)['passed'])
                self.assertTrue(c.check(self.root, self.feature, routed)['passed'])
                with self.assertRaisesRegex(w.WorkflowError, 'POLICY_CHANGED'):
                    c.check(self.root, self.feature, semantic)

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

    def test_index_preflight_reports_add_force_recipe_for_gitignored_evidence(self):
        run = self.ready()
        (self.root / '.gitignore').write_text('*.log\n', encoding='utf-8')
        ignored_evidence = run.feature / 'evidence/verify.log'
        ignored_evidence.write_text('ignored evidence', encoding='utf-8')
        state = w.read(run.path)
        state['receipts']['verify']['fingerprints'][self.feature + '/evidence/verify.log'] = w.fingerprint_files(
            self.root, [self.feature + '/evidence/verify.log'])[self.feature + '/evidence/verify.log']
        run.save(state)
        subprocess.run(['git', 'add', '.gitignore'], cwd=self.root, check=True)
        with self.assertRaisesRegex(w.WorkflowError, 'EVIDENCE_NOT_PORTABLE') as failure:
            c.check_index(self.root, self.feature)
        message = str(failure.exception)
        self.assertIn('git add -f ' + self.feature + '/evidence/verify.log', message)

    def test_index_preflight_warns_on_cross_feature_evidence_path(self):
        run = self.ready()
        state = w.read(run.path)
        other = 'specs/002-other/evidence/verify.txt'
        (self.root / other).parent.mkdir(parents=True, exist_ok=True)
        (self.root / other).write_text('borrowed evidence', encoding='utf-8')
        state['receipts']['verify']['fingerprints'][other] = w.fingerprint_files(self.root, [other])[other]
        run.save(state)
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        result = c.check_index(self.root, self.feature)
        self.assertEqual(len(result['warnings']), 1)
        self.assertIn('CROSS_FEATURE_EVIDENCE', result['warnings'][0])
        self.assertIn(other, result['warnings'][0])

    def test_index_preflight_has_no_warnings_when_all_evidence_is_own(self):
        run = self.ready()
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        self.assertEqual(c.check_index(self.root, self.feature)['warnings'], [])

    def test_check_index_warnings_surface_on_gate_result(self):
        self.policy['ci']['gate']['mode'] = 'required'
        self.configure()
        warning = ("CROSS_FEATURE_EVIDENCE: receipt references path(s) under another feature's "
                   "specs/ directory: specs/002-other/evidence/verify.txt")
        def fake_check(root, feature, policy, base, rules):
            return {'feature': feature, 'passed': True, 'rules': ['receipts']}
        output = io.StringIO()
        with patch.object(c, 'resolve_features', return_value=[self.feature]), \
             patch.object(c, 'check_index', return_value={'feature': self.feature, 'indexed_paths': 3,
                                                          'warnings': [warning]}), \
             patch.object(c, 'check', side_effect=fake_check), \
             patch.object(sys, 'argv', ['ci_gate.py', '--root', str(self.root),
                                        '--base-ref', 'HEAD', '--check-index']), \
             contextlib.redirect_stdout(output):
            code = c.main()
        result = __import__('json').loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertIn('CROSS_FEATURE_EVIDENCE', result['features'][0]['index_warnings'][0])

    def test_check_index_without_warnings_omits_the_field(self):
        self.policy['ci']['gate']['mode'] = 'required'
        self.configure()
        def fake_check(root, feature, policy, base, rules):
            return {'feature': feature, 'passed': True, 'rules': ['receipts']}
        output = io.StringIO()
        with patch.object(c, 'resolve_features', return_value=[self.feature]), \
             patch.object(c, 'check_index', return_value={'feature': self.feature, 'indexed_paths': 3,
                                                          'warnings': []}), \
             patch.object(c, 'check', side_effect=fake_check), \
             patch.object(sys, 'argv', ['ci_gate.py', '--root', str(self.root),
                                        '--base-ref', 'HEAD', '--check-index']), \
             contextlib.redirect_stdout(output):
            code = c.main()
        result = __import__('json').loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertNotIn('index_warnings', result['features'][0])

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

    def test_report_warnings_prints_to_stderr_and_writes_step_summary(self):
        """Finding 2, round 4: a ready_checks warning (unverified-local
        ledger trust, in particular) must reach a reviewer even though it
        never changes the gate's exit code."""
        results = [{'feature': self.feature, 'warnings': [
            'DELEGATION_LEDGER_TRUST_UNVERIFIED_LOCAL: no local dispatcher-write marker for ' + self.feature]}]
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / 'summary.md'
            with contextlib.redirect_stderr(stderr), \
                 patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(summary_path)}):
                c.report_warnings(results)
            self.assertIn('DELEGATION_LEDGER_TRUST_UNVERIFIED_LOCAL', stderr.getvalue())
            self.assertTrue(summary_path.is_file())
            self.assertIn('DELEGATION_LEDGER_TRUST_UNVERIFIED_LOCAL', summary_path.read_text(encoding='utf-8'))

    def test_report_warnings_still_prints_to_stderr_without_step_summary(self):
        results = [{'feature': self.feature,
                   'warnings': ['DELEGATION_LEDGER_TRUST_UNVERIFIED_LOCAL: x']}]
        stderr = io.StringIO()
        env = dict(os.environ)
        env.pop('GITHUB_STEP_SUMMARY', None)
        with contextlib.redirect_stderr(stderr), patch.dict(os.environ, env, clear=True):
            c.report_warnings(results)
        self.assertIn('DELEGATION_LEDGER_TRUST_UNVERIFIED_LOCAL', stderr.getvalue())

    def test_report_warnings_no_op_when_there_are_no_warnings(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / 'summary.md'
            with contextlib.redirect_stderr(stderr), \
                 patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(summary_path)}):
                c.report_warnings([{'feature': self.feature, 'warnings': []}])
            self.assertEqual(stderr.getvalue(), '')
            self.assertFalse(summary_path.exists())

    def test_report_warnings_falls_back_to_stderr_when_summary_is_unwritable(self):
        """Finding 2, round 5: report_warnings runs inside main's own try
        block, so an OSError from an unwritable $GITHUB_STEP_SUMMARY must
        never propagate and turn a passing gate into a reported failure."""
        results = [{'feature': self.feature,
                   'warnings': ['DELEGATION_LEDGER_TRUST_UNVERIFIED_LOCAL: x']}]
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            # A directory, not a file: opening it for append raises OSError.
            unwritable = Path(tmp) / 'unwritable-dir'
            unwritable.mkdir()
            with contextlib.redirect_stderr(stderr), \
                 patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(unwritable)}):
                c.report_warnings(results)  # must not raise
        self.assertIn('DELEGATION_LEDGER_TRUST_UNVERIFIED_LOCAL', stderr.getvalue())
        self.assertIn('SUMMARY_UNWRITABLE', stderr.getvalue())
