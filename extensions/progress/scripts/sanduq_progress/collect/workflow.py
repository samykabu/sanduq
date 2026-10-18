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
    # A receipt Workflow marked stale (outcome still passed) is no longer current: it never names the stage the feature
    # is at. It stays in `accepted` for pause supersession and the events list, which record what happened.
    current = [r for r in accepted if not r['_stale']]
    latest = current[-1] if current else None
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
            'generation': _int(data.get('generation')), 'stage_plan': stage_plan(data.get('stage_plan')),
            'next_action': next_action(data.get('next_action')), 'recoveries': recoveries(data.get('recoveries')),
            'processes': _processes(data.get('policy')),
            'receipt_flags': {str(r['stage']): {'stale': r['_stale'], 'mode': r['mode']} for r in accepted},
            'started_at': first, 'last_accepted': {'stage': latest['stage'], 'at': latest['at']} if latest else None,
            'receipts': [{'stage': r['stage'], 'at': r['at']} for r in accepted],
            'pause': {'reason': clean(pause.get('reason'), 120), 'at': pause.get('at'), 'superseded': superseded}
            if pause else None}


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _processes(policy):
    """The policy snapshot's qa / user_manual switches when the checkpoint carries them, else None for each."""
    processes = policy.get('processes') if isinstance(policy, dict) and isinstance(policy.get('processes'), dict) else {}
    return {k: processes.get(k) if isinstance(processes.get(k), bool) else None for k in ('qa', 'user_manual')}


def stage_plan(value):
    """Workflow's published stage list (`stage_plan: {v, generation, stages}`), validated. `state` is absent, available,
    unsupported (a version this reader does not know) or invalid; only `available` carries stages."""
    if value is None:
        return {'state': 'absent', 'generation': None, 'stages': []}
    if not isinstance(value, dict) or not isinstance(value.get('stages'), list):
        return {'state': 'invalid', 'generation': None, 'stages': []}
    if value.get('v') != 1:
        return {'state': 'unsupported', 'generation': None, 'stages': []}
    out = []
    for item in value['stages']:
        ident = (item.get('id') or item.get('stage')) if isinstance(item, dict) else item
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,40}', ident) or any(s['id'] == ident for s in out):
            return {'state': 'invalid', 'generation': None, 'stages': []}
        label = item.get('label') if isinstance(item, dict) and isinstance(item.get('label'), str) else None
        out.append({'id': ident, 'label': clean(label, 60) if label else None})
    return {'state': 'available', 'generation': _int(value.get('generation')), 'stages': out}


NEXT_KINDS = ('active-claim', 'next-stage')


def next_action(value):
    """Workflow's cached next-action evaluation, or None. Progress never computes one."""
    if not isinstance(value, dict) or not isinstance(value.get('text'), str) or not value['text'].strip():
        return None
    kind, stage = value.get('kind'), value.get('stage')
    return {'text': clean(value['text'], 200), 'stage': stage if isinstance(stage, str) and stage else None,
            'kind': kind if kind in NEXT_KINDS else None,
            'evaluated_at': value.get('evaluated_at') if isinstance(value.get('evaluated_at'), str) else None,
            'generation': _int(value.get('generation'))}


def _claim_id(value):
    """The non-credential claim id Workflow 1.12.0 writes on receipts and recoveries, or None (a legacy record)."""
    return clean(value, 120) if isinstance(value, str) and value.strip() else None


def recoveries(value):
    """Recorded recoveries. Workflow stores each as `{claim: {stage, claimed_at, mode, delegation: {identity}, ...}, reason, at}`
    (an older flat `{stage, reason, at}` is read too). The claim's `claimed_at` is kept as the episode start and its
    delegation identity as identity evidence. The claim token is never read."""
    if not isinstance(value, list):
        return []
    out = []
    for r in value:
        if not isinstance(r, dict) or not parse_time(r.get('at')):
            continue
        claim = r.get('claim') if isinstance(r.get('claim'), dict) else {}
        stage = r.get('stage') or claim.get('stage')
        delegation = claim.get('delegation') if isinstance(claim.get('delegation'), dict) else {}
        identity = delegation.get('identity')
        started = claim.get('claimed_at')
        out.append({'stage': str(stage) if stage else None, 'reason': clean(r.get('reason'), 120), 'at': r.get('at'),
                    'started_at': started if parse_time(started) else None, 'claim_id': _claim_id(claim.get('claim_id')),
                    'mode': claim.get('mode') if claim.get('mode') in ('initial', 'revalidate', 'resume') else None,
                    'identity': clean(identity, 160) if isinstance(identity, str) and identity.strip() else None})
    return out


