"""Workflow collector: checkpoint, delegations.json and decisions.json as versioned JSON, tolerant of missing or
older shapes. Progress never imports Workflow code and never writes these files."""
import re
from pathlib import Path

from ..util import clean, parse_time, read_json

ACTIVE = ('starting', 'running')


def checkpoint(feature_dir):
    data = read_json(Path(feature_dir) / 'workflow' / 'checkpoint.json')
    if not isinstance(data, dict):
        return None
    active = data.get('active') if isinstance(data.get('active'), dict) else None
    issue = data.get('issue') if isinstance(data.get('issue'), str) else None
    link = None
    match = re.fullmatch(r'([^/\s]+/[^#\s]+)#(\d+)', issue or '')
    if match:
        link = {'number': int(match.group(2)), 'url': f'https://github.com/{match.group(1)}/issues/{match.group(2)}'}
    pause = data.get('pause') if isinstance(data.get('pause'), dict) else None
    first = next((h.get('at') for h in data.get('branch_history', []) if isinstance(h, dict) and h.get('at')), None)
    accepted = accepted_receipts(data.get('receipts'))
    last = accepted[-1] if accepted else None
    # A pause is a snapshot taken when the feature stopped. An accepted receipt completed after it means the feature
    # moved on, so the pause is history, not a blocker. The checkpoint keeps the stale record; we do not.
    paused_at = parse_time(pause.get('at')) if pause else None
    claimed = parse_time(active.get('claimed_at')) if active else None
    status = data.get('status')
    # Workflow's claim moves the status off `paused` and stamps `active.claimed_at`, but never clears `pause`.
    superseded = None  # why the pause is history: a neutral reason, or None while it still stands
    if pause:
        if paused_at and last and last['_when'] > paused_at:
            superseded = 'later accepted receipt'
        elif paused_at and claimed and claimed > paused_at:
            superseded = 'newer claim'
        elif status not in (None, 'paused'):
            superseded = f'status is {status}'
    return {'branch': data.get('branch'), 'feature': data.get('feature'), 'status': data.get('status'),
            'stage': active.get('stage') if active else None, 'issue': link, 'updated_at': data.get('updated_at'),
            'started_at': first, 'last_accepted': {'stage': last['stage'], 'at': last['at']} if last else None,
            'receipts': [{'stage': r['stage'], 'at': r['at']} for r in accepted],
            'pause': {'reason': clean(pause.get('reason'), 120), 'at': pause.get('at'), 'superseded': superseded}
            if pause else None}


def accepted_receipts(receipts):
    """Accepted stage receipts ({stage, at, _when}) in completion order: outcome `passed` with a completion time. Ties
    keep the receipts' own (lifecycle) order. Receipt bodies are not read beyond these three fields."""
    rows = []
    for index, (key, item) in enumerate((receipts or {}).items() if isinstance(receipts, dict) else ()):
        if not isinstance(item, dict) or item.get('outcome') != 'passed':
            continue
        at = item.get('completed_at') or item.get('created_at')
        when = parse_time(at)
        if when:
            rows.append((when, index, {'stage': str(item.get('stage') or key), 'at': at, '_when': when}))
    return [r[2] for r in sorted(rows, key=lambda r: (r[0], r[1]))]


def attempts(feature_dir):
    data = read_json(Path(feature_dir) / 'workflow' / 'delegations.json')
    rows = data.get('attempts') if isinstance(data, dict) else None
    return [a for a in rows or [] if isinstance(a, dict) and a.get('identity')]


def identity_tasks(attempt):
    """Task ids a delegation owns: an explicit list when the attempt carries one, else ids in its identity."""
    for key in ('tasks', 'task_ids', 'owned_tasks'):
        if isinstance(attempt.get(key), list):
            return [str(t) for t in attempt[key] if re.fullmatch(r'T\d+', str(t))]
    return list(dict.fromkeys(re.findall(r'(?<![A-Za-z0-9])T\d+(?![A-Za-z0-9])', str(attempt.get('identity')))))


def _option_text(value, options):
    """A letter answer (A, B, ...) names the option at that position; anything else is shown as the cleaned text."""
    text = value.strip()
    letter = ord(text.upper()) - 65 if len(text) == 1 else -1
    return options[letter] if 0 <= letter < len(options) else clean(text, 80)


def decisions(feature_dir):
    """(exists, normalised list). Workflow decisions carry ids like SD1; the question text is not stored in the
    ledger, so a missing `question` is shown as the id."""
    path = Path(feature_dir) / 'workflow' / 'decisions.json'
    if not path.is_file():
        return False, []
    data = read_json(path, {})
    out = []
    for item in (data.get('decisions') if isinstance(data, dict) else None) or []:
        if not isinstance(item, dict) or not item.get('id'):
            continue
        options = [clean(o, 80) for o in item.get('options') or []] if isinstance(item.get('options'), list) else []
        status = str(item.get('status') or 'pending')
        pending = status in ('pending', 'conflict')
        answers = [x for x in item.get('answers') or [] if isinstance(x, dict)] if isinstance(item.get('answers'), list) else []
        # Producer shapes (workflow decisions.py): single mode stores `option` (a letter) and `selected` ([letter]);
        # multiple mode stores `option: null` and `selected: [letters]`. Either may be absent in older ledgers.
        picked = item.get('selected') if isinstance(item.get('selected'), list) else []
        if not picked and item.get('option'):
            picked = [item['option']]
        multiple = item.get('mode') == 'multiple' or (item.get('mode') is None and len(picked) > 1)
        chosen = [] if pending else [_option_text(p, options) for p in picked if isinstance(p, str) and p.strip()]
        selected = (chosen if multiple else chosen[0]) if chosen else None
        stamps = [str(x.get(k)) for x in answers for k in ('updated_at', 'created_at', 'at') if x.get(k)]
        stamp = max(stamps) if stamps else None
        out.append({'id': str(item['id']), 'question': clean(item.get('question') or f"Workflow decision {item['id']}", 200),
                    'options': options, 'selected': selected, 'decided_by': 'user' if selected else None,
                    'at': stamp, 'url': item.get('question_url'), 'source': 'workflow',
                    'pending': pending})
    return True, out
