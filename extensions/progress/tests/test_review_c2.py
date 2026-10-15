"""Regression tests for the cycle-2 review findings (F1 duplicate lane, F5 agent id fallback, A1 fast logger, A2 stale
terminal, A3 durable child identity, A4 referenced run ids, A5 empty referenced set)."""
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from helpers import SCRIPTS, Project
from sanduq_progress import hosts, model, snapshot
from sanduq_progress.collect import runs as runscol
from test_review_c1 import HOOK, can_symlink, stamp

NOW = datetime(2026, 10, 15, 12, 30, tzinfo=timezone.utc)


def child_lanes(report):
    return [l for l in report['lanes'] if l['origin'] == 'host-child']


class F1DuplicateLane(Project):
    def start(self):
        self.init(debounce_seconds=0)
        self.bind()
        self.hook('pre_tool_use', self.payload('claude_pre_task.json'), now='2026-10-15T12:00:00Z')
        self.hook('post_tool_use', self.payload('claude_child_event.json'), now='2026-10-15T12:01:00Z')

    def build(self, at='2026-10-15T12:02:00Z'):
        return model.build(self.ctx, stamp(at), 1, {})

    def test_one_running_subagent_is_one_lane(self):
        self.start()
        lanes = child_lanes(self.build())
        self.assertEqual(len(lanes), 1, [(l['id'], l['owner']) for l in lanes])
        children = self.snap()['children']
        self.assertEqual(list(children), ['toolu_01TASK'])
        self.assertEqual(children['toolu_01TASK']['agent_id'], 'agent-9f')

    def test_the_tool_result_confirms_the_link(self):
        self.start()
        self.hook('post_tool_use', self.payload('claude_post_task.json'), now='2026-10-15T12:03:00Z')
        lanes = child_lanes(self.build('2026-10-15T12:04:00Z'))
        self.assertEqual([l['status'] for l in lanes], ['done'])
        self.assertEqual(list(self.snap()['children']), ['toolu_01TASK'])

    def test_a_different_agent_id_in_the_tool_result_splits_the_link(self):
        self.start()
        post = self.payload('claude_post_task.json')
        post['tool_response']['agentId'] = 'agent-other'
        self.hook('post_tool_use', post, now='2026-10-15T12:03:00Z')
        children = self.snap()['children']
        self.assertEqual(set(children), {'toolu_01TASK', 'agent-9f'})
        self.assertEqual(children['toolu_01TASK']['agent_id'], 'agent-other')
        self.assertEqual(children['agent-9f']['status'], 'running')
        self.assertEqual(len(child_lanes(self.build('2026-10-15T12:04:00Z'))), 2)

    def test_two_running_launches_are_never_guessed(self):
        self.init(debounce_seconds=0)
        self.bind()
        for tool_id in ('toolu_A', 'toolu_B'):
            self.hook('pre_tool_use', self.payload('claude_pre_task.json', tool_use_id=tool_id), now='2026-10-15T12:00:00Z')
        self.hook('post_tool_use', self.payload('claude_child_event.json'), now='2026-10-15T12:01:00Z')
        self.assertEqual(len(self.snap()['children']), 3)


class F5AgentIdFallback(unittest.TestCase):
    def update(self, tool_name, response):
        payload = {'tool_name': tool_name, 'tool_use_id': 't1', 'tool_input': {}, 'tool_response': response}
        return hosts.subagent_child(payload, 'post_tool_use', NOW, 'hook', 'claude')['update']

    def test_a_bare_id_is_not_an_agent_id(self):
        self.assertNotIn('agent_id', self.update('Agent', {'id': 'msg_123'}))
        self.assertEqual(self.update('Agent', {'agentId': 'a1'})['agent_id'], 'a1')

    def test_codex_spawn_agent_may_use_its_id(self):
        self.assertEqual(self.update('spawn_agent', {'id': 'thread-7'})['agent_id'], 'thread-7')


