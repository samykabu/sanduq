#!/usr/bin/env python3
"""Evaluate the project-selected workflow evidence rules for a PR."""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from workflow import load_policy, stages, read, require, inside, git, digest, checkpoint_policy_digest, receipt_current, receipt_drift, WorkflowError
import sanduq_ci


def check_candidate_merge(root, env=None):
    env = env or os.environ
    require(re.fullmatch(r'refs/pull/[1-9]\d*/merge', env.get('GITHUB_REF', ''))
            and env.get('GITHUB_SHA') == git(root, 'rev-parse', 'HEAD'),
            'CANDIDATE_MERGE_REF_REQUIRED')
    parents = git(root, 'rev-list', '--parents', '-n', '1', 'HEAD').split()
    require(len(parents) == 3 and parents[1] == env.get('BASE_SHA')
            and parents[2] == env.get('PR_HEAD_SHA'),
            'CANDIDATE_MERGE_PARENTS_MISMATCH')
    return {'merge_sha': parents[0], 'base_sha': parents[1], 'head_sha': parents[2]}


def resolve_features(root, base, explicit, allow_empty=False):
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
    require(features or allow_empty, 'FEATURE_MAPPING_REQUIRED: no changed spec evidence; pass --feature explicitly for source-only PRs')
    return sorted(features)


