"""Illustrate dependency-plan acceptance: coverage, reachability, freshness, visual checks, review and migration."""
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCOPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCOPE / 'scripts'))
spec = importlib.util.spec_from_file_location('accept_plan', SCOPE / 'scripts/accept_plan.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ILLUSTRATE = SCOPE.parent / 'illustrate/skill'

PLAN_HTML = '''<!DOCTYPE html><html><body><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">
<path data-plan-from="first" data-plan-to="second" d="M 80,56 V 120"/>
<rect data-plan-node="first" x="0" y="0" width="160" height="56"/>
<rect data-plan-node="second" x="0" y="120" width="160" height="56"/>
</svg></body></html>'''


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class GraphMappingTests(unittest.TestCase):
    def setUp(self):
        self.graph = {'issues': [{'number': 1, 'dependencies': [], 'children': []},
                                 {'number': 2, 'dependencies': [1], 'children': []},
                                 {'number': 3, 'dependencies': [], 'children': [1, 2]}]}
        self.diagram = {'nodes': [{'id': 'first'}, {'id': 'second'}], 'edges': [{'from': 'first', 'to': 'second'}]}
        self.mapping = {'graph_sha256': 'abc', 'issue_to_node': {'1': 'first', '2': 'second'}}

    def test_complete_mapping(self):
        m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'abc')

    def test_stale_graph_rejected(self):
        with self.assertRaisesRegex(ValueError, 'stale'):
            m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'changed')

    def test_missing_issue_rejected(self):
        del self.mapping['issue_to_node']['2']
        with self.assertRaisesRegex(ValueError, 'every executable'):
            m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'abc')

    def test_missing_dependency_path_rejected(self):
        self.diagram['edges'] = []
        with self.assertRaisesRegex(ValueError, 'omits dependency'):
            m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'abc')

    def test_dependent_same_wave_rejected(self):
        self.mapping['issue_to_node']['2'] = 'first'
        with self.assertRaisesRegex(ValueError, 'parallel implementation wave'):
            m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'abc')

    def test_dependency_on_parent_rejected(self):
        self.graph['issues'][1]['dependencies'] = [3]
        with self.assertRaisesRegex(ValueError, 'aggregate'):
            m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'abc')

    def test_dependency_cycle_rejected(self):
        self.graph['issues'][0]['dependencies'] = [2]
        self.diagram['edges'].append({'from': 'second', 'to': 'first'})
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'abc')


class DiagramAndLayoutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.html = Path(temporary.name) / 'plan.html'

    def read(self, text):
        self.html.write_text(text, encoding='utf-8')
        return m.read_diagram(self.html)

    def test_nodes_and_edges_come_from_the_html(self):
        self.assertEqual(self.read(PLAN_HTML), {'nodes': [{'id': 'first'}, {'id': 'second'}],
                                                'edges': [{'from': 'first', 'to': 'second'}]})

    def test_unmarked_duplicate_or_dangling_diagrams_rejected(self):
        with self.assertRaisesRegex(ValueError, 'No data-plan-node'):
            self.read('<svg><rect/></svg>')
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            self.read(PLAN_HTML.replace('"second"', '"first"'))
        with self.assertRaisesRegex(ValueError, 'two declared'):
            self.read(PLAN_HTML.replace('data-plan-to="second"', 'data-plan-to="third"'))

    def probe(self, **overrides):
        value = {'svg': {'x': 0, 'y': 0, 'w': 400, 'h': 200},
                 'nodes': [{'id': 'first', 'x': 0, 'y': 0, 'w': 160, 'h': 56}, {'id': 'second', 'x': 0, 'y': 120, 'w': 160, 'h': 56}],
                 'edges': [{'id': 'first->second', 'length': 64}]}
        value.update(overrides)
        return value

    def test_clean_layout_has_no_findings(self):
        self.assertEqual(m.check_layout(self.probe(), '1280x800'), [])

    def test_layout_defects_are_findings(self):
        overlap = self.probe(nodes=[{'id': 'a', 'x': 0, 'y': 0, 'w': 160, 'h': 56}, {'id': 'b', 'x': 100, 'y': 20, 'w': 160, 'h': 56}])
        self.assertIn('1280x800: nodes a and b overlap', m.check_layout(overlap, '1280x800'))
        outside = self.probe(nodes=[{'id': 'a', 'x': 380, 'y': 0, 'w': 160, 'h': 56}])
        self.assertIn('outside the diagram', m.check_layout(outside, 'v')[0])
        hidden = self.probe(nodes=[{'id': 'a', 'x': 0, 'y': 0, 'w': 0, 'h': 0}], edges=[{'id': 'a->b', 'length': 0}])
        self.assertEqual(m.check_layout(hidden, 'v'), ['v: node a is not visible', 'v: edge a->b has no drawn length'])
        self.assertEqual(m.check_layout({'error': 'no <svg> rendered'}, 'v'), ['v: no <svg> rendered'])


class ReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.html = self.root / 'plan.html'
        self.html.write_text('<html>Current diagram</html>', encoding='utf-8')
        self.screenshot = self.root / 'review.png'
        self.screenshot.write_bytes(b'fixture screenshot bytes')
        self.review = {'html_sha256': digest(self.html), 'passed': True, 'reviewer': 'image-capable reviewer', 'findings': [],
                       'screenshots': [{'path': 'review.png', 'sha256': digest(self.screenshot)}]}

    def test_current_review_is_accepted(self):
        m.validate_review(self.root, self.html, self.review)

    def test_changed_html_is_rejected(self):
        self.html.write_text('New diagram', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'current HTML'):
            m.validate_review(self.root, self.html, self.review)

    def test_changed_or_deleted_screenshot_is_rejected(self):
        self.screenshot.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'missing, changed'):
            m.validate_review(self.root, self.html, self.review)
        self.screenshot.unlink()
        with self.assertRaisesRegex(ValueError, 'missing, changed'):
            m.validate_review(self.root, self.html, self.review)

    def test_unresolved_findings_or_no_images_are_rejected(self):
        self.review['findings'] = ['Unreadable label']
        with self.assertRaisesRegex(ValueError, 'zero unresolved'):
            m.validate_review(self.root, self.html, self.review)
        self.review['findings'] = []
        self.review['screenshots'] = []
        with self.assertRaisesRegex(ValueError, 'actual screenshot'):
            m.validate_review(self.root, self.html, self.review)

    def test_outside_project_image_is_rejected(self):
        self.review['screenshots'][0]['path'] = '../review.png'
        with self.assertRaisesRegex(ValueError, 'outside the project'):
            m.validate_review(self.root, self.html, self.review)


