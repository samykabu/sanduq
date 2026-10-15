"""Small shared helpers: time, atomic writes, text sanitising, tolerant JSON, bounded diagnostics log."""
import json
import os
import re
import stat
import time
from datetime import datetime, timezone
from pathlib import Path

from . import safelog  # standard library only; the fast hook entry loads the same file by path

CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f  ]')
DIAG_LIMIT = safelog.DIAG_LIMIT
REPLACE_ATTEMPTS = 8  # os.replace can hit a sharing violation on Windows while a reader has the target open


class ProgressError(Exception):
    def __init__(self, code, message='', exit_code=2):
        super().__init__(code)
        self.code, self.message, self.exit_code = code, message, exit_code

    def line(self):
        return f'progress: error {self.code}' + (f' {self.message}' if self.message else '')


is_link = safelog.is_link


def refuse_link(path):
    """Raise before a write goes through a symlink or reparse point (the target could lie outside the repository)."""
    if is_link(path):
        raise ProgressError('PROGRESS_UNSAFE_TARGET', f'{Path(path).name} is a symlink or reparse point; refusing to write', 3)


def utcnow():
    return datetime.now(timezone.utc)


def iso(moment):
    return moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if moment else None


def parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def clean(value, cap=200):
    """Strip control characters, collapse whitespace and cap the length."""
    text = CONTROL.sub(' ', str(value if value is not None else ''))
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:cap]


LOCAL_DIRS = ('.host', '.view')  # directories that hold only local-only runtime files


def ensure_local_dir(directory):
    """Create a local-only directory with a nested `.gitignore` holding a single `*`. Git applies the closest .gitignore
    first, so a parent rule that re-includes a file (`!claude-*.json`) cannot expose anything inside; the `*` also
    ignores the .gitignore itself. Refuses a link at the directory or the file. Written atomically, only when missing or
    different."""
    directory = Path(directory)
    refuse_link(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / '.gitignore'
    refuse_link(target)
    try:
        if target.read_text(encoding='utf-8').strip() == '*':
            return
    except OSError:
        pass
    _write_atomic(target, '*\n')


def atomic_write(path, data):
    path = Path(path)
    if path.parent.name in LOCAL_DIRS:
        ensure_local_dir(path.parent)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    refuse_link(path)
    _write_atomic(path, data)


def _write_atomic(path, data):
    path = Path(path)
    # tempfile.mkstemp would import shutil, random and more on every hook; an exclusive create is all that is needed
    name = str(path.parent / f'.{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp')
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data.encode('utf-8') if isinstance(data, str) else data)
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                os.replace(name, path)
                break
            except PermissionError:  # a concurrent reader (browser, scanner, another hook) holds the target open
                if attempt == REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(min(0.2, 0.01 * 2 ** attempt))
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    atomic_write(path, json.dumps(value, indent=2, sort_keys=False, ensure_ascii=False) + '\n')


def diag(path, message, now=None):
    """Append one line to a bounded diagnostics log (rotate at 256 KB, keep one). Never raises."""
    try:
        path = Path(path)
        if path.parent.name in LOCAL_DIRS:
            ensure_local_dir(path.parent)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
        refuse_link(path)
        if path.exists() and path.stat().st_size > DIAG_LIMIT:
            os.replace(path, str(path) + '.1')
        with open(path, 'a', encoding='utf-8') as stream:
            stream.write(f'{iso(now or utcnow())} {clean(message, 400)}\n')
    except Exception:
        pass


def count_lines(path):
    try:
        with open(path, 'rb') as stream:
            return sum(1 for _ in stream)
    except OSError:
        return 0


def diag_once(path, message, now=None):
    """Like `diag`, but a message already present in the log is not written again."""
    try:
        if message in Path(path).read_text(encoding='utf-8', errors='replace'):
            return
    except OSError:
        pass
    diag(path, message, now)
