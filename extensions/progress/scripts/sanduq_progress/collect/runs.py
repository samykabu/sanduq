"""Run-journal projection for `.delegate/runs/<id>/{meta.json,journal.jsonl,result.json}`.

Ported from the Workflow lean branch (execution_tools.progress) behind a stable function interface:

    collect_runs(runs_dir, *, since=None, now=None, stall_seconds=300) -> list[dict]

Caveats, kept deliberately:
  * `elapsed_seconds` is wall time between start and end (or now). It is not active work time.
  * `phase == "stalled"` is a heuristic: no journal event for `stall_seconds`. A quiet worker may be healthy.
  * A terminal harness status (`successful`) is not acceptance. Acceptance is Workflow's decision, recorded in its
    ledger; this module never infers it.
  * Only each journal event's `t` and a lowercase `state` word are read, from the last 64 KiB. No prompt, stdout
    or stderr text is consulted.
  * `task_verdict`, `review_verdict` (one short word) and `next_action` (<= 200 characters) are copied from a final
    result.json when present; absent means 'unknown'/None. They are the harness's words, not acceptance.
  * `model` is the model that was requested at launch; only `model_reported` (from the result's `model_reported` or
    `model_observed`) is evidence of the model that ran.
  * `usage` is None unless the harness reported exact counters; zero placeholders are unknown, never measured.
  * Two records of one run_id are merged: a final record beats a live one; real disagreement is listed in
    `conflict`. Malformed run directories are skipped (and reported through `last_malformed()`).
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from ..util import parse_time

USAGE_FIELDS = ('input_total', 'input_fresh', 'cache_read', 'cache_write', 'output_total', 'reasoning', 'total')
JOURNAL_STATE = re.compile(r'[a-z][a-z_]{0,31}')
JOURNAL_TAIL_BYTES = 65536
DEFAULT_STALL_SECONDS = 300
CONFLICT_FIELDS = ('harness', 'harness_status', 'started_at', 'ended_at', 'usage')
_malformed = []
_duplicates = []


def last_malformed():
    return list(_malformed)


def last_duplicates():
    return sorted(set(_duplicates))


def usage_of(data):
    tokens = data.get('tokens')
    if not isinstance(tokens, dict) or tokens.get('fidelity') != 'exact':
        return None
    usage = {}
    for field in USAGE_FIELDS:
        value = tokens.get(field)
        usage[field] = value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    return usage if usage['total'] is not None else None


def journal_projection(directory):
    path = directory / 'journal.jsonl'
    if not path.is_file():
        return {'events': 0, 'state': None, 'last_event_at': None, 'terminal': False}
    with open(path, 'rb') as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - JOURNAL_TAIL_BYTES))
        tail = stream.read().decode('utf-8', 'replace').splitlines()
    if size > JOURNAL_TAIL_BYTES:
        tail = tail[1:]  # first line is probably cut
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


VERDICT = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,31}')


def _word(value):
    return value if isinstance(value, str) and VERDICT.fullmatch(value) else 'unknown'


def _text(value):
    return value[:200] if isinstance(value, str) and value else None


def _seconds(started, ended):
    return max(0, int((ended - started).total_seconds())) if started and ended else None


def _model_reported(data):
    """The model the harness says it actually ran. `model` in a result is the launch request, not an observation."""
    for key in ('model_reported', 'model_observed'):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
    if data.get('model_observed') is True:  # the delegate driver's shape: a flag plus the model it observed
        value = data.get('actual_model')
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
    return None


def project_run(live, path, now, stall_seconds):
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('run_id'), str) or not data['run_id']:
        raise ValueError('needs a non-empty string run_id')
    started, ended = parse_time(data.get('started_at')), parse_time(data.get('ended_at'))
    base = {'run_id': data['run_id'], 'harness': data.get('harness') or 'unknown', 'source': path.parent.name,
            'started_at': data.get('started_at'), 'model': data.get('model'),
            'model_reported': _model_reported(data)}
    # Verdict words are copied as short plain strings; their absence stays 'unknown'. Neither is acceptance.
    verdicts = {key: _word(data.get(key)) for key in ('task_verdict', 'review_verdict')}
    if live:
        journal = journal_projection(path.parent)
        last = parse_time(journal['last_event_at'])
        if journal['terminal']:
            phase, status = 'finishing', 'finalizing'
        elif last and (now - last).total_seconds() > stall_seconds:
            phase, status = 'stalled', 'stalled'
        else:
            phase, status = 'active', 'running'
        return {**base, **{k: 'unknown' for k in verdicts}, 'next_action': None, 'harness_status': status, 'phase': phase, 'usage': None,
                'elapsed_seconds': _seconds(started, now), 'journal_events': journal['events'],
                'latest_event': journal['state'], 'latest_event_at': journal['last_event_at'], 'ended_at': None}
    elapsed = _seconds(started, ended)
    if elapsed is None and isinstance(data.get('duration_ms'), int) and not isinstance(data['duration_ms'], bool):
        elapsed = data['duration_ms'] // 1000
    return {**base, **verdicts, 'next_action': _text(data.get('next_action')),
            'harness_status': data.get('status') or 'unknown', 'phase': 'done', 'usage': usage_of(data),
            'elapsed_seconds': elapsed, 'journal_events': None, 'latest_event': data.get('latest_event'),
            'latest_event_at': data.get('ended_at'), 'ended_at': data.get('ended_at')}


def _conflicts(first, second):
    if (first['phase'] == 'done') != (second['phase'] == 'done'):
        return [f for f in ('harness', 'started_at') if first[f] != second[f]]
    return [f for f in CONFLICT_FIELDS if first[f] != second[f]]


def collect_runs(runs_dir, *, since=None, now=None, stall_seconds=DEFAULT_STALL_SECONDS, only=None):
    """Compact projections of every run under `runs_dir`, sorted by (started_at, run_id).

    `since` (aware datetime) drops runs that started earlier; runs with an unknown start are kept.
    `only` (a set of run ids) limits the read to those runs: directories named after an id are read first, the run id
    each one holds is what counts (a directory name is only a hint), and the rest are scanned only while some id is
    still unresolved, so a long history is not parsed on every refresh. An empty set reads nothing."""
    global _malformed, _duplicates
    _malformed, _duplicates = [], []
    if only is not None and not only:
        return []
    now = now or datetime.now(timezone.utc)
    root = Path(runs_dir)
    if not root.is_dir():
        return []
    folders = sorted(p for p in root.iterdir() if p.is_dir())
    if only is not None:
        # a directory name is only a hint: read the same-named directories first, validate the run id each one holds,
        # and scan the rest only while some requested id is still unresolved
        hinted = [p for p in folders if p.name in only]
        rest = [p for p in folders if p.name not in only]
        folders = hinted
    runs, conflicting = {}, {}

    def read(directories):
        for directory in directories:
            result, meta = directory / 'result.json', directory / 'meta.json'
            source = result if result.is_file() else meta if meta.is_file() else None
            if source is None:
                continue
            try:
                run = project_run(source is meta, source, now, stall_seconds)
            except (OSError, ValueError) as exc:
                _malformed.append({'source': directory.name, 'error': str(exc)[:120]})
                continue
            known = runs.get(run['run_id'])
            if known:
                _duplicates.append(run['run_id'])
                diff = _conflicts(known, run)
                if diff:
                    conflicting.setdefault(run['run_id'], set()).update(diff)
                if run['phase'] != 'done':
                    continue
            runs[run['run_id']] = run

    read(folders)
    if only is not None and not only <= set(runs):
        read(rest)
    for run_id, fields in conflicting.items():
        runs[run_id]['conflict'] = sorted(fields)
    started = lambda r: parse_time(r['started_at'])
    chosen = [r for r in runs.values() if (since is None or started(r) is None or started(r) >= since)
              and (only is None or r['run_id'] in only)]
    return sorted(chosen, key=lambda r: (r['started_at'] or '', r['run_id']))
