"""Exact-input local verification manifests and affected-check selection.

A plan is {schema_version: 1, checks: [{id, sources, fixtures, command,
environment, evidence, inputs?}]}. `inputs` follows shared check_inputs.py's
complete version-1 declaration; without it, all project inputs share freshness.
Paths are repository-relative files; environment is
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
import uuid
from pathlib import Path, PurePosixPath

try:
    import check_inputs
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'shared'))
    import check_inputs


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
        require(isinstance(check, dict) and set(check) - {'inputs'} ==
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


def identity(root, check, outputs=()):
    try:
        check_inputs.command_input(root, check['command'])
        environment = check_inputs.environment_identity(root, check['command'], check['environment'])
        manifest = (check_inputs.manifest_identity(root, check, check['command'], check['inputs'])
                    if 'inputs' in check else None)
    except check_inputs.InputIdentityError as exc:
        raise VerificationPlanError(str(exc)) from exc
    result = {'definition': digest(check), 'sources': {p: file_hash(root, p) for p in check['sources']},
            'fixtures': {p: file_hash(root, p) for p in check['fixtures']},
            'command': check['command'], 'environment': environment}
    if manifest is not None:
        result['inputs'] = manifest
    else:
        paths = [check['evidence'], *outputs]
        try:
            result['legacy_global'] = check_inputs.global_identity(root, paths +
                [(PurePosixPath(p).parent / 'attempts').as_posix() for p in paths])
        except check_inputs.InputIdentityError as exc:
            raise VerificationPlanError(str(exc)) from exc
    return result


def passing_record(root, check, expected, retained=None):
    path = check['evidence']
    try:
        record = json.loads(file_path(root, path).read_text(encoding='utf-8'))
        if 'attempt' in record:
            proof = record['attempt']
            require(isinstance(proof, dict) and set(proof) == {'path', 'sha256'}, 'VERIFICATION_ATTEMPT_INVALID')
            require(file_hash(root, proof['path']) == proof['sha256'], 'VERIFICATION_ATTEMPT_TAMPERED')
            immutable = json.loads(file_path(root, proof['path']).read_text(encoding='utf-8'))
            require({k: v for k, v in record.items() if k != 'attempt'} == immutable,
                    'VERIFICATION_ATTEMPT_POINTER_TAMPERED')
            require(immutable.get('identity') != expected or immutable.get('outcome') == 'passed',
                    'VERIFICATION_LATEST_ATTEMPT_FAILED')
            if retained:
                require(file_hash(root, retained['path']) == retained['sha256'], 'VERIFICATION_ATTEMPT_TAMPERED')
                proof = retained
                immutable = json.loads(file_path(root, proof['path']).read_text(encoding='utf-8'))
            record, path = immutable, proof['path']
            output = record.get('output_proof', {})
            require(file_hash(root, output['path']) == output['sha256'], 'VERIFICATION_OUTPUT_TAMPERED')
    except (OSError, ValueError, KeyError, TypeError) as exc:
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
        expected = identity(root, check, [c['evidence'] for c in value['checks']])
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
            expected = identity(root, check, [c['evidence'] for c in value['checks']])
            evidence = passing_record(root, check, expected, saved.get(name, {}).get('evidence'))
            require(same_plan and saved.get(name) == {'identity': expected, 'evidence': evidence},
                    'VERIFICATION_SNAPSHOT_CHANGED: ' + name)
        except (VerificationPlanError, OSError) as exc:
            affected.append(name)
            reasons[name] = str(exc)
        else:
            reusable.append(name)
    return {'affected': affected, 'reusable': reusable, 'reasons': reasons,
            'statuses': {c['id']: ('reused' if c['id'] in reusable else
                         'unknown' if 'INPUT_' in reasons.get(c['id'], '') else 'invalidated') for c in value['checks']},
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
        if selected is None or check['id'] in selected:
            try:
                check_inputs.command_input(root, check['command'])
            except check_inputs.InputIdentityError as exc:
                raise VerificationPlanError(str(exc)) from exc
    for check in value['checks']:
        if selected is not None and check['id'] not in selected:
            continue
        before = identity(root, check, [c['evidence'] for c in value['checks']])
        argv = [before['environment']['executable']['invocation'], *check['command'][1:]]
        path = file_path(root, check['evidence'])
        attempt_dir = path.parent / 'attempts' / digest(check['id'])[:16] / uuid.uuid4().hex
        attempt_dir.mkdir(parents=True, exist_ok=False)
        try:
            with check_inputs.utf8_environment():
                measured = dispatch.run_capped(argv, Path(root), timeout)
        except OSError as exc:
            measured = {'exit_code': None, 'timed_out': False, 'output': str(exc), 'truncated': False}
        try:
            stable = before == identity(root, check, [c['evidence'] for c in value['checks']]) and plan_hash == file_hash(root, plan)
        except (VerificationPlanError, OSError):
            stable = False
        passed = measured['exit_code'] == 0 and not measured['timed_out'] and stable
        record = {'schema_version': 1, 'check': check['id'], 'identity': before,
                  'outcome': 'passed' if passed else 'failed', 'source': 'local', 'ci_grade': False,
                  'exit_code': measured['exit_code'], 'timed_out': measured['timed_out'],
                  'inputs_unchanged': stable, 'output': measured['output'],
                  'truncated': measured['truncated']}
        output_path = attempt_dir / 'output.txt'
        output_path.write_bytes(measured['output'].encode('utf-8'))
        record.update(status='executed', attempt_id=attempt_dir.name,
                      output_proof={'path': output_path.relative_to(Path(root).resolve()).as_posix(),
                                    'sha256': check_inputs.file_digest(output_path)})
        immutable_path = attempt_dir / 'receipt.json'
        with immutable_path.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        path.parent.mkdir(parents=True, exist_ok=True)
        dispatch.save(path, {**record, 'attempt': {'path': immutable_path.relative_to(Path(root).resolve()).as_posix(),
                                                'sha256': check_inputs.file_digest(immutable_path)}})
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
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
