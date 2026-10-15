import json
import os
import socket
import subprocess
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone

import helpers
from helpers import FIXTURES, Project
from sanduq_progress import facts
from sanduq_progress.collect import runs as runscol, tasks as taskscol
from sanduq_progress.lock import Lock, LockBusy
from sanduq_progress.paths import ProgressError, resolve_feature


class FeatureResolution(Project):
    def test_order_explicit_env_checkpoint_branch(self):
        (self.root / 'specs' / '002-other').mkdir()
        self.assertEqual(resolve_feature(self.root), 'specs/001-demo')  # branch
        os.environ['SPECIFY_FEATURE'] = '002-other'
        self.assertEqual(resolve_feature(self.root), 'specs/002-other')  # env beats branch
        self.assertEqual(resolve_feature(self.root, 'specs/001-demo'), 'specs/001-demo')  # flag beats env

    def test_checkpoint_beats_branch_name(self):
        (self.root / 'specs' / '002-other' / 'workflow').mkdir(parents=True)
        cp = json.loads((FIXTURES / 'checkpoint.json').read_text())
        cp.update(feature='specs/002-other', branch='001-demo')
        (self.root / 'specs/002-other/workflow/checkpoint.json').write_text(json.dumps(cp))
        self.assertEqual(resolve_feature(self.root), 'specs/002-other')

    def test_no_feature_is_a_one_line_error(self):
        (self.root / 'specs' / '001-demo' / 'tasks.md').unlink()
        os.rename(self.root / 'specs' / '001-demo', self.root / 'specs' / 'renamed')
        with self.assertRaises(ProgressError) as caught:
            resolve_feature(self.root)
        self.assertEqual(caught.exception.line(), 'progress: error PROGRESS_NO_FEATURE pass --feature specs/<dir>')
        code, out = self.cli('status')
        self.assertEqual((code, out.count('\n')), (2, 0))
        self.assertTrue(out.startswith('progress: error PROGRESS_NO_FEATURE'))


