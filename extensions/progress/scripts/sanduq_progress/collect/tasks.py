"""tasks.md collector. tasks.md owns task text and checkbox state; Progress only reads it.

Recognised: `- [ ] T001 [P] Title (depends on T000, T002)` and `(after T001)`. Headings of level 2 or 3 name the
phase. Fenced blocks and inline code spans are ignored, so task ids quoted in prose never create tasks or edges.
"""
import re
from pathlib import Path

from ..util import clean, read_bytes

CRLF, CR, LF = chr(13) + chr(10), chr(13), chr(10)
TASK = re.compile(r'^\s*[-*]\s+\[([ xX])\]\s+(T\d+)\b\s*(.*)$')
HEADING = re.compile(r'^(#{1,3})\s+(.*?)\s*#*\s*$')
FENCE = re.compile(r'^\s*(```|~~~)')
SPAN = re.compile(r'(`+)(.+?)\1')
DEPENDS = re.compile(r'\((?:depends on|after)\s+([^)]*)\)', re.I)
TASK_ID = re.compile(r'\bT\d+\b')


def _blank_spans(text):
    return SPAN.sub(lambda m: ' ' * len(m.group(0)), text)


# ---- workstream legend ------------------------------------------------------------------------------------------------
# A workstream tag is a bracket tag a tasks.md legend declares as a lane or workstream: a table row whose first cell holds
# the tags (`[A]` / `[B]`) and whose second cell says "lane" or "workstream", or a bold `**Workstream A**` mention.
# Role markers, `[P]` and phase headings never qualify, even when a legend row names them.
ROLE_TAGS = frozenset(('IMPL', 'QA', 'DOCS', 'COLLECT', 'REVIEW', 'P', 'TDD', 'US'))
TAG = re.compile(r'\[([A-Za-z0-9]{1,12})\]')
LEGEND_ROW = re.compile(r'^\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|?\s*$')
LEGEND_FIRST_CELL = re.compile(r'[\s`/,]*(?:\[[A-Za-z0-9]{1,12}\][\s`/,]*)+')
BOLD_WORKSTREAM = re.compile(r'\*\*(?:Workstream|Lane)\s+([A-Za-z0-9]{1,12})\*\*', re.I)
LEADING_TAGS = re.compile(r'^(?:\s*\[[^\]]*\])+')


def _workstream_tag(tag):
    return tag.upper() not in ROLE_TAGS and not re.fullmatch(r'US\d+', tag.upper())


def legend(text):
    """{tag: {'label': 'Workstream A', 'description': str|None}} for the workstream tags a tasks.md legend declares."""
    found, fence = {}, None
    for line in text.splitlines():
        marker = FENCE.match(line)
        if marker:
            fence = None if fence == marker.group(1) else (fence or marker.group(1))
            continue
        if fence:
            continue
        row = LEGEND_ROW.match(line)
        if row and LEGEND_FIRST_CELL.fullmatch(row.group(1)) and re.search(r'\b(?:lane|workstream)s?\b', row.group(2), re.I):
            for tag in TAG.findall(row.group(1)):
                if _workstream_tag(tag):
                    detail = re.search(r'\*\*' + re.escape(tag) + r'\*\*\s+([^;.|]+)', row.group(2))
                    found.setdefault(tag, {'label': f'Workstream {tag}', 'description': clean(detail.group(1), 100) if detail else None})
        for tag in BOLD_WORKSTREAM.findall(line):
            if _workstream_tag(tag):
                found.setdefault(tag, {'label': f'Workstream {tag}', 'description': None})
    return found


def parse(text):
    """Return {'title': str|None, 'tasks': [ordered task dicts], 'legend': {tag: {...}}}. Each task carries `tags` (the
    leading bracket tags as written) and `workstream` (the one legend tag among them, else None)."""
    tasks, seen, phase, title, fence = [], set(), None, None, None
    declared = legend(text)
    for line in text.splitlines():
        marker = FENCE.match(line)
        if marker:
            fence = None if fence == marker.group(1) else (fence or marker.group(1))
            continue
        if fence:
            continue
        heading = HEADING.match(line)
        if heading:
            if len(heading.group(1)) == 1 and title is None:
                title = clean(heading.group(2), 160)
            elif len(heading.group(1)) > 1:
                phase = clean(heading.group(2), 120)
            continue
        found = TASK.match(line)
        if not found or found.group(2) in seen:
            continue
        seen.add(found.group(2))
        body = found.group(3)
        bare = _blank_spans(body)
        depends = []
        for match in DEPENDS.finditer(bare):
            depends += [t for t in TASK_ID.findall(match.group(1)) if t not in depends and t != found.group(2)]
        parallel = bool(re.search(r'(?<![\w`])\[P\](?![\w`])', bare))
        shown = re.sub(r'\(\s*(?:depends on|after)\s+[^)]*\)', '', body, flags=re.I)
        shown = re.sub(r'(?<![\w`])\[P\](?![\w`])', '', shown)
        lead = LEADING_TAGS.match(body)
        tags = TAG.findall(lead.group(0)) if lead else []
        mine = [t for t in tags if t in declared]
        tasks.append({'id': found.group(2), 'title': clean(shown, 160), 'phase': phase or '',
                      'done': found.group(1) != ' ', 'parallel': parallel, 'depends_on': depends,
                      'tags': tags, 'workstream': mine[0] if len(mine) == 1 else None})
    return {'title': title, 'tasks': tasks, 'legend': declared}


def _text(raw):
    """Decode like Path.read_text: UTF-8 with universal newlines."""
    return raw.decode('utf-8').replace(CRLF, LF).replace(CR, LF)


def collect(feature_dir):
    path = Path(feature_dir) / 'tasks.md'
    try:
        return parse(_text(read_bytes(path)))
    except OSError:
        return {'title': None, 'tasks': [], 'legend': {}}


def expand(spec):
    """`T001-T004,T009` -> ['T001','T002','T003','T004','T009']; raises ValueError on bad input. Any id prefix works
    (`P001-P003`, `US1-3`); a range keeps one prefix and the width of its first number."""
    out = []
    for part in [p.strip() for p in str(spec).split(',') if p.strip()]:
        match = re.fullmatch(r'([A-Za-z]{1,3}-?)(\d+)(?:\s*-\s*(?:\1)?(\d+))?', part, re.I)
        if not match:
            raise ValueError(part)
        prefix = match.group(1).upper()
        low, high = int(match.group(2)), int(match.group(3) or match.group(2))
        if high < low or high - low > 500:
            raise ValueError(part)
        width = len(match.group(2))
        out += [f'{prefix}{n:0{width}d}' for n in range(low, high + 1) if f'{prefix}{n:0{width}d}' not in out]
    return out
