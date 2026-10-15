"""tasks.md collector. tasks.md owns task text and checkbox state; Progress only reads it.

Recognised: `- [ ] T001 [P] Title (depends on T000, T002)` and `(after T001)`. Headings of level 2 or 3 name the
phase. Fenced blocks and inline code spans are ignored, so task ids quoted in prose never create tasks or edges.
"""
import re
from pathlib import Path

from ..util import clean

TASK = re.compile(r'^\s*[-*]\s+\[([ xX])\]\s+(T\d+)\b\s*(.*)$')
HEADING = re.compile(r'^(#{1,3})\s+(.*?)\s*#*\s*$')
FENCE = re.compile(r'^\s*(```|~~~)')
SPAN = re.compile(r'(`+)(.+?)\1')
DEPENDS = re.compile(r'\((?:depends on|after)\s+([^)]*)\)', re.I)
TASK_ID = re.compile(r'\bT\d+\b')


def _blank_spans(text):
    return SPAN.sub(lambda m: ' ' * len(m.group(0)), text)


def parse(text):
    """Return {'title': str|None, 'tasks': [ordered task dicts]}."""
    tasks, seen, phase, title, fence = [], set(), None, None, None
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
        tasks.append({'id': found.group(2), 'title': clean(shown, 160), 'phase': phase or '',
                      'done': found.group(1) != ' ', 'parallel': parallel, 'depends_on': depends})
    return {'title': title, 'tasks': tasks}


def collect(feature_dir):
    path = Path(feature_dir) / 'tasks.md'
    try:
        return parse(path.read_text(encoding='utf-8'))
    except OSError:
        return {'title': None, 'tasks': []}


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
