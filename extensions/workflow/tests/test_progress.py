import importlib.util
import json
import re
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
            self.assertNotIn('<script>alert(1)', page)
            self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', page)
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



class ReportTitleTests(unittest.TestCase):
    def run_report(self, out, *args):
        p.main([args[0], '--output', str(out), *args[1:]])

    def page_title(self, out):
        return re.search(r'<title>(.*?)</title>', (out / 'index.html').read_text(encoding='utf-8')).group(1)

    def test_new_report_takes_the_feature_title_from_the_tasks_heading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks, out = root / 'tasks.md', root / 'report'
            tasks.write_text('# Tasks: Create & switch <projects>\n\n- [ ] T001 One\n', encoding='utf-8')
            self.run_report(out, 'init', '--tasks', str(tasks))
            self.assertEqual(json.loads((out / 'state.json').read_text(encoding='utf-8'))['title'],
                             'Create & switch <projects>')
            self.assertEqual(self.page_title(out), 'Create &amp; switch &lt;projects&gt;')
            self.assertIn('<h1>Create &amp; switch &lt;projects&gt;</h1>', (out / 'index.html').read_text(encoding='utf-8'))

    def test_plan_without_a_heading_keeps_the_generic_title(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks, out = root / 'tasks.md', root / 'report'
            tasks.write_text('- [ ] T001 One\n', encoding='utf-8')
            self.run_report(out, 'init', '--tasks', str(tasks))
            self.assertEqual(self.page_title(out), 'Implementation progress')

    def test_explicit_title_renames_an_existing_report_and_survives_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks, out = root / 'tasks.md', root / 'report'
            tasks.write_text('- [ ] T001 One\n', encoding='utf-8')
            self.run_report(out, 'init', '--tasks', str(tasks))
            self.run_report(out, 'task', '--id', 'T001', '--status', 'running')
            self.run_report(out, 'init', '--tasks', str(tasks), '--title', 'UC-1A-05 · Create a project')
            state = json.loads((out / 'state.json').read_text(encoding='utf-8'))
            self.assertEqual(state['title'], 'UC-1A-05 · Create a project')
            self.assertEqual(state['tasks'][0]['status'], 'running')
            self.assertIn('Renamed report', '\n'.join(state['events']))
            self.run_report(out, 'event', '--message', 'later update')
            self.assertEqual(self.page_title(out), 'UC-1A-05 · Create a project')

    def test_resume_without_title_adopts_the_heading_only_for_the_generic_title(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks, out = root / 'tasks.md', root / 'report'
            tasks.write_text('- [ ] T001 One\n', encoding='utf-8')
            self.run_report(out, 'init', '--tasks', str(tasks))
            tasks.write_text('# Tasks: Review Home\n- [ ] T001 One\n', encoding='utf-8')
            self.run_report(out, 'init', '--tasks', str(tasks))
            self.assertEqual(self.page_title(out), 'Review Home')
            self.run_report(out, 'init', '--tasks', str(tasks), '--title', 'Chosen name')
            self.run_report(out, 'init', '--tasks', str(tasks))
            self.assertEqual(self.page_title(out), 'Chosen name')



class ReportLayoutTests(unittest.TestCase):
    def build(self, root):
        tasks, out = root / 'tasks.md', root / 'report'
        tasks.write_text('# Tasks: Layout\n## Phase 1: Setup <b>\n- [x] T001 First\n'
                         '## Phase 2: Build\n- [ ] T002 Second\n- [ ] T003 Third\n', encoding='utf-8')
        run = lambda *args: p.main([args[0], '--output', str(out), *args[1:]])
        run('init', '--tasks', str(tasks))
        run('task', '--id', 'T002', '--status', 'running', '--agent', 'worker-2')
        run('task', '--id', 'T003', '--status', 'blocked', '--note', 'Waiting on T002')
        run('event', '--message', 'Assigned <T002>')
        return out, (out / 'index.html').read_text(encoding='utf-8')

    def test_rows_carry_phase_and_status_for_filtering(self):
        with tempfile.TemporaryDirectory() as directory:
            out, page = self.build(Path(directory))
            self.assertIn('<th scope="col">Phase</th>', page)
            self.assertIn('data-status="blocked" data-phase="Phase 2: Build"', page)
            self.assertIn('data-phase="Phase 1: Setup &lt;b&gt;"', page)
            self.assertNotIn('<b>', page)
            self.assertRegex(page, r'<select id="status-filter"[^>]*>')
            self.assertRegex(page, r'<select id="phase-filter"[^>]*>')
            for status in ('pending', 'running', 'done', 'blocked'):
                self.assertIn(f'<option value="{status}">', page)
            self.assertIn('<option value="Phase 2: Build">', page)
            run = lambda *args: p.main([args[0], '--output', str(out), *args[1:]])
            run('phase', '--name', 'Build (short name)', '--status', 'complete', '--commit', 'abc123')
            page = (out / 'index.html').read_text(encoding='utf-8')
            self.assertIn('Build (short name): complete (abc123)', page)
            self.assertNotIn('<option value="Build (short name)">', page)

    def test_activity_is_a_separate_tab_with_escaped_events(self):
        with tempfile.TemporaryDirectory() as directory:
            out, page = self.build(Path(directory))
            self.assertIn('role="tablist"', page)
            self.assertRegex(page, r'<button[^>]*role="tab"[^>]*aria-controls="tasks-panel"')
            self.assertRegex(page, r'<button[^>]*role="tab"[^>]*aria-controls="activity-panel"')
            self.assertRegex(page, r'<section id="activity-panel" role="tabpanel"[^>]*hidden')
            self.assertIn('Assigned &lt;T002&gt;', page)
            self.assertNotIn('<T002>', page)

    def test_logo_is_copied_beside_the_report(self):
        with tempfile.TemporaryDirectory() as directory:
            out, page = self.build(Path(directory))
            for name in ('sanduq-logo.png', 'sanduq-logo-dark.png'):
                self.assertTrue((out / name).is_file(), name)
                self.assertEqual((out / name).read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
            self.assertIn('src="sanduq-logo.png"', page)
            self.assertIn('srcset="sanduq-logo-dark.png"', page)
            self.assertIn('alt="Sanduq"', page)

    def test_refresh_keeps_the_selected_filters_and_tab(self):
        with tempfile.TemporaryDirectory() as directory:
            out, page = self.build(Path(directory))
            self.assertIn('location.hash', page)
            self.assertIn('http-equiv="refresh"', page)
