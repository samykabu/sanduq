"""Source-drift classification (B3) and checked revalidation from CI evidence (B4), workflow 1.6.0.

The two 007 failure shapes are reconstructed, anonymised, from the recorded gate failures of that feature
(`STALE_RECEIPT: verify` after commits that changed verification inputs, and after a commit that changed an
integration test); both end green through `revalidate`. The CI side is a fake GitHub client serving a plan
artifact that follows the A9a contract, so nothing here touches the network.
"""
import copy
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_gate as c  # noqa: E402
import source_key as sk  # noqa: E402
import workflow as w  # noqa: E402
import fake_github  # noqa: E402
import fixture_008  # noqa: E402
from test_receipt_contract import Harness, checkpoint_validator  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/workflow.py'
HOOK = '.specify/hooks/affected.py'
# The affected-lane rules of a Bunyan-like project, in the shape of `eng/ci/affected.mjs`: words and committed
# artifacts reach no lane; verification inputs, tests and product source do.
HOOK_SOURCE = '''import json, sys
def lanes(path):
    if path.lower().endswith('.md') or path.startswith('artifacts/'):
        return []
    if path.startswith(('.github/workflows/', 'eng/')):
        return ['backend-unit', 'projects-integration', 'web-chromium']
    if path.startswith('tests/App.IntegrationTests/Projects/'):
        return ['backend-unit', 'projects-integration']
    if path.startswith(('src/', 'tests/')):
        return ['backend-unit']
    return ['backend-unit', 'projects-integration', 'web-chromium']
paths = json.load(sys.stdin)
json.dump({'paths': {path: lanes(path) for path in paths}}, sys.stdout)
'''
ALL_LANES = ['backend-unit', 'projects-integration', 'web-chromium']
SOURCE = {
    'src/App.Api/Projects/ProjectEndpoints.cs': 'endpoints',
    'tests/App.IntegrationTests/Projects/ProjectsTests.cs': 'tests',
    '.github/workflows/verify.yml': 'on: pull_request',
    'eng/ci/isolation.mjs': 'isolation',
    'eng/images.lock.json': '{}',
    'eng/verification/adapters/dotnet.mjs': 'adapter',
    'README.md': 'words',
    'artifacts/report.json': '{}',
}
# 007, shape 1: the verification harness itself changed after Verify (workflow, CI scripts, image lock, adapters).
SHAPE_VERIFICATION_INPUTS = ['.github/workflows/verify.yml', 'eng/ci/isolation.mjs', 'eng/images.lock.json',
                             'eng/verification/adapters/dotnet.mjs']
# 007, shape 2: an integration test changed after Verify.
SHAPE_TEST_CHANGE = ['tests/App.IntegrationTests/Projects/ProjectsTests.cs']


class DriftHarness(Harness):
    hook = True
    check = True

    def setUp(self):
        super().setUp()
        self.policy = w.default_policy(False, False)
        gate = self.policy['ci']['gate']
        if self.hook:
            gate['affected_command'] = [sys.executable, HOOK]
        if self.check:
            gate['verification_check'] = {'name': fake_github.CHECK, 'workflow': fake_github.WORKFLOW}
        self.configure()
        self.write(HOOK, HOOK_SOURCE)
        for path, text in SOURCE.items():
            self.write(path, text)
        self.commit_all('Product source')
        self.run = self.run_object()
        self.complete_through(self.run, 'ready')
        self.commit_all('Record the workflow through Ready')
        self.recorded = copy.deepcopy(self.run.load()['receipts'])
        self.next_run = 500

    def head(self):
        return w.git(self.root, 'rev-parse', 'HEAD')

    def change(self, paths, message='Change'):
        for path in paths:
            self.write(path, (self.root / path).read_text(encoding='utf-8') + ' changed')
        self.commit_all(message)

    def gate(self, github=None):
        policy = w.load_policy(self.root)
        c.check_index(self.root, self.feature)
        return c.check(self.root, self.feature, policy, None, self.gate_rules(policy),
                       github=github or getattr(self, 'client', None))

    def status(self, stage):
        return w.receipt_status(self.root, self.feature, stage, self.run.load()['receipts'][stage], self.policy)

    def green_run(self, lanes=ALL_LANES, head=None, **options):
        """A successful verification run of `head` (default HEAD) with the given lanes."""
        head = head or self.head()
        self.next_run += 1
        client = fake_github.fake_run('acme/app', self.next_run, head, sk.tree_of(self.root, head),
                                      sk.source_key(self.root, head), lanes, **options)
        self.client = client
        return self.next_run, client

    def review_evidence(self, name='review-diff.md', base=None, head=None, blocking='0', diff_sha256=None,
                        reviewer='Reviewer A'):
        """A diff-review note; by default bound to the true hash of the reviewed diff."""
        base = base or self.run.load()['receipts']['review']['head']
        head = head or self.head()
        if diff_sha256 is None:
            diff_sha256 = w.diff_review_sha256(self.root, base, head)
        lines = ['# Incremental review', '', f'- **Diff reviewed:** `{base}..{head}`']
        if diff_sha256:
            lines.append(f'- **Diff sha256:** `{diff_sha256}`')
        if reviewer is not None:
            lines.append(f'- **Reviewer:** {reviewer}')
        lines += ['- Findings: none', f'- Blocking findings: {blocking}', '']
        return self.write(self.feature + '/evidence/' + name, '\n'.join(lines))

    def revalidate_all(self):
        run_id, client = self.green_run()
        verify = self.run.revalidate('verify', check_run=run_id, github=client)
        review = self.run.revalidate('review', diff_reviewed=self.review_evidence())
        ready = self.run.revalidate('ready')
        return verify, review, ready


