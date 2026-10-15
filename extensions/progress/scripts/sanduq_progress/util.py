"""Small shared helpers: time, atomic writes, text sanitising, tolerant JSON, bounded diagnostics log."""
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f  ]')
DIAG_LIMIT = 256 * 1024


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
    fd, name = tempfile.mkstemp(dir=str(path.parent), suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data.encode('utf-8') if isinstance(data, str) else data)
        os.replace(name, path)
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
