"""Actual installed Memory CLI decisions in disposable native Workflow fixtures.

No archive preparation/finalization, network, synthesis or fake archive success.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_workflow as fixture

w = fixture.w
mh = w.memory_handoff
SOURCE = Path(__file__).resolve().parents[2] / 'memory'


class MemoryHandoffTests(unittest.TestCase):
    setUp = fixture.WorkflowTests.setUp
    configure = fixture.WorkflowTests.configure
    receipt = fixture.WorkflowTests.receipt
    run_object = fixture.WorkflowTests.run_object

    def install_memory(self):
        w.git(self.root, 'config', 'core.autocrlf', 'false')
        # A consumer keeps Workflow runtime state local, so Memory never sees it as feature input.
        w.ensure_local_excludes(self.root)
        installed = self.root / '.specify/extensions/memory'
        shutil.copytree(SOURCE / 'scripts', installed / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(SOURCE / 'extension.yml', installed / 'extension.yml')
        # Packaging stages these shared helpers beside the Memory scripts.
        for helper in ('check_inputs.py', 'bounded_json.py'):
            shutil.copyfile(SOURCE.parent / 'scripts/shared' / helper, installed / 'scripts' / helper)
        entries = w.registry(self.root)
        entries['memory'] = {'enabled': True, 'version': '2.1.1'}
        w.write(self.root / '.specify/extensions/.registry', {'extensions': entries})
        self.policy_file = self.root / '.specify/memory-policy.json'
        w.write(self.policy_file, {'schema_version': 1, 'target_branch': 'develop',
                                  'default_checks': ['product'], 'checks': {
                                      'product': {'argv': [sys.executable, '-c', 'pass'],
                                                  'covers': ['src/*', 'tests/*']}}})
        self.memory_state = self.root / '.git/sanduq-memory'
        w.git(self.root, 'branch', 'develop')
        for name in ('prepare', 'session', 'run'):
            path = self.root / f'.agents/skills/speckit-memory-{name}/SKILL.md'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture registration', encoding='utf-8')

    def enable(self):
        # Real Memory approval API: the fixture explicitly authorizes its exact
        # installed implementation and policy. This never enables a consumer.
        w.git(self.root, 'add', '-A')
        w.git(self.root, 'commit', '-qm', 'fixture policy and implementation')
        policy = mh.helper(self.root, 'policy')
        mh.helper(self.root, 'enable', '--approve-hash', policy['policy_hash'])

    def executed(self, provider='speckit.implement', complete=True):
        run = self.run_object()
        receipt = self.receipt('execute')
        state = run.load()
        state['commands']['execute'] = provider
        state['active'] = {'stage': 'execute', 'token': 'execute-token', 'baseline': {}}
        state['target_branch'] = 'develop'
        run.save(state)
        return (run, run.complete('execute-token', receipt)) if complete else (run, receipt)

    def call(self, transition='execute', **kwargs):
        return mh.handoff(w, self.root, transition, kwargs.pop('feature', self.feature), **kwargs)

    def merge(self):
        w.git(self.root, 'add', '-A')
        w.git(self.root, 'commit', '-qm', 'fixture implementation')
        self.head = w.git(self.root, 'rev-parse', 'HEAD')
        w.git(self.root, 'checkout', 'develop')
        w.git(self.root, 'merge', '--no-ff', '-', '-m', 'fixture merge')

    def postmerge_report(self, run):
        state = run.load(allow_branch_change=True)
        state['receipts']['pr'] = {'pr_url': 'https://github.com/acme/app/pull/12'}
        # Save the fixture checkpoint directly; preserve its original feature branch.
        w.write(run.path, state)
        return {'feature': self.feature, 'repository': 'acme/app',
                'pr_url': state['receipts']['pr']['pr_url'], 'target_branch': 'develop',
                'verified': True, 'head_sha': self.head,
                'merge_sha': w.git(self.root, 'rev-parse', 'HEAD')}

    def test_missing_and_registry_disabled_are_durable_pending(self):
        self.assertEqual('MEMORY_DEPENDENCY_MISSING_OR_DISABLED', self.call()['reason'])
        self.install_memory()
        entries = w.registry(self.root)
        entries['memory']['enabled'] = False
        w.write(self.root / '.specify/extensions/.registry', {'extensions': entries})
        result = self.call()
        self.assertEqual('pending', result['status'])
        self.assertTrue((self.root / result['state_file']).is_file())

    def test_disabled_memory_preserves_accepted_execute(self):
        self.install_memory()
        run, result = self.executed()
        self.assertEqual('pending', result['memory_handoff']['status'])
        self.assertIn('disabled', result['memory_handoff']['reason'])
        self.assertEqual('passed', run.load()['receipts']['execute']['outcome'])
        self.assertFalse((self.memory_state / 'pending.json').exists())

    def test_both_providers_queue_once_and_duplicate_completion_cannot_reset(self):
        self.install_memory()
        self.enable()
        run, result = self.executed('speckit.superspec.execute')
        self.assertEqual('queued', result['memory_handoff']['status'])
        before = (self.memory_state / 'pending.json').read_bytes()
        self.assertEqual('MEMORY_ALREADY_QUEUED', self.call()['reason'])
        # The same native path is used after Core completion too.
        state = run.load()
        state['commands']['execute'] = 'speckit.implement'
        state['active'] = {'stage': 'execute', 'token': 'core-token', 'baseline': {}}
        run.save(state)
        result = run.complete('core-token', self.receipt('execute'))
        self.assertEqual('MEMORY_ALREADY_QUEUED', result['memory_handoff']['reason'])
        with self.assertRaisesRegex(w.WorkflowError, 'CLAIM_TOKEN_MISMATCH'):
            run.complete('core-token', self.receipt('execute'))
        self.assertEqual(before, (self.memory_state / 'pending.json').read_bytes())

    def test_stale_approval_never_queues(self):
        self.install_memory()
        self.enable()
        policy = w.read(self.policy_file)
        policy['default_checks'] = []
        w.write(self.policy_file, policy)
        self.assertIn('renewal', self.call()['reason'])
        self.assertFalse((self.memory_state / 'pending.json').exists())

    def test_wrong_approved_checkout_never_queues(self):
        self.install_memory()
        self.enable()
        approval = w.read(self.memory_state / 'approval.json')
        approval['root'] = str(self.root / 'other-worktree')
        w.write(self.memory_state / 'approval.json', approval)
        self.assertEqual('MEMORY_APPROVAL_CHECKOUT_MISMATCH', self.call()['reason'])

    def test_check_selection_and_real_coverage_error_preserve_receipt(self):
        self.install_memory()
        policy = w.read(self.policy_file)
        policy['default_checks'] = []
        w.write(self.policy_file, policy)
        self.enable()
        run, result = self.executed()
        self.assertEqual('MEMORY_CHECK_SELECTION_REQUIRED', result['memory_handoff']['reason'])
        self.assertEqual('speckit.memory.prepare', result['memory_handoff']['actions'][0]['command'])
        (self.root / 'src').mkdir()
        (self.root / 'src/app.py').write_text('product = True', encoding='utf-8')
        # Unknown approved name and coverage errors come from the real helper.
        failed = self.call(checks=['unknown'])
        self.assertFalse(failed['ok'])
        self.assertIn('Select named verification commands', failed['reason'])
        policy['checks']['docs'] = {'argv': [sys.executable, '-c', 'pass'], 'covers': ['docs/*']}
        w.write(self.policy_file, policy)
        self.enable()
        failed = self.call(checks=['docs'])
        self.assertFalse(failed['ok'])
        self.assertIn('cover', failed['reason'])
        self.assertEqual('passed', run.load()['receipts']['execute']['outcome'])

    def test_target_branch_waits_and_eligible_handoff_dispatches_registered_run(self):
        self.install_memory()
        self.enable()
        run, _ = self.executed()
        self.assertIn('Awaiting local merge', self.call('session')['reason'])
        self.merge()
        result = self.call('session')
        self.assertEqual('speckit.memory.session', result['actions'][0]['command'])
        report = self.postmerge_report(run)
        mh.helper(self.root, 'verify', '--spec', self.feature, '--complete', '--check', 'product')
        before = w.read(run.path)
        result = self.call('postmerge', report=report)
        self.assertEqual('dispatch', result['status'])
        self.assertEqual({'command': 'speckit.memory.run',
                          'arguments': ['--spec', self.feature, '--automatic', '--check', 'product'],
                          'reason': 'Approved eligible work; synthesis and independent review still required.'},
                         result['actions'][0])
        self.assertEqual(before['receipts']['execute'], w.read(run.path)['receipts']['execute'])
        self.assertFalse((self.memory_state / 'active.json').exists())
        self.assertTrue((self.root / self.feature).is_dir())

    def test_postmerge_requires_exact_feature_repo_pr_target_and_ancestry(self):
        self.install_memory()
        self.enable()
        run, _ = self.executed()
        self.merge()
        report = self.postmerge_report(run)
        for key, value in [('feature', 'specs/999-other'), ('repository', 'other/repo'),
                           ('pr_url', 'https://github.com/acme/app/pull/99'),
                           ('target_branch', 'main'), ('verified', False)]:
            with self.subTest(key=key):
                self.assertEqual('MEMORY_POSTMERGE_BINDING_MISMATCH',
                                 self.call('postmerge', report={**report, key: value})['reason'])
        self.assertFalse(self.call('postmerge', report={**report, 'merge_sha': 'f' * 40})['ok'])
        result = self.call('postmerge', report={**report, 'report_only': True})
        self.assertEqual('MEMORY_REPORT_ONLY_FOLLOWUP', result['reason'])
        self.assertEqual([], result['actions'])

    def test_active_recovery_precedes_disabled_mode_and_new_work(self):
        self.install_memory()
        pending = {'enabled': False, 'ready': [], 'blocked': [], 'active_run': 'a' * 32,
                   'writer': None, 'guard_blockers': [], 'reason': 'disabled'}
        with patch.object(mh, 'helper', side_effect=[pending, {'active': {'phase': 'prepared'}}]) as helper:
            result = self.call('session')
        self.assertEqual('MEMORY_ACTIVE_RECOVERY_REQUIRED', result['reason'])
        self.assertEqual(['--run', 'a' * 32], result['actions'][0]['arguments'])
        self.assertEqual('status', helper.call_args_list[-1].args[1])
        self.assertFalse(result['ok'])

    def test_native_cli_recovers_unicode_active_run_under_cp1252(self):
        self.install_memory()
        run_id = 'b' * 32
        text = 'Implemented \u2192 \u0645\u0631\u0627\u062c\u0639\u0629 \u0627\u0644\u0630\u0627\u0643\u0631\u0629'
        active = self.memory_state / 'active.json'
        journal = self.memory_state / 'runs' / run_id / 'journal.json'
        w.write(active, {'run_id': run_id})
        w.write(journal, {'run_id': run_id, 'root': str(self.root), 'phase': 'synthesis',
                          'units': [{'id': 'L1', 'text': text}]})
        before = {path: path.read_bytes() for path in (active, journal, self.policy_file)}
        head = w.git(self.root, 'rev-parse', 'HEAD')
        environment = {**os.environ, 'PYTHONIOENCODING': 'cp1252', 'PYTHONUTF8': '0'}
        result = subprocess.run(
            [sys.executable, '-B', str(Path(w.__file__)), '--root', str(self.root),
             'memory-handoff', '--transition', 'session'],
            env=environment, capture_output=True)
        self.assertEqual(b'', result.stderr)
        body = json.loads(result.stdout.decode('utf-8'))
        self.assertEqual('MEMORY_ACTIVE_RECOVERY_REQUIRED', body['reason'])
        # Recovery still gates new lifecycle work; retrieving it is not finalization.
        self.assertEqual(1, result.returncode)
        self.assertFalse(body['ok'])
        self.assertEqual('blocked', body['status'])
        self.assertFalse(body['pending']['enabled'])
        self.assertEqual('synthesis', body['pending']['active_phase'])
        self.assertIsNone(body['pending']['writer'])
        self.assertEqual(text, body['recovery']['active']['units'][0]['text'])
        self.assertEqual([{'command': 'speckit.memory.session', 'arguments': ['--run', run_id],
                           'reason': 'Resume the active transaction before new work.'}], body['actions'])
        for path, content in before.items():
            self.assertEqual(content, path.read_bytes())
        self.assertEqual(head, w.git(self.root, 'rev-parse', 'HEAD'))
        self.assertFalse((self.memory_state / 'approval.json').exists())
        self.assertFalse((self.memory_state / 'pending.json').exists())

    def test_helper_overrides_only_child_io_encoding(self):
        process = subprocess.CompletedProcess([], 0, '{"success":true,"data":{}}', '')
        with patch.dict(os.environ, {'PYTHONIOENCODING': 'cp1252', 'PYTHONUTF8': '0',
                                     'SANDUQ_UTF8_PROBE': 'preserve exactly'}):
            environment = dict(os.environ)
            with patch.object(mh.subprocess, 'run', return_value=process) as invoke:
                self.assertEqual({}, mh.helper(self.root, 'status'))
            self.assertTrue({**environment, 'PYTHONIOENCODING': 'utf-8'} == invoke.call_args.kwargs['env'],
                            'Child environment changed beyond its I/O encoding')
            self.assertTrue(environment == dict(os.environ), 'Parent environment was modified')

    def test_nonzero_false_and_malformed_envelopes_fail_and_remain_durable(self):
        self.install_memory()
        for code, body in [(7, {'success': True, 'data': {}}),
                           (0, {'success': False, 'error': 'helper rejected'}),
                           (0, []), (0, {'success': True}), (0, 'not json')]:
            with self.subTest(code=code, body=body):
                result = subprocess.CompletedProcess([], code,
                    body if isinstance(body, str) else json.dumps(body), '')
                with patch.object(mh.subprocess, 'run', return_value=result):
                    failed = self.call()
                self.assertFalse(failed['ok'])
                self.assertEqual('blocked', failed['status'])
                self.assertEqual(failed['reason'], w.read(self.root / failed['state_file'])['reason'])

    def test_helper_uses_explicit_argument_array_and_honors_nonzero_success(self):
        process = subprocess.CompletedProcess([], 9, '{"success":true,"data":{}}', '')
        with patch.object(mh.subprocess, 'run', return_value=process) as invoke:
            with self.assertRaisesRegex(mh.HandoffError, 'FAILED \\(9\\)'):
                mh.helper(self.root, 'queue', '--spec', self.feature, '--check', 'product')
        self.assertEqual([sys.executable, '-B', str(self.root / '.specify/extensions/memory/scripts/archive.py'),
                          '--root', str(self.root), 'queue', '--spec', self.feature, '--check', 'product'],
                         invoke.call_args.args[0])

    def test_lost_queue_response_is_recoverable_without_resetting_entry(self):
        self.install_memory()
        self.enable()
        original = mh.helper

        def interrupted(root, *args):
            result = original(root, *args)
            if args[0] == 'queue':
                raise mh.HandoffError('MEMORY_HELPER_FAILED (1): response lost after durable queue')
            return result

        with patch.object(mh, 'helper', side_effect=interrupted):
            run, result = self.executed()
        self.assertFalse(result['ok'])
        self.assertEqual('passed', run.load()['receipts']['execute']['outcome'])
        self.assertIsNone(run.load()['active'])
        before = (self.memory_state / 'pending.json').read_bytes()
        self.assertEqual('MEMORY_ALREADY_QUEUED', self.call()['reason'])
        self.assertEqual(before, (self.memory_state / 'pending.json').read_bytes())

    def test_old_enablement_queue_remains_pending_without_reset(self):
        self.install_memory()
        self.enable()
        self.executed()
        queue = w.read(self.memory_state / 'pending.json')
        queue[self.feature]['enabled_at'] = 'old-enablement'
        w.write(self.memory_state / 'pending.json', queue)
        before = (self.memory_state / 'pending.json').read_bytes()
        self.assertIn('predates current enablement', self.call()['reason'])
        self.assertEqual(before, (self.memory_state / 'pending.json').read_bytes())

    def test_native_cli_requires_explicit_feature_and_propagates_failure_exit(self):
        script = Path(w.__file__)
        command = [sys.executable, '-B', str(script), '--root', str(self.root), 'memory-handoff']
        missing = subprocess.run([*command, '--transition', 'execute'], capture_output=True, text=True)
        self.assertEqual(1, missing.returncode)
        self.assertEqual('EXPLICIT_FEATURE_REQUIRED', json.loads(missing.stdout)['error'])
        self.install_memory()
        # Actual CLI malformed installed-helper failure, not an asserted success.
        helper = self.root / '.specify/extensions/memory/scripts/archive.py'
        helper.write_text('print("malformed helper response")', encoding='utf-8')
        result = subprocess.run([*command, '--transition', 'session'], capture_output=True, text=True)
        self.assertEqual(1, result.returncode)
        body = json.loads(result.stdout)
        self.assertFalse(body['ok'])
        self.assertIn('MEMORY_HELPER_MALFORMED', body['reason'])

    def test_pending_with_policy_facts_saves_the_policy_helper(self):
        # PM24: with automatic mode on, Memory's `pending` carries policy_hash and policy; no second helper process.
        self.install_memory()
        pending = {'enabled': True, 'ready': [], 'blocked': [], 'active_run': None, 'writer': None,
                   'guard_blockers': [], 'policy_hash': 'f' * 64,
                   'policy': {'target_branch': 'develop', 'default_checks': ['product']}}
        with patch.object(mh, 'helper', return_value=pending) as helper:
            result = self.call('session')
        self.assertEqual(['pending'], [c.args[1] for c in helper.call_args_list])
        self.assertEqual('pending', result['status'])  # the fixture approval does not match this hash

    def test_missing_registered_action_is_a_concrete_blocker(self):
        self.install_memory()
        (self.root / '.agents/skills/speckit-memory-session/SKILL.md').unlink()
        pending = {'enabled': False, 'ready': [], 'blocked': [], 'active_run': 'a' * 32,
                   'writer': None, 'guard_blockers': []}
        with patch.object(mh, 'helper', side_effect=[pending, {}]):
            result = self.call('session')
        self.assertFalse(result['ok'])
        self.assertEqual('MEMORY_COMMAND_UNAVAILABLE: speckit.memory.session', result['reason'])


class ClaimSessionHandoffTests(unittest.TestCase):
    """W14: the claim runs the session handoff the before_specify hook ran, under the dispatch lock it holds."""
    setUp = fixture.WorkflowTests.setUp
    configure = fixture.WorkflowTests.configure
    usage = fixture.WorkflowTests.usage
    run_object = fixture.WorkflowTests.run_object
    install_memory = MemoryHandoffTests.install_memory

    DISABLED = {'enabled': False, 'ready': [], 'blocked': [], 'active_run': None,
                'writer': None, 'guard_blockers': [], 'reason': 'MEMORY_AUTOMATIC_MODE_DISABLED'}

    def test_claim_without_memory_starts_no_helper_and_records_the_session(self):
        run = self.run_object()
        with patch.object(mh, 'helper', side_effect=AssertionError('no helper without Memory')):
            claim = run.claim(self.usage())
        self.assertEqual('scope', claim['stage'])
        self.assertNotIn('memory_handoff', claim)
        self.assertEqual({'session_id': 'new-session', 'status': 'pending'},
                         {k: v for k, v in run.load()['memory_session'].items() if k != 'at'})

    def test_claim_runs_the_handoff_inside_its_own_dispatch_lock(self):
        # The lock is not re-entrant: without lock=False the handoff would block on WORKFLOW_BUSY.
        self.install_memory()
        run = self.run_object()
        with patch.object(mh, 'helper', return_value=dict(self.DISABLED)) as helper:
            claim = run.claim(self.usage())
        self.assertEqual('scope', claim['stage'])
        self.assertEqual(['pending'], [c.args[1] for c in helper.call_args_list])

    def test_every_blocked_result_refuses_the_claim_and_is_not_recorded(self):
        self.install_memory()
        run = self.run_object()
        active = {**self.DISABLED, 'active_run': 'a' * 32}
        for side_effect, reason in (([active, {'active': {}}], 'MEMORY_ACTIVE_RECOVERY_REQUIRED'),
                                    ([{'enabled': True}], 'MEMORY_HELPER_MALFORMED')):
            with patch.object(mh, 'helper', side_effect=side_effect):
                claim = run.claim(self.usage())
            self.assertIs(claim['ok'], False)
            self.assertEqual('memory_blocked', claim['status'])
            self.assertIn(reason, claim['memory_handoff']['reason'])
            state = run.load()
            self.assertIsNone(state['active'])
            self.assertNotIn('memory_session', state)

    def test_an_unavailable_memory_command_refuses_the_claim(self):
        self.install_memory()
        (self.root / '.agents/skills/speckit-memory-session/SKILL.md').unlink()
        run = self.run_object()
        with patch.object(mh, 'helper', side_effect=[{**self.DISABLED, 'active_run': 'a' * 32}, {}]):
            claim = run.claim(self.usage())
        self.assertIn('MEMORY_COMMAND_UNAVAILABLE', claim['memory_handoff']['reason'])
        self.assertIsNone(run.load()['active'])

    def test_dispatch_returns_the_actions_before_granting_work(self):
        run = self.run_object()
        dispatch = {'status': 'dispatch', 'ok': True, 'reason': 'MEMORY_REGISTERED_ACTION_REQUIRED',
                    'actions': [{'command': 'speckit.memory.run', 'arguments': [], 'reason': 'x'}]}
        with patch.object(mh, 'handoff', return_value=dispatch):
            claim = run.claim(self.usage())
        self.assertEqual('memory_dispatch', claim['status'])
        self.assertTrue(claim['ok'])
        self.assertEqual(dispatch, claim['memory_handoff'])
        self.assertIsNone(run.load()['active'])

    def test_every_claim_runs_the_handoff_whatever_session_id_it_supplies(self):
        """I2: the usage session_id is the model's word, not the host's, so a repeated one never skips the handoff."""
        run = self.run_object()
        state = run.load()
        state['memory_session'] = {'session_id': 'old', 'status': 'idle', 'at': w.now()}
        idle = {'status': 'idle', 'ok': True, 'reason': 'MEMORY_NO_ELIGIBLE_WORK', 'actions': []}
        with patch.object(mh, 'handoff', return_value=idle) as handoff:
            self.assertIsNone(run.memory_session(state, 'clarify', 'old'))
            self.assertEqual(1, handoff.call_count)
            self.assertIsNone(run.memory_session(state, 'clarify', 'new'))
            self.assertIsNone(run.memory_session(state, 'clarify', 'new'))
            self.assertIsNone(run.memory_session(state, 'specify', 'new'))
        self.assertEqual(4, handoff.call_count)
        self.assertFalse(handoff.call_args.kwargs['lock'])
        self.assertEqual('new', state['memory_session']['session_id'])


if __name__ == '__main__':
    unittest.main()