class A1FastLogger(Project):
    def setUp(self):
        super().setUp()
        self.init()
        self.log = self.root / '.specify' / 'progress' / 'diagnostics.log'

    def run_hook(self, session):
        payload = self.payload('claude_pre_task.json', session_id=session)
        return subprocess.run([sys.executable, HOOK, 'pre_tool_use'], input=json.dumps(payload), capture_output=True, text=True,
                              cwd=str(self.root), timeout=60, env={**os.environ, 'SANDUQ_PROGRESS_ROOT': str(self.root)})

    def test_oversized_log_is_rotated_on_the_fast_path(self):
        self.log.write_text('x' * (300 * 1024), encoding='utf-8')
        result = self.run_hook('stranger')
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertLess(self.log.stat().st_size, 1024)
        self.assertGreater(self.log.with_name('diagnostics.log.1').stat().st_size, 256 * 1024)
        self.assertIn('stranger', self.log.read_text(encoding='utf-8'))

    @unittest.skipUnless(can_symlink(), 'symlinks are not available here')
    def test_a_linked_log_is_not_written_through(self):
        outside = self.root.parent / f'{self.root.name}-outside.log'
        outside.write_text('keep\n', encoding='utf-8')
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        os.symlink(outside, self.log)
        self.assertEqual(self.run_hook('stranger').returncode, 0)
        self.assertEqual(outside.read_text(encoding='utf-8'), 'keep\n')

    def test_the_shared_helper_imports_only_light_modules(self):
        path = str(SCRIPTS / 'sanduq_progress' / 'safelog.py')
        code = (f"import sys, importlib.util as u; s = u.spec_from_file_location('safelog', {path!r}); m = u.module_from_spec(s); s.loader.exec_module(m); "
                "print(sorted(m for m in ('json', 're', 'datetime', 'pathlib', 'tempfile') if m in sys.modules))")
        out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), '[]', out)


class A2StaleTerminal(Project):
    def put(self, status, at, **extra):
        snapshot.merge(self.ctx, 'claude', 's1', stamp(at), child={'key': 'agent-1', 'update': {
            'status': status, 'last_observed_at': at, **extra}})
        return json.loads(snapshot.snapshot_path(self.ctx, 'claude', 's1').read_text())['children']['agent-1']

    def test_a_delayed_done_does_not_end_a_newer_generation(self):
        self.init()
        self.put('running', '2026-10-15T12:00:00Z', started_at='2026-10-15T12:00:00Z')
        self.put('done', '2026-10-15T12:05:00Z', ended_at='2026-10-15T12:05:00Z')
        self.put('running', '2026-10-15T12:10:00Z')
        late = self.put('done', '2026-10-15T12:05:00Z', ended_at='2026-10-15T12:05:00Z')
        self.assertEqual((late['status'], late['generation'], late['started_at'], late['ended_at']),
                         ('running', 2, '2026-10-15T12:10:00Z', None))
        self.assertEqual(late['last_observed_at'], '2026-10-15T12:10:00Z')

    def test_a_current_done_still_ends_the_generation(self):
        self.init()
        self.put('running', '2026-10-15T12:00:00Z', started_at='2026-10-15T12:00:00Z')
        self.put('done', '2026-10-15T12:05:00Z', ended_at='2026-10-15T12:05:00Z')
        self.put('running', '2026-10-15T12:10:00Z')
        done = self.put('done', '2026-10-15T12:15:00Z', ended_at='2026-10-15T12:15:00Z')
        self.assertEqual((done['status'], done['ended_at'], done['generation']), ('done', '2026-10-15T12:15:00Z', 2))


