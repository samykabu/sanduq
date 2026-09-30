"""B13: speckit-workflow-ci-report reads run/job data through the same GhClient contract
Verify evidence already uses, and computes fixed-vs-test time only from what --fixed-job names."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ci_report as report
from ci_evidence import EvidenceError


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def api(self, endpoint):
        self.calls.append(endpoint)
        for prefix, value in self.responses.items():
            if endpoint.startswith(prefix):
                return value
        raise AssertionError('Unexpected endpoint: ' + endpoint)


class PagedClient:
    """A fake GitHub client that actually paginates, honouring the caller's own `per_page` and
    `page` query params against a flat list keyed by endpoint prefix -- so a pagination bug
    (finding 9) shows up as a wrong item count or a hang, not as a fake that always returns
    everything on page 1 regardless of what was asked for."""

    def __init__(self, items_by_prefix):
        self.items_by_prefix = items_by_prefix
        self.calls = []

    def api(self, endpoint):
        self.calls.append(endpoint)
        for prefix, items in self.items_by_prefix.items():
            if endpoint.startswith(prefix):
                page = int(re.search(r'[?&]page=(\d+)', endpoint).group(1))
                per_page = int(re.search(r'per_page=(\d+)', endpoint).group(1))
                start = (page - 1) * per_page
                key = 'workflow_runs' if 'workflow_runs' in items else 'jobs'
                return {key: items[key][start:start + per_page]}
        raise AssertionError('Unexpected endpoint: ' + endpoint)


RUNS = {'workflow_runs': [
    {'id': 1, 'conclusion': 'success', 'status': 'completed', 'created_at': '2026-01-01T00:00:00Z', 'head_sha': 'a'},
    {'id': 2, 'conclusion': 'cancelled', 'status': 'completed', 'created_at': '2026-01-02T00:00:00Z', 'head_sha': 'b'},
]}
JOBS_1 = {'jobs': [
    {'name': 'setup', 'conclusion': 'success', 'started_at': '2026-01-01T00:00:00Z', 'completed_at': '2026-01-01T00:01:00Z'},
    {'name': 'test-lane-a', 'conclusion': 'success', 'started_at': '2026-01-01T00:01:00Z', 'completed_at': '2026-01-01T00:05:00Z'},
]}
JOBS_2 = {'jobs': []}


class CIReportTests(unittest.TestCase):
    def client(self):
        return FakeClient({
            'repos/acme/app/actions/workflows/ci.yml/runs': RUNS,
            'repos/acme/app/actions/runs/1/jobs': JOBS_1,
            'repos/acme/app/actions/runs/2/jobs': JOBS_2,
        })

    def test_build_report_computes_wall_clock_span_and_fixed_vs_test(self):
        result = report.build_report(self.client(), 'acme/app', 'ci.yml', 10, fixed_job_names=['setup'])
        row = result['runs'][0]
        self.assertEqual(row['run_id'], 1)
        self.assertEqual(row['wall_clock_span_seconds'], 300.0)
        self.assertEqual(row['fixed_seconds'], 60.0)
        self.assertEqual(row['test_seconds'], 240.0)

    def test_without_fixed_job_everything_counts_as_test(self):
        result = report.build_report(self.client(), 'acme/app', 'ci.yml', 10)
        row = result['runs'][0]
        self.assertEqual(row['fixed_seconds'], 0.0)
        self.assertEqual(row['test_seconds'], 300.0)

    def test_cancelled_runs_are_counted(self):
        result = report.build_report(self.client(), 'acme/app', 'ci.yml', 10)
        self.assertEqual(result['cancelled_runs'], 1)
        self.assertTrue(result['runs'][1]['cancelled'])

    def test_limit_bounds_the_run_count(self):
        result = report.build_report(self.client(), 'acme/app', 'ci.yml', 1)
        self.assertEqual(len(result['runs']), 1)

    def test_unexpected_shape_raises_evidence_error(self):
        client = FakeClient({'repos/acme/app/actions/workflows/ci.yml/runs': {'nope': True}})
        with self.assertRaises(EvidenceError):
            report.fetch_runs(client, 'acme/app', 'ci.yml', 5)

    def test_markdown_render_includes_run_and_leg_rows(self):
        result = report.build_report(self.client(), 'acme/app', 'ci.yml', 10, fixed_job_names=['setup'])
        markdown = report.render_markdown(result)
        self.assertIn('| 1 | success |', markdown)
        self.assertIn('| 1 | setup | success | 60 | yes |', markdown)
        self.assertIn('| 1 | test-lane-a | success | 240 | no |', markdown)

    def test_fetch_runs_paginates_past_the_100_per_page_cap(self):
        # Review round 1, finding 9: a limit over 100 must not silently
        # truncate at GitHub's own per-page cap.
        runs = [{'id': i, 'conclusion': 'success', 'status': 'completed',
                'created_at': '2026-01-01T00:00:00Z', 'head_sha': str(i)} for i in range(1, 151)]
        client = PagedClient({'repos/acme/app/actions/workflows/ci.yml/runs': {'workflow_runs': runs}})
        result = report.fetch_runs(client, 'acme/app', 'ci.yml', 150)
        self.assertEqual(len(result), 150)
        self.assertEqual([r['id'] for r in result], list(range(1, 151)))
        self.assertEqual(len(client.calls), 2)  # one 100-item page, one 50-item page

    def test_fetch_jobs_paginates_past_the_100_per_page_cap(self):
        jobs = [{'name': f'leg-{i}', 'conclusion': 'success', 'started_at': '2026-01-01T00:00:00Z',
                'completed_at': '2026-01-01T00:01:00Z'} for i in range(120)]
        client = PagedClient({'repos/acme/app/actions/runs/1/jobs': {'jobs': jobs}})
        result = report.fetch_jobs(client, 'acme/app', 1)
        self.assertEqual(len(result), 120)
        self.assertEqual(len(client.calls), 2)

    def test_branch_is_url_encoded(self):
        client = self.client()
        report.fetch_runs(client, 'acme/app', 'ci.yml', 10, branch='feature/needs encoding')
        self.assertTrue(any('branch=feature%2Fneeds%20encoding' in call for call in client.calls), client.calls)


if __name__ == '__main__':
    unittest.main()
