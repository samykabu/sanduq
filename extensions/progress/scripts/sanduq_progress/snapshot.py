"""Host snapshots (progress.host.v1) and the explicit binding handshake.

Snapshots merge field by field under the feature lock: an update replaces only the fields it carries and never
a newer observation. Bindings live in .specify/progress/bindings.json under their own small lock:

    {"pending": [{feature, worktree, nonce, created_at}],
     "sessions": {"<host>:<session_id>": {session_id, host, feature, worktree, bound_at}}}
"""
import json
import os
from datetime import timedelta
from pathlib import Path

from .hosts import session_key
from .lock import Lock
from .util import iso, parse_time, read_json, write_json

MEASURED = ('model', 'effort', 'context', 'elapsed_ms', 'api_ms')
TERMINAL = ('done', 'failed')
BIND_TTL = timedelta(seconds=120)


def snapshot_path(ctx, host, session_id):
    return ctx.host_dir / (session_key(host, session_id) + '.json')


def _newer(new, old):
    return not old or (new.get('observed_at') or '') >= (old.get('observed_at') or '')


def _apply(entry, name, value):
    """Set one child field. A terminal status is not reopened, an older observation never replaces a newer one, and a
    requested (partial) model never replaces an observed (exact) one, whichever order the two events arrive in."""
    if value is None:
        return
    if name == 'status' and entry.get('status') in TERMINAL and value not in TERMINAL:
        return
    if name == 'last_observed_at' and (entry.get(name) or '') > value:
        return
    if name == 'model' and isinstance(value, dict) and isinstance(entry.get('model'), dict):
        current = entry['model']
        if current.get('fidelity') == 'exact' and value.get('fidelity') != 'exact':
            return
        if (current.get('fidelity') == 'exact') == (value.get('fidelity') == 'exact') and not _newer(value, current):
            return  # an older measurement never replaces a newer one of the same kind
    if name == 'effort' and isinstance(value, dict) and isinstance(entry.get('effort'), dict) and not _newer(value, entry['effort']):
        return
    entry[name] = value


def _restarts(entry, update):
    """A newer running observation after a terminal one is a new attempt generation of the same child (the agent was
    given follow-up work): the end time is cleared and the generation counts up. An observation at or before the end
    time is stale and is rejected by `_apply`."""
    status, at = update.get('status'), update.get('last_observed_at') or ''
    return (entry.get('status') in TERMINAL and status is not None and status not in TERMINAL
            and at > (entry.get('ended_at') or '') and at > '')


def _restart(entry, update):
    entry.update(status=update['status'], ended_at=None, started_at=update.get('started_at') or update['last_observed_at'],
                 generation=int(entry.get('generation') or 1) + 1)


def merge(ctx, host, session_id, now, fields=None, child=None, parent_session_id=None, agent_id=None):
    """Merge one observation into the session snapshot. Caller holds the feature lock. Returns True if changed."""
    path = snapshot_path(ctx, host, session_id)
    snap = read_json(path, None)
    before = json.dumps(snap, sort_keys=True)
    if not isinstance(snap, dict):
        snap = {'v': 1, 'host': host, 'session_id': session_id, 'parent_session_id': parent_session_id,
                'agent_id': agent_id, 'bound_feature': ctx.feature, 'first_seen': iso(now), 'children': {}}
    snap.setdefault('children', {})
    for name, value in (fields or {}).items():
        if name in MEASURED and value and _newer(value, snap.get(name)):
            snap[name] = value
    if child:
        children = snap['children']
        key, update = child['key'], dict(child['update'])
        # A child launched by a tool call (keyed by tool_use_id) is later seen by its own agent id: merge them.
        if child.get('by_agent') and key not in children:
            key = next((k for k, v in children.items() if v.get('agent_id') == key), key)
        elif update.get('agent_id') and update['agent_id'] in children and update['agent_id'] != key:
            old = children.pop(update['agent_id'])
            entry = children.setdefault(key, {})
            if _restarts(entry, old):
                _restart(entry, old)
            for name, value in old.items():
                if name in ('model', 'effort', 'status', 'last_observed_at'):
                    _apply(entry, name, value)
                elif value is not None:
                    entry.setdefault(name, value)  # the tool-call record keeps its own description and type
        entry = children.setdefault(key, {})
        if child.get('by_agent'):
            entry.setdefault('agent_id', child['key'])
        if _restarts(entry, update):
            _restart(entry, update)
            update.pop('status'), update.pop('started_at', None)
        for name, value in update.items():
            _apply(entry, name, value)
        entry.setdefault('ended_at', None)
        entry.setdefault('started_at', None)
        entry.setdefault('status', 'unknown')
    snap['last_observed_at'] = iso(now)
    changed = json.dumps(snap, sort_keys=True) != before
    if changed:
        write_json(path, snap)
    return changed


