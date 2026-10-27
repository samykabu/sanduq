"""Issue 99: the Project Sync state as a binding projection, sync-amend, and the runtime-owned project-sync step.

R1 status-only transition during a claim, R2 post-stage sync, R3 binding drift, R4 sync retries,
R8 lean and legacy ownership, and legacy raw-hash receipts. No live GitHub: the Project script is a fake.
"""
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
import ci_gate as c  # noqa: E402
import delegate_dispatch as dispatch  # noqa: E402
import lean_policy  # noqa: E402
import workflow as w  # noqa: E402
from test_receipt_contract import Harness, checkpoint_validator  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
DEFAULT_STATE = '.specify/project-sync-state.json'
LOGS = '.specify/fake-sync/'

# Stands in for project_sync.py: records each call (and the checkpoint's sync record it saw), writes the bound
# entry's status like the real script, and fails before or after its remote write on request.
FAKE_SYNC = r'''
import json, sys
from pathlib import Path
args = sys.argv[1:]
phase, slug = args[args.index('--phase') + 1], args[args.index('--feature') + 1]
logs = Path('.specify/fake-sync')
logs.mkdir(parents=True, exist_ok=True)
control = json.loads((logs / 'control.json').read_text()) if (logs / 'control.json').is_file() else {}
seen = json.loads(Path('specs', slug, 'workflow/checkpoint.json').read_text()).get('project_sync')
with open(logs / 'calls.jsonl', 'a') as f:
    f.write(json.dumps({'phase': phase, 'summary': '--summary' in args, 'seen': seen}) + '\n')
if control.get('mode') == 'fail-before':
    print('error exit=1 reason=network unreachable')
    sys.exit(1)
config = json.loads(Path('.specify/extensions/project/config.json').read_text())
path = Path(config['stateFile'])
state = json.loads(path.read_text()) if path.is_file() else {}
entry = state.setdefault(slug, {'issue': 10, 'issueNodeId': 'I_10', 'itemId': 'PVTI_10', 'status': '', 'subIssues': {}})
status = config['phaseToStatus']['in-review' if control.get('mode') == 'review' else phase]
if control.get('mode') == 'no-status':  # Project's set_status skips an unmapped column or a missing item
    status = entry['status']
if entry['status'] != status:
    with open(logs / 'remote.jsonl', 'a') as f:
        f.write(json.dumps({'item': entry['itemId'], 'status': status}) + '\n')
    entry['status'] = status
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(state, indent=2) + '\n')
if control.get('mode') == 'fail-after':
    print('error exit=1 reason=connection reset after the write')
    sys.exit(1)
print('ok issue=%d status=%s created=0 closed=0' % (entry['issue'], entry['status']))
'''


class Base(Harness):
    state_file = DEFAULT_STATE

    def setUp(self):
        super().setUp()
        self.policy = w.default_policy(False, False)
        self.configure()
        self.slug = self.feature.rsplit('/', 1)[-1]

    def configure(self, superspec=False):
        Harness.configure(self, superspec)
        path = self.root / '.specify/extensions/project/config.json'
        config = w.read(path)
        config['stateFile'] = self.state_file
        w.write(path, config)

    def entry(self, **changes):
        return {'issue': 10, 'issueNodeId': 'I_10', 'itemId': 'PVTI_10', 'status': 'Feature Specification',
                'subIssues': {}, **changes}

    def write_sync(self, other=None, drop=False, **changes):
        state = {'002-other': other or {'issue': 20, 'issueNodeId': 'I_20', 'itemId': 'PVTI_20', 'status': 'Backlog',
                                        'subIssues': {}}}
        if not drop:
            state[self.slug] = self.entry(**changes)
        w.write(self.root / self.state_file, state)

    def advance(self, run, last, receipts=None):
        while True:
            claim = self.claim_any(run)
            stage = claim['stage']
            run.complete(claim['token'], (receipts or {}).get(stage) or self.receipt(stage))
            if stage == last:
                return

    def depends_on_state(self, stage):
        receipt = self.receipt(stage)
        receipt['inputs'] = receipt['inputs'] + [self.state_file]
        return receipt

    def gate(self):
        policy = w.load_policy(self.root)
        return c.check(self.root, self.feature, policy, None, self.gate_rules(policy))

    def current(self, run):
        state = run.load()
        return {stage: w.receipt_status(self.root, self.feature, stage, receipt, self.policy)['current']
                for stage, receipt in state['receipts'].items()}


