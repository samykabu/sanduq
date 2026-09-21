import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('progress', Path(__file__).resolve().parents[1] / 'scripts/progress.py')
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


class ProgressTests(unittest.TestCase):
    def test_resume_update_escape_and_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks = root / 'tasks.md'
            tasks.write_text('- [ ] T001 <script>alert(1)</script>\n- [x] T002 Existing work\n', encoding='utf-8')
            out = root / 'report'
            def run(*args):
                p.main([args[0], '--output', str(out), *args[1:]])
            run('init', '--tasks', str(tasks))
            run('task', '--id', 'T001', '--status', 'running', '--agent', 'worker')
            run('init', '--tasks', str(tasks))
            state = json.loads((out / 'state.json').read_text())
            self.assertEqual(state['tasks'][0]['status'], 'running')
            run('task', '--id', 'T001', '--status', 'done', '--note', 'Tests passed')
            run('phase', '--name', 'Implementation', '--status', 'pushed', '--commit', 'abc123')
            run('pr', '--url', 'https://github.com/a/b/pull/1', '--status', 'merged')
            page = (out / 'index.html').read_text()
            self.assertIn('2 of 2 tasks complete', page)
            self.assertIn('merged:', page)
            self.assertIn('abc123', page)
            self.assertNotIn('<script>', page)
            self.assertIn('http-equiv="refresh"', page)
            with self.assertRaises(SystemExit):
                run('task', '--id', 'unknown', '--status', 'done')
            self.assertEqual(json.loads((out / 'state.json').read_text())['tasks'][0]['status'], 'done')

    def test_reject_empty_or_duplicate_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for text in ('No tasks', '- [ ] T1 One\n- [ ] T1 Duplicate'):
                tasks = root / 'tasks.md'
                tasks.write_text(text)
                with self.assertRaises(SystemExit):
                    p.main(['init', '--tasks', str(tasks), '--output', str(root / 'report')])
                self.assertFalse((root / 'report/state.json').exists())

    def test_reconcile_plan_preserves_evidence_and_reopens_changed_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks, out = root / 'tasks.md', root / 'report'
            tasks.write_text('## Phase 1: Build\n- [x] T001 Original\n- [x] T002 Remove later\n'
                             '### Phase 2: Verify\n- [ ] T003 Keep running\n', encoding='utf-8')
            def run(*args):
                p.main([args[0], '--output', str(out), *args[1:]])
            def state():
                return json.loads((out / 'state.json').read_text(encoding='utf-8'))
            run('init', '--tasks', str(tasks))
            self.assertEqual(state()['phases'], {'Phase 1: Build': 'pending', 'Phase 2: Verify': 'pending'})
            run('task', '--id', 'T001', '--status', 'done', '--agent', 'worker-1', '--note', 'Old evidence')
            run('task', '--id', 'T002', '--status', 'done', '--note', 'Removed evidence')
            run('task', '--id', 'T003', '--status', 'running', '--agent', 'worker-3')
            run('phase', '--name', 'Phase 1: Build', '--status', 'pushed', '--commit', 'abc123')
            tasks.write_text('## Phase 1: Build\n- [x] T001 Revised acceptance\n'
                             '### Phase 2: Verify\n- [ ] T003 Keep running\n'
                             '## Phase 3: Delivery\n- [x] T004 Added work\n', encoding='utf-8')
            run('init', '--tasks', str(tasks))
            current = state()
            by_id = {task['id']: task for task in current['tasks']}
            self.assertEqual(by_id['T001']['status'], 'pending')
            self.assertEqual(by_id['T001']['title'], 'Revised acceptance')
            self.assertEqual(by_id['T001']['note'], 'Old evidence')
            self.assertEqual(by_id['T003']['status'], 'running')
            self.assertEqual(by_id['T003']['agent'], 'worker-3')
            self.assertEqual(by_id['T004']['status'], 'pending')
            self.assertEqual(current['archived_tasks'][0]['id'], 'T002')
            self.assertEqual(current['archived_tasks'][0]['note'], 'Removed evidence')
            self.assertIn('abc123', '\n'.join(current['events']))
            self.assertIn('Original', '\n'.join(current['events']))
            self.assertEqual(current['phases']['Phase 1: Build'], 'pending')
            self.assertEqual(current['phases']['Phase 3: Delivery'], 'pending')
            self.assertIn('0 of 3 tasks complete', (out / 'index.html').read_text())
            run('init', '--tasks', str(tasks))
            self.assertEqual(state()['events'], current['events'])
            self.assertEqual(state()['archived_tasks'], current['archived_tasks'])
            run('task', '--id', 'T004', '--status', 'running')
            with self.assertRaises(SystemExit):
                run('task', '--id', 'T002', '--status', 'done')

    def test_invalid_resumed_plan_does_not_replace_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks, out = root / 'tasks.md', root / 'report'
            tasks.write_text('- [ ] T001 Accepted task\n', encoding='utf-8')
            args = ['init', '--tasks', str(tasks), '--output', str(out)]
            p.main(args)
            previous = (out / 'state.json').read_bytes()
            tasks.write_text('- [ ] T001 Duplicate\n- [ ] T001 Duplicate\n', encoding='utf-8')
            with self.assertRaises(SystemExit):
                p.main(args)
            self.assertEqual((out / 'state.json').read_bytes(), previous)
