"""Regression tests for the round-1 code-review findings (one class per finding, named F<n>)."""
import json
import os
import socket
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

import helpers
import progress
from helpers import FIXTURES, T0, Project, fixture
from sanduq_progress import facts as factslib, model, refresh, snapshot, statusline
from sanduq_progress.lock import Lock, LockBusy
from sanduq_progress.paths import Ctx, ProgressError, normalise_feature

NOW = datetime(2026, 10, 15, 12, 30, tzinfo=timezone.utc)


def stamp(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00'))


class WorkflowFiles(Project):
    def delegations(self, *attempts):
        folder = self.feature_dir / 'workflow'
        folder.mkdir(exist_ok=True)
        (folder / 'delegations.json').write_text(json.dumps({'attempts': list(attempts)}), encoding='utf-8')

    def attempt(self, **over):
        row = {'identity': 'specs/001-demo/T002', 'task_type': 'implement', 'run_id': 'run-1', 'requested_harness': 'codex',
               'requested_model': 'req-alias', 'actual_model': None, 'actual_model_evidence': 'pending', 'status': 'successful',
               'started_at': '2026-10-15T10:00:00Z', 'ended_at': '2026-10-15T11:00:00Z'}
        row.update(over)
        return row

    def run_result(self, run_id, **fields):
        folder = self.root / '.delegate' / 'runs' / run_id
        folder.mkdir(parents=True)
        (folder / 'result.json').write_text(json.dumps({'run_id': run_id, 'harness': 'codex', 'status': 'successful',
                                                        'started_at': '2026-10-15T10:00:00Z', 'ended_at': '2026-10-15T11:00:00Z',
                                                        **fields}), encoding='utf-8')

    def build(self):
        return model.build(self.ctx, NOW, 1, {})

    def lane_of(self, report, owner):
        return next(l for l in report['lanes'] if l['owner'] == owner)


class F01ActiveTime(WorkflowFiles):
    def test_attempt_wall_time_is_never_active_time(self):
        self.init()
        self.delegations(self.attempt())
        lane = self.lane_of(self.build(), 'specs/001-demo/T002')
        self.assertEqual(lane['elapsed']['value'], 3600)
        self.assertIsNone(lane['active']['value'])
        self.assertEqual(lane['active']['fidelity'], 'unknown')

    def test_active_is_the_sum_of_observed_intervals_only(self):
        self.init()
        self.delegations(self.attempt(active_intervals=[{'start': '2026-10-15T10:00:00Z', 'end': '2026-10-15T10:10:00Z'},
                                                         {'start': '2026-10-15T10:30:00Z', 'end': '2026-10-15T10:35:00Z'}]))
        lane = self.lane_of(self.build(), 'specs/001-demo/T002')
        self.assertEqual((lane['active']['value'], lane['active']['fidelity']), (900, 'partial'))


class F02Units(WorkflowFiles):
    def test_every_duration_in_the_projection_is_whole_seconds(self):
        self.init()
        self.bind()
        stat = json.loads(fixture('claude_statusline.json', CWD=self.root.as_posix()))
        statusline.record(json.dumps(stat), self.root, stamp('2026-10-15T12:00:05Z'))
        self.delegations(self.attempt())
        report = self.build()
        self.assertEqual(report['orchestrator']['elapsed']['value'], 45)  # 45000 ms from the statusline
        self.assertEqual(self.lane_of(report, 'specs/001-demo/T002')['elapsed']['value'], 3600)


class F03ObservedModel(WorkflowFiles):
    def test_requested_run_model_is_not_an_observation(self):
        self.init()
        self.delegations(self.attempt(run_id='run-req'))
        self.run_result('run-req', model='requested-alias')
        lane = self.lane_of(self.build(), 'specs/001-demo/T002')
        self.assertIsNone(lane['observed']['model']['value'])
        self.assertEqual(lane['observed']['model']['fidelity'], 'unknown')
        self.assertEqual(lane['requested']['model'], 'req-alias')

    def test_run_requested_model_fills_requested_when_the_ledger_has_none(self):
        self.init()
        self.delegations(self.attempt(run_id='run-req', requested_model=None))
        self.run_result('run-req', model='requested-alias')
        lane = self.lane_of(self.build(), 'specs/001-demo/T002')
        self.assertEqual(lane['requested']['model'], 'requested-alias')
        self.assertIsNone(lane['observed']['model']['value'])

    def test_explicit_reported_model_is_observed(self):
        self.init()
        self.delegations(self.attempt(run_id='run-obs'))
        self.run_result('run-obs', model='requested-alias', model_reported='gpt-real')
        observed = self.lane_of(self.build(), 'specs/001-demo/T002')['observed']['model']
        self.assertEqual((observed['value'], observed['source']), ('gpt-real', 'run-result'))


class F04Rebind(Project):
    def test_fresh_handshake_overrides_an_existing_binding(self):
        nonce_a = self.init()
        other = self.root / 'specs' / '002-other'
        other.mkdir()
        (other / 'tasks.md').write_text('# Tasks\n- [ ] T001 x\n', encoding='utf-8')
        payload = lambda nonce: {'session_id': 'sess-r', 'cwd': self.root.as_posix(), 'hook_event_name': 'PostToolUse',
                                 'tool_name': 'Bash', 'tool_input': {'command': 'python progress.py init'},
                                 'tool_response': {'stdout': f'progress: ready x bind={nonce}'}, 'tool_use_id': 't'}
        self.assertIn(self.hook('post_tool_use', payload(nonce_a)), ('dirty', 'refreshed'))
        self.assertEqual(snapshot.lookup(self.root, 'claude', 'sess-r')['feature'], 'specs/001-demo')
        code, line = self.cli('init', '--feature', 'specs/002-other')
        self.assertEqual(code, 0, line)
        nonce_b = line.rsplit('bind=', 1)[1]
        self.hook('post_tool_use', payload(nonce_b))
        self.assertEqual(snapshot.lookup(self.root, 'claude', 'sess-r')['feature'], 'specs/002-other')
        self.hook('pre_tool_use', {'session_id': 'sess-r', 'cwd': self.root.as_posix(), 'hook_event_name': 'PreToolUse',
                                   'effort': {'level': 'low'}, 'tool_name': 'Bash', 'tool_input': {}})
        snap_b = snapshot.snapshot_path(Ctx(self.root, 'specs/002-other'), 'claude', 'sess-r')
        self.assertEqual(json.loads(snap_b.read_text())['effort']['value'], 'low')


class F05StaleLockRace(Project):
    """Round 1 asked for race-free stale handling; round 2 replaced recovery with an OS-held lock (see test_review_r2.F01)."""
    def test_a_contender_cannot_take_a_held_lock_whatever_the_file_says(self):
        path = self.root / 'lockfile'
        holder = Lock(path, retries=0).acquire()
        try:
            path.write_text(json.dumps({'pid': 99999999, 'host': socket.gethostname(), 'started_at': '2026-10-15T00:00:00Z'}))
            with self.assertRaises(LockBusy):
                Lock(path, retries=0).acquire()
        finally:
            holder.release()


class F06ChildMerge(Project):
    def child_events(self, owner):
        self.init(debounce_seconds=0)
        self.bind()
        self.cli('lane', 'L1', '--tasks', 'T002', '--owner', owner)
        self.hook('pre_tool_use', self.payload('claude_pre_task.json'), now='2026-10-15T12:10:00Z')
        self.hook('post_tool_use', self.payload('claude_child_event.json', model={'id': 'claude-haiku-5-5'},
                                                effort={'level': 'xhigh'}), now='2026-10-15T12:11:00Z')
        self.hook('post_tool_use', self.payload('claude_post_task.json', tool_response={'agentId': 'agent-9f'}), now='2026-10-15T12:11:30Z')
        self.hook('stop', self.payload('claude_child_event.json', model={'id': 'claude-haiku-5-5'}), now='2026-10-15T12:12:00Z')
        return model.build(self.ctx, NOW, 1, json.loads(self.ctx.state.read_text()))

    def test_child_matching_the_lane_owner_by_agent_id_merges(self):
        report = self.child_events('agent-9f')
        self.assertEqual([l['id'] for l in report['lanes'] if l['origin'] == 'host-child'], [])
        lane = next(l for l in report['lanes'] if l['id'] == 'L1')
        self.assertEqual(lane['observed']['model']['value'], 'claude-haiku-5-5')
        self.assertEqual(lane['observed']['effort']['value'], 'xhigh')  # F07: child effort reaches the lane
        # the child's Stop event ended it: the lane waits for its unchecked task (round 2 F03) instead of staying active
        self.assertEqual(lane['status'], 'waiting')

    def merged_by(self, owner):
        report = self.child_events(owner)
        self.assertEqual([l for l in report['lanes'] if l['origin'] == 'host-child'], [])
        self.assertEqual(next(l for l in report['lanes'] if l['id'] == 'L1')['observed']['model']['value'], 'claude-haiku-5-5')

    def test_match_by_tool_use_id(self):
        self.merged_by('toolu_01TASK')

    def test_match_by_description_label_ignores_case(self):
        self.merged_by('explore the PARSER module')

    def test_unmatched_child_stays_a_separate_lane(self):
        report = self.child_events('someone-else')
        self.assertEqual([l['id'] for l in report['lanes'] if l['origin'] == 'host-child'], ['C1'])
        self.assertIsNone(next(l for l in report['lanes'] if l['id'] == 'L1')['observed']['model']['value'])


class F07ChildEffort(Project):
    def test_child_effort_is_kept_in_the_snapshot(self):
        self.init(debounce_seconds=0)
        self.bind()
        self.hook('post_tool_use', self.payload('claude_child_event.json', effort={'level': 'xhigh'}))
        child = self.snap()['children']['agent-9f']
        self.assertEqual(child['effort']['value'], 'xhigh')

    def test_unmatched_child_lane_shows_effort(self):
        self.init(debounce_seconds=0)
        self.bind()
        self.hook('post_tool_use', self.payload('claude_child_event.json', effort={'level': 'xhigh'}))
        report = model.build(self.ctx, NOW, 1, {})
        lane = next(l for l in report['lanes'] if l['origin'] == 'host-child')
        self.assertEqual(lane['observed']['effort']['value'], 'xhigh')


class F08ContextTokens(Project):
    def fields(self, window):
        payload = {'session_id': 's', 'context_window': window}
        from sanduq_progress.hosts import claude
        return claude.parse_statusline(payload, NOW)['fields']['context']['value']

    def test_cumulative_totals_are_never_used(self):
        value = self.fields({'total_input_tokens': 900000, 'context_window_size': 200000, 'used_percentage': 41})
        self.assertIsNone(value['used_tokens'])
        self.assertEqual(value['used_percent'], 41.0)

    def test_current_usage_counters_give_the_used_tokens(self):
        value = self.fields({'total_input_tokens': 900000, 'context_window_size': 200000, 'used_percentage': 41,
                             'current_usage': {'input_tokens': 2000, 'cache_creation_input_tokens': 400,
                                               'cache_read_input_tokens': 79600, 'output_tokens': 50}})
        self.assertEqual(value['used_tokens'], 82000)

    def test_null_or_empty_current_usage_is_unknown(self):
        for usage in (None, {}, {'output_tokens': 5}):
            with self.subTest(usage=usage):
                value = self.fields({'context_window_size': 200000, 'used_percentage': 10, 'current_usage': usage})
                self.assertIsNone(value['used_tokens'])


class F09DebouncedFreshness(Project):
    def read_data_js(self):
        text = self.ctx.data_js.read_text(encoding='utf-8')
        return json.loads(text[len('window.__SANDUQ_PROGRESS__ = '):].rstrip().rstrip(';'))

    def test_debounced_event_is_published_to_data_js_without_a_full_rebuild(self):
        self.init(debounce_seconds=1000)
        self.bind()
        self.hook('stop', self.payload('claude_pre_task.json', tool_name=None), now='2026-10-15T12:00:00Z')  # forced refresh
        before = self.read_data_js()
        self.assertFalse(before['collection']['dirty'])
        self.assertEqual(self.hook('pre_tool_use', self.payload('claude_pre_task.json'), now='2026-10-15T12:00:07Z'), 'dirty')
        after = self.read_data_js()
        self.assertTrue(after['collection']['dirty'])
        self.assertEqual(after['collection']['last_event_at'], '2026-10-15T12:00:07Z')
        self.assertGreater(after['rev'], before['rev'])  # the UI ignores a document that does not advance rev
        self.assertEqual(after['lanes'], before['lanes'])  # cheap: nothing else was rebuilt
        report = json.loads(self.ctx.report.read_text(encoding='utf-8'))
        self.assertEqual(report['rev'], after['rev'])
        # the next verb or final refresh clears it and continues the rev sequence
        self.cli('refresh')
        cleared = self.read_data_js()
        self.assertFalse(cleared['collection']['dirty'])
        self.assertGreater(cleared['rev'], after['rev'])
        self.assertTrue(any(l['origin'] == 'host-child' for l in cleared['lanes']))

    def test_hook_after_the_debounce_window_performs_the_deferred_refresh(self):
        self.init(debounce_seconds=1000)
        self.bind()
        self.hook('pre_tool_use', self.payload('claude_pre_task.json'), now='2026-10-15T12:00:07Z')
        state = json.loads(self.ctx.state.read_text())
        state['last_refresh_ts'] = time.time() - 2000
        self.ctx.state.write_text(json.dumps(state))
        self.assertEqual(self.hook('post_tool_use', self.payload('claude_pre_task.json', tool_name='Bash', tool_input={}),
                                   now='2026-10-15T12:50:00Z'), 'refreshed')
        data = self.read_data_js()
        self.assertFalse(data['collection']['dirty'])
        self.assertTrue(any(l['origin'] == 'host-child' for l in data['lanes']))


class F11DuplicateConflicts(Project):
    def write_run(self, folder, run_id, final, harness, started='2026-10-15T10:00:00Z'):
        d = self.root / folder / run_id
        d.mkdir(parents=True)
        body = {'run_id': run_id, 'harness': harness, 'started_at': started}
        if final:
            body.update(status='successful', ended_at='2026-10-15T10:05:00Z')
        (d / ('result.json' if final else 'meta.json')).write_text(json.dumps(body), encoding='utf-8')

    def test_conflict_with_a_later_live_duplicate_stays_on_the_final_record(self):
        self.write_run('a', 'run-x', True, 'codex')
        self.write_run('b', 'run-x', False, 'claude')
        code, text = self.cli('runs', '--json', '--runs-dir', 'a', '--runs-dir', 'b', '--now', '2026-10-15T10:06:00Z')
        self.assertEqual(code, 0)
        data = json.loads(text)
        run = data['runs'][0]
        self.assertEqual((run['harness'], run['phase']), ('codex', 'done'))
        self.assertEqual(run['conflict'], ['harness'])
        self.assertEqual(data['duplicates'], ['run-x'])

    def test_conflicts_accumulate_across_three_roots(self):
        self.write_run('a', 'run-x', True, 'codex')
        self.write_run('b', 'run-x', False, 'claude')
        self.write_run('c', 'run-x', False, 'codex', started='2026-10-15T09:00:00Z')
        code, text = self.cli('runs', '--json', '--runs-dir', 'a', '--runs-dir', 'b', '--runs-dir', 'c', '--now', '2026-10-15T10:06:00Z')
        self.assertEqual(json.loads(text)['runs'][0]['conflict'], ['harness', 'started_at'])


class F13WorkflowDecisions(Project):
    def decisions(self, *items):
        folder = self.feature_dir / 'workflow'
        folder.mkdir(exist_ok=True)
        (folder / 'decisions.json').write_text(json.dumps({'version': 1, 'feature': 'specs/001-demo', 'issue': 'a/b#1',
                                                           'decisions': list(items)}), encoding='utf-8')

    def made(self):
        return {d['id']: d for d in model.build(self.ctx, NOW, 1, {})['decisions']['made']}

    def test_multiple_selection_keeps_every_selected_option_and_updated_at(self):
        self.init()
        self.decisions({'id': 'SD1', 'mode': 'multiple', 'options': ['Alpha', 'Beta', 'Gamma'], 'status': 'answered',
                        'option': None, 'selected': ['A', 'C'],
                        'answers': [{'option': 'A', 'source': 'comment', 'comment_id': 1, 'updated_at': '2026-10-15T09:00:00Z'},
                                    {'option': 'C', 'source': 'comment', 'comment_id': 1, 'updated_at': '2026-10-15T09:05:00Z'}]})
        item = self.made()['SD1']
        self.assertEqual(item['selected'], ['Alpha', 'Gamma'])
        self.assertEqual(item['at'], '2026-10-15T09:05:00Z')
        self.assertEqual(item['decided_by'], 'user')

    def test_single_selection_from_selected_list_or_option(self):
        self.init()
        self.decisions({'id': 'SD1', 'mode': 'single', 'options': ['Alpha', 'Beta'], 'status': 'answered', 'option': None,
                        'selected': ['B'], 'answers': [{'option': 'B', 'updated_at': '2026-10-15T08:00:00Z'}]},
                       {'id': 'SD2', 'mode': 'single', 'options': ['Alpha', 'Beta'], 'status': 'answered', 'option': 'A',
                        'selected': ['A'], 'answers': [{'option': 'A', 'created_at': '2026-10-15T07:00:00Z'}]})
        made = self.made()
        self.assertEqual((made['SD1']['selected'], made['SD1']['at']), ('Beta', '2026-10-15T08:00:00Z'))
        self.assertEqual((made['SD2']['selected'], made['SD2']['at']), ('Alpha', '2026-10-15T07:00:00Z'))

    def test_pending_decision_has_no_selection(self):
        self.init()
        self.decisions({'id': 'SD1', 'mode': 'multiple', 'options': ['Alpha', 'Beta'], 'status': 'pending', 'option': None,
                        'selected': [], 'answers': []})
        report = model.build(self.ctx, NOW, 1, {})
        self.assertEqual([d['id'] for d in report['decisions']['pending']], ['SD1'])
        self.assertIsNone(report['decisions']['pending'][0]['selected'])


class F15FeatureConfinement(Project):
    def link_dir(self, link, target):
        try:
            os.symlink(target, link, target_is_directory=True)
            return True
        except (OSError, NotImplementedError):
            pass
        if os.name == 'nt':
            done = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
            return done.returncode == 0
        return False

    def test_dot_components_are_rejected(self):
        for value in ('specs/..', 'specs/.', '..', '.', 'specs/../specs', 'specs/001-demo/..', './specs/001-demo/.'):
            with self.subTest(value=value):
                self.assertIsNone(normalise_feature(self.root, value))
        self.assertEqual(normalise_feature(self.root, 'specs/001-demo'), 'specs/001-demo')
        self.assertEqual(normalise_feature(self.root, '001-demo'), 'specs/001-demo')

    def test_dotdot_feature_via_cli_is_refused(self):
        code, line = self.cli('init', '--feature', 'specs/..')
        self.assertEqual((code, line.split()[:3]), (2, ['progress:', 'error', 'PROGRESS_NO_FEATURE']))

    def test_symlinked_feature_cannot_direct_writes_outside_the_repo(self):
        outside = Path(self.tmp.name).parent / (Path(self.tmp.name).name + '-outside')
        outside.mkdir()
        self.addCleanup(lambda: __import__('shutil').rmtree(outside, ignore_errors=True))
        if not self.link_dir(self.root / 'specs' / '002-link', outside):
            self.skipTest('symlinks/junctions unavailable without privilege')
        self.assertIsNone(normalise_feature(self.root, 'specs/002-link'))
        code, line = self.cli('init', '--feature', 'specs/002-link')
        self.assertEqual(code, 2)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_progress_directory_is_not_followed(self):
        outside = Path(self.tmp.name).parent / (Path(self.tmp.name).name + '-out2')
        outside.mkdir()
        self.addCleanup(lambda: __import__('shutil').rmtree(outside, ignore_errors=True))
        if not self.link_dir(self.feature_dir / 'progress', outside):
            self.skipTest('symlinks/junctions unavailable without privilege')
        with self.assertRaises(ProgressError):
            Ctx(self.root, 'specs/001-demo').check_confined()
        code, line = self.cli('init')
        self.assertEqual(code, 2, line)
        self.assertEqual(list(outside.iterdir()), [])

    def test_hook_with_a_forged_binding_outside_specs_is_dropped(self):
        self.init()
        self.cli('bind', '--session', 'forged')
        data = json.loads(self.ctx.bindings.read_text())
        data['sessions']['claude:forged']['feature'] = 'specs/..'
        self.ctx.bindings.write_text(json.dumps(data))
        self.assertIn(self.hook('pre_tool_use', {'session_id': 'forged', 'cwd': self.root.as_posix(), 'effort': {'level': 'low'}}),
                      ('error', 'dropped', 'uninitialised'))
        self.assertFalse((self.root / 'progress').exists())


class F16FactValidation(Project):
    def setUp(self):
        super().setUp()
        self.init()

    def refused(self, *args):
        before = self.ctx.facts.read_bytes()
        code, line = self.cli(*args)
        self.assertEqual((code, line.split()[:3]), (3, ['progress:', 'error', 'PROGRESS_FORBIDDEN_CONTENT']), line)
        self.assertEqual(self.ctx.facts.read_bytes(), before)

    def test_actor_is_constrained_and_secret_checked(self):
        self.refused('note', 'x', '--actor', 'agent:sk-abcdefghijklmnopqrstuv')
        self.refused('note', 'x', '--actor', 'password=hunter2hunter2')
        self.refused('note', 'x', '--actor', 'someone else')

    def test_valid_actors_pass(self):
        for actor in ('user', 'agent:coordinator', 'agent:codex-1.a_b', 'hook'):
            self.assertEqual(self.cli('note', 'fine', '--actor', actor)[0], 0, actor)

    def test_path_containment_uses_components_not_prefixes(self):
        root = self.root.as_posix()
        for bad in (f'{root}-evil/a.txt', f'{root}x/y', '/srv/data/x', '/Library/Keys/k', '\\\\fileserver\\share\\x', '//fileserver/share/x',
                    'C:\\Windows\\system32', f'{root}/../outside/x'):
            with self.subTest(bad=bad):
                self.refused('note', f'see {bad} for details')
        self.assertEqual(self.cli('note', f'see {root}/specs/001-demo/spec.md', )[0], 0)

    def test_every_string_field_is_validated(self):
        record = factslib.make('lane', 'L1', 'user', now=NOW, tasks=[], owner='/srv/secret', label='x',
                               requested={'harness': None, 'model': 'sk-abcdefghijklmnopqrstuv', 'effort': None}, state='open')
        with self.assertRaises(ProgressError):
            factslib.check(record, self.root)
        ok = factslib.make('lane', 'L1', 'user', now=NOW, tasks=['T001'], owner='agent-9f', label='x',
                           requested={'harness': 'codex', 'model': None, 'effort': None}, state='open')
        factslib.check(ok, self.root)

    def test_append_refuses_an_unchecked_forbidden_record(self):
        bad = factslib.make('note', 'N1', 'agent:' + 'x' * 5, now=NOW, text='token=abcdefghijk', target=None)
        with self.assertRaises(ProgressError):
            factslib.append(self.ctx.facts, bad, root=self.root)


class F17LogPaths(Project):
    def test_windows_and_posix_absolute_paths_normalise_on_any_platform(self):
        root = self.root
        cases = {'C:/Users/x/a.jsonl': 'external:a.jsonl', 'C:\\Users\\x\\a.jsonl': 'external:a.jsonl',
                 '/home/u/logs/a.jsonl': 'external:a.jsonl', '\\\\srv\\share\\a.jsonl': 'external:a.jsonl',
                 '//srv/share/a.jsonl': 'external:a.jsonl', 'logs/a.jsonl': 'logs/a.jsonl',
                 f'{root.as_posix()}/logs/a.jsonl': 'logs/a.jsonl', f'{root.as_posix()}-evil/a.jsonl': 'external:a.jsonl'}
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(progress._log_path(value, root), expected)

    def test_usage_json_with_a_foreign_absolute_log_is_stored_as_external(self):
        self.init()
        usage = self.root / 'usage.json'
        usage.write_text(json.dumps({'fidelity': 'exact', 'log': 'C:/Users/runner/a.jsonl', 'fresh_input': 1}), encoding='utf-8')
        code, line = self.cli('attempt', 'record', '--overhead', 'review', '--run', 'r1', '--status', 'done', '--usage-json', str(usage))
        self.assertEqual(code, 0, line)
        fact = [json.loads(x) for x in self.ctx.facts.read_text(encoding='utf-8').splitlines()][-1]
        self.assertEqual(fact['usage']['log'], 'external:a.jsonl')


if __name__ == '__main__':
    unittest.main()


class SlashWordsInNotes(unittest.TestCase):
    """Single-segment slash words are commands, not paths; two-segment POSIX paths outside the repo are refused."""

    def test_slash_command_allowed_and_posix_path_refused(self):
        import tempfile
        facts = factslib
        root = Path(tempfile.mkdtemp())
        self.assertEqual(facts.scan('run /speckit.tasks then /help', root), 'run /speckit.tasks then /help')
        with self.assertRaises(ProgressError):
            facts.scan('see /etc/passwd', root)
        with self.assertRaises(ProgressError):
            facts.scan('logs in /srv/data', root)
