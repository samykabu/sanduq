"""Host snapshots (progress.host.v1) and the explicit binding handshake.

Snapshots merge field by field under the feature lock: an update replaces only the fields it carries and never
a newer observation. Bindings live in <project dir>/bindings.json (.specify/progress, or .progress/.project without Spec Kit) under their own small lock:

    {"pending": [{feature, worktree, nonce, created_at}],
     "sessions": {"<host>:<session_id>": {session_id, host, feature, worktree, bound_at}}}
"""
import json
import os
from datetime import timedelta
from pathlib import Path

from .hosts import session_key
from .lock import Lock
from .paths import project_dir
from .util import iso, parse_time, read_json, write_json

MEASURED = ('model', 'effort', 'context', 'elapsed_ms', 'api_ms')
TERMINAL = ('done', 'failed')
BIND_TTL = timedelta(seconds=120)


def _unsafe_legacy(ctx, legacy):
    """True when the legacy directory (or an entry in it) is a link or resolves outside the feature's progress dir."""
    from .util import is_link
    try:
        if is_link(legacy) or is_link(ctx.view) or is_link(ctx.dir):
            return True
        base = Path(os.path.realpath(str(ctx.dir)))
        if base not in Path(os.path.realpath(str(legacy))).parents:
            return True
        with os.scandir(legacy) as entries:
            return any(is_link(entry.path) or base not in Path(os.path.realpath(entry.path)).parents for entry in entries)
    except OSError:
        return True


def migrate_host_dir(ctx):
    """Host snapshots used to live under the disposable `.view/host`. Move them to the durable `.host` once. Caller holds
    the feature lock. Returns True when nothing is left to migrate; False means the migration is pending (a linked
    source, or a failed move) and the caller must not create a fresh snapshot, so a child never loses its identity."""
    legacy = ctx.view / 'host'
    if not os.path.lexists(legacy):
        return True
    from .util import diag, is_link
    if is_link(ctx.host_dir) or _unsafe_legacy(ctx, legacy):
        diag(ctx.diag, 'host snapshot migration skipped: .view/host or .host is a link or outside the progress directory')
        return False
    try:
        if not legacy.is_dir():
            return True
        if not os.path.lexists(ctx.host_dir):
            os.replace(legacy, ctx.host_dir)  # one atomic rename: no state with half the history in each place
        else:
            for path in sorted(legacy.iterdir()):
                target = ctx.host_dir / path.name
                if os.path.lexists(target):
                    target = ctx.host_dir / ('legacy-' + path.name)
                    n = 1
                    while os.path.lexists(target):
                        n += 1
                        target = ctx.host_dir / f'legacy-{n}-{path.name}'
                os.replace(path, target)
            legacy.rmdir()
    except OSError as exc:
        diag(ctx.diag, f'host snapshot migration pending: {type(exc).__name__}')
        return False
    from .paths import git_exclude
    from .util import ensure_local_dir
    try:
        ensure_local_dir(ctx.host_dir)  # the moved directory keeps a nested .gitignore
    except Exception as exc:
        diag(ctx.diag, f'host snapshot migration pending: nested .gitignore not written ({type(exc).__name__})')
        return False
    git_exclude(ctx.root)  # the new directory must be ignored even if `init` is not re-run after an upgrade
    return True


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
                 generation=int(entry.get('generation') or 1) + 1, status_at=update['last_observed_at'])


def _stale_lifecycle(entry, update):
    """A lifecycle observation (status with its start and end times) older than the entry's last accepted lifecycle
    observation describes an earlier moment: a delayed `done` must not end a generation that started after it."""
    at = update.get('last_observed_at') or ''
    return bool(update.get('status') is not None and at and at < (entry.get('status_at') or ''))


def _gate(entry, update):
    """Apply the lifecycle freshness rule to `update` (mutated): a stale lifecycle is dropped, a newer running
    observation after a terminal one starts a new generation. Used for every way an observation reaches an entry."""
    if _stale_lifecycle(entry, update):
        for name in ('status', 'started_at', 'ended_at'):
            update.pop(name, None)
    elif _restarts(entry, update):
        _restart(entry, update)
        update.pop('status'), update.pop('started_at', None)


def _absorb_lifecycle(entry, old):
    """The lifecycle of another record of the same child (linking two ids) is one more observation, stamped with when
    that record's lifecycle was last accepted, and goes through the same freshness rule."""
    update = {n: old[n] for n in ('status', 'started_at', 'ended_at') if old.get(n) is not None}
    update['last_observed_at'] = old.get('status_at') or old.get('last_observed_at') or ''
    _gate(entry, update)
    if 'status' in update:
        _apply(entry, 'status', update['status'])
        if entry.get('status') == update['status'] and update.get('ended_at'):
            entry['ended_at'] = max(entry.get('ended_at') or '', update['ended_at'])
    if update.get('started_at') and not entry.get('started_at'):
        entry['started_at'] = update['started_at']
    if old.get('generation'):
        entry['generation'] = max(int(entry.get('generation') or 1), int(old['generation']))
    entry['status_at'] = max(entry.get('status_at') or '', old.get('status_at') or '') or None


def _numbers(entry):
    return [n for n in [entry.get('lane_no'), *(entry.get('lane_aliases') or [])] if isinstance(n, int) and not isinstance(n, bool)]


def _next_lane_no(ctx, snap):
    """The next `C<n>` number: one above every number any host snapshot ever held, retired aliases included, so a number is
    never reused. The numbers live in the host snapshots (durable host data), not in the disposable view."""
    top = max((n for child in (snap.get('children') or {}).values() for n in _numbers(child)), default=0)
    for other in read_all(ctx):
        top = max([top] + [n for child in (other.get('children') or {}).values() for n in _numbers(child)])
    return top + 1