class Facts(Project):
    def test_torn_last_line_is_skipped_and_next_append_stays_clean(self):
        path = self.feature_dir / 'progress' / 'facts.jsonl'
        path.parent.mkdir()
        good = facts.make('note', 'N1', 'user', text='one')
        path.write_text(json.dumps(good) + '\n{"v":1,"kind":"note","id":"N2","te', encoding='utf-8')
        loaded = facts.load(path)
        self.assertTrue(loaded['torn'])
        self.assertEqual([r['id'] for r in loaded['current']], ['N1'])
        facts.append(path, facts.make('note', 'N2', 'user', text='two'))
        loaded = facts.load(path)
        self.assertEqual([r['id'] for r in loaded['current']], ['N1', 'N2'])
        self.assertEqual(loaded['corrupt'], 1)  # the old fragment, now a closed corrupt line

    def test_supersede_by_id_and_id_allocation(self):
        path = self.feature_dir / 'facts.jsonl'
        facts.append(path, facts.make('block', 'B1', 'user', state='open', target='T001', by={}))
        facts.append(path, facts.make('block', 'B2', 'user', state='open', target='T002', by={}))
        facts.append(path, facts.make('block', 'B1', 'user', state='resolved', target='T001', by={}))
        loaded = facts.load(path)
        self.assertEqual({r['id']: r['state'] for r in loaded['current']}, {'B1': 'resolved', 'B2': 'open'})
        self.assertEqual(facts.next_id(loaded['all'], 'block'), 'B3')
        self.assertEqual(facts.next_id(loaded['all'], 'lane'), 'L1')

    def test_sanitise_caps_strips_and_refuses(self):
        self.assertEqual(facts.sanitise('a\x00b\x1b[31m\nc', self.root), 'a b [31m c')
        self.assertEqual(len(facts.sanitise('x' * 500, self.root)), 200)
        for bad in ('token=abcdef123456', 'key sk-abcdefghijklmnopqrstuv', 'see C:\\Users\\bob\\secrets.txt', 'cat /home/bob/x'):
            with self.assertRaises(ProgressError) as caught:
                facts.sanitise(bad, self.root)
            self.assertEqual((caught.exception.code, caught.exception.exit_code), ('PROGRESS_FORBIDDEN_CONTENT', 3))
        inside = f'edited {self.root.as_posix()}/specs/x.md'
        self.assertEqual(facts.sanitise(inside, self.root), inside)

    def test_cli_verbs_round_trip(self):
        self.init()
        self.assertEqual(self.cli('lane', 'new', '--tasks', 'T001-T002,T004', '--label', 'Core', '--harness', 'codex'),
                         (0, 'progress: L1 open 3 tasks'))
        self.assertEqual(self.cli('block', 'T004', '--by', 'L2'), (0, 'progress: B1 open T004 by L2'))
        self.assertEqual(self.cli('block', 'T004', '--by', 'L2'), (0, 'progress: B1 open T004 by L2'))  # idempotent
        self.assertEqual(self.cli('unblock', '--all-for', 'T004'), (0, 'progress: B1 resolved'))
        self.assertEqual(self.cli('note', 'checked', '--target', 'T001'), (0, 'progress: N1 noted'))
        self.assertEqual(self.cli('decide', 'ask', 'Which db?', '--options', 'sqlite,postgres'), (0, 'progress: D1 pending'))
        self.assertEqual(self.cli('decide', 'made', 'D1', 'postgres', '--by', 'user'), (0, 'progress: D1 made postgres'))
        code, out = self.cli('block', 'T001', '--by', 'bogus')
        self.assertEqual((code, out.split()[:3]), (2, ['progress:', 'error', 'PROGRESS_USAGE']))
        report = self.report()
        self.assertEqual(report['decisions']['made'][0]['selected'], 'postgres')
        self.assertEqual(report['summary']['blocked'], 0)

    def test_decision_authority_refused_when_workflow_owns_decisions(self):
        self.init()
        self.workflow_file('decisions.json')
        code, out = self.cli('decide', 'ask', 'Which?', '--options', 'a,b')
        self.assertEqual((code, out.split()[:3]), (3, ['progress:', 'error', 'PROGRESS_DECISION_AUTHORITY']))
        self.assertEqual(len(facts.load(self.ctx.facts)['all']), 0)


class Locking(Project):
    def setUp(self):
        super().setUp()
        self.path = self.root / 'lockfile'

    def test_contention_raises_busy_then_releases(self):
        with Lock(self.path):
            with self.assertRaises(LockBusy):
                Lock(self.path, retries=1, delay=0.01).acquire()
        with Lock(self.path, retries=0):
            pass

    def _write_owner(self, pid, host):
        self.path.write_text(json.dumps({'pid': pid, 'host': host, 'started_at': '2026-10-15T00:00:00Z'}))

    def test_owner_metadata_is_diagnostic_only(self):
        """A dead pid, a live pid or a foreign host in the file decides nothing: only the OS lock does."""
        child = subprocess.Popen([sys.executable, '-c', 'pass'])
        child.wait()
        for pid, host in ((child.pid, socket.gethostname()), (os.getpid(), socket.gethostname()), (99999999, 'some-other-host')):
            self._write_owner(pid, host)
            with Lock(self.path, retries=0):
                owner = json.loads(self.path.read_bytes().rstrip(b'\x00').decode('utf-8'))
                self.assertEqual(owner['pid'], os.getpid())

    def test_verbs_exit_4_when_the_feature_lock_is_held(self):
        self.init()
        holder = Lock(self.ctx.lock).acquire()
        try:
            started = time.time()
            code, out = self.cli('note', 'blocked')
            self.assertEqual((code, out.split()[:3]), (4, ['progress:', 'error', 'PROGRESS_LOCK_BUSY']))
            self.assertGreaterEqual(time.time() - started, 0.55)  # 3 retries at 200 ms
        finally:
            holder.release()
        self.assertEqual(self.cli('note', 'free')[0], 0)


