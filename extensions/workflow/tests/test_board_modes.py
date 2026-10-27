"""PH-03 stream B: board sync modes (REQ-22, DEC-17 B), the mode-aware board check (AHMED-06), policy loading and
init (AHMED-04, AHMED-25, AHMED-08) and the confirmation before a claim removes later receipts (AHMED-12)."""
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow as w  # noqa: E402
from test_receipt_contract import Harness  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/workflow.py'
CONFIG = '.specify/extensions/project/config.json'


class Base(Harness):
    def board(self, mode, tasks=None):
        self.policy['project_sync'] = {'mode': mode}
        self.policy['issue_sync']['taskstoissues'] = tasks or ('required' if mode == 'full' else 'off')
        self.configure()

    def advance(self, run, last):
        claims = []
        while True:
            claim = run.claim(self.usage())  # stream C: finalize before Ready is refused
            claims.append(claim)
            run.complete(claim['token'], self.receipt(claim['stage']))
            if claim['stage'] == last:
                return claims

    def cli(self, *args):
        done = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), *args],
                              capture_output=True, text=True, encoding='utf-8')
        return done.returncode, json.loads(done.stdout)


class BoardModeTests(Base):
    def test_policy_accepts_the_modes_and_refuses_others(self):
        for mode in ('full', 'minimal', 'off'):
            policy = copy.deepcopy(self.policy)
            policy['project_sync'] = {'mode': mode}
            w.validate_policy(policy)
        policy = copy.deepcopy(self.policy)
        policy['issue_sync']['taskstoissues'] = 'off'
        w.validate_policy(policy)
        policy['project_sync'] = {'mode': 'sometimes'}
        with self.assertRaisesRegex(w.WorkflowError, 'PROJECT_SYNC_POLICY_INVALID: mode'):
            w.validate_policy(policy)

    def test_switching_the_mode_reaches_no_stage(self):
        base = w.validate_policy(copy.deepcopy(self.policy))
        for mutate in (lambda p: p.update(project_sync={'mode': 'minimal'}),
                       lambda p: p.update(project_sync={'mode': 'off'}),
                       lambda p: p['issue_sync'].update(taskstoissues='off')):
            changed = copy.deepcopy(base)
            mutate(changed)
            self.assertEqual(w.policy_cutoff(base, changed), len(w.BASE_STAGES))

    def test_doctor_passes_without_a_board_in_mode_off_and_names_the_mode(self):
        (self.root / CONFIG).unlink()
        self.board('off')
        result = w.doctor(self.root, self.policy, project=True)
        self.assertTrue(result['ok'], result['errors'])
        self.assertTrue(result['board_sync'].startswith('off: no board'), result['board_sync'])
        self.assertIn('issue_sync.taskstoissues off', result['board_sync'])
        run = self.run_object()
        self.assertEqual(run.claim(self.usage())['stage'], 'scope')

    def test_a_missing_board_in_full_mode_is_one_actionable_error(self):
        (self.root / CONFIG).unlink()
        errors = w.project_errors(self.root, self.policy)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith('PROJECT_NOT_CONFIGURED: '), errors)
        self.assertIn('$speckit-project-init', errors[0])
        self.assertIn('--board none', errors[0])
        run = self.run_object()
        with self.assertRaises(w.WorkflowError) as caught:
            run.claim(self.usage())
        self.assertTrue(str(caught.exception).startswith('PROJECT_NOT_CONFIGURED: '), str(caught.exception))
        self.assertEqual(str(caught.exception).count('PROJECT_'), 1)
        w.write(self.root / CONFIG, {})
        self.assertEqual(len(w.project_errors(self.root, self.policy)), 1)

    def test_a_partial_board_names_the_expected_column(self):
        config = w.read(self.root / CONFIG)
        config['phaseToStatus'].pop('in-review')
        w.write(self.root / CONFIG, config)
        errors = w.project_errors(self.root, self.policy)
        self.assertEqual(errors, ['PROJECT_PHASE_UNMAPPED: in-review (expected column In review, or map it in '
                                  'config.json phaseToStatus)'])

    def test_minimal_mode_skips_task_issues_and_writes_only_tracked_phases(self):
        self.board('minimal')
        run = self.run_object()
        state = run.load()
        self.assertEqual(state['skipped'], {'taskstoissues': 'issue_sync.taskstoissues: off'})
        self.assertNotIn('taskstoissues', state['stage_plan']['stages'])
        claims = self.advance(run, 'execute')
        self.assertNotIn('taskstoissues', [c['stage'] for c in claims])
        synced = {c['stage']: c['project_sync'] for c in claims if c['project_sync']}
        self.assertEqual({s: p['phase'] for s, p in synced.items()}, {'analyze': 'ready', 'execute': 'in-progress'})
        self.assertNotIn('workflow/task-issues.json', ' '.join(w.required_inputs(self.root, self.feature, 'execute')))
        # A parking phase is a no-op write: recorded as done, no Project script call.
        real_run = subprocess.run

        def guarded(command, *args, **kwargs):
            self.assertNotIn(w.PROJECT_SYNC_SCRIPT, ' '.join(map(str, command)), 'the Project script was called')
            return real_run(command, *args, **kwargs)
        with patch.object(w.subprocess, 'run', guarded):
            result = run.sync_project('open')
        self.assertEqual((result['ok'], result['applied']), (True, False))
        self.assertIn('skipped: project_sync.mode minimal does not write phase open', result['project_sync']['summary'])
        self.assertEqual(run.load()['project_sync']['state'], 'done')
        ran = w.ready_checks(self.root, self.feature, self.policy, run.load(), rules={'tasks': True, 'task_links': True})
        self.assertEqual(ran, ['tasks', 'task_links:skipped (issue_sync.taskstoissues off)'])

    def test_full_mode_is_unchanged(self):
        run = self.run_object()
        claims = self.advance(run, 'execute')
        self.assertIn('taskstoissues', [c['stage'] for c in claims])
        self.assertEqual([c['project_sync']['phase'] for c in claims if c['project_sync']],
                         ['open', 'analysis', 'engineer-review', 'ready', 'in-progress'])
        self.assertNotIn('skipped', run.load())

    def test_switching_the_mode_on_a_feature_at_implement_invalidates_nothing(self):
        run = self.run_object()
        self.advance(run, 'execute')
        before = set(run.load()['receipts'])
        self.board('minimal')
        run = w.Run(self.root, self.feature)
        self.assertEqual(run.next(run.load())['stage'], 'verify')
        claim = run.claim(self.usage())
        self.assertEqual(claim['stage'], 'verify')
        self.assertEqual(set(run.load()['receipts']), before)

    def test_the_task_issue_adapter_refuses_in_mode_off(self):
        self.board('off')
        script = SCRIPT.parent / 'task_issues.py'
        done = subprocess.run([sys.executable, str(script), '--root', str(self.root), '--feature', self.feature,
                               '--parent', '10', '--sync-states', '--summary'], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertTrue(done.stdout.startswith('error TASK_ISSUES_OFF: '), done.stdout)


class PolicyLoadingAndInitTests(Base):
    def test_a_duplicated_section_is_refused_with_its_line(self):
        text = yaml.safe_dump(self.policy, sort_keys=False) + 'issue_sync:\n  taskstoissues: required\n'
        (self.root / '.specify/workflow.yml').write_text(text, encoding='utf-8')
        line = text.count('\n') - 1
        with self.assertRaisesRegex(w.WorkflowError, 'POLICY_DUPLICATE_KEY: issue_sync at line ' + str(line) + ' '):
            w.load_policy(self.root)

    def test_doctor_warns_per_inert_value(self):
        self.policy['execution']['checkpoints'] = 'every-phase'
        self.policy['context']['mode'] = 'measured-with-estimated-fallback'
        warnings = [x for x in w.doctor(self.root, self.policy)['warnings'] if x.startswith('POLICY_VALUE_INERT')]
        self.assertEqual([x.split(' changes')[0] for x in warnings],
                         ['POLICY_VALUE_INERT: execution.checkpoints: every-phase',
                          'POLICY_VALUE_INERT: context.mode: measured-with-estimated-fallback'])
        self.assertFalse([x for x in w.doctor(self.root, w.default_policy(True, True))['warnings']
                          if x.startswith('POLICY_VALUE_INERT')])

    def test_init_is_idempotent_keeps_comments_and_backs_up_the_raw_bytes(self):
        path = self.root / '.specify/workflow.yml'
        path.unlink()
        code, result = self.cli('init', '--qa', 'on', '--manual', 'on', '--board', 'minimal')
        self.assertEqual(code, 0, result)
        self.assertTrue(result['written'])
        self.assertTrue(result['board'].startswith('minimal: '))
        policy = w.load_policy(self.root)
        self.assertEqual((policy['project_sync']['mode'], policy['issue_sync']['taskstoissues']), ('minimal', 'off'))
        path.write_bytes(b'# keep this comment\n' + path.read_bytes())
        original = path.read_bytes()
        code, result = self.cli('init', '--qa', 'on', '--manual', 'on')
        self.assertEqual((code, result['written']), (0, False))
        self.assertNotIn('backup', result)
        self.assertEqual(path.read_bytes(), original)
        code, result = self.cli('init', '--qa', 'on', '--manual', 'on', '--board', 'full')
        self.assertEqual((code, result['written']), (0, True))
        self.assertEqual((self.root / result['backup']).read_bytes(), original)
        policy = w.load_policy(self.root)
        self.assertEqual((policy['project_sync']['mode'], policy['issue_sync']['taskstoissues']), ('full', 'required'))

    def test_init_replace_lists_the_features_it_invalidates(self):
        run = self.run_object()
        self.advance(run, 'qa_analyze')
        code, result = self.cli('init', '--qa', 'off', '--manual', 'on', '--replace')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['affected_features'], [{
            'feature': self.feature, 'restarts_from': 'tasks', 'invalidated': ['tasks', 'qa_analyze'],
            'migrate': w.WORKFLOW_SCRIPT + ' migrate --feature ' + self.feature + ' --reason "<why>"'}])
        code, result = self.cli('init', '--qa', 'off', '--manual', 'on', '--replace')
        self.assertFalse(result['written'])  # still listed: the feature is affected until it is migrated
        self.assertEqual([f['feature'] for f in result['affected_features']], [self.feature])


class ConfirmInvalidationTests(Base):
    def test_a_stale_stage_with_later_receipts_needs_confirmation(self):
        run = self.run_object()
        self.advance(run, 'plan')
        (self.root / self.feature / 'evidence/specify.txt').unlink()
        self.assertEqual(run.next(run.load())['reason'], 'inputs-or-evidence-changed')
        result = run.claim(self.usage())
        self.assertEqual((result['status'], result['stage'], result['invalidates']),
                         ('confirm_invalidation', 'specify', ['clarify', 'plan']))
        self.assertIn('--confirm-invalidation', result['confirm'])
        self.assertTrue(result['recovery'])
        state = run.load()
        self.assertIsNone(state['active'])
        self.assertEqual(set(state['receipts']), {'scope', 'specify', 'clarify', 'plan'})
        claim = run.claim(self.usage(), confirm_invalidation=True)
        self.assertEqual(claim['stage'], 'specify')
        self.assertEqual(set(run.load()['receipts']), {'scope'})

    def test_a_pending_stage_with_no_later_receipt_claims_without_asking(self):
        run = self.run_object()
        self.advance(run, 'specify')
        self.assertEqual(run.claim(self.usage())['stage'], 'clarify')


if __name__ == '__main__':
    unittest.main()
