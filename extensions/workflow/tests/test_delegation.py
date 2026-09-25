"""Opt-in routing, task compatibility and measured delegation history."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
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

    def rejected_claim_leaves_no_trace(self, run, expected, **patches):
        path = self.tasks()
        before = path.read_bytes()
        with patch.object(delegation, 'doctor') as delegation_doctor, \
             patch.object(delegation, 'install_skill') as install, \
             patch.object(delegation, 'annotate_tasks') as annotate, \
             patch.object(w, 'doctor', return_value=patches.get('health', {'ok': True, 'errors': []})), \
             patch.object(w.Run, 'next', side_effect=patches.get('next', w.Run.next), autospec=True):
            if expected:
                with self.assertRaisesRegex(w.WorkflowError, expected):
                    run.claim({'session_id': 'test-session'})
                result = None
            else:
                result = run.claim({'session_id': 'test-session'})
        delegation_doctor.assert_not_called()
        install.assert_not_called()
        annotate.assert_not_called()
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.root / '.agents/skills/delegate-task').exists())
        self.assertFalse((self.root / '.claude/skills/delegate-task').exists())
        self.assertIsNone(w.read(run.path)['active'])
        return result

    def test_rejected_claim_does_not_install_skill_or_annotate_tasks(self):
        self.enable()
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        other = self.root / 'specs/002-other/workflow/checkpoint.json'
        w.write(other, {'active': {'stage': 'plan', 'token': 'other'}})
        self.rejected_claim_leaves_no_trace(run, 'OTHER_FEATURE_STAGE_ACTIVE')
        other.unlink()
        self.rejected_claim_leaves_no_trace(
            run, 'COMMAND_UNAVAILABLE', health={'ok': False, 'errors': ['COMMAND_UNAVAILABLE: x']})

    def test_claim_without_next_stage_does_not_install_skill_or_annotate_tasks(self):
        self.enable()
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        for status in ('ready_to_finalize', 'pr_open'):
            with self.subTest(status=status):
                result = self.rejected_claim_leaves_no_trace(
                    run, None, next=lambda self_, state, finalize=False, s=status: {'stage': None, 'status': s})
                self.assertEqual(result['status'], status)

    def test_claim_checks_skill_health_after_rejections_but_before_dispatch(self):
        path = self.tasks()
        self.enable()
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        with patch.object(delegation, 'doctor',
                          return_value={'ok': False, 'error': 'DELEGATE_SKILL_INSTALL_FAILED'}), \
             patch.object(w, 'doctor', return_value={'ok': True, 'errors': []}):
            with self.assertRaisesRegex(w.WorkflowError, 'DELEGATE_SKILL_INSTALL_FAILED'):
                run.claim({'session_id': 'test-session'})
        self.assertIsNone(w.read(run.path)['active'])
        self.assertNotIn('sanduq-delegation', path.read_text(encoding='utf-8'))
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()) as delegation_doctor, \
             patch.object(w, 'doctor', return_value={'ok': True, 'errors': []}) as health:
            claim = run.claim({'session_id': 'test-session'})
        self.assertEqual(delegation_doctor.call_args.kwargs['install'], True)
        self.assertIs(health.call_args.kwargs['check_delegation'], False)
        self.assertIn('sanduq-delegation', path.read_text(encoding='utf-8'))
        self.assertEqual(w.read(run.path)['active']['delegation']['candidates'],
                         claim['delegation']['candidates'])

    def test_doctor_names_install_command_for_missing_skill_without_installing(self):
        self.enable()
        self.policy['delegation']['install_scope'] = 'global'
        policy = w.validate_policy(self.policy)
        for error in ('DELEGATE_SKILL_MISSING', 'DELEGATE_SKILL_BROKEN'):
            with self.subTest(error=error), \
                 patch.object(delegation, 'doctor', return_value={'ok': False, 'error': error}) as probe, \
                 patch.object(delegation, 'install_skill') as install:
                errors = w.doctor(self.root, policy, project=True)['errors']
                message = next(e for e in errors if e.startswith(error))
                self.assertIn('delegation.py install', message)
                self.assertIn('global scope', message)
                self.assertNotIn('install', probe.call_args.kwargs)
                install.assert_not_called()
        stale = {'ok': False, 'error': 'DELEGATE_SKILL_INCOMPATIBLE', 'broken': [],
                 'incompatible': [{'path': '/home/u/.claude/skills/delegate-task',
                                   'reason': 'driver predates the contract command (exit 2)'}]}
        with patch.object(delegation, 'doctor', return_value=stale):
            message = next(e for e in w.doctor(self.root, policy)['errors']
                           if e.startswith('DELEGATE_SKILL_INCOMPATIBLE'))
        self.assertIn('/home/u/.claude/skills/delegate-task (driver predates the contract command', message)
        self.assertIn('delegation.py install', message)
        with patch.object(delegation, 'doctor', return_value={'ok': False, 'error': 'NODE_18_REQUIRED'}):
            self.assertIn('NODE_18_REQUIRED', w.doctor(self.root, policy)['errors'])
        with patch.object(delegation, 'doctor', return_value={
                'ok': True, 'harnesses': {'codex': False, 'claude': False},
                'cli_errors': {'codex': 'AGENT_CLI_MISSING', 'claude': 'AGENT_CLI_BROKEN'}}):
            errors = w.doctor(self.root, policy)['errors']
        self.assertIn('DELEGATE_AGENT_CLI_UNAVAILABLE: no supported Codex or Claude CLI', errors)
        self.assertFalse(any('delegation.py install' in e for e in errors))

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

    def isolated_skills(self):
        """A private global root and no driver overrides, whatever this machine has installed."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        global_root = Path(directory.name).resolve()
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(delegation, 'global_root', return_value=global_root))
        environ = {k: v for k, v in os.environ.items()
                   if k not in ('SANDUQ_DELEGATE_DRIVER', 'CLAUDE_PLUGIN_ROOT')}
        stack.enter_context(patch.dict(os.environ, environ, clear=True))
        return global_root

    def copy_bundle(self, target, driver_edit=None):
        shutil.copytree(delegation.bundled_skill(), target,
                        ignore=shutil.ignore_patterns('test', 'runs', 'node_modules'))
        if driver_edit:
            driver = target / 'delegate.mjs'
            driver.write_bytes(driver_edit(driver.read_bytes()))
        return target

    def assert_outside_skill_roots(self, path, *bases):
        path = Path(path).resolve()
        for base in bases:
            for skills in delegation.SKILL_ROOTS:
                self.assertFalse(path.is_relative_to((base / skills).resolve()), str(path))

    @staticmethod
    def without_contract_command(content):
        line = b"  else if (cmd === 'contract') cmdContract();"
        assert line in content
        return content.replace(line, b'')

    def test_skill_install_uses_bundled_source_and_preserves_existing(self):
        global_root = self.isolated_skills()
        project_skill = self.root / '.agents/skills/delegate-task'
        result = delegation.install_skill(self.root, 'codex', 'project')
        self.assertTrue(result['installed'])
        driver = project_skill / 'delegate.mjs'
        self.assertTrue(driver.is_file())
        self.assertFalse(delegation.install_skill(self.root, 'codex', 'project')['installed'])
        driver.unlink()
        self.assertEqual(delegation.inspect_skill(self.root, 'codex')['error'], 'DELEGATE_SKILL_BROKEN')
        repaired = delegation.install_skill(self.root, 'codex', 'project')
        self.assertTrue(repaired['installed'])
        self.assertTrue(driver.is_file())
        backup = Path(repaired['backup'])
        self.assertTrue((backup / 'SKILL.md').is_file())
        self.assertFalse((backup / 'delegate.mjs').exists())
        self.assertTrue(backup.resolve().is_relative_to(
            (self.root / '.specify/workflow/backups/delegate-task').resolve()))
        self.assert_outside_skill_roots(backup, self.root, global_root)
        self.assertEqual([p.name for p in (self.root / '.agents/skills').iterdir()
                          if p.name.startswith('delegate-task')], ['delegate-task'])
        self.assertIn('/.specify/workflow/backups/',
                      (self.root / '.git/info/exclude').read_text(encoding='utf-8'))

    def test_global_install_is_discoverable_without_project_copy(self):
        global_root = self.isolated_skills()
        installed = delegation.install_skill(self.root, 'claude', 'global')
        self.assertTrue(installed['installed'])
        self.assertTrue((global_root / '.claude/skills/delegate-task/delegate.mjs').is_file())
        self.assertEqual(delegation.inspect_skill(self.root, 'claude')['scope'], 'global')
        self.assertFalse((self.root / '.claude/skills/delegate-task').exists())

    def test_usable_global_or_project_copy_is_reused_at_any_configured_scope(self):
        global_root = self.isolated_skills()
        delegation.install_skill(self.root, 'codex', 'global')
        reused = delegation.install_skill(self.root, 'codex', 'project')
        self.assertFalse(reused['installed'])
        self.assertEqual(reused['scope'], 'global')
        self.assertFalse((self.root / '.agents/skills/delegate-task').exists())
        shutil.rmtree(global_root / '.agents')
        delegation.install_skill(self.root, 'codex', 'project')
        reused = delegation.install_skill(self.root, 'codex', 'global')
        self.assertFalse(reused['installed'])
        self.assertEqual(reused['scope'], 'project')
        self.assertFalse((global_root / '.agents/skills/delegate-task').exists())

    def test_driver_compatibility_requires_the_reported_contract(self):
        node = shutil.which('node')
        bundled = delegation.bundled_skill() / 'delegate.mjs'
        self.assertIsNone(delegation.driver_compatibility(node, bundled))
        contract = json.loads(subprocess.run([node, str(bundled), 'contract'], capture_output=True,
                                             text=True, encoding='utf-8').stdout)
        def fake(name, value):
            path = self.root / (name.replace(' ', '-') + '.mjs')
            path.write_text('console.log(' + json.dumps(json.dumps(value)) + ');\n', encoding='utf-8')
            return path
        def dropped(key, item):
            return {**contract, key: [x for x in contract[key] if x != item]}
        cases = {
            'requested_model': dropped('result_fields', 'requested_model'),
            'model_observed': dropped('result_fields', 'model_observed'),
            'actual_model': dropped('result_fields', 'actual_model'),
            '--constraint': dropped('start_flags', '--constraint'),
            'DELEGATE_RUNS_DIR': dropped('env', 'DELEGATE_RUNS_DIR'),
            'result schema': {**contract, 'result_schema': 'delegate-task.result.v1'},
            'is not delegate-task.driver.v1': {**contract, 'contract': 'delegate-task.driver.v0'},
            'exit code 3': {**contract, 'exit_codes': {}},
        }
        for expected, value in cases.items():
            with self.subTest(expected=expected):
                reason = delegation.driver_compatibility(node, fake(expected.strip('-'), value))
                self.assertIn(expected, reason)
        legacy = self.copy_bundle(self.root / 'legacy', self.without_contract_command)
        self.assertIn('predates the contract command',
                      delegation.driver_compatibility(node, legacy / 'delegate.mjs'))

    def test_incompatible_copy_is_backed_up_and_refreshed_at_configured_scope(self):
        global_root = self.isolated_skills()
        for scope, base in (('project', self.root), ('global', global_root)):
            with self.subTest(scope=scope):
                target = base / '.agents/skills/delegate-task'
                self.copy_bundle(target, self.without_contract_command)
                (target / 'team-notes.md').write_text('local customisation\n', encoding='utf-8')
                found = delegation.inspect_skill(self.root, 'codex')
                self.assertEqual(found['error'], 'DELEGATE_SKILL_INCOMPATIBLE')
                self.assertIn('predates the contract command', found['incompatible'][0]['reason'])
                installed = delegation.install_skill(self.root, 'codex', scope)
                self.assertTrue(installed['installed'])
                self.assertEqual(installed['scope'], scope)
                self.assertEqual(installed['replaced'][0]['path'], str(target))
                backup = Path(installed['backup'])
                self.assertEqual((backup / 'team-notes.md').read_text(encoding='utf-8'),
                                 'local customisation\n')
                self.assertNotIn(b"cmd === 'contract'", (backup / 'delegate.mjs').read_bytes())
                self.assert_outside_skill_roots(backup, self.root, global_root)
                self.assertTrue(backup.resolve().is_relative_to(base.resolve()))
                self.assertFalse((target / 'team-notes.md').exists())
                self.assertTrue(delegation.inspect_skill(self.root, 'codex')['ok'])
                shutil.rmtree(target)

    def test_incompatible_global_copy_does_not_block_project_install(self):
        global_root = self.isolated_skills()
        stale = self.copy_bundle(global_root / '.agents/skills/delegate-task',
                                 self.without_contract_command)
        installed = delegation.install_skill(self.root, 'codex', 'project')
        self.assertTrue(installed['installed'])
        self.assertIsNone(installed['backup'])
        self.assertNotIn(b"cmd === 'contract'", (stale / 'delegate.mjs').read_bytes())
        self.assertEqual(delegation.inspect_skill(self.root, 'codex')['scope'], 'project')

    def test_upgrade_keeps_a_compatible_customised_copy_and_moves_legacy_backups(self):
        global_root = self.isolated_skills()
        skills = self.root / '.agents/skills'
        target = self.copy_bundle(skills / 'delegate-task',
                                  lambda content: content + b'// team patch\n')
        (target / 'team-notes.md').write_text('keep me\n', encoding='utf-8')
        reused = delegation.install_skill(self.root, 'codex', 'project')
        self.assertFalse(reused['installed'])
        self.assertTrue((target / 'delegate.mjs').read_bytes().endswith(b'// team patch\n'))
        self.assertTrue((target / 'team-notes.md').is_file())
        # A broken copy is refreshed; a sibling backup an earlier build left in
        # the discovery root moves out with it.
        legacy = self.copy_bundle(skills / 'delegate-task.sanduq-backup-0123')
        (target / 'SKILL.md').unlink()
        repaired = delegation.install_skill(self.root, 'codex', 'project')
        self.assertTrue(repaired['installed'])
        self.assertEqual([p.name for p in skills.iterdir() if p.name.startswith('delegate-task')],
                         ['delegate-task'])
        self.assertFalse(legacy.exists())
        backups = self.root / '.specify/workflow/backups/delegate-task'
        moved = list(backups.glob('delegate-task.sanduq-backup-0123.*'))
        self.assertEqual(len(moved), 1)
        self.assertTrue((moved[0] / 'SKILL.md').is_file())
        self.assertEqual((Path(repaired['backup']) / 'team-notes.md').read_text(encoding='utf-8'),
                         'keep me\n')
        self.assert_outside_skill_roots(repaired['backup'], self.root, global_root)

    def test_failed_refresh_restores_the_previous_copy(self):
        self.isolated_skills()
        target = self.copy_bundle(self.root / '.agents/skills/delegate-task',
                                  self.without_contract_command)
        (target / 'team-notes.md').write_text('keep me\n', encoding='utf-8')
        with patch.object(delegation, 'driver_compatibility', return_value='still incompatible'):
            with self.assertRaisesRegex(delegation.DelegationError, 'DELEGATE_SKILL_INSTALL_FAILED'):
                delegation.install_skill(self.root, 'codex', 'project')
        self.assertEqual((target / 'team-notes.md').read_text(encoding='utf-8'), 'keep me\n')
        self.assertEqual(list((self.root / '.specify/workflow/backups/delegate-task').iterdir()), [])

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

    def skill_copy(self, base):
        folder = base / '.agents/skills/delegate-task'
        (folder / 'contracts').mkdir(parents=True, exist_ok=True)
        for name in ('delegate.mjs', 'SKILL.md', 'contracts/result-schema-v2.md'):
            (folder / name).write_text('// fixture\n', encoding='utf-8')
        return folder / 'delegate.mjs'

    def fake_doctor(self):
        return {'ok': True, 'driver': str(self.skill_copy(self.root)),
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
                   'head_changed': False, 'index_changed': False, 'coverage_complete': True,
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

    def failed_payload(self, run_id='codex-1', **fields):
        payload = {'run_id': run_id, 'status': 'failed', 'status_reason': 'task failed',
                   'status_provenance': {'primary': 'harness_telemetry'},
                   'harness': 'codex', 'model_reported': False, 'dirty_paths_changed': [],
                   'head_changed': False, 'index_changed': False, 'coverage_complete': True,
                   'artifacts': {'dir': str(self.root / '.delegate/runs' / run_id)}}
        payload.update(fields)
        return {key: value for key, value in payload.items() if value is not ...}

    def start_one(self, identity='T001', run_id='codex-1'):
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', return_value={'run_id': run_id, 'state': 'running'}):
            return dispatch.start(self.root, self.feature, identity)

    def collect_with(self, payload, launch, run_id='codex-1'):
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch.shutil, 'which', return_value='node'), \
             patch.object(dispatch.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), '')), \
             patch.object(dispatch, 'launch', side_effect=launch):
            return dispatch.collect(self.root, self.feature, run_id)

    def test_concurrent_starts_of_different_tasks_both_persist(self):
        self.tasks()
        self.enable()
        ids = iter(('codex-1', 'codex-2'))
        lock = threading.Lock()
        def launch(*args):
            time.sleep(0.3)
            with lock:
                return {'run_id': next(ids), 'state': 'running'}
        errors = []
        def run(identity):
            try:
                dispatch.start(self.root, self.feature, identity)
            except Exception as error:  # surfaced below
                errors.append(error)
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', side_effect=launch):
            threads = [threading.Thread(target=run, args=(identity,)) for identity in ('T001', 'T002')]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
        self.assertEqual(errors, [])
        attempts = dispatch.load_ledger(self.root, self.feature)['attempts']
        self.assertEqual(sorted(a['identity'].rsplit('/', 1)[1] for a in attempts), ['T001', 'T002'])
        self.assertEqual({a['status'] for a in attempts}, {'running'})
        self.assertEqual(sorted(a['run_id'] for a in attempts), ['codex-1', 'codex-2'])

    def test_concurrent_duplicate_start_launches_once(self):
        self.tasks()
        self.enable()
        errors = []
        def run():
            try:
                dispatch.start(self.root, self.feature, 'T001')
            except delegation.DelegationError as error:
                errors.append(str(error))
        def launch(*args):
            time.sleep(0.3)
            return {'run_id': 'codex-1', 'state': 'running'}
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', side_effect=launch) as launched:
            threads = [threading.Thread(target=run) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
        self.assertEqual(launched.call_count, 1)
        self.assertEqual(len(errors), 1)
        self.assertIn('DELEGATION_ALREADY_RUNNING', errors[0])
        self.assertEqual(len(dispatch.load_ledger(self.root, self.feature)['attempts']), 1)

    def test_busy_ledger_lock_is_bounded_and_retryable(self):
        self.tasks()
        self.enable()
        lock = (self.root / '.specify/workflow/runtime' /
                ('delegation-' + w.digest(self.feature) + '.lock'))
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text('{}', encoding='utf-8')
        with patch.object(dispatch, 'LOCK_TIMEOUT', 0.2), \
             patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch') as launched:
            with self.assertRaisesRegex(delegation.DelegationError, 'DELEGATION_LEDGER_BUSY: retry'):
                dispatch.start(self.root, self.feature, 'T001')
        launched.assert_not_called()
        self.assertTrue(lock.exists())
        self.assertFalse(delegation.ledger_path(self.root, self.feature).exists())

    def test_concurrent_collects_launch_one_replacement(self):
        self.tasks()
        self.enable()
        self.start_one()
        def launch(*args):
            time.sleep(0.3)
            return {'run_id': 'codex-2', 'state': 'running'}
        results, errors = [], []
        def run():
            try:
                results.append(dispatch.collect(self.root, self.feature, 'codex-1'))
            except Exception as error:  # surfaced below
                errors.append(error)
        payload = self.failed_payload()
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch.shutil, 'which', return_value='node'), \
             patch.object(dispatch.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), '')), \
             patch.object(dispatch, 'launch', side_effect=launch) as launched:
            threads = [threading.Thread(target=run) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(launched.call_count, 1)
        ledger = dispatch.load_ledger(self.root, self.feature)
        self.assertEqual([a['run_id'] for a in ledger['attempts']], ['codex-1', 'codex-2'])
        self.assertEqual(sum(d['decision'] == 'reassignment' for d in ledger['route_decisions']), 1)

    def test_model_rejection_wording_fixtures(self):
        rejected = (
            'Unknown model gpt-6-sol',
            'The model `gpt-6-sol` does not exist or you do not have access to it.',
            "The 'gpt-6-sol' model is not supported when using Codex with a ChatGPT account.",
            '{"error":{"code":"model_not_found","message":"The requested model was not found"}}',
            'API Error: 404 {"type":"error","error":{"type":"not_found_error","message":"model: claude-x"}}',
            "There's an issue with the selected model (claude-x). It may not exist or you may not have access to it.",
            'Error: model claude-x is not available for this account',
            'invalid model: gpt-7',
        )
        for text in rejected:
            with self.subTest(text=text):
                self.assertTrue(dispatch.model_rejected({'status_reason': text}))
        for text in ('task failed: 3 tests red', 'model saved; build failed', '',
                     'File not found: src/parser.py'):
            with self.subTest(text=text):
                self.assertFalse(dispatch.model_rejected({'status_reason': text}))

    def test_model_rejection_keeps_configured_fallback_over_stronger_retry(self):
        self.tasks()
        self.enable()
        self.start_one()
        stderr = self.root / 'model-error.txt'
        stderr.write_text('{"error":{"code":"model_not_found"}}', encoding='utf-8')
        payload = self.failed_payload(status_reason='',
                                      artifacts={'stderr': str(stderr),
                                                 'dir': str(self.root / '.delegate/runs/codex-1')})
        result = self.collect_with(payload, lambda *args: {'run_id': 'codex-2', 'state': 'running'})
        self.assertIsNone(result['replacement']['route']['requested_model'])
        ledger = dispatch.load_ledger(self.root, self.feature)
        self.assertEqual(ledger['attempts'][1]['retry_count'], 0)
        self.assertEqual(ledger['attempts'][1]['route_candidates'][0]['choice'], 'fallback:1')
        # The fallback is also rejected: nothing remains, and no stronger model replaces it.
        payload = self.failed_payload('codex-2', status_reason='model does not exist')
        with patch.object(dispatch, 'launch') as launched:
            result = self.collect_with(payload, launched, run_id='codex-2')
        launched.assert_not_called()
        self.assertNotIn('replacement', result)

    def test_stronger_retry_requires_complete_measured_no_edits(self):
        unknown = ({'dirty_paths_changed': None}, {'dirty_paths_changed': ...},
                   {'head_changed': None}, {'head_changed': ...}, {'index_changed': None},
                   {'index_changed': ...}, {'coverage_complete': False},
                   {'coverage_complete': None}, {'coverage_complete': ...},
                   {'dirty_paths_changed': ['src/parser.py']}, {'head_changed': True})
        self.tasks()
        self.enable()
        # One fixture serves every case: each failed run is terminal, so the
        # next case can start the same task again under a fresh run ID.
        for number, fields in enumerate(unknown, 1):
            run_id = 'codex-' + str(number)
            with self.subTest(fields=fields):
                self.start_one(run_id=run_id)
                with patch.object(dispatch, 'launch') as launched:
                    result = self.collect_with(self.failed_payload(run_id, **fields), launched,
                                               run_id=run_id)
                launched.assert_not_called()
                self.assertNotIn('replacement', result)
                self.assertEqual(result['status'], 'failed')
        attempts = dispatch.load_ledger(self.root, self.feature)['attempts']
        self.assertEqual([a['run_id'] for a in attempts],
                         ['codex-' + str(n) for n in range(1, len(unknown) + 1)])
        self.assertFalse(any(a.get('replacement_run_id') or a.get('parent_run_id') for a in attempts))
        self.assertTrue(dispatch.measured_no_edits(self.failed_payload()))
        # Coverage is part of the measurement: absent or not exactly true means unknown.
        self.assertFalse(dispatch.measured_no_edits(self.failed_payload(coverage_complete=...)))
        self.assertFalse(dispatch.measured_no_edits(self.failed_payload(coverage_complete='true')))

    def test_feature_spellings_share_one_ledger_and_override(self):
        self.tasks()
        self.enable()
        name = self.feature.split('/')[1]
        for spelling in ('specs/' + name, 'specs\\' + name, 'specs/' + name + '/',
                         'specs\\' + name + '\\', './specs/' + name, 'specs//' + name,
                         str(self.root / 'specs' / name)):
            with self.subTest(spelling=spelling):
                self.assertEqual(dispatch.feature_identity(self.root, spelling), self.feature)
        for spelling in ('specs', 'specs/..', '../specs/' + name, 'specs/../' + name,
                         'specs/' + name + '/..', 'specs/a/b', '/etc/specs/' + name,
                         'C:/specs/' + name, 'other/' + name, ''):
            with self.subTest(spelling=spelling):
                with self.assertRaisesRegex(delegation.DelegationError, 'DELEGATION_FEATURE_INVALID'):
                    dispatch.feature_identity(self.root, spelling)
        self.policy['delegation']['overrides'][self.feature + '/T001'] = {
            'preferred': {'harness': 'claude', 'model': 'custom-reviewer'}, 'fallbacks': []}
        self.configure()
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', return_value={'run_id': 'claude-1', 'state': 'running'}):
            started = dispatch.start(self.root, 'specs\\' + name + '\\', 'T001')
            self.assertEqual(started['route']['requested_model'], 'custom-reviewer')
            with self.assertRaisesRegex(delegation.DelegationError, 'ALREADY_RUNNING'):
                dispatch.start(self.root, 'specs/' + name + '/', 'T001')
        ledger = dispatch.load_ledger(self.root, self.feature)
        self.assertEqual(ledger['feature'], self.feature)
        self.assertEqual(ledger['attempts'][0]['identity'], self.feature + '/T001')
        ledger['feature'] = 'specs\\' + name + '\\'
        w.write(delegation.ledger_path(self.root, self.feature), ledger)
        self.assertEqual(len(dispatch.load_ledger(self.root, self.feature)['attempts']), 1)
        ledger['feature'] = 'specs/other'
        w.write(delegation.ledger_path(self.root, self.feature), ledger)
        with self.assertRaisesRegex(delegation.DelegationError, 'LEDGER_INVALID'):
            dispatch.load_ledger(self.root, self.feature)

    def test_launch_reports_spawn_oserror_as_confirmed_start_failure(self):
        with patch.object(dispatch.shutil, 'which', return_value='node'), \
             patch.object(dispatch.subprocess, 'run', side_effect=OSError('exec format error')):
            with self.assertRaises(dispatch.StartFailed):
                dispatch.launch(self.root, 'delegate.mjs', {'harness': 'codex', 'requested_model': None},
                                self.root, 'Task', 1800)
        with patch.object(dispatch.shutil, 'which', return_value='node'), \
             patch.object(dispatch.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 2, '', 'delegate: bad cwd')):
            with self.assertRaisesRegex(dispatch.StartFailed, 'bad cwd'):
                dispatch.launch(self.root, 'delegate.mjs', {'harness': 'codex', 'requested_model': None},
                                self.root, 'Task', 1800)

    def test_confirmed_start_failure_moves_to_fallback_then_blocks(self):
        self.tasks()
        self.enable()
        outcomes = iter((dispatch.StartFailed('DELEGATE_START_FAILED: codex not found'),
                         {'run_id': 'codex-1', 'state': 'running'}))
        def launch(*args):
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', side_effect=launch) as launched:
            started = dispatch.start(self.root, self.feature, 'T001')
        self.assertEqual(launched.call_count, 2)
        self.assertEqual(started['route']['choice'], 'fallback:1')
        ledger = dispatch.load_ledger(self.root, self.feature)
        self.assertEqual(ledger['attempts'][0]['status'], 'running')
        self.assertEqual(len(ledger['attempts'][0]['start_failures']), 1)
        self.assertEqual(ledger['route_decisions'][0]['decision'], 'start-failed')
        # Every candidate fails before a run exists: the intent is closed, not left starting.
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', side_effect=dispatch.StartFailed('DELEGATE_START_FAILED: x')):
            with self.assertRaisesRegex(delegation.DelegationError, 'ROUTES_UNAVAILABLE'):
                dispatch.start(self.root, self.feature, 'T002')
        ledger = dispatch.load_ledger(self.root, self.feature)
        self.assertEqual(ledger['attempts'][1]['status'], 'blocked')
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', return_value={'run_id': 'codex-2', 'state': 'running'}):
            self.assertEqual(dispatch.start(self.root, self.feature, 'T002')['run_id'], 'codex-2')

    def test_failed_start_with_driver_meta_stays_recoverable(self):
        self.tasks()
        self.enable()
        def launch(root, driver, candidate, cwd, task, timeout, intent_id):
            w.write(self.root / '.delegate/runs/codex-1/meta.json',
                    {'run_id': 'codex-1', 'constraint': ['Sanduq delegation intent: ' + intent_id],
                     'harness': 'codex', 'model': candidate['requested_model'], 'permission': 'bypass'})
            raise dispatch.StartFailed('DELEGATE_START_FAILED: supervisor failed to start')
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', side_effect=launch) as launched:
            with self.assertRaisesRegex(delegation.DelegationError, 'START_UNCERTAIN'):
                dispatch.start(self.root, self.feature, 'T001')
        self.assertEqual(launched.call_count, 1)
        intent = dispatch.load_ledger(self.root, self.feature)['attempts'][0]
        with self.assertRaisesRegex(delegation.DelegationError, 'INTENT_HAS_RUN'):
            dispatch.abandon_intent(self.root, self.feature, intent['intent_id'], 'looks stuck')
        self.assertEqual(dispatch.recover_intent(self.root, self.feature, intent['intent_id'])['run_id'],
                         'codex-1')

    def test_unresolved_intent_can_be_abandoned_with_reason_and_redispatched(self):
        self.tasks()
        self.enable()
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', side_effect=delegation.DelegationError('response lost')):
            with self.assertRaisesRegex(delegation.DelegationError, 'START_UNCERTAIN'):
                dispatch.start(self.root, self.feature, 'T001')
        intent_id = dispatch.load_ledger(self.root, self.feature)['attempts'][0]['intent_id']
        with patch.object(dispatch, 'launch') as launched:
            with self.assertRaisesRegex(delegation.DelegationError, 'ALREADY_RUNNING'):
                self.start_one()
        launched.assert_not_called()
        self.assertFalse(dispatch.recover_intent(self.root, self.feature, intent_id)['found'])
        with self.assertRaisesRegex(delegation.DelegationError, 'REASON_REQUIRED'):
            dispatch.abandon_intent(self.root, self.feature, intent_id, ' ')
        result = dispatch.abandon_intent(self.root, self.feature, intent_id,
                                         'Driver printed no response and wrote no run')
        self.assertEqual(result['status'], 'intent-abandoned')
        ledger = dispatch.load_ledger(self.root, self.feature)
        self.assertEqual(ledger['attempts'][0]['abandon_reason'],
                         'Driver printed no response and wrote no run')
        self.assertEqual(ledger['route_decisions'][-1]['decision'], 'intent-abandoned')
        with self.assertRaisesRegex(delegation.DelegationError, 'NOT_STARTING'):
            dispatch.recover_intent(self.root, self.feature, intent_id)
        self.assertEqual(self.start_one(run_id='codex-9')['run_id'], 'codex-9')

    def test_abandon_waits_while_a_start_may_still_be_in_flight(self):
        self.tasks()
        self.enable()
        ledger = dispatch.load_ledger(self.root, self.feature)
        ledger['attempts'].append({'intent_id': 'intent-1', 'identity': self.feature + '/T001',
                                   'status': 'starting', 'started_at': dispatch.stamp(),
                                   'route_candidates': []})
        w.write(delegation.ledger_path(self.root, self.feature), ledger)
        with self.assertRaisesRegex(delegation.DelegationError, 'START_IN_PROGRESS'):
            dispatch.abandon_intent(self.root, self.feature, 'intent-1', 'dispatcher crashed')
        with patch.object(dispatch, 'ABANDON_GRACE_SECONDS', 0):
            dispatch.abandon_intent(self.root, self.feature, 'intent-1', 'dispatcher crashed')
        self.assertEqual(dispatch.load_ledger(self.root, self.feature)['attempts'][0]['status'],
                         'intent-abandoned')

    def test_collect_uses_the_driver_copy_that_started_the_run(self):
        self.tasks()
        self.enable()
        self.start_one()
        project_driver = str((self.root / '.agents/skills/delegate-task/delegate.mjs').resolve())
        calls = []
        payload = {'run_id': 'codex-1', 'status': 'successful', 'harness': 'codex',
                   'dirty_paths_changed': [], 'artifacts': {'dir': str(self.root / '.delegate/runs/codex-1')}}
        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, json.dumps(payload), '')
        with tempfile.TemporaryDirectory() as directory:
            global_root = Path(directory)
            global_driver = self.skill_copy(global_root)
            self.policy['delegation']['install_scope'] = 'global'
            self.configure()
            with patch.object(delegation, 'global_root', return_value=global_root), \
                 patch.object(delegation, 'inspect_skill',
                              return_value={'ok': True, 'driver': str(global_driver)}), \
                 patch.object(dispatch.shutil, 'which', return_value='node'), \
                 patch.object(dispatch.subprocess, 'run', side_effect=run):
                dispatch.collect(self.root, self.feature, 'codex-1')
        self.assertEqual(calls[0][1], project_driver)

    def test_task_type_uses_markers_and_leading_actions_only(self):
        expected = {
            # Embedded domain nouns never reroute implementation work.
            '- [ ] T010 Add audit logging middleware': 'implementation',
            '- [ ] T011 [P] Build the review queue UI': 'implementation',
            '- [ ] T012 Implement login endpoint so contract tests pass': 'implementation',
            '- [ ] T013 [US1] Implement evidence upload API': 'implementation',
            '- [ ] T014 Add manual override toggle': 'implementation',
            '- [ ] T015 Add test fixtures loader': 'implementation',
            '- [ ] T016 Document storage service': 'implementation',
            '- [ ] T017 Implement parser per [docs] page': 'implementation',
            # A leading domain noun is the thing being built, not a check or a doc.
            '- [ ] T018 Audit log retention: implement purge job': 'implementation',
            '- [ ] T019 Review queue API endpoint': 'implementation',
            '- [ ] T040 Inspect payload parser and fix crash': 'implementation',
            '- [ ] T041 Test runner integration in CI': 'implementation',
            '- [ ] T042 Create guide page component': 'implementation',
            '- [ ] T043 Review and fix lint errors': 'implementation',
            '- [ ] T044 Run tests and fix failures': 'implementation',
            '- [ ] T045 Test coverage report widget': 'implementation',
            # [Impl] is the explicit escape for anything the heuristics misread.
            '- [ ] T046 [Impl] Review auth module for injection risks': 'implementation',
            '- [ ] T047 [P] [Implementation] Update README with setup steps': 'implementation',
            '- [ ] T048 [Code] [QA] Run the integration test suite': 'implementation',
            # Explicit markers win in the leading tag block.
            '- [ ] T020 [QA] Check signup': 'qa',
            '- [ ] T021 [P] [TDD] Implement parser': 'qa',
            '- [ ] T022 [Docs] Refresh setup': 'documentation',
            '- [ ] T023 [Manual] Explain exports': 'documentation',
            '- [ ] T024 [P] [Review] Check auth module': 'review',
            # Clear unmarked QA, documentation and review actions keep their routes.
            '- [ ] T030 Run the integration test suite': 'qa',
            '- [ ] T031 Write contract test for POST /users in tests/contract/test_users.py': 'qa',
            '- [ ] T032 Add unit tests': 'qa',
            '- [ ] T033 [P] [US2] Test login flow in the browser': 'qa',
            '- [ ] T034 Capture screenshots of the settings page': 'qa',
            '- [ ] T035 Update README with setup steps': 'documentation',
            '- [ ] T036 Document the export API': 'documentation',
            '- [ ] T037 Write release notes for 1.5': 'documentation',
            '- [ ] T038 Review auth module for injection risks': 'review',
            '- [ ] T039 Audit dependency licences': 'review',
            '- [ ] T049 Inspect the session handling for fixation': 'review',
            '- [ ] T050 Update README section': 'documentation',
            '- [ ] T051 Write the user guide for exports': 'documentation',
        }
        for description, work_type in expected.items():
            with self.subTest(description=description):
                self.assertEqual(delegation.task_type(description), work_type)

    def test_review_and_implementation_routes_launch_writable(self):
        self.tasks('- [ ] T001 Implement parser\n- [ ] T002 [Review] Check parser\n')
        self.enable()
        launched = []
        def launch(root, driver, candidate, *args):
            launched.append(candidate)
            return {'run_id': 'codex-' + str(len(launched)), 'state': 'running'}
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', side_effect=launch):
            dispatch.start(self.root, self.feature, 'T001')
            dispatch.start(self.root, self.feature, 'T002')
            route = delegation.selected_route(self.policy['delegation'], 'review', 'codex')
            dispatch.candidate_start(self.root, self.feature, self.feature + '/stage:review', 'review',
                                     route, dispatch.brief_file(self.root, 'Review stage'),
                                     self.root, 1800)
        self.assertEqual(len(launched), 3)
        self.assertEqual([c['read_only'] for c in launched], [False, False, False])
        attempts = dispatch.load_ledger(self.root, self.feature)['attempts']
        self.assertEqual([a['task_type'] for a in attempts], ['implementation', 'review', 'review'])
        self.assertFalse(any(a['read_only'] for a in attempts))

    def test_annotation_adds_newline_before_marker_on_final_task_line(self):
        self.enable()
        path = self.tasks()
        cases = {
            'lf': b'# Tasks\n- [ ] T001 Implement parser\n- [ ] T002 [QA] Run tests',
            'crlf-bom': b'\xef\xbb\xbf# Tasks\r\n- [ ] T001 Implement parser\r\n- [ ] T002 [QA] Run tests',
        }
        for name, original in cases.items():
            with self.subTest(case=name):
                newline = b'\r\n' if b'\r\n' in original else b'\n'
                path.write_bytes(original)
                before = w.fingerprint_files(self.root, [self.feature + '/tasks.md'])
                self.assertEqual(delegation.annotate_tasks(self.root, self.feature,
                                                           self.policy['delegation'], 'codex')['annotated'], 2)
                content = path.read_bytes()
                self.assertEqual(content.startswith(b'\xef\xbb\xbf'), original.startswith(b'\xef\xbb\xbf'))
                self.assertIn(b'Run tests' + newline + b'  <!-- sanduq-delegation ', content)
                self.assertTrue(content.endswith(b' -->'))
                self.assertNotIn(b'tests  <!--', content)
                if newline == b'\r\n':
                    self.assertNotIn(b'\n', content.replace(b'\r\n', b''))
                text = content.decode('utf-8-sig')
                self.assertEqual(list(task_issues.parse_tasks(text)), ['T001', 'T002'])
                self.assertEqual(before, w.fingerprint_files(self.root, [self.feature + '/tasks.md']))
                again = delegation.annotate_tasks(self.root, self.feature, self.policy['delegation'], 'codex')
                self.assertFalse(again['changed'])
                self.assertEqual(path.read_bytes(), content)

    def test_annotation_repairs_marker_joined_to_final_task_line(self):
        self.enable()
        path = self.tasks()
        original = b'- [ ] T001 Implement parser\n- [ ] T002 [QA] Run tests'
        path.write_bytes(original)
        before = w.fingerprint_files(self.root, [self.feature + '/tasks.md'])
        joined = (original + b'  <!-- sanduq-delegation {"preferred_harness": "codex", '
                  b'"preferred_model": "old", "rule": "default:qa", "task_id": "T002", '
                  b'"task_type": "qa"} -->\n')
        path.write_bytes(joined)
        self.assertEqual(before, w.fingerprint_files(self.root, [self.feature + '/tasks.md']))
        delegation.annotate_tasks(self.root, self.feature, self.policy['delegation'], 'codex')
        lines = path.read_text(encoding='utf-8').splitlines()
        self.assertEqual(lines[2], '- [ ] T002 [QA] Run tests')
        self.assertTrue(lines[3].startswith('  <!-- sanduq-delegation '))
        self.assertNotIn('"old"', lines[3])
        self.assertEqual(len(lines), 4)
        self.assertEqual(before, w.fingerprint_files(self.root, [self.feature + '/tasks.md']))

    def test_collect_refuses_a_ledger_driver_outside_skill_locations(self):
        self.tasks()
        self.enable()
        self.start_one()
        (self.root / 'evil.mjs').write_text('// not a skill\n', encoding='utf-8')
        ledger = dispatch.load_ledger(self.root, self.feature)
        ledger['attempts'][0]['driver'] = 'evil.mjs'
        w.write(delegation.ledger_path(self.root, self.feature), ledger)
        with patch.object(dispatch.shutil, 'which', return_value='node'), \
             patch.object(dispatch.subprocess, 'run') as run:
            with self.assertRaisesRegex(delegation.DelegationError, 'DRIVER_UNTRUSTED'):
                dispatch.collect(self.root, self.feature, 'codex-1')
        run.assert_not_called()


    # --- Final review remediation -------------------------------------------------

    @staticmethod
    def dead_pid():
        child = subprocess.Popen([sys.executable, '-c', 'pass'])
        child.wait()
        return child.pid

    def driver_start_failure(self, intent_id, candidate, run_id, supervisor_pid, journal=()):
        """Write the run the real driver leaves behind when it exits 5.

        meta.json and the "created" journal entry mirror cmdStart; result.json
        comes from the driver's own finalizeStartFailure, the exit-5 code path.
        """
        directory = self.root / '.delegate/runs' / run_id
        directory.mkdir(parents=True)
        meta = {'run_id': run_id, 'parent_run_id': None, 'resume_session': None,
                'harness': candidate['harness'], 'harness_label': 'OpenAI Codex',
                'harness_version': 'test', 'tier': 'verified', 'task': 'Task', 'cwd': str(self.root),
                'model': candidate['requested_model'], 'deliverable': None,
                'constraint': ['Sanduq delegation intent: ' + intent_id], 'permission': 'bypass',
                'allow_commit': False, 'raw': False, 'timeout_ms': 1000, 'clean_env': False,
                'keep_env': [], 'kept_env_names': None, 'started_at': dispatch.stamp(), 'nonce': 'n',
                'supervisor_pid': supervisor_pid}
        w.write(directory / 'meta.json', meta)
        with (directory / 'journal.jsonl').open('w', encoding='utf-8') as handle:
            for state in ('created', *journal):
                handle.write(json.dumps({'t': dispatch.stamp(), 'state': state}) + '\n')
        driver = (delegation.bundled_skill() / 'delegate.mjs').resolve().as_uri()
        script = ("import { finalizeStartFailure } from " + json.dumps(driver) + ";"
                  "const meta = JSON.parse(process.argv[1]);"
                  "finalizeStartFailure({ meta, dir: process.argv[2], t0: Date.now(),"
                  " why: 'supervisor did not acknowledge start within 15s' });")
        subprocess.run([shutil.which('node'), '--input-type=module', '-e', script,
                        json.dumps(meta), str(directory)], check=True, capture_output=True)
        return directory

    def test_exit_five_without_any_launch_moves_to_the_configured_fallback(self):
        self.tasks()
        self.enable()
        dead = self.dead_pid()
        calls = []
        def launch(root, driver, candidate, cwd, task, timeout, intent_id):
            calls.append(candidate)
            if len(calls) == 1:
                self.driver_start_failure(intent_id, candidate, 'codex-dead', dead)
                raise dispatch.StartFailed('DELEGATE_START_FAILED: delegate: supervisor failed to start',
                                           dispatch.SUPERVISOR_START_FAILED)
            # The fallback's answer is lost after its driver wrote a run.
            w.write(self.root / '.delegate/runs/codex-live/meta.json',
                    {'run_id': 'codex-live', 'constraint': ['Sanduq delegation intent: ' + intent_id],
                     'harness': candidate['harness'], 'model': candidate['requested_model'],
                     'permission': 'bypass'})
            raise delegation.DelegationError('DELEGATE_START_RESPONSE_INVALID')
        with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
             patch.object(dispatch, 'launch', side_effect=launch):
            with self.assertRaisesRegex(delegation.DelegationError, 'START_UNCERTAIN'):
                dispatch.start(self.root, self.feature, 'T001')
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]['choice'], 'fallback:1')
        ledger = dispatch.load_ledger(self.root, self.feature)
        intent = ledger['attempts'][0]
        self.assertEqual(intent['start_failures'][0]['run_id'], 'codex-dead')
        self.assertEqual([d['decision'] for d in ledger['route_decisions']],
                         ['start-failed', 'start-uncertain'])
        # The proven non-launch never makes recovery ambiguous or abandonable.
        with self.assertRaisesRegex(delegation.DelegationError, 'INTENT_HAS_RUN'):
            dispatch.abandon_intent(self.root, self.feature, intent['intent_id'], 'stuck')
        recovered = dispatch.recover_intent(self.root, self.feature, intent['intent_id'])
        self.assertEqual(recovered['run_id'], 'codex-live')
        attempt = dispatch.load_ledger(self.root, self.feature)['attempts'][0]
        self.assertEqual(attempt['candidate_index'], 1)

    def test_exit_five_that_may_have_launched_stays_uncertain(self):
        self.tasks()
        self.enable()
        dead = self.dead_pid()
        cases = {
            'supervisor acknowledged late': dict(exit_code=5, supervisor=dead, journal=('supervisor_started',)),
            'agent child started': dict(exit_code=5, supervisor=dead, journal=('child_started',)),
            'supervisor still alive': dict(exit_code=5, supervisor=os.getpid(), journal=()),
            'other exit code': dict(exit_code=1, supervisor=dead, journal=()),
            'no finalised result': dict(exit_code=5, supervisor=dead, journal=(), result=False),
        }
        for number, (name, case) in enumerate(cases.items(), 1):
            identity = 'T00' + str(number)
            with self.subTest(case=name):
                self.tasks(''.join('- [ ] T00' + str(n) + ' Implement part ' + str(n) + '\n'
                                   for n in range(1, len(cases) + 1)))
                def launch(root, driver, candidate, cwd, task, timeout, intent_id):
                    directory = self.driver_start_failure(intent_id, candidate, 'codex-' + str(number),
                                                          case['supervisor'], case['journal'])
                    if case.get('result') is False:
                        (directory / 'result.json').unlink()
                    raise dispatch.StartFailed('DELEGATE_START_FAILED: x', case['exit_code'])
                with patch.object(delegation, 'doctor', return_value=self.fake_doctor()), \
                     patch.object(dispatch, 'launch', side_effect=launch) as launched:
                    with self.assertRaisesRegex(delegation.DelegationError, 'START_UNCERTAIN'):
                        dispatch.start(self.root, self.feature, identity)
                self.assertEqual(launched.call_count, 1)
                intent = dispatch.load_ledger(self.root, self.feature)['attempts'][-1]
                self.assertEqual(intent['status'], 'starting')
                self.assertNotIn('start_failures', intent)

    def test_stale_ledger_lock_from_a_dead_process_is_recovered(self):
        self.tasks()
        self.enable()
        lock = (self.root / '.specify/workflow/runtime' /
                ('delegation-' + w.digest(self.feature) + '.lock'))
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(json.dumps({'pid': self.dead_pid(), 'host': delegation.socket.gethostname(),
                                    'token': 'dead', 'created': 0}), encoding='utf-8')
        self.assertEqual(self.start_one()['run_id'], 'codex-1')
        self.assertFalse(lock.exists())
        self.assertEqual(len(dispatch.load_ledger(self.root, self.feature)['attempts']), 1)
        # An owner record that was never written is stale only once it is old.
        lock.write_text('', encoding='utf-8')
        old = time.time() - delegation.LOCK_UNREADABLE_STALE_SECONDS - 5
        os.utime(lock, (old, old))
        self.assertEqual(dispatch.read_ledger(self.root, self.feature)['feature'], self.feature)
        self.assertFalse(lock.exists())

    def test_live_or_foreign_ledger_lock_is_never_taken(self):
        self.tasks()
        self.enable()
        lock = (self.root / '.specify/workflow/runtime' /
                ('delegation-' + w.digest(self.feature) + '.lock'))
        lock.parent.mkdir(parents=True, exist_ok=True)
        owners = {'live process': {'pid': os.getpid(), 'host': delegation.socket.gethostname()},
                  'dead pid on another host': {'pid': self.dead_pid(), 'host': 'other-host'}}
        for name, owner in owners.items():
            with self.subTest(owner=name):
                content = json.dumps({**owner, 'token': 'held', 'created': 0})
                lock.write_text(content, encoding='utf-8')
                with patch.object(dispatch, 'LOCK_TIMEOUT', 0.2), \
                     patch.object(dispatch, 'launch') as launched:
                    with self.assertRaisesRegex(delegation.DelegationError, 'DELEGATION_LEDGER_BUSY: retry'):
                        self.start_one()
                launched.assert_not_called()
                self.assertEqual(lock.read_text(encoding='utf-8'), content)

    def test_stale_lock_recovery_puts_back_a_lock_that_turned_live(self):
        lock = self.root / '.specify/workflow/runtime/probe.lock'
        lock.parent.mkdir(parents=True, exist_ok=True)
        live = json.dumps({'pid': os.getpid(), 'host': delegation.socket.gethostname(),
                           'token': 'live', 'created': 0})
        lock.write_text(live, encoding='utf-8')
        verdicts = iter((True,))
        real = delegation.lock_is_stale
        # The inspection sees a dead owner; by the capture a live owner holds it.
        with patch.object(delegation, 'lock_is_stale',
                          side_effect=lambda path, owner: next(verdicts, None) or real(path, owner)):
            self.assertFalse(delegation.recover_stale_lock(lock))
        self.assertEqual(lock.read_text(encoding='utf-8'), live)
        self.assertEqual([p.name for p in lock.parent.iterdir()], ['probe.lock'])

    def test_displaced_ledger_owner_refuses_to_write(self):
        self.tasks()
        self.enable()
        with self.assertRaisesRegex(delegation.DelegationError, 'lock was lost'):
            with dispatch.edit_ledger(self.root, self.feature) as ledger:
                ledger['attempts'].append({'identity': 'x', 'status': 'running'})
                lock = next((self.root / '.specify/workflow/runtime').glob('delegation-*.lock'))
                lock.write_text(json.dumps({'pid': os.getpid(), 'token': 'newer'}), encoding='utf-8')
        self.assertFalse(delegation.ledger_path(self.root, self.feature).exists())

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = delegation.main(['--root', str(self.root), *args])
        return code, json.loads(output.getvalue())

    def test_delegation_cli_normalises_feature_for_route_and_annotate(self):
        self.tasks()
        name = self.feature.split('/')[1]
        self.policy['delegation']['enabled'] = True
        self.policy['delegation']['overrides'][self.feature + '/T001'] = {
            'preferred': {'harness': 'claude', 'model': 'custom-reviewer'}, 'fallbacks': []}
        self.configure()
        for spelling in ('specs\\' + name + '\\', 'specs/' + name + '/', './specs//' + name,
                         str((self.root / 'specs' / name).resolve())):
            with self.subTest(spelling=spelling):
                code, routed = self.run_cli('route', '--feature', spelling, '--id', 'T001',
                                            '--type', 'implementation')
                self.assertEqual(code, 0)
                self.assertEqual(routed['identity'], self.feature + '/T001')
                self.assertEqual(routed['candidates'][0]['requested_model'], 'custom-reviewer')
                self.assertEqual(routed['candidates'][0]['rule'], 'override:' + self.feature + '/T001')
                code, annotated = self.run_cli('annotate', '--feature', spelling)
                self.assertEqual(code, 0)
                text = (self.root / self.feature / 'tasks.md').read_text(encoding='utf-8')
                self.assertIn('"rule": "override:' + self.feature + '/T001"', text)
                self.assertEqual(text.count('"task_id": "T001"'), 1)
        for spelling in ('specs/../' + name, '../specs/' + name, 'specs/' + name + '/..', 'specs',
                         'other/' + name, str(Path(tempfile.gettempdir()) / 'specs' / name)):
            with self.subTest(spelling=spelling):
                for action in (['route', '--feature', spelling, '--id', 'T001', '--type', 'qa'],
                               ['annotate', '--feature', spelling]):
                    code, failed = self.run_cli(*action)
                    self.assertEqual(code, 1)
                    self.assertIn('DELEGATION_FEATURE_INVALID', failed['error'])
        code, failed = self.run_cli('route', '--feature', self.feature, '--id', '../T001', '--type', 'qa')
        self.assertIn('DELEGATION_IDENTITY_INVALID', failed['error'])
        # The workflow claim and the dispatcher share this one identity function.
        self.assertIs(dispatch.feature_identity, delegation.feature_identity)

    def test_concurrent_installs_replace_an_incompatible_copy_once(self):
        global_root = self.isolated_skills()
        target = self.copy_bundle(self.root / '.agents/skills/delegate-task',
                                  self.without_contract_command)
        (target / 'team-notes.md').write_text('keep me\n', encoding='utf-8')
        barrier = threading.Barrier(3)
        results, errors = [], []
        def run():
            barrier.wait()
            try:
                results.append(delegation.install_skill(self.root, 'codex', 'project'))
            except Exception as error:  # surfaced below
                errors.append(error)
        threads = [threading.Thread(target=run) for _ in range(3)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(sorted(r['installed'] for r in results), [False, False, True])
        backups = self.root / '.specify/workflow/backups/delegate-task'
        entries = sorted(p.name for p in backups.iterdir())
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].startswith('delegate-task.'))
        self.assertEqual((backups / entries[0] / 'team-notes.md').read_text(encoding='utf-8'), 'keep me\n')
        self.assertTrue(delegation.inspect_skill(self.root, 'codex')['ok'])
        self.assertFalse((target / 'team-notes.md').exists())
        self.assertEqual(list((self.root / '.specify/workflow/runtime').glob('*.lock')), [])
        self.assertFalse((global_root / '.sanduq').exists())

    def test_install_waits_for_a_live_install_lock_and_then_reuses(self):
        self.isolated_skills()
        lock = delegation.install_lock_path(self.root, 'project')
        release = threading.Event()
        def holder():
            with delegation.file_lock(lock, 5, 'BUSY'):
                delegation.install_skill_locked(self.root, 'codex', 'project', False)
                release.set()
                time.sleep(0.5)
        thread = threading.Thread(target=holder)
        thread.start()
        release.wait(60)
        waited = delegation.install_skill(self.root, 'codex', 'project')
        thread.join()
        self.assertFalse(waited['installed'])
        self.assertEqual(waited['scope'], 'project')

    def test_staged_install_failure_leaves_no_partial_copy(self):
        self.isolated_skills()
        with patch.object(delegation, 'driver_compatibility', return_value='bad staged copy'):
            with self.assertRaisesRegex(delegation.DelegationError, 'INSTALL_FAILED: bad staged copy'):
                delegation.install_skill(self.root, 'codex', 'project')
        self.assertFalse((self.root / '.agents/skills/delegate-task').exists())
        self.assertEqual(list((self.root / '.specify/workflow/backups/delegate-task').iterdir()), [])

    def test_legacy_backups_leave_discovery_roots_when_a_copy_is_reused(self):
        global_root = self.isolated_skills()
        self.copy_bundle(self.root / '.agents/skills/delegate-task')
        project_legacy = self.copy_bundle(self.root / '.claude/skills/delegate-task.sanduq-backup-aa')
        global_legacy = self.copy_bundle(global_root / '.codex/skills/delegate-task.sanduq-backup-bb')
        reused = delegation.install_skill(self.root, 'codex', 'project')
        self.assertFalse(reused['installed'])
        self.assertFalse(project_legacy.exists())
        self.assertFalse(global_legacy.exists())
        moved = {Path(item['from']).name: Path(item['to']) for item in reused['legacy_backups_moved']}
        self.assertTrue(moved['delegate-task.sanduq-backup-aa'].resolve().is_relative_to(
            (self.root / '.specify/workflow/backups/delegate-task').resolve()))
        self.assertTrue(moved['delegate-task.sanduq-backup-bb'].resolve().is_relative_to(
            (global_root / '.sanduq/backups/delegate-task').resolve()))
        for path in moved.values():
            self.assertTrue((path / 'SKILL.md').is_file())
            self.assert_outside_skill_roots(path, self.root, global_root)
        self.assertEqual(len([n for n in reused['notices'] if 'LEGACY_BACKUP_MOVED' in n]), 2)
        again = delegation.install_skill(self.root, 'codex', 'project')
        self.assertEqual(again['legacy_backups_moved'], [])

    def test_replaced_customised_copy_is_reported_by_install_dispatch_and_claim(self):
        self.isolated_skills()
        target = self.copy_bundle(self.root / '.agents/skills/delegate-task',
                                  self.without_contract_command)
        installed = delegation.install_skill(self.root, 'codex', 'project')
        notice = next(n for n in installed['notices'] if n.startswith('DELEGATE_SKILL_REPLACED'))
        self.assertIn(str(target), notice)
        self.assertIn(installed['backup'], notice)
        self.assertIn('predates the contract command', notice)
        self.assertEqual(installed['replaced'][0]['backup'], installed['backup'])
        self.tasks()
        self.enable()
        health = {**self.fake_doctor(), 'notices': [notice]}
        with patch.object(delegation, 'doctor', return_value=health), \
             patch.object(dispatch, 'launch', return_value={'run_id': 'codex-1', 'state': 'running'}):
            self.assertEqual(dispatch.start(self.root, self.feature, 'T001')['notices'], [notice])
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        with patch.object(delegation, 'doctor', return_value=health), \
             patch.object(w, 'doctor', return_value={'ok': True, 'errors': []}):
            claim = run.claim({'session_id': 'test-session'})
        self.assertEqual(claim['notices'], [notice])
        self.assertNotIn('notices', w.read(run.path)['active'])

    def test_model_rejection_ignores_quoted_worker_output(self):
        stderr = self.root / 'stderr.log'
        def rejected(text, requested='gpt-6-sol', reason=''):
            stderr.write_text(text, encoding='utf-8')
            return dispatch.model_rejected({'status_reason': reason, 'artifacts': {'stderr': str(stderr)}},
                                           requested)
        self.assertFalse(rejected('FAILED tests/test_orders.py::test_lookup\n'
                                  'orders.models.DoesNotExist: Model matching query does not exist.\n'))
        self.assertFalse(rejected('E   AssertionError: model not found in registry\n'))
        self.assertTrue(rejected('Error: model gpt-6-sol is not available for this account\n'))
        self.assertTrue(rejected('{"error":{"code":"model_not_found","message":"no"}}\n'))
        self.assertFalse(rejected('Error: model gpt-6-sol is not available\n' + 'progress\n' * 60))
        # Without a requested model only the driver's status reason can say so.
        self.assertFalse(rejected('Error: model is not available\n', requested=None))
        self.assertTrue(rejected('', requested=None, reason='Unknown model'))


if __name__ == '__main__':
    unittest.main()
