"""Lean opt-in gates and conservative legacy contracts, without live harnesses."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import delegation
import delegate_dispatch as dispatch
import lean_policy as lean
import workflow as w


class LeanExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.feature = 'specs/001-example'
        self.policy = w.default_policy(False, False)
        self.policy['lean_execution'] = {'enabled': True}
        self.directory = self.root / self.feature
        self.directory.mkdir(parents=True)
        self.tasks('- [x] T001 Implement src/parser.py\n- [x] T002 [QA] Run parser tests\n'
                   '- [ ] T003 [REVIEW] Review complete implementation\n'
                   '- [ ] T004 [Docs] Update README.md\n')
        self.candidate = {'harness': 'codex', 'requested_model': 'gpt-6-sol', 'tier': 'standard',
                          'rule': 'default:implementation', 'choice': 'preferred'}

    def tasks(self, text):
        (self.directory / 'tasks.md').write_text(text, encoding='utf-8')

    def test_policy_opt_in_validation_preserves_legacy_digest(self):
        legacy = w.default_policy(False, False)
        before = w.delivery_digest(legacy)
        w.validate_policy(legacy)
        self.assertNotIn('lean_execution', legacy)
        self.assertEqual(before, w.delivery_digest(legacy))
        self.assertFalse(lean.enabled(legacy))
        for config in ({'enabled': 1}, {'enabled': True, 'stronger_retry': 1},
                       {'enabled': True, 'finalization_seconds': 400},
                       {'enabled': True, 'timeout_max_seconds': 200},
                       {'enabled': True, 'verification_plan': '../outside.json'}):
            bad = {**legacy, 'lean_execution': config}
            with self.subTest(config=config), self.assertRaises(w.WorkflowError):
                w.validate_policy(bad)
        self.assertEqual(w.policy_cutoff(legacy, self.policy), w.BASE_STAGES.index('execute'))

    def test_ready_requires_every_task_while_coding_review_is_coding_only(self):
        # Only T003 [REVIEW] and T004 [Docs] remain: final coding review may start...
        self.assertEqual(w.coding_review_checks(self.root, self.feature, self.policy, {}), ['tasks'])
        # ...but the shared Ready/CI checks refuse until they are done.
        with self.assertRaisesRegex(w.WorkflowError, 'INCOMPLETE_TASKS'):
            w.ready_checks(self.root, self.feature, self.policy, {}, rules={'tasks': True})
        self.tasks('- [x] T001 Implement src/parser.py\n- [x] T002 [QA] Run parser tests\n'
                   '- [x] T003 [REVIEW] Review complete implementation\n- [ ] T004 [Docs] Update README.md\n')
        with self.assertRaisesRegex(w.WorkflowError, 'INCOMPLETE_TASKS'):
            w.ready_checks(self.root, self.feature, self.policy, {}, rules={'tasks': True})

    def test_failed_delegated_doc_cannot_pass_ready_but_not_coding_review(self):
        self.tasks('- [x] T001 Implement src/parser.py\n- [x] T002 [Docs] Update README.md\n')
        policy = copy.deepcopy(self.policy)
        policy['delegation']['enabled'] = True

        def attempt(root, feature, task_id):
            return {'status': 'successful'} if task_id == 'T001' else {'status': 'failed'}
        with patch('delegation.latest_attempt', side_effect=attempt), \
             patch('delegation.ledger_trust_state', return_value='trusted'):
            with self.assertRaises(w.WorkflowError):
                w.ready_checks(self.root, self.feature, policy, {}, rules={'tasks': True})
            self.assertEqual(w.coding_review_checks(self.root, self.feature, policy, {}), ['tasks'])

    def test_review_waits_for_coding_but_excludes_review_and_docs(self):
        self.assertEqual(w.coding_review_checks(self.root, self.feature, self.policy, {}), ['tasks'])
        self.tasks('- [x] T001 Implement parser\n- [ ] T002 [QA] Run parser tests\n'
                   '- [ ] T003 [REVIEW] Review implementation\n')
        with self.assertRaisesRegex(w.WorkflowError, 'INCOMPLETE_TASKS'):
            w.coding_review_checks(self.root, self.feature, self.policy, {})
        self.assertEqual(w.coding_review_checks(self.root, self.feature,
                         w.default_policy(False, False), {}), [])
        with self.assertRaisesRegex(w.WorkflowError, 'INCOMPLETE_TASKS'):
            w.ready_checks(self.root, self.feature, w.default_policy(False, False), {},
                           rules={'tasks': True})

    def test_review_still_requires_verified_task_ownership(self):
        self.policy['delegation']['enabled'] = True
        with patch.object(delegation, 'ledger_trust_state', return_value='trusted'), \
             patch.object(delegation, 'latest_attempt', return_value={'status': 'failed'}):
            with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_TASK_UNVERIFIED'):
                w.coding_review_checks(self.root, self.feature, self.policy, {})
        with patch.object(delegation, 'ledger_trust_state', return_value='untrusted'):
            with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_LEDGER_UNTRUSTED'):
                w.coding_review_checks(self.root, self.feature, self.policy, {})

    def test_artifact_analysis_is_available_before_coding(self):
        self.assertEqual(delegation.task_type('- [ ] T005 [artifact-analysis] Analyze spec.md', True), 'discovery')
        self.assertEqual(delegation.task_type('- [ ] T005 [artifact-analysis] [Impl] Implement parser', True),
                         'implementation')
        self.assertEqual(delegation.stage_work_type({}, 'analyze'), 'review')

    def test_coordinator_mechanics_are_opt_in_and_fixed_collection_is_exact(self):
        for stage in ('execute', 'ready', 'pr', 'taskstoissues'):
            self.assertTrue(lean.coordinator_owned(self.policy, stage, {}))
            self.assertFalse(lean.coordinator_owned(w.default_policy(False, False), stage, {}))
        self.policy['delegation']['fixed_collection_commands'] = {'verify': 'python scripts/check.py'}
        self.assertTrue(lean.coordinator_owned(self.policy, 'verify', {'verify': 'python scripts/check.py'}))
        self.assertFalse(lean.coordinator_owned(self.policy, 'verify', {'verify': 'python scripts/check.py --all'}))

    def test_admission_one_planned_correction_then_concrete_diagnosis(self):
        identity = self.feature + '/T001'
        deliverable = 'Implement src/parser.py with passing parser unit tests'
        with self.assertRaisesRegex(lean.LeanPolicyError, 'CONCRETE_DELIVERABLE'):
            lean.admit(self.policy, [], identity, 'implementation', None)
        with self.assertRaisesRegex(lean.LeanPolicyError, 'NESTED_COORDINATOR'):
            lean.admit(self.policy, [], identity, 'coordination', deliverable)
        prior = [{'identity': identity, 'status': 'failed'}]
        with self.assertRaisesRegex(lean.LeanPolicyError, 'CORRECTION_PLAN'):
            lean.admit(self.policy, prior, identity, 'implementation', deliverable)
        correction = 'Correct parser Unicode handling and rerun parser tests'
        lean.admit(self.policy, prior, identity, 'implementation', deliverable, correction)
        prior *= 2
        with self.assertRaisesRegex(lean.LeanPolicyError, 'CONCRETE_DIAGNOSIS'):
            lean.admit(self.policy, prior, identity, 'implementation', deliverable, correction,
                       {'cause': 'try harder', 'evidence': 'none', 'change': 'try again'})
        accepted = lean.admit(self.policy, prior, identity, 'implementation', deliverable, correction,
                             {'cause': 'Unicode escape was decoded twice', 'evidence': 'evidence/failure.json',
                              'change': 'Decode once inside parse_string and rerun fixture tests'})
        self.assertEqual(accepted['attempt_number'], 3)

    def test_no_automatic_stronger_retry_but_legacy_keeps_retry(self):
        attempt = {'pinned': False, 'retry_count': 0, 'route_candidates': [self.candidate],
                   'candidate_index': 0, 'requested_harness': 'codex', 'requested_model': 'gpt-6-sol',
                   'rule': 'default:implementation', 'choice': 'preferred'}
        payload = {'status': 'failed', 'git_dirty_changed': False, 'dirty_paths_changed': []}
        self.assertIsNone(dispatch.retry_plan(self.policy, attempt, payload, False, 'codex'))
        with patch.object(dispatch, 'measured_no_edits', return_value=True):
            plan = dispatch.retry_plan(w.default_policy(False, False), attempt, payload, False, 'codex')
        self.assertEqual(plan[0][0]['tier'], 'high')

    def test_failure_categories_do_not_invent_a_worker_failure(self):
        self.assertEqual(lean.failure_category({'status': 'failed', 'summary': 'Tests failed'}), 'unknown')
        self.assertEqual(lean.failure_category({'status': 'failed'}, True), 'provider-rejection')
        self.assertEqual(lean.failure_category({'status': 'failed', 'timed_out': True}), 'timeout')
        self.assertEqual(lean.failure_category({'status': 'unverified'}), 'evidence-missing')
        self.assertEqual(lean.failure_category({'status': 'failed',
                         'status_provenance': {'primary': 'harness_telemetry'}}), 'harness-failure')
        self.assertEqual(lean.failure_category({'status': 'abandoned',
                         'status_provenance': {'primary': 'timeout'}}), 'timeout')
        self.assertEqual(lean.failure_category({'status': 'abandoned',
                         'status_provenance': {'primary': 'telemetry_incomplete'}}), 'harness-failure')
        self.assertEqual(lean.failure_category({'status': 'failed',
                         'status_provenance': {'primary': 'self_report'}}), 'task-failure')

    def test_timeout_guidance_uses_only_comparable_successful_runs(self):
        attempts = [{'task_type': 'implementation', 'status': 'successful',
                     'requested_harness': 'codex', 'requested_model': 'gpt-6-sol',
                     'started_at': '2026-10-12T00:00:00+00:00', 'ended_at': '2026-10-12T00:10:00+00:00'},
                    {'task_type': 'implementation', 'status': 'failed'}]
        result = lean.timeout_guidance(self.policy, attempts, 'implementation', [self.candidate])
        self.assertEqual(result['timeout_seconds'], 1020)
        self.assertEqual(result['comparable_runs'], 1)
        self.assertEqual(lean.timeout_guidance(self.policy, attempts, 'review', [self.candidate])['usage'], 'unknown')

    def test_coordinator_stage_start_refuses_before_launch(self):
        self.policy['delegation']['enabled'] = True
        with patch.object(w, 'load_policy', return_value=self.policy), \
             patch.dict(os.environ, {}, clear=True), patch.object(dispatch, 'candidate_start') as launch:
            with self.assertRaisesRegex(delegation.DelegationError, 'COORDINATOR_OWNS_STAGE'):
                dispatch.start(self.root, self.feature, 'stage:execute', token='owned')
        launch.assert_not_called()

    def state_and_run(self):
        with patch.object(w, 'load_policy', return_value=self.policy):
            run = w.Run(self.root, self.feature)
        state = {'active': None, 'dependency_digest': 'pkg', 'policy_digest': w.delivery_digest(self.policy),
                 'policy_digest_version': w.POLICY_DIGEST_VERSION, 'commands': dict(w.COMMANDS),
                 'receipts': {}, 'issue': 'acme/app#10'}
        return state, run

    def test_coordinator_claim_does_not_install_or_record_another_coordinator(self):
        self.policy['delegation']['enabled'] = True
        state, run = self.state_and_run()
        with patch.object(run, 'load', return_value=state), patch.object(run, 'save'), \
             patch.object(run, 'next', return_value={'stage': 'execute'}), \
             patch.object(w, 'doctor', return_value={'ok': True, 'errors': []}), \
             patch.object(w, 'package_digest', return_value='pkg'), \
             patch.object(w, 'context_gate', return_value={'pause': False}), \
             patch.object(delegation, 'doctor') as install:
            claim = run.claim({'session_id': 'session'})
        self.assertEqual(claim['execution_owner'], 'coordinator')
        self.assertNotIn('delegation', claim)
        install.assert_not_called()

    def test_review_claim_blocks_before_delegation_side_effects(self):
        self.policy['delegation']['enabled'] = True
        self.tasks('- [ ] T001 Implement parser and run its tests\n')
        state, run = self.state_and_run()
        with patch.object(run, 'load', return_value=state), patch.object(run, 'save') as save, \
             patch.object(run, 'next', return_value={'stage': 'review'}), \
             patch.object(w, 'doctor', return_value={'ok': True, 'errors': []}), \
             patch.object(w, 'package_digest', return_value='pkg'), \
             patch.object(w, 'context_gate', return_value={'pause': False}), \
             patch.object(delegation, 'doctor') as install:
            with self.assertRaisesRegex(w.WorkflowError, 'INCOMPLETE_TASKS'):
                run.claim({'session_id': 'session'})
        install.assert_not_called()
        save.assert_not_called()

    def test_coordinator_completion_keeps_evidence_and_claim_token_checks(self):
        self.policy['delegation']['enabled'] = True
        state, run = self.state_and_run()
        state['active'] = {'stage': 'execute', 'token': 'owned', 'baseline': {},
                           'execution_owner': 'coordinator'}
        w.write(self.directory / 'scope-source.json', {'repo': 'acme/app', 'issue': 10})
        (self.directory / 'result.md').write_text('Implemented parser and passed tests', encoding='utf-8')
        receipt = {'stage': 'execute', 'outcome': 'passed', 'summary': 'Implemented parser',
                   'inputs': [self.feature + '/tasks.md'], 'evidence': [self.feature + '/result.md']}
        with patch.object(run, 'load', return_value=state), patch.object(run, 'save'), \
             patch.object(run, 'next', return_value={'stage': 'verify'}), \
             patch.object(w, 'required_inputs', return_value=[]), \
             patch.object(w, 'fingerprint_files', side_effect=lambda root, paths: {p: 'hash' for p in paths}), \
             patch.object(delegation, 'latest_attempt') as attempt:
            with self.assertRaisesRegex(w.WorkflowError, 'CLAIM_TOKEN_MISMATCH'):
                run.complete('foreign', receipt)
            with self.assertRaisesRegex(w.WorkflowError, 'EVIDENCE_REQUIRED'):
                run.complete('owned', {**receipt, 'evidence': []})
            self.assertEqual(run.complete('owned', receipt), {'stage': 'verify'})
        attempt.assert_not_called()
        self.assertIsNone(state['active'])

    def test_candidate_admission_cannot_bypass_review_by_changing_work_type(self):
        self.tasks('- [ ] T001 Implement parser\n- [ ] T002 [REVIEW] Review implementation\n')
        brief = self.root / 'brief.txt'
        brief.write_text('Review parser code', encoding='utf-8')
        self.policy['delegation']['enabled'] = True
        with patch.object(w, 'load_policy', return_value=self.policy), \
             patch.dict(os.environ, {}, clear=True), patch.object(delegation, 'doctor') as install:
            with self.assertRaisesRegex(w.WorkflowError, 'INCOMPLETE_TASKS'):
                dispatch.candidate_start(self.root, self.feature, self.feature + '/T002', 'implementation',
                                         [self.candidate], brief, self.root, 1800,
                                         deliverable='Write final parser review with recorded findings')
        install.assert_not_called()

    def test_artifact_analysis_stage_can_dispatch_before_feature_coding_finishes(self):
        self.tasks('- [ ] T001 Implement parser and run tests\n')
        self.policy['delegation']['enabled'] = True
        brief = self.root / 'brief.txt'
        brief.write_text('Analyze spec and plan consistency', encoding='utf-8')
        health = {'ok': True, 'driver': self.root / 'driver.mjs', 'harnesses': {'codex': True}}
        with patch.object(w, 'load_policy', return_value=self.policy), \
             patch.dict(os.environ, {}, clear=True), patch.object(delegation, 'doctor', return_value=health), \
             patch.object(w, 'active_host', return_value='codex'), \
             patch.object(dispatch, 'launch', return_value={'run_id': 'analysis', 'state': 'running'}):
            result = dispatch.candidate_start(self.root, self.feature, self.feature + '/stage:analyze',
                       'review', [self.candidate], brief, self.root, 1800,
                       deliverable='Write spec and plan consistency findings in analysis.md')
        self.assertEqual(result['run_id'], 'analysis')

    def test_lean_candidate_admission_records_exact_correction_context(self):
        self.tasks('- [ ] T001 Implement parser and run tests\n')
        self.policy['delegation']['enabled'] = True
        brief = self.root / 'brief.txt'
        brief.write_text('Implement parser', encoding='utf-8')
        health = {'ok': True, 'driver': self.root / 'driver.mjs', 'harnesses': {'codex': True}}
        with patch.object(w, 'load_policy', return_value=self.policy), \
             patch.dict(os.environ, {}, clear=True), patch.object(delegation, 'doctor', return_value=health), \
             patch.object(w, 'active_host', return_value='codex'), \
             patch.object(dispatch, 'launch', return_value={'run_id': 'r1', 'state': 'running'}) as launch:
            response = dispatch.candidate_start(self.root, self.feature, self.feature + '/T001',
                       'implementation', [self.candidate], brief, self.root, 1800,
                       deliverable='Implement parser.py with passing parser unit tests')
        self.assertEqual(response['timeout_guidance']['finalization_seconds'], 120)
        attempt = dispatch.read_ledger(self.root, self.feature)['attempts'][0]
        self.assertEqual(attempt['lean_admission']['attempt_number'], 1)
        self.assertIn('Finalization reserve: 120 seconds', launch.call_args.args[4])

    def test_repeated_identity_cannot_reset_correction_budget_and_reassign_keeps_model(self):
        self.tasks('- [ ] T001 Implement parser and run tests\n')
        self.policy['delegation']['enabled'] = True
        brief = self.root / 'brief.txt'
        brief.write_text('Implement parser', encoding='utf-8')
        health = {'ok': True, 'driver': self.root / 'driver.mjs', 'harnesses': {'codex': True}}
        with patch.object(w, 'load_policy', return_value=self.policy), \
             patch.dict(os.environ, {}, clear=True), patch.object(delegation, 'doctor', return_value=health), \
             patch.object(w, 'active_host', return_value='codex'), \
             patch.object(dispatch, 'launch', side_effect=[{'run_id': 'r1', 'state': 'running'},
                                                         {'run_id': 'r2', 'state': 'running'}]) as launch:
            dispatch.candidate_start(self.root, self.feature, self.feature + '/T001',
                                     'implementation', [self.candidate], brief, self.root, 1800,
                                     deliverable='Implement parser.py with passing parser unit tests')
            with dispatch.edit_ledger(self.root, self.feature) as ledger:
                ledger['attempts'][0]['status'] = 'failed'
            replacement = dispatch.reassign(self.root, self.feature, 'r1',
                                            'Fix Unicode parsing and rerun parser tests')
            self.assertEqual(replacement['run_id'], 'r2')
            self.assertEqual(launch.call_args.args[2]['requested_model'], 'gpt-6-sol')
            with dispatch.edit_ledger(self.root, self.feature) as ledger:
                ledger['attempts'][-1]['status'] = 'failed'
            with self.assertRaisesRegex(lean.LeanPolicyError, 'CONCRETE_DIAGNOSIS'):
                dispatch.candidate_start(self.root, self.feature, self.feature + '/T001',
                                         'implementation', [self.candidate], brief, self.root, 1800,
                                         deliverable='Implement parser.py with passing parser unit tests',
                                         correction_plan='Fix Unicode parsing and rerun parser tests')
            self.assertEqual(launch.call_count, 2)

    def test_lean_start_failure_never_uses_a_stronger_fallback(self):
        self.tasks('- [ ] T001 Implement parser and run tests\n')
        self.policy['delegation']['enabled'] = True
        brief = self.root / 'brief.txt'
        brief.write_text('Implement parser', encoding='utf-8')
        health = {'ok': True, 'driver': self.root / 'driver.mjs', 'harnesses': {'codex': True}}
        stronger = {**self.candidate, 'requested_model': 'gpt-6-astra', 'tier': 'high'}
        with patch.object(w, 'load_policy', return_value=self.policy), \
             patch.dict(os.environ, {}, clear=True), patch.object(delegation, 'doctor', return_value=health), \
             patch.object(w, 'active_host', return_value='codex'), \
             patch.object(dispatch, 'intent_run_dirs', return_value=[]), \
             patch.object(dispatch, 'launch', side_effect=dispatch.StartFailed('provider refused model')) as launch:
            with self.assertRaisesRegex(delegation.DelegationError, 'ROUTES_UNAVAILABLE'):
                dispatch.candidate_start(self.root, self.feature, self.feature + '/T001',
                       'implementation', [self.candidate, stronger], brief, self.root, 1800,
                       deliverable='Implement parser.py with passing parser unit tests')
        self.assertEqual(launch.call_count, 1)


if __name__ == '__main__':
    unittest.main()
