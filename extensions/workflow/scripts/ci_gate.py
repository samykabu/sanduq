#!/usr/bin/env python3
"""Validate required workflow evidence for every feature changed by a PR."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from workflow import load_policy, stages, read, require, inside, git, digest, receipt_current, receipt_drift, WorkflowError


def resolve_features(root, base, explicit):
    try:
        comparison = git(root, 'merge-base', 'HEAD', base)
    except WorkflowError as exc:
        raise WorkflowError('BASE_HISTORY_UNAVAILABLE: fetch the target and PR history (checkout fetch-depth: 0); ' + str(exc)) from exc
    changed = git(root, 'diff', '--name-only', '-z', comparison, 'HEAD').split('\0')
    features = set(explicit)
    for path in changed:
        parts = Path(path).parts
        if len(parts) >= 3 and parts[0] == 'specs': features.add('/'.join(parts[:2]))
    mapping = '.specify/workflow/pr-features.json'
    if mapping in changed:
        values = read(root / mapping, {}).get('features')
        require(isinstance(values, list) and values and all(isinstance(v, str) for v in values), 'PR_FEATURE_MAPPING_INVALID')
        features.update(values)
    require(features, 'FEATURE_MAPPING_REQUIRED: no changed spec evidence; pass --feature explicitly for source-only PRs')
    return sorted(features)


def check(root, feature, policy, base=None):
    directory = inside(root, feature)
    require(directory.is_relative_to(root / 'specs'), 'FEATURE_PATH_INVALID')
    state = read(directory / 'workflow/checkpoint.json', {})
    require(state.get('feature') == feature and state.get('schema_version') == 1, 'CHECKPOINT_MISSING_OR_WRONG_FEATURE')
    require(not state.get('active'), 'ACTIVE_STAGE_REMAINS')
    require(state.get('policy_digest') == digest(policy), 'POLICY_CHANGED')
    source = read(directory / 'scope-source.json', {})
    require(f"{source.get('repo')}#{source.get('issue')}" == state.get('issue'), 'FEATURE_BINDING_MISMATCH')
    for stage in stages(policy):
        if stage == 'pr': continue  # PR publication follows readiness; never requires a recursive PR commit.
        receipt = state.get('receipts', {}).get(stage, {})
        require(receipt.get('outcome') == 'passed' and receipt.get('evidence'), 'RECEIPT_MISSING: ' + stage)
        if not receipt_current(root, feature, stage, receipt):
            raise WorkflowError('STALE_RECEIPT: ' + stage + '; changed paths: ' +
                                json.dumps(receipt_drift(root, feature, stage, receipt)))
        if stage == 'clarify': require(receipt.get('unresolved') == 0 and receipt.get('answers_applied') is True, 'CLARIFICATION_UNRESOLVED')
        if stage in ('verify','review','ready'): require(receipt.get('blocking_findings') == 0, 'BLOCKING_FINDINGS_REMAIN')
    from task_issues import parse_tasks
    tasks = parse_tasks((directory / 'tasks.md').read_text(encoding='utf-8-sig'))
    require(all(t['done'] for t in tasks.values()), 'INCOMPLETE_TASKS')
    mapping = read(directory / 'workflow/task-issues.json', {})
    repo, parent = state['issue'].split('#')
    require((mapping.get('repo'), mapping.get('parent'), mapping.get('feature')) == (repo, int(parent), feature), 'TASK_MAPPING_IDENTITY_MISMATCH')
    require(set(tasks) <= set(mapping.get('tasks', {})) and all(mapping['tasks'][t].get('linked') for t in tasks), 'TASK_MAPPING_INCOMPLETE')
    checks = []
    if policy['processes']['qa']:
        checks.append(['.specify/extensions/assure/scripts/assure_state.py', 'status', '--kind', 'document'])
    if policy['processes']['user_manual']:
        checks.append(['.specify/extensions/user-manual/scripts/manual_state.py', 'status'])
    for args in checks:
        require((root / args[0]).is_file(), 'SELECTED_PROCESS_MISSING: ' + args[0])
        command = [sys.executable, *args, '--feature', feature, '--repo-root', str(root)]
        if base: command += ['--base-ref', base]
        result = subprocess.run(command, cwd=root, text=True, encoding='utf-8', capture_output=True)
        require(result.returncode == 0, 'DOCUMENTATION_GATE_FAILED: ' + result.stdout + result.stderr)
        require(json.loads(result.stdout).get('current') is True, 'DOCUMENTATION_NOT_CURRENT')
    return {'feature': feature, 'passed': True, 'scope': 'committed evidence freshness; live GitHub and human acceptance are separate'}


def check_index(root, feature):
    """Catch local-only receipt dependencies before publishing. Never stages files."""
    checkpoint = feature + '/workflow/checkpoint.json'
    state = read(inside(root, checkpoint), {})
    require(state.get('feature') == feature, 'CHECKPOINT_MISSING_OR_WRONG_FEATURE: ' + feature)
    paths = {checkpoint, '.specify/workflow.yml'}
    for stage, receipt in state.get('receipts', {}).items():
        if stage == 'pr':
            continue
        for key in ('fingerprints', 'source_fingerprints'):
            paths.update(p for p, value in receipt.get(key, {}).items() if value is not None)
    tracked = set(git(root, 'ls-files', '--cached', '-z').split('\0'))
    unstaged = set(git(root, 'diff', '--name-only', '-z').split('\0'))
    missing = sorted(paths - tracked)
    modified = sorted(paths & unstaged)
    require(not missing and not modified, 'EVIDENCE_NOT_PORTABLE: ' +
            json.dumps({'not_in_index': missing, 'unstaged': modified}))
    return {'feature': feature, 'indexed_paths': len(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--feature', action='append', default=[])
    parser.add_argument('--base-ref', required=True)
    parser.add_argument('--check-index', action='store_true',
                        help='Require receipt dependencies in the Git index before publication')
    args = parser.parse_args(); root = args.root.resolve()
    try:
        policy = load_policy(root)
        features = resolve_features(root, args.base_ref, args.feature)
        if args.check_index:
            for feature in features:
                check_index(root, feature)
        results = [check(root, feature, policy, args.base_ref) for feature in features]
        print(json.dumps({'ok': True, 'features': results}, indent=2)); return 0
    except (WorkflowError, ValueError, OSError, KeyError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)})); return 1


if __name__ == '__main__': sys.exit(main())
