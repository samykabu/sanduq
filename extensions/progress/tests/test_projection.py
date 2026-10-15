import json
import os
import unittest

import helpers
from helpers import FIXTURES, T0, Project
from sanduq_progress import model, render_md
from datetime import datetime, timezone

GOLDEN = FIXTURES / 'expected_report.json'
NOW = datetime(2026, 10, 15, 12, 30, tzinfo=timezone.utc)


def normalised(report):
    return {**report, 'generated_at': '<now>', 'rev': 0}


class Projection(Project):
    def workflow_scenario(self):
        self.init(debounce_seconds=0)
        for name in ('checkpoint.json', 'delegations.json', 'decisions.json'):
            self.workflow_file(name)
        self.bind()
        self.hook('pre_tool_use', self.payload('claude_pre_task.json'), now='2026-10-15T12:10:00Z')
        self.hook('post_tool_use', self.payload('claude_post_task.json'), now='2026-10-15T12:12:00Z')
        self.cli('lane', 'L1', '--tasks', 'T003-T004', '--label', 'Docs', '--owner', 'specs/001-demo/T003')
        self.cli('block', 'T004', '--by', 'T003')
        self.cli('note', 'waiting on review')

    def test_golden_projection(self):
        self.workflow_scenario()
        built = normalised(model.build(self.ctx, NOW, 3, json.loads(self.ctx.state.read_text())))
        if os.environ.get('UPDATE_GOLDEN'):
            GOLDEN.write_text(json.dumps(built, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        self.assertEqual(built, json.loads(GOLDEN.read_text(encoding='utf-8')))

    def test_workflow_mode_lanes_attempts_and_decisions(self):
        self.workflow_scenario()
        report = model.build(self.ctx, NOW, 1, json.loads(self.ctx.state.read_text()))
        self.assertTrue(report['feature']['workflow'])
        self.assertEqual(report['feature']['issue'], {'number': 10, 'url': 'https://github.com/acme/app/issues/10'})
        self.assertEqual(report['feature']['stage'], {'value': 'execute', 'source': 'workflow-checkpoint'})
        self.assertNotIn('coordinator', [lane['id'] for lane in report['lanes']])
        lanes = {lane['id']: lane for lane in report['lanes']}
        docs = lanes['L1']  # the facts lane owns the delegation identity: retries are attempts of one lane
        self.assertEqual(docs['label'], 'Docs')
        retry = next(l for l in report['lanes'] if l['owner'] == 'specs/001-demo/T002')
        self.assertEqual([a['run_id'] for a in retry['attempts']], ['run-a1', 'run-a2'])
        self.assertEqual((retry['status'], retry['origin']), ('active', 'workflow-delegation'))
        self.assertEqual(retry['tasks']['active'], ['T002'])
        self.assertEqual(retry['requested']['model'], 'sonnet')
        self.assertEqual(retry['observed']['model']['fidelity'], 'unknown')  # actual model still pending
        review = next(l for l in report['lanes'] if l['owner'] == 'stage:execute')
        self.assertEqual(review['status'], 'done')
        self.assertEqual(review['observed']['model']['value'], 'gpt-6-astra')
        self.assertEqual([d['id'] for d in report['decisions']['pending']], ['SD2'])
        self.assertEqual(report['decisions']['made'][0]['selected'], 'Use Postgres')
        self.assertEqual(docs['tasks']['blocked'], [{'task': 'T004', 'by': [{'type': 'task', 'ref': 'T003', 'blocker': 'B1'}]}])
        self.assertEqual(docs['tasks']['active'], ['T003'])
        self.assertEqual(report['summary'], {'tasks_total': 5, 'tasks_done': 2, 'lanes_active': 2, 'blocked': 1, 'decisions_pending': 1})
        child = next(l for l in report['lanes'] if l['origin'] == 'host-child')
        self.assertEqual((child['status'], child['tasks']), ('done', {'active': [], 'waiting': [], 'blocked': [], 'done': []}))
        self.assertTrue(report['collection']['automatic'])

    def test_plain_mode_has_a_coordinator_lane_and_no_workflow_fields(self):
        self.init()
        report = model.build(self.ctx, NOW, 1, {})
        self.assertFalse(report['feature']['workflow'])
        self.assertIsNone(report['feature']['stage'])
        self.assertEqual([l['id'] for l in report['lanes']], ['coordinator'])
        coordinator = report['lanes'][0]
        self.assertEqual(coordinator['origin'], 'coordinator')
        self.assertEqual(coordinator['tasks']['done'], ['T001', 'T005'])
        self.assertEqual(sorted(coordinator['tasks']['waiting'] + coordinator['tasks']['active']), ['T002', 'T003', 'T004'])
        self.assertEqual(report['unassigned_tasks'], {'active': [], 'waiting': [], 'blocked': [], 'done': []})
        self.assertEqual(report['orchestrator']['model']['fidelity'], 'unknown')
        self.assertFalse(report['collection']['automatic'])

    def test_unmapped_host_child_has_no_tasks_and_unassigned_stays_visible_in_workflow_mode(self):
        self.init(debounce_seconds=0)
        self.workflow_file('checkpoint.json')
        report = model.build(self.ctx, NOW, 1, {})
        self.assertEqual(report['unassigned_tasks']['waiting'], ['T002', 'T003', 'T004'])
        self.assertEqual(report['unassigned_tasks']['done'], ['T001', 'T005'])

    def test_workflow_pause_becomes_a_blocker(self):
        self.init()
        cp = json.loads((FIXTURES / 'checkpoint.json').read_text())
        cp['pause'] = {'reason': 'Needs owner input', 'at': '2026-10-15T11:00:00Z'}
        (self.feature_dir / 'workflow').mkdir()
        (self.feature_dir / 'workflow' / 'checkpoint.json').write_text(json.dumps(cp))
        report = model.build(self.ctx, NOW, 1, {})
        self.assertEqual(report['blockers'][0]['source'], 'workflow-pause')

    def test_markdown_export_is_deterministic_and_complete(self):
        self.workflow_scenario()
        first = self.cli('export')
        second = self.cli('export')
        self.assertEqual(first, second)
        self.assertEqual(first[0], 0)
        self.assertIn('| L1 | Docs |', first[1])
        self.assertIn('T004', first[1])
        report = self.report()
        self.assertEqual(render_md.render(report), render_md.render(json.loads(json.dumps(report))))
        out = self.root / 'out.md'
        self.assertEqual(self.cli('export', '--out', str(out)), (0, f'progress: exported {out}'))
        self.assertEqual(out.read_text(encoding='utf-8'), render_md.render(report))
        code, text = self.cli('export', '--format', 'json')
        self.assertEqual(json.loads(text), report)

    def test_report_files_and_data_js(self):
        self.init()
        data = (self.ctx.view / 'data.js').read_text(encoding='utf-8')
        self.assertTrue(data.startswith('window.__SANDUQ_PROGRESS__ = {'))
        payload = json.loads(data[len('window.__SANDUQ_PROGRESS__ = '):].rstrip().rstrip(';'))
        self.assertEqual(payload, self.report())
        self.assertEqual(self.report()['schema'], 'sanduq.progress.v2')
        revs = [self.report()['rev']]
        self.cli('refresh')
        revs.append(self.report()['rev'])
        self.assertEqual(revs[1], revs[0] + 1)
        self.assertEqual(self.cli('refresh', '--final', '--verbose'), (0, f'progress: refreshed rev {revs[1] + 1}'))

    def test_init_layout_exclude_and_theme_fallback(self):
        line = self.init()
        self.assertTrue(self.ctx.facts.exists())
        exclude = (self.root / '.git' / 'info' / 'exclude').read_text()
        self.assertIn('specs/*/progress/.view/', exclude)
        self.assertIn(':root{', (self.ctx.view / 'theme.css').read_text())
        self.assertTrue((self.ctx.view / 'layout.js').exists())
        self.assertTrue((self.ctx.view / 'index.html').exists())
        self.assertEqual(len(line), 12)
        code, out = self.cli('init', '--statusline', 'no')
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith('progress: ready specs/001-demo/progress/.view/index.html bind='))
        self.assertEqual(self.cli('status')[1].split(',')[0], 'progress: 2/5 tasks')

    @unittest.skipIf(__import__('importlib').util.find_spec('sanduq_progress.theme'), 'theme module present')
    def test_theme_verb_reports_unavailable_module(self):
        self.init()
        self.assertEqual(self.cli('theme', '--show'), (2, 'progress: error PROGRESS_THEME_UNAVAILABLE'))


if __name__ == '__main__':
    unittest.main()