def check(root, feature, policy, base=None, rules=None):
    rules = rules or sanduq_ci.LEGACY_GATE_RULES
    directory = inside(root, feature)
    require(directory.is_relative_to(root / 'specs'), 'FEATURE_PATH_INVALID')
    state = read(directory / 'workflow/checkpoint.json', {})
    require(state.get('feature') == feature and state.get('schema_version') == 1, 'CHECKPOINT_MISSING_OR_WRONG_FEATURE')
    require(not state.get('active'), 'ACTIVE_STAGE_REMAINS')
    if rules['receipts']:
        require(state.get('policy_digest') == checkpoint_policy_digest(state, policy), 'POLICY_CHANGED')
    source = read(directory / 'scope-source.json', {})
    require(f"{source.get('repo')}#{source.get('issue')}" == state.get('issue'), 'FEATURE_BINDING_MISMATCH')
    if rules['receipts']:
        for stage in stages(policy):
            if stage == 'pr': continue  # PR publication follows readiness; never requires a recursive PR commit.
            receipt = state.get('receipts', {}).get(stage, {})
            require(receipt.get('outcome') == 'passed' and receipt.get('evidence'), 'RECEIPT_MISSING: ' + stage)
            if not receipt_current(root, feature, stage, receipt):
                raise WorkflowError('STALE_RECEIPT: ' + stage + '; changed paths: ' +
                                    json.dumps(receipt_drift(root, feature, stage, receipt)))
            if stage == 'clarify': require(receipt.get('unresolved') == 0 and receipt.get('answers_applied') is True, 'CLARIFICATION_UNRESOLVED')
            if stage in ('verify','review','ready'): require(receipt.get('blocking_findings') == 0, 'BLOCKING_FINDINGS_REMAIN')
    tasks = None
    if rules['tasks'] or rules['task_links']:
        from task_issues import parse_tasks
        tasks = parse_tasks((directory / 'tasks.md').read_text(encoding='utf-8-sig'))
    if rules['tasks']:
        require(all(t['done'] for t in tasks.values()), 'INCOMPLETE_TASKS')
    if rules['task_links']:
        mapping = read(directory / 'workflow/task-issues.json', {})
        repo, parent = state['issue'].split('#')
        require((mapping.get('repo'), mapping.get('parent'), mapping.get('feature')) == (repo, int(parent), feature), 'TASK_MAPPING_IDENTITY_MISMATCH')
        require(set(tasks) <= set(mapping.get('tasks', {})) and all(mapping['tasks'][t].get('linked') for t in tasks), 'TASK_MAPPING_INCOMPLETE')
    if rules['decisions']:
        from decisions import verify_ledger
        decisions = read(directory / 'workflow/decisions.json',
                         {'version': 1, 'feature': feature, 'issue': state['issue'], 'decisions': []})
        require(decisions.get('issue') == state['issue'], 'DECISION_ISSUE_MISMATCH')
        verify_ledger(root, feature, decisions)
    if rules['live_answers']:
        from decisions import GitHub, answers
        repo, number = state['issue'].split('#')
        gh = GitHub()
        issue = gh.api(f'repos/{repo}/issues/{number}')
        comments = gh.api(f'repos/{repo}/issues/{number}/comments?per_page=100', pages=True)
        live = answers(comments, issue, policy)
        require({item['id']: (item['answer_digest'], item.get('option'),
                              item.get('question_comment_id'), item.get('options'))
                 for item in decisions['decisions']} ==
                {item['id']: (digest(item['answers']), item.get('option'),
                              item.get('question_comment_id'), item.get('options'))
                 for item in live},
                'DECISION_LIVE_ANSWERS_CHANGED')
        require(all(item['status'] == 'answered' for item in live), 'DECISION_LIVE_UNRESOLVED')
    if rules['candidate_merge']:
        check_candidate_merge(root)
    checks = []
    if rules['documentation'] and policy['processes']['qa']:
        checks.append(['.specify/extensions/assure/scripts/assure_state.py', 'status', '--kind', 'document'])
    if rules['documentation'] and policy['processes']['user_manual']:
        checks.append(['.specify/extensions/user-manual/scripts/manual_state.py', 'status'])
    for args in checks:
        require((root / args[0]).is_file(), 'SELECTED_PROCESS_MISSING: ' + args[0])
        command = [sys.executable, *args, '--feature', feature, '--repo-root', str(root)]
        if base: command += ['--base-ref', base]
        result = subprocess.run(command, cwd=root, text=True, encoding='utf-8', capture_output=True)
        require(result.returncode == 0, 'DOCUMENTATION_GATE_FAILED: ' + result.stdout + result.stderr)
        require(json.loads(result.stdout).get('current') is True, 'DOCUMENTATION_NOT_CURRENT')
    return {'feature': feature, 'passed': True, 'rules': [name for name, enabled in rules.items() if enabled],
            'scope': 'selected committed evidence checks; live answers are checked when selected; human acceptance is separate'}


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
    parser.add_argument('--pr-number', default=os.environ.get('PR_NUMBER'),
                        help='PR number for an exact authorized rule waiver, when applicable')
    parser.add_argument('--check-index', action='store_true',
                        help='Require receipt dependencies in the Git index before publication')
    args = parser.parse_args(); root = args.root.resolve()
    mode = 'required'
    try:
        policy = load_policy(root)
        gate = sanduq_ci.gate_config(policy['ci'])
        mode = gate['mode']
        if mode == 'disabled':
            print(json.dumps({'ok': True, 'status': 'disabled', 'features': [], 'rules': []}, indent=2)); return 0
        features = resolve_features(root, args.base_ref, args.feature,
                                    allow_empty=gate['scope'] == 'managed-only')
        if not features:
            print(json.dumps({'ok': True, 'status': 'not_applicable', 'reason': 'no managed feature in this PR',
                              'features': [], 'rules': []}, indent=2)); return 0
        rules = gate['rules']
        results = []
        for feature in features:
            effective = dict(rules)
            applied_waivers = []
            while True:
                try:
                    if args.check_index and effective['portability']:
                        check_index(root, feature)
                    result = check(root, feature, policy, args.base_ref, effective)
                    result['waivers'] = applied_waivers
                    results.append(result)
                    break
                except WorkflowError as exc:
                    from waivers import error_rule, verify
                    rule = error_rule(exc)
                    if not args.pr_number or not rule or not effective[rule]:
                        raise
                    try:
                        waiver = verify(root, args.pr_number, feature, rule, policy)
                    except WorkflowError as waiver_error:
                        raise WorkflowError(str(exc) + '; ' + str(waiver_error)) from waiver_error
                    applied_waivers.append(waiver)
                    effective[rule] = False
        print(json.dumps({'ok': True, 'status': 'passed', 'features': results}, indent=2)); return 0
    except (WorkflowError, ValueError, OSError, KeyError) as exc:
        advisory = mode == 'advisory'
        print(json.dumps({'ok': advisory, 'status': 'advisory_findings' if advisory else 'failed',
                          'error': str(exc), 'feature_verified': False})); return 0 if advisory else 1


if __name__ == '__main__': sys.exit(main())
