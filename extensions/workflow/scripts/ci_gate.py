#!/usr/bin/env python3
"""Evaluate the project-selected workflow evidence rules for a PR."""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from workflow import (load_policy, stages, read, require, inside, git, digest, checkpoint_policy_digest, receipt_status,
                      receipt_drift, recovery_recipe, ready_checks, github_repository, verification_check, WorkflowError,
                      WORKFLOW_SCRIPT)
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
        raise WorkflowError('BASE_HISTORY_UNAVAILABLE: fetch the target and PR history '
                            '(an unbounded fetch of the base ref, or checkout fetch-depth: 0); ' + str(exc)) from exc
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


def recheck_ci_evidence(root, feature, stage, receipt, policy, github=None):
    """Re-read a Verify receipt's recorded CI run through the REST API.

    `ci_evidence` is runtime-written, but it lives in a committed checkpoint,
    so the gate never trusts the record alone: every Verify receipt accepted
    through it is re-read here and the plan contract re-applied to the live
    run. A run that cannot be read (no policy check, no token, an API error)
    fails closed.
    """
    import ci_evidence
    import source_key as sk
    recorded = receipt['ci_evidence']
    check = verification_check(policy)
    require(check, 'CI_VERIFICATION_CHECK_UNSET: ' + feature + ': Verify is accepted through CI run ' +
            str(recorded.get('run_id')) + ', which the gate must re-read; set ci.gate.verification_check or '
            're-record Verify')
    repository = github_repository(root)
    try:
        evidence = ci_evidence.collect(github or ci_evidence.GhClient(), repository, int(recorded['run_id']),
                                       recorded.get('attempt'), check['artifact_prefix'])
    except (ci_evidence.EvidenceError, OSError, ValueError) as exc:
        raise WorkflowError('CI_EVIDENCE_UNREADABLE: ' + stage + ': run ' + str(recorded.get('run_id')) + ': ' +
                            str(exc) + ' (the gate job needs permissions actions: read and GH_TOKEN)') from exc
    plan = evidence['plan'] if isinstance(evidence.get('plan'), dict) else {}
    head = plan.get('headSha')
    local = None
    if isinstance(head, str) and ci_evidence.SHA.match(head):
        try:
            local = {'tree': sk.tree_of(root, head), 'key': sk.source_key(root, head)}
        except sk.SourceKeyError:
            local = {'tree': 'unavailable (fetch ' + head + ')', 'key': 'unavailable'}
    errors = ci_evidence.validate(evidence, repository, int(recorded['run_id']), check['name'], check['workflow'],
                                  recorded.get('attempt'), local, check['artifact_prefix'])
    if not errors and (plan.get('sourceKey') != recorded.get('source_key') or head != recorded.get('head')):
        errors.append('The run no longer matches the recorded ci_evidence.')
    require(not errors, 'CI_EVIDENCE_REJECTED: ' + stage + ': run ' + str(recorded['run_id']) + ': ' + ' '.join(errors))


def check(root, feature, policy, base=None, rules=None, verify_ci_evidence=True, github=None):
    """Evaluate the selected evidence rules for one feature.

    `verify_ci_evidence` is kept for callers of 1.6.0 and changes nothing: a
    Verify receipt accepted through `ci_evidence` is always re-read.
    """
    rules = rules or sanduq_ci.LEGACY_GATE_RULES
    directory = inside(root, feature)
    require(directory.is_relative_to(root / 'specs'), 'FEATURE_PATH_INVALID')
    state = read(directory / 'workflow/checkpoint.json', {})
    require(state.get('feature') == feature and state.get('schema_version') == 1, 'CHECKPOINT_MISSING_OR_WRONG_FEATURE')
    require(not state.get('active'), 'ACTIVE_STAGE_REMAINS')
    if rules['receipts']:
        require(state.get('policy_digest') == checkpoint_policy_digest(state, policy),
                'POLICY_CHANGED: recovery: ' + WORKFLOW_SCRIPT + ' migrate --feature ' + feature + ' --preview, review '
                'the invalidated list, then ' + WORKFLOW_SCRIPT + ' migrate --feature ' + feature + ' --reason "<why>" '
                '(on the feature branch) and re-record any invalidated stage')
    source = read(directory / 'scope-source.json', {})
    require(f"{source.get('repo')}#{source.get('issue')}" == state.get('issue'), 'FEATURE_BINDING_MISMATCH')
    amendments, revalidations, accepted, warnings = [], [], [], []
    if rules['receipts']:
        for stage in stages(policy):
            if stage == 'pr': continue  # PR publication follows readiness; never requires a recursive PR commit.
            receipt = state.get('receipts', {}).get(stage, {})
            require(receipt.get('outcome') == 'passed' and receipt.get('evidence'), 'RECEIPT_MISSING: ' + stage)
            status = receipt_status(root, feature, stage, receipt, policy)
            if not status['current']:
                stale = receipt.get('stale')
                note = ''
                if isinstance(stale, dict) and stale.get('reason') == 'ci-lane-gap':
                    note = ('; marked stale by a lane gap of run ' + str(stale.get('run_id')) + ': ' +
                            ', '.join(stale.get('lanes') or []))
                elif isinstance(stale, dict):
                    note = ('; marked stale by a changed amendment of ' + stale.get('stage', '?') + ' evidence ' +
                            stale.get('path', '?'))
                if status.get('rule') == 'classification-failed':
                    note += '; the affected-lane hook failed (fails closed): ' + str(status.get('error'))
                elif status.get('rule') == 'affected-lanes':
                    note += '; drift reaching lanes: ' + json.dumps(status['lanes'])
                raise WorkflowError('STALE_RECEIPT: ' + stage + '; changed paths: ' +
                                    json.dumps(receipt_drift(root, feature, stage, receipt)) + note +
                                    '; recovery: ' + ' | '.join(recovery_recipe(feature, stage, status, policy, receipt)))
            if status.get('via') in ('ci-evidence', 'lane-free-drift'):
                accepted.append({'stage': stage, 'via': status['via'], 'drift': status.get('paths', []),
                                 **({'run_id': status.get('run_id')} if status['via'] == 'ci-evidence' else {})})
                if status['via'] == 'ci-evidence':
                    recheck_ci_evidence(root, feature, stage, receipt, policy, github)
            revalidations += [{'stage': stage, **{key: item.get(key) for key in
                               ('via', 'outcome', 'at', 'actor', 'run_id', 'evidence', 'lane_gap')}}
                              for item in receipt.get('revalidations', [])]
            # An amended receipt is accepted like any current one; the reviewer sees each amendment.
            amendments += [{'stage': stage, **{key: item.get(key) for key in
                            ('path', 'assessment', 'reason', 'actor', 'at', 'old_hash', 'new_hash')}}
                           for item in receipt.get('amendments', [])]
            if stage == 'clarify': require(receipt.get('unresolved') == 0 and receipt.get('answers_applied') is True, 'CLARIFICATION_UNRESOLVED')
            if stage in ('verify','review','ready'): require(receipt.get('blocking_findings') == 0, 'BLOCKING_FINDINGS_REMAIN')
    ready_checks(root, feature, policy, state, base, {'tasks': rules['tasks'], 'task_links': rules['task_links']},
                warnings=warnings)
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
    ready_checks(root, feature, policy, state, base, {'documentation': rules['documentation']}, warnings=warnings)
    return {'feature': feature, 'passed': True, 'rules': [name for name, enabled in rules.items() if enabled],
            'amendments': amendments, 'revalidations': revalidations, 'accepted_drift': accepted,
            'warnings': warnings,
            'scope': 'selected committed evidence checks; live answers are checked when selected; human acceptance is separate'}


