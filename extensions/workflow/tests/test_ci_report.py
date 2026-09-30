"""B13: speckit-workflow-ci-report reads run/job data through the same GhClient contract
Verify evidence already uses, and computes fixed-vs-test time only from what --fixed-job names."""
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

    def test_build_report_computes_critical_path_and_fixed_vs_test(self):
        result = report.build_report(self.client(), 'acme/app', 'ci.yml', 10, fixed_job_names=['setup'])
        row = result['runs'][0]
        self.assertEqual(row['run_id'], 1)
        self.assertEqual(row['critical_path_seconds'], 300.0)
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


if __name__ == '__main__':
    unittest.main()
