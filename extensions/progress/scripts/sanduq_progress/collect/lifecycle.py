"""Workflow lifecycle events: `workflow/lifecycle.jsonl`, one JSON record per line (producer contract, version 1):

    {v, event_id, workflow_run_id, generation, at, stage, event, episode_id, claim_id, caused_by_claim_id,
     candidate_run_id, delegation_run_ids, reason}

`event` is one of EVENTS. `episode_id`, `claim_id`, `caused_by_claim_id`, `candidate_run_id` and `workflow_run_id` may be
null; null is explicit and is never filled in from time or adjacency. `claim_id` is a non-credential id, never the raw
claim token.

- `delegation_run_ids` is claim membership: every delegation run linked to the claim. It never implies acceptance.
- `candidate_run_id` (on `accepted` and `rejected-completion`) is the exact run whose candidate Workflow validated, or null.
- A claim-time `invalidated` event removes a downstream receipt: it has `claim_id` and `episode_id` null and names the
  claim that caused it in `caused_by_claim_id`.
- `stage` may be null only for `paused` and `recovered`, which can happen with no claim held (a feature-level event).

The reader tolerates a torn final line (a crashed append), skips a corrupt complete line and counts it, and de-duplicates
by `event_id` (a replayed append writes the same event twice). It reads at most `READ_CAP` bytes: a larger file is read
from its tail (the newest events), the cut line is dropped and `truncated` is reported. Progress never writes this file."""
import json
from pathlib import Path

from ..util import clean, parse_time, read_capped

EVENTS = ('claim', 'resume', 'accepted', 'rejected-completion', 'recovered', 'paused', 'invalidated', 'revalidated',
          'revalidation-stale')
STARTS = ('claim', 'resume')
STAGE_OPTIONAL = ('paused', 'recovered')
READ_CAP = 8 * 1024 * 1024


def _text(value, cap=80):
    return clean(value, cap) if isinstance(value, str) and value.strip() else None


def _event(item):
    """Normalised event or None when the record is not a usable version-1 event."""
    if not isinstance(item, dict) or item.get('v') != 1 or item.get('event') not in EVENTS:
        return None
    ident, stage = _text(item.get('event_id'), 120), _text(item.get('stage'), 60)
    if not ident or not parse_time(item.get('at')):
        return None
    if not stage and item['event'] not in STAGE_OPTIONAL:
        return None
    runs = item.get('delegation_run_ids')
    generation = item.get('generation')
    return {'event_id': ident, 'workflow_run_id': _text(item.get('workflow_run_id'), 120),
            'generation': generation if isinstance(generation, int) and not isinstance(generation, bool) else None,
            'at': item['at'], 'stage': stage, 'event': item['event'], 'episode_id': _text(item.get('episode_id'), 120),
            'claim_id': _text(item.get('claim_id'), 120), 'caused_by_claim_id': _text(item.get('caused_by_claim_id'), 120),
            'candidate_run_id': _text(item.get('candidate_run_id'), 120),
            'delegation_run_ids': [str(r)[:120] for r in runs if isinstance(r, (str, int)) and str(r)] if isinstance(runs, list) else [],
            'reason': _text(item.get('reason'), 120)}


def collect(feature_dir, cap=None):
    """{'state': absent|available|invalid, 'events': [...], 'torn': bool, 'corrupt': n, 'skipped': n, 'conflicts': [event_id],
    'truncated': bool, 'bytes': file size}. Events are ordered by time, then by their position in the file."""
    path = Path(feature_dir) / 'workflow' / 'lifecycle.jsonl'
    out = {'state': 'absent', 'events': [], 'torn': False, 'corrupt': 0, 'skipped': 0, 'conflicts': [], 'truncated': False,
           'bytes': 0}
    try:
        raw, size, truncated = read_capped(path, cap or READ_CAP, tail=True)
    except OSError:
        return out
    out['state'], out['bytes'] = 'available', size
    if truncated:
        # the read began inside a line: drop that partial line, keep the newest complete ones
        out['truncated'] = True
        cut = raw.find(b'\n')
        raw = raw[cut + 1:] if cut >= 0 else b''
    chunks = raw.split(b'\n')
    tail = chunks.pop()  # empty when the file ends with a newline; otherwise a possibly torn final record
    seen, rows = {}, []
    for index, chunk in enumerate([*chunks, tail]):
        if not chunk.strip():
            continue
        try:
            item = json.loads(chunk.decode('utf-8'))
        except ValueError:
            if index == len(chunks):
                out['torn'] = True
            else:
                out['corrupt'] += 1
            continue
        event = _event(item)
        if event is None:
            out['skipped'] += 1
            continue
        known = seen.get(event['event_id'])
        if known is not None:
            if known != event:
                out['conflicts'].append(event['event_id'])
            continue
        seen[event['event_id']] = event
        rows.append((parse_time(event['at']), len(rows), event))
    out['events'] = [e for _, _, e in sorted(rows, key=lambda r: (r[0], r[1]))]
    if not out['events'] and (out['corrupt'] or out['skipped']):
        out['state'] = 'invalid'
    return out