class Collectors(Project):
    def test_tasks_phases_markers_and_decoys(self):
        parsed = taskscol.parse((FIXTURES / 'tasks.md').read_text())
        by_id = {t['id']: t for t in parsed['tasks']}
        self.assertEqual(parsed['title'], 'Tasks: Demo feature')
        self.assertEqual(list(by_id), ['T001', 'T002', 'T003', 'T004', 'T005'])  # fenced T050 and prose ids ignored
        self.assertEqual((by_id['T001']['done'], by_id['T005']['done']), (True, True))
        self.assertTrue(by_id['T002']['parallel'])
        self.assertFalse(by_id['T003']['parallel'])
        self.assertEqual(by_id['T002']['depends_on'], ['T001'])
        self.assertEqual(by_id['T003']['depends_on'], ['T002'])  # code-span annotation and bare T097 are ignored
        self.assertEqual(by_id['T004']['depends_on'], ['T002', 'T003'])
        self.assertEqual(by_id['T002']['phase'], 'Phase 1: Setup')
        self.assertEqual(by_id['T004']['phase'], 'Phase 2: Polish')
        self.assertEqual(by_id['T002']['title'], 'Build the parser')

    def test_expand_ranges(self):
        self.assertEqual(taskscol.expand('T001-T003,T009'), ['T001', 'T002', 'T003', 'T009'])
        with self.assertRaises(ValueError):
            taskscol.expand('T005-T001')

    def test_run_journal_projection(self):
        now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
        runs = self.root / 'runs'

        def make(name, meta=None, result=None, journal=None):
            d = runs / name
            d.mkdir(parents=True)
            if meta:
                (d / 'meta.json').write_text(json.dumps(meta))
            if result:
                (d / 'result.json').write_text(json.dumps(result))
            if journal:
                (d / 'journal.jsonl').write_text('\n'.join(json.dumps(j) for j in journal) + '\nnot json\n')
        make('live', meta={'run_id': 'live', 'harness': 'codex', 'started_at': '2026-10-15T11:59:00Z'},
             journal=[{'t': '2026-10-15T11:59:30Z', 'state': 'working', 'prompt': 'secret text'}])
        make('stalled', meta={'run_id': 'stalled', 'harness': 'claude', 'started_at': '2026-10-15T11:00:00Z'},
             journal=[{'t': '2026-10-15T11:10:00Z', 'state': 'working'}])
        make('done', meta={'run_id': 'done', 'harness': 'codex'}, result={
            'run_id': 'done', 'harness': 'codex', 'status': 'successful', 'started_at': '2026-10-15T10:00:00Z',
            'ended_at': '2026-10-15T10:05:00Z', 'tokens': {'fidelity': 'exact', 'input_total': 10, 'input_fresh': 8, 'cache_read': 2,
                                                          'cache_write': 0, 'output_total': 5, 'reasoning': 1, 'total': 15}})
        make('dup', meta={'run_id': 'done', 'harness': 'claude', 'started_at': '2026-10-15T10:00:00Z'})
        make('bad', result={'status': 'x'})
        found = {r['run_id']: r for r in runscol.collect_runs(runs, now=now)}
        self.assertEqual(found['live']['phase'], 'active')
        self.assertEqual(found['stalled']['phase'], 'stalled')
        self.assertEqual(found['done']['elapsed_seconds'], 300)
        self.assertEqual(found['done']['usage']['total'], 15)
        self.assertEqual(found['done']['harness_status'], 'successful')  # terminal harness status, not acceptance
        self.assertEqual(found['done']['conflict'], ['harness'])
        self.assertEqual(len(runscol.last_malformed()), 1)
        since = now - timedelta(minutes=5)
        self.assertEqual([r['run_id'] for r in runscol.collect_runs(runs, since=since, now=now)], ['live'])


if __name__ == '__main__':
    unittest.main()
