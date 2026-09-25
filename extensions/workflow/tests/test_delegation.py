"""Opt-in routing, task compatibility and measured delegation history."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import delegate_dispatch as dispatch
import delegation
import task_issues
import workflow as w
import test_workflow as fixture


class DelegationTests(unittest.TestCase):
    configure = fixture.WorkflowTests.configure

    def setUp(self):
        fixture.WorkflowTests.setUp(self)

    def enable(self):
        self.policy['delegation']['enabled'] = True
        self.configure()

    def tasks(self, content='- [ ] T001 [P] Implement parser\n- [ ] T002 [QA] Run tests\n- [x] T003 Done docs\n'):
        path = self.root / self.feature / 'tasks.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def test_disabled_by_default_and_legacy_policy_stays_disabled(self):
        self.assertFalse(self.policy['delegation']['enabled'])
        self.assertFalse(dispatch.start(self.root, self.feature, 'T001')['enabled'])
        old = self.policy.copy(); old.pop('delegation')
        self.assertFalse(w.validate_policy(old)['delegation']['enabled'])

    def test_init_selection_requires_review_and_preserves_custom_routes(self):
        script = Path(w.__file__)
        policy_path = self.root / '.specify/workflow.yml'
        policy_path.unlink()
        def run(*args):
            return subprocess.run([sys.executable, str(script), '--root', str(self.root),
                                   'init', '--qa', 'on', '--manual', 'on', *args],
                                  capture_output=True, text=True)
        self.assertEqual(run('--delegate', 'off').returncode, 0)
        self.assertFalse(w.load_policy(self.root)['delegation']['enabled'])
        self.assertIn('DELEGATION_SELECTION_EXISTS', run('--delegate', 'on').stdout)
        policy = w.load_policy(self.root)
        policy['delegation']['models']['codex']['standard'] = 'team-model'
        policy_path.write_text(__import__('yaml').safe_dump(policy), encoding='utf-8')
        self.assertEqual(run('--delegate', 'on', '--replace').returncode, 0)
        selected = w.load_policy(self.root)['delegation']
        self.assertTrue(selected['enabled'])
        self.assertEqual(selected['models']['codex']['standard'], 'team-model')

    def test_claim_refreshes_pending_metadata_and_exposes_stage_route(self):
        path = self.tasks()
        self.enable()
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(w, 'doctor', return_value={'ok': True, 'errors': []}):
            claim = run.claim({'session_id': 'test-session'})
        self.assertEqual(claim['delegation']['task_type'], 'discovery')
        self.assertEqual(claim['delegation']['candidates'][0]['requested_model'], 'gpt-6-astra')
        self.assertIn('sanduq-delegation', path.read_text(encoding='utf-8'))

    def test_route_override_precedence_and_validation(self):
        config = self.policy['delegation']
        config['overrides'][self.feature + '/T001'] = {
            'preferred': {'harness': 'claude', 'model': 'custom-reviewer'}, 'fallbacks': []}
        route = delegation.selected_route(config, 'implementation', 'codex', self.feature + '/T001')
        self.assertEqual((route[0]['harness'], route[0]['requested_model']),
                         ('claude', 'custom-reviewer'))
        self.assertEqual(route[0]['rule'], 'override:' + self.feature + '/T001')
        self.assertEqual(delegation.selected_route(config, 'implementation', 'codex',
                                                    self.feature + '/T002')[0]['requested_model'],
                         'gpt-6-sol')
        config['overrides']['T001'] = config['overrides'].pop(self.feature + '/T001')
        with self.assertRaisesRegex(delegation.DelegationError, 'OVERRIDE_KEY_INVALID'):
            delegation.validate_delegation(config)

    def test_default_routes_cover_all_work_types_on_both_harnesses(self):
        expected = {
            'codex': ['gpt-6-astra', 'gpt-6-sol', 'gpt-6-terra',
                      'gpt-6-sol', 'gpt-6-sol', 'gpt-6-terra'],
            'claude': ['opus', 'sonnet', 'haiku', 'opus', 'opus', 'haiku'],
        }
        for host, models in expected.items():
            actual = [delegation.selected_route(self.policy['delegation'], work_type, host)[0]
                      ['requested_model'] for work_type in delegation.TYPES]
            self.assertEqual(actual, models)

    def test_annotation_preserves_task_lines_and_earlier_task_fingerprints(self):
        path = self.tasks()
        before = w.fingerprint_files(self.root, [self.feature + '/tasks.md'])
        self.enable()
        result = delegation.annotate_tasks(self.root, self.feature, self.policy['delegation'], 'codex')
        self.assertEqual(result['annotated'], 2)
        text = path.read_text(encoding='utf-8')
        self.assertIn('"task_type": "qa"', text)
        self.assertEqual(list(task_issues.parse_tasks(text)), ['T001', 'T002', 'T003'])
        self.assertEqual(before, w.fingerprint_files(self.root, [self.feature + '/tasks.md']))
        self.assertFalse(delegation.annotate_tasks(self.root, self.feature,
                                                    self.policy['delegation'], 'codex')['changed'])
        self.assertNotIn('"task_id": "T003"', text)

    def test_annotation_preserves_crlf_bytes(self):
        path = self.tasks()
        path.write_bytes(b'- [ ] T001 Implement parser\r\n')
        before = w.fingerprint_files(self.root, [self.feature + '/tasks.md'])
        self.enable()
        delegation.annotate_tasks(self.root, self.feature, self.policy['delegation'], 'codex')
        content = path.read_bytes()
        self.assertIn(b'parser\r\n', content)
        self.assertIn(b' -->\r\n', content)
        self.assertNotIn(b'\r\r\n', content)
        self.assertEqual(before, w.fingerprint_files(self.root, [self.feature + '/tasks.md']))

    def test_annotation_does_not_reassign_running_task(self):
        path = self.tasks()
        self.enable()
        delegation.annotate_tasks(self.root, self.feature, self.policy['delegation'], 'codex')
        original = path.read_text(encoding='utf-8').splitlines()[1]
        ledger = dispatch.load_ledger(self.root, self.feature)
        ledger['attempts'].append({'identity': self.feature + '/T001', 'status': 'running'})
        w.write(delegation.ledger_path(self.root, self.feature), ledger)
        w.write(self.root / self.feature / 'workflow/progress/state.json',
                {'tasks': [{'id': 'T002', 'status': 'running'}]})
        self.policy['delegation']['models']['codex']['standard'] = 'new-model'
        self.configure()
        delegation.annotate_tasks(self.root, self.feature, self.policy['delegation'], 'codex')
        self.assertEqual(path.read_text(encoding='utf-8').splitlines()[1], original)
        self.assertNotIn('new-model', path.read_text(encoding='utf-8'))

    def test_skill_install_uses_bundled_source_and_preserves_existing(self):
        project_skill = self.root / '.agents/skills/delegate-task'
        with patch.object(delegation, 'local_skill_paths', return_value=[project_skill]):
            result = delegation.install_skill(self.root, 'codex', 'project')
            self.assertTrue(result['installed'])
            driver = project_skill / 'delegate.mjs'
            self.assertTrue(driver.is_file())
            self.assertFalse(delegation.install_skill(self.root, 'codex', 'project')['installed'])
            driver.unlink()
            repaired = delegation.install_skill(self.root, 'codex', 'project')
            self.assertTrue(repaired['installed'])
            self.assertTrue(driver.is_file())
            self.assertTrue(Path(repaired['backup']).is_dir())

    def test_global_install_is_discoverable_without_project_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            global_root = Path(directory)
            with patch.object(delegation, 'global_root', return_value=global_root):
                installed = delegation.install_skill(self.root, 'claude', 'global')
                self.assertTrue(installed['installed'])
                self.assertTrue((global_root / '.claude/skills/delegate-task/delegate.mjs').is_file())
                self.assertEqual(delegation.inspect_skill(self.root, 'claude')['scope'], 'global')
                self.assertFalse((self.root / '.claude/skills/delegate-task').exists())

    def test_project_install_does_not_reuse_global_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            global_root = Path(directory)
            with patch.object(delegation, 'global_root', return_value=global_root):
                delegation.install_skill(self.root, 'codex', 'global')
                installed = delegation.install_skill(self.root, 'codex', 'project')
                self.assertTrue(installed['installed'])
                self.assertEqual(installed['scope'], 'project')
                self.assertTrue((self.root / '.agents/skills/delegate-task/delegate.mjs').is_file())

    def test_doctor_separates_missing_and_broken_agent_clis(self):
        output = ('harness tier version read-only resume launches as\n'
                  'codex verified - enforced verified NOT FOUND on PATH\n'
                  'claude verified BROKEN: bad shim plan verified claude.exe\n')
        responses = [subprocess.CompletedProcess([], 0, 'v20.0.0\n', ''),
                     subprocess.CompletedProcess([], 0, output, '')]
        with patch.object(delegation, 'inspect_skill', return_value={'ok': True, 'driver': 'driver.mjs'}), \
             patch.object(delegation.shutil, 'which', return_value='node'), \
             patch.object(delegation.subprocess, 'run', side_effect=responses):
            result = delegation.doctor(self.root, 'codex')
        self.assertEqual(result['cli_errors'], {'codex': 'AGENT_CLI_MISSING',
                                                 'claude': 'AGENT_CLI_BROKEN'})

    def fake_doctor(self):
        return {'ok': True, 'driver': 'delegate.mjs',
                'harnesses': {'codex': True, 'claude': True}}

    def test_dispatch_records_unverified_actual_model_and_usage(self):
        self.tasks()
        self.enable()
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', return_value={'run_id': 'codex-1', 'state': 'running'}):
            started = dispatch.start(self.root, self.feature, 'T001')
        self.assertEqual(started['route']['requested_model'], 'gpt-6-sol')
        payload = {'run_id': 'codex-1', 'status': 'successful', 'summary': 'Implemented',
                   'harness': 'codex', 'model': 'gpt-6-sol', 'model_reported': False,
                   'actual_model': None, 'model_observed': False,
                   'status_provenance': {'primary': 'harness_telemetry'},
                   'tokens': {'fidelity': 'exact', 'input_fresh': 15, 'output_total': 4},
                   'dirty_paths_changed': ['src/parser.py'],
                   'artifacts': {'dir': str(self.root / '.delegate/runs/codex-1')}}
        with patch.object(delegation, 'inspect_skill', return_value=self.fake_doctor()), \
             patch.object(dispatch.shutil, 'which', return_value='node'), \
             patch.object(dispatch.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), '')):
            result = dispatch.collect(self.root, self.feature, 'codex-1')
        self.assertIsNone(result['actual_model'])
        self.assertEqual(result['actual_model_evidence'], 'unverified')
        self.assertEqual(result['token_usage']['input_fresh'], 15)
        self.assertEqual(dispatch.load_ledger(self.root, self.feature)['attempts'][0]['status'], 'successful')

    def test_actual_model_requires_harness_observation(self):
        self.tasks()
        self.enable()
        self.policy['delegation']['overrides'][self.feature + '/T001'] = {
            'preferred': {'harness': 'claude', 'model': 'requested-alias'}, 'fallbacks': []}
        self.configure()
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', return_value={'run_id': 'claude-1', 'state': 'running'}):
            dispatch.start(self.root, self.feature, 'T001')
        payload = {'run_id': 'claude-1', 'status': 'successful', 'summary': 'Done',
                   'harness': 'claude', 'model': 'requested-alias', 'model_reported': True,
                   'actual_model': 'claude-sonnet-5', 'model_observed': True,
                   'status_provenance': {'primary': 'harness_telemetry'},
                   'dirty_paths_changed': [], 'artifacts': {'dir': str(self.root / '.delegate/runs/claude-1')}}
        with patch.object(delegation, 'inspect_skill', return_value=self.fake_doctor()), \
             patch.object(dispatch.shutil, 'which', return_value='node'), \
             patch.object(dispatch.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), '')):
            result = dispatch.collect(self.root, self.feature, 'claude-1')
        self.assertEqual(result['actual_model'], 'claude-sonnet-5')
        self.assertEqual(result['actual_model_evidence'], 'harness-reported')

    def test_stage_delegate_keeps_dispatcher_claim(self):
        self.enable()
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(w, 'doctor', return_value={'ok': True, 'errors': []}):
            claim = run.claim({'session_id': 'test-session'})
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', return_value={'run_id': 'codex-scope', 'state': 'running'}):
            result = dispatch.start(self.root, self.feature, 'stage:scope', token=claim['token'])
        self.assertEqual(result['route']['requested_model'], 'gpt-6-astra')
        checkpoint = w.read(self.root / self.feature / 'workflow/checkpoint.json')
        self.assertEqual(checkpoint['active']['token'], claim['token'])
        self.assertEqual(checkpoint['receipts'], {})
        with self.assertRaisesRegex(delegation.DelegationError, 'CLAIM_MISMATCH'):
            dispatch.start(self.root, self.feature, 'stage:scope', token='wrong')

    def test_dispatch_permissions_are_explicit(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, '{"run_id":"codex-1","state":"running"}', '')
        with patch.object(dispatch.shutil, 'which', return_value='node'), \
             patch.object(dispatch.subprocess, 'run', side_effect=run):
            dispatch.launch(self.root, 'delegate.mjs',
                            {'harness': 'codex', 'requested_model': 'gpt-6-sol',
                             'read_only': True, 'allow_commit': False}, self.root, 'Review', 1800)
            dispatch.launch(self.root, 'delegate.mjs',
                            {'harness': 'codex', 'requested_model': 'gpt-6-sol',
                             'read_only': False, 'allow_commit': True}, self.root, 'Execute', 7200)
        self.assertIn('--sandbox', calls[0])
        self.assertNotIn('--allow-commit', calls[0])
        self.assertIn('--allow-commit', calls[1])
        self.assertNotIn('--sandbox', calls[1])

    def test_unavailable_model_falls_back_and_records_decision(self):
        self.tasks()
        self.enable()
        ids = iter(('codex-1', 'codex-2'))
        def launch(*args):
            return {'run_id': next(ids), 'state': 'running'}
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', side_effect=launch):
            dispatch.start(self.root, self.feature, 'T001')
        stderr = self.root / 'model-error.txt'
        stderr.write_text('Unknown model gpt-6-sol', encoding='utf-8')
        payload = {'run_id': 'codex-1', 'status': 'failed', 'status_reason': '',
                   'status_provenance': {'primary': 'harness_telemetry'},
                   'harness': 'codex', 'model_reported': False, 'dirty_paths_changed': [],
                   'head_changed': False, 'index_changed': False,
                   'artifacts': {'stderr': str(stderr), 'dir': str(self.root / '.delegate/runs/codex-1')}}
        with patch.object(delegation, 'inspect_skill', return_value=self.fake_doctor()), \
             patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch.shutil, 'which', return_value='node'), \
             patch.object(dispatch.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), '')), \
             patch.object(dispatch, 'launch', side_effect=launch):
            result = dispatch.collect(self.root, self.feature, 'codex-1')
        self.assertEqual(result['replacement']['run_id'], 'codex-2')
        self.assertIsNone(result['replacement']['route']['requested_model'])
        ledger = dispatch.load_ledger(self.root, self.feature)
        self.assertEqual(ledger['attempts'][0]['replacement_run_id'], 'codex-2')
        self.assertTrue(any(d['reason'] == 'requested model rejected by CLI'
                            for d in ledger['route_decisions']))

    def test_failed_work_with_no_edits_gets_one_stronger_attempt(self):
        self.tasks()
        self.enable()
        ids = iter(('codex-1', 'codex-2'))
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', side_effect=lambda *args: {'run_id': next(ids), 'state': 'running'}):
            dispatch.start(self.root, self.feature, 'T001')
        payload = {'run_id': 'codex-1', 'status': 'failed', 'status_reason': 'task failed',
                   'status_provenance': {'primary': 'harness_telemetry'},
                   'harness': 'codex', 'model_reported': False, 'dirty_paths_changed': [],
                   'head_changed': False, 'index_changed': False,
                   'artifacts': {'dir': str(self.root / '.delegate/runs/codex-1')}}
        with patch.object(delegation, 'inspect_skill', return_value=self.fake_doctor()), \
             patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch.shutil, 'which', return_value='node'), \
             patch.object(dispatch.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), '')), \
             patch.object(dispatch, 'launch', side_effect=lambda *args: {'run_id': next(ids), 'state': 'running'}):
            result = dispatch.collect(self.root, self.feature, 'codex-1')
        self.assertEqual(result['replacement']['route']['requested_model'], 'gpt-6-astra')
        self.assertEqual(dispatch.load_ledger(self.root, self.feature)['attempts'][1]['retry_count'], 1)

    def test_start_intent_recovers_driver_run_after_lost_ack(self):
        self.tasks()
        self.enable()
        candidate = delegation.selected_route(self.policy['delegation'], 'implementation',
                                              'codex', self.feature + '/T001')[0]
        ledger = dispatch.load_ledger(self.root, self.feature)
        ledger['attempts'].append({'intent_id': 'intent-1', 'identity': self.feature + '/T001',
                                   'task_type': 'implementation', 'status': 'starting',
                                   'route_candidates': [candidate]})
        w.write(delegation.ledger_path(self.root, self.feature), ledger)
        w.write(self.root / '.delegate/runs/codex-1/meta.json',
                {'run_id': 'codex-1', 'constraint': ['Sanduq delegation intent: intent-1'],
                 'harness': 'codex', 'model': 'gpt-6-sol', 'permission': 'bypass'})
        recovered = dispatch.recover_intent(self.root, self.feature, 'intent-1')
        self.assertEqual(recovered['run_id'], 'codex-1')
        self.assertEqual(dispatch.load_ledger(self.root, self.feature)['attempts'][0]['status'],
                         'running')

    def test_uncertain_start_keeps_intent_instead_of_launching_fallback(self):
        self.tasks()
        self.enable()
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', side_effect=delegation.DelegationError('response lost')) as launch:
            with self.assertRaisesRegex(delegation.DelegationError, 'START_UNCERTAIN'):
                dispatch.start(self.root, self.feature, 'T001')
        self.assertEqual(launch.call_count, 1)
        ledger = dispatch.load_ledger(self.root, self.feature)
        self.assertEqual(ledger['attempts'][0]['status'], 'starting')
        self.assertEqual(ledger['route_decisions'][0]['decision'], 'start-uncertain')

    def test_orchestrator_can_reassign_complex_terminal_work(self):
        self.tasks()
        self.enable()
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', return_value={'run_id': 'codex-1', 'state': 'running'}):
            dispatch.start(self.root, self.feature, 'T001')
        ledger = dispatch.load_ledger(self.root, self.feature)
        ledger['attempts'][0]['status'] = 'successful'
        w.write(delegation.ledger_path(self.root, self.feature), ledger)
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', return_value={'run_id': 'codex-2', 'state': 'running'}):
            result = dispatch.reassign(self.root, self.feature, 'codex-1',
                                       'The first result omitted migration safety')
        self.assertEqual(result['route']['requested_model'], 'gpt-6-astra')
        ledger = dispatch.load_ledger(self.root, self.feature)
        self.assertEqual(ledger['attempts'][1]['parent_run_id'], 'codex-1')
        self.assertEqual(ledger['attempts'][1]['retry_count'], 1)
        self.assertTrue(any('migration safety' in item['reason']
                            for item in ledger['route_decisions']))

    def test_collect_recovers_unlinked_replacement_without_duplicate_launch(self):
        self.tasks()
        self.enable()
        ledger = dispatch.load_ledger(self.root, self.feature)
        ledger['attempts'] = [
            {'identity': self.feature + '/T001', 'run_id': 'codex-1', 'status': 'failed',
             'retry_count': 0},
            {'identity': self.feature + '/T001', 'run_id': 'codex-2', 'status': 'running',
             'parent_run_id': 'codex-1', 'intent_id': 'intent-2'},
        ]
        w.write(delegation.ledger_path(self.root, self.feature), ledger)
        result = dispatch.collect(self.root, self.feature, 'codex-1')
        self.assertEqual(result['replacement_run_id'], 'codex-2')
        self.assertEqual(dispatch.load_ledger(self.root, self.feature)['attempts'][0]
                         ['replacement_run_id'], 'codex-2')
        with self.assertRaisesRegex(delegation.DelegationError, 'ALREADY_REASSIGNED'):
            dispatch.reassign(self.root, self.feature, 'codex-1', 'Retry again')


if __name__ == '__main__':
    unittest.main()
