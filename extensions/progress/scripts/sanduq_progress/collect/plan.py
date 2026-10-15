"""Plan collector: any Markdown checklist is a task list. The plan file is read, never written; whoever owns the plan
checks items off.

Recognised: `- [ ] Title`, `- [x] T001 [P] Title (depends on T000, P002)`, `(after T001)`. A level-2 or deeper heading
names the phase of the items below it; the first level-1 heading is the title. Fenced blocks and inline code spans are
ignored, so ids quoted in prose never create tasks or edges.

Ids. An item that starts with an id keeps it: `**T001**`/`**US3**` (bold, any form), or a bare `T001`, `T-12`, `US3`, `P003`
followed by a space or `:` `.` `)` when it has two digits or more, or the prefix `T`/`US`. Words such as MP3, GPT-4, Q3, A4 and
ES6 are text. A second item with an id already taken becomes an auto item (with a diagnostics line), never dropped.
Every other item gets an auto id `P001`, `P002`, ... The tracked `plan.json` stores only the id and a one-way fingerprint
of the normalised text (never the text). The text itself, needed for fuzzy matching, lives in the git-ignored
`.host/plan-keys.json`. The map is applied in this order, so ids stay stable as the plan is edited:

1. an item whose fingerprint equals a stored one reuses its id (first unused match, in plan order);
2. an item whose text is at least 60 percent similar to a stored, still unmatched one (text known locally) reuses that id;
3. anything else takes the next number. Numbers are never reused, even after an item is deleted.

Reordering therefore changes nothing, and a small rewording keeps the id. Rewording an item beyond recognition, or
deleting it and adding another, gives a new id. Checking an item off never changes its id.
"""
import difflib
import hashlib
import re
from pathlib import Path

from ..paths import RESERVED_ID, TASK_REF, plan_info, plan_source
from ..util import clean, diag_once, read_json

ITEM = re.compile(r'^\s*[-*+]\s+\[([ xX])\]\s+(.*)$')
HEADING = re.compile(r'^(#{1,6})\s+(.*?)\s*#*\s*$')
FENCE = re.compile(r'^\s*(```|~~~)')
SPAN = re.compile(r'(`+)(.+?)\1')
LEAD_ID = re.compile(r'^(?:(\*\*|__)(' + TASK_REF + r')(?:\*\*|__)|(' + TASK_REF + r'))([:.)]|\s|$)\s*(.*)$')
BARE_ID = re.compile(r'(?:T|US|P)\d+')  # an id with no bold and no `:` `.` `)` after it: T001, US12, P003; X11, H264, RFC-7231 are text
BARE_PREFIXES = ('T', 'US')  # a one-digit delimited id is an id only with one of these prefixes (T7, US3)
DEPENDS = re.compile(r'\((?:depends on|after)\s+([^)]*)\)', re.I)
PARALLEL = re.compile(r'(?<![\w`])\[P\](?![\w`])')
REF = re.compile(r'(?<![\w-])' + TASK_REF + r'(?![\w-])')
SIMILAR = 0.6
MAX_BYTES = 1 << 20


def _blank_spans(text):
    return SPAN.sub(lambda m: ' ' * len(m.group(0)), text)


def _key(text):
    """Normalised item text: what identifies an item across edits (case, spacing and markdown emphasis are ignored)."""
    text = re.sub(r'[*_`~]', '', text.lower())
    return re.sub(r'\s+', ' ', text).strip()[:120]


def fingerprint(key):
    """One-way, truncated identity of an item's normalised text: what the tracked plan.json stores instead of the text."""
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]


def explicit_id(body):
    """(id, rest of the item) when `body` starts with a documented id form, else (None, body)."""
    lead = LEAD_ID.match(body)
    if not lead:
        return None, body
    bold, ident, bare, delimiter, rest = lead.groups()
    ident = (ident or bare).upper()
    if RESERVED_ID.fullmatch(ident):
        return None, body
    if not bold and delimiter not in (':', '.', ')') and not BARE_ID.fullmatch(ident):
        return None, body
    if not bold:
        digits = re.search(r'\d+$', ident).group(0)
        if len(digits) < 2 and not re.match(r'(?:' + '|'.join(BARE_PREFIXES) + r')-?\d', ident):
            return None, body
    return ident, rest


def _number(ident):
    match = re.fullmatch(r'P(\d+)', str(ident))
    return int(match.group(1)) if match else 0


def parse(text):
    """Return {'title', 'items'}: items in plan order with `id` (explicit ids only; auto items carry None)."""
    items, seen, phase, title, fence, duplicates = [], set(), None, None, None, []
    for line in text.splitlines():
        marker = FENCE.match(line)
        if marker:
            fence = None if fence == marker.group(1) else (fence or marker.group(1))
            continue
        if fence:
            continue
        heading = HEADING.match(line)
        if heading:
            if len(heading.group(1)) == 1:
                title = title or clean(heading.group(2), 160)
            else:
                phase = clean(heading.group(2), 120)
            continue
        found = ITEM.match(line)
        if not found:
            continue
        body = found.group(2)
        ident, rest = explicit_id(body)
        if ident and ident in seen:
            duplicates.append(ident)
            ident = None
        elif ident:
            seen.add(ident)
            body = rest
        bare = _blank_spans(body)
        refs = []
        for match in DEPENDS.finditer(bare):
            refs += [r.upper() for r in REF.findall(match.group(1)) if r.upper() not in refs]
        shown = re.sub(r'\(\s*(?:depends on|after)\s+[^)]*\)', '', body, flags=re.I)
        shown = clean(PARALLEL.sub('', shown), 160)
        items.append({'id': ident, 'title': shown, 'phase': phase or '', 'done': found.group(1) != ' ',
                      'parallel': bool(PARALLEL.search(bare)), 'refs': refs, 'key': _key(shown)})
    return {'title': title, 'items': items, 'duplicates': duplicates}