class SourceDriftClassificationTests(DriftHarness):
    """B3: drifted source paths are classified through `ci.gate.affected_command`."""

    def test_source_stages_record_head_and_source_key(self):
        state = self.run.load()
        head = w.git(self.root, 'rev-parse', 'HEAD~1')  # the commit the receipts were recorded at
        for stage in w.SOURCE_STAGES:
            receipt = state['receipts'][stage]
            self.assertEqual(receipt['head'], head)
            self.assertEqual(receipt['source_key'], sk.source_key(self.root, head))
        for stage in ('execute', 'tasks'):
            self.assertNotIn('source_key', state['receipts'][stage])
        checkpoint_validator().validate(state)

    def test_markdown_and_artifact_drift_keeps_review_current(self):
        self.change(['README.md', 'artifacts/report.json'], 'Words and a committed report')
        for stage in w.SOURCE_STAGES:
            status = self.status(stage)
            self.assertEqual((status['current'], status.get('via')), (True, 'lane-free-drift'), stage)
            self.assertEqual(status['paths'], ['README.md', 'artifacts/report.json'])
        self.assertEqual(self.run.next(self.run.load())['status'], 'ready_to_finalize')
        result = self.gate()
        self.assertTrue(result['passed'])
        self.assertEqual([item['stage'] for item in result['accepted_drift']], list(w.SOURCE_STAGES))
        # Nothing was re-stamped: the recorded receipts are byte-for-byte what Ready left.
        self.assertEqual(self.run.load()['receipts'], self.recorded)

    def test_a_test_or_workflow_change_stales_review(self):
        for path in ('tests/App.IntegrationTests/Projects/ProjectsTests.cs', '.github/workflows/verify.yml'):
            with self.subTest(path):
                self.change([path])
                status = self.status('review')
                self.assertFalse(status['current'])
                self.assertEqual(status['rule'], 'affected-lanes')
                self.assertIn(path, status['lanes'])
                with self.assertRaisesRegex(w.WorkflowError, 'STALE_RECEIPT: verify.*drift reaching lanes'):
                    self.gate()
                subprocess.run(['git', 'revert', '--no-edit', 'HEAD'], cwd=self.root, check=True, capture_output=True)

    def test_a_mixed_commit_stales_even_with_lane_free_paths(self):
        self.change(['README.md', 'src/App.Api/Projects/ProjectEndpoints.cs'])
        status = self.status('ready')
        self.assertEqual(status['lanes'], {'src/App.Api/Projects/ProjectEndpoints.cs': ['backend-unit']})

    def test_hook_failure_stales(self):
        for name, source in (('exit', 'import sys; sys.exit(3)'), ('not json', 'print("lanes: none")'),
                             ('path left out', 'import json; json.dump({"paths": {}}, open(1, "w"))'),
                             ('wrong shape', 'import json; json.dump({"README.md": []}, open(1, "w"))'),
                             ('bad lanes', 'import json, sys; json.dump({"paths": {p: "none" for p in '
                                           'json.load(sys.stdin)}}, sys.stdout)')):
            with self.subTest(name):
                self.write(HOOK, source)
                self.change(['README.md'])
                status = self.status('review')
                self.assertEqual((status['current'], status['rule']), (False, 'classification-failed'))
                with self.assertRaisesRegex(w.WorkflowError, 'fails closed'):
                    self.gate()

    def test_a_drifted_explicit_fingerprint_stales(self):
        # README.md consulted by Review: its explicit hash is advisory, but as drifted source it still stales.
        state = self.run.load()
        receipt = state['receipts']['review']
        receipt['inputs'].append('README.md')
        receipt['input_roles'] = {'README.md': {'role': 'consulted', 'because': 'orientation only'}}
        receipt['fingerprints']['README.md'] = w.fingerprint_files(self.root, ['README.md'])['README.md']
        w.write(self.run.path, state)
        self.commit_all('Review consulted the README')
        self.change(['README.md'])
        status = self.status('review')
        self.assertEqual((status['current'], status['rule'], status['explicit']),
                         (False, 'explicit-fingerprint', ['README.md']))

    def test_a_legacy_receipt_without_source_key_keeps_the_identity_rule(self):
        state = self.run.load()
        for stage in w.SOURCE_STAGES:
            state['receipts'][stage].pop('source_key')
            state['receipts'][stage].pop('head')
        w.write(self.run.path, state)
        self.commit_all('A receipt written before 1.6.0')
        self.change(['README.md'])
        status = self.status('review')
        self.assertEqual((status['current'], status['rule']), (False, 'identity'))

    def test_dirty_source_at_completion_records_no_key(self):
        self.write('src/scratch.cs', 'uncommitted')
        run = self.run
        state = run.load()  # reopen Verify
        state['receipts'] = {k: v for k, v in state['receipts'].items() if k not in w.SOURCE_STAGES}
        w.write(run.path, state)
        claim = run.claim(self.usage())
        self.assertEqual(claim['stage'], 'verify')
        run.complete(claim['token'], self.receipt('verify'))
        receipt = run.load()['receipts']['verify']
        self.assertNotIn('source_key', receipt)
        self.assertNotIn('head', receipt)


