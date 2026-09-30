#!/usr/bin/env python3
"""Run the project's affected lanes locally, producing the same results.json CI would (B13).

Reuses the classify contract Verify/Review/Ready already trust
(`ci.gate.affected_command`, `workflow.affected_lanes`) to turn a diff into a
lane set, then hands that lane set to a second, optional, equally
project-agnostic hook (`ci.gate.verify_command`) that actually runs them and
writes a results file. Sanduq never runs tests itself: both hooks are the
project's own commands, read from `.specify/workflow.yml`, so this script
stays portable across projects and hosts.

`ci.gate.verify_command` contract: an argv list or command string (same
shape as `affected_command`). It is run with a JSON object on stdin,
`{"lanes": [<lane>, ...], "results_path": "<project-relative path>"}`, in the
repository root, and must exit 0 and leave valid JSON at that path -- the
same results.json shape the project's own CI tier writes, so downstream
tooling (summarizers, the gate) reads one format either way.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sanduq_ci
from workflow import WorkflowError, affected_command, affected_lanes, gate_settings, git, load_policy, require


class VerifyAffectedError(WorkflowError):
    """Raised with the same `CODE: detail` shape as the rest of the runtime."""


def verify_command(policy):
    """The optional local runner (`ci.gate.verify_command`) as an argv list, or None.

    Delegates to `sanduq_ci.verify_command`, the one place that contract is
    parsed, so this script and `validate_gate` never disagree.
    """
    try:
        return sanduq_ci.verify_command(gate_settings(policy))
    except sanduq_ci.CIPolicyError as exc:
        raise VerifyAffectedError(str(exc)) from exc


def diffed_paths(root, base_ref):
    """Repository-relative paths that differ between `base_ref` and HEAD."""
    try:
        comparison = git(root, 'merge-base', 'HEAD', base_ref)
    except WorkflowError as exc:
        raise VerifyAffectedError('BASE_HISTORY_UNAVAILABLE: fetch the target ref; ' + str(exc)) from exc
    changed = git(root, 'diff', '--name-only', '-z', comparison, 'HEAD').split('\0')
    return sorted(path for path in changed if path)


def affected_lane_set(root, policy, paths):
    """The union of lanes the project's affected-lane hook assigns to `paths`, or
    None when there is nothing to classify with (no hook configured).

    A path the hook maps to no lane contributes nothing (mirrors the gate's
    own `lane-free-drift` rule); an empty `paths` list needs no hook call.
    """
    if not paths:
        return set()
    command = affected_command(policy)
    if not command:
        return None
    lanes = affected_lanes(root, command, paths)
    result = set()
    for value in lanes.values():
        result.update(value)
    return result


def run_lanes(root, command, lanes, results_path):
    """Run the project's local verifier over exactly `lanes`, writing `results_path`."""
    payload = json.dumps({'lanes': sorted(lanes), 'results_path': results_path})
    try:
        result = subprocess.run(command, cwd=root, input=payload, capture_output=True,
                                text=True, encoding='utf-8', timeout=3600)
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerifyAffectedError('VERIFY_COMMAND_FAILED: ' + str(exc)) from exc
    require(result.returncode == 0, 'VERIFY_COMMAND_FAILED: exit ' + str(result.returncode) + ': ' +
            (result.stderr or result.stdout).strip()[:500])
    return result.stdout


def read_results(root, results_path):
    path = root / results_path
    require(path.is_file(), 'VERIFY_RESULTS_MISSING: ' + results_path)
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except ValueError as exc:
        raise VerifyAffectedError('VERIFY_RESULTS_INVALID: ' + results_path + ': ' + str(exc)) from exc


def summarize(results):
    """Best-effort pass/fail counts when `results` has a recognizable `{"lanes": {...}}` shape."""
    lanes = results.get('lanes') if isinstance(results, dict) else None
    if not isinstance(lanes, dict):
        return None
    passed = sum(1 for value in lanes.values() if isinstance(value, dict) and value.get('outcome') == 'passed')
    failed = sum(1 for value in lanes.values() if isinstance(value, dict) and value.get('outcome') not in (None, 'passed'))
    return {'lanes': len(lanes), 'passed': passed, 'failed': failed}


def run(root, feature, base_ref, extra_lanes=None, results_path=None):
    root = root.resolve()
    policy = load_policy(root)
    paths = diffed_paths(root, base_ref)
    extra_lanes = set(extra_lanes or [])
    classified = affected_lane_set(root, policy, paths)
    if classified is None:
        require(extra_lanes, 'AFFECTED_COMMAND_UNSET: set ci.gate.affected_command, or pass --lane explicitly')
        lanes = extra_lanes
    else:
        lanes = classified | extra_lanes
    results_path = results_path or (feature + '/workflow/verify-affected-results.json')
    if not lanes:
        return {'ok': True, 'status': 'no_affected_lanes', 'diffed_paths': paths, 'lanes': [], 'results_path': None}
    command = verify_command(policy)
    require(command, 'VERIFY_COMMAND_UNSET: set ci.gate.verify_command to a project-local runner')
    (root / results_path).parent.mkdir(parents=True, exist_ok=True)
    run_lanes(root, command, lanes, results_path)
    results = read_results(root, results_path)
    return {'ok': True, 'status': 'ran', 'diffed_paths': paths, 'lanes': sorted(lanes),
            'results_path': results_path, 'results_summary': summarize(results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--feature', required=True)
    parser.add_argument('--base-ref', required=True)
    parser.add_argument('--lane', action='append', default=[], help='Extra lane to always run, repeatable')
    parser.add_argument('--results', dest='results_path', default=None,
                        help='Project-relative results.json path (default: <feature>/workflow/verify-affected-results.json)')
    args = parser.parse_args()
    try:
        result = run(args.root, args.feature, args.base_ref, args.lane, args.results_path)
        print(json.dumps(result, indent=2))
        return 0
    except WorkflowError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, indent=2))
        return 1


if __name__ == '__main__':
    sys.exit(main())
