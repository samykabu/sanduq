"""Regression tests for the cycle-1 review findings (F1 hygiene, F4 Windows flakes, F5a fast hook, F6/A8 publish once,
F8 referenced runs only, F10 dead code, A1 async launches, A2 restarts, A3 stable child lanes, A4 link targets)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import helpers
from helpers import SCRIPTS, Project
from sanduq_progress import model, paths, refresh, render_data, snapshot, util
from sanduq_progress.collect import runs as runscol

NOW = datetime(2026, 10, 15, 12, 30, tzinfo=timezone.utc)
HOOK = str(SCRIPTS / 'hook.py')


def stamp(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00'))


def can_symlink():
    with tempfile.TemporaryDirectory() as d:
        try:
            os.symlink(Path(d) / 'a', Path(d) / 'b')
            return True
        except (OSError, NotImplementedError):
            return False


class F1Hygiene(Project):
    def run_hook(self, event, payload):
        return subprocess.run([sys.executable, HOOK, event], input=json.dumps(payload), capture_output=True, text=True,
                              cwd=str(self.root), timeout=60, env={**os.environ, 'SANDUQ_PROGRESS_ROOT': str(self.root)})

    def test_runtime_files_are_excluded_from_git(self):
        for pattern in ('.specify/progress/diagnostics.log*', '.specify/progress/*.lock'):
            self.assertIn(pattern, paths.EXCLUDES)
        self.init()
        self.bind()
        self.hook('post_tool_use', self.payload('claude_pre_task.json', session_id='stranger', tool_name='Bash', tool_input={}))
        paths.git_exclude(self.root)
        status = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=all', '.specify'], cwd=self.root,
                                capture_output=True, text=True).stdout
        self.assertNotIn('diagnostics.log', status)
        self.assertNotIn('.lock', status)

    def test_uninitialised_project_gets_no_files_from_a_hook(self):
        payload = self.payload('claude_pre_task.json', session_id='stranger')
        self.assertEqual(self.hook('pre_tool_use', payload), 'dropped')
        self.assertEqual(self.hook('pre_tool_use', {}), 'dropped')
        result = self.run_hook('pre_tool_use', payload)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertFalse((self.root / '.specify' / 'progress').exists())

    def test_unbound_drop_is_logged_once_per_session_id(self):
        self.init()
        log = self.root / '.specify' / 'progress' / 'diagnostics.log'
        for _ in range(3):
            self.hook('pre_tool_use', self.payload('claude_pre_task.json', session_id='stranger-1'))
            self.assertEqual(self.run_hook('pre_tool_use', self.payload('claude_pre_task.json', session_id='stranger-1')).returncode, 0)
        self.run_hook('pre_tool_use', self.payload('claude_pre_task.json', session_id='stranger-2'))
        lines = [l for l in log.read_text(encoding='utf-8').splitlines() if 'unbound' in l]
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(any('stranger-1' in l for l in lines) and any('stranger-2' in l for l in lines))


class F4WindowsFlakes(Project):
    def test_atomic_write_retries_a_sharing_violation(self):
        target = self.root / 'x.json'
        real, calls = os.replace, []

        def flaky(src, dst):
            calls.append(1)
            if len(calls) < 4:
                raise PermissionError(13, 'sharing violation')
            return real(src, dst)

        with mock.patch('os.replace', flaky), mock.patch('time.sleep'):
            util.atomic_write(target, 'ok')
        self.assertEqual((target.read_text(), len(calls)), ('ok', 4))
        self.assertEqual([p.name for p in self.root.glob('*.tmp')], [])

    def test_atomic_write_gives_up_and_cleans_its_temp_file(self):
        with mock.patch('os.replace', side_effect=PermissionError(13, 'locked')), mock.patch('time.sleep'):
            with self.assertRaises(PermissionError):
                util.atomic_write(self.root / 'y.json', 'x')
        self.assertEqual([p.name for p in self.root.glob('*.tmp')], [])

    def test_directory_cleanup_helper_retries(self):
        calls = []

        class Flaky:
            def cleanup(self):
                calls.append(1)
                if len(calls) < 3:
                    raise PermissionError(13, 'in use')

        with mock.patch('time.sleep'):
            helpers.remove_tree(Flaky())
        self.assertEqual(len(calls), 3)


class F5FastHook(Project):
    def run_hook(self, event, payload, profile=False):
        env = {**os.environ, 'SANDUQ_PROGRESS_ROOT': str(self.root)}
        if profile:
            env['PYTHONPROFILEIMPORTTIME'] = '1'
        return subprocess.run([sys.executable, HOOK, event], input=json.dumps(payload), capture_output=True, text=True,
                              cwd=str(self.root), timeout=60, env=env)

    def test_hook_commands_use_the_fast_entry(self):
        files = list((SCRIPTS.parent / 'commands').glob('hook-*.md'))
        self.assertEqual(len(files), 5)
        for path in files:
            self.assertIn('scripts/hook.py ', path.read_text(encoding='utf-8'), path.name)

    def test_unbound_session_exits_before_importing_progress_or_argparse(self):
        self.init()
        result = self.run_hook('pre_tool_use', self.payload('claude_pre_task.json', session_id='stranger'), profile=True)
        self.assertEqual((result.returncode, result.stdout), (0, ''))
        import re
        for heavy in ('sanduq_progress', 'argparse', 'subprocess', 'shutil', 'secrets', 'dataclasses', 'tempfile'):
            self.assertIsNone(re.search(rf'\|\s+{heavy}(\.\w+)*\s*$', result.stderr, re.M), heavy)

    def test_bound_session_is_recorded_through_the_fast_entry(self):
        self.init(debounce_seconds=1000)
        self.bind()
        result = self.run_hook('pre_tool_use', self.payload('claude_pre_task.json'))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertEqual(len(self.snap()['children']), 1)

    def test_bind_handshake_still_works_through_the_fast_entry(self):
        import test_hosts
        nonce = self.init()
        data = json.loads(self.ctx.bindings.read_text())
        data['pending'][0]['created_at'] = util.iso(util.utcnow())  # the subprocess uses the real clock
        self.ctx.bindings.write_text(json.dumps(data))
        result = self.run_hook('post_tool_use', test_hosts.bash_bind_payload(self, 'claude-sess-9', nonce))
        self.assertEqual(result.returncode, 0)
        self.assertIn('claude:claude-sess-9', json.loads(self.ctx.bindings.read_text())['sessions'])

    def test_garbage_input_is_silent(self):
        self.init()
        for raw in ('', 'nope', '[1]'):
            result = subprocess.run([sys.executable, HOOK, 'stop'], input=raw, capture_output=True, text=True,
                                    cwd=str(self.root), env={**os.environ, 'SANDUQ_PROGRESS_ROOT': str(self.root)})
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))


class F6PublishOnce(Project):
    def test_100_debounced_events_write_the_projection_once(self):
        self.init(debounce_seconds=1000)
        self.bind()
        self.hook('stop', self.payload('claude_pre_task.json', tool_name=None), now='2026-10-15T12:00:00Z')
        self.assertNotIn('final_at', json.loads(self.ctx.state.read_text()))
        with mock.patch.object(render_data, 'write', wraps=render_data.write) as write:
            for i in range(100):
                second = f'2026-10-15T12:{1 + i // 60:02d}:{i % 60:02d}Z'
                self.assertEqual(self.hook('pre_tool_use', self.payload('claude_pre_task.json', tool_name='Bash', tool_input={}),
                                           now=second), 'dirty')
            self.assertEqual(write.call_count, 1)
        state = json.loads(self.ctx.state.read_text())
        self.assertTrue(state['dirty'])
        self.assertEqual(state['last_event_at'], '2026-10-15T12:02:39Z')  # the latest event moved only state.json
        self.assertTrue(self.report()['collection']['dirty'])
        self.assertEqual(self.report()['rev'], state['rev'])
        self.cli('refresh')
        cleared = self.report()
        self.assertFalse(cleared['collection']['dirty'])
        self.assertEqual(cleared['collection']['last_event_at'], '2026-10-15T12:02:39Z')
        self.assertNotIn('dirty_published', json.loads(self.ctx.state.read_text()))

    def test_a_failed_first_publish_is_retried_by_the_next_event(self):
        self.init(debounce_seconds=1000)
        self.bind()
        self.ctx.report.unlink()  # nothing to patch yet
        self.hook('pre_tool_use', self.payload('claude_pre_task.json', tool_name='Bash', tool_input={}), now='2026-10-15T12:01:00Z')
        self.assertFalse(self.ctx.report.exists())
        state = json.loads(self.ctx.state.read_text())
        self.assertTrue(state['dirty'] and not state.get('dirty_published'))


class F8ReferencedRuns(Project):
    def make_run(self, folder, run_id):
        path = self.root / '.delegate' / 'runs' / folder
        path.mkdir(parents=True)
        (path / 'result.json').write_text(json.dumps({'run_id': run_id, 'harness': 'codex', 'status': 'successful',
                                                      'started_at': '2026-10-15T10:00:00Z', 'ended_at': '2026-10-15T11:00:00Z'}),
                                          encoding='utf-8')

    def ledger(self, *run_ids):
        folder = self.feature_dir / 'workflow'
        folder.mkdir(exist_ok=True)
        rows = [{'identity': 'specs/001-demo/T002', 'run_id': r, 'status': 'successful', 'requested_harness': 'codex',
                 'started_at': '2026-10-15T10:00:00Z', 'ended_at': '2026-10-15T11:00:00Z'} for r in run_ids]
        (folder / 'delegations.json').write_text(json.dumps({'attempts': rows}), encoding='utf-8')

    def build_counting(self):
        with mock.patch.object(runscol, 'project_run', wraps=runscol.project_run) as read:
            report = model.build(self.ctx, NOW, 1, {})
        return read.call_count, report

    def test_only_runs_referenced_by_the_ledger_are_read(self):
        for i in range(20):
            self.make_run(f'run-{i}', f'run-{i}')
        self.ledger('run-7')
        count, report = self.build_counting()
        self.assertEqual(count, 1)
        self.assertEqual(report['lanes'][0]['attempts'][0]['run_id'], 'run-7')

    def test_no_ledger_reads_no_runs(self):
        for i in range(5):
            self.make_run(f'run-{i}', f'run-{i}')
        self.assertEqual(self.build_counting()[0], 0)

    def test_run_stored_under_another_folder_name_is_still_found(self):
        self.make_run('first', 'run-1')
        self.make_run('second', 'run-9')
        self.ledger('run-9')
        count, _ = self.build_counting()
        self.assertEqual(count, 2)  # fell back to the full scan because no folder carries the id's name
        found = runscol.collect_runs(self.root / '.delegate' / 'runs', only={'run-9'})
        self.assertEqual([r['run_id'] for r in found], ['run-9'])

    def test_runs_verb_stays_complete(self):
        for i in range(4):
            self.make_run(f'run-{i}', f'run-{i}')
        self.ledger('run-1')
        code, out = self.cli('runs', '--json')
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)['runs']), 4)


class F10DeadCode(unittest.TestCase):
    def test_removed_helpers_are_gone(self):
        from sanduq_progress import lock
        self.assertFalse(hasattr(lock, 'pid_alive'))
        self.assertFalse(hasattr(refresh, 'count_dropped'))
        js = (SCRIPTS.parent / 'assets' / 'ui' / 'blocks.js').read_text(encoding='utf-8')
        self.assertEqual(js.count('function selectedList('), 1)


class A1AsyncLaunch(Project):
    def spawn(self, event, **response):
        payload = {'session_id': 'codex-sess-1', 'turn_id': 't1', 'cwd': self.root.as_posix(), 'model': 'gpt-6.1-sol',
                   'tool_name': 'spawn_agent', 'tool_use_id': 'call_1', 'tool_input': {'agent_type': 'worker', 'message': 'go'}}
        if response:
            payload['tool_response'] = response
        return self.hook(event, payload, host='codex', now='2026-10-15T12:10:00Z')

    def test_spawn_response_is_not_completion(self):
        self.init(debounce_seconds=0)
        self.bind('codex-sess-1', 'codex')
        self.spawn('pre_tool_use')
        self.spawn('post_tool_use', agent_id='agent-x')
        child = self.snap('codex-sess-1', 'codex')['children']['call_1']
        self.assertEqual((child['status'], child['ended_at'], child['agent_id']), ('running', None, 'agent-x'))
        stop = {'session_id': 'codex-sess-1', 'turn_id': 't2', 'agent_id': 'agent-x', 'agent_type': 'worker',
                'cwd': self.root.as_posix(), 'hook_event_name': 'Stop', 'parent_session_id': 'codex-sess-1'}
        self.hook('stop', stop, host='codex', now='2026-10-15T12:20:00Z')
        child = self.snap('codex-sess-1', 'codex')['children']['call_1']
        self.assertEqual((child['status'], child['ended_at']), ('done', '2026-10-15T12:20:00Z'))

    def test_failed_spawn_is_terminal_and_claude_background_task_stays_running(self):
        self.init(debounce_seconds=0)
        self.bind('codex-sess-1', 'codex')
        self.spawn('post_tool_use', error='no capacity')
        self.assertEqual(self.snap('codex-sess-1', 'codex')['children']['call_1']['status'], 'failed')
        self.bind()
        task = self.payload('claude_post_task.json')
        task['tool_input']['run_in_background'] = True
        self.hook('post_tool_use', task)
        self.assertEqual(self.snap()['children']['toolu_01TASK']['status'], 'running')


class A2Restart(Project):
    def put(self, status, at, **extra):
        snapshot.merge(self.ctx, 'claude', 's1', stamp(at), child={'key': 'agent-1', 'update': {
            'status': status, 'last_observed_at': at, **extra}})
        return json.loads(snapshot.snapshot_path(self.ctx, 'claude', 's1').read_text())['children']['agent-1']

    def test_newer_running_observation_after_done_starts_a_new_generation(self):
        self.init()
        self.put('running', '2026-10-15T12:00:00Z', started_at='2026-10-15T12:00:00Z')
        done = self.put('done', '2026-10-15T12:05:00Z', ended_at='2026-10-15T12:05:00Z')
        self.assertEqual((done['status'], done['ended_at']), ('done', '2026-10-15T12:05:00Z'))
        again = self.put('running', '2026-10-15T12:10:00Z')
        self.assertEqual((again['status'], again['ended_at'], again['started_at'], again['generation']),
                         ('running', None, '2026-10-15T12:10:00Z', 2))
        finished = self.put('done', '2026-10-15T12:15:00Z', ended_at='2026-10-15T12:15:00Z')
        self.assertEqual((finished['status'], finished['ended_at']), ('done', '2026-10-15T12:15:00Z'))

    def test_stale_running_observation_is_rejected(self):
        self.init()
        self.put('done', '2026-10-15T12:05:00Z', ended_at='2026-10-15T12:05:00Z')
        stale = self.put('running', '2026-10-15T12:04:00Z')
        self.assertEqual((stale['status'], stale['ended_at']), ('done', '2026-10-15T12:05:00Z'))
        self.assertNotIn('generation', stale)
        self.assertEqual(self.put('running', '2026-10-15T12:05:00Z')['status'], 'done')

    def test_restart_reaches_the_projection(self):
        self.init(debounce_seconds=0)
        self.bind()
        for status, at, extra in (('running', '2026-10-15T12:00:00Z', {}),
                                  ('done', '2026-10-15T12:05:00Z', {'ended_at': '2026-10-15T12:05:00Z'}),
                                  ('running', '2026-10-15T12:10:00Z', {})):
            snapshot.merge(self.ctx, 'claude', 'claude-sess-1', stamp(at), child={'key': 'agent-1', 'update': {
                'status': status, 'last_observed_at': at, 'started_at': '2026-10-15T12:00:00Z', **extra}})
        report = model.build(self.ctx, stamp('2026-10-15T12:12:00Z'), 1, {})
        lane = next(l for l in report['lanes'] if l['origin'] == 'host-child')
        self.assertEqual(lane['status'], 'active')


class A3StableChildLanes(Project):
    def children(self, *names):
        for i, name in enumerate(names, 1):
            snapshot.merge(self.ctx, 'claude', 'claude-sess-1', NOW, child={'key': name, 'update': {
                'agent_id': name, 'description': f'work {name}', 'status': 'running', 'started_at': f'2026-10-15T12:0{i}:00Z',
                'last_observed_at': '2026-10-15T12:20:00Z'}})

    def ids(self, report):
        return {l['owner']: l['id'] for l in report['lanes'] if l['origin'] == 'host-child'}

    def test_ids_do_not_renumber_when_another_child_merges_into_a_lane(self):
        self.init(debounce_seconds=0)
        self.bind()
        self.children('agent-a', 'agent-b', 'agent-c')
        state = {}
        self.assertEqual(self.ids(model.build(self.ctx, NOW, 1, state)), {'agent-a': 'C1', 'agent-b': 'C2', 'agent-c': 'C3'})
        self.cli('lane', 'L1', '--tasks', 'T002', '--owner', 'agent-a')
        self.cli('block', 'C2', '--by', 'ext:waiting')
        report = model.build(self.ctx, NOW, 2, state)
        self.assertEqual(self.ids(report), {'agent-b': 'C2', 'agent-c': 'C3'})
        blocker = next(b for b in report['blockers'] if b['target'] == 'C2')
        self.assertEqual(next(l for l in report['lanes'] if l['id'] == blocker['target'])['owner'], 'agent-b')

    def test_new_children_get_fresh_ids_and_state_survives_refresh(self):
        self.init(debounce_seconds=0)
        self.bind()
        self.children('agent-a', 'agent-b')
        self.cli('refresh')
        self.cli('lane', 'L1', '--tasks', 'T002', '--owner', 'agent-a')
        self.children('agent-z')
        self.cli('refresh')
        self.assertEqual(self.ids(self.report()), {'agent-b': 'C2', 'agent-z': 'C3'})  # C1 is never reused


@unittest.skipUnless(can_symlink(), 'symlinks are not available here')
class A4LinkTargets(Project):
    def outside(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        victim = folder / 'victim.txt'
        victim.write_text('untouched', encoding='utf-8')
        return victim

    def test_facts_file_symlink_is_refused(self):
        self.init()
        victim = self.outside()
        self.ctx.facts.unlink(missing_ok=True)
        os.symlink(victim, self.ctx.facts)
        code, line = self.cli('note', 'hello')
        self.assertEqual(code, 3, line)
        self.assertIn('PROGRESS_UNSAFE_TARGET', line)
        self.assertEqual(victim.read_text(encoding='utf-8'), 'untouched')

    def test_view_file_symlink_is_refused(self):
        self.init()
        victim = self.outside()
        self.ctx.data_js.unlink()
        os.symlink(victim, self.ctx.data_js)
        code, line = self.cli('refresh')
        self.assertEqual(code, 3, line)
        self.assertEqual(victim.read_text(encoding='utf-8'), 'untouched')

    def test_copied_asset_symlink_is_refused(self):
        self.init()
        victim = self.outside()
        asset = self.ctx.view / 'blocks.js'
        asset.unlink()
        os.symlink(victim, asset)
        code, line = self.cli('init')
        self.assertEqual(code, 3, line)
        self.assertEqual(victim.read_text(encoding='utf-8'), 'untouched')

    def test_lock_file_symlink_is_refused(self):
        from sanduq_progress.lock import Lock
        self.init()
        victim = self.outside()
        self.ctx.lock.unlink(missing_ok=True)
        os.symlink(victim, self.ctx.lock)
        with self.assertRaises(util.ProgressError):
            Lock(self.ctx.lock, retries=0).acquire()
        self.assertEqual(victim.read_text(encoding='utf-8'), 'untouched')


class A4Detection(Project):
    @unittest.skipUnless(os.name == 'nt', 'junctions are a Windows feature')
    def test_a_junction_is_a_link_and_a_plain_directory_is_not(self):
        real = self.root / 'real'
        real.mkdir()
        junction = self.root / 'junction'
        done = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(real)], capture_output=True, text=True)
        if done.returncode != 0:
            self.skipTest('mklink /J unavailable')
        self.assertTrue(util.is_link(junction))
        self.assertFalse(util.is_link(real))
        self.assertFalse(util.is_link(self.root / 'missing'))
        with self.assertRaises(util.ProgressError):
            util.refuse_link(junction)


if __name__ == '__main__':
    unittest.main()