class NoHookTests(DriftHarness):
    hook = False

    def test_without_a_hook_the_identity_rule_applies(self):
        self.change(['README.md'])
        status = self.status('review')
        self.assertEqual((status['current'], status['rule']), (False, 'identity'))
        with self.assertRaisesRegex(w.WorkflowError, 'STALE_RECEIPT: verify'):
            self.gate()

    def test_verify_revalidation_needs_the_hook_to_know_the_lanes(self):
        self.change(SHAPE_TEST_CHANGE)
        run_id, client = self.green_run()
        with self.assertRaisesRegex(w.WorkflowError, 'CI_AFFECTED_COMMAND_REQUIRED'):
            self.run.revalidate('verify', check_run=run_id, github=client)

    def test_gate_accepts_verify_through_ci_evidence_on_the_same_source_key(self):
        """After a revalidation, a Markdown-only commit keeps Verify current through its CI run."""
        self.policy['ci']['gate']['affected_command'] = [sys.executable, HOOK]
        self.configure()
        self.run = w.Run(self.root, self.feature)
        self.change(SHAPE_TEST_CHANGE)
        self.revalidate_all()
        self.commit_all('Revalidated')
        self.policy['ci']['gate'].pop('affected_command')
        self.configure()
        self.run = w.Run(self.root, self.feature)
        self.commit_all('Drop the hook')
        self.change(['README.md'])
        verify = self.status('verify')
        self.assertEqual((verify['current'], verify['via']), (True, 'ci-evidence'))
        with self.assertRaisesRegex(w.WorkflowError, 'STALE_RECEIPT: review'):
            self.gate()
        # A source change moves the key: the CI run no longer covers Verify.
        self.change(['src/App.Api/Projects/ProjectEndpoints.cs'])
        self.assertFalse(self.status('verify')['current'])


class PolicyChangedRecipeTests(DriftHarness):
    hook = False

    def test_policy_changed_names_the_migration(self):
        state = self.run.load()
        state['policy_digest'] = '0' * 64
        w.write(self.run.path, state)
        self.commit_all('A policy recorded by another release')
        with self.assertRaisesRegex(w.WorkflowError, r'POLICY_CHANGED: recovery: .*migrate --feature '
                                    + self.feature + ' --preview'):
            self.gate()