def _join_numbers(entry, other):
    """Two entries turn out to be one child: the lowest number stays its lane id and the others become aliases that
    still resolve, so a blocker recorded against a retired number keeps its meaning."""
    numbers = sorted(set(_numbers(entry)) | set(_numbers(other)))
    if numbers:
        entry['lane_no'] = numbers[0]
        if numbers[1:]:
            entry['lane_aliases'] = numbers[1:]


def _provisional_target(children):
    """The one running tool-launched child (no agent id yet) that an agent-keyed event can belong to, or None."""
    open_launches = [k for k, v in children.items()
                     if not v.get('agent_id') and v.get('kind') == 'subagent' and v.get('status') == 'running']
    return open_launches[0] if len(open_launches) == 1 else None


def _split_provisional(ctx, snap, entry, real_id):
    """The tool result names another agent than the one provisionally attached: the attached agent was a different
    child. It gets its own entry (with the observations that came from it); the launch keeps the id the host reported."""
    children, guessed = snap['children'], entry.get('agent_id')
    moved = {name: entry.pop(name) for name in ('model', 'effort')
             if isinstance(entry.get(name), dict) and entry[name].get('fidelity') != 'partial'}
    children[guessed] = {**moved, 'kind': 'subagent', 'agent_id': guessed, 'status': entry.get('status') or 'running',
                         'started_at': entry.get('started_at'), 'ended_at': entry.get('ended_at'),
                         'last_observed_at': entry.get('last_observed_at'), 'status_at': entry.get('status_at'),
                         'lane_no': _next_lane_no(ctx, snap)}
    if entry.get('generation'):
        children[guessed]['generation'] = entry['generation']
    if entry.get('status') in TERMINAL:  # that end belonged to the attached agent, not to the launch
        entry.update(status='running', ended_at=None, status_at=None)
        entry.pop('generation', None)
    entry.pop('agent_link', None)
    entry['agent_id'] = real_id


def merge(ctx, host, session_id, now, fields=None, child=None, parent_session_id=None, agent_id=None):
    """Merge one observation into the session snapshot. Caller holds the feature lock. Returns True if changed."""
    if not migrate_host_dir(ctx):
        return False  # migration pending: write nothing now, retry on the next event
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
        provisional = False
        # A child launched by a tool call (keyed by tool_use_id) is later seen by its own agent id: merge them.
        if child.get('by_agent') and key not in children:
            linked = next((k for k, v in children.items() if v.get('agent_id') == key), None)
            if linked is None:
                # The host reports a running subagent under two ids (the launching tool call, then its own agent id)
                # before the tool result names the agent. With exactly one open launch the two are the same child;
                # the tool result confirms the link or splits it.
                linked = _provisional_target(children)
                provisional = linked is not None
            key = linked or key
        elif update.get('agent_id'):
            # The tool result names the agent. A provisional association is reconciled first (confirmed, or split off
            # as its own child), so merging a record of the named agent can never overwrite another running child.
            attached = children.get(key) or {}
            if attached.get('agent_link') == 'provisional':
                if attached.get('agent_id') == update['agent_id']:
                    attached.pop('agent_link')
                else:
                    _split_provisional(ctx, snap, attached, update['agent_id'])
            if update['agent_id'] in children and update['agent_id'] != key:
                old = children.pop(update['agent_id'])
                entry = children.setdefault(key, {})
                for name, value in old.items():
                    if name in ('model', 'effort', 'last_observed_at'):
                        _apply(entry, name, value)
                    elif name in ('status', 'started_at', 'ended_at', 'generation', 'lane_no', 'lane_aliases', 'agent_link', 'status_at'):
                        continue
                    elif value is not None:
                        entry.setdefault(name, value)  # the tool-call record keeps its own description and type
                _absorb_lifecycle(entry, old)
                _join_numbers(entry, old)
        entry = children.setdefault(key, {})
        if not isinstance(entry.get('lane_no'), int):
            entry['lane_no'] = _next_lane_no(ctx, snap)
        if child.get('by_agent') and not entry.get('agent_id'):
            entry['agent_id'] = child['key']
            if provisional:
                entry['agent_link'] = 'provisional'
        _gate(entry, update)
        for name, value in update.items():
            _apply(entry, name, value)
        if update.get('status') is not None and entry.get('status') == update['status'] and update.get('last_observed_at'):
            entry['status_at'] = max(entry.get('status_at') or '', update['last_observed_at'])
        entry.setdefault('ended_at', None)
        entry.setdefault('started_at', None)
        entry.setdefault('status', 'unknown')
    snap['last_observed_at'] = iso(now)
    changed = json.dumps(snap, sort_keys=True) != before
    if changed:
        write_json(path, snap)
    return changed


def read_all(ctx):
    """Read-only: never migrates. A legacy `.view/host` that is safe to read and not yet migrated is read as well."""
    out, seen = [], set()
    legacy = ctx.view / 'host'
    folders = [ctx.host_dir]
    if os.path.lexists(legacy) and legacy.is_dir() and not _unsafe_legacy(ctx, legacy):
        folders.append(legacy)
    for folder in folders:
        if folder.is_dir():
            for path in sorted(folder.glob('*.json')):
                if path.name in seen:
                    continue
                seen.add(path.name)
                data = read_json(path)
                if not (isinstance(data, dict) and data.get('session_id')):
                    continue
                # A conflict kept as `legacy-<name>` holds the same session as the current file, which sorts first.
                key = (data.get('host'), data.get('session_id'))
                if key in seen:
                    continue
                seen.add(key)
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
    data = _load(project_dir(root) / 'bindings.json')
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
    path = project_dir(root) / 'bindings.json'
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