class A3DurableChildLane(Project):
    def child(self, key, at, by_agent=False, **extra):
        snapshot.merge(self.ctx, 'claude', 'claude-sess-1', stamp(at), child={'key': key, 'by_agent': by_agent, 'update': {
            'description': f'work {key}', 'status': 'running', 'started_at': at, 'last_observed_at': at, **extra}})

    def owners(self, report):
        return {l['owner']: l['id'] for l in child_lanes(report)}

    def test_a_blocker_survives_deleting_the_disposable_view(self):
        self.init(debounce_seconds=0)
        self.bind()
        for i, name in enumerate(('agent-a', 'agent-b', 'agent-c'), 1):
            self.child(name, f'2026-10-15T12:0{i}:00Z', agent_id=name)
        self.assertEqual(self.owners(model.build(self.ctx, NOW, 1, {})), {'agent-a': 'C1', 'agent-b': 'C2', 'agent-c': 'C3'})
        self.cli('lane', 'L1', '--tasks', 'T002', '--owner', 'agent-a')
        self.cli('block', 'C2', '--by', 'ext:waiting')
        self.cli('refresh')
        self.assertEqual(self.owners(self.report()), {'agent-b': 'C2', 'agent-c': 'C3'})
        for path in self.ctx.view.glob('state.json'):
            path.unlink()
        report = model.build(self.ctx, NOW, 1, {})
        self.assertEqual(self.owners(report), {'agent-b': 'C2', 'agent-c': 'C3'})
        self.assertTrue(any(b['target'] == 'C2' for b in report['blockers']))

    def test_a_blocker_survives_a_key_change_between_agent_id_and_tool_use_id(self):
        self.init(debounce_seconds=0)
        self.bind()
        self.child('agent-x', '2026-10-15T12:01:00Z')
        self.child('toolu_Y', '2026-10-15T12:02:00Z')
        state = {}
        self.assertEqual(self.owners(model.build(self.ctx, NOW, 1, state)), {'agent-x': 'C1', 'toolu_Y': 'C2'})
        self.cli('block', 'C2', '--by', 'ext:waiting')
        # the tool result later names the agent id: the entry keeps its number whatever its key becomes
        self.child('toolu_Y', '2026-10-15T12:03:00Z', agent_id='agent-y')
        report = model.build(self.ctx, NOW, 2, state)
        self.assertEqual(self.owners(report), {'agent-x': 'C1', 'agent-y': 'C2'})
        self.child('agent-y', '2026-10-15T12:04:00Z', by_agent=True)  # an agent-keyed event for it merges, never renumbers
        self.assertEqual(self.owners(model.build(self.ctx, NOW, 3, {})), {'agent-x': 'C1', 'agent-y': 'C2'})
        self.assertTrue(any(b['target'] == 'C2' for b in report['blockers']))

    def test_a_retired_number_still_resolves_to_the_merged_lane(self):
        self.init(debounce_seconds=0)
        self.bind()
        self.child('agent-a', '2026-10-15T12:01:00Z')
        self.child('toolu_A', '2026-10-15T12:02:00Z')
        self.assertEqual(sorted(self.owners(model.build(self.ctx, NOW, 1, {})).values()), ['C1', 'C2'])
        self.cli('block', 'C2', '--by', 'ext:waiting')
        self.child('toolu_A', '2026-10-15T12:03:00Z', agent_id='agent-a')
        report = model.build(self.ctx, NOW, 2, {})
        lanes = child_lanes(report)
        self.assertEqual(len(lanes), 1)
        blocker = next(b for b in report['blockers'] if b['source'] == 'facts')
        self.assertEqual(blocker['target'], lanes[0]['id'])


class A4A5ReferencedRuns(Project):
    def make_run(self, folder, run_id):
        path = self.root / '.delegate' / 'runs' / folder
        path.mkdir(parents=True)
        (path / 'result.json').write_text(json.dumps({'run_id': run_id, 'harness': 'codex', 'status': 'successful',
                                                      'started_at': '2026-10-15T10:00:00Z', 'ended_at': '2026-10-15T11:00:00Z'}),
                                          encoding='utf-8')

    def test_a_directory_name_is_not_a_run_id(self):
        self.make_run('wanted', 'other')
        self.make_run('renamed', 'wanted')
        found = runscol.collect_runs(self.root / '.delegate' / 'runs', only={'wanted'})
        self.assertEqual([r['run_id'] for r in found], ['wanted'])

    def test_a_found_run_is_not_scanned_for_again(self):
        self.make_run('run-1', 'run-1')
        self.make_run('run-2', 'run-2')
        with mock.patch.object(runscol, 'project_run', wraps=runscol.project_run) as read:
            found = runscol.collect_runs(self.root / '.delegate' / 'runs', only={'run-1'})
        self.assertEqual((read.call_count, [r['run_id'] for r in found]), (1, ['run-1']))

    def test_an_empty_set_returns_without_touching_the_history(self):
        self.make_run('run-1', 'run-1')
        folder = self.root / '.delegate' / 'runs'
        with mock.patch.object(Path, 'iterdir', side_effect=AssertionError('listed')), \
                mock.patch.object(Path, 'is_dir', side_effect=AssertionError('stat')):
            self.assertEqual(runscol.collect_runs(folder, only=set()), [])


if __name__ == '__main__':
    unittest.main()