class RevalidateFrom007Tests(DriftHarness):
    """B4: both 007 failure shapes end green through revalidate; nothing is re-stamped on a note."""

    def assert_end_to_end(self, shape):
        self.change(shape, 'Post-Verify change')
        with self.assertRaises(w.WorkflowError) as failure:
            self.gate()
        message = str(failure.exception)
        self.assertIn('STALE_RECEIPT: verify', message)
        self.assertIn('revalidate --feature ' + self.feature + ' --stage verify --check-run <run id>', message)
        nxt = self.run.next(self.run.load())
        self.assertEqual(nxt['stage'], 'verify')
        self.assertTrue(any('--check-run' in step for step in nxt['recovery']))

        verify, review, ready = self.revalidate_all()
        state = self.run.load()
        head, key = self.head(), sk.source_key(self.root)
        evidence = state['receipts']['verify']['ci_evidence']
        self.assertEqual({k: evidence[k] for k in ('run_id', 'head', 'source_key', 'tier', 'conclusion')},
                         {'run_id': verify['revalidation']['run_id'], 'head': head, 'source_key': key, 'tier': 'pr',
                          'conclusion': 'success'})
        self.assertEqual(evidence['lanes'], ALL_LANES)
        self.assertLessEqual(set(evidence['required_lanes']), set(evidence['lanes']))
        self.assertTrue(evidence['required_lanes'])
        for stage in w.SOURCE_STAGES:
            receipt, before = state['receipts'][stage], self.recorded[stage]
            self.assertEqual((receipt['head'], receipt['source_key']), (head, key))
            self.assertEqual(receipt['source_fingerprints'], w.source_fingerprints(self.root))
            self.assertEqual(receipt['blocking_findings'], 0)
            self.assertEqual(receipt['summary'], before['summary'])
            self.assertEqual(receipt['revalidations'][-1]['outcome'], 'current')
            self.assertEqual(sorted(receipt['revalidations'][-1]['drift']), sorted(shape))
            # Explicit fingerprints keep their recorded hashes; Review only gains its diff-review evidence.
            added = {p: h for p, h in receipt['fingerprints'].items() if p not in before['fingerprints']}
            self.assertEqual({p: receipt['fingerprints'][p] for p in before['fingerprints']}, before['fingerprints'])
            self.assertEqual(list(added), [self.feature + '/evidence/review-diff.md'] if stage == 'review' else [])
        self.assertEqual(state['receipts']['review']['diff_reviewed']['base'], self.recorded['review']['head'])
        self.assertIn('tasks', ready['revalidation']['checks'])
        checkpoint_validator().validate(state)
        self.commit_all('Revalidated Verify, Review and Ready')  # an operational commit: the key does not move
        self.assertEqual(sk.source_key(self.root), key)
        result = self.gate()
        self.assertTrue(result['passed'])
        self.assertEqual([item['via'] for item in result['revalidations']],
                         ['check-run', 'diff-review', 'ready-checks'])

    def test_007_verification_input_drift_ends_green(self):
        self.assert_end_to_end(SHAPE_VERIFICATION_INPUTS)

    def test_007_test_change_ends_green(self):
        self.assert_end_to_end(SHAPE_TEST_CHANGE)

    def test_a_narrower_check_leaves_verify_stale_until_a_covering_run(self):
        self.change(SHAPE_VERIFICATION_INPUTS)
        run_id, client = self.green_run(lanes=['backend-unit'])
        result = self.run.revalidate('verify', check_run=run_id, github=client)
        self.assertFalse(result['revalidated'])
        self.assertEqual(result['lane_gap'], ['projects-integration', 'web-chromium'])
        receipt = self.run.load()['receipts']['verify']
        self.assertEqual(receipt['stale']['reason'], 'ci-lane-gap')
        self.assertNotIn('ci_evidence', receipt)
        self.assertEqual(receipt['source_fingerprints'], self.recorded['verify']['source_fingerprints'])
        self.assertEqual(receipt['revalidations'][-1]['outcome'], 'stale')
        checkpoint_validator().validate(self.run.load())
        self.commit_all('Record the lane gap')
        with self.assertRaisesRegex(w.WorkflowError, 'lane gap of run 501: projects-integration, web-chromium'):
            self.gate()
        self.assertTrue(any('covering lanes projects-integration, web-chromium' in step
                            for step in self.run.next(self.run.load())['recovery']))
        # Review cannot move ahead of a stale Verify.
        with self.assertRaisesRegex(w.WorkflowError, 'EARLIER_STAGE_NOT_CURRENT: verify'):
            self.run.revalidate('review', diff_reviewed=self.review_evidence())
        run_id, client = self.green_run()
        result = self.run.revalidate('verify', check_run=run_id, github=client)
        self.assertTrue(result['revalidated'] and result['current'])
        self.assertNotIn('stale', self.run.load()['receipts']['verify'])

    def test_run_on_other_source_or_failed_is_rejected_and_nothing_changes(self):
        self.change(SHAPE_TEST_CHANGE)
        before = self.run.path.read_bytes()
        old_head = w.git(self.root, 'rev-parse', 'HEAD~1')
        cases = {
            'older source': (self.green_run(head=old_head), 'not the current'),
            'check failed': (self.green_run(check_conclusion='failure'), 'did not conclude success'),
            'cancelled': (self.green_run(conclusion='cancelled'), 'was cancelled'),
            'no artifact': (self.green_run(artifact=False), 'no artifact'),
            'wrong PR': (self.green_run(plan_overrides={'pullRequest': 99}), 'pullRequest 99'),
            'forged key': (self.green_run(plan_overrides={'sourceKey': 'e' * 64}), 'does not match the key'),
        }
        for name, ((run_id, client), message) in cases.items():
            with self.subTest(name):
                with self.assertRaisesRegex(w.WorkflowError, 'CHECK_RUN_REJECTED.*' + message):
                    self.run.revalidate('verify', check_run=run_id, github=client)
                self.assertEqual(self.run.path.read_bytes(), before)

    def test_never_restamped_on_a_note(self):
        self.change(SHAPE_TEST_CHANGE)
        with self.assertRaisesRegex(w.WorkflowError, 'REVALIDATE_VERIFY_NEEDS_CHECK_RUN'):
            self.run.revalidate('verify', reason='the tests pass on my machine')
        with self.assertRaisesRegex(w.WorkflowError, 'REVALIDATE_STAGE_UNSUPPORTED'):
            self.run.revalidate('execute', reason='fine')
        run_id, client = self.green_run()
        self.run.revalidate('verify', check_run=run_id, github=client)
        with self.assertRaisesRegex(w.WorkflowError, 'REVALIDATE_REVIEW_NEEDS_DIFF_REVIEW'):
            self.run.revalidate('review', reason='looked at it')

    def test_review_revalidation_without_a_diff_review_is_refused(self):
        self.change(SHAPE_TEST_CHANGE)
        run_id, client = self.green_run()
        self.run.revalidate('verify', check_run=run_id, github=client)
        before = self.run.path.read_bytes()
        review_head = self.run.load()['receipts']['review']['head']
        cases = {
            'no range': (self.write(self.feature + '/evidence/note.md', 'Looks fine.\nBlocking findings: 0\n'),
                         'DIFF_REVIEW_RANGE_MISSING'),
            'another range': (self.review_evidence('old.md', base='1234567', head='89abcde', diff_sha256='f' * 64),
                              'DIFF_REVIEW_RANGE_MISSING'),
            'blocking findings': (self.review_evidence('blocking.md', blocking='2'), 'DIFF_REVIEW_OUTCOME_MISSING'),
            'outside the feature': (self.write('notes/review.md', f'Diff reviewed: {review_head}..{self.head()}\n'
                                                                  'Blocking findings: 0\n'),
                                    'DIFF_REVIEW_EVIDENCE_OUTSIDE_FEATURE'),
            'missing file': (self.feature + '/evidence/absent.md', 'EVIDENCE_MISSING'),
        }
        for name, (path, error) in cases.items():
            with self.subTest(name):
                with self.assertRaisesRegex(w.WorkflowError, error):
                    self.run.revalidate('review', diff_reviewed=path)
                self.assertEqual(self.run.path.read_bytes(), before)
        with self.assertRaisesRegex(w.WorkflowError, 'EARLIER_STAGE_NOT_CURRENT: review'):
            self.run.revalidate('ready')

    def test_explicit_evidence_drift_is_never_revalidated(self):
        self.change(SHAPE_TEST_CHANGE)
        self.write(self.feature + '/evidence/verify.txt', 'edited evidence')
        self.commit_all('Edit Verify evidence')
        run_id, client = self.green_run()
        with self.assertRaisesRegex(w.WorkflowError, 'EXPLICIT_FINGERPRINTS_CHANGED.*amend --feature'):
            self.run.revalidate('verify', check_run=run_id, github=client)

    def test_uncommitted_source_and_current_receipts_are_refused(self):
        run_id, client = self.green_run()
        with self.assertRaisesRegex(w.WorkflowError, 'REVALIDATION_NOT_NEEDED'):
            self.run.revalidate('verify', check_run=run_id, github=client)
        self.change(SHAPE_TEST_CHANGE)
        self.write('src/wip.cs', 'work in progress')
        with self.assertRaisesRegex(w.WorkflowError, 'SOURCE_TREE_DIRTY: .*src/wip.cs'):
            self.run.revalidate('verify', check_run=run_id, github=client)

    def test_an_unset_verification_check_is_refused(self):
        self.policy['ci']['gate'].pop('verification_check')
        self.configure()
        self.commit_all('No verification check')
        self.change(SHAPE_TEST_CHANGE)
        run_id, client = self.green_run()
        with self.assertRaisesRegex(w.WorkflowError, 'CI_VERIFICATION_CHECK_UNSET'):
            w.Run(self.root, self.feature).revalidate('verify', check_run=run_id, github=client)

    def test_gate_rechecks_ci_evidence_through_the_api_when_asked(self):
        self.change(SHAPE_TEST_CHANGE)
        run_id, client = self.green_run()
        self.run.revalidate('verify', check_run=run_id, github=client)
        self.run.revalidate('review', diff_reviewed=self.review_evidence())
        self.run.revalidate('ready')
        self.commit_all('Revalidated')
        self.change(['README.md'])  # Verify now rests on its CI run (same key)
        policy = w.load_policy(self.root)
        rules = self.gate_rules(policy)
        result = c.check(self.root, self.feature, policy, None, rules, verify_ci_evidence=True, github=client)
        self.assertIn({'stage': 'verify', 'via': 'ci-evidence', 'drift': ['README.md'], 'run_id': run_id},
                      result['accepted_drift'])
        client.responses[f'repos/acme/app/actions/runs/{run_id}']['conclusion'] = 'cancelled'
        with self.assertRaisesRegex(w.WorkflowError, 'CI_EVIDENCE_REJECTED: verify'):
            c.check(self.root, self.feature, policy, None, rules, verify_ci_evidence=True, github=client)


