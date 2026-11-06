"""PH-06-T01: the claim's invalidation preview and the receipts an unused claim gets back (#109, #112, #114).

Each scenario replays its issue's sequence on the current source: a later receipt is never lost when the claim that
removed it did no work, and a real change still invalidates.
"""
import copy
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_gate as c  # noqa: E402
import lifecycle  # noqa: E402
import workflow as w  # noqa: E402
import lifecycle_snapshot  # noqa: E402
from test_receipt_contract import Harness, checkpoint_validator  # noqa: E402

LATER = ['verify', 'review', 'ready']


class RetentionHarness(Harness):
    def ready(self, before=None):
        self.policy = w.default_policy(False, False)
        self.configure()

        def build():
            if before:
                before()
            run = self.run_object()
            self.complete_through(run, 'ready')
            self.commit_all()
            return run
        return lifecycle_snapshot.reuse(self, build, lambda: w.Run(self.root, self.feature), key=bool(before))

    def recover(self, run, token):
        return run.release_ownership(token, 'claim not used', force_live_owner='test: owner gone')

    def gate(self):
        policy = w.load_policy(self.root)
        return c.check(self.root, self.feature, policy, None, self.gate_rules(policy))

    def accepted_after(self, run, claim_id):
        events = lifecycle.read_events(run.feature / 'workflow/lifecycle.jsonl')[0]
        start = next(i for i, e in enumerate(events) if e['event'] == 'claim' and e['claim_id'] == claim_id)
        return [e for e in events[start:] if e['event'] in ('accepted', 'rejected-completion')]


class InvalidationPreviewTests(RetentionHarness):
    """#112: before acting, claim lists every receipt it would remove and why."""

    def test_preview_names_each_receipt_its_cause_and_writes_nothing(self):
        run = self.ready()
        path = self.write(self.feature + '/evidence/execute.txt', 'administrative state changed')
        raw = run.path.read_bytes()
        pending = run.claim(self.usage())
        self.assertEqual(run.path.read_bytes(), raw)  # nothing written before confirmation
        self.assertEqual((pending['status'], pending['stage'], pending['invalidates']),
                         ('confirm_invalidation', 'execute', LATER))
        why = {item['stage']: item for item in pending['invalidation']}
        self.assertEqual(list(why), ['execute', *LATER])
        self.assertEqual((why['execute']['current'], why['execute']['why'], why['execute']['paths']),
                         (False, 'stale: explicit-drift', [path]))
        for stage in LATER:
            self.assertTrue(why[stage]['current'], why[stage])
            self.assertEqual(why[stage]['why'], 'current; removed only because it follows execute')
            self.assertTrue(why[stage]['completed_at'])


