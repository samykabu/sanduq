"""Regression tests for the round-2 code-review findings (one class per finding, named F<n>, same numbering as the review)."""
import json
import os
import shutil
import subprocess
import sys
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

import helpers
from helpers import Project
from sanduq_progress import model, snapshot
from sanduq_progress.lock import Lock, LockBusy
from sanduq_progress.paths import Ctx, ProgressError, normalise_feature
from test_review_r1 import WorkflowFiles

NOW = datetime(2026, 10, 15, 12, 30, tzinfo=timezone.utc)


def link_dir(link, target):
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name == 'nt':
        done = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
        return done.returncode == 0
    return False


class F01OsHeldLock(Project):
    def setUp(self):
        super().setUp()
        self.path = self.root / 'lockfile'

    def test_threads_never_hold_the_lock_together(self):
        inside, worst, errors = [0], [0], []
        guard = threading.Lock()

        def worker():
            for _ in range(15):
                try:
                    with Lock(self.path, retries=400, delay=0.002):
                        with guard:
                            inside[0] += 1
                            worst[0] = max(worst[0], inside[0])
                        with guard:
                            inside[0] -= 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(worst[0], 1)

    def test_stale_looking_metadata_and_an_old_guard_file_never_admit_a_second_holder(self):
        # The reviewer's scenario: a dead owner's metadata plus an expired .recover guard. Whoever holds the OS lock
        # owns it; nobody can take it by reading or deleting files.
        self.path.write_text(json.dumps({'pid': 99999999, 'host': 'x', 'started_at': '2026-10-15T00:00:00Z'}))
        guard = self.path.with_name(self.path.name + '.recover')
        guard.write_text('{}')
        old = os.stat(guard).st_mtime - 60
        os.utime(guard, (old, old))
        first = Lock(self.path, retries=0).acquire()
        try:
            for _ in range(3):
                with self.assertRaises(LockBusy):
                    Lock(self.path, retries=0).acquire()
        finally:
            first.release()
        with Lock(self.path, retries=0):
            pass

    def test_a_killed_holder_releases_the_lock_without_recovery(self):
        code = ("import sys,time;sys.path.insert(0,r'%s');from sanduq_progress.lock import Lock;"
                "Lock(r'%s',retries=0).acquire();print('held',flush=True);time.sleep(60)" % (helpers.SCRIPTS, self.path))
        child = subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'held')
            with self.assertRaises(LockBusy):
                Lock(self.path, retries=0).acquire()
            child.kill()
            child.wait()
            with Lock(self.path, retries=40, delay=0.05):
                owner = json.loads(self.path.read_bytes().rstrip(b'\0').decode('utf-8'))
                self.assertEqual(owner['pid'], os.getpid())
        finally:
            child.kill()
            child.wait()
            child.stdout.close()

    def test_release_is_idempotent_and_reacquire_is_a_noop(self):
        lock = Lock(self.path, retries=0)
        self.assertIs(lock.acquire(), lock)
        self.assertIs(lock.acquire(), lock)
        lock.release()
        lock.release()
        with Lock(self.path, retries=0):
            pass


class F02AnchoredSpecsRoot(Project):
    def test_a_linked_specs_root_outside_the_repository_is_refused(self):
        outside = Path(self.tmp.name).parent / (Path(self.tmp.name).name + '-specs-out')
        outside.mkdir()
        self.addCleanup(lambda: shutil.rmtree(outside, ignore_errors=True))
        shutil.move(str(self.root / 'specs'), str(outside / 'specs'))
        if not link_dir(self.root / 'specs', outside / 'specs'):
            shutil.move(str(outside / 'specs'), str(self.root / 'specs'))
            self.skipTest('symlinks/junctions unavailable without privilege')
        self.addCleanup(lambda: os.rmdir(self.root / 'specs'))
        self.assertIsNone(normalise_feature(self.root, 'specs/001-demo'))
        with self.assertRaises(ProgressError):
            Ctx(self.root, 'specs/001-demo')
        code, _ = self.cli('init', '--feature', 'specs/001-demo')
        self.assertEqual(code, 2)
        self.assertFalse((outside / 'specs' / '001-demo' / 'progress').exists())


