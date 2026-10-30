"""PH-04-T09: the gate flags a receipt edited outside the dispatcher, through the append-only receipt log."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ci_gate as c
import receipt_log
import workflow as w
import test_ci_gate


class ReceiptLogGateTests(unittest.TestCase):
    setUp = test_ci_gate.CIGateTests.setUp
    configure = test_ci_gate.CIGateTests.configure
    usage = test_ci_gate.CIGateTests.usage
    receipt = test_ci_gate.CIGateTests.receipt
    ready = test_ci_gate.CIGateTests.ready

    def checkpoint(self):
        return self.root / self.feature / 'workflow/checkpoint.json'

    def hand_edit(self, stage='verify'):
        state = w.read(self.checkpoint())
        state['receipts'][stage]['summary'] = 'Edited by hand'
        w.write(self.checkpoint(), state)

    def commit(self, message):
        subprocess.run(['git', 'add', '-A'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', message], cwd=self.root, check=True)
        return w.git(self.root, 'rev-parse', 'HEAD')

    def test_every_dispatcher_receipt_is_logged_and_the_gate_passes(self):
        self.ready()
        result = c.check(self.root, self.feature, self.policy)
        receipts = w.read(self.checkpoint())['receipts']
        self.assertGreaterEqual(result['receipt_log']['entries'], len(receipts))
        self.assertFalse([x for x in result['warnings'] if x.startswith('RECEIPT_')], result['warnings'])

    def test_a_direct_receipt_edit_is_flagged(self):
        self.ready()
        self.hand_edit()
        with self.assertRaisesRegex(w.WorkflowError, 'RECEIPT_EDITED_OUTSIDE_DISPATCHER: verify: the receipt in '
                                    'checkpoint.json differs'):
            c.check(self.root, self.feature, self.policy)

    def test_a_later_save_logs_the_edit_instead_of_adopting_it(self):
        run = self.ready()
        self.hand_edit()
        run.save(run.load())
        last = receipt_log.latest(receipt_log.read_entries(run.feature))['verify']
        self.assertEqual(last['by'], receipt_log.OUTSIDE)
        with self.assertRaisesRegex(w.WorkflowError, 'RECEIPT_EDITED_OUTSIDE_DISPATCHER: verify: the receipt was '
                                    'logged as edited outside the dispatcher'):
            c.check(self.root, self.feature, self.policy)

    def test_a_receipt_deleted_by_hand_is_flagged(self):
        self.ready()
        state = w.read(self.checkpoint())
        state['receipts'].pop('pr', None)
        removed = sorted(state['receipts'])[0]
        state['receipts'].pop(removed)
        w.write(self.checkpoint(), state)
        with self.assertRaisesRegex(w.WorkflowError, 'RECEIPT_MISSING|RECEIPT_EDITED_OUTSIDE_DISPATCHER: ' + removed):
            c.check(self.root, self.feature, self.policy)
        self.assertRaisesRegex(w.WorkflowError, 'RECEIPT_EDITED_OUTSIDE_DISPATCHER: ' + removed, receipt_log.check,
                               self.root, self.feature, state['receipts'])

    def test_merged_entries_cannot_be_rewritten_or_dropped(self):
        self.ready()
        base = self.commit('Ready')
        log = self.root / self.feature / receipt_log.LOG
        lines = log.read_text(encoding='utf-8').splitlines()
        first = json.loads(lines[0]); first['at'] = '2000-01-01T00:00:00+00:00'
        log.write_text('\n'.join([json.dumps(first)] + lines[1:]) + '\n', encoding='utf-8')
        self.commit('Rewrite history')
        with self.assertRaisesRegex(w.WorkflowError, 'RECEIPT_LOG_REWRITTEN'):
            c.check(self.root, self.feature, self.policy, base)
        log.unlink()
        self.commit('Drop the log')
        with self.assertRaisesRegex(w.WorkflowError, 'RECEIPT_LOG_MISSING'):
            c.check(self.root, self.feature, self.policy, base)

    def test_a_feature_from_before_the_log_passes_with_a_warning_and_the_next_save_starts_it(self):
        run = self.ready()
        log = run.feature / receipt_log.LOG
        log.unlink()
        result = c.check(self.root, self.feature, self.policy)
        self.assertTrue(any(x.startswith('RECEIPT_LOG_ABSENT') for x in result['warnings']), result['warnings'])
        run.save(run.load())
        entries = receipt_log.read_entries(run.feature)
        self.assertEqual({e['by'] for e in entries}, {receipt_log.DISPATCHER})
        self.assertFalse([x for x in c.check(self.root, self.feature, self.policy)['warnings']
                          if x.startswith('RECEIPT_LOG_ABSENT')])

    def test_the_log_is_required_in_the_index_with_the_checkpoint(self):
        self.ready()
        self.commit('Ready')
        log = self.root / self.feature / receipt_log.LOG
        log.write_text(log.read_text(encoding='utf-8') + '\n', encoding='utf-8')
        with self.assertRaisesRegex(w.WorkflowError, 'EVIDENCE_NOT_PORTABLE.*receipt-log.jsonl'):
            c.check_index(self.root, self.feature)


class ReceiptLogUnitTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__('shutil').rmtree, self.root)
        self.feature = self.root / 'specs/001-x'

    def test_re_recording_an_edited_stage_passes_with_a_warning(self):
        receipt_log.record(self.feature, {}, {'plan': {'summary': 'A'}}, 't1')
        receipt_log.record(self.feature, {'plan': {'summary': 'hand'}}, {'plan': {'summary': 'B'}}, 't2')
        self.assertEqual([e['by'] for e in receipt_log.read_entries(self.feature)],
                         ['dispatcher', 'outside-edit', 'dispatcher'])
        result = receipt_log.check(self.root, 'specs/001-x', {'plan': {'summary': 'B'}})
        self.assertEqual(result['warnings'], ['RECEIPT_OUTSIDE_EDIT_SUPERSEDED: plan was edited outside the '
                                              'dispatcher at t2 and re-recorded through it since'])

    def test_hash_ignores_key_order_and_an_unchanged_save_appends_nothing(self):
        self.assertEqual(receipt_log.receipt_hash({'a': 1, 'b': [2]}), receipt_log.receipt_hash({'b': [2], 'a': 1}))
        receipt_log.record(self.feature, {}, {'plan': {'a': 1}}, 't1')
        self.assertEqual(receipt_log.record(self.feature, {'plan': {'a': 1}}, {'plan': {'a': 1}}, 't2'), [])
        self.assertEqual(len(receipt_log.read_entries(self.feature)), 1)

    def test_a_damaged_line_is_refused(self):
        (self.feature / 'workflow').mkdir(parents=True)
        (self.feature / receipt_log.LOG).write_text('{"stage": "plan"}\n', encoding='utf-8')
        with self.assertRaisesRegex(w.WorkflowError, 'RECEIPT_LOG_INVALID: .* line 1'):
            receipt_log.check(self.root, 'specs/001-x', {})


if __name__ == '__main__':
    unittest.main()
