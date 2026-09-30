#!/usr/bin/env python3
"""Summarize the last N CI runs of a workflow: legs, cancellations, and a critical path (B13).

Reads exclusively through the GitHub REST API (`ci_evidence.GhClient`, the
same `gh api` wrapper Verify evidence already uses), so it needs no new
credential handling. Every figure is derived from `started_at`/`completed_at`
timestamps the API returns; nothing is estimated or invented. "Fixed" time is
the duration of jobs whose name matches `--fixed-job` (repeatable); everything
else is counted as test time. Without `--fixed-job`, every job's time counts
as test time and fixed is reported as zero -- an honest default, not a guess.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_evidence import EvidenceError, GhClient


def _parse(timestamp):
    if not timestamp:
        return None
    return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')


def _duration_seconds(start, end):
    start, end = _parse(start), _parse(end)
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds())


def fetch_runs(client, repository, workflow, limit, branch=None):
    endpoint = f'repos/{repository}/actions/workflows/{workflow}/runs?per_page={limit}'
    if branch:
        endpoint += '&branch=' + branch
    data = client.api(endpoint)
    runs = data.get('workflow_runs') if isinstance(data, dict) else None
    if not isinstance(runs, list):
        raise EvidenceError('Unexpected /actions/workflows/.../runs response shape')
    return runs[:limit]


def fetch_jobs(client, repository, run_id):
    data = client.api(f'repos/{repository}/actions/runs/{run_id}/jobs?per_page=100')
    jobs = data.get('jobs') if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        raise EvidenceError('Unexpected /actions/runs/.../jobs response shape')
    return jobs


def summarize_run(run, jobs, fixed_job_names):
    legs = []
    for job in jobs:
        duration = _duration_seconds(job.get('started_at'), job.get('completed_at'))
        legs.append({'name': job.get('name'), 'conclusion': job.get('conclusion'),
                    'duration_seconds': duration, 'fixed': job.get('name') in fixed_job_names})
    starts = [job.get('started_at') for job in jobs if job.get('started_at')]
    ends = [job.get('completed_at') for job in jobs if job.get('completed_at')]
    critical_path = None
    if starts and ends:
        earliest, latest = min(starts), max(ends)
        critical_path = _duration_seconds(earliest, latest)
    fixed_seconds = sum(leg['duration_seconds'] or 0 for leg in legs if leg['fixed'])
    test_seconds = sum(leg['duration_seconds'] or 0 for leg in legs if not leg['fixed'])
    return {'run_id': run.get('id'), 'conclusion': run.get('conclusion'), 'status': run.get('status'),
            'created_at': run.get('created_at'), 'head_sha': run.get('head_sha'),
            'cancelled': run.get('conclusion') == 'cancelled', 'legs': legs,
            'critical_path_seconds': critical_path, 'fixed_seconds': fixed_seconds, 'test_seconds': test_seconds}


def build_report(client, repository, workflow, limit, branch=None, fixed_job_names=None):
    fixed_job_names = set(fixed_job_names or ())
    runs = fetch_runs(client, repository, workflow, limit, branch)
    rows = []
    for run in runs:
        jobs = fetch_jobs(client, repository, run['id'])
        rows.append(summarize_run(run, jobs, fixed_job_names))
    return {'repository': repository, 'workflow': workflow, 'runs': rows,
            'cancelled_runs': sum(1 for row in rows if row['cancelled']),
            'total_fixed_seconds': sum(row['fixed_seconds'] for row in rows),
            'total_test_seconds': sum(row['test_seconds'] for row in rows)}


def render_markdown(report):
    lines = [f"# CI report: {report['workflow']} ({report['repository']})", '',
             f"{len(report['runs'])} run(s); {report['cancelled_runs']} cancelled; "
             f"fixed {report['total_fixed_seconds']:.0f}s, test {report['total_test_seconds']:.0f}s.", '',
             '| Run | Conclusion | Created | Critical path (s) | Fixed (s) | Test (s) |',
             '| --- | --- | --- | --- | --- | --- |']
    for row in report['runs']:
        critical = '' if row['critical_path_seconds'] is None else f"{row['critical_path_seconds']:.0f}"
        lines.append(f"| {row['run_id']} | {row['conclusion']} | {row['created_at']} | {critical} | "
                     f"{row['fixed_seconds']:.0f} | {row['test_seconds']:.0f} |")
    lines.append('')
    lines.append('| Run | Leg | Conclusion | Duration (s) | Fixed |')
    lines.append('| --- | --- | --- | --- | --- |')
    for row in report['runs']:
        for leg in row['legs']:
            duration = '' if leg['duration_seconds'] is None else f"{leg['duration_seconds']:.0f}"
            lines.append(f"| {row['run_id']} | {leg['name']} | {leg['conclusion']} | {duration} | "
                         f"{'yes' if leg['fixed'] else 'no'} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, help='owner/repo')
    parser.add_argument('--workflow', required=True, help='Workflow file name or numeric ID')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--branch')
    parser.add_argument('--fixed-job', action='append', default=[], dest='fixed_job_names')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        report = build_report(GhClient(), args.repository, args.workflow, args.limit, args.branch, args.fixed_job_names)
    except EvidenceError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, indent=2))
        return 1
    print(json.dumps(report, indent=2) if args.json else render_markdown(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