class F03ChildTerminalEvidence(Project):
    def child_events(self, status, ended='2026-10-15T12:12:00Z'):
        self.init(debounce_seconds=0)
        self.bind()
        self.cli('lane', 'L1', '--tasks', 'T002', '--owner', 'agent-9f')
        self.hook('pre_tool_use', self.payload('claude_pre_task.json'), now='2026-10-15T12:10:00Z')
        self.hook('post_tool_use', self.payload('claude_child_event.json'), now='2026-10-15T12:11:00Z')
        path = snapshot.snapshot_path(self.ctx, 'claude', 'claude-sess-1')
        snap = json.loads(path.read_text())
        for child in snap['children'].values():
            child.update(status=status, ended_at=ended)
        path.write_text(json.dumps(snap))
        return model.build(self.ctx, NOW, 1, json.loads(self.ctx.state.read_text()))

    def lane(self, report):
        return next(l for l in report['lanes'] if l['id'] == 'L1')

    def test_failed_child_fails_the_lane_and_stops_elapsed(self):
        lane = self.lane(self.child_events('failed'))
        self.assertEqual(lane['status'], 'failed')
        self.assertEqual(lane['tasks']['active'], [])
        self.assertEqual(lane['tasks']['waiting'], ['T002'])  # the checkbox is the task's truth
        self.assertEqual(lane['elapsed']['value'], 720)  # lane created 12:00, child ended 12:12, not NOW

    def test_finished_child_with_unchecked_tasks_is_waiting_not_active(self):
        lane = self.lane(self.child_events('done'))
        self.assertEqual(lane['status'], 'waiting')
        self.assertEqual(lane['tasks']['waiting'], ['T002'])

    def test_open_lane_blocker_outranks_a_finished_child(self):
        self.child_events('done')
        self.cli('block', 'L1', '--by', 'ext:waiting-on-review')
        report = model.build(self.ctx, NOW, 1, json.loads(self.ctx.state.read_text()))
        self.assertEqual(self.lane(report)['status'], 'blocked')

    def test_running_child_keeps_the_lane_active(self):
        lane = self.lane(self.child_events('running', ended=None))
        self.assertEqual(lane['status'], 'active')


class F04ObservedModelFlag(WorkflowFiles):
    def test_model_observed_true_with_actual_model_is_observed(self):
        self.init()
        self.delegations(self.attempt(run_id='run-flag'))
        self.run_result('run-flag', model='requested-alias', model_observed=True, actual_model='gpt-real')
        observed = self.lane_of(self.build(), 'specs/001-demo/T002')['observed']['model']
        self.assertEqual((observed['value'], observed['source']), ('gpt-real', 'run-result'))

    def test_flag_false_is_not_observed(self):
        self.init()
        self.delegations(self.attempt(run_id='run-no'))
        self.run_result('run-no', model='requested-alias', model_observed=False, actual_model='gpt-real')
        self.assertIsNone(self.lane_of(self.build(), 'specs/001-demo/T002')['observed']['model']['value'])


