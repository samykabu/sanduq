#!/usr/bin/env python3
"""Fast hook entry: `hook.py <event>` with the host JSON on stdin.

A hook runs on every tool call of every session, so this file imports only the standard library and decides cheaply
whether the event can matter. An event from a session that is not bound (or from a project where Progress was never
initialised) exits here, before the Progress modules are imported; everything else is handed to
`sanduq_progress.hook.handle`. It never prints, never raises and always exits 0."""
import os
import sys
import time

PARENT_KEYS = ('parent_session_id', 'parent_thread_id', 'forked_from_session_id', 'forked_from_id')


def find_root():
    override = os.environ.get('SANDUQ_PROGRESS_ROOT')
    if override:
        return os.path.realpath(override)
    here = os.path.realpath(os.getcwd())
    for marker in ('.specify', '.git', '.progress'):
        folder = here
        while True:
            if os.path.exists(os.path.join(folder, marker)):
                return folder
            parent = os.path.dirname(folder)
            if parent == folder:
                break
            folder = parent
    return here


def project_dir(root):
    """Same rule as sanduq_progress.paths.project_dir: an existing home wins; else .specify/progress when the project has
    Spec Kit, .progress/.project otherwise."""
    for candidate in (('.specify', 'progress'), ('.progress', '.project')):
        folder = os.path.join(root, *candidate)
        if os.path.isdir(folder):
            return folder
    return os.path.join(root, '.specify', 'progress') if os.path.isdir(os.path.join(root, '.specify')) else os.path.join(root, '.progress', '.project')


def load(path):
    import json
    try:
        with open(path, encoding='utf-8') as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def detect_host(payload):
    """Same rule as sanduq_progress.hosts.detect_host: explicit Codex markers win, Claude is the default."""
    path = str(payload.get('transcript_path') or '').replace(chr(92), '/')
    codex = 'turn_id' in payload or '/.codex/' in path or 'rollout-' in path or (
        os.environ.get('CODEX_HOME') and 'permission_mode' not in payload)
    return 'codex' if codex else 'claude'


def log_unbound_once(progress_dir, payload, now):
    """One line per unbound session id, same text as sanduq_progress.hook; skipped when the log already holds it. The
    append goes through the shared link-refusing, size-bounded writer (`sanduq_progress.safelog`, standard library only)."""
    path = os.path.join(progress_dir, 'diagnostics.log')
    session = ''.join(ch if ch.isprintable() else ' ' for ch in str(payload['session_id'])).strip()[:80]
    message = f'unbound {detect_host(payload)} session {session} dropped'
    try:
        with open(path, encoding='utf-8', errors='replace') as stream:
            if message in stream.read():
                return
    except OSError:
        pass
    try:
        import importlib.util  # by path: importing the package (even its __init__) is what this entry avoids
        spec = importlib.util.spec_from_file_location(
            'safelog', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sanduq_progress', 'safelog.py'))
        safelog = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(safelog)
        safelog.append_line(path, f'{safelog.stamp(now)} {message}')
    except OSError:
        pass


SAFE_ID = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-')


def read_text(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as stream:
            return stream.read()
    except OSError:
        return ''


def quick_unbound(root, event, raw):
    """True when the event is provably ignorable using only string tests, so not even `json` (which pulls in `re`) is
    imported: Progress was never initialised here, or the payload opens with a plain session_id that no binding
    names, no handshake is pending for it and its drop is already logged. Anything unusual returns False."""
    progress_dir = project_dir(root)
    if not os.path.isdir(progress_dir):
        return True
    head = raw.lstrip()
    if not head.startswith('{"session_id"') or any(key in raw for key in PARENT_KEYS):
        return False
    rest = head[len('{"session_id"'):].lstrip()
    if not rest.startswith(':'):
        return False
    rest = rest[1:].lstrip()
    if not rest.startswith('"'):
        return False
    sid = rest[1:rest.find('"', 1)] if rest.find('"', 1) > 0 else ''
    if not sid or len(sid) > 80 or not set(sid) <= SAFE_ID:
        return False
    bindings = read_text(os.path.join(progress_dir, 'bindings.json'))
    if f':{sid}"' in bindings:
        return False  # bound under some host (or a child of it): take the full path
    if '"nonce"' in bindings and event.replace('-', '_').lower() in ('post_tool_use', 'posttooluse'):
        return False  # a bind handshake may be waiting for this tool call
    log = read_text(os.path.join(progress_dir, 'diagnostics.log'))
    return f' session {sid} dropped' in log


def relevant(root, event, payload):
    """False when the event provably cannot attach to a binding (no state, no bound session, no pending handshake)."""
    progress_dir = project_dir(root)
    if not os.path.isdir(progress_dir):
        return False
    bindings = load(os.path.join(progress_dir, 'bindings.json'))
    sessions = bindings.get('sessions') if isinstance(bindings.get('sessions'), dict) else {}
    ids = {str(payload.get(k)) for k in ('session_id',) + PARENT_KEYS if payload.get(k)}
    if any(f'{host}:{sid}' in sessions for sid in ids for host in ('claude', 'codex')):
        return True
    if event.replace('-', '_').lower() in ('post_tool_use', 'posttooluse') and bindings.get('pending'):
        return True  # the bind handshake: a tool call that carries the nonce converts a pending bind
    if payload.get('session_id'):
        log_unbound_once(progress_dir, payload, time.time())
    return False


EVENTS = ('session_start', 'pre_tool_use', 'post_tool_use', 'stop', 'session_end')


def sniff_event(raw):
    """The payload's `hook_event_name` as the snake_case event, '' when absent or unknown. Spec Kit's dispatcher runs the
    hook without an event argument; only the fast path needs the name (`handle` derives it itself). String tests only."""
    _, found, tail = raw.partition('"hook_event_name"')
    name = tail.split('"', 2)[1] if found and tail.count('"') >= 2 else ''
    name = ''.join('_' + c.lower() if c.isupper() and i else c.lower() for i, c in enumerate(name)).replace('-', '_')
    return name if name in EVENTS else ''


def main(argv):
    event = argv[1] if len(argv) > 1 else ''
    raw = '' if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
    event = event or sniff_event(raw)
    root = find_root()
    if quick_unbound(root, event, raw):
        return 0
    import json
    try:
        payload = json.loads(raw) if raw.strip() else None
    except ValueError:
        payload = None
    if isinstance(payload, dict) and payload.get('session_id') and not relevant(root, event, payload):
        return 0
    # empty or malformed payloads, bound sessions and pending handshakes take the full path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sanduq_progress import hook
    hook.handle(event, raw, root=root)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv))
    except BaseException:  # the host must never see a failure from an automatic hook
        sys.exit(0)
