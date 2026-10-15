#!/usr/bin/env python3
"""Lean-execution helpers: aggregate preflight (P03), PR closing-reference lint (P08) and
run progress reporting (P12).

Every subcommand takes explicit inputs and prints one JSON object (exit 0 ok, 1 findings,
2 malformed input). Nothing launches an app or a browser, calls GitHub, or reads a raw log
or prompt.

  preflight       Check a project-owned manifest (declared encoding/newlines, source/base/
                  artifact identities including stale fixture binaries, executables and
                  arguments, browser paths, strict runtime-status).
  scope-command   Print the exact Scope gate/bind command for an initial or revalidation call.
  pr-lint         Reject PR closing keywords that name anything but the bound issue.
  progress        Summarise normalized delegate-task result files from explicit roots. With the optional
                  Progress extension installed the runs come from its `runs --json` (progress.runs.v1).

Public JSON contracts: PREFLIGHT_SCHEMA, PR_LINT_SCHEMA, PROGRESS_SCHEMA (see `contracts`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PREFLIGHT_SCHEMA = 'sanduq.execution.preflight.v1'
PR_LINT_SCHEMA = 'sanduq.execution.pr-lint.v1'
PROGRESS_SCHEMA = 'sanduq.execution.progress.v1'
SCOPE_COMMAND_SCHEMA = 'sanduq.execution.scope-command.v1'
SCOPE_SCRIPT = 'python .specify/extensions/scope/scripts/scope.py'

NEWLINES = ('lf', 'crlf')
IDENTITY_KINDS = ('source', 'base', 'artifact', 'fixture')
RUNTIME_STATES = ('running', 'stopped')
RUNTIME_KEYS = {'owner', 'state', 'pid'}


class InputError(Exception):
    """Malformed manifest, option or input file (exit 2)."""


def contracts():
    return {
        'preflight': {'schema': PREFLIGHT_SCHEMA,
                      'output': {'ok': 'bool', 'checks': '[{id, ok, detail}]', 'failed': '[id]'},
                      'manifest': {
                          'files': '[{path, encoding: utf-8, newlines?: lf|crlf}]',
                          'identities': '[{name, kind: source|base|artifact|fixture, path, sha256?, built_from?: [path]}]',
                          'commands': '[{name, executable, args: [str], required_args?: [str], forbidden_args?: [str]}]',
                          'browsers': '[{name, path}]',
                          'runtime_status': '{path, owner, state: running|stopped}  (file keys: owner, state, pid?)'}},
        'pr-lint': {'schema': PR_LINT_SCHEMA,
                    'output': {'ok': 'bool', 'body_sha256': 'sha256 of the exact UTF-8 body linted', 'closes': '[{keyword, repo, issue}]', 'violations': '[{code, repo, issue}]'}},
        'progress': {'schema': PROGRESS_SCHEMA,
                     'output': {'runs': '[run]', 'harness_totals': '{harness: totals}', 'duplicates': '[run_id]',
                                'malformed': '[{path, error}]', 'next_action': 'str'}},
    }


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- preflight

def _resolve(base, value, where):
    if not isinstance(value, str) or not value:
        raise InputError(f'{where}: path must be a non-empty string')
    path = Path(value)
    return path if path.is_absolute() else base / path


def _entries(manifest, key, required=()):
    items = manifest.get(key, [])
    if not isinstance(items, list):
        raise InputError(f'{key} must be a list')
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise InputError(f'{key}[{index}] must be an object')
        for field in required:
            if field not in item:
                raise InputError(f'{key}[{index}] missing "{field}"')
    return items


def check_file(base, item):
    cid = 'file:' + str(item['path'])
    path = _resolve(base, item['path'], cid)
    if item.get('encoding', 'utf-8').lower() not in ('utf-8', 'utf8'):
        raise InputError(f'{cid}: only utf-8 may be declared')
    newlines = item.get('newlines')
    if newlines is not None and newlines not in NEWLINES:
        raise InputError(f'{cid}: newlines must be one of {NEWLINES}')
    if not path.is_file():
        return {'id': cid, 'ok': False, 'detail': 'missing'}
    data = path.read_bytes()
    try:
        data.decode('utf-8')
    except UnicodeDecodeError as exc:
        return {'id': cid, 'ok': False, 'detail': f'not valid UTF-8 at byte {exc.start}'}
    if data.startswith(b'\xef\xbb\xbf'):
        return {'id': cid, 'ok': False, 'detail': 'UTF-8 BOM present'}
    if newlines:
        crlf = data.count(b'\r\n')
        bare_lf = data.count(b'\n') - crlf
        bare_cr = data.count(b'\r') - crlf
        bad = (bare_lf + bare_cr) if newlines == 'crlf' else (crlf + bare_cr)
        if bad:
            return {'id': cid, 'ok': False, 'detail': f'{bad} line ending(s) are not {newlines.upper()}'}
    return {'id': cid, 'ok': True, 'detail': 'ok'}


def check_identity(base, item):
    cid = 'identity:' + str(item['name'])
    if item.get('kind') not in IDENTITY_KINDS:
        raise InputError(f'{cid}: kind must be one of {IDENTITY_KINDS}')
    path = _resolve(base, item['path'], cid)
    if not path.is_file():
        return {'id': cid, 'ok': False, 'detail': 'missing'}
    expected = item.get('sha256')
    if expected is not None:
        if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
            raise InputError(f'{cid}: sha256 must be 64 lowercase hex characters')
        actual = sha256_file(path)
        if actual != expected:
            return {'id': cid, 'ok': False, 'detail': f'sha256 mismatch: expected {expected[:12]}, found {actual[:12]}'}
    sources = item.get('built_from', [])
    if not isinstance(sources, list):
        raise InputError(f'{cid}: built_from must be a list')
    for source in sources:
        spath = _resolve(base, source, cid)
        if not spath.is_file():
            return {'id': cid, 'ok': False, 'detail': f'built_from source missing: {source}'}
        if spath.stat().st_mtime_ns > path.stat().st_mtime_ns:
            return {'id': cid, 'ok': False, 'detail': f'stale: {source} is newer than {item["path"]}'}
    if expected is None and not sources:
        raise InputError(f'{cid}: declare sha256 or built_from; an identity without either proves nothing')
    return {'id': cid, 'ok': True, 'detail': 'ok'}


def check_command(item):
    cid = 'command:' + str(item['name'])
    args = item.get('args', [])
    for field in ('args', 'required_args', 'forbidden_args'):
        value = item.get(field, [])
        if not isinstance(value, list) or not all(isinstance(a, str) for a in value):
            raise InputError(f'{cid}: {field} must be a list of strings')
    executable = item['executable']
    if not isinstance(executable, str) or not executable:
        raise InputError(f'{cid}: executable must be a non-empty string')
    problems = []
    if not (shutil.which(executable) or Path(executable).is_file()):
        problems.append(f'executable not found: {executable}')
    problems += [f'empty argument at position {i}' for i, a in enumerate(args) if not a.strip()]
    problems += [f'missing required argument {a}' for a in item.get('required_args', []) if a not in args]
    problems += [f'forbidden argument {a}' for a in item.get('forbidden_args', []) if a in args]
    return {'id': cid, 'ok': not problems, 'detail': '; '.join(problems) or 'ok'}


def check_browser(base, item):
    cid = 'browser:' + str(item['name'])
    path = _resolve(base, item['path'], cid)
    return {'id': cid, 'ok': path.is_file(), 'detail': 'ok' if path.is_file() else f'missing: {item["path"]}'}


def check_runtime_status(base, spec):
    cid = 'runtime_status'
    if not isinstance(spec, dict) or not all(k in spec for k in ('path', 'owner', 'state')):
        raise InputError('runtime_status needs path, owner and state')
    if spec['state'] not in RUNTIME_STATES:
        raise InputError(f'runtime_status.state must be one of {RUNTIME_STATES}')
    path = _resolve(base, spec['path'], cid)
    if not path.is_file():
        return {'id': cid, 'ok': False, 'detail': 'supplied status file missing'}
    try:
        status = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeDecodeError) as exc:
        return {'id': cid, 'ok': False, 'detail': f'status is not valid JSON: {exc}'}
    if not isinstance(status, dict):
        return {'id': cid, 'ok': False, 'detail': 'status must be a JSON object'}
    problems = []
    unknown = sorted(set(status) - RUNTIME_KEYS)
    if unknown:
        problems.append('unknown keys: ' + ', '.join(unknown))
    if not isinstance(status.get('owner'), str) or not status.get('owner'):
        problems.append('owner must be a non-empty string')
    if status.get('state') not in RUNTIME_STATES:
        problems.append(f'state must be one of {RUNTIME_STATES}')
    pid = status.get('pid')
    if 'pid' in status and (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0):
        problems.append('pid must be a positive integer')
    if status.get('state') == 'running' and 'pid' not in status:
        problems.append('running status requires pid')
    if not problems:
        if status['owner'] != spec['owner']:
            problems.append(f'owner is {status["owner"]!r}, expected {spec["owner"]!r}')
        if status['state'] != spec['state']:
            problems.append(f'state is {status["state"]!r}, expected {spec["state"]!r}')
    return {'id': cid, 'ok': not problems, 'detail': '; '.join(problems) or 'ok'}


def preflight(manifest_path):
    manifest_path = Path(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise InputError(f'cannot read manifest: {exc}') from exc
    if not isinstance(manifest, dict):
        raise InputError('manifest must be a JSON object')
    unknown = sorted(set(manifest) - {'files', 'identities', 'commands', 'browsers', 'runtime_status'})
    if unknown:
        raise InputError('unknown manifest keys: ' + ', '.join(unknown))
    base = manifest_path.resolve().parent
    checks = [check_file(base, i) for i in _entries(manifest, 'files', ('path',))]
    checks += [check_identity(base, i) for i in _entries(manifest, 'identities', ('name', 'kind', 'path'))]
    checks += [check_command(i) for i in _entries(manifest, 'commands', ('name', 'executable'))]
    checks += [check_browser(base, i) for i in _entries(manifest, 'browsers', ('name', 'path'))]
    if 'runtime_status' in manifest:
        checks.append(check_runtime_status(base, manifest['runtime_status']))
    if not checks:
        raise InputError('manifest declares no checks')
    failed = [c['id'] for c in checks if not c['ok']]
    return {'schema': PREFLIGHT_SCHEMA, 'ok': not failed, 'checks': checks, 'failed': failed}


# ------------------------------------------------------------------------ scope command

def scope_command(mode, command, issue, feature=None, token=None, session=None, analysis=None):
    """The exact `scope.py` invocation, checked against its parser and Scope.gate/bind.

    `initial` is the fresh managed claim: feature, token, session and the analysis file are all
    required (a partial set raises SCOPE_WORKFLOW_BINDING_REQUIRED, and gate/bind need the analysis
    for the fresh path). `revalidate` takes no claim flags at all: Scope recognises the existing
    claim itself from `.specify/feature.json` and the bound checkpoint, and any of --feature/
    --token/--session would force the fresh-claim path instead."""
    if command not in ('gate', 'bind'):
        raise InputError('command must be gate or bind')
    if mode not in ('initial', 'revalidate'):
        raise InputError('mode must be initial or revalidate')
    if not re.fullmatch(r'[1-9]\d*', str(issue)):
        raise InputError('issue must be one explicit positive integer')
    argv = [SCOPE_SCRIPT, command, str(issue)]
    if mode == 'initial':
        if not all((feature, token, session, analysis)):
            raise InputError('initial requires --feature, --token, --session and --analysis')
        for flag, value in (('--feature', feature), ('--token', token), ('--session', session),
                            ('--analysis', analysis)):
            argv += [flag, shlex.quote(value)]
    elif any((feature, token, session, analysis)):
        raise InputError('revalidate takes no --feature, --token, --session or --analysis')
    if command == 'bind':
        argv.append('--apply')
    return {'schema': SCOPE_COMMAND_SCHEMA, 'mode': mode, 'command': ' '.join(argv)}


# ----------------------------------------------------------------------------- pr lint

CLOSE_REF = re.compile(
    r'\b(?P<kw>close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s+'
    r'(?:https?://github\.com/(?P<urepo>[\w.-]+/[\w.-]+)/issues/(?P<unum>\d+)|(?P<repo>[\w.-]+/[\w.-]+)?#(?P<num>\d+))',
    re.I)
FENCE = re.compile(r'```.*?```|~~~.*?~~~|`[^`\n]*`', re.S)


def pr_lint(body, repo, issue, prerequisites=()):
    repo_key = repo.lower()
    prereqs = {int(p) for p in prerequisites}
    text = FENCE.sub('', body)
    closes, violations = [], []
    for match in CLOSE_REF.finditer(text):
        ref_repo = (match.group('urepo') or match.group('repo') or repo).lower()
        number = int(match.group('unum') or match.group('num'))
        closes.append({'keyword': match.group('kw').lower(), 'repo': ref_repo, 'issue': number})
        if ref_repo != repo_key:
            code = 'FOREIGN_REPO_CLOSE'
        elif number in prereqs:
            code = 'PREREQUISITE_CLOSE'
        elif number != int(issue):
            code = 'UNBOUND_ISSUE_CLOSE'
        else:
            continue
        violations.append({'code': code, 'repo': ref_repo, 'issue': number})
    return {'schema': PR_LINT_SCHEMA, 'ok': not violations,
            'body_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(), 'bound': {'repo': repo_key, 'issue': int(issue)},
            'closes': closes, 'violations': violations}


# ------------------------------------------------------------------------------ progress

RESULT_NAMES = ('result.json',)
USAGE_FIELDS = ('input_total', 'input_fresh', 'cache_read', 'cache_write', 'output_total', 'reasoning', 'total')
TERMINAL_STATUSES = ('successful', 'failed', 'abandoned')
JOURNAL_STATE = re.compile(r'[a-z][a-z_]{0,31}')
JOURNAL_TAIL_BYTES = 65536
DEFAULT_STALL_SECONDS = 300
CONFLICT_FIELDS = ('harness', 'harness_status', 'started_at', 'ended_at', 'usage')


def parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def discover(roots):
    """Run directories: any directory holding result.json (or *.result.json), or a meta.json
    with no result beside it (a live run; the real driver writes result.json only at the end)."""
    found = {}
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            raise InputError(f'root is not a directory: {root}')
        for path in sorted(p for p in root.rglob('*') if p.is_file()):
            if path.name in RESULT_NAMES or path.name.endswith('.result.json'):
                found[path] = ('result', path)
            elif path.name == 'meta.json' and not (path.parent / 'result.json').is_file():
                found[path] = ('live', path)
    return list(found.values())


def usage_of(data):
    """Measured counters only. `fidelity` other than "exact" (e.g. "unavailable") means the
    harness reported nothing, so its zero placeholders are unknown, never measured zeros."""
    tokens = data.get('tokens')
    if not isinstance(tokens, dict) or tokens.get('fidelity') != 'exact':
        return None
    usage = {}
    for field in USAGE_FIELDS:
        value = tokens.get(field)
        usage[field] = value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    return usage if usage['total'] is not None else None


def journal_projection(directory):
    """Bounded, safe journal projection: only each event's `t` and a lowercase `state` word are
    read, from the last JOURNAL_TAIL_BYTES. No other key, prompt, stdout or stderr is consulted."""
    path = directory / 'journal.jsonl'
    if not path.is_file():
        return {'events': 0, 'state': None, 'last_event_at': None, 'terminal': False}
    with open(path, 'rb') as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - JOURNAL_TAIL_BYTES))
        tail = stream.read().decode('utf-8', 'replace').splitlines()
    if size > JOURNAL_TAIL_BYTES:
        tail = tail[1:]
    events = []
    for line in tail:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        state, when = (item.get('state'), item.get('t')) if isinstance(item, dict) else (None, None)
        if isinstance(state, str) and JOURNAL_STATE.fullmatch(state) and parse_time(when):
            events.append((state, when))
    last = events[-1] if events else (None, None)
    return {'events': len(events), 'state': last[0], 'last_event_at': last[1],
            'terminal': any(state == 'terminal' for state, _ in events)}


def elapsed_between(started, ended):
    return max(0, int((ended - started).total_seconds())) if started and ended else None


def project_run(kind, path, now, stall_seconds=DEFAULT_STALL_SECONDS):
    """Compact projection of one run; every unmeasured value stays None."""
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('run_id'), str) or not data['run_id']:
        raise ValueError('needs a non-empty string run_id')
    started, ended = parse_time(data.get('started_at')), parse_time(data.get('ended_at'))
    if kind == 'live':
        journal = journal_projection(path.parent)
        last = parse_time(journal['last_event_at'])
        if journal['terminal']:
            phase, status = 'finishing', 'finalizing'
        elif last and (now - last).total_seconds() > stall_seconds:
            phase, status = 'stalled', 'stalled'
        else:
            phase, status = 'active', 'running'
        elapsed = elapsed_between(started, now)
        latest = journal['state']
        next_action = {'finishing': 'wait for the driver to write result.json',
                       'stalled': 'check the supervisor, then collect or cancel the run',
                       'active': 'wait; no action needed'}[phase]
        return {'run_id': data['run_id'], 'harness': data.get('harness') or 'unknown', 'harness_status': status,
                'phase': phase, 'task_verdict': 'unknown', 'review_verdict': 'unknown', 'usage': None,
                'elapsed_seconds': elapsed, 'journal_events': journal['events'], 'latest_event': latest,
                'latest_event_at': journal['last_event_at'], 'next_action': next_action,
                'started_at': data.get('started_at'), 'ended_at': None, 'source': str(path)}
    elapsed = elapsed_between(started, ended)
    if elapsed is None and isinstance(data.get('duration_ms'), int) and not isinstance(data['duration_ms'], bool):
        elapsed = data['duration_ms'] // 1000
    return {'run_id': data['run_id'], 'harness': data.get('harness') or 'unknown',
            'harness_status': data.get('status') or 'unknown', 'phase': 'done',
            'task_verdict': data.get('task_verdict') or 'unknown',
            'review_verdict': data.get('review_verdict') or 'unknown', 'usage': usage_of(data),
            'elapsed_seconds': elapsed, 'journal_events': None, 'latest_event': data.get('latest_event'),
            'latest_event_at': data.get('ended_at'), 'next_action': data.get('next_action'),
            'started_at': data.get('started_at'), 'ended_at': data.get('ended_at'), 'source': str(path)}


def conflicts(first, second):
    """Fields on which two records of one run_id disagree. A live record yields to a final one
    for the same harness and start; otherwise any disagreement is a real conflict."""
    if first['phase'] != 'done' and second['phase'] == 'done' or first['phase'] == 'done' != second['phase']:
        return [f for f in ('harness', 'started_at') if first[f] != second[f]]
    return [f for f in CONFLICT_FIELDS if first['usage' if f == 'usage' else f] != second['usage' if f == 'usage' else f]]


LIVE_NEXT_ACTION = {'finishing': 'wait for the driver to write result.json',
                    'stalled': 'check the supervisor, then collect or cancel the run',
                    'active': 'wait; no action needed'}


def runs_dirs(roots):
    """Roots that Progress can read directly (a runs folder, or a worktree holding .delegate/runs); else None."""
    found = []
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            raise InputError(f'root is not a directory: {root}')
        nested = root / '.delegate' / 'runs'
        direct = any((child / name).is_file() for child in root.iterdir() if child.is_dir() for name in RESULT_NAMES + ('meta.json',))
        if direct:
            found.append(str(root))
        elif nested.is_dir():
            found.append(str(nested))
        else:
            return None
    return found


def progress_from_cli(roots, now, stall_seconds):
    """Normalized runs from the optional Progress extension's `runs --json` (schema progress.runs.v1), or None
    when Progress is absent or a root is not a plain runs folder. The same totals and caveats are rendered."""
    import progress_bridge
    root = progress_bridge.find_root(roots[0])
    if progress_bridge.script(root) is None:
        return None
    folders = runs_dirs(roots)
    if not folders:
        return None
    data = progress_bridge.runs(root, folders, now.isoformat(), stall_seconds)
    if data is None:
        return None
    runs = {}
    for item in data.get('runs') or []:
        run = {**item, 'next_action': item.get('next_action') or LIVE_NEXT_ACTION.get(item.get('phase'))}
        run.setdefault('task_verdict', 'unknown')
        run.setdefault('review_verdict', 'unknown')
        runs[run['run_id']] = run
    conflicting = {run_id: set(run['conflict']) for run_id, run in runs.items() if run.get('conflict')}
    malformed = [{'path': m.get('source'), 'error': m.get('error')} for m in data.get('malformed') or []]
    report = summarize(runs, list(data.get('duplicates') or []), conflicting, malformed, now)
    report['via'] = data['schema']
    return report


def progress(roots, now=None, stall_seconds=DEFAULT_STALL_SECONDS):
    now = now or datetime.now(timezone.utc)
    if roots:
        via_progress = progress_from_cli(roots, now, stall_seconds)
        if via_progress is not None:
            return via_progress
    runs, duplicates, conflicting, malformed = {}, [], {}, []
    for kind, path in discover(roots):
        try:
            run = project_run(kind, path, now, stall_seconds)
        except (OSError, ValueError) as exc:
            malformed.append({'path': str(path), 'error': str(exc)})
            continue
        known = runs.get(run['run_id'])
        if known:
            duplicates.append(run['run_id'])
            diff = conflicts(known, run)
            if diff:
                conflicting.setdefault(run['run_id'], set()).update(diff)
            if run['phase'] != 'done':
                continue
        runs[run['run_id']] = run
    for run_id in conflicting:
        runs[run_id]['conflict'] = sorted(conflicting[run_id])
    return summarize(runs, duplicates, conflicting, malformed, now)


def summarize(runs, duplicates, conflicting, malformed, now):
    """Per-harness totals and the next action. Caveats kept: elapsed is wall time and not active work, a stalled
    phase is a heuristic, and a terminal harness status is not acceptance (the ledger decides that)."""
    ordered = sorted(runs.values(), key=lambda r: (r['harness'], r['run_id']))
    totals = {}
    for run in ordered:
        bucket = totals.setdefault(run['harness'], {
            'runs': 0, 'by_harness_status': {}, 'measured_usage_runs': 0, 'unknown_usage_runs': 0,
            'usage': {field: 0 for field in USAGE_FIELDS}, 'elapsed_seconds_known': 0})
        bucket['runs'] += 1
        bucket['by_harness_status'][run['harness_status']] = bucket['by_harness_status'].get(run['harness_status'], 0) + 1
        if run['usage'] is None:
            bucket['unknown_usage_runs'] += 1
        else:
            bucket['measured_usage_runs'] += 1
            for field in USAGE_FIELDS:
                bucket['usage'][field] += run['usage'][field] or 0
        bucket['elapsed_seconds_known'] += run['elapsed_seconds'] or 0
    live = [r for r in ordered if r['phase'] != 'done']
    latest = max(ordered, key=lambda r: parse_time(r['latest_event_at']) or datetime.min.replace(tzinfo=timezone.utc),
                 default=None)
    pick = next((r for r in live if r['phase'] == 'stalled'), live[0] if live else latest)
    if conflicting:
        next_action = 'resolve conflicting duplicate runs: ' + ', '.join(sorted(conflicting))
    elif malformed:
        next_action = 'fix or remove malformed run files'
    else:
        next_action = (pick.get('next_action') if pick else None) or ('none recorded' if pick else 'no runs found')
    return {'schema': PROGRESS_SCHEMA, 'generated_at': now.isoformat(), 'ok': not (conflicting or malformed),
            'usage_semantics': 'per-harness counters of exact usage only; input_total is harness-defined '
                               '(Claude excludes cache reads in input_fresh, Codex includes cached input), '
                               'so totals are never summed across harnesses',
            'runs': ordered, 'harness_totals': totals, 'duplicates': sorted(set(duplicates)),
            'conflicts': {k: sorted(v) for k, v in sorted(conflicting.items())}, 'malformed': malformed,
            'latest_event': latest.get('latest_event') if latest else None, 'next_action': next_action}


def progress_markdown(report):
    lines = ['# Run progress', '', f'Next action: {report["next_action"]}', '']
    if report['latest_event']:
        lines += [f'Latest event: {report["latest_event"]}', '']
    lines += ['| Run | Harness | Harness status | Task verdict | Review verdict | Total tokens | Elapsed |',
              '| --- | --- | --- | --- | --- | --- | --- |']
    for r in report['runs']:
        tokens = 'unknown' if r['usage'] is None else str(r['usage']['total'])
        elapsed = 'unknown' if r['elapsed_seconds'] is None else f'{r["elapsed_seconds"]}s'
        flag = ' (CONFLICT: ' + ', '.join(r['conflict']) + ')' if r.get('conflict') else ''
        lines.append(f'| {r["run_id"]}{flag} | {r["harness"]} | {r["harness_status"]} | {r["task_verdict"]} | '
                     f'{r["review_verdict"]} | {tokens} | {elapsed} |')
    lines += ['', '| Harness | Runs | Measured usage | Unknown usage | Fresh input | Cache read | Cache write | Output |',
              '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for name, t in sorted(report['harness_totals'].items()):
        u = t['usage']
        lines.append(f'| {name} | {t["runs"]} | {t["measured_usage_runs"]} | {t["unknown_usage_runs"]} | '
                     f'{u["input_fresh"]} | {u["cache_read"]} | {u["cache_write"]} | {u["output_total"]} |')
    if report['duplicates']:
        lines += ['', 'Duplicate run IDs seen: ' + ', '.join(report['duplicates'])]
    for m in report['malformed']:
        lines.append(f'Malformed: {m["path"]}: {m["error"]}')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------------- cli

def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('preflight', help='aggregate deterministic preflight from a manifest')
    p.add_argument('--manifest', required=True)
    p = sub.add_parser('scope-command', help='exact Scope gate/bind command')
    p.add_argument('--mode', required=True, choices=('initial', 'revalidate'))
    p.add_argument('--command', dest='scope_cmd', required=True, choices=('gate', 'bind'))
    p.add_argument('--issue', required=True)
    p.add_argument('--feature')
    p.add_argument('--token')
    p.add_argument('--session')
    p.add_argument('--analysis')
    p = sub.add_parser('pr-lint', help='reject foreign/prerequisite closing keywords')
    p.add_argument('--repo', required=True, help='bound owner/repo')
    p.add_argument('--issue', required=True, type=int, help='bound issue number')
    p.add_argument('--prerequisite', action='append', default=[], type=int)
    p.add_argument('--output', help='also write the JSON result here (for the finalize receipt)')
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--body')
    group.add_argument('--body-file', help='file path, or - for stdin')
    p = sub.add_parser('progress', help='summarise normalized results from explicit roots')
    p.add_argument('--root', action='append', required=True, help='result root or worktree (repeatable)')
    p.add_argument('--format', choices=('json', 'markdown'), default='json')
    p.add_argument('--now', help='ISO timestamp for deterministic elapsed time')
    p.add_argument('--stall-seconds', type=int, default=DEFAULT_STALL_SECONDS,
                   help='a live run with no journal event for this long is reported stalled')
    sub.add_parser('contracts', help='print the public JSON contracts')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == 'preflight':
            result = preflight(args.manifest)
        elif args.cmd == 'scope-command':
            result = scope_command(args.mode, args.scope_cmd, args.issue, args.feature, args.token,
                                   args.session, args.analysis)
        elif args.cmd == 'pr-lint':
            if not re.fullmatch(r'[\w.-]+/[\w.-]+', args.repo):
                raise InputError('--repo must be owner/repo')
            body = args.body
            if body is None:
                try:
                    body = sys.stdin.read() if args.body_file == '-' else Path(args.body_file).read_text(encoding='utf-8')
                except (OSError, UnicodeDecodeError) as exc:
                    raise InputError(f'cannot read body: {exc}') from exc
            result = pr_lint(body, args.repo, args.issue, args.prerequisite)
            if args.output:
                Path(args.output).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        elif args.cmd == 'progress':
            now = parse_time(args.now) if args.now else None
            if args.now and now is None:
                raise InputError('--now must be an ISO timestamp')
            result = progress(args.root, now, args.stall_seconds)
            if args.format == 'markdown':
                sys.stdout.write(progress_markdown(result))
                return 0 if result['ok'] else 1
        else:
            result = contracts()
    except InputError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result.get('ok', True) else 1


if __name__ == '__main__':
    sys.exit(main())