class CiEvidenceIntegrityTests(DriftHarness):
    """1.6.1: a committed `ci_evidence` is never trusted on its own (fail closed)."""

    def accept_through_ci_evidence(self):
        self.change(SHAPE_TEST_CHANGE)
        self.revalidate_all()
        self.commit_all('Revalidated')
        self.change(['README.md'])  # Verify now rests on its CI run (same key)
        status = self.status('verify')
        self.assertEqual((status['current'], status['via']), (True, 'ci-evidence'))
        return self.run.load()['receipts']['verify']

    def rerun(self, receipt, **options):
        """The recorded run served again, with its responses changed by `options`."""
        evidence = receipt['ci_evidence']
        head = evidence['head']
        return fake_github.fake_run('acme/app', evidence['run_id'], head, sk.tree_of(self.root, head),
                                    options.pop('key', evidence['source_key']), ALL_LANES, **options)

    def test_a_partial_or_forged_ci_evidence_is_not_current(self):
        receipt = self.accept_through_ci_evidence()
        self.assertTrue(w.ci_evidence_current(self.root, receipt))
        evidence = receipt['ci_evidence']
        # The reviewed forgery: only the conclusion and the current source key.
        forged = {**receipt, 'ci_evidence': {'conclusion': 'success', 'source_key': evidence['source_key']}}
        self.assertFalse(w.ci_evidence_current(self.root, forged))
        status = w.receipt_status(self.root, self.feature, 'verify', forged, self.policy)
        self.assertNotEqual(status.get('via'), 'ci-evidence')
        for field in ('run_id', 'attempt', 'head', 'source_key', 'tier', 'lanes', 'required_lanes', 'conclusion',
                      'lane_gap'):
            with self.subTest(missing=field):
                partial = {key: value for key, value in evidence.items() if key != field}
                self.assertFalse(w.ci_evidence_current(self.root, {**receipt, 'ci_evidence': partial}))
        malformed = {
            'run_id as a string': {'run_id': str(evidence['run_id'])},
            'run_id zero': {'run_id': 0},
            'run_id boolean': {'run_id': True},
            'attempt zero': {'attempt': 0},
            'short head': {'head': evidence['head'][:12]},
            'head not of this branch': {'head': 'f' * 40},
            'short source key': {'source_key': evidence['source_key'][:63]},
            'empty tier': {'tier': ' '},
            'lanes as a string': {'lanes': 'backend-unit'},
            'lanes not strings': {'lanes': [1]},
            'required_lanes not strings': {'required_lanes': [None]},
            'required lane not run': {'required_lanes': ['web-other']},
            'failed conclusion': {'conclusion': 'failure'},
            'lane gap': {'lane_gap': ['web-chromium']},
            'lane gap null': {'lane_gap': None},
        }
        for name, change in malformed.items():
            with self.subTest(malformed=name):
                self.assertFalse(w.ci_evidence_current(self.root, {**receipt, 'ci_evidence': {**evidence, **change}}))
        self.assertFalse(w.ci_evidence_current(self.root, {k: v for k, v in receipt.items() if k != 'head'}))

    def test_a_run_on_an_ancestor_with_the_same_key_stays_current(self):
        receipt = self.accept_through_ci_evidence()
        moved = {**receipt, 'head': self.head()}  # the run's head is now an ancestor of the receipt's head
        self.assertNotEqual(moved['head'], receipt['ci_evidence']['head'])
        self.assertTrue(w.ci_evidence_current(self.root, moved))

    def test_the_gate_always_rereads_the_run(self):
        receipt = self.accept_through_ci_evidence()
        run_id = receipt['ci_evidence']['run_id']
        self.client.calls.clear()
        result = self.gate()  # no flag
        self.assertIn({'stage': 'verify', 'via': 'ci-evidence', 'drift': ['README.md'], 'run_id': run_id},
                      result['accepted_drift'])
        self.assertIn(f'repos/acme/app/actions/runs/{run_id}', self.client.calls)
        cases = {
            'check failed': (self.rerun(receipt, check_conclusion='failure'), 'CI_EVIDENCE_REJECTED: verify'),
            'run cancelled': (self.rerun(receipt, conclusion='cancelled'), 'CI_EVIDENCE_REJECTED: verify'),
            'key differs': (self.rerun(receipt, plan_overrides={'sourceKey': 'e' * 64}),
                            'CI_EVIDENCE_REJECTED: verify'),
            'artifact gone': (self.rerun(receipt, artifact=False), 'CI_EVIDENCE_REJECTED: verify'),
        }
        for name, (client, error) in cases.items():
            with self.subTest(name):
                with self.assertRaisesRegex(w.WorkflowError, error):
                    self.gate(github=client)

    def test_the_gate_fails_closed_when_the_run_cannot_be_read(self):
        self.accept_through_ci_evidence()

        class Broken(fake_github.FakeGitHub):
            def api(self, endpoint):
                raise OSError('gh: command not found')

        for name, client in {'HTTP error': fake_github.FakeGitHub(), 'no gh': Broken()}.items():
            with self.subTest(name):
                with self.assertRaisesRegex(w.WorkflowError, 'CI_EVIDENCE_UNREADABLE: verify.*actions: read'):
                    self.gate(github=client)

    def test_the_gate_fails_closed_without_a_verification_check(self):
        self.accept_through_ci_evidence()
        self.policy['ci']['gate'].pop('verification_check')
        self.configure()
        self.commit_all('Drop the verification check')
        with self.assertRaisesRegex(w.WorkflowError, 'CI_VERIFICATION_CHECK_UNSET'):
            self.gate()

    def test_the_command_line_flag_is_still_accepted(self):
        receipt = self.accept_through_ci_evidence()
        policy = w.load_policy(self.root)
        rules = self.gate_rules(policy)
        for flag in (True, False):
            with self.subTest(verify_ci_evidence=flag):
                with self.assertRaisesRegex(w.WorkflowError, 'CI_EVIDENCE_REJECTED'):
                    c.check(self.root, self.feature, policy, None, rules, verify_ci_evidence=flag,
                            github=self.rerun(receipt, check_conclusion='failure'))


