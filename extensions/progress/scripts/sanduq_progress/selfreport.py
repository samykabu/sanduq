"""Coordinator self-report: `progress bind --host H --model M --effort E` stores what the coordinator says about itself in
`<progress dir>/.host/self-report.json`. The file is durable (it is not under the disposable `.view`) and git-ignored.

A self-report is scoped to the feature and worktree it was written in, and to one session, or to an explicit
"session unknown" binding (`session_id: null`). Host observations (hooks, statusline) always win per field; a
self-report only fills a field the host did not observe, and the projection labels it `self-report`."""
import os

from .util import clean, iso, parse_time, read_json, write_json

FIELDS = ('model', 'effort')


def path_of(ctx):
    return ctx.host_dir / 'self-report.json'


def _same(a, b):
    try:
        return os.path.normcase(os.path.realpath(str(a))) == os.path.normcase(os.path.realpath(str(b)))
    except OSError:
        return False


def write(ctx, host, session_id, values, now, actor='agent:coordinator'):
    """Merge `values` ({'model':..,'effort':..}, None entries ignored) into the stored report. A different session
    replaces the report; the same session keeps the fields this call does not restate. Returns the stored document."""
    current = read(ctx, any_session=True) or {}
    keep = current.get('fields', {}) if current.get('host') == host and current.get('session_id') == session_id else {}
    fields = dict(keep)
    for name in FIELDS:
        if values.get(name):
            fields[name] = {'value': clean(values[name], 80), 'at': iso(now)}
    doc = {'v': 1, 'feature': ctx.feature, 'worktree': str(ctx.root), 'host': host, 'session_id': session_id,
           'actor': actor, 'fields': fields}
    write_json(path_of(ctx), doc)
    return doc


def read(ctx, any_session=False):
    """The stored self-report when it belongs to this feature and worktree, else None."""
    doc = read_json(path_of(ctx), None)
    if not isinstance(doc, dict) or doc.get('v') != 1 or doc.get('feature') != ctx.feature or not _same(doc.get('worktree') or '', ctx.root):
        return None
    if not isinstance(doc.get('fields'), dict):
        return None
    return doc


def applicable(doc, main_session_id):
    """Fields that apply to the orchestrating session: a self-report bound to a session applies only when the observed main session equals it (a missing or unreadable host
    snapshot, so no observed session, does not apply it); a
    session-unknown report applies to whichever session the host bound."""
    if not doc:
        return {}
    session = doc.get('session_id')
    if session is not None and session != main_session_id:  # no observed main session means a bound report cannot be shown to match
        return {}
    return {name: f for name, f in doc['fields'].items()
            if name in FIELDS and isinstance(f, dict) and isinstance(f.get('value'), str) and parse_time(f.get('at'))}
