"""Native helper integration; synthetic filesystem only, no GitHub/app launches."""
import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import execution_tools as tools
import workflow as w
from runtime_patch import patch_runtime
import delegate_dispatch as dispatch
import delegation
import test_lean_execution as fixture


class NativeIntegrationTests(unittest.TestCase):
    setUp = fixture.LeanExecutionTests.setUp
    tasks = fixture.LeanExecutionTests.tasks
    state_and_run = fixture.LeanExecutionTests.state_and_run

    def claim(self, stage):
        state, run = self.state_and_run()
        with patch.object(run, 'load', return_value=state), patch.object(run, 'save'), \
             patch.object(run, 'next', return_value={'stage': stage}), \
             patch_runtime('doctor', return_value={'ok': True, 'errors': []}), \
             patch_runtime('package_digest', return_value='pkg'), \
             patch.object(w, 'context_gate', return_value={'pause': False}):
            return run.claim({'session_id': 'native-session'})

    def test_native_scope_initial_commands_require_explicit_analysis_placeholder(self):
        for stage, action in [('scope', 'gate'), ('specify', 'bind')]:
            claim = self.claim(stage)
            command = claim['scope_command']['command']
            self.assertIn('scope.py ' + action + ' 10', command)
            self.assertIn('--analysis', command)
            self.assertIn('<analysis.json>', command)
            self.assertIn('--token ' + claim['token'], command)
            self.assertIn('--session native-session', command)
            self.assertEqual(claim['environment']['SANDUQ_WORKFLOW_CLAIM_TOKEN'], claim['token'])

    def test_native_scope_revalidation_has_no_initial_flags(self):
        (self.directory / 'spec.md').write_text('Existing spec', encoding='utf-8')
        w.write(self.directory / 'scope-source.json', {'repo': 'acme/app', 'issue': 10})
        for stage, action in [('scope', 'gate'), ('specify', 'bind')]:
            claim = self.claim(stage)
            command = claim['scope_command']['command']
            self.assertEqual(command, tools.SCOPE_SCRIPT + ' ' + action + ' 10' + (' --apply' if action == 'bind' else ''))
            self.assertFalse(claim['scope_analysis_required'])

    def test_initial_scope_uses_selected_analysis_without_guessing(self):
        self.policy['lean_execution']['scope_analysis'] = self.feature + '/approved-analysis.json'
        claim = self.claim('scope')
        self.assertIn('--analysis ' + self.feature + '/approved-analysis.json', claim['scope_command']['command'])
        self.assertNotIn('<analysis.json>', claim['scope_command']['command'])

    def test_preflight_claim_reports_all_findings_before_execution(self):
        label = self.feature + '/preflight.json'
        w.write(self.root / label, {'files': [{'path': 'missing-a'}, {'path': 'missing-b'}]})
        self.policy['lean_execution']['preflight_manifest'] = label
        report = w.lean_preflight(self.root, self.policy)
        self.assertEqual(report['failed'], ['file:missing-a', 'file:missing-b'])
        with self.assertRaisesRegex(w.WorkflowError, 'missing-a.*missing-b'):
            self.claim('execute')
        self.policy['lean_execution']['enabled'] = False
        self.assertIsNone(w.lean_preflight(self.root, self.policy))

    def test_doctor_exposes_aggregate_preflight_diagnostics(self):
        self.policy['lean_execution']['preflight_manifest'] = self.feature + '/missing.json'
        with patch_runtime('compatible', return_value=True), \
             patch_runtime('resolve_commands', return_value=w.COMMANDS), \
             patch_runtime('command_exists', return_value=True), \
             patch_runtime('ci_errors', return_value=[]), patch_runtime('host_warnings', return_value=[]), \
             patch_runtime('eol_drift', return_value=[]):
            report = w.doctor(self.root, self.policy)
        self.assertFalse(report['preflight']['ok'])
        self.assertTrue(any('LEAN_PREFLIGHT_FAILED' in e for e in report['errors']))

    def pr_receipt(self, body='Closes #10\n'):
        w.write(self.directory / 'scope-source.json', {'repo': 'acme/app', 'issue': 10, 'dependencies': [9]})
        body_label = self.feature + '/body.md'
        lint_label = self.feature + '/lint.json'
        (self.root / body_label).write_bytes(body.encode('utf-8'))
        lint = tools.pr_lint(body, 'acme/app', 10, [9])
        w.write(self.root / lint_label, lint)
        return {'stage': 'pr', 'outcome': 'passed', 'summary': 'Published exact body',
                'pr_body_file': body_label, 'pr_lint_file': lint_label, 'pr_body_sha256': lint['body_sha256'],
                'inputs': [self.feature + '/tasks.md'], 'evidence': [body_label, lint_label],
                'images_verified': True, 'pr_url': 'https://github.com/acme/app/pull/11'}

    def test_native_pr_recomputes_lint_and_rejects_forged_success(self):
        state, _ = self.state_and_run()
        for body in ('Closes #9', 'Fixes #99', 'Closes foreign/repo#10'):
            receipt = self.pr_receipt(body)
            w.write(self.root / receipt['pr_lint_file'], {'ok': True})
            with patch_runtime('github_repository', return_value='acme/app'), \
                 self.assertRaisesRegex(w.WorkflowError, 'CLOSING_REFERENCE_REJECTED'):
                w.pr_lint_binding(self.root, self.feature, state, receipt)

    def test_native_pr_rejects_changed_body_sent_sha_and_repository(self):
        state, _ = self.state_and_run()
        receipt = self.pr_receipt()
        with patch_runtime('github_repository', return_value='acme/app'):
            with self.assertRaisesRegex(w.WorkflowError, 'SENT_BODY_SHA'):
                w.pr_lint_binding(self.root, self.feature, state, {**receipt, 'pr_body_sha256': '0' * 64})
            (self.root / receipt['pr_body_file']).write_text('Closes #10\nExtra paragraph', encoding='utf-8')
            with self.assertRaisesRegex(w.WorkflowError, 'RECEIPT_MISMATCH'):
                w.pr_lint_binding(self.root, self.feature, state, receipt)
        with patch_runtime('github_repository', return_value='foreign/repo'), \
             self.assertRaisesRegex(w.WorkflowError, 'REPOSITORY_MISMATCH'):
            w.pr_lint_binding(self.root, self.feature, state, receipt)

    def test_native_pr_missing_body_file_is_a_workflow_error_not_a_traceback(self):
        state, _ = self.state_and_run()
        receipt = self.pr_receipt()
        (self.root / receipt['pr_body_file']).unlink()
        with patch_runtime('github_repository', return_value='acme/app'),              self.assertRaisesRegex(w.WorkflowError, 'PR_LINT_BODY_UNREADABLE'):
            w.pr_lint_binding(self.root, self.feature, state, receipt)

    def test_native_pr_completion_fingerprints_body_lint_and_scope(self):
        state, run = self.state_and_run()
        state['active'] = {'stage': 'pr', 'token': 'owned', 'baseline': {}}
        receipt = self.pr_receipt()
        with patch.object(run, 'load', return_value=state), patch.object(run, 'save'), \
             patch.object(run, 'next', return_value={'stage': None}), \
             patch_runtime('github_repository', return_value='acme/app'), \
             patch_runtime('required_inputs', return_value=[]), \
             patch_runtime('fingerprint_files', side_effect=lambda root, paths, **_: {p: 'hash' for p in paths}):
            run.complete('owned', receipt)
        stored = state['receipts']['pr']
        self.assertEqual(stored['pr_lint_binding']['prerequisites'], [9])
        self.assertTrue(set(receipt['evidence'] + [self.feature + '/scope-source.json']) <= set(stored['fingerprints']))

    def test_native_status_preserves_unknown_and_ledger_acceptance_separately(self):
        runs = self.root / 'runs'
        runs.mkdir()
        w.write(runs / 'a.result.json', {'run_id': 'a', 'harness': 'codex', 'status': 'successful'})
        w.write(runs / 'b.result.json', {'run_id': 'b', 'harness': 'codex', 'status': 'successful'})
        w.write(self.directory / 'workflow/delegations.json', {'attempts': [
            {'run_id': 'a', 'identity': self.feature + '/T001', 'status': 'successful',
             'accepted_evidence': {'source': 'accept'}}]})
        with patch.object(delegation, 'ledger_trust_state', return_value='trusted'):
            report = w.native_run_status(self.root, self.feature, {'issue': 'acme/app#10'}, [runs])
        a, b = report['progress']['runs']
        self.assertEqual(a['harness_status'], 'successful')
        self.assertEqual(a['acceptance_verdict'], 'accepted')
        self.assertEqual(a['task_verdict'], 'unknown')
        self.assertEqual(b['acceptance_verdict'], 'unknown')
        self.assertIsNone(b['usage'])

    def test_explicit_failure_domain_preserves_technical_provenance(self):
        with dispatch.edit_ledger(self.root, self.feature) as ledger:
            ledger['attempts'].append({'run_id': 'failed', 'identity': self.feature + '/T001', 'status': 'failed',
                                      'failure_category': 'harness-failure',
                                      'status_provenance': {'primary': 'exit_code'}})
        (self.root / 'failure.json').write_text('Test database unavailable', encoding='utf-8')
        attribution = {'domain': 'environment', 'actor': 'coordinator',
                       'reason': 'Test database connection was refused', 'evidence': 'failure.json'}
        with patch.dict(os.environ, {}, clear=True):
            response = dispatch.classify_failure(self.root, self.feature, 'failed', attribution)
        self.assertEqual(response['failure_domain'], 'environment')
        self.assertEqual(response['failure_category'], 'harness-failure')
        self.assertEqual(response['status_provenance']['primary'], 'exit_code')
        self.assertIn('evidence_sha256', response['failure_attribution'])

    def test_unattributed_failure_domain_stays_unknown_and_invalid_domain_refuses(self):
        import lean_policy
        self.assertEqual(lean_policy.failure_attribution(None), {'domain': 'unknown', 'attribution': None})
        with self.assertRaisesRegex(lean_policy.LeanPolicyError, 'ATTRIBUTION_INVALID'):
            lean_policy.failure_attribution({'domain': 'probably database error from prose'})

    def test_status_uses_explicit_worktree_ledgers_and_refuses_conflicting_acceptance(self):
        other = self.root / 'other'
        runs = other / '.delegate/runs'
        runs.mkdir(parents=True)
        w.write(runs / 'a.result.json', {'run_id': 'a', 'harness': 'codex', 'status': 'successful'})
        row = {'run_id': 'a', 'identity': self.feature + '/T001', 'status': 'successful',
               'accepted_evidence': {'source': 'accept'}}
        w.write(other / self.feature / 'workflow/delegations.json', {'attempts': [row]})
        with patch.object(delegation, 'ledger_trust_state', return_value='trusted'):
            report = w.native_run_status(self.root, self.feature, {'issue': 'acme/app#10'}, [runs])
            self.assertEqual(report['progress']['runs'][0]['acceptance_verdict'], 'accepted')
            w.write(self.directory / 'workflow/delegations.json', {'attempts': [{**row, 'status': 'failed'}]})
            report = w.native_run_status(self.root, self.feature, {'issue': 'acme/app#10'}, [runs])
        self.assertFalse(report['ok'])
        self.assertEqual(report['ledger_conflicts'], ['a'])
        self.assertEqual(report['progress']['runs'][0]['acceptance_verdict'], 'unknown')

    def write_claim(self, feature, branch, token):
        directory = self.root / feature / 'workflow'
        directory.mkdir(parents=True, exist_ok=True)
        w.write(directory / 'checkpoint.json', {'feature': feature, 'branch': branch,
                                                'active': {'token': token, 'session_id': 's-' + token}})

    def claim_env(self, feature, branch='feature-b', inherited=None):
        with patch_runtime('git', return_value=branch), patch.object(dispatch, 'lean_enabled', return_value=True), patch.dict(os.environ, inherited or {}):
            return dispatch.driver_env(self.root, run_context='intent', feature=feature)

    def test_worker_native_environment_preserves_current_claim_identity(self):
        self.write_claim(self.feature, 'feature-b', 'owned')
        env = self.claim_env(self.feature)
        self.assertEqual(env['SANDUQ_WORKFLOW_CLAIM_TOKEN'], 'owned')
        self.assertEqual(env['SANDUQ_WORKFLOW_SESSION_ID'], 's-owned')
        self.assertEqual(env['SANDUQ_DELEGATED_RUN'], 'intent')

    def test_two_active_features_worker_gets_only_its_own_claim(self):
        self.write_claim('specs/002-other', 'feature-a', 'token-a')
        self.write_claim(self.feature, 'feature-b', 'token-b')
        captured = {}

        def run(args, **kwargs):
            captured['env'] = kwargs['env']
            return type('R', (), {'returncode': 0, 'stdout': json.dumps({'run_id': 'r', 'state': 'running'}),
                                  'stderr': ''})()
        candidate = {'harness': 'codex', 'requested_model': None}
        with patch_runtime('git', return_value='feature-b'), patch.object(dispatch, 'lean_enabled', return_value=True), \
             patch.object(dispatch.shutil, 'which', return_value='node'), \
             patch.object(dispatch.subprocess, 'run', side_effect=run), \
             patch.dict(os.environ, {'SANDUQ_WORKFLOW_CLAIM_TOKEN': 'token-a'}):
            dispatch.launch(self.root, 'driver.mjs', candidate, self.root, 'task', 60, 'intent',
                            feature=self.feature)
        self.assertEqual(captured['env']['SANDUQ_WORKFLOW_CLAIM_TOKEN'], 'token-b')
        self.assertEqual(captured['env']['SANDUQ_DELEGATED_RUN'], 'intent')
        self.assertNotIn('SANDUQ_DELEGATED_ROLE', captured['env'])

    def test_wrong_stale_branch_or_feature_claim_is_not_passed(self):
        inherited = {'SANDUQ_WORKFLOW_CLAIM_TOKEN': 'stale', 'SANDUQ_WORKFLOW_SESSION_ID': 'stale'}
        self.write_claim(self.feature, 'old-branch', 'owned')
        env = self.claim_env(self.feature, 'feature-b', inherited)
        self.assertNotIn('SANDUQ_WORKFLOW_CLAIM_TOKEN', env)
        self.assertNotIn('SANDUQ_WORKFLOW_SESSION_ID', env)
        self.write_claim('specs/002-other', 'feature-b', 'owned')
        path = self.root / self.feature / 'workflow/checkpoint.json'
        saved = w.read(path, {})
        saved.update(branch='feature-b', feature='specs/002-other')
        w.write(path, saved)
        self.assertNotIn('SANDUQ_WORKFLOW_CLAIM_TOKEN', self.claim_env(self.feature, 'feature-b', inherited))

    def test_no_active_claim_clears_inherited_claim_environment(self):
        inherited = {'SANDUQ_WORKFLOW_CLAIM_TOKEN': 'stale', 'SANDUQ_WORKFLOW_SESSION_ID': 'stale'}
        w.write(self.directory / 'workflow/checkpoint.json',
                {'feature': self.feature, 'branch': 'feature-b', 'active': None})
        env = self.claim_env(self.feature, 'feature-b', inherited)
        self.assertNotIn('SANDUQ_WORKFLOW_CLAIM_TOKEN', env)
        self.assertNotIn('SANDUQ_WORKFLOW_SESSION_ID', env)

    def test_preflight_blocks_direct_worker_admission_without_launch(self):
        self.tasks('- [ ] T001 Implement parser and tests\n')
        self.policy['delegation']['enabled'] = True
        self.policy['lean_execution']['preflight_manifest'] = self.feature + '/missing.json'
        with patch.object(w, 'load_policy', return_value=self.policy), \
             patch.dict(os.environ, {}, clear=True), patch.object(dispatch, 'launch') as launch:
            with self.assertRaisesRegex(delegation.DelegationError, 'LEAN_PREFLIGHT_FAILED'):
                dispatch.candidate_start(self.root, self.feature, self.feature + '/T001', 'implementation',
                       [self.candidate], self.root / 'brief.txt', self.root, 1800,
                       deliverable='Implement parser.py with passing parser unit tests')
        launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
