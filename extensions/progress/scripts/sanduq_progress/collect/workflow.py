"""Workflow collector: checkpoint, delegations.json and decisions.json as versioned JSON, tolerant of missing or
older shapes. Progress never imports Workflow code and never writes these files."""
import re
from pathlib import Path

from ..util import clean, read_json

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
    return {'branch': data.get('branch'), 'feature': data.get('feature'), 'status': data.get('status'),
            'stage': active.get('stage') if active else None, 'issue': link, 'updated_at': data.get('updated_at'),
            'started_at': first, 'pause': {'reason': clean(pause.get('reason'), 120), 'at': pause.get('at')}
            if pause else None}


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
