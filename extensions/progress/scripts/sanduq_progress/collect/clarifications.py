"""Clarification records: `workflow/clarifications.json`, written by Scope after a published clarification round
(producer contract, version 1). Progress renders from this file and makes no GitHub calls.

    {"v": 1, "items": [{source_id, revision, question, options, answer: {kind, value}|null, state, url, editor|null,
                        observed_at, answered_at|null, applied: {at, evidence}|null, evidence: [..]}]}

`state` is pending, conflict, answered, applied, waived, superseded or withdrawn. `answer.kind` is single, multiple or
text. `editor` and `answered_at` are null when the evidence does not record them; Progress never fills them in. Several
items may share a `source_id` (revisions): the highest `revision` is current and the others are shown as superseded.

Evidence types. `evidence` is a list of objects `{kind, url|null, comment_id|null, explanation|null}`; `applied.evidence`
is a list of strings. The reader also accepts plain strings in `evidence` and one string for `applied.evidence` (it is
wrapped in a list). An evidence object is flattened to a display string of at most 200 characters, and its `url` is kept
as a link in `evidence_links` ({text, url}) when it is an https URL. Nothing is invented for a missing field.

Input size. The file is read up to `READ_CAP` bytes. A larger file is reported as `invalid` with `truncated` set and is not
parsed, so a runaway file cannot consume memory during a refresh."""
import json
import re
from pathlib import Path

from ..util import clean, read_capped

STATES = ('pending', 'conflict', 'answered', 'applied', 'waived', 'superseded', 'withdrawn')
KINDS = ('single', 'multiple', 'text')
READ_CAP = 2 * 1024 * 1024
EVIDENCE_CAP = 200
EVIDENCE_ITEMS = 10


def _str(value, cap):
    return clean(value, cap) if isinstance(value, str) and value.strip() else None


def _https(value):
    return value.strip()[:500] if isinstance(value, str) and value.strip().startswith('https://') else None


def _decode(text, options):
    """(option text, index). Scope records a choice as a letter (A, B, ...) that names the option at that position; a
    letter in range is decoded here, once, so nothing downstream guesses. Otherwise the text counts only when it equals an
    option exactly. Free text (kind `text`) is never decoded."""
    if re.fullmatch(r'[A-Za-z]', text) and ord(text.upper()) - 65 < len(options):  # ASCII letters only; anything else is exact text
        i = ord(text.upper()) - 65
        return options[i], i
    return text, options.index(text) if text in options else None


def _answer(value, options):
    if not isinstance(value, dict) or value.get('kind') not in KINDS:
        return None
    raw = value.get('value')
    if value['kind'] == 'multiple':
        items = [clean(x, 200) for x in raw if isinstance(x, str) and x.strip()] if isinstance(raw, list) else []
        if not items:
            return None
        pairs = [_decode(x, options) for x in items]
        idx = [i for _, i in pairs]
        return {'kind': 'multiple', 'value': [t for t, _ in pairs], 'index': None if None in idx else idx}
    text = _str(raw, 400)
    if not text:
        return None
    if value['kind'] == 'text':
        return {'kind': 'text', 'value': text, 'index': options.index(text) if text in options else None}
    shown, i = _decode(text, options)
    return {'kind': value['kind'], 'value': shown, 'index': i}


def _evidence_one(entry):
    """(display text, https url or None) for one evidence entry, or None when it holds nothing readable."""
    if isinstance(entry, str):
        text = _str(entry, EVIDENCE_CAP)
        return (text, None) if text else None
    if not isinstance(entry, dict):
        return None
    kind, explanation = _str(entry.get('kind'), 60), _str(entry.get('explanation'), EVIDENCE_CAP)
    comment, url = entry.get('comment_id'), _https(entry.get('url'))
    comment = clean(comment, 40) if isinstance(comment, (str, int)) and not isinstance(comment, bool) and str(comment).strip() else None
    parts = [kind, f'comment {comment}' if comment else None, explanation]
    if not (comment or explanation) and url:
        parts.append(url)
    text = clean(' '.join(p for p in parts if p), EVIDENCE_CAP)
    return (text, url) if text else None


def _evidence(value):
    """([display strings], [{text, url}]) from a list of objects or strings (a single string or object is wrapped)."""
    if isinstance(value, (str, dict)):
        value = [value]
    rows = [x for x in map(_evidence_one, value[:EVIDENCE_ITEMS]) if x] if isinstance(value, list) else []
    return [t for t, _ in rows], [{'text': t, 'url': u} for t, u in rows if u]


def _item(item):
    if not isinstance(item, dict) or not _str(item.get('source_id'), 80) or item.get('state') not in STATES:
        return None
    revision = item.get('revision')
    applied = item.get('applied') if isinstance(item.get('applied'), dict) else None
    options = item.get('options')
    texts, links = _evidence(item.get('evidence'))
    return {'source_id': _str(item['source_id'], 80),
            'revision': revision if isinstance(revision, int) and not isinstance(revision, bool) else 1,
            'question': _str(item.get('question'), 200),
            'options': [clean(o, 200) for o in options[:20] if isinstance(o, str)] if isinstance(options, list) else [],
            'answer': _answer(item.get('answer'), [clean(o, 200) for o in options[:20] if isinstance(o, str)] if isinstance(options, list) else []), 'state': item['state'],
            'url': _https(item.get('url')),
            'editor': _str(item.get('editor'), 80), 'observed_at': _str(item.get('observed_at'), 40),
            'answered_at': _str(item.get('answered_at'), 40),
            'applied': {'at': _str(applied.get('at'), 40), 'evidence': _evidence(applied.get('evidence'))[0]} if applied else None,
            'evidence': texts, 'evidence_links': links}


def collect(feature_dir, cap=None):
    """{'state': absent|available|unsupported|invalid, 'items': [...], 'skipped': n, 'truncated': bool}."""
    path = Path(feature_dir) / 'workflow' / 'clarifications.json'
    out = {'state': 'absent', 'items': [], 'skipped': 0, 'truncated': False}
    if not path.is_file():
        return out
    try:
        raw, size, truncated = read_capped(path, cap or READ_CAP)
        data = None if truncated else json.loads(raw.decode('utf-8'))
    except (OSError, ValueError):
        data, truncated = None, False
    if truncated:
        return {**out, 'state': 'invalid', 'truncated': True}
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        return {**out, 'state': 'invalid'}
    if data.get('v') != 1:
        return {**out, 'state': 'unsupported'}
    items = [x for x in map(_item, data['items']) if x]
    return {**out, 'state': 'available', 'items': items, 'skipped': len(data['items']) - len(items)}
