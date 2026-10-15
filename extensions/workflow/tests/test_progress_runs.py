"""Lean run reporting reads Progress' progress.runs.v1 when Progress is installed, and its own code otherwise."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
PROGRESS_SCRIPT = Path(__file__).resolve().parents[2] / 'progress' / 'scripts' / 'progress.py'
sys.path.insert(0, str(SCRIPTS))
import execution_tools as tools  # noqa: E402
import progress_bridge as bridge  # noqa: E402

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
SAME = ('run_id', 'harness', 'harness_status', 'phase', 'task_verdict', 'review_verdict', 'usage', 'elapsed_seconds',
        'journal_events', 'latest_event', 'latest_event_at', 'next_action', 'started_at', 'ended_at')


class RunsViaProgress(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / '.specify').mkdir()
        self.runs = self.root / '.delegate' / 'runs'
        saved = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(saved)))
        os.environ.pop('SANDUQ_PROGRESS_SCRIPT', None)

        def make(name, meta=None, result=None, journal=None):
            folder = self.runs / name
            folder.mkdir(parents=True)
            if meta:
                (folder / 'meta.json').write_text(json.dumps(meta), encoding='utf-8')
            if result:
                (folder / 'result.json').write_text(json.dumps(result), encoding='utf-8')
            if journal:
                (folder / 'journal.jsonl').write_text('\n'.join(json.dumps(j) for j in journal) + '\n', encoding='utf-8')
        make('live', meta={'run_id': 'live', 'harness': 'codex', 'started_at': '2026-10-15T11:59:00Z'},
             journal=[{'t': '2026-10-15T11:59:30Z', 'state': 'working', 'prompt': 'secret text'}])
        make('stalled', meta={'run_id': 'stalled', 'harness': 'claude', 'started_at': '2026-10-15T11:00:00Z'},
             journal=[{'t': '2026-10-15T11:10:00Z', 'state': 'working'}])
        make('done', meta={'run_id': 'done', 'harness': 'codex'}, result={
            'run_id': 'done', 'harness': 'codex', 'status': 'successful', 'started_at': '2026-10-15T10:00:00Z',
            'ended_at': '2026-10-15T10:05:00Z', 'task_verdict': 'pass', 'review_verdict': 'unknown',
            'next_action': 'review the diff',
            'tokens': {'fidelity': 'exact', 'input_total': 10, 'input_fresh': 8, 'cache_read': 2, 'cache_write': 0,
                       'output_total': 5, 'reasoning': 1, 'total': 15}})
        make('dup', meta={'run_id': 'done', 'harness': 'claude', 'started_at': '2026-10-15T10:00:00Z'})
        make('bad', result={'status': 'x'})

    def lean(self):
        os.environ.pop('SANDUQ_PROGRESS_SCRIPT', None)
        return tools.progress([str(self.runs)], NOW)

    def via_progress(self):
        os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(PROGRESS_SCRIPT)
        return tools.progress([str(self.runs)], NOW)

    def test_without_progress_the_lean_implementation_runs(self):
        report = self.lean()
        self.assertNotIn('via', report)
        self.assertEqual(report['duplicates'], ['done'])

    def test_with_progress_the_same_facts_come_from_the_versioned_json(self):
        lean, cli = self.lean(), self.via_progress()
        self.assertEqual(cli['via'], 'progress.runs.v1')
        self.assertEqual([{k: r[k] for k in SAME} for r in cli['runs']], [{k: r[k] for k in SAME} for r in lean['runs']])
        self.assertEqual(cli['harness_totals'], lean['harness_totals'])
        self.assertEqual(cli['duplicates'], lean['duplicates'])
        self.assertEqual(cli['conflicts'], lean['conflicts'])
        self.assertEqual(cli['next_action'], lean['next_action'])
        self.assertEqual(len(cli['malformed']), len(lean['malformed']))
        self.assertEqual(cli['ok'], lean['ok'])

    def test_caveats_survive_the_cli_path(self):
        runs = {r['run_id']: r for r in self.via_progress()['runs']}
        self.assertEqual(runs['stalled']['phase'], 'stalled')  # heuristic phase, not a failure
        self.assertEqual(runs['done']['harness_status'], 'successful')  # harness verdict, never acceptance
        self.assertNotIn('acceptance_verdict', runs['done'])
        self.assertIsNone(runs['live']['usage'])
        self.assertEqual(runs['done']['elapsed_seconds'], 300)  # wall time between start and end

    def test_unreadable_root_shape_falls_back_to_lean(self):
        odd = self.root / 'odd'
        (odd / 'deep' / 'er').mkdir(parents=True)
        (odd / 'deep' / 'er' / 'result.json').write_text(json.dumps({'run_id': 'deep', 'status': 'successful'}), encoding='utf-8')
        os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(PROGRESS_SCRIPT)
        report = tools.progress([str(odd)], NOW)
        self.assertNotIn('via', report)
        self.assertEqual([r['run_id'] for r in report['runs']], ['deep'])

    def test_a_worktree_root_resolves_to_its_runs_folder(self):
        os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(PROGRESS_SCRIPT)
        report = tools.progress([str(self.root)], NOW)
        self.assertEqual(report.get('via'), 'progress.runs.v1')
        self.assertEqual(len(report['runs']), 3)

    def test_missing_root_is_still_an_input_error(self):
        os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(PROGRESS_SCRIPT)
        with self.assertRaises(tools.InputError):
            tools.progress([str(self.root / 'nope')], NOW)

    def test_a_progress_that_answers_another_schema_is_ignored(self):
        fake = self.root / 'fake_progress.py'
        fake.write_text('import json\nprint(json.dumps({"schema": "progress.runs.v9", "runs": []}))\n', encoding='utf-8')
        os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(fake)
        self.assertIsNone(bridge.runs(self.root, [str(self.runs)]))
        report = tools.progress([str(self.runs)], NOW)
        self.assertNotIn('via', report)


if __name__ == '__main__':
    unittest.main()
