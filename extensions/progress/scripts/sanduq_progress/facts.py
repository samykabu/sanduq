"""facts.jsonl: append-only facts that no producer records (progress.facts.v1)."""
import json
import os
import posixpath
import re
from pathlib import Path

from .util import ProgressError, clean, iso, refuse_link, utcnow

PREFIX = {'lane': 'L', 'block': 'B', 'decision': 'D', 'note': 'N', 'attempt': 'A'}
TEXT_CAP = 200
SECRET = re.compile(r'(sk-[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|'
                    r'(?i:bearer\s+[A-Za-z0-9._-]{16,})|(?i:(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S{6,}))')
ACTOR = re.compile(r'user|hook|legacy|agent:[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
# Absolute-path candidates in free text, on any platform: drive paths, UNC paths and POSIX absolute paths. A slash that
# follows a word character, ':' (URL) or '.' is not the start of a path ("and/or", "https://host/x", "a/b").
# A POSIX candidate needs two segments, so slash commands such as /speckit.tasks stay allowed.
ABSOLUTE = re.compile(r'(?<![\w:/.\\-])(?:[A-Za-z]:[\\/]|\\\\[^\s\\/]|//[^\s\\/]|/(?=[^\s/\\]+/))\S*')
BS = chr(92)  # backslash
TRAILING = ".,;:)]}>'\""


def _is_inside(candidate, root_text):
    """Path-component containment of an absolute candidate beneath the repository root (never a string prefix)."""
    cand = posixpath.normpath(candidate.replace(BS, '/'))
    base = posixpath.normpath(root_text.replace(BS, '/'))
    if re.match(r'[A-Za-z]:', base) or os.name == 'nt':
        cand, base = cand.lower(), base.lower()
    cand_parts, base_parts = cand.split('/'), base.split('/')
    return cand_parts[:len(base_parts)] == base_parts


def scan(text, root):
    """Raise unless `text` is free of secrets and of absolute paths outside the repository."""
    if SECRET.search(text):
        raise ProgressError('PROGRESS_FORBIDDEN_CONTENT', 'looks like a secret', 3)
    root_text = Path(root).as_posix()
    for match in ABSOLUTE.finditer(text):
        token = match.group(0).rstrip(TRAILING)
        flat = token.replace(BS, '/')
        if flat.startswith('//') or not _is_inside(flat, root_text):
            raise ProgressError('PROGRESS_FORBIDDEN_CONTENT', 'absolute path outside the repository', 3)
    return text


def sanitise(text, root, cap=TEXT_CAP):
    """Cap and strip free text; refuse secrets and absolute paths outside the repository."""
    return scan(clean(text, cap), root)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def check(record, root):
    """Validate the whole stored record: a constrained actor, and the secret and path rules on every string it holds."""
    actor = record.get('actor')
    if not isinstance(actor, str) or not ACTOR.fullmatch(actor):
        raise ProgressError('PROGRESS_FORBIDDEN_CONTENT', 'actor must be user, hook, legacy or agent:<id>', 3)
    for text in _strings(record):
        scan(text, root)
    return record


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


def append(path, record, root=None):
    """Append one record with flush+fsync. The caller holds the feature lock. With `root` the whole record is validated
    first (see `check`), so nothing forbidden reaches the tracked file."""
    if root is not None:
        check(record, root)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    refuse_link(path)  # an append through a link would write outside the repository
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