class DiffReviewBindingTests(DriftHarness):
    """1.6.1: a diff-review note is bound to the exact diff (`Diff sha256:`) and names its reviewer."""

    def setUp(self):
        super().setUp()
        self.base = self.run.load()['receipts']['review']['head']
        self.change(SHAPE_TEST_CHANGE, 'First source change')
        self.first = self.head()
        # Words, an excluded prefix and an upper-case Markdown file drift too; none of them is source.
        self.write('docs/notes.txt', 'words')
        self.write('guide/INTRO.MD', 'words')
        self.change(['src/App.Api/Projects/ProjectEndpoints.cs', 'README.md'], 'Second source change')
        run_id, client = self.green_run()
        self.run.revalidate('verify', check_run=run_id, github=client)
        self.before = self.run.path.read_bytes()

    def independent_hash(self, base, head):
        """The diff of exactly the source-key paths, listed explicitly instead of through the pathspec."""
        names = subprocess.run(['git', 'diff-tree', '-r', '--name-only', '-z', '--no-renames', base, head],
                               cwd=self.root, capture_output=True, check=True).stdout.split(b'\0')
        paths = [name.decode() for name in names if name and sk.is_source_path(name)]
        self.assertEqual(sorted(paths), sorted(['src/App.Api/Projects/ProjectEndpoints.cs', SHAPE_TEST_CHANGE[0]]))
        diff = subprocess.run(['git', '-c', 'core.quotePath=true', 'diff-tree', '-r', '-p', '--binary',
                               '--no-renames', base, head, '--', *paths], cwd=self.root, capture_output=True,
                              check=True).stdout
        return hashlib.sha256(diff).hexdigest()

    def test_the_correct_hash_is_accepted(self):
        expected = self.independent_hash(self.base, self.head())
        self.assertEqual(w.diff_review_sha256(self.root, self.base, self.head()), expected)
        result = self.run.revalidate('review', diff_reviewed=self.review_evidence())
        self.assertTrue(result['revalidated'])
        recorded = self.run.load()['receipts']['review']['diff_reviewed']
        self.assertEqual((recorded['diff_sha256'], recorded['reviewer']), (expected, 'Reviewer A'))
        checkpoint_validator().validate(self.run.load())

    def test_a_stale_or_wrong_hash_is_refused(self):
        cases = {
            'stale (an earlier head)': w.diff_review_sha256(self.root, self.base, self.first),
            'wrong': '0' * 64,
        }
        for name, value in cases.items():
            with self.subTest(name):
                with self.assertRaises(w.WorkflowError) as failure:
                    self.run.revalidate('review', diff_reviewed=self.review_evidence(diff_sha256=value))
                message = str(failure.exception)
                self.assertIn('DIFF_REVIEW_HASH_MISMATCH', message)
                self.assertIn(w.diff_review_shell(self.base, self.head()) + ' | sha256sum', message)
                self.assertEqual(self.run.path.read_bytes(), self.before)

    def test_a_missing_hash_or_reviewer_is_refused(self):
        cases = {
            'no hash': ({'diff_sha256': ''}, 'DIFF_REVIEW_HASH_MISSING.*diff-tree.*sha256sum'),
            'no reviewer line': ({'reviewer': None}, 'DIFF_REVIEW_REVIEWER_MISSING'),
            'empty reviewer': ({'reviewer': ''}, 'DIFF_REVIEW_REVIEWER_MISSING'),
        }
        for name, (options, error) in cases.items():
            with self.subTest(name):
                with self.assertRaisesRegex(w.WorkflowError, error):
                    self.run.revalidate('review', diff_reviewed=self.review_evidence(**options))
                self.assertEqual(self.run.path.read_bytes(), self.before)

    def test_the_recovery_recipe_names_the_hash_command(self):
        recovery = ' '.join(self.run.next(self.run.load())['recovery'])
        for part in ('Diff sha256: <hash>', 'Reviewer: <who reviewed it>',
                     w.diff_review_shell(self.base, 'HEAD') + ' | sha256sum'):
            self.assertIn(part, recovery)


