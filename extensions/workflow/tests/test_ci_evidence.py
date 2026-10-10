"""CI verification runs read as evidence (workflow 1.6.0, B4): the A9a plan contract, no network."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_evidence as ce  # noqa: E402
import fake_github  # noqa: E402

REPOSITORY = 'example-org/booking-app'
PUSH_RUN, PR_RUN = 36334869932, 36333797874
# Recomputed by source_key.py from the recorded repository for tree 7d58f42 (the tree of both runs' heads), matching
# the artifacts' sourceKey; recorded so the tests need neither the repository nor the network.
TREE = '7d58f42d5a14cc94ca4f234bd7cd626090f94c57'
HEAD = '270dfb5e43e2a66a95ba3b5e12dc3d1c46b22891'
KEY = '23e9caebc5ffa4b40d64a61e36a6d7fd62b5b5efcb5a99747c2f4738b2c9cb3c'
LOCAL = {'tree': TREE, 'key': KEY}


class RecordedRunTests(unittest.TestCase):
    """Two real Bootstrap verification runs, recorded from the GitHub REST API."""

    def check(self, client, run_id, **options):
        evidence = ce.collect(client, REPOSITORY, run_id)
        return evidence, ce.validate(evidence, REPOSITORY, run_id, fake_github.CHECK, fake_github.WORKFLOW,
                                     local=options.pop('local', LOCAL), **options)

    def test_push_run_artifact_parses_and_validates_against_its_run(self):
        client = fake_github.recorded(PUSH_RUN)
        evidence, errors = self.check(client, PUSH_RUN)
        self.assertEqual(errors, [])
        plan = evidence['plan']
        self.assertEqual(evidence['artifact'], 'bootstrap-plan-36334869932-1')
        self.assertEqual((plan['event'], plan['tier'], plan['pullRequest']), ('push', 'merge', None))
        self.assertEqual((plan['headSha'], plan['headTreeSha'], plan['sourceKey']),
                         ('acd33dc27c168471b5979888a87178b62310a6ba', TREE, KEY))
        self.assertEqual(len(plan['lanes']), 45)
        self.assertEqual(plan['lanes'], sorted(set(plan['lanes'])))
        # Everything came through the REST endpoints of the contract, the artifact through its zip.
        self.assertIn('repos/example-org/booking-app/actions/artifacts/10936644522/zip', client.calls)

    def test_pull_request_run_shares_the_tree_and_key_of_its_merge(self):
        evidence, errors = self.check(fake_github.recorded(PR_RUN), PR_RUN)
        plan = evidence['plan']
        self.assertEqual((plan['event'], plan['tier'], plan['pullRequest']), ('pull_request', 'pr', 761))
        self.assertEqual((plan['headTreeSha'], plan['sourceKey']), (TREE, KEY))
        # GitHub empties a run's pull_requests once the PR merges; the recorded run no longer names PR 761, so the
        # pull requests whose head is still the run's head confirm it instead.
        self.assertEqual(errors, [])
        self.assertEqual(evidence['head_pulls'], [761])
        listed = fake_github.recorded(PR_RUN)
        listed.responses[f'repos/{REPOSITORY}/actions/runs/{PR_RUN}']['pull_requests'] = [{'number': 761}]
        self.assertEqual(self.check(listed, PR_RUN)[1], [])
        # A pull request whose head has moved on, or none at all, does not confirm the run.
        for pulls in ([{'number': 761, 'head': {'sha': 'f' * 40}}], []):
            moved = fake_github.recorded(PR_RUN)
            moved.responses[f'repos/{REPOSITORY}/commits/{HEAD}/pulls'] = pulls
            self.assertEqual(self.check(moved, PR_RUN)[1], ['pullRequest 761 is not a pull request of run 36333797874 (none).'])
        # The PR tier ran a subset of the merge tier's lanes on the same key.
        push = self.check(fake_github.recorded(PUSH_RUN), PUSH_RUN)[0]['plan']
        self.assertLess(set(plan['lanes']), set(push['lanes']))

    def test_negative_fixtures(self):
        runs = f'repos/{REPOSITORY}/actions/runs/{PUSH_RUN}'
        cases = {
            'cancelled': (lambda c: c.responses[runs].update(conclusion='cancelled'), 'was cancelled'),
            'in progress': (lambda c: c.responses[runs].update(status='in_progress', conclusion=None), 'has not completed'),
            'check failed': (lambda c: c.responses[f'{runs}/attempts/1/jobs?per_page=100']['jobs'][-1].update(
                conclusion='failure'), 'did not conclude success'),
            'missing artifact': (lambda c: c.responses[f'{runs}/artifacts?per_page=100&name=bootstrap-plan-{PUSH_RUN}-1']
                                 .update(artifacts=[]), 'no artifact'),
            'mismatched run': (lambda c: c.responses[runs].update(id=PUSH_RUN + 1), 'not 36334869932'),
            'wrong workflow': (lambda c: c.responses[runs].update(name='Other'), 'not Bootstrap verification'),
            'wrong head tree': (lambda c: c.responses[f'repos/{REPOSITORY}/git/commits/'
                                                      'acd33dc27c168471b5979888a87178b62310a6ba']['tree']
                                .update(sha='0' * 40), 'is not the tree of'),
        }
        for name, (tamper, message) in cases.items():
            with self.subTest(name):
                client = fake_github.recorded(PUSH_RUN)
                tamper(client)
                errors = self.check(client, PUSH_RUN)[1]
                self.assertTrue(any(message in error for error in errors), errors)
        with self.subTest('key does not match the local tree'):
            errors = self.check(fake_github.recorded(PUSH_RUN), PUSH_RUN, local={'tree': TREE, 'key': 'f' * 64})[1]
            self.assertTrue(any('does not match the key' in error for error in errors), errors)
        with self.subTest('named attempt that is not the latest'):
            errors = self.check(fake_github.recorded(PUSH_RUN), PUSH_RUN, attempt=2)[1]
            self.assertTrue(any('not 2' in error for error in errors), errors)

    def test_partial_rerun_is_covered_by_the_earlier_attempts_plan(self):
        # Attempt 2 re-ran only failed jobs, so it reused attempt 1's plan job and published no artifact of its own.
        runs = f'repos/{REPOSITORY}/actions/runs/{PUSH_RUN}'
        client = fake_github.recorded(PUSH_RUN)
        rerun = dict(client.responses[runs], run_attempt=2)
        client.responses[runs] = rerun
        client.responses[f'{runs}/attempts/2'] = rerun
        client.responses[f'{runs}/attempts/2/jobs?per_page=100'] = client.responses[f'{runs}/attempts/1/jobs?per_page=100']
        evidence, errors = self.check(client, PUSH_RUN)
        self.assertEqual(errors, [])
        self.assertEqual(evidence['artifact'], f'bootstrap-plan-{PUSH_RUN}-1')
        # With no plan at any attempt it still fails.
        client.responses[f'{runs}/artifacts?per_page=100&name=bootstrap-plan-{PUSH_RUN}-1']['artifacts'] = []
        errors = self.check(client, PUSH_RUN)[1]
        self.assertTrue(any('no artifact' in error for error in errors), errors)

    def test_unreadable_run_and_artifact(self):
        with self.assertRaises(ce.EvidenceError):
            ce.collect(fake_github.FakeGitHub(), REPOSITORY, PUSH_RUN)
        client = fake_github.recorded(PUSH_RUN)
        client.downloads = {key: b'not a zip' for key in client.downloads}
        evidence, errors = self.check(client, PUSH_RUN)
        self.assertIsNone(evidence['plan'])
        self.assertIn('verification-plan.json in bootstrap-plan-36334869932-1 is missing or unreadable.', errors)

    def test_plan_field_rules(self):
        head, tree = 'a' * 40, 'b' * 40
        base = dict(repository='acme/app', run_id=900, head=head, tree=tree, key='c' * 64, lanes=['unit'])
        mutations = {
            'unsorted lanes': ({'lanes': ['z', 'a']}, 'lanes is not a sorted list'),
            'key version': ({'keyVersion': 'other/1'}, 'keyVersion'),
            'short key': ({'sourceKey': 'abc'}, 'not a 64-hex key'),
            'repository': ({'repository': 'acme/other'}, 'repository'),
            'attempt': ({'runAttempt': 2}, 'runAttempt'),
        }
        for name, (overrides, message) in mutations.items():
            with self.subTest(name):
                client = fake_github.fake_run(base['repository'], base['run_id'], head, tree, base['key'],
                                              base['lanes'], plan_overrides=overrides)
                evidence = ce.collect(client, 'acme/app', 900)
                errors = ce.validate(evidence, 'acme/app', 900, fake_github.CHECK)
                self.assertTrue(any(message in error for error in errors), errors)
        client = fake_github.fake_run('acme/app', 900, head, tree, 'c' * 64, ['unit'])
        self.assertEqual(ce.validate(ce.collect(client, 'acme/app', 900), 'acme/app', 900, fake_github.CHECK), [])
        # The same run under another prefix is not found.
        evidence = ce.collect(copy.deepcopy(client), 'acme/app', 900, prefix='other-plan')
        self.assertIsNone(evidence['plan'])


if __name__ == '__main__':
    unittest.main()