def check_index(root, feature):
    """Catch local-only receipt dependencies before publishing. Never stages files."""
    checkpoint = feature + '/workflow/checkpoint.json'
    state = read(inside(root, checkpoint), {})
    require(state.get('feature') == feature, 'CHECKPOINT_MISSING_OR_WRONG_FEATURE: ' + feature)
    paths = {checkpoint, '.specify/workflow.yml'}
    own_feature = Path(feature).parts[1] if Path(feature).parts[:1] == ('specs',) and len(Path(feature).parts) > 1 else None
    cross_feature = set()
    for stage, receipt in state.get('receipts', {}).items():
        if stage == 'pr':
            continue
        for key in ('fingerprints', 'source_fingerprints'):
            for p, value in receipt.get(key, {}).items():
                if value is None:
                    continue
                paths.add(p)
                parts = Path(p).parts
                if own_feature and len(parts) > 1 and parts[0] == 'specs' and parts[1] != own_feature:
                    cross_feature.add(p)
    tracked = set(git(root, 'ls-files', '--cached', '-z').split('\0'))
    unstaged = set(git(root, 'diff', '--name-only', '-z').split('\0'))
    missing = sorted(paths - tracked)
    modified = sorted(paths & unstaged)
    if missing or modified:
        # `git ls-files --others --ignored` never fails (unlike `git check-ignore`,
        # whose exit code doubles as "nothing matched"), so it is safe with `git()`.
        ignored = set(git(root, 'ls-files', '--others', '--ignored', '--exclude-standard', '-z').split('\0'))
        recipes = ['git add -f ' + p for p in sorted(ignored & set(missing))]
        detail = {'not_in_index': missing, 'unstaged': modified}
        if recipes:
            detail['ignored_by_git'] = sorted(ignored & set(missing))
            detail['recipe'] = recipes
        require(False, 'EVIDENCE_NOT_PORTABLE: ' + json.dumps(detail))
    warnings = []
    if cross_feature:
        warnings.append('CROSS_FEATURE_EVIDENCE: receipt references path(s) under another feature\'s specs/ '
                         'directory: ' + ', '.join(sorted(cross_feature)))
    return {'feature': feature, 'indexed_paths': len(paths), 'warnings': warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--feature', action='append', default=[])
    parser.add_argument('--base-ref', required=True)
    parser.add_argument('--pr-number', default=os.environ.get('PR_NUMBER'),
                        help='PR number for an exact authorized rule waiver, when applicable')
    parser.add_argument('--check-index', action='store_true',
                        help='Require receipt dependencies in the Git index before publication')
    parser.add_argument('--verify-ci-evidence', action='store_true',
                        help='Accepted for compatibility; the gate always re-reads through the GitHub REST API '
                             'every CI run a Verify receipt is accepted through')
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
            index_warnings = []
            while True:
                try:
                    if args.check_index and effective['portability']:
                        index_warnings = check_index(root, feature)['warnings']
                    result = check(root, feature, policy, args.base_ref, effective)
                    result['waivers'] = applied_waivers
                    if index_warnings:
                        result['index_warnings'] = index_warnings
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
