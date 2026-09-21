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
