"""Small shared helpers: time, atomic writes, text sanitising, tolerant JSON, bounded diagnostics log."""
import json
import os
import re
import stat
import time
from datetime import datetime, timezone
from pathlib import Path

CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f  ]')
DIAG_LIMIT = 256 * 1024
REPLACE_ATTEMPTS = 8  # os.replace can hit a sharing violation on Windows while a reader has the target open
LINK_TAGS = (0xA000000C, 0xA0000003)  # Windows symlink and junction (mount point) reparse tags


class ProgressError(Exception):
    def __init__(self, code, message='', exit_code=2):
        super().__init__(code)
        self.code, self.message, self.exit_code = code, message, exit_code

    def line(self):
        return f'progress: error {self.code}' + (f' {self.message}' if self.message else '')


def is_link(path):
    """True for a symbolic link or a Windows junction. Other reparse points (cloud placeholders) are ordinary files."""
    try:
        info = os.lstat(str(path))
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, 'st_file_attributes', 0) & 0x400) and getattr(info, 'st_reparse_tag', 0) in LINK_TAGS


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


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    refuse_link(path)
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