class Issue112Tests(RetentionHarness):
    """An administrative dependency of an earlier stage changes; the replacement claim is recovered unused."""

    def stale_execute_claim(self):
        run = self.ready()
        before = copy.deepcopy(run.load()['receipts'])
        self.write(self.feature + '/evidence/execute.txt', 'administrative state changed')
        claim = run.claim(self.usage(), confirm_invalidation=True)
        self.assertEqual((claim['stage'], claim['invalidated']), ('execute', ['execute', *LATER]))
        self.assertNotIn('retained', claim)  # the removed receipts stay in the checkpoint, not in the output
        self.assertFalse({'execute', *LATER} & set(run.load()['receipts']))
        return run, claim, before

    def test_unused_claim_gets_every_receipt_back_and_stale_stays_stale(self):
        run, claim, before = self.stale_execute_claim()
        result = self.recover(run, claim['token'])
        self.assertEqual(result['retained'], {'restored': ['execute', *LATER]})
        state = run.load()
        self.assertEqual(state['receipts'], before)  # byte-for-byte the accepted receipts, nothing re-stamped
        self.assertEqual(state['recoveries'][-1]['retained'], {'restored': ['execute', *LATER]})
        self.assertEqual(self.accepted_after(run, claim['claim_id']), [])  # no worker or check ran
        nxt = run.next(state)
        self.assertEqual((nxt['stage'], nxt['reason']), ('execute', 'inputs-or-evidence-changed'))  # stale, not missing
        for stage in LATER:
            self.assertTrue(w.receipt_current(self.root, self.feature, stage, state['receipts'][stage]))
        checkpoint_validator().validate(state)

    def test_a_source_change_after_the_claim_keeps_the_receipts_as_history_only(self):
        run, claim, before = self.stale_execute_claim()
        self.write('src/app.py', 'print("work ran")')
        result = self.recover(run, claim['token'])
        self.assertEqual(result['retained']['restored'], [])
        self.assertEqual(result['retained']['kept_as_history'], ['execute', *LATER])
        self.assertIn('source or a recorded dependency changed after the claim', result['retained']['because'])
        state = run.load()
        self.assertFalse({'execute', *LATER} & set(state['receipts']))
        # The last acceptance stays diagnosable in the recovery record.
        self.assertEqual(state['recoveries'][-1]['claim']['retained']['receipts'],
                         {name: before[name] for name in ('execute', *LATER)})
        self.assertEqual(run.next(state)['reason'], 'pending')

    def test_a_rejected_completion_is_judged_by_the_bytes_it_changed(self):
        run, claim, before = self.stale_execute_claim()
        with self.assertRaisesRegex(w.WorkflowError, 'STAGE_NOT_PASSED'):  # a candidate that changed no file
            run.complete(claim['token'], {'stage': 'execute', 'outcome': 'failed'})
        self.assertEqual(self.recover(run, claim['token'])['retained'], {'restored': ['execute', *LATER]})
        self.assertEqual(run.load()['receipts'], before)
        run = w.Run(self.root, self.feature)
        claim = run.claim(self.usage(), confirm_invalidation=True)
        bad = self.receipt('execute')  # the worker rewrote its evidence before the rejection
        bad['outcome'] = 'failed'
        with self.assertRaisesRegex(w.WorkflowError, 'STAGE_NOT_PASSED'):
            run.complete(claim['token'], bad)
        result = self.recover(run, claim['token'])
        self.assertEqual(result['retained']['because'], ['source or a recorded dependency changed after the claim'])
        self.assertNotIn('execute', run.load()['receipts'])

    def test_a_completed_claim_keeps_its_invalidation(self):
        run, claim, _ = self.stale_execute_claim()
        run.complete(claim['token'], self.receipt('execute'))
        state = run.load()
        self.assertIsNone(state['active'])
        self.assertFalse(set(LATER) & set(state['receipts']))  # real new work: later stages run again
        self.assertEqual(run.next(state)['stage'], 'verify')


