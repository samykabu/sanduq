"""Workflow 1.12.0 lifecycle events, the checkpoint outbox, the stage plan and the cached next action."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lifecycle  # noqa: E402
import workflow as w  # noqa: E402
from test_receipt_contract import Harness, checkpoint_validator  # noqa: E402
from test_ci_revalidation import DriftHarness, SHAPE_VERIFICATION_INPUTS, ALL_LANES  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/workflow.py'
FIELDS = ('v', 'event_id', 'workflow_run_id', 'generation', 'at', 'stage', 'event', 'episode_id', 'claim_id',
          'caused_by_claim_id', 'candidate_run_id', 'delegation_run_ids', 'reason')


class LifecycleBase(Harness):
    def events(self, run=None):
        run = run or self.run
        found, torn = lifecycle.read_events(run.feature / 'workflow/lifecycle.jsonl')
        self.assertFalse(torn)
        return found

    def kinds(self, run=None):
        return [(e['event'], e['stage']) for e in self.events(run)]

    def cli(self, *args):
        done = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), *args],
                              capture_output=True, text=True, encoding='utf-8')
        return done.returncode, json.loads(done.stdout)

    def start(self):
        self.run = self.run_object()
        return self.run


class ClaimAndAcceptTests(LifecycleBase):
    def test_claim_and_accepted_completion_write_linked_events_without_the_token(self):
        run = self.start()
        claim = run.claim(self.usage())
        self.assertEqual(self.kinds(), [('claim', 'scope')])
        run.complete(claim['token'], self.receipt('scope'))
        events = self.events()
        self.assertEqual([e['event'] for e in events], ['claim', 'accepted'])
        for event in events:
            self.assertEqual(set(event), set(FIELDS))
            self.assertEqual(event['v'], 1)
            self.assertEqual(event['workflow_run_id'], run.load()['run_id'])
            self.assertEqual(event['claim_id'], lifecycle.claim_id_for(claim['token']))
            self.assertEqual(event['episode_id'], 'claim:' + event['claim_id'])
            self.assertEqual(event['delegation_run_ids'], [])
            self.assertIsNone(event['caused_by_claim_id'])
            self.assertIsNone(event['candidate_run_id'])  # no delegation route: nothing was validated
        self.assertEqual(len({e['event_id'] for e in events}), 2)
        self.assertLess(events[0]['generation'], events[1]['generation'])
        self.assertEqual(events[1]['generation'], run.load()['generation'])
        self.assertEqual(claim['claim_id'], events[0]['claim_id'])
        raw = (run.feature / 'workflow/lifecycle.jsonl').read_text(encoding='utf-8')
        self.assertNotIn(claim['token'], raw)
        self.assertNotIn(claim['token'], json.dumps(events))
        self.assertNotIn('lifecycle_outbox', run.load())

    def test_accepted_is_written_only_after_validation_passes(self):
        run = self.start()
        claim = run.claim(self.usage())
        bad = self.receipt('scope')
        bad['outcome'] = 'failed'
        with self.assertRaisesRegex(w.WorkflowError, 'STAGE_NOT_PASSED'):
            run.complete(claim['token'], bad)
        self.assertNotIn('accepted', [e['event'] for e in self.events()])
        self.assertNotIn('scope', run.load()['receipts'])

    def test_a_claim_after_a_pause_is_a_resume(self):
        run = self.start()
        self.assertEqual(run.claim(self.usage(.51, method='measured'))['status'], 'paused')
        self.assertEqual(self.kinds(), [('paused', None)])
        # A feature-level pause (no claim held) is valid: stage, claim and episode are all null.
        paused = self.events()[0]
        self.assertEqual((paused['stage'], paused['claim_id'], paused['episode_id'], paused['reason']),
                         (None, None, None, 'context-budget'))
        claim = run.claim(self.usage())
        self.assertEqual(claim['stage'], 'scope')
        self.assertEqual(self.kinds(), [('paused', None), ('resume', 'scope')])

    def test_claim_records_the_downstream_receipts_it_removes_before_the_claim_event(self):
        run = self.start()
        for stage in ('scope', 'specify'):
            run.complete(run.claim(self.usage())['token'], self.receipt(stage))
        (run.feature / 'evidence/scope.txt').unlink()
        pending = run.claim(self.usage())  # stream B (AHMED-12): removing later receipts needs confirmation
        self.assertEqual((pending['status'], pending['invalidates']), ('confirm_invalidation', ['specify']))
        claim = run.claim(self.usage(), confirm_invalidation=True)
        self.assertEqual(claim['stage'], 'scope')
        tail = self.events()[-3:]
        self.assertEqual([(e['event'], e['stage']) for e in tail],
                         [('invalidated', 'scope'), ('invalidated', 'specify'), ('claim', 'scope')])
        # A removed receipt belongs to no claim or episode; the new claim is only its cause.
        for removed in tail[:2]:
            self.assertEqual((removed['claim_id'], removed['episode_id']), (None, None))
            self.assertEqual(removed['caused_by_claim_id'], claim['claim_id'])
        self.assertEqual(tail[2]['claim_id'], claim['claim_id'])
        self.assertEqual(tail[2]['episode_id'], 'claim:' + claim['claim_id'])
        self.assertIsNone(tail[2]['caused_by_claim_id'])
        self.assertEqual(run.load()['receipts'], {})

    def test_pause_and_recover_record_the_claim_before_it_is_cleared(self):
        run = self.start()
        claim = run.claim(self.usage())
        code, result = self.cli('recover', '--feature', self.feature, '--token', claim['token'], '--reason', 'lost session',
                                '--force-live-owner', 'test: owner gone')
        self.assertEqual(code, 0, result)
        events = self.events()
        self.assertEqual([e['event'] for e in events], ['claim', 'recovered', 'paused'])
        recovered = events[1]
        self.assertEqual(recovered['claim_id'], claim['claim_id'])
        self.assertEqual(recovered['reason'], 'lost session')
        self.assertIsNone(run.load()['active'])
        self.assertIsNone(events[2]['claim_id'])
        # A plain pause of an active claim keeps the claim and names it.
        run = w.Run(self.root, self.feature)
        claim = run.claim(self.usage())
        code, result = self.cli('pause', '--feature', self.feature, '--reason', 'context')
        self.assertEqual(code, 0, result)
        paused = self.events()[-1]
        self.assertEqual((paused['event'], paused['claim_id'], paused['stage']), ('paused', claim['claim_id'], 'scope'))


class LinkedLogTests(LifecycleBase):
    def link(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=target.is_dir())
        except (OSError, NotImplementedError):
            self.skipTest('this OS does not allow creating symbolic links here')

    def test_a_symlinked_log_is_refused_and_the_events_stay_queued(self):
        run = self.start()
        outside = self.root / 'outside.txt'
        outside.write_text('keep', encoding='utf-8')
        (run.feature / 'workflow').mkdir(parents=True, exist_ok=True)
        self.link(run.feature / 'workflow/lifecycle.jsonl', outside)
        with self.assertRaisesRegex(ValueError, 'LIFECYCLE_LOG_UNSAFE'):
            run.claim(self.usage())
        self.assertEqual(outside.read_text(encoding='utf-8'), 'keep')
        state = run.load()
        self.assertEqual([e['event'] for e in state['lifecycle_outbox']], ['claim'])
        # Removing the link lets the queued event through on the next write; nothing was lost.
        (run.feature / 'workflow/lifecycle.jsonl').unlink()
        w.Run(self.root, self.feature).complete(state['active']['token'], self.receipt('scope'))
        self.assertEqual(self.kinds(), [('claim', 'scope'), ('accepted', 'scope')])

    def test_a_symlinked_workflow_folder_is_refused_for_reading_and_appending(self):
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        feature = self.root / 'feat'
        feature.mkdir()
        self.link(feature / 'workflow', elsewhere)
        state = {'run_id': 'r', 'generation': 0}
        record = lifecycle.make_event(state, 'scope', 'claim', claim_id='c-1')
        with self.assertRaisesRegex(ValueError, 'LIFECYCLE_LOG_UNSAFE'):
            lifecycle.append_events(lifecycle.log_path(feature), [record])
        with self.assertRaisesRegex(ValueError, 'LIFECYCLE_LOG_UNSAFE'):
            lifecycle.read_events(lifecycle.log_path(feature))
        self.assertEqual(list(elsewhere.iterdir()), [])
        state['lifecycle_outbox'] = [record]
        with self.assertRaises(ValueError):
            lifecycle.flush(state, feature)
        self.assertEqual(state['lifecycle_outbox'], [record])


class IdentityLinkTests(LifecycleBase):
    def test_receipts_and_recoveries_carry_the_claim_id_and_the_instant_of_their_events(self):
        run = self.start()
        claim = run.claim(self.usage())
        run.complete(claim['token'], self.receipt('scope'))
        receipt = run.load()['receipts']['scope']
        accepted, = [e for e in self.events() if e['event'] == 'accepted']
        self.assertEqual(receipt['claim_id'], claim['claim_id'])
        self.assertEqual(receipt['claim_id'], accepted['claim_id'])
        self.assertEqual(receipt['completed_at'], accepted['at'])
        second = run.claim(self.usage())
        code, result = self.cli('recover', '--feature', self.feature, '--token', second['token'], '--reason', 'lost session',
                                '--force-live-owner', 'test: owner gone')
        self.assertEqual(code, 0, result)
        recovery, = run.load()['recoveries']
        recovered, = [e for e in self.events() if e['event'] == 'recovered']
        self.assertEqual(recovery['claim']['claim_id'], second['claim_id'])
        self.assertEqual(recovery['claim']['claim_id'], recovered['claim_id'])
        self.assertEqual(recovery['at'], recovered['at'])
        self.assertEqual(recovery['claim']['stage'], recovered['stage'])


class RejectionTests(LifecycleBase):
    def test_a_rejected_completion_is_recorded_and_the_claim_stays(self):
        run = self.start()
        for stage in ('scope', 'specify'):
            run.complete(run.claim(self.usage())['token'], self.receipt(stage))
        claim = run.claim(self.usage())
        receipt = self.receipt('clarify')
        receipt['unresolved'] = 1
        before = run.load()
        with self.assertRaisesRegex(w.WorkflowError, 'CLARIFICATION_UNRESOLVED'):
            run.complete(claim['token'], receipt)
        after = run.load()
        self.assertEqual(after['active'], before['active'])
        self.assertEqual(after['receipts'].keys(), before['receipts'].keys())
        self.assertEqual(after['generation'], before['generation'])
        last = self.events()[-1]
        self.assertEqual((last['event'], last['stage'], last['claim_id']), ('rejected-completion', 'clarify', claim['claim_id']))
        self.assertEqual(last['reason'], 'CLARIFICATION_UNRESOLVED')
        self.assertEqual(last['generation'], after['generation'])
        self.assertNotIn('lifecycle_outbox', after)
        # The same claim can still complete with a valid receipt, and both outcomes are on record.
        run.complete(claim['token'], self.receipt('clarify'))
        self.assertEqual([e['event'] for e in self.events()][-2:], ['rejected-completion', 'accepted'])

    def test_a_value_error_rejection_is_recorded_like_a_workflow_error(self):
        # DelegationError and VerificationPlanError are ValueErrors raised from inside the acceptance.
        import delegation
        run = self.start()
        claim = run.claim(self.usage())
        with patch.object(w.Run, '_accept_completion', side_effect=delegation.DelegationError('DELEGATION_LEDGER_UNTRUSTED: x')):
            with self.assertRaises(delegation.DelegationError):
                run.complete(claim['token'], self.receipt('scope'))
        last = self.events()[-1]
        self.assertEqual((last['event'], last['claim_id']), ('rejected-completion', claim['claim_id']))
        self.assertIn('DELEGATION_LEDGER_UNTRUSTED', last['reason'])
        self.assertEqual(run.load()['active']['token'], claim['token'])
        path = self.root / 'receipt.json'
        path.write_text(json.dumps(self.receipt('scope')), encoding='utf-8')
        with patch.object(w.Run, '_accept_completion', side_effect=ValueError('VERIFICATION_PLAN_X')):
            with patch.object(sys, 'argv', ['workflow.py', '--root', str(self.root), 'complete', '--feature', self.feature,
                                            '--token', claim['token'], '--receipt', str(path)]):
                with patch('builtins.print') as out:
                    self.assertEqual(w.main(), 1)
        self.assertEqual(json.loads(out.call_args.args[0]), {'ok': False, 'error': 'VERIFICATION_PLAN_X'})
        self.assertEqual(self.events()[-1]['event'], 'rejected-completion')

    def test_a_wrong_token_is_not_a_recorded_rejection(self):
        run = self.start()
        run.claim(self.usage())
        with self.assertRaisesRegex(w.WorkflowError, 'CLAIM_TOKEN_MISMATCH'):
            run.complete('wrong', self.receipt('scope'))
        self.assertEqual(self.kinds(), [('claim', 'scope')])

    def test_cli_behaviour_of_a_rejected_completion_is_unchanged(self):
        run = self.start()
        for stage in ('scope', 'specify'):
            run.complete(run.claim(self.usage())['token'], self.receipt(stage))
        claim = run.claim(self.usage())
        receipt = self.receipt('clarify')
        receipt['unresolved'] = 1
        path = self.root / 'receipt.json'
        path.write_text(json.dumps(receipt), encoding='utf-8')
        code, result = self.cli('complete', '--feature', self.feature, '--token', claim['token'], '--receipt', str(path))
        self.assertEqual((code, result), (1, {'ok': False, 'error': 'CLARIFICATION_UNRESOLVED'}))
        self.assertEqual(run.load()['active']['token'], claim['token'])
        self.assertEqual(self.events()[-1]['event'], 'rejected-completion')

    def test_a_rejection_for_missing_evidence_keeps_the_claim_and_adds_no_lineage(self):
        run = self.start()
        claim = run.claim(self.usage())
        receipt = self.receipt('scope')
        (run.feature / 'evidence/scope.txt').unlink()
        with self.assertRaisesRegex(w.WorkflowError, 'EVIDENCE_MISSING'):
            run.complete(claim['token'], receipt)
        state = run.load()
        self.assertEqual(state['active']['token'], claim['token'])
        self.assertNotIn('lineage', state)


class OutboxTests(LifecycleBase):
    def test_an_interrupted_append_is_replayed_once(self):
        run = self.start()
        real = lifecycle.append_events

        def crash_after_write(path, records):
            real(path, records)
            raise RuntimeError('crash between the append and clearing the outbox')

        with patch.object(lifecycle, 'append_events', crash_after_write):
            with self.assertRaises(RuntimeError):
                run.claim(self.usage())
        state = run.load()
        queued = state['lifecycle_outbox']
        self.assertEqual([e['event'] for e in queued], ['claim'])
        self.assertEqual(len(self.events()), 1)  # the file write happened before the crash
        # The next write under the lock replays the queue; the event is deduplicated by event_id.
        claim = state['active']
        run = w.Run(self.root, self.feature)
        run.complete(claim['token'], self.receipt('scope'))
        events = self.events()
        self.assertEqual([e['event'] for e in events], ['claim', 'accepted'])
        self.assertEqual(events[0]['event_id'], queued[0]['event_id'])
        self.assertNotIn('lifecycle_outbox', run.load())

    def test_a_crash_before_the_append_replays_from_the_checkpoint(self):
        run = self.start()
        with patch.object(lifecycle, 'append_events', side_effect=RuntimeError('disk full')):
            with self.assertRaises(RuntimeError):
                run.claim(self.usage())
        self.assertFalse((run.feature / 'workflow/lifecycle.jsonl').exists())
        claim = run.load()['active']
        w.Run(self.root, self.feature).complete(claim['token'], self.receipt('scope'))
        self.assertEqual(self.kinds(), [('claim', 'scope'), ('accepted', 'scope')])

    def test_replaying_the_same_events_never_duplicates_them(self):
        path = self.root / 'lifecycle.jsonl'
        state = {'run_id': 'r', 'generation': 0}
        records = [lifecycle.make_event(state, 'scope', 'claim', claim_id='c-1'),
                   lifecycle.make_event(state, 'scope', 'accepted', claim_id='c-1')]
        self.assertEqual(lifecycle.append_events(path, records), 2)
        self.assertEqual(lifecycle.append_events(path, records), 0)
        self.assertEqual(lifecycle.append_events(path, records + [lifecycle.make_event(state, 'plan', 'claim')]), 1)
        self.assertEqual(len(lifecycle.read_events(path)[0]), 3)

    def test_a_torn_final_line_is_tolerated_by_the_reader_and_repaired_by_the_next_append(self):
        path = self.root / 'workflow/lifecycle.jsonl'
        state = {'run_id': 'r', 'generation': 0}
        first = lifecycle.make_event(state, 'scope', 'claim', claim_id='c-1')
        lifecycle.append_events(path, [first])
        with open(path, 'ab') as handle:
            handle.write(b'{"v": 1, "event_id": "torn", "stage": "sco')
        events, torn = lifecycle.read_events(path)
        self.assertEqual([e['event_id'] for e in events], [first['event_id']])
        self.assertTrue(torn)
        second = lifecycle.make_event(state, 'scope', 'accepted', claim_id='c-1')
        self.assertEqual(lifecycle.append_events(path, [second]), 1)
        events, torn = lifecycle.read_events(path)
        self.assertFalse(torn)
        self.assertEqual([e['event_id'] for e in events], [first['event_id'], second['event_id']])
        self.assertTrue(path.read_bytes().endswith(b'\n'))

    def test_a_missing_or_empty_log_reads_as_no_events(self):
        self.assertEqual(lifecycle.read_events(self.root / 'absent.jsonl'), ([], False))
        empty = self.root / 'empty.jsonl'
        empty.write_bytes(b'')
        self.assertEqual(lifecycle.read_events(empty), ([], False))

    def test_claim_id_is_stable_and_not_the_token(self):
        self.assertEqual(lifecycle.claim_id_for('abc'), lifecycle.claim_id_for('abc'))
        self.assertNotIn('abc', lifecycle.claim_id_for('abc'))
        self.assertIsNone(lifecycle.claim_id_for(None))

    def test_the_log_is_written_with_unix_line_endings(self):
        run = self.start()
        run.claim(self.usage())
        self.assertNotIn(b'\r', (run.feature / 'workflow/lifecycle.jsonl').read_bytes())


class TailRepairTests(LifecycleBase):
    def test_a_complete_record_missing_only_its_newline_is_kept(self):
        path = self.root / 'workflow/lifecycle.jsonl'
        state = {'run_id': 'r', 'generation': 0}
        first = lifecycle.make_event(state, 'scope', 'claim', claim_id='c-1')
        lifecycle.append_events(path, [first])
        # Interrupted right before the newline: the record is whole, only the terminator is missing.
        path.write_bytes(path.read_bytes().rstrip(b'\n'))
        self.assertFalse(path.read_bytes().endswith(b'\n'))
        second = lifecycle.make_event(state, 'scope', 'accepted', claim_id='c-1')
        # Replaying the same record plus a new one must not lose or duplicate the first.
        self.assertEqual(lifecycle.append_events(path, [first, second]), 1)
        events, torn = lifecycle.read_events(path)
        self.assertFalse(torn)
        self.assertEqual([e['event_id'] for e in events], [first['event_id'], second['event_id']])
        self.assertTrue(path.read_bytes().endswith(b'\n'))
        self.assertEqual(path.read_bytes().count(b'\n'), 2)

    def test_replaying_only_the_unterminated_record_appends_nothing_but_terminates_it(self):
        path = self.root / 'workflow/lifecycle.jsonl'
        state = {'run_id': 'r', 'generation': 0}
        only = lifecycle.make_event(state, 'scope', 'claim', claim_id='c-1')
        lifecycle.append_events(path, [only])
        path.write_bytes(path.read_bytes().rstrip(b'\n'))
        self.assertEqual(lifecycle.append_events(path, [only]), 0)
        self.assertEqual([e['event_id'] for e in lifecycle.read_events(path)[0]], [only['event_id']])
        self.assertTrue(path.read_bytes().endswith(b'\n'))

    def test_a_crash_before_the_newline_loses_nothing_through_the_outbox(self):
        run = self.start()
        real = lifecycle.append_events

        def crash_before_the_newline(path, records):
            real(path, records)
            Path(path).write_bytes(Path(path).read_bytes().rstrip(b'\n'))
            raise RuntimeError('crash before the newline reached the disk')

        with patch.object(lifecycle, 'append_events', crash_before_the_newline):
            with self.assertRaises(RuntimeError):
                run.claim(self.usage())
        claim = run.load()['active']
        w.Run(self.root, self.feature).complete(claim['token'], self.receipt('scope'))
        self.assertEqual(self.kinds(), [('claim', 'scope'), ('accepted', 'scope')])

    def test_an_unparseable_fragment_is_still_dropped(self):
        path = self.root / 'workflow/lifecycle.jsonl'
        state = {'run_id': 'r', 'generation': 0}
        first = lifecycle.make_event(state, 'scope', 'claim', claim_id='c-1')
        lifecycle.append_events(path, [first])
        with open(path, 'ab') as handle:
            handle.write(b'{"v": 1, "event_id": "torn"}')  # parses, but is not an event of this run's shape
            handle.write(b'{')
        second = lifecycle.make_event(state, 'scope', 'accepted', claim_id='c-1')
        self.assertEqual(lifecycle.append_events(path, [second]), 1)
        events, torn = lifecycle.read_events(path)
        self.assertFalse(torn)
        self.assertEqual([e['event_id'] for e in events], [first['event_id'], second['event_id']])


class PlanAndNextActionTests(LifecycleBase):
    def test_the_checkpoint_carries_the_stage_plan_and_the_next_action(self):
        run = self.start()
        state = run.load()
        self.assertEqual(state['stage_plan'], {'v': 1, 'generation': state['generation'], 'stages': w.stages(self.policy)})
        self.assertEqual(state['next_action']['kind'], 'next-stage')
        self.assertEqual(state['next_action']['stage'], 'scope')
        self.assertEqual(state['next_action']['generation'], state['generation'])
        claim = run.claim(self.usage())
        state = run.load()
        self.assertEqual((state['next_action']['kind'], state['next_action']['stage']), ('active-claim', 'scope'))
        self.assertEqual(state['next_action']['generation'], state['generation'])
        run.complete(claim['token'], self.receipt('scope'))
        state = run.load()
        self.assertEqual((state['next_action']['kind'], state['next_action']['stage']), ('next-stage', 'specify'))
        self.assertTrue(state['next_action']['evaluated_at'])
        checkpoint_validator().validate(state)

    def test_the_stage_plan_is_policy_filtered(self):
        self.policy = w.default_policy(False, False)
        self.configure()
        run = self.start()
        stages = run.load()['stage_plan']['stages']
        self.assertEqual(stages, w.stages(self.policy))
        self.assertNotIn('qa_analyze', stages)
        self.assertNotIn('manual_update', stages)

    def test_the_final_states_are_named(self):
        run = self.start()
        for stage in w.stages(self.policy):
            if stage == 'pr':
                self.assertEqual(run.load()['next_action']['stage'], None)
                self.assertIn('Finalize', run.load()['next_action']['text'])
            claim = run.claim(self.usage(), finalize=stage == 'pr')
            run.complete(claim['token'], self.receipt(stage))
        self.assertIsNone(run.load()['next_action']['stage'])


class InvalidationTests(LifecycleBase):
    def test_migrate_records_each_invalidated_stage(self):
        self.policy = w.default_policy(False, False)
        self.configure()
        run = self.start()
        for stage in ('scope', 'specify', 'clarify', 'plan', 'tasks'):
            run.complete(run.claim(self.usage())['token'], self.receipt(stage))
        self.policy['processes']['qa'] = True
        self.configure()
        run = w.Run(self.root, self.feature)
        run.migrate('Enable QA after review')
        tail = [e for e in self.events(run) if e['event'] == 'invalidated']
        self.assertEqual([e['stage'] for e in tail], ['tasks'])
        self.assertEqual(tail[0]['reason'], 'migrate: Enable QA after review')
        self.assertIsNone(tail[0]['claim_id'])

    def test_refresh_records_each_invalidated_stage(self):
        run = self.start()
        for stage in ('scope', 'specify', 'clarify', 'plan'):
            run.complete(run.claim(self.usage())['token'], self.receipt(stage))
        run.refresh('clarify', 'New answers')
        tail = [e for e in self.events(run) if e['event'] == 'invalidated']
        self.assertEqual([e['stage'] for e in tail], ['clarify', 'plan'])
        self.assertTrue(all(e['reason'] == 'refresh clarify: New answers' for e in tail))


class DriftLifecycleTests(DriftHarness):
    def kinds(self):
        events, torn = lifecycle.read_events(self.run.feature / 'workflow/lifecycle.jsonl')
        self.assertFalse(torn)
        return events

    def test_a_changed_amendment_records_the_receipts_it_stales(self):
        before = len(self.kinds())
        evidence = self.recorded['scope']['evidence'][0]
        (self.root / evidence).write_text('amended evidence', encoding='utf-8')
        self.run.amend('scope', evidence, 'The finding changed', 'changed')
        added = self.kinds()[before:]
        self.assertEqual([(e['event'], e['stage']) for e in added],
                         [('invalidated', 'verify'), ('invalidated', 'review'), ('invalidated', 'ready')])
        self.assertTrue(all('changed amendment of scope' in e['reason'] for e in added))

    def test_an_unchanged_amendment_records_nothing(self):
        before = len(self.kinds())
        evidence = self.recorded['scope']['evidence'][0]
        (self.root / evidence).write_text('fixed a typo', encoding='utf-8')
        self.run.amend('scope', evidence, 'Typo', 'unchanged')
        self.assertEqual(len(self.kinds()), before)

    def test_revalidation_records_stale_then_current(self):
        self.change(SHAPE_VERIFICATION_INPUTS)
        before = len(self.kinds())
        run_id, client = self.green_run(lanes=['backend-unit'])
        self.assertFalse(self.run.revalidate('verify', check_run=run_id, github=client)['revalidated'])
        stale = self.kinds()[before:]
        self.assertEqual([(e['event'], e['stage']) for e in stale], [('revalidation-stale', 'verify')])
        self.assertIn('projects-integration', stale[0]['reason'])
        self.assertEqual(stale[0]['episode_id'], 'revalidation:' + stale[0]['event_id'])
        self.assertIsNone(stale[0]['claim_id'])
        run_id, client = self.green_run(lanes=ALL_LANES)
        self.assertTrue(self.run.revalidate('verify', check_run=run_id, github=client, reason='CI is green')['revalidated'])
        done = self.kinds()[before + 1:]
        self.assertEqual([(e['event'], e['stage']) for e in done], [('revalidated', 'verify')])
        self.assertEqual(done[0]['reason'], 'CI is green')
        self.assertNotEqual(done[0]['episode_id'], stale[0]['episode_id'])


if __name__ == '__main__':
    unittest.main()
