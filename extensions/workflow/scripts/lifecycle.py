"""Lifecycle events for one Workflow feature: ``workflow/lifecycle.jsonl``.

The runtime queues each event in the checkpoint (`lifecycle_outbox`) in the same write that changes
the state, then appends the queue to the JSONL file under the feature lock. An append interrupted
between the file write and the checkpoint clearing is replayed on the next save and deduplicated by
``event_id``. Readers tolerate a torn final line. Nothing here records a claim token: ``claim_id`` is
a one-way identifier derived from it.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
EVENTS = ('claim', 'resume', 'accepted', 'rejected-completion', 'recovered', 'paused',
          'invalidated', 'revalidated', 'revalidation-stale')
FIELDS = ('v', 'event_id', 'workflow_run_id', 'generation', 'at', 'stage', 'event', 'episode_id',
          'claim_id', 'caused_by_claim_id', 'candidate_run_id', 'delegation_run_ids', 'reason')
REASON_LIMIT = 240
OUTBOX = 'lifecycle_outbox'


def claim_id_for(token):
    """A non-credential identifier for a claim; the token cannot be recovered from it."""
    if not token:
        return None
    return 'c-' + hashlib.sha256(('sanduq-claim-id:' + str(token)).encode('utf-8')).hexdigest()[:20]


def episode_for_claim(claim_id):
    return ('claim:' + claim_id) if claim_id else None


def log_path(feature_dir):
    return Path(feature_dir) / 'workflow' / 'lifecycle.jsonl'


def make_event(state, stage, event, *, episode_id=None, claim_id=None, caused_by_claim_id=None,
               candidate_run_id=None, delegation_run_ids=None, reason=None, generation=None, at=None):
    """Build one record. Nullable ids are written explicitly as null.

    ``candidate_run_id`` is set on ``accepted`` and on a ``rejected-completion`` that happened after the
    exact-claim check passed: the delegation run that check validated. Every other event leaves it null.
    ``caused_by_claim_id`` is set only on a claim-time ``invalidated``, which carries no claim or episode
    of its own.
    """
    assert event in EVENTS, event
    event_id = uuid.uuid4().hex
    if episode_id == 'revalidation':
        episode_id = 'revalidation:' + event_id
    text = None if reason is None else str(reason)[:REASON_LIMIT]
    return {'v': VERSION, 'event_id': event_id, 'workflow_run_id': state.get('run_id'),
            'generation': state.get('generation', 0) + 1 if generation is None else generation,
            'at': at or datetime.now(timezone.utc).isoformat(), 'stage': stage, 'event': event,
            'episode_id': episode_id, 'claim_id': claim_id, 'caused_by_claim_id': caused_by_claim_id,
            'candidate_run_id': candidate_run_id, 'delegation_run_ids': list(delegation_run_ids or []), 'reason': text}


def queue(state, stage, event, **kwargs):
    """Queue an event in the checkpoint state; it reaches the file when the state is saved."""
    record = make_event(state, stage, event, **kwargs)
    state.setdefault(OUTBOX, []).append(record)
    return record


def read_events(path):
    """Return ``(events, torn)``. Unparseable lines are skipped; ``torn`` is true when any were found."""
    events, torn = [], False
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return events, torn
    for line in raw.decode('utf-8', errors='replace').split('\n'):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            torn = True
            continue
        if isinstance(value, dict) and value.get('event_id'):
            events.append(value)
        else:
            torn = True
    return events, torn


def _repair_tail(path):
    """Make the file end on a record boundary before the replay is deduplicated.

    A complete JSON record that only lacks its newline is kept and terminated; an unparseable fragment
    is dropped. Returns True when the file changed.
    """
    if not path.exists():
        return False
    data = path.read_bytes()
    if not data or data.endswith(b'\n'):
        return False
    cut = data.rfind(b'\n') + 1
    tail = data[cut:]
    try:
        value = json.loads(tail.decode('utf-8'))
        keep = isinstance(value, dict) and bool(value.get('event_id'))
    except ValueError:
        keep = False
    data = data + b'\n' if keep else data[:cut]
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_bytes(data)
    os.replace(temp, path)
    return True


def append_events(path, records):
    """Append records whose ``event_id`` is not in the file yet. Returns the number appended."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _repair_tail(path)
    seen = {event['event_id'] for event in read_events(path)[0]}
    fresh = []
    for record in records:
        if record['event_id'] not in seen:
            seen.add(record['event_id'])
            fresh.append(record)
    if not fresh:
        return 0
    payload = ''.join(json.dumps(record, ensure_ascii=False, sort_keys=False) + '\n' for record in fresh)
    with open(path, 'ab') as handle:
        handle.write(payload.encode('utf-8'))
        handle.flush()
        os.fsync(handle.fileno())
    return len(fresh)


def flush(state, feature_dir):
    """Append the queued events. Returns True when the checkpoint must be rewritten to clear the queue."""
    pending = state.get(OUTBOX)
    if not pending:
        return False
    append_events(log_path(feature_dir), pending)
    state.pop(OUTBOX, None)
    return True


def delegation_runs_for(feature_dir, token=None, claim_id=None):
    """Run ids the delegation ledger links to this claim (by claim_id, else by the claim token)."""
    path = Path(feature_dir) / 'workflow' / 'delegations.json'
    try:
        ledger = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return []
    attempts = ledger.get('attempts') if isinstance(ledger, dict) else None
    runs = []
    for attempt in attempts or []:
        if not isinstance(attempt, dict) or not attempt.get('run_id'):
            continue
        linked = (claim_id and attempt.get('claim_id') == claim_id) or \
                 (token and attempt.get('claim_token') == token)
        if linked and attempt['run_id'] not in runs:
            runs.append(attempt['run_id'])
    return runs