class StatusTransitionTests(Base):
    def test_r1_status_only_transition_during_the_pr_claim_completes(self):
        run = self.run_object()
        self.write_sync(status='Feature Specification')
        self.advance(run, 'ready', {'specify': self.depends_on_state('specify')})
        claim = run.claim(self.usage(), finalize=True)
        self.assertEqual(claim['stage'], 'pr')
        self.write_sync(status='In review')  # the in-review sync, run before `complete`
        run.complete(claim['token'], self.receipt('pr'))
        state = run.load()
        self.assertTrue(all(self.current(run).values()), self.current(run))
        self.assertEqual(run.next(state)['status'], 'pr_open')
        self.assertTrue(state['receipts']['specify']['fingerprints'][self.state_file].startswith('sync-binding:v1:'))
        checkpoint_validator().validate(state)

    def test_r2_post_stage_sync_returns_to_no_stage_and_passes_the_gate(self):
        run = self.run_object()
        self.write_sync(status='Backlog')
        self.advance(run, 'ready', {'specify': self.depends_on_state('specify')})
        self.write_sync(status='In progress')
        self.commit_all()
        self.assertEqual(run.next(run.load()).get('status'), 'ready_to_finalize')
        self.assertTrue(self.gate()['passed'])
        # A status write into another feature's entry matters neither.
        self.write_sync(status='In progress', other={'issue': 21, 'status': 'Done'})
        self.assertEqual(run.next(run.load()).get('status'), 'ready_to_finalize')


class BindingDriftTests(Base):
    state_file = '.specify/board/sync-state.json'  # nondefault, from the Project config

    def test_r3_binding_changes_reject_while_other_features_and_status_do_not(self):
        run = self.run_object()
        self.write_sync()
        # The default path is no longer the state file: a dependency on it keeps byte hashing.
        self.write(DEFAULT_STATE, '{"001-example": {"status": "Backlog"}}')
        receipt = self.depends_on_state('specify')
        receipt['inputs'] = receipt['inputs'] + [DEFAULT_STATE]
        self.advance(run, 'specify', {'specify': receipt})
        recorded = run.load()['receipts']['specify']['fingerprints']
        self.assertTrue(recorded[self.state_file].startswith('sync-binding:v1:'))
        self.assertEqual(recorded[DEFAULT_STATE], w.fingerprint_files(self.root, [DEFAULT_STATE])[DEFAULT_STATE])
        claim = run.claim(self.usage())
        self.assertEqual(claim['stage'], 'clarify')
        self.assertIn(self.state_file, claim['side_effects'])  # Clarify's permission follows the configured path
        run.complete(claim['token'], self.receipt('clarify'))
        claim = run.claim(self.usage())
        self.assertEqual(claim['stage'], 'plan')
        drifts = {'issue': dict(issue=11), 'issueNodeId': dict(issueNodeId='I_other'),
                  'itemId': dict(itemId='PVTI_other'),
                  'subIssues': dict(subIssues={'T001': {'number': 12, 'nodeId': 'I_12', 'closed': False}}),
                  'missing entry': dict(drop=True)}
        for name, change in drifts.items():
            with self.subTest(drift=name):
                self.write_sync(**change)
                status = w.receipt_status(self.root, self.feature, 'specify', run.load()['receipts']['specify'])
                self.assertEqual((status['current'], status.get('paths')), (False, [self.state_file]))
                with self.assertRaisesRegex(w.WorkflowError, 'UPSTREAM_INPUT_CHANGED_DURING_STAGE: ' + self.state_file):
                    run.complete(claim['token'], self.receipt('plan'))
        # Repository binding: scope-source.json is a required input, and sync-amend checks the entry against it.
        source = self.root / self.feature / 'scope-source.json'
        w.write(source, {'repo': 'other/app', 'issue': 10})
        with self.assertRaisesRegex(w.WorkflowError, 'FEATURE_BINDING_MISMATCH'):
            run.complete(claim['token'], self.receipt('plan'))
        w.write(source, {'repo': 'acme/app', 'issue': 10})
        # Status and another feature's entry (even its binding) change: the completion stands.
        self.write_sync(status='Ready', other={'issue': 21, 'issueNodeId': 'I_21', 'itemId': 'X', 'status': 'Done'})
        run.complete(claim['token'], self.receipt('plan'))
        self.assertTrue(all(self.current(run).values()))
        # The default-path file is byte-hashed: any change stales the receipt that listed it.
        self.write(DEFAULT_STATE, '{"001-example": {"status": "Ready"}}')
        self.assertFalse(self.current(run)['specify'])

    def test_projection_ignores_timestamps_and_key_order(self):
        self.write_sync()
        before = w.sync_binding(self.root, self.feature)
        state = w.read(self.root / self.state_file)
        entry = state.pop(self.slug)
        state[self.slug] = dict(reversed(list({**entry, 'updatedAt': '2026-10-20T00:00:00Z',
                                               'synced_at': 'now'}.items())))
        w.write(self.root / self.state_file, state)
        self.assertEqual(w.sync_binding(self.root, self.feature), before)
        self.assertTrue(before.startswith('sync-binding:v1:'))


