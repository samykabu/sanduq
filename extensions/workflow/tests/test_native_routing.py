"""PH-05: native-first routing, record-native and its provenance, and the same-lineage review refusal."""
import copy
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import delegate_dispatch as dispatch
import delegation
import workflow as w
from runtime_patch import patch_runtime
import test_delegation
import test_workflow as fixture

base = test_delegation.DelegationTests
PASS = '{"total": 3, "passed": 3, "failed": 0}'
FAIL = '{"total": 3, "passed": 2, "failed": 1}'
TASK_GATE = {'tasks': True, 'task_links': False, 'documentation': False}


class NativeRoutingTests(unittest.TestCase):
    configure = fixture.WorkflowTests.configure
    setUp, enable, tasks = base.setUp, base.enable, base.tasks
    skill_copy, fake_doctor, fake_run_capped = base.skill_copy, base.fake_doctor, base.fake_run_capped

    def claim(self):
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch_runtime('doctor', return_value={'ok': True, 'errors': []}):
            return run, run.claim({'session_id': 'test-session'})

    def execute_claim(self):
        """An active Execute claim, the claim a task's record-native binds to."""
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        state = run.load()
        state['active'] = {'stage': 'execute', 'token': 'exec-token', 'session_id': 'test-session',
                           'claimed_at': dispatch.stamp()}
        w.write(run.path, state)
        return run

    def record(self, identity, token, output=PASS, exit_code=0, agent='agent-a', parent='top', **kwargs):
        with patch.object(dispatch, 'run_capped', return_value=self.fake_run_capped(exit_code, output)):
            return dispatch.record_native(self.root, self.feature, identity, token, agent, 'gpt-6-sol',
                                          'pytest -q', 'counts', parent_agent_id=parent, **kwargs)

    def test_route_is_native_first_and_external_only_with_a_reason(self):
        config = copy.deepcopy(self.policy['delegation'])
        config['enabled'] = True
        route = delegation.selected_route(config, 'implementation', 'codex')
        self.assertEqual({k: route[0][k] for k in ('harness', 'requested_model', 'route_kind', 'route_reason')},
                         {'harness': 'codex', 'requested_model': 'gpt-6-sol', 'route_kind': 'native',
                          'route_reason': 'native-first'})
        self.assertEqual([(c['route_kind'], c['route_reason']) for c in route[1:]],
                         [('external', 'native-failed:pending')] * 2)
        stronger = delegation.stronger_candidate(config, route[1], 'codex')
        self.assertEqual((stronger['route_kind'], stronger['route_reason']), ('external', 'native-failed:pending'))
        cases = {'work-type-disabled': ({'native_allowed': {'implementation': False}}, None),
                 'model-pin': ({}, {'preferred': {'harness': 'selected', 'model': 'pinned-x'}, 'fallbacks': []}),
                 'cross-vendor': ({}, {'preferred': {'harness': 'claude', 'tier': 'standard'},
                                       'fallbacks': [{'harness': 'selected', 'model': None}]})}
        for name, (extra, override) in cases.items():
            with self.subTest(name):
                changed = {**copy.deepcopy(config), **extra}
                if override:
                    changed['overrides'][self.feature + '/T001'] = override
                route = delegation.selected_route(changed, 'implementation', 'codex', self.feature + '/T001')
                self.assertTrue(all(c['route_kind'] == 'external' for c in route))
                self.assertTrue(all(c['route_reason'].startswith(('native-unsupported:', 'external:cross-vendor'))
                                    for c in route), route)
        cross = delegation.selected_route({**config, 'overrides': {self.feature + '/T001': cases['cross-vendor'][1]}},
                                          'implementation', 'codex', self.feature + '/T001')
        self.assertEqual([c['route_reason'] for c in cross],
                         ['external:cross-vendor', 'native-unsupported:cross-vendor-route'])
        self.assertEqual(delegation.selected_route(self.policy['delegation'], 'implementation', 'codex')[0]
                         ['route_reason'], 'native-unsupported:delegation-disabled')
        # Coordination's high tier has no role file to pin its model, so it never goes native first.
        self.assertEqual(delegation.selected_route(config, 'coordination', 'codex')[0]['route_reason'],
                         'native-unsupported:model-pin')
        for bad in ({'bogus': True}, {'implementation': 'yes'}, ['implementation']):
            with self.subTest(bad=bad), self.assertRaisesRegex(delegation.DelegationError,
                                                               'DELEGATION_NATIVE_ALLOWED_INVALID'):
                delegation.validate_delegation({**config, 'native_allowed': bad})

    def test_start_and_collect_carry_route_kind_and_reason_and_a_legacy_attempt_still_loads(self):
        self.tasks()
        self.enable()
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', return_value={'run_id': 'codex-1', 'state': 'running'}):
            started = dispatch.start(self.root, self.feature, 'T001')
        # start never launches the native candidate; the external route says why native was not used.
        self.assertEqual((started['route']['route_kind'], started['route']['route_reason']),
                         ('external', 'native-failed:not-attempted'))
        attempt = dispatch.load_ledger(self.root, self.feature)['attempts'][0]
        self.assertEqual((attempt['route_kind'], attempt['route_reason'], attempt['candidate_index']),
                         ('external', 'native-failed:not-attempted', 0))
        payload = {'run_id': 'codex-1', 'status': 'successful', 'summary': 'done', 'harness': 'codex',
                   'model_observed': False, 'status_provenance': {'primary': 'harness_telemetry'},
                   'dirty_paths_changed': [], 'artifacts': {'dir': str(self.root / '.delegate/runs/codex-1')}}
        with patch.object(delegation, 'inspect_skill', return_value=self.fake_doctor()), \
             patch.object(dispatch.shutil, 'which', return_value='node'), \
             patch.object(dispatch.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), '')):
            collected = dispatch.collect(self.root, self.feature, 'codex-1')
        self.assertEqual((collected['route_kind'], collected['route_reason']),
                         ('external', 'native-failed:not-attempted'))
        with dispatch.edit_ledger(self.root, self.feature) as ledger:
            for key in ('route_kind', 'route_reason'):
                ledger['attempts'][0].pop(key)
        legacy = dispatch.collect(self.root, self.feature, 'codex-1')
        self.assertEqual((legacy['route_kind'], legacy['route_reason']), ('unknown', 'unknown'))

    def test_claim_shows_the_native_candidate_first(self):
        self.tasks()
        self.enable()
        run, claim = self.claim()
        route = claim['delegation']
        self.assertEqual((route['route_kind'], route['candidates'][0]['route_kind'],
                          route['candidates'][0]['route_reason']), ('native', 'native', 'native-first'))
        self.assertIsInstance(route['git_status_at_claim'], list)

    def test_record_native_stage_is_decided_by_the_acceptance_check(self):
        self.enable()
        run, claim = self.claim()
        with self.assertRaisesRegex(delegation.DelegationError, 'DELEGATION_STAGE_CLAIM_MISMATCH'):
            self.record('stage:scope', 'wrong')
        failed = self.record('stage:scope', claim['token'], FAIL, exit_code=1)
        self.assertEqual((failed['status'], failed['accepted'], failed['kind']), ('failed', False, 'native'))
        receipt = fixture.WorkflowTests.receipt(self, 'scope')
        with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_STAGE_NOT_VERIFIED'):
            run.complete(claim['token'], receipt)
        passed = self.record('stage:scope', claim['token'], observed_model='gpt-6-sol', evidence='host transcript',
                             tools=['Read', 'Edit'])
        self.assertEqual((passed['status'], passed['replaces_run_id']), ('successful', failed['run_id']))
        attempt = delegation.latest_attempt(self.root, self.feature, 'stage:scope')
        self.assertEqual({k: attempt[k] for k in ('kind', 'route_kind', 'route_reason', 'host_agent_id',
                                                   'parent_agent_id', 'author_lineage', 'requested_model',
                                                   'actual_model', 'actual_model_evidence', 'tools_granted',
                                                   'claim_token')},
                         {'kind': 'native', 'route_kind': 'native', 'route_reason': 'native-first',
                          'host_agent_id': 'agent-a', 'parent_agent_id': 'top', 'author_lineage': ['top', 'agent-a'],
                          'requested_model': 'gpt-6-sol', 'actual_model': 'gpt-6-sol',
                          'actual_model_evidence': 'host transcript', 'tools_granted': ['Read', 'Edit'],
                          'claim_token': claim['token']})
        self.assertEqual(attempt['git_status_before']['source'], 'claim')
        self.assertIsInstance(attempt['git_status_after'], list)
        self.assertEqual(attempt['accepted_evidence']['source'], 'record-native')
        run.complete(claim['token'], receipt)
        stored = run.load()['receipts']['scope']['native_attestation']
        self.assertEqual((stored['run_id'], stored['evidence']), (passed['run_id'], 'acceptance check passed: pytest -q'))

    def test_record_native_task_needs_the_execute_claim_and_a_passing_check_for_ready(self):
        self.tasks('- [x] T001 Implement parser\n')
        self.enable()
        run = self.execute_claim()
        with self.assertRaisesRegex(delegation.DelegationError, 'DELEGATION_EXECUTE_CLAIM_REQUIRED'):
            self.record('T001', 'wrong')
        result = self.record('T001', 'exec-token', observed_model=None)
        self.assertEqual((result['status'], result['actual_model'], result['actual_model_evidence']),
                         ('successful', 'unreported', 'unverified'))
        self.assertEqual(delegation.latest_attempt(self.root, self.feature, 'T001')['git_status_before']['source'],
                         'unavailable')
        warnings = []
        self.assertIn('tasks', w.ready_checks(self.root, self.feature, self.policy, run.load(), rules=TASK_GATE,
                                              warnings=warnings))
        self.assertTrue(any(warning.startswith('DELEGATION_TASK_NATIVE: T001 by top > agent-a')
                            for warning in warnings), warnings)
        # A self-asserted native task (no acceptance check) never earns Ready.
        with dispatch.edit_ledger(self.root, self.feature) as ledger:
            ledger['attempts'][-1].pop('accepted_evidence')
        with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_TASK_UNVERIFIED: T001'):
            w.ready_checks(self.root, self.feature, self.policy, run.load(), rules=TASK_GATE)

    def test_review_by_the_authoring_lineage_is_refused(self):
        self.tasks('- [x] T001 Implement parser\n- [x] T002 [Review] Review the parser\n')
        self.enable()
        run = self.execute_claim()
        self.record('T001', 'exec-token', agent='agent-a')
        with self.assertRaisesRegex(delegation.DelegationError, 'SAME_LINEAGE_REVIEW'):
            self.record('T002', 'exec-token', agent='agent-a')
        self.assertEqual(self.record('T002', 'exec-token', agent='agent-b')['status'], 'successful')
        w.ready_checks(self.root, self.feature, self.policy, run.load(), rules=TASK_GATE)
        # The Ready gate checks it too, for a ledger written any other way.
        with dispatch.edit_ledger(self.root, self.feature) as ledger:
            ledger['attempts'][-1]['author_lineage'] = ['top', 'agent-a']
        with self.assertRaisesRegex(w.WorkflowError, 'SAME_LINEAGE_REVIEW: T002'):
            w.ready_checks(self.root, self.feature, self.policy, run.load(), rules=TASK_GATE)

    def test_review_by_the_same_agent_is_refused_whichever_recording_gave_a_parent(self):
        for author_parent, reviewer_parent in (('top', None), (None, 'top')):
            with self.subTest(author_parent=author_parent, reviewer_parent=reviewer_parent):
                self.setUp()
                self.tasks('- [x] T001 Implement parser\n- [x] T002 [Review] Review the parser\n')
                self.enable()
                run = self.execute_claim()
                self.record('T001', 'exec-token', agent='agent-a', parent=author_parent)
                with self.assertRaisesRegex(delegation.DelegationError, 'SAME_LINEAGE_REVIEW'):
                    self.record('T002', 'exec-token', agent='agent-a', parent=reviewer_parent)
                self.record('T002', 'exec-token', agent='agent-b', parent=reviewer_parent)
                with dispatch.edit_ledger(self.root, self.feature) as ledger:
                    ledger['attempts'][-1]['author_lineage'] = [p for p in (reviewer_parent, 'agent-a') if p]
                with self.assertRaisesRegex(w.WorkflowError, 'SAME_LINEAGE_REVIEW: T002'):
                    w.ready_checks(self.root, self.feature, self.policy, run.load(), rules=TASK_GATE)

    def test_ready_refuses_a_native_task_whose_line_changed_after_it_was_recorded(self):
        self.tasks('- [x] T001 Implement parser\n')
        self.enable()
        run = self.execute_claim()
        self.record('T001', 'exec-token')
        w.ready_checks(self.root, self.feature, self.policy, run.load(), rules=TASK_GATE)
        self.tasks('- [x] T001 Implement the whole compiler\n')
        with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_ADOPT_TASK_CHANGED: T001'):
            w.ready_checks(self.root, self.feature, self.policy, run.load(), rules=TASK_GATE)

    def test_reassign_refuses_a_native_attempt(self):
        self.tasks('- [x] T001 Implement parser\n')
        self.enable()
        self.execute_claim()
        failed = self.record('T001', 'exec-token', output=FAIL, exit_code=1)
        self.assertEqual(failed['status'], 'failed')
        with self.assertRaisesRegex(delegation.DelegationError,
                                    'DELEGATION_REASSIGN_NATIVE_UNSUPPORTED.*record-native.*start'):
            dispatch.reassign(self.root, self.feature, failed['run_id'], 'try a stronger model')
        self.assertIn('DELEGATION_REASSIGN_NATIVE_UNSUPPORTED', w.ERRORS)

    def test_a_fast_native_record_does_not_shrink_the_external_timeout(self):
        import lean_policy
        candidates = [{'harness': 'codex', 'requested_model': 'gpt-6-sol'}]
        native = {'kind': 'native', 'task_type': 'implementation', 'status': 'successful',
                  'requested_harness': 'codex', 'requested_model': 'gpt-6-sol',
                  'started_at': '2026-10-28T10:00:00+00:00', 'ended_at': '2026-10-28T10:00:05+00:00'}
        default = lean_policy.timeout_guidance(self.policy, [], 'implementation', candidates)
        guided = lean_policy.timeout_guidance(self.policy, [native], 'implementation', candidates)
        self.assertEqual((guided['timeout_seconds'], guided['comparable_runs']), (default['timeout_seconds'], 0))

    def test_a_failed_native_record_blocks_a_review_kind_stage_without_a_route(self):
        self.enable()
        run, claim = self.claim()
        state = run.load()  # a review-kind stage claims with delegation_refused, not a route
        state['active']['delegation_refused'] = {'task_type': 'review'}
        state['active'].pop('delegation', None)
        w.write(run.path, state)
        self.record('stage:scope', claim['token'], FAIL, exit_code=1)
        with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_STAGE_NOT_VERIFIED.*acceptance check failed'):
            run.complete(claim['token'], fixture.WorkflowTests.receipt(self, 'scope'))

    def test_attest_native_honours_the_opt_out_when_the_route_is_cross_vendor(self):
        self.policy['delegation']['native_allowed'] = {'discovery': False}
        self.policy['delegation']['routes']['discovery'] = {'preferred': {'harness': 'claude', 'tier': 'standard'},
                                                            'fallbacks': []}
        self.enable()
        run, claim = self.claim()
        self.assertEqual(run.load()['active']['delegation']['candidates'][0]['route_reason'], 'external:cross-vendor')
        with self.assertRaisesRegex(delegation.DelegationError, 'NATIVE_ROUTE_DISALLOWED'):
            dispatch.attest_native(self.root, self.feature, 'stage:scope', claim['token'], 'gpt-6-sol')

    def test_record_native_refuses_a_disallowed_route_and_a_subagent(self):
        self.tasks('- [x] T001 Implement parser\n')
        self.policy['delegation']['native_allowed'] = {'implementation': False}
        self.enable()
        self.execute_claim()
        with self.assertRaisesRegex(delegation.DelegationError,
                                    'NATIVE_ROUTE_DISALLOWED.*native-unsupported:work-type-disabled'):
            self.record('T001', 'exec-token')
        for env in ({'SANDUQ_DELEGATED_RUN': 'codex-1'}, {'SANDUQ_DELEGATED_ROLE': 'orchestrator'},
                    {'SANDUQ_ROLE': 'worker'}):
            with self.subTest(env=env), patch.dict(os.environ, env), \
                    self.assertRaisesRegex(delegation.DelegationError, 'NATIVE_ATTESTATION_FORBIDDEN'):
                self.record('T001', 'exec-token')


    def adopt(self, task_id='T001', reason=None):
        with patch.object(dispatch, 'run_capped', return_value=self.fake_run_capped(0, PASS)):
            return dispatch.adopt(self.root, self.feature, task_id, 'pytest -q', 'counts', reason=reason)

    def test_adopt_refuses_an_external_route_unless_a_reason_labels_the_substitution(self):
        """2.0.1: implementing an externally routed task in-session and adopting it is a silent substitution."""
        self.tasks('- [x] T001 Implement parser\n')
        self.policy['delegation']['native_allowed'] = {'implementation': False}
        self.enable()
        with self.assertRaisesRegex(delegation.DelegationError, 'DELEGATION_ADOPT_ROUTE_EXTERNAL.*'
                                    'native-unsupported:work-type-disabled.*start --feature .* --id T001'):
            self.adopt()
        self.assertEqual(delegation.ledger_attempts(self.root, self.feature), [])
        result = self.adopt(reason='codex harness missing')
        self.assertEqual((result['status'], result['route_kind'], result['route_reason']),
                         ('successful', 'in-session', 'external-substituted:codex harness missing'))
        self.assertTrue(result['warning'].startswith('DELEGATION_TASK_SUBSTITUTED: T001'))
        attempt = delegation.latest_attempt(self.root, self.feature, 'T001')
        self.assertEqual((attempt['route_kind'], attempt['route_reason']),
                         ('in-session', 'external-substituted:codex harness missing'))
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        warnings = []
        w.ready_checks(self.root, self.feature, self.policy, run.load(), rules=TASK_GATE, warnings=warnings)
        self.assertTrue(any(item.startswith('DELEGATION_TASK_SUBSTITUTED: T001') for item in warnings), warnings)
        # A failed check later resolved by `accept --run-id` replaces the evidence source; the disclosure stays.
        with dispatch.edit_ledger(self.root, self.feature) as ledger:
            ledger['attempts'][-1]['accepted_evidence']['source'] = 'accept'
        warnings = []
        w.ready_checks(self.root, self.feature, self.policy, run.load(), rules=TASK_GATE, warnings=warnings)
        self.assertTrue(any(item.startswith('DELEGATION_TASK_SUBSTITUTED: T001') for item in warnings), warnings)

    def test_adopt_keeps_its_behaviour_on_a_native_first_route_and_with_delegation_off(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                self.setUp()
                self.tasks('- [x] T001 Implement parser\n')
                if enabled:
                    self.enable()
                result = self.adopt(reason='ignored: the route is not external')
                self.assertEqual((result['status'], result['route_kind'], result['route_reason']),
                                 ('successful', 'in-session', 'adopted'))
                self.assertNotIn('warning', result)
                attempt = delegation.latest_attempt(self.root, self.feature, 'T001')
                self.assertEqual((attempt['route_kind'], attempt['route_reason']), ('in-session', 'adopted'))

    def test_accept_refuses_a_reason_with_a_run_id(self):
        with self.assertRaisesRegex(delegation.DelegationError, 'DELEGATION_ACCEPT_REASON_NO_ATTEMPT_ONLY'):
            dispatch.accept(self.root, self.feature, 'codex-1', 'pytest -q', 'counts', reason='x')

del base  # only NativeRoutingTests runs here, not a second copy of DelegationTests


if __name__ == '__main__':
    unittest.main()