class Issue109Tests(RetentionHarness):
    """Verify is accepted, an unchanged ignored dependency is published, and the Verify re-claim is recovered."""

    def ignored_dependency(self):
        self.write('.gitignore', 'tools/\n')
        self.write('tools/dep.py', 'DEPENDENCY = 1\n')

    def test_publishing_then_recovering_the_unused_verify_claim_loses_no_receipt(self):
        run = self.ready(self.ignored_dependency)
        before = copy.deepcopy(run.load()['receipts'])
        subprocess.run(['git', 'add', '-f', 'tools/dep.py'], cwd=self.root, check=True, capture_output=True)
        self.commit_all('publish the unchanged dependency')
        pending = run.claim(self.usage())
        why = {item['stage']: item for item in pending['invalidation']}
        self.assertEqual((pending['stage'], why['verify']['why'], why['verify']['paths']),
                         ('verify', 'stale: source-drift', ['tools/dep.py']))
        claim = run.claim(self.usage(), confirm_invalidation=True)
        self.assertEqual(self.recover(run, claim['token'])['retained'], {'restored': ['verify', *LATER[1:]]})
        state = run.load()
        self.assertEqual(state['receipts'], before)
        self.assertEqual(self.accepted_after(run, claim['claim_id']), [])
        with self.assertRaisesRegex(w.WorkflowError, 'STALE_RECEIPT: verify'):  # never RECEIPT_MISSING: verify
            self.gate()
        # A genuine change to the dependency's bytes is still drift.
        self.write('tools/dep.py', 'DEPENDENCY = 2\n')
        status = w.receipt_status(self.root, self.feature, 'verify', run.load()['receipts']['verify'], run.policy)
        self.assertEqual((status['current'], status['paths']), (False, ['tools/dep.py']))

    def test_publishing_an_unchanged_declared_dependency_keeps_verify_current(self):
        for dependency in ('tools/dep.py', '.delegate/uiux/final-verify-interface.json'):
            with self.subTest(dependency=dependency):
                self.setUp()
                self.policy = w.default_policy(False, False)
                self.configure()
                self.write('.gitignore', dependency.split('/')[0] + '/\n')
                self.write(dependency, 'DEPENDENCY = 1\r\n')
                run = self.run_object()
                self.complete_through(run, 'execute')
                claim = run.claim(self.usage())
                self.assertEqual(claim['stage'], 'verify')
                receipt = self.receipt('verify')
                run.complete(claim['token'], {**receipt, 'inputs': receipt['inputs'] + [dependency]})
                self.commit_all()
                self.assertNotIn(dependency, run.load()['receipts']['verify'].get('source_fingerprints', {}))
                subprocess.run(['git', 'add', '-f', dependency], cwd=self.root, check=True, capture_output=True)
                self.commit_all('publish the unchanged dependency')
                verify = run.load()['receipts']['verify']
                self.assertTrue(w.receipt_status(self.root, self.feature, 'verify', verify, run.policy)['current'])
                self.assertEqual(w.receipt_drift(self.root, self.feature, 'verify', verify), [])
                self.assertEqual(run.next(run.load())['stage'], 'review')  # no second Verify pass
                # Real bytes still count, and a missing dependency still fails closed.
                self.write(dependency, 'DEPENDENCY = 2\r\n')
                status = w.receipt_status(self.root, self.feature, 'verify', verify, run.policy)
                self.assertEqual((status['current'], status['paths']), (False, [dependency]))
                (self.root / dependency).unlink()
                self.assertFalse(w.receipt_current(self.root, self.feature, 'verify', verify, run.policy))


class Issue114Tests(RetentionHarness):
    """A Verify source-inventory side file is damaged: a storage fault, never whole-inventory drift."""

    def sidecar(self, run):
        return run.feature / run.load()['receipts']['verify']['source_inventory']['path']

    def test_crlf_checkout_of_the_side_file_stays_current(self):
        run = self.ready()
        path = self.sidecar(run)
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
        self.assertTrue(w.receipt_current(self.root, self.feature, 'verify', run.load()['receipts']['verify']))

    def test_damaged_side_file_is_reported_as_storage_and_an_unused_claim_keeps_the_receipts(self):
        run = self.ready()
        path = self.sidecar(run)
        good = path.read_bytes()
        path.write_bytes(good[:-5])  # truncated
        pending = run.claim(self.usage())
        verify = next(item for item in pending['invalidation'] if item['stage'] == 'verify')
        self.assertEqual(verify['why'], 'stale: source-inventory-invalid')
        self.assertIn('SOURCE_INVENTORY_INVALID', verify['detail'])
        self.assertNotIn('paths', verify)  # no fabricated list of every source file
        claim = run.claim(self.usage(), confirm_invalidation=True)
        self.assertEqual(self.recover(run, claim['token'])['retained']['restored'], ['verify', *LATER[1:]])
        self.assertEqual(run.next(run.load())['reason'], 'inputs-or-evidence-changed')  # restored, never current
        path.write_bytes(good)  # the storage repair alone
        state = run.load()
        self.assertTrue(all(w.receipt_current(self.root, self.feature, s, state['receipts'][s]) for s in LATER))
        self.assertEqual(self.accepted_after(run, claim['claim_id']), [])


if __name__ == '__main__':
    unittest.main()
