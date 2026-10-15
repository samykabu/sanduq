"""Refresh engine: state.json cursors, debounce and dirty logic, and the projection write.
All functions expect the caller to hold the feature lock."""
import time

from . import model, render_data
from .util import iso, read_json, utcnow, write_json


def read_state(ctx):
    data = read_json(ctx.state, {})
    return data if isinstance(data, dict) else {}


def refresh(ctx, now=None, final=False):
    now = now or utcnow()
    state = read_state(ctx)
    state['rev'] = int(state.get('rev') or 0) + 1
    state['dirty'] = False
    state.setdefault('started_at', iso(now))
    report = model.build(ctx, now, state['rev'], state)
    render_data.write(ctx, report)
    state['last_refresh_ts'] = time.time()
    state['last_refresh_at'] = iso(now)
    if final:
        state['final_at'] = iso(now)
    write_json(ctx.state, state)
    return report


def after_update(ctx, now, force=False):
    """Debounced refresh after an observation. Returns True when it refreshed, False when it only marked dirty."""
    state = read_state(ctx)
    state['last_event_at'] = iso(now)
    debounce = float(ctx.config_data().get('debounce_seconds') or 0)
    if force or time.time() - float(state.get('last_refresh_ts') or 0) >= debounce:
        write_json(ctx.state, state)
        refresh(ctx, now, final=force)
        return True
    state['dirty'] = True
    publish_pending(ctx, state)
    write_json(ctx.state, state)
    return False


def publish_pending(ctx, state):
    """Feed the browser while a refresh is deferred. data.js is the UI's only input, so the dirty flag and the last event
    time are patched into the current document (cheap: no producers are read, nothing is rebuilt) and `rev` advances so
    the poller accepts it. The next real refresh replaces it and clears the flag. Best effort."""
    try:
        report = read_json(ctx.report)
        if not isinstance(report, dict) or not isinstance(report.get('collection'), dict):
            return False
        state['rev'] = max(int(state.get('rev') or 0), int(report.get('rev') or 0)) + 1
        report['rev'] = state['rev']
        report['collection'].update(dirty=True, last_event_at=state.get('last_event_at'))
        render_data.write(ctx, report)
        return True
    except (OSError, ValueError, TypeError):
        return False


def count_dropped(ctx, reason, now=None):
    state = read_state(ctx)
    state['dropped'] = int(state.get('dropped') or 0) + 1
    write_json(ctx.state, state)
