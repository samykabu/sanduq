"""`progress hook <event>`: the single entry the host's event dispatcher calls.

Never prints, never raises, always exits 0. Observations attach only to a bound session (or a child whose
parent is verified from the payload); everything else is dropped. A project where Progress was never initialised
(no project directory) gets nothing written; elsewhere an unbound session is logged once per session id."""
import json
import os
from pathlib import Path

from . import refresh as refreshlib, snapshot
from .hosts import claude, codex, detect_host, normalise_event
from .lock import Lock, LockBusy
from .paths import Ctx, find_root, project_dir
from .util import clean, diag, diag_once, utcnow

ROLLOUT_EVENTS = ('session_start', 'user_prompt_submit', 'stop', 'session_end')
FORCE_EVENTS = ('stop', 'session_end')


def handle(event_arg, raw, root=None, now=None, host=None):
    """Process one hook invocation. Returns a short status string for tests; callers ignore it."""
    root = Path(root) if root else find_root()
    now = now or utcnow()
    project_log = project_dir(root) / 'diagnostics.log'

    def note(message, once=False):
        if project_log.parent.is_dir():  # never create the project directory just to log a dropped event
            (diag_once if once else diag)(project_log, message, now)

    try:
        try:
            payload = json.loads(raw) if raw and raw.strip() else None
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            note(f'hook {event_arg}: empty or invalid payload')
            return 'invalid'
        host = host or detect_host(payload, os.environ)
        event = normalise_event(event_arg or payload.get('hook_event_name'))
        adapter = codex if host == 'codex' else claude
        obs = adapter.parse_hook(payload, event, now)
        if not obs['session_id']:
            note(f'hook {event}: payload without session_id dropped')
            return 'dropped'
        # A fresh, matching handshake (the nonce is in this very tool call) outranks an existing binding: it is the
        # explicit request to attach this session to the feature that was just initialised.
        binding = snapshot.convert_pending(root, obs, now) if event == 'post_tool_use' else None
        binding = binding or snapshot.lookup(root, host, obs['session_id'])
        if not binding:
            note(f"unbound {host} session {clean(obs['session_id'], 80)} dropped", once=True)
            return 'dropped'
        if not snapshot.cwd_valid(binding, obs.get('cwd')):
            note(f'hook {event}: cwd outside the bound worktree dropped')
            return 'dropped'
        ctx = Ctx(root, binding['feature'])
        if not ctx.dir.is_dir():
            return 'uninitialised'
        try:
            with Lock(ctx.lock, retries=2, delay=0.05):
                fields = dict(obs['fields'])
                if host == 'codex' and not obs.get('child') and obs.get('transcript_path') and event in ROLLOUT_EVENTS:
                    for name, value in codex.read_rollout(obs['transcript_path'], now).items():
                        fields.setdefault(name, value)
                snapshot.merge(ctx, host, obs['session_id'], now, fields=fields, child=obs.get('child'))
                refreshed = refreshlib.after_update(ctx, now, force=event in FORCE_EVENTS)
            return 'refreshed' if refreshed else 'dirty'
        except LockBusy:
            diag(ctx.diag, f'hook {event}: lock busy, observation dropped', now)
            return 'busy'
    except Exception as exc:  # the host must never be blocked by Progress
        note(f'hook {event_arg}: {type(exc).__name__}: {exc}')
        return 'error'
