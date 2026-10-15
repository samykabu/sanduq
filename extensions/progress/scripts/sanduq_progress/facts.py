"""facts.jsonl: append-only facts that no producer records (progress.facts.v1)."""
import json
import os
import re
from pathlib import Path

from .paths import ProgressError
from .util import clean, iso, utcnow

PREFIX = {'lane': 'L', 'block': 'B', 'decision': 'D', 'note': 'N'}
TEXT_CAP = 200
SECRET = re.compile(r'(sk-[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|'
                    r'(?i:bearer\s+[A-Za-z0-9._-]{16,})|(?i:(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S{6,}))')
ABSOLUTE = re.compile(r'(?<![\w:/.\\])(?:[A-Za-z]:[\\/]|/(?:home|Users|etc|var|tmp|opt|root|mnt|usr|private)/)\S*')


def sanitise(text, root, cap=TEXT_CAP):
    """Cap and strip free text; refuse secrets and absolute paths outside the repository."""
    value = clean(text, cap)
    if SECRET.search(value):
        raise ProgressError('PROGRESS_FORBIDDEN_CONTENT', 'looks like a secret', 3)
    root_text = Path(root).as_posix().lower()
    for match in ABSOLUTE.finditer(value):
        if not match.group(0).replace('\\', '/').lower().startswith(root_text):
            raise ProgressError('PROGRESS_FORBIDDEN_CONTENT', 'absolute path outside the repository', 3)
    return value


def read_lines(path):
    """Return (records, torn, corrupt). A torn final line is skipped, not an error."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return [], False, 0
    records, corrupt, torn = [], 0, False
    chunks = raw.split(b'\n')
    tail = chunks.pop()  # empty when the file ends with a newline
    for chunk in chunks:
        if not chunk.strip():
            continue
        try:
            item = json.loads(chunk.decode('utf-8'))
        except ValueError:
            corrupt += 1
            continue
        if isinstance(item, dict) and item.get('id') and item.get('kind'):
            records.append(item)
        else:
            corrupt += 1
    if tail.strip():
        try:
            item = json.loads(tail.decode('utf-8'))
            if isinstance(item, dict) and item.get('id') and item.get('kind'):
                records.append(item)
            else:
                torn = True
        except ValueError:
            torn = True
    return records, torn, corrupt


def reduce(records):
    """Latest record per id, in order of first appearance."""
    latest = {}
    for item in records:
        latest[item['id']] = item
    return list(latest.values())


def load(path):
    records, torn, corrupt = read_lines(path)
    return {'all': records, 'current': reduce(records), 'torn': torn, 'corrupt': corrupt}


def next_id(records, kind):
    prefix = PREFIX[kind]
    top = 0
    for item in records:
        match = re.fullmatch(prefix + r'(\d+)', str(item.get('id')))
        if match:
            top = max(top, int(match.group(1)))
    return f'{prefix}{top + 1}'


def append(path, record):
    """Append one record with flush+fsync. The caller holds the feature lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n'
    prefix = b''
    if path.exists() and path.stat().st_size:
        with open(path, 'rb') as stream:
            stream.seek(-1, os.SEEK_END)
            if stream.read(1) != b'\n':
                prefix = b'\n'  # end a torn line so the new record starts clean
    with open(path, 'ab') as stream:
        stream.write(prefix + line.encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())
    return record


def make(kind, ident, actor, source='cli', now=None, **fields):
    return {'v': 1, 'ts': iso(now or utcnow()), 'kind': kind, 'id': ident, 'actor': actor, 'source': source, **fields}