class F07NewestObservationWins(Project):
    def exact(self, value, at):
        return {'value': value, 'source': 'hook', 'observed_at': at, 'fidelity': 'exact'}

    def put(self, key, model_value, at, **extra):
        snapshot.merge(self.ctx, 'claude', 'claude-sess-1', datetime.fromisoformat(at.replace('Z', '+00:00')),
                       child={'key': key, 'update': {'agent_id': key, 'model': self.exact(model_value, at),
                                                      'last_observed_at': at, **extra}})

    def test_older_exact_model_never_replaces_a_newer_one_in_the_snapshot(self):
        self.init(debounce_seconds=0)
        self.put('agent-1', 'model-new', '2026-10-15T12:10:00Z')
        self.put('agent-1', 'model-old', '2026-10-15T12:05:00Z')
        self.assertEqual(self.snap()['children']['agent-1']['model']['value'], 'model-new')

    def test_newer_exact_model_replaces_an_older_one(self):
        self.init(debounce_seconds=0)
        self.put('agent-1', 'model-old', '2026-10-15T12:05:00Z')
        self.put('agent-1', 'model-new', '2026-10-15T12:10:00Z')
        self.assertEqual(self.snap()['children']['agent-1']['model']['value'], 'model-new')

    def test_multiple_matched_children_pick_the_newest_model_not_the_first(self):
        self.init(debounce_seconds=0)
        self.bind()
        self.cli('lane', 'L1', '--tasks', 'T002', '--owner', 'agent-9f')
        path = snapshot.snapshot_path(self.ctx, 'claude', 'claude-sess-1')
        self.put('agent-9f', 'model-old', '2026-10-15T12:05:00Z', started_at='2026-10-15T12:01:00Z')
        self.put('k-second', 'model-new', '2026-10-15T12:20:00Z', started_at='2026-10-15T12:02:00Z')
        snap = json.loads(path.read_text())
        snap['children']['k-second']['agent_id'] = 'agent-9f'
        path.write_text(json.dumps(snap))
        report = model.build(self.ctx, NOW, 1, {})
        lane = next(l for l in report['lanes'] if l['id'] == 'L1')
        self.assertEqual(lane['observed']['model']['value'], 'model-new')
        self.assertEqual([l for l in report['lanes'] if l['origin'] == 'host-child'], [])


class F08AmbiguousDescription(Project):
    def setup_children(self, owner, descriptions):
        self.init(debounce_seconds=0)
        self.bind()
        self.cli('lane', 'L1', '--tasks', 'T002', '--owner', owner)
        for i, text in enumerate(descriptions, 1):
            snapshot.merge(self.ctx, 'claude', 'claude-sess-1', NOW, child={'key': f'agent-{i}', 'update': {
                'agent_id': f'agent-{i}', 'description': text, 'started_at': f'2026-10-15T12:0{i}:00Z',
                'model': {'value': f'm{i}', 'source': 'hook', 'observed_at': f'2026-10-15T12:1{i}:00Z', 'fidelity': 'exact'}}})
        return model.build(self.ctx, NOW, 1, {})

    def test_two_children_with_the_same_description_stay_separate(self):
        report = self.setup_children('Explore the parser', ['Explore the parser', 'explore the PARSER'])
        self.assertEqual(len([l for l in report['lanes'] if l['origin'] == 'host-child']), 2)
        lane = next(l for l in report['lanes'] if l['id'] == 'L1')
        self.assertIsNone(lane['observed']['model']['value'])
        self.assertIn('matches 2 children', self.ctx.diag.read_text(encoding='utf-8'))
        model.build(self.ctx, NOW, 2, {})  # rebuilding does not repeat the diagnostic
        self.assertEqual(self.ctx.diag.read_text(encoding='utf-8').count('matches 2 children'), 1)

    def test_stable_id_still_merges_when_descriptions_collide(self):
        report = self.setup_children('agent-2', ['same', 'same'])
        lane = next(l for l in report['lanes'] if l['id'] == 'L1')
        self.assertEqual(lane['observed']['model']['value'], 'm2')
        self.assertEqual(len([l for l in report['lanes'] if l['origin'] == 'host-child']), 1)

    def test_a_single_description_match_still_merges(self):
        report = self.setup_children('Explore the parser', ['Explore the parser'])
        self.assertEqual([l for l in report['lanes'] if l['origin'] == 'host-child'], [])


if __name__ == '__main__':
    unittest.main()