class PolicyKeyTests(Harness):
    def test_gate_keys_are_validated(self):
        valid = [({'affected_command': 'node eng/ci/affected.mjs --paths-json'},
                  ['node', 'eng/ci/affected.mjs', '--paths-json']),
                 ({'affected_command': ['node', 'x.mjs']}, ['node', 'x.mjs'])]
        for keys, argv in valid:
            gate = {**w.default_policy(False, False)['ci']['gate'], **keys}
            self.assertEqual(w.sanduq_ci.affected_command(w.sanduq_ci.validate_gate(gate)), argv)
        self.assertEqual(w.sanduq_ci.verification_check({'verification_check': 'Bootstrap required lanes'}),
                         {'name': 'Bootstrap required lanes', 'workflow': None, 'artifact_prefix': 'bootstrap-plan'})
        for keys, error in (({'affected_command': []}, 'CI_AFFECTED_COMMAND_INVALID'),
                            ({'affected_command': ['node', '']}, 'CI_AFFECTED_COMMAND_INVALID'),
                            ({'affected_command': 'node "unclosed'}, 'CI_AFFECTED_COMMAND_INVALID'),
                            ({'verification_check': ''}, 'CI_VERIFICATION_CHECK_INVALID'),
                            ({'verification_check': {'workflow': 'x'}}, 'CI_VERIFICATION_CHECK_INVALID'),
                            ({'verification_check': {'name': 'x', 'extra': 1}}, 'CI_VERIFICATION_CHECK_INVALID'),
                            ({'verification_check': {'name': 'x', 'artifact_prefix': '../x'}},
                             'CI_VERIFICATION_CHECK_INVALID')):
            with self.subTest(keys):
                policy = w.default_policy(False, False)
                policy['ci']['gate'].update(keys)
                with self.assertRaisesRegex(w.WorkflowError, error):
                    w.validate_policy(policy)

    def test_policy_schema_accepts_the_keys_and_they_do_not_move_the_digest(self):
        from jsonschema import Draft202012Validator
        schema = json.loads((SCRIPT.parents[1] / 'schemas/policy-v1.schema.json').read_text(encoding='utf-8'))
        policy = w.default_policy(True, True)
        before = w.delivery_digest(policy)
        policy['ci']['gate'].update(affected_command=['node', 'eng/ci/affected.mjs', '--paths-json'],
                                    verification_check='Bootstrap required lanes')
        Draft202012Validator(schema).validate(json.loads(json.dumps(policy)))
        self.assertEqual(w.delivery_digest(policy), before)
        policy['ci']['gate']['affected_command'] = []
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(json.loads(json.dumps(policy)))))

    def test_ci_command_sets_and_removes_the_keys(self):
        run = lambda *args: subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), 'ci', *args],  # noqa: E731
                                           capture_output=True, text=True, encoding='utf-8')
        result = run('--affected-command', 'node eng/ci/affected.mjs --paths-json',
                     '--verification-check', 'Bootstrap required lanes')
        gate = json.loads(result.stdout)['ci']['gate']
        self.assertEqual((gate['affected_command'], gate['verification_check']),
                         ('node eng/ci/affected.mjs --paths-json', 'Bootstrap required lanes'))
        saved = yaml.safe_load((self.root / '.specify/workflow.yml').read_text(encoding='utf-8'))['ci']['gate']
        self.assertEqual(saved['verification_check'], 'Bootstrap required lanes')
        run('--affected-command', 'none')
        saved = yaml.safe_load((self.root / '.specify/workflow.yml').read_text(encoding='utf-8'))['ci']['gate']
        self.assertNotIn('affected_command', saved)
        self.assertIn('verification_check', saved)


