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

This is a local, uncertified run: it stamps `source: "local"` and
`ci_grade: false` on both the returned summary and the results.json itself
(review round 1, finding 7). It is evidence a developer can act on, never a
substitute for the project's actual CI run -- do not record it as a Verify
receipt's `ci_evidence`; that field is written only by
`workflow.py revalidate --stage verify --check-run`, which re-reads a real
CI run through the GitHub REST API.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delegate_dispatch as dd
import sanduq_ci
from workflow import WorkflowError, affected_command, affected_lanes, gate_settings, git, inside, load_policy, require

# Bytes kept per output stream before it is discarded (delegate_dispatch's own cap).
OUTPUT_CAP = 200_000
# A spool file past this many bytes while the command is still running kills it.
HARD_OUTPUT_LIMIT = 10 * OUTPUT_CAP
POLL_SECONDS = 0.25


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
    """Repository-relative paths that differ between `base_ref` and the actual working tree.

    Diffing only `base_ref..HEAD` (finding 6) would give a false green for an
    uncommitted edit: `git diff <comparison>` (one ref) compares against the
    working tree instead, which is a superset of `<comparison>..HEAD` (it
    includes every committed change plus staged and unstaged ones), and
    untracked files are added separately since a diff never reports them.
    """
    try:
        comparison = git(root, 'merge-base', 'HEAD', base_ref)
    except WorkflowError as exc:
        raise VerifyAffectedError('BASE_HISTORY_UNAVAILABLE: fetch the target ref; ' + str(exc)) from exc
    working = git(root, 'diff', '--name-only', '-z', comparison).split('\0')
    untracked = git(root, 'ls-files', '--others', '--exclude-standard', '-z').split('\0')
    changed = set(working) | set(untracked)
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


def run_lanes(root, command, lanes, results_path, timeout=3600):
    """Run the project's local verifier over exactly `lanes`, writing `results_path`.

    Mirrors `delegate_dispatch.run_capped` (which has no stdin): the child
    starts in its own session on POSIX (`start_new_session=True`), so
    `kill_process_tree`'s `killpg` on a timeout kills only the verifier's own
    tree and never this process's group (round 2, blocker 1: without it the
    group was the test runner's own and a timeout SIGKILLed the runner).
    stdin is a temp file and stdout/stderr spool to temp files of which only
    `OUTPUT_CAP` bytes are ever read back, so a runaway command cannot exhaust
    memory while being buffered.
    """
    payload = json.dumps({'lanes': sorted(lanes), 'results_path': results_path}).encode('utf-8')
    popen_kwargs = {} if os.name == 'nt' else {'start_new_session': True}
    with tempfile.TemporaryFile() as in_file, tempfile.TemporaryFile() as out_file,             tempfile.TemporaryFile() as err_file:
        in_file.write(payload)
        in_file.seek(0)
        try:
            proc = subprocess.Popen(command, cwd=root, stdin=in_file, stdout=out_file, stderr=err_file,
                                    **popen_kwargs)
        except OSError as exc:
            raise VerifyAffectedError('VERIFY_COMMAND_FAILED: ' + str(exc)) from exc
        # Poll instead of one blocking wait so the cap is enforced *while the
        # command runs*: a spool file that passes HARD_OUTPUT_LIMIT (round 3,
        # finding 5) gets the whole process tree killed before it fills the disk.
        deadline = time.monotonic() + timeout
        failure = None
        while True:
            try:
                proc.wait(timeout=POLL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                pass
            if max(os.fstat(out_file.fileno()).st_size, os.fstat(err_file.fileno()).st_size) > HARD_OUTPUT_LIMIT:
                failure = 'VERIFY_COMMAND_OUTPUT_LIMIT: output exceeded ' + str(HARD_OUTPUT_LIMIT) + ' bytes'
            elif time.monotonic() >= deadline:
                failure = 'VERIFY_COMMAND_TIMEOUT: exceeded ' + str(timeout) + 's'
            if failure:
                dd.kill_process_tree(proc)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
                raise VerifyAffectedError(failure)
        out_file.seek(0)
        err_file.seek(0)
        stdout = out_file.read(OUTPUT_CAP).decode('utf-8', errors='replace')
        stderr = err_file.read(OUTPUT_CAP).decode('utf-8', errors='replace')
    require(proc.returncode == 0, 'VERIFY_COMMAND_FAILED: exit ' + str(proc.returncode) + ': ' +
            (stderr or stdout).strip()[:500])
    return stdout


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


def validate_results(results, requested):
    """(missing lanes, failed lanes, schema_ok) for a verifier's results (round 3, finding 4).

    Exit 0 plus *any* JSON is not a pass: the results must be an object with a
    `lanes` object, carry every requested lane, and each lane's `outcome` must
    be `passed`. A lane whose entry is malformed counts as failed.
    """
    lanes = results.get('lanes') if isinstance(results, dict) else None
    if not isinstance(lanes, dict):
        return sorted(requested), [], False
    missing = sorted(lane for lane in requested if lane not in lanes)
    failed = sorted(lane for lane in requested if lane in lanes and not (
        isinstance(lanes[lane], dict) and lanes[lane].get('outcome') == 'passed'))
    return missing, failed, True


def run(root, feature, base_ref, extra_lanes=None, results_path=None, timeout=3600):
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
    inside(root, results_path)  # finding 8: --results must stay inside the repo
    command = verify_command(policy)
    require(command, 'VERIFY_COMMAND_UNSET: set ci.gate.verify_command to a project-local runner')
    (root / results_path).parent.mkdir(parents=True, exist_ok=True)
    run_lanes(root, command, lanes, results_path, timeout)
    results = read_results(root, results_path)
    # Finding 7: this run is never CI evidence -- stamp both the file and the
    # returned summary so nothing downstream can mistake one for the other.
    # A results file that is not a JSON object is wrapped, never left unstamped.
    results = ({**results, 'source': 'local', 'ci_grade': False} if isinstance(results, dict)
               else {'results': results, 'source': 'local', 'ci_grade': False})
    (root / results_path).write_text(json.dumps(results, indent=2), encoding='utf-8')
    missing, failed, schema_ok = validate_results(results, lanes)
    ok = schema_ok and not missing and not failed
    return {'ok': ok, 'status': 'ran' if ok else 'failed', 'diffed_paths': paths, 'lanes': sorted(lanes),
            'results_path': results_path, 'source': 'local', 'ci_grade': False,
            'missing_lanes': missing, 'failed_lanes': failed, 'results_schema_valid': schema_ok,
            'results_summary': summarize(results)}


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
        return 0 if result.get('ok') else 1
    except WorkflowError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, indent=2))
        return 1


if __name__ == '__main__':
    sys.exit(main())