def _fp(entry):
    """Fingerprint of a stored entry; entries written before fingerprints existed carried the text itself."""
    return entry.get('fp') or (fingerprint(entry['key']) if isinstance(entry.get('key'), str) else None)


def assign(items, stored, floor=0):
    """Give every auto item its id. `stored` is the previous [{id, fp, key?}] map (`key` only when known locally); returns
    (new map of {id, fp, key}, next number)."""
    explicit = {i['id'] for i in items if i['id']}
    autos = [i for i in items if not i['id']]
    previous = [dict(s) for s in stored if isinstance(s, dict) and re.fullmatch(r'P\d+', str(s.get('id'))) and s['id'] not in explicit]
    highest = max([floor, *(_number(s['id']) for s in previous), *(_number(e) for e in explicit)] or [0])
    taken = {}
    free = list(range(len(previous)))
    by_fp = {}  # fingerprint -> previous slots in stored order, so equal texts keep their order
    for slot in free:
        by_fp.setdefault(_fp(previous[slot]), []).append(slot)
    prints = [fingerprint(item['key']) for item in autos]  # once per item
    for index in range(len(autos)):  # 1. exact text
        slots = by_fp.get(prints[index])
        if slots:
            slot = slots.pop(0)
            taken[index] = previous[slot]['id']
            free.remove(slot)
    pairs = []
    for index, item in enumerate(autos):  # 2. similar text, best first
        if index in taken:
            continue
        for slot in free:
            known = previous[slot].get('key')
            if not isinstance(known, str) or not known:
                continue
            ratio = difflib.SequenceMatcher(None, item['key'], known).ratio()
            if ratio >= SIMILAR:
                pairs.append((-ratio, abs(index - slot), index, slot))
    for _, _, index, slot in sorted(pairs):
        if index not in taken and slot in free:
            taken[index] = previous[slot]['id']
            free.remove(slot)
    for index, item in enumerate(autos):  # 3. new numbers
        if index not in taken:
            highest += 1
            while f'P{highest:03d}' in explicit:
                highest += 1
            taken[index] = f'P{highest:03d}'
    for index, item in enumerate(autos):
        item['id'] = taken[index]
    return [{'id': i['id'], 'fp': prints[n], 'key': i['key']} for n, i in enumerate(autos)], highest


def _read(ctx):
    source = plan_source(ctx.root, ctx.feature)
    if source is None:
        return None
    try:
        with open(source, 'rb') as stream:
            return stream.read(MAX_BYTES).decode('utf-8', errors='replace')
    except OSError:
        return None


def _stored(ctx, info):
    """Previous id map: fingerprints from the tracked plan.json, texts (when this clone has them) from the ignored host file."""
    keys = read_json(ctx.host_dir / 'plan-keys.json', {})
    keys = keys if isinstance(keys, dict) else {}
    out = []
    for entry in info.get('ids') or []:
        if isinstance(entry, dict):
            entry = dict(entry)
            if isinstance(keys.get(entry.get('id')), str):
                entry['key'] = keys[entry['id']]
            out.append(entry)
    return out


def collect(ctx):
    """Tasks of a plan in the shape the projection expects, plus the id map to persist (`ids` tracked: id and fingerprint;
    `keys` local: id to normalised text)."""
    info = plan_info(ctx.root, ctx.feature)
    text = _read(ctx)
    if text is None:
        return {'title': None, 'tasks': [], 'ids': info.get('ids') or [], 'keys': {}, 'next': info.get('next') or 0, 'missing': True}
    parsed = parse(text)
    mapping, highest = assign(parsed['items'], _stored(ctx, info), int(info.get('next') or 0))
    for ident in dict.fromkeys(parsed['duplicates']):
        diag_once(ctx.diag, f'plan: id {ident} is used by more than one item; later items got automatic ids')
    known = {i['id'] for i in parsed['items']}
    tasks = []
    for item in parsed['items']:
        depends = [r for r in item['refs'] if r in known and r != item['id']]
        tasks.append({'id': item['id'], 'title': item['title'], 'phase': item['phase'], 'done': item['done'],
                      'parallel': item['parallel'], 'depends_on': depends})
    return {'title': parsed['title'], 'tasks': tasks, 'ids': [{'id': m['id'], 'fp': m['fp']} for m in mapping],
            'keys': {m['id']: m['key'] for m in mapping}, 'next': highest, 'missing': False}


def persist(ctx, got=None):
    """Store the id map so the next edit keeps ids stable; returns the collected plan so the caller can reuse it. Caller
    holds the report lock. Writes only on change. The tracked plan.json gets ids and fingerprints, never item text."""
    from ..util import write_json
    got = got or collect(ctx)
    info = plan_info(ctx.root, ctx.feature)
    if not info or got['missing']:
        return got
    if info.get('ids') != got['ids'] or info.get('next') != got['next']:
        info['ids'], info['next'] = got['ids'], got['next']
        write_json(ctx.plan_file, info)
    if read_json(ctx.host_dir / 'plan-keys.json', None) != got['keys']:
        write_json(ctx.host_dir / 'plan-keys.json', got['keys'])
    return got