class CommandLineRevalidateTests(DriftHarness):
    def test_revalidate_command_refuses_without_evidence(self):
        self.change(SHAPE_TEST_CHANGE)
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), 'revalidate',
                                 '--feature', self.feature, '--stage', 'review', '--reason', 'looks fine'],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1)
        self.assertIn('REVALIDATE_REVIEW_NEEDS_DIFF_REVIEW', json.loads(result.stdout)['error'])


class Legacy008Tests(Harness):
    """The anonymised 1.3.0 checkpoint of 008: legacy receipts (no head, no source key) against a fake artifact."""

    def setUp(self):
        super().setUp()
        self.policy = copy.deepcopy(fixture_008.load()['policy'])
        self.policy['ci']['gate'].update(affected_command=[sys.executable, HOOK],
                                         verification_check=fake_github.CHECK)
        self.configure(superspec=True)
        self.write(HOOK, HOOK_SOURCE)
        subprocess.run(['git', 'switch', '-qc', fixture_008.BRANCH], cwd=self.root, check=True)
        self.original = fixture_008.materialise(self.root)
        self.feature = fixture_008.FEATURE
        self.commit_all('Materialise the anonymised 1.3.0 checkpoint')
        self.run = w.Run(self.root, self.feature)
        self.run.migrate('workflow 1.6.0')
        self.commit_all('Migrate to 1.6.0')
        self.source = next(p for p in self.original['receipts']['verify']['source_fingerprints']
                           if p.startswith('src/'))

    def gate(self):
        policy = w.load_policy(self.root)
        c.check_index(self.root, self.feature)
        return c.check(self.root, self.feature, policy, None, self.gate_rules(policy))

    def test_008_shape_amend_then_revalidate_verify_against_a_fake_artifact(self):
        # The recorded 008 failure: an editorial edit of evidence shared by Execute and Review.
        evidence = self.root / fixture_008.AMENDED_EVIDENCE
        evidence.write_bytes(evidence.read_bytes() + b'One more word.\n')
        self.commit_all('Editorial fix')
        with self.assertRaises(w.WorkflowError) as failure:
            self.gate()
        self.assertIn('STALE_RECEIPT: execute', str(failure.exception))
        self.assertIn('amend --feature ' + self.feature + ' --stage execute --evidence ' +
                      fixture_008.AMENDED_EVIDENCE, str(failure.exception))
        # A CI run proves nothing about explicit evidence: revalidation refuses and names the amendment.
        (self.root / self.source).write_text('changed source', encoding='utf-8')
        self.commit_all('Source change after Verify')
        head = w.git(self.root, 'rev-parse', 'HEAD')
        client = fake_github.fake_run('acme/app', 777, head, sk.tree_of(self.root, head),
                                      sk.source_key(self.root, head), ALL_LANES)
        with self.assertRaisesRegex(w.WorkflowError, 'EARLIER_STAGE_NOT_CURRENT: execute.*amend --feature'):
            self.run.revalidate('verify', check_run=777, github=client)
        for stage in ('execute', 'review'):
            self.run.amend(stage, fixture_008.AMENDED_EVIDENCE, 'Editorial fix', 'unchanged', actor='fixture')
        verify = self.run.load()['receipts']['verify']
        self.assertNotIn('source_key', verify)  # legacy: the identity rule decides until it is revalidated
        result = self.run.revalidate('verify', check_run=777, github=client)
        self.assertTrue(result['current'])
        saved = self.run.load()['receipts']['verify']
        self.assertEqual(saved['ci_evidence']['required_lanes'], ['backend-unit'])
        self.assertEqual(saved['fingerprints'], self.original['receipts']['verify']['fingerprints'])
        self.assertEqual((saved['head'], saved['source_key']), (head, sk.source_key(self.root, head)))
        # Legacy Review records no head to diff from, so it is re-recorded rather than revalidated.
        self.write(self.feature + '/evidence/review-diff.md', 'Diff reviewed: 0000000..' + head + '\n'
                   'Blocking findings: 0\n')
        with self.assertRaisesRegex(w.WorkflowError, 'RECEIPT_HEAD_UNKNOWN'):
            self.run.revalidate('review', diff_reviewed=self.feature + '/evidence/review-diff.md')
        self.commit_all('Amended and revalidated Verify')
        with self.assertRaisesRegex(w.WorkflowError, 'STALE_RECEIPT: review.*recovery: .*claim --feature'):
            self.gate()
        checkpoint_validator().validate(self.run.load())


if __name__ == '__main__':
    unittest.main()