class LegacyReceiptTests(Base):
    def legacy(self, run):
        """A Specify receipt recorded before this release: a raw byte hash for the state file."""
        self.write_sync(status='Feature Specification')
        self.advance(run, 'specify', {'specify': self.depends_on_state('specify')})
        state = run.load()
        raw = w.fingerprint_files(self.root, [self.state_file])[self.state_file]
        state['receipts']['specify']['fingerprints'][self.state_file] = raw
        w.write(run.path, state)
        return raw

    def test_raw_hash_stays_byte_exact_until_sync_amend(self):
        run = self.run_object()
        raw = self.legacy(run)
        self.assertTrue(self.current(run)['specify'])
        self.commit_all()  # the old bytes are in HEAD, so the amendment can name the changed fields
        self.write_sync(status='Ready')
        self.assertFalse(self.current(run)['specify'])
        before = copy.deepcopy(run.load()['receipts'])
        result = run.sync_amend('Board status moved to Ready; binding unchanged', actor='reviewer')
        state = run.load()
        record = state['lineage'][-1]
        self.assertEqual((record['kind'], record['via'], record['path'], record['reason'], record['actor']),
                         ('administrative-amendment', 'sync-amend', self.state_file,
                          'Board status moved to Ready; binding unchanged', 'reviewer'))
        new = w.sync_binding(self.root, self.feature)
        self.assertEqual(record['receipts'], {'specify': {'before': raw, 'after': new, 'fields': ['status']}})
        self.assertIn('at', record)
        self.assertEqual(result['amended'], ['specify'])
        for stage, receipt in state['receipts'].items():  # no other hash moved
            expected = dict(before[stage]['fingerprints'])
            if stage == 'specify':
                expected[self.state_file] = new
            self.assertEqual(receipt['fingerprints'], expected)
        self.assertTrue(all(self.current(run).values()))
        checkpoint_validator().validate(state)
        with self.assertRaisesRegex(w.WorkflowError, 'SYNC_AMEND_NOT_NEEDED'):
            run.sync_amend('again')

    def test_sync_amend_refuses_a_binding_that_differs_from_scope_and_task_mapping(self):
        run = self.run_object()
        raw = self.legacy(run)
        self.commit_all('recorded bytes')
        directory = self.root / self.feature
        mapping = {'repo': 'acme/app', 'parent': 10, 'feature': self.feature,
                   'tasks': {'T001': {'number': 11, 'linked': True}}}
        w.write(directory / 'workflow/task-issues.json', mapping)
        cases = {'issue': dict(issue=11), 'task mapping': dict(subIssues={'T001': {'number': 12}}),
                 'missing entry': dict(drop=True)}
        for name, change in cases.items():
            with self.subTest(binding=name):
                self.write_sync(**change)
                with self.assertRaisesRegex(w.WorkflowError, 'SYNC_BINDING_MISMATCH'):
                    run.sync_amend('status only')
                self.assertEqual(run.load()['receipts']['specify']['fingerprints'][self.state_file], raw)
        self.write_sync(status='Ready')
        w.write(directory / 'scope-source.json', {'repo': 'other/app', 'issue': 10})
        with self.assertRaisesRegex(w.WorkflowError, 'SYNC_BINDING_MISMATCH'):
            run.sync_amend('status only')
        w.write(directory / 'scope-source.json', {'repo': 'acme/app', 'issue': 10})
        self.assertEqual(run.sync_amend('status only')['amended'], ['specify'])

    def test_review_fix_1_the_recorded_bytes_must_be_found(self):
        run = self.run_object()
        self.legacy(run)
        # The recorded bytes are in no commit and the binding moved: nothing proves the old item id.
        self.write_sync(status='Ready', itemId='PVTI_other')
        self.commit_all()
        with self.assertRaisesRegex(w.WorkflowError, 'SYNC_BINDING_MISMATCH: no version'):
            run.sync_amend('status only')

    def test_review_fix_1_history_names_the_fields(self):
        run = self.run_object()
        raw = self.legacy(run)
        self.commit_all('recorded bytes')
        self.write_sync(status='Ready')
        self.commit_all('status only')
        self.write_sync(status='In progress')  # neither HEAD nor the working tree holds the recorded bytes
        result = run.sync_amend('status only')
        self.assertEqual(result['amendment']['receipts']['specify']['fields'], ['status'])
        self.assertEqual(result['amendment']['receipts']['specify']['before'], raw)

    def test_w20_the_recipe_for_a_raw_hash_drift_names_sync_amend(self):
        run = self.run_object()
        self.legacy(run)
        self.write_sync(status='Ready')
        receipt = run.load()['receipts']['specify']
        status = w.receipt_status(self.root, self.feature, 'specify', receipt, self.policy)
        recipe = w.recovery_recipe(self.feature, 'specify', status, self.policy, receipt, self.root)
        self.assertIn('sync-amend --feature ' + self.feature, recipe[0])
        self.assertIn('re-record', recipe[-1])
        # Without the root (older callers) the recipe is unchanged.
        self.assertNotIn('sync-amend', ' '.join(w.recovery_recipe(self.feature, 'specify', status, self.policy, receipt)))

    def test_w11_crlf_history_matches_the_portable_recorded_hash(self):
        # Project writes its state file with write_text, which is CRLF on Windows; with autocrlf off the
        # blob keeps CRLF. The receipt hashed the portable (LF) bytes, so history must be folded too.
        subprocess.run(['git', 'config', 'core.autocrlf', 'false'], cwd=self.root, check=True)
        run = self.run_object()
        path = self.root / self.state_file
        raw = self.legacy(run)
        path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        self.assertEqual(w.fingerprint_files(self.root, [self.state_file])[self.state_file], raw)
        self.commit_all('recorded bytes, CRLF')
        self.write_sync(status='Ready')
        self.commit_all('status only')
        self.write_sync(status='In progress')
        result = run.sync_amend('status only')
        self.assertEqual(result['amendment']['receipts']['specify']['fields'], ['status'])

    def test_review_fix_1_history_refuses_a_binding_change(self):
        run = self.run_object()
        raw = self.legacy(run)
        self.commit_all('recorded bytes')
        self.write_sync(itemId='PVTI_other')
        self.commit_all('item moved')
        with self.assertRaisesRegex(w.WorkflowError, 'SYNC_BINDING_MISMATCH: specify was recorded with other itemId'):
            run.sync_amend('status only')
        self.assertEqual(run.load()['receipts']['specify']['fingerprints'][self.state_file], raw)

    def test_review_fix_2_clarify_restamp_keeps_a_legacy_hash_raw(self):
        run = self.run_object()
        raw = self.legacy(run)
        claim = run.claim(self.usage())
        self.assertEqual(claim['stage'], 'clarify')
        self.write_sync(itemId='PVTI_moved')  # Clarify may change the state file
        run.complete(claim['token'], self.receipt('clarify'))
        state = run.load()
        written = state['receipts']['specify']['fingerprints'][self.state_file]
        self.assertEqual(written, w.fingerprint_files(self.root, [self.state_file])[self.state_file])
        self.assertFalse(written.startswith(w.SYNC_BINDING_PREFIX))
        self.assertEqual(state['lineage'][-1]['raw'], {'specify': {self.state_file: {'before': raw, 'after': written}}})
        self.assertTrue(self.current(run)['specify'])
        self.write_sync(status='Ready', itemId='PVTI_moved')
        self.assertFalse(self.current(run)['specify'])  # still byte-exact until sync-amend

    def test_migrate_converts_a_verified_binding_and_keeps_a_differing_one_raw(self):
        run = self.run_object()
        raw = self.legacy(run)
        self.commit_all('recorded bytes')
        self.write_sync(issue=11)
        result = run.migrate('upgrade to 1.16.0')
        self.assertEqual(result['sync_binding']['amended'], [])
        self.assertIn('SYNC_BINDING_MISMATCH', result['sync_binding']['refused'])
        self.assertEqual(run.load()['receipts']['specify']['fingerprints'][self.state_file], raw)
        self.write_sync(status='Ready')
        result = run.migrate('upgrade to 1.16.0')
        self.assertEqual(result['sync_binding']['amended'], ['specify'])
        record = run.load()['lineage'][-1]
        self.assertEqual((record['kind'], record['via']), ('administrative-amendment', 'migrate'))
        self.assertTrue(self.current(run)['specify'])

    def test_sync_amend_command_line(self):
        run = self.run_object()
        self.legacy(run)
        self.commit_all('recorded bytes')
        self.write_sync(status='Ready')
        done = subprocess.run([sys.executable, str(SCRIPTS / 'workflow.py'), '--root', str(self.root), 'sync-amend',
                               '--feature', self.feature, '--reason', 'status only'],
                              capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(json.loads(done.stdout)['amended'], ['specify'])


class ProjectSyncStepTests(Base):
    def setUp(self):
        super().setUp()
        self.write(w.PROJECT_SYNC_SCRIPT, FAKE_SYNC)

    def control(self, mode=None):
        self.write(LOGS + 'control.json', json.dumps({'mode': mode}))

    def lines(self, name):
        path = self.root / LOGS / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []

    def cli(self, *args):
        done = subprocess.run([sys.executable, str(SCRIPTS / 'workflow.py'), '--root', str(self.root), *args],
                              capture_output=True, text=True, encoding='utf-8')
        return done.returncode, json.loads(done.stdout)

    def test_claim_names_the_runtime_step(self):
        self.policy['project_sync'] = {'points': ['specify', 'pr']}
        self.configure()
        run = self.run_object()
        self.advance(run, 'scope')
        claim = run.claim(self.usage())
        self.assertEqual(claim['project_sync'], {
            'phase': 'open', 'command': 'python .specify/extensions/workflow/scripts/workflow.py project-sync '
                                        '--feature ' + self.feature + ' --phase open'})

    def test_r4_retries_are_honest_idempotent_and_write_once(self):
        run = self.run_object()
        self.write_sync(status='Backlog')
        self.advance(run, 'specify', {'specify': self.depends_on_state('specify')})
        # Failure before the remote write.
        self.control('fail-before')
        code, result = self.cli('project-sync', '--feature', self.feature, '--phase', 'open')
        self.assertEqual(code, 1, result)
        self.assertEqual((result['ok'], result['project_sync']['state']), (False, 'failed'))
        self.assertIn('network unreachable', result['project_sync']['summary'])
        calls = self.lines('calls.jsonl')
        self.assertEqual(calls[-1]['seen']['state'], 'pending')  # recorded before the call
        self.assertTrue(calls[-1]['summary'])
        self.assertEqual(self.lines('remote.jsonl'), [])
        self.assertEqual(run.next(run.load())['project_sync']['state'], 'failed')
        code, status = self.cli('status', '--feature', self.feature)
        self.assertEqual(status['project_sync']['state'], 'failed')
        # Failure after a successful remote write.
        self.control('fail-after')
        self.assertEqual(run.sync_project('open')['project_sync']['state'], 'failed')
        self.assertEqual(len(self.lines('remote.jsonl')), 1)
        self.assertEqual(len(self.lines('calls.jsonl')), 2)
        # A failed attempt always runs again; the status is already set, so no second remote write.
        self.control(None)
        result = run.sync_project('open')
        self.assertEqual((result['project_sync']['state'], result['applied']), ('done', True))
        self.assertEqual((len(self.lines('calls.jsonl')), len(self.lines('remote.jsonl'))), (3, 1))
        self.assertNotIn('project_sync', run.next(run.load()))
        # A done phase whose entry still shows its status is not run again.
        result = run.sync_project('open')
        self.assertEqual((result['project_sync']['state'], result['applied']), ('done', False))
        self.assertEqual(len(self.lines('calls.jsonl')), 3)
        # The status write never staled the Specify receipt that depends on the state file.
        self.assertTrue(all(self.current(run).values()))
        # A later phase runs once and succeeds.
        result = run.sync_project('analysis')
        self.assertEqual((result['project_sync']['state'], result['applied']), ('done', True))
        self.assertEqual((len(self.lines('calls.jsonl')), len(self.lines('remote.jsonl'))), (4, 2))
        checkpoint_validator().validate(run.load())

    def test_r4_failure_before_the_write_retries_once(self):
        run = self.run_object()
        self.advance(run, 'specify')
        self.control('fail-before')
        self.assertEqual(run.sync_project('open')['project_sync']['state'], 'failed')
        self.control(None)
        result = run.sync_project('open')
        self.assertEqual(result['project_sync']['state'], 'done')
        self.assertIn('ok issue=10 status=Feature Specification', result['project_sync']['summary'])
        self.assertEqual((len(self.lines('calls.jsonl')), len(self.lines('remote.jsonl'))), (2, 1))

    def test_pending_attempt_whose_status_is_set_is_done_without_a_call(self):
        # The script wrote the status, then the runtime lost the result: the checkpoint still says pending.
        run = self.run_object()
        self.write_sync(status='Feature Specification')
        state = run.load()
        state['project_sync'] = {'phase': 'open', 'state': 'pending', 'at': w.now(), 'summary': None}
        w.write(run.path, state)
        result = run.sync_project('open')
        self.assertEqual((result['project_sync']['state'], result['applied']), ('done', False))
        self.assertEqual(self.lines('calls.jsonl'), [])

    def test_review_fix_3_a_failed_attempt_is_never_reported_done_without_running(self):
        run = self.run_object()
        self.write_sync(status='Feature Specification')  # the entry already shows the open status
        self.control('fail-before')  # e.g. Project refused the parent binding
        self.assertEqual(run.sync_project('open')['project_sync']['state'], 'failed')
        result = run.sync_project('open')
        self.assertEqual((result['ok'], result['project_sync']['state']), (False, 'failed'))
        self.assertEqual(len(self.lines('calls.jsonl')), 2)

    def test_review_fix_4_ok_without_the_configured_status_is_failed(self):
        run = self.run_object()
        self.write_sync(status='Backlog')
        self.control('no-status')
        result = run.sync_project('open')
        self.assertEqual((result['ok'], result['project_sync']['state']), (False, 'failed'))
        self.assertIn('ok issue=10 status=Backlog', result['project_sync']['summary'])
        self.assertIn('not the configured status', result['project_sync']['summary'])
        # In-progress accepts the in-review status Project advances to when a PR is open.
        self.control('review')
        result = run.sync_project('in-progress')
        self.assertEqual((result['ok'], result['project_sync']['state']), (True, 'done'))
        self.assertEqual(w.read(self.root / self.state_file)[self.slug]['status'], 'In review')

    def test_unknown_phase_is_refused(self):
        run = self.run_object()
        with self.assertRaisesRegex(w.WorkflowError, 'PROJECT_SYNC_PHASE_INVALID'):
            run.sync_project('shipping')

    def test_r2_runtime_sync_after_complete_keeps_specify_current(self):
        run = self.run_object()
        self.write_sync(status='Backlog')
        self.advance(run, 'specify', {'specify': self.depends_on_state('specify')})
        self.assertEqual(run.sync_project('open')['project_sync']['state'], 'done')
        self.assertEqual(run.next(run.load())['stage'], 'clarify')


class LeanOwnershipTests(Base):
    """R8 additions. Already covered elsewhere: coordinator stage start refusing before launch
    (test_lean_execution), wrong-token dispatch and completion (test_delegation), tier defaults
    (test_front_half_runtime)."""

    def test_r8_ready_and_pr_are_coordinator_mechanics_only_when_lean(self):
        cases = {'explicit lean': ({'enabled': True}, None, True),
                 'explicit legacy': ({'enabled': False}, 'lite', False),
                 'legacy default': (None, 'full', False),
                 'lite default': (None, 'lite', True), 'standard default': (None, 'standard', True)}
        for name, (config, tier, owned) in cases.items():
            policy = copy.deepcopy(self.policy)
            if config is not None:
                policy['lean_execution'] = config
            for stage in ('ready', 'pr'):
                with self.subTest(case=name, stage=stage):
                    self.assertEqual(lean_policy.coordinator_owned(policy, stage, {}, tier), owned)

    def test_r8_lean_ready_and_pr_claims_launch_no_model_and_refuse_a_foreign_token(self):
        self.policy['lean_execution'] = {'enabled': True}
        self.configure()
        run = self.run_object()
        self.advance(run, 'review')
        ready = run.claim(self.usage(), finalize=True)
        self.assertEqual((ready['stage'], ready['execution_owner']), ('ready', 'coordinator'))
        self.assertNotIn('delegation', ready)
        run.complete(ready['token'], self.receipt('ready'))
        claim = run.claim(self.usage(), finalize=True)
        self.assertEqual((claim['stage'], claim['execution_owner']), ('pr', 'coordinator'))
        self.assertIn('workflow.py project-sync', claim['project_sync']['command'])
        with self.assertRaisesRegex(w.WorkflowError, 'CLAIM_TOKEN_MISMATCH'):
            run.complete(ready['token'], self.receipt('pr'))  # a candidate bound to another claim
        delegated = copy.deepcopy(self.policy)
        delegated['delegation']['enabled'] = True
        with patch.object(w, 'load_policy', return_value=delegated), \
                patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith('SANDUQ_')},
                           clear=True), patch.object(dispatch, 'candidate_start') as launch:
            with self.assertRaisesRegex(Exception, 'COORDINATOR_OWNS_STAGE'):
                dispatch.start(self.root, self.feature, 'stage:pr', token=claim['token'])
        launch.assert_not_called()
        self.assertEqual(run.load()['active']['token'], claim['token'])


if __name__ == '__main__':
    unittest.main()