def read_all(ctx):
    out = []
    if ctx.host_dir.is_dir():
        for path in sorted(ctx.host_dir.glob('*.json')):
            data = read_json(path)
            if isinstance(data, dict) and data.get('session_id'):
                out.append(data)
    return out


# ---- bindings ----------------------------------------------------------------------------------------------

def _load(path):
    data = read_json(path, {})
    data = data if isinstance(data, dict) else {}
    data.setdefault('pending', [])
    data.setdefault('sessions', {})
    return data


def lookup(root, host, session_id):
    data = _load(Path(root) / '.specify' / 'progress' / 'bindings.json')
    return data['sessions'].get(f'{host}:{session_id}')


def create_pending(ctx, now):
    nonce = os.urandom(6).hex()
    with Lock(ctx.bindings_lock):
        data = _load(ctx.bindings)
        data['pending'] = [p for p in data['pending']
                           if (parse_time(p.get('created_at')) or now) + BIND_TTL > now and p.get('feature') != ctx.feature]
        data['pending'].append({'feature': ctx.feature, 'worktree': str(ctx.root), 'nonce': nonce, 'created_at': iso(now)})
        write_json(ctx.bindings, data)
    return nonce


def bind_session(ctx, host, session_id, now):
    with Lock(ctx.bindings_lock):
        data = _load(ctx.bindings)
        data['sessions'][f'{host}:{session_id}'] = {'session_id': session_id, 'host': host, 'feature': ctx.feature,
                                                    'worktree': str(ctx.root), 'bound_at': iso(now)}
        write_json(ctx.bindings, data)


def _inside(path, base):
    try:
        a, b = os.path.normcase(os.path.realpath(str(path))), os.path.normcase(os.path.realpath(str(base)))
        return a == b or a.startswith(b + os.sep)
    except OSError:
        return False


def cwd_valid(binding, cwd):
    """A cwd inside the bound worktree validates a binding; its absence does not invalidate it."""
    return not cwd or _inside(cwd, binding.get('worktree') or '')


def convert_pending(root, obs, now):
    """Turn a pending bind into a session binding when this tool call carries the nonce. Returns the binding or None."""
    path = Path(root) / '.specify' / 'progress' / 'bindings.json'
    if not path.is_file() or not obs.get('session_id'):
        return None
    sent, got = obs.get('tool_input_text', ''), obs.get('tool_response_text', '')
    if 'progress' not in sent:
        return None
    with Lock(path.with_name('bindings.lock')):
        data = _load(path)
        live = [p for p in data['pending'] if (parse_time(p.get('created_at')) or now) + BIND_TTL > now]
        hit = next((p for p in live if p['nonce'] in got or (p['nonce'] in sent and ('bind' in sent or 'init' in sent))), None)
        if hit is None or not cwd_valid(hit, obs.get('cwd')):
            if len(live) != len(data['pending']):
                data['pending'] = live
                write_json(path, data)
            return None
        data['pending'] = [p for p in live if p is not hit]
        binding = {'session_id': obs['session_id'], 'host': obs['host'], 'feature': hit['feature'],
                   'worktree': hit['worktree'], 'bound_at': iso(now)}
        data['sessions'][f"{obs['host']}:{obs['session_id']}"] = binding
        write_json(path, data)
        return binding
