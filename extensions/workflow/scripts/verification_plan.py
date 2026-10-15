"""Exact-input local verification manifests and affected-check selection.

A plan is {schema_version: 1, checks: [{id, sources, fixtures, command,
environment, evidence}]}. Paths are repository-relative files; environment is
an explicit list of variable names. Each evidence path is a runner-written
JSON record. Local records are not CI certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
from pathlib import Path, PurePosixPath


class VerificationPlanError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationPlanError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file_path(root, label):
    require(isinstance(label, str) and label and '\\' not in label and
            not Path(label).is_absolute() and ':' not in label and
            '..' not in label.split('/') and PurePosixPath(label).as_posix() == label,
            'VERIFICATION_PATH_INVALID: ' + str(label))
    root = Path(root).resolve()
    path = (root / label).resolve()
    require(path.is_relative_to(root), 'VERIFICATION_PATH_OUTSIDE_ROOT: ' + label)
    return path


def file_hash(root, label):
    path = file_path(root, label)
    require(path.is_file(), 'VERIFICATION_FILE_MISSING: ' + label)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_plan(root, label):
    try:
        value = json.loads(file_path(root, label).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise VerificationPlanError('VERIFICATION_PLAN_UNREADABLE: ' + str(exc)) from exc
    require(isinstance(value, dict) and set(value) == {'schema_version', 'checks'} and
            type(value['schema_version']) is int and value['schema_version'] == 1 and
            isinstance(value['checks'], list) and value['checks'],
            'VERIFICATION_PLAN_INVALID')
    ids, outputs = set(), set()
    for check in value['checks']:
        require(isinstance(check, dict) and set(check) ==
                {'id', 'sources', 'fixtures', 'command', 'environment', 'evidence'},
                'VERIFICATION_CHECK_INVALID')
        require(isinstance(check['id'], str) and check['id'].strip() and check['id'] not in ids,
                'VERIFICATION_CHECK_ID_INVALID')
        ids.add(check['id'])
        for key in ('sources', 'fixtures', 'command', 'environment'):
            items = check[key]
            require(isinstance(items, list) and all(isinstance(v, str) and v.strip() for v in items),
                    'VERIFICATION_CHECK_INVALID: ' + key)
            if key != 'command':
                require(len(set(items)) == len(items), 'VERIFICATION_CHECK_DUPLICATE: ' + key)
        require(check['sources'] and check['command'], 'VERIFICATION_CHECK_INPUTS_REQUIRED')
        for path in check['sources'] + check['fixtures'] + [check['evidence']]:
            file_path(root, path)
        require(check['evidence'] not in outputs and check['evidence'] != label,
                'VERIFICATION_EVIDENCE_COLLISION')
        outputs.add(check['evidence'])
    inputs = {p for c in value['checks'] for p in c['sources'] + c['fixtures']}
    require(not inputs & outputs, 'VERIFICATION_EVIDENCE_IS_INPUT')
    return value


def identity(root, check):
    command = check['command'][0]
    local = Path(root) / command
    # The selected invocation path is kept as-is (a venv python is often a
    # symlink whose location drives interpreter discovery); the resolved
    # target and its bytes are bound separately.
    selected = os.path.abspath(local) if local.is_file() else shutil.which(command)
    require(selected and Path(selected).is_file(), 'VERIFICATION_EXECUTABLE_MISSING: ' + command)
    selected = os.path.abspath(selected)
    target = Path(selected).resolve()
    executable = {'invocation': selected, 'path': str(target),
                  'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    return {'definition': digest(check), 'sources': {p: file_hash(root, p) for p in check['sources']},
            'fixtures': {p: file_hash(root, p) for p in check['fixtures']},
            'command': check['command'],
            'environment': {'python': sys.version, 'platform': platform.platform(),
                            'cwd': str(Path(root).resolve()), 'executable': executable,
                            'variables': {name: os.environ.get(name)
                                          for name in sorted(set(check['environment']) | {'PATH'})}}}


def passing_record(root, check, expected):
    path = check['evidence']
    try:
        record = json.loads(file_path(root, path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise VerificationPlanError('VERIFICATION_EVIDENCE_UNREADABLE: ' + path) from exc
    require(isinstance(record, dict) and record.get('schema_version') == 1 and
            record.get('check') == check['id'] and record.get('identity') == expected and
            record.get('outcome') == 'passed' and type(record.get('exit_code')) is int and
            record['exit_code'] == 0 and record.get('timed_out') is False and
            record.get('inputs_unchanged') is True and
            record.get('source') == 'local' and record.get('ci_grade') is False,
            'VERIFICATION_PASSING_EVIDENCE_REQUIRED: ' + check['id'])
    return {'path': path, 'sha256': file_hash(root, path)}


def snapshot(root, plan):
    value = read_plan(root, plan)
    checks = {}
    for check in value['checks']:
        expected = identity(root, check)
        checks[check['id']] = {'identity': expected, 'evidence': passing_record(root, check, expected)}
    return {'schema_version': 1, 'plan': plan, 'plan_sha256': file_hash(root, plan), 'checks': checks}


def affected_checks(root, plan, prior=None):
    """A saved receipt is authoritative for reuse, including exact evidence bytes."""
    value = read_plan(root, plan)
    saved = (prior or {}).get('checks', {}) if isinstance(prior, dict) else {}
    same_plan = isinstance(prior, dict) and prior.get('schema_version') == 1 and prior.get('plan') == plan
    affected, reusable, reasons = [], [], {}
    for check in value['checks']:
        name = check['id']
        try:
            expected = identity(root, check)
            evidence = passing_record(root, check, expected)
            require(same_plan and saved.get(name) == {'identity': expected, 'evidence': evidence},
                    'VERIFICATION_SNAPSHOT_CHANGED: ' + name)
        except (VerificationPlanError, OSError) as exc:
            affected.append(name)
            reasons[name] = str(exc)
        else:
            reusable.append(name)
    return {'affected': affected, 'reusable': reusable, 'reasons': reasons,
            'removed': sorted(set(saved) - {c['id'] for c in value['checks']})}


def current(root, plan, prior):
    try:
        selected = affected_checks(root, plan, prior)
        unchanged = isinstance(prior, dict) and prior.get('plan_sha256') == file_hash(root, plan)
        return {'current': not selected['affected'] and unchanged and not selected['removed'],
                **selected}
    except (VerificationPlanError, OSError) as exc:
        return {'current': False, 'error': str(exc)}


def run_checks(root, plan, selected=None, timeout=1800):
    """Run exact argv with bounded output/process lifetime using the existing API."""
    import delegate_dispatch as dispatch
    value = read_plan(root, plan)
    require(type(timeout) is int and 0 < timeout <= 28800, 'VERIFICATION_TIMEOUT_INVALID')
    names = {c['id'] for c in value['checks']}
    require(selected is None or bool(selected) and set(selected) <= names,
            'VERIFICATION_SELECTION_INVALID')
    results = {}
    plan_hash = file_hash(root, plan)
    for check in value['checks']:
        if selected is not None and check['id'] not in selected:
            continue
        before = identity(root, check)
        argv = [before['environment']['executable']['invocation'], *check['command'][1:]]
        measured = dispatch.run_capped(argv, Path(root), timeout)
        stable = before == identity(root, check) and plan_hash == file_hash(root, plan)
        passed = measured['exit_code'] == 0 and not measured['timed_out'] and stable
        record = {'schema_version': 1, 'check': check['id'], 'identity': before,
                  'outcome': 'passed' if passed else 'failed', 'source': 'local', 'ci_grade': False,
                  'exit_code': measured['exit_code'], 'timed_out': measured['timed_out'],
                  'inputs_unchanged': stable, 'output': measured['output'],
                  'truncated': measured['truncated']}
        path = file_path(root, check['evidence'])
        path.parent.mkdir(parents=True, exist_ok=True)
        dispatch.save(path, record)
        results[check['id']] = record['outcome']
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--plan', required=True)
    parser.add_argument('--check', action='append')
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--prior', type=Path)
    parser.add_argument('action', choices=('run', 'select', 'snapshot'))
    args = parser.parse_args(argv)
    try:
        if args.action == 'run':
            result = run_checks(args.root, args.plan, args.check, args.timeout)
            ok = all(v == 'passed' for v in result.values())
        elif args.action == 'snapshot':
            result, ok = snapshot(args.root, args.plan), True
        else:
            prior = json.loads(args.prior.read_text(encoding='utf-8')) if args.prior else None
            if isinstance(prior, dict) and 'verification_snapshot' in prior:
                prior = prior['verification_snapshot']
            result, ok = affected_checks(args.root, args.plan, prior), True
        print(json.dumps(result, indent=2))
        return 0 if ok else 1
    except (VerificationPlanError, OSError, ValueError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