def accepted_receipts(receipts):
    """Accepted stage receipts ({stage, at, _when}) in completion order: outcome `passed` with a completion time. Ties
    keep the receipts' own (lifecycle) order. Receipt bodies are not read beyond these three fields and the `stale` mark."""
    rows = []
    for index, (key, item) in enumerate((receipts or {}).items() if isinstance(receipts, dict) else ()):
        if not isinstance(item, dict) or item.get('outcome') != 'passed':
            continue
        at = item.get('completed_at') or item.get('created_at')
        when = parse_time(at)
        if when:
            rows.append((when, index, {'stage': str(item.get('stage') or key), 'at': at, '_when': when, '_stale': bool(item.get('stale')),
                                    'mode': item.get('mode') if isinstance(item.get('mode'), str) else None,
                                    'claim_id': _claim_id(item.get('claim_id')),
                                    'created_at': item.get('created_at') if parse_time(item.get('created_at')) else None}))
    return [r[2] for r in sorted(rows, key=lambda r: (r[0], r[1]))]


def attempts(feature_dir):
    data = read_json(Path(feature_dir) / 'workflow' / 'delegations.json')
    rows = data.get('attempts') if isinstance(data, dict) else None
    return [a for a in rows or [] if isinstance(a, dict) and a.get('identity')]


def ledger_feature(feature_dir):
    """The feature directory the delegation ledger says it belongs to (it prefixes every delegation identity)."""
    data = read_json(Path(feature_dir) / 'workflow' / 'delegations.json')
    value = data.get('feature') if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


def identity_tasks(attempt):
    """Task ids a delegation owns: an explicit list when the attempt carries one, else ids in its identity."""
    for key in ('tasks', 'task_ids', 'owned_tasks'):
        if isinstance(attempt.get(key), list):
            return [str(t) for t in attempt[key] if re.fullmatch(r'T\d+', str(t))]
    return list(dict.fromkeys(re.findall(r'(?<![A-Za-z0-9])T\d+(?![A-Za-z0-9])', str(attempt.get('identity')))))


def _option_text(value, options):
    """(option text, option index or None). The ledger stores choices as letters (A, B, ...), which name the option at that
    position; the text is returned here so no later stage decodes it again. Anything else is the cleaned text, with its
    index only when it equals an option exactly."""
    text = value.strip()
    letter = ord(text.upper()) - 65 if re.fullmatch(r'[A-Za-z]', text) else -1  # ASCII letters only
    if 0 <= letter < len(options):
        return options[letter], letter
    shown = clean(text, 80)
    return shown, options.index(shown) if shown in options else None


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
        pairs = [] if pending else [_option_text(p, options) for p in picked if isinstance(p, str) and p.strip()]
        chosen = [t for t, _ in pairs]
        indexes = [i for _, i in pairs]
        selected = (chosen if multiple else chosen[0]) if chosen else None
        selected_index = (None if None in indexes else indexes if multiple else indexes[0]) if indexes else None
        stamps = [str(x.get(k)) for x in answers for k in ('updated_at', 'created_at', 'at') if x.get(k)]
        stamp = max(stamps) if stamps else None
        authors = [clean(x.get('author'), 80) for x in answers if isinstance(x.get('author'), str) and x['author'].strip()]
        application = item.get('application') if isinstance(item.get('application'), dict) else None
        evidence = application.get('evidence') if application and isinstance(application.get('evidence'), dict) else {}
        out.append({'id': str(item['id']), 'question': clean(item.get('question') or f"Workflow decision {item['id']}", 200),
                    'options': options, 'selected': selected, 'selected_index': selected_index, 'decided_by': 'user' if selected else None,
                    'at': stamp, 'url': item.get('question_url'), 'source': 'workflow',
                    'pending': pending,
                    # v3 adapter inputs: the ledger's own status and mode, answer digest, recorded author, application evidence
                    'raw_status': status, 'multiple': multiple, 'revision': len(answers),
                    'answer_digest': item.get('answer_digest') if isinstance(item.get('answer_digest'), str) else None,
                    'author': authors[-1] if authors else None,
                    'applied_evidence': sorted(clean(k, 160) for k in evidence)})
    return True, out