class AcceptanceTests(unittest.TestCase):
    """main() end to end with Illustrate tools and the browser stubbed."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.artifacts = self.root / 'Design/UI-Spec/github'
        self.artifacts.mkdir(parents=True)
        self.plan = self.root / 'Design/UI-Spec/implementation-plan.html'
        self.plan.write_text('<html>previous plan</html>', encoding='utf-8')
        self.pending = self.root / '.specify/scope/plan-pending.json'
        self.pending.parent.mkdir(parents=True)
        self.pending.write_text(json.dumps({'operation': 'op', 'issue': 9, 'renderer': 'illustrate', 'required': 'x'}), encoding='utf-8')
        graph = self.artifacts / 'scope-dependencies.json'
        graph.write_text(json.dumps({'repo': 'acme/app', 'issues': [{'number': 1, 'dependencies': [], 'children': []},
                                                                    {'number': 2, 'dependencies': [1], 'children': []}]}), encoding='utf-8')
        self.candidate = self.artifacts / 'implementation-plan.illustrate.html'
        self.candidate.write_text(PLAN_HTML, encoding='utf-8')
        self.mapping = self.artifacts / 'implementation-plan.mapping.json'
        self.mapping.write_text(json.dumps({'graph_sha256': digest(graph), 'issue_to_node': {'1': 'first', '2': 'second'}}), encoding='utf-8')
        self.skill = self.root / 'skill'
        (self.skill / 'scripts').mkdir(parents=True)
        for name in ('self_check.py', 'verify-geometry.py', 'export_diagram.py'):
            (self.skill / 'scripts' / name).write_text('', encoding='utf-8')
        self.failing = None
        self.shot = self.artifacts / 'plan-review/shot.png'

    def tool(self, receipt, name, command):
        receipt['commands'].append({'command': name})
        if name == 'export':
            for suffix in ('.svg', '.png'):
                (self.artifacts / ('implementation-plan' + suffix)).write_bytes(b'export')
        return subprocess.CompletedProcess(command, 1 if name == self.failing else 0, '', f'{name} broke')

    def browser(self, html, folder, root):
        folder.mkdir(parents=True, exist_ok=True)
        self.shot.write_bytes(b'screenshot')
        return {'viewports': ['1280x800'], 'findings': [], 'screenshots': [{'path': self.shot.relative_to(root).as_posix(), 'sha256': digest(self.shot)}]}

    def run_main(self, *args, browser=None):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(m.subprocess, 'check_output', return_value=str(self.root)), \
                patch.object(m, 'run_tool', side_effect=self.tool), \
                patch.object(m, 'browser_check', side_effect=browser or self.browser), \
                redirect_stdout(out), redirect_stderr(err):
            m.main(list(args))
        return out.getvalue() + err.getvalue()

    def accept(self, *extra, **kwargs):
        return self.run_main('--html', str(self.candidate), '--mapping', str(self.mapping), '--illustrate', str(self.skill), *extra, **kwargs)

    def receipt(self):
        return json.loads((self.artifacts / 'scope-plan-receipt.json').read_text(encoding='utf-8'))

    def test_unmanaged_success_delivers_and_clears_pending(self):
        self.assertIn('Plan copies synchronized', self.accept())
        self.assertFalse(self.pending.exists())
        self.assertEqual(self.plan.read_text(encoding='utf-8'), PLAN_HTML)
        self.assertEqual((self.artifacts / 'implementation-plan.html').read_text(encoding='utf-8'), PLAN_HTML)
        receipt = self.receipt()
        self.assertEqual(receipt['renderer'], 'illustrate')
        self.assertEqual(receipt['html_sha256'], digest(self.candidate))
        self.assertEqual([c['command'] for c in receipt['commands']], ['self-check', 'verify-geometry', 'export'])
        self.assertEqual(set(receipt['exports']), {'svg', 'png'})

    def test_failed_render_keeps_previous_plan_and_pending_marker(self):
        for step in ('self-check', 'verify-geometry', 'export'):
            self.failing = step
            with self.assertRaisesRegex(SystemExit, f'Illustrate {step} failed.*pending marker retained'):
                self.accept()
            self.assertTrue(self.pending.exists())
            self.assertEqual(self.plan.read_text(encoding='utf-8'), '<html>previous plan</html>')
            self.assertEqual(json.loads((self.pending.parent / 'plan-failed-receipt.json').read_text(encoding='utf-8'))['commands'][-1]['command'], step)

    def test_browser_findings_or_missing_browser_fail_closed(self):
        def defects(html, folder, root):
            return {'viewports': ['1280x800'], 'findings': ['1280x800: nodes first and second overlap'], 'screenshots': []}
        with self.assertRaisesRegex(SystemExit, 'overlap'):
            self.accept(browser=defects)
        def missing(*args):
            raise RuntimeError('Playwright is required')
        with self.assertRaisesRegex(SystemExit, 'Browser check could not run: Playwright is required'):
            self.accept(browser=missing)
        self.assertTrue(self.pending.exists())
        self.assertEqual(self.plan.read_text(encoding='utf-8'), '<html>previous plan</html>')

    def test_incomplete_mapping_is_rejected_before_any_tool_runs(self):
        self.mapping.write_text(json.dumps({'graph_sha256': 'stale', 'issue_to_node': {}}), encoding='utf-8')
        with self.assertRaisesRegex(SystemExit, 'stale.*Pending marker retained'):
            self.accept()
        self.assertFalse((self.artifacts / 'scope-plan-receipt.json').exists())

    def test_missing_illustrate_is_reported(self):
        shutil.rmtree(self.skill)
        with self.assertRaisesRegex(SystemExit, r'Illustrate \(>=2.2.1\) is not installed'):
            self.accept()

    def test_managed_review_accepts_only_unchanged_delivered_bytes(self):
        (self.root / '.specify/workflow.yml').write_text(
            'schema_version: 1\nscope:\n  artifact_directory: Design/UI-Spec/github\n  plan_file: Design/UI-Spec/implementation-plan.html\n', encoding='utf-8')
        self.assertIn('Pending marker retained until image review', self.accept())
        self.assertTrue(self.pending.exists())
        review = self.root / 'review.json'
        review.write_text(json.dumps({'html_sha256': digest(self.plan), 'passed': True, 'reviewer': 'reviewer', 'findings': [],
                                      'screenshots': self.receipt()['browser']['screenshots']}), encoding='utf-8')
        self.plan.write_text('<html>rerendered</html>', encoding='utf-8')
        with self.assertRaisesRegex(SystemExit, 'changed after browser checks'):
            self.accept('--review', str(review))
        shutil.copy2(self.candidate, self.plan)
        self.assertIn('perceptual review accepted', self.accept('--review', str(review)))
        self.assertFalse(self.pending.exists())
        self.assertEqual(self.receipt()['perceptual_review']['reviewer'], 'reviewer')

    def test_deprecated_flags_still_work_for_one_minor_version(self):
        output = self.run_main('--archify', 'old/cli.mjs', '--spec', str(self.candidate), '--mapping', str(self.mapping), '--illustrate', str(self.skill))
        self.assertIn('--archify is deprecated and ignored', output)
        self.assertIn('--spec is deprecated', output)
        self.assertFalse(self.pending.exists())

    def test_previous_renderer_candidate_requires_regeneration(self):
        legacy = self.artifacts / 'implementation-plan.legacy.json'
        legacy.write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(SystemExit, 'must be regenerated'):
            self.run_main('--spec', str(legacy), '--mapping', str(self.mapping))
        self.assertTrue(self.pending.exists())

    def test_pending_plan_from_previous_renderer_is_migrated_not_dropped(self):
        old = {'operation': 'op', 'issue': 9, 'required': 'Run the previous renderer and plan-accept.'}
        self.pending.write_text(json.dumps(old), encoding='utf-8')
        receipt = self.artifacts / 'scope-plan-receipt.json'
        receipt.write_text(json.dumps({'graph_sha256': 'g', 'spec_sha256': 's', 'html_sha256': 'h'}), encoding='utf-8')
        output = self.run_main('--migrate-only')
        self.assertIn('PLAN_REGENERATION_REQUIRED: issue #9', output)
        marker = json.loads(self.pending.read_text(encoding='utf-8'))
        self.assertEqual((marker['renderer'], marker['operation'], marker['migrated_from']), ('illustrate', 'op', old))
        self.assertEqual(json.loads((self.artifacts / 'scope-plan-receipt.legacy.json').read_text(encoding='utf-8'))['spec_sha256'], 's')
        self.assertFalse(receipt.exists())
        # The legacy receipt can never be reviewed as Illustrate evidence.
        review = self.root / 'review.json'
        review.write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(SystemExit, 'No Illustrate plan receipt'):
            self.accept('--review', str(review))
        self.assertIn('nothing to migrate', self.run_main('--migrate-only'))
        self.assertIn('Plan copies synchronized', self.accept())


@unittest.skipUnless(importlib.util.find_spec('playwright') and (ILLUSTRATE / 'scripts/export_diagram.py').is_file(),
                     'needs Playwright with Chromium and the Illustrate source tree')
class RealIllustrateTests(unittest.TestCase):
    """Runs the real Illustrate checks, exporter and Chromium on Illustrate's own dependency example."""

    def test_real_dependency_graph_is_accepted(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        artifacts = root / 'Design/UI-Spec/github'
        artifacts.mkdir(parents=True)
        html = (ILLUSTRATE / 'assets/example-dependency.html').read_text(encoding='utf-8')
        html = html.replace('<rect x="520" y="80" width="160" height="56" rx="6" fill="#ffffff"', '<rect data-plan-node="w1" x="520" y="80" width="160" height="56" rx="6" fill="#ffffff"', 1)
        html = html.replace('<rect x="320" y="200" width="160" height="56" rx="6" fill="#ffffff"', '<rect data-plan-node="w2" x="320" y="200" width="160" height="56" rx="6" fill="#ffffff"', 1)
        html = html.replace('<path d="M 640,136', '<path data-plan-from="w1" data-plan-to="w2" d="M 640,136', 1)
        candidate = artifacts / 'implementation-plan.illustrate.html'
        candidate.write_text(html, encoding='utf-8')
        graph = artifacts / 'scope-dependencies.json'
        graph.write_text(json.dumps({'issues': [{'number': 1, 'dependencies': [], 'children': []}, {'number': 2, 'dependencies': [1], 'children': []}]}), encoding='utf-8')
        mapping = artifacts / 'implementation-plan.mapping.json'
        mapping.write_text(json.dumps({'graph_sha256': digest(graph), 'issue_to_node': {'1': 'w1', '2': 'w2'}}), encoding='utf-8')
        pending = root / '.specify/scope/plan-pending.json'
        pending.parent.mkdir(parents=True)
        pending.write_text(json.dumps({'operation': 'op', 'issue': 1, 'renderer': 'illustrate'}), encoding='utf-8')
        try:
            with patch.object(m.subprocess, 'check_output', return_value=str(root)), redirect_stdout(io.StringIO()):
                m.main(['--html', str(candidate), '--mapping', str(mapping), '--illustrate', str(ILLUSTRATE)])
        except SystemExit as exc:
            if 'Executable doesn' in str(exc) or 'playwright install' in str(exc):
                self.skipTest('Chromium is not installed for Playwright')
            raise
        self.assertFalse(pending.exists())
        receipt = json.loads((artifacts / 'scope-plan-receipt.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['browser']['findings'], [])
        self.assertEqual(len(receipt['browser']['screenshots']), len(m.VIEWPORTS))
        self.assertTrue((artifacts / 'implementation-plan.png').is_file())


if __name__ == '__main__':
    unittest.main()
