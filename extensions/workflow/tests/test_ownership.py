"""Ownership cleanup in disposable repositories; GitHub responses are explicit fixtures."""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_workflow as fixture

w = fixture.w
import delegate_dispatch as dispatch
import delegation
from task_issues import GitHub


class OwnershipTests(unittest.TestCase):
    setUp = fixture.WorkflowTests.setUp
    configure = fixture.WorkflowTests.configure
    usage = fixture.WorkflowTests.usage

    def owned(self, delegated=True):
        w.git(self.root, 'checkout', '-b', 'feature-10')
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        state = run.load()
        state['target_branch'] = 'develop'
        state['receipts'] = {'pr': {'pr_url': 'https://github.com/acme/app/pull/11', 'outcome': 'passed',
                                    'fingerprints': {}, 'summary': 'historical evidence'}}
        state['active'] = {'stage': 'execute', 'token': 'old-token', 'baseline': {}, 'session_id': 'old-session',
                           'claimed_at': w.now()}
        if delegated:
            state['active']['delegation'] = {'candidates': []}
        run.save(state)
        if delegated:
            self.ledger(run, 'successful')
        self.issue = {'number': 10, 'html_url': 'https://github.com/acme/app/issues/10',
                      'state': 'closed', 'state_reason': 'completed'}
        self.pr = {'html_url': 'https://github.com/acme/app/pull/11', 'state': 'closed', 'merged': True,
                   'merged_at': '2026-10-26T00:00:00Z', 'merge_commit_sha': 'b' * 40,
                   'head': {'ref': 'feature-10', 'sha': 'a' * 40, 'repo': {'full_name': 'acme/app'}},
                   'base': {'ref': 'develop', 'repo': {'full_name': 'acme/app'}}, 'body': 'Closes #10'}
        self.report = {'feature': self.feature, 'repository': 'acme/app', 'target_branch': 'develop',
                       'pr_url': self.pr['html_url'], 'head_sha': 'a' * 40, 'merge_sha': 'b' * 40, 'verified': True}
        return run

    def ledger(self, run, status):
        with dispatch.edit_ledger(self.root, run.relative) as ledger:
            ledger['attempts'] = [{'identity': run.relative + '/stage:execute', 'claim_token': 'old-token',
                                   'run_id': 'run-1', 'status': status}]

    def api(self, endpoint, **kwargs):
        if endpoint == 'repos/acme/app/issues/10':
            return copy.deepcopy(self.issue)
        if endpoint == 'repos/acme/app/pulls/11':
            return copy.deepcopy(self.pr)
        self.fail('unexpected GitHub request: ' + endpoint)

    def cli(self, *args):
        with patch.object(sys, 'argv', ['workflow.py', '--root', str(self.root), *args]), redirect_stdout(io.StringIO()) as out:
            code = w.main()
        return code, json.loads(out.getvalue())

    def test_terminal_release_enables_dependent_claim_once_preserving_receipts(self):
        run = self.owned()
        handoff, prompt = run.path.parent / 'handoff.md', run.path.parent / 'resume-prompt.md'
        handoff.write_text('User note before\n' + w.HANDOFF_BEGIN + '\nold managed content\n' +
                           w.HANDOFF_END + '\nUser note after\n', encoding='utf-8')
        before = run.load()
        w.git(self.root, 'checkout', '-b', 'dependent-20')
        dependent = w.Run(self.root, 'specs/020-dependent')
        dependent.start('acme/app#20')
        with patch.object(GitHub, 'api', side_effect=self.api):
            claimed = dependent.claim(self.usage())
        self.assertEqual('scope', claimed['stage'])
        state = run.load(allow_branch_change=True)
        self.assertIsNone(state['active'])
        self.assertEqual(json.dumps(before['receipts'], sort_keys=True), json.dumps(state['receipts'], sort_keys=True))
        self.assertEqual(before['branch'], state['branch'])
        self.assertEqual(before['head'], state['head'])
        recovery, = state['recoveries']
        self.assertEqual(before['active']['token'], recovery['claim']['token'])
        self.assertEqual('github-rest', recovery['terminal_evidence']['delivery']['transport'])
        self.assertTrue(recovery['actor'])
        self.assertIn('User note before', handoff.read_text(encoding='utf-8'))
        self.assertIn('User note after', handoff.read_text(encoding='utf-8'))
        self.assertIn('- Active claim: None', handoff.read_text(encoding='utf-8'))
        self.assertIn('- Reason: ' + recovery['reason'], handoff.read_text(encoding='utf-8'))
        artifacts = handoff.read_bytes(), prompt.read_bytes()
        checkpoint, events = run.path.read_bytes(), (run.feature / 'workflow/lifecycle.jsonl').read_bytes()
        retry = run.release_ownership(automatic=True)
        self.assertFalse(retry['released'])
        self.assertEqual('paused', retry['status'])
        self.assertEqual(str(run.path), retry['checkpoint'])
        self.assertEqual(prompt.read_text(encoding='utf-8'), retry['prompt'])
        self.assertEqual(checkpoint, run.path.read_bytes())
        self.assertEqual(events, (run.feature / 'workflow/lifecycle.jsonl').read_bytes())
        self.assertEqual(artifacts, (handoff.read_bytes(), prompt.read_bytes()))

    def test_postmerge_releases_before_disabled_memory_without_pr_receipt(self):
        run = self.owned()
        state = run.load()
        del state['receipts']['pr']
        run.save(state)
        with patch.object(GitHub, 'api', side_effect=self.api):
            result = w.memory_handoff.handoff(self.root, 'postmerge', self.feature, report=self.report, run_class=w.Run)
        self.assertTrue(result['ownership']['released'])
        self.assertEqual('MEMORY_DEPENDENCY_MISSING_OR_DISABLED', result['reason'])
        self.assertEqual({}, run.load()['receipts'])
        with patch.object(GitHub, 'api', side_effect=self.api):
            self.assertFalse(w.memory_handoff.handoff(self.root, 'postmerge', self.feature, run_class=w.Run,
                                                     report=self.report)['ownership']['released'])

    def test_enabled_memory_keeps_pr_receipt_guard_after_external_ownership_release(self):
        from test_memory_handoff import MemoryHandoffTests
        run = self.owned()
        state = run.load()
        del state['receipts']['pr']
        run.save(state)
        MemoryHandoffTests.install_memory(self)
        MemoryHandoffTests.enable(self)
        with patch.object(GitHub, 'api', side_effect=self.api):
            result = w.memory_handoff.handoff(self.root, 'postmerge', self.feature, report=self.report, run_class=w.Run)
        self.assertTrue(result['ownership']['released'])
        self.assertFalse(result['ok'])
        self.assertEqual('MEMORY_POSTMERGE_BINDING_MISMATCH', result['reason'])
        self.assertEqual([], result['actions'])
        self.assertIsNone(run.load()['active'])
        self.assertEqual({}, run.load()['receipts'])
        self.assertFalse((self.memory_state / 'active.json').exists())
        self.assertFalse((self.memory_state / 'pending.json').exists())
        checkpoint = run.path.read_bytes()
        retry = w.memory_handoff.handoff(self.root, 'postmerge', self.feature, report=self.report, run_class=w.Run)
        self.assertFalse(retry['ownership']['released'])
        self.assertFalse(retry['ok'])
        self.assertEqual('MEMORY_POSTMERGE_BINDING_MISMATCH', retry['reason'])
        self.assertEqual(checkpoint, run.path.read_bytes())

    def test_live_unknown_and_untrusted_writers_fail_closed_without_network(self):
        run = self.owned()
        for status in ('starting', 'running', 'cancelled', 'unknown'):
            with self.subTest(status=status):
                self.ledger(run, status)
                before = run.path.read_bytes()
                with patch.object(GitHub, 'api') as api, self.assertRaisesRegex((w.WorkflowError, ValueError), 'OWNERSHIP_(EXECUTOR_ACTIVE|UNVERIFIABLE)'):
                    run.release_ownership(automatic=True)
                api.assert_not_called()
                self.assertEqual(before, run.path.read_bytes())
        self.ledger(run, 'successful')
        delegation.record_foreign_write(self.root, self.feature)
        with self.assertRaisesRegex((w.WorkflowError, ValueError), 'OWNERSHIP_UNVERIFIABLE'):
            run.release_ownership('old-token', 'inspected stopped owner')

    def test_native_legacy_requires_exact_token_recovery_on_deleted_branch(self):
        run = self.owned(delegated=False)
        handoff, prompt = run.path.parent / 'handoff.md', run.path.parent / 'resume-prompt.md'
        handoff.write_text('Keep these user notes.\n', encoding='utf-8')
        before = run.load()
        w.git(self.root, 'checkout', '-b', 'new-work')
        w.git(self.root, 'branch', '-D', before['branch'])
        checkpoint = run.path.read_bytes()
        checked = subprocess.run([sys.executable, str(w.__file__), '--root', str(self.root),
                                  'status', '--feature', self.feature], capture_output=True, text=True, encoding='utf-8')
        code, status = checked.returncode, json.loads(checked.stdout)
        self.assertEqual(0, code, status)
        self.assertEqual('old-token', status['active']['token'])
        self.assertEqual(checkpoint, run.path.read_bytes())
        with self.assertRaisesRegex((w.WorkflowError, ValueError), 'OWNERSHIP_UNVERIFIABLE.*recover --feature'):
            run.release_ownership(automatic=True)
        with self.assertRaisesRegex((w.WorkflowError, ValueError), 'CLAIM_TOKEN_MISMATCH'):
            run.release_ownership('wrong', 'inspected owner')
        self.assertEqual(checkpoint, run.path.read_bytes())
        code, result = self.cli('recover', '--feature', self.feature, '--token', 'old-token', '--reason', 'Owner stopped; inspected writes')
        self.assertEqual(0, code, result)
        self.assertTrue(result['released'])
        self.assertEqual('paused', result['status'])
        self.assertEqual(str(run.path), result['checkpoint'])
        self.assertEqual(prompt.read_text(encoding='utf-8'), result['prompt'])
        self.assertIn('Keep these user notes.', handoff.read_text(encoding='utf-8'))
        self.assertIn('- Active claim: None', handoff.read_text(encoding='utf-8'))
        self.assertIn('- Reason: Owner stopped; inspected writes', handoff.read_text(encoding='utf-8'))
        state = run.load(allow_branch_change=True)
        self.assertEqual(before['branch'], state['branch'])
        self.assertEqual(before['head'], state['head'])
        self.assertEqual(before['receipts'], state['receipts'])
        artifacts = run.path.read_bytes(), handoff.read_bytes(), prompt.read_bytes()
        self.assertFalse(run.release_ownership('old-token', 'retry')['released'])
        self.assertEqual(artifacts, (run.path.read_bytes(), handoff.read_bytes(), prompt.read_bytes()))
        with self.assertRaisesRegex((w.WorkflowError, ValueError), 'CHECKPOINT_BRANCH_MISMATCH'):
            run.claim(self.usage())

    def test_delivery_mismatches_and_unavailable_github_leave_claim_untouched(self):
        run = self.owned()
        original_issue, original_pr = copy.deepcopy(self.issue), copy.deepcopy(self.pr)
        changes = [('issue', 'state', 'open'), ('issue', 'state_reason', 'not_planned'),
                   ('issue', 'number', 99), ('pr', 'merged', False), ('pr', 'state', 'open'),
                   ('pr', 'body', 'Relates to #10'), ('head', 'ref', 'wrong-feature'),
                   ('base', 'ref', 'main'), ('head', 'repo', {'full_name': 'foreign/app'}),
                   ('base', 'repo', {'full_name': 'foreign/app'}), ('pr', 'merge_commit_sha', None)]
        for group, key, value in changes:
            with self.subTest(group=group, key=key):
                self.issue, self.pr = copy.deepcopy(original_issue), copy.deepcopy(original_pr)
                target = self.issue if group == 'issue' else self.pr if group == 'pr' else self.pr[group]
                target[key] = value
                before = run.path.read_bytes()
                with patch.object(GitHub, 'api', side_effect=self.api), self.assertRaisesRegex((w.WorkflowError, ValueError), 'OWNERSHIP_DELIVERY'):
                    run.release_ownership(automatic=True)
                self.assertEqual(before, run.path.read_bytes())
        before = run.path.read_bytes()
        with patch.object(GitHub, 'api', side_effect=w.WorkflowError('GITHUB_API_FAILED')):
            with self.assertRaisesRegex((w.WorkflowError, ValueError), 'GITHUB_API_FAILED'):
                run.release_ownership(automatic=True)
        self.assertEqual(before, run.path.read_bytes())

    def test_report_cannot_override_bound_pr_repository_target_or_shas(self):
        run = self.owned()
        for key, value in [('feature', 'specs/other'), ('repository', 'foreign/app'), ('target_branch', 'main'),
                           ('pr_url', 'https://github.com/acme/app/pull/12'), ('verified', False),
                           ('head_sha', 'c' * 40), ('merge_sha', 'c' * 40), ('report_only', True)]:
            with self.subTest(key=key):
                before = run.path.read_bytes()
                with patch.object(GitHub, 'api', side_effect=self.api), self.assertRaisesRegex((w.WorkflowError, ValueError), 'OWNERSHIP_DELIVERY'):
                    run.release_ownership(automatic=True, report={**self.report, key: value})
                self.assertEqual(before, run.path.read_bytes())

    def test_claim_replacement_during_external_verification_is_never_released(self):
        run = self.owned()
        def racing_api(endpoint, **kwargs):
            answer = self.api(endpoint)
            if '/pulls/' in endpoint:
                state = w.read(run.path)
                state['active']['token'] = 'replacement'
                w.write(run.path, state)
            return answer
        with patch.object(GitHub, 'api', side_effect=racing_api), self.assertRaisesRegex((w.WorkflowError, ValueError), 'OWNERSHIP_CHANGED'):
            run.release_ownership(automatic=True)
        self.assertEqual('replacement', w.read(run.path)['active']['token'])
        self.assertFalse(w.read(run.path).get('recoveries'))

    def test_worker_reservation_rechecks_claim_after_recovery(self):
        run = self.owned(delegated=False)
        task = self.root / 'assignment.md'
        task.write_text('Bound stage assignment', encoding='utf-8')
        candidate = {'harness': 'codex', 'requested_model': 'gpt-6.1-sol', 'tier': 'standard', 'read_only': False}
        def before_reservation(*args, **kwargs):
            run.release_ownership('old-token', 'Owner stopped before worker reservation')
            return {'ok': True, 'driver': str(self.root / 'driver.mjs'), 'harnesses': {'codex': True}}
        with patch.object(delegation, 'doctor', side_effect=before_reservation), patch.object(dispatch, 'launch') as launch:
            with self.assertRaisesRegex(delegation.DelegationError, 'DELEGATION_STAGE_CLAIM_MISMATCH'):
                dispatch.candidate_start(self.root, self.feature, self.feature + '/stage:execute', 'implementation',
                                         [candidate], task, self.root, 1800, claim_token='old-token')
            launch.assert_not_called()
        self.assertEqual([], dispatch.load_ledger(self.root, self.feature)['attempts'])


if __name__ == '__main__':
    unittest.main()
