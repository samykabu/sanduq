"""Codex adapter.

Hook payload (as handed to the extension by the Spec Kit dispatcher): session_id, turn_id, agent_id, agent_type,
transcript_path, model, tool_name, tool_input, tool_response. Effort and context are not in the payload; they
come from the rollout adapter below, which is pinned to the record shapes of ROLLOUT_ADAPTER and returns nothing
(unknown) when the shapes differ. Only the last 512 KiB of the rollout is read and only numbers and the model and
effort words are kept; no message text.
"""
import json
import os
from pathlib import Path

from ..util import clean, iso, read_capped
from . import SUBAGENT_TOOLS, meas, subagent_child, text_of

ROLLOUT_ADAPTER = 'codex-rollout-v1 (turn_context.payload.model/effort, event token_count.info)'
TAIL_BYTES = 512 * 1024
PARENT_KEYS = ('parent_session_id', 'parent_thread_id', 'forked_from_session_id', 'forked_from_id')
SPAWN_TOOLS = SUBAGENT_TOOLS + ('spawn_agent',)


def parse_hook(payload, event, now):
    sid = str(payload.get('session_id') or '')
    agent_id = str(payload.get('agent_id') or '') or None
    parent = next((str(payload[k]) for k in PARENT_KEYS if payload.get(k)), None)
    obs = {'host': 'codex', 'session_id': sid, 'agent_id': agent_id, 'parent_session_id': parent,
           'cwd': payload.get('cwd'), 'transcript_path': payload.get('transcript_path'), 'fields': {}, 'child': None,
           'tool_input_text': text_of(payload.get('tool_input')), 'tool_response_text': text_of(payload.get('tool_response'))}
    model = meas(payload.get('model') if isinstance(payload.get('model'), str) else None, 'hook', now)
    if agent_id or parent:
        # Verified child: the hook fires inside a child agent or thread whose parent is named in the payload.
        update = {'kind': 'subagent', 'last_observed_at': iso(now)}
        if payload.get('agent_type'):
            update['subagent_type'] = clean(payload['agent_type'], 60)
        if model:
            update['model'] = model
        if event == 'stop':
            update.update(status='done', ended_at=iso(now))
        else:
            update['status'] = 'running'
        obs['child'] = {'key': agent_id or sid, 'update': update, 'by_agent': True}
        if parent:
            obs['session_id'] = parent
        return obs
    if model:
        obs['fields']['model'] = model
    if payload.get('tool_name') in SPAWN_TOOLS:
        obs['child'] = subagent_child(payload, event, now, 'hook', 'codex')
    return obs


def _tail_records(path):
    path = Path(path)
    if not path.is_file() or path.suffix != '.jsonl':
        return []
    raw, size, _ = read_capped(path, TAIL_BYTES, tail=True)
    lines = raw.decode('utf-8', 'replace').splitlines()
    if size > TAIL_BYTES:
        lines = lines[1:]
    out = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def read_rollout(path, now):
    """Latest turn_context model and effort plus the last token_count event. Tolerant; partial fidelity."""
    try:
        records = _tail_records(path)
    except OSError:
        return {}
    model = effort = info = None
    for item in records:
        payload = item.get('payload') if isinstance(item.get('payload'), dict) else {}
        if item.get('type') == 'turn_context':
            model = payload.get('model') or model
            mode = payload.get('collaboration_mode') if isinstance(payload.get('collaboration_mode'), dict) else {}
            settings = mode.get('settings') if isinstance(mode.get('settings'), dict) else {}
            effort = payload.get('effort') or payload.get('reasoning_effort') or settings.get('reasoning_effort') or effort
        elif payload.get('type') == 'token_count' and isinstance(payload.get('info'), dict):
            info = payload['info']
    fields = {}
    if isinstance(model, str):
        fields['model'] = meas(model, 'rollout', now, 'partial')
    if isinstance(effort, str):
        fields['effort'] = meas(effort, 'rollout', now, 'partial')
    if info:
        last = info.get('last_token_usage') if isinstance(info.get('last_token_usage'), dict) else {}
        used = last.get('total_tokens', last.get('input_tokens'))
        window = info.get('model_context_window')
        if isinstance(used, int) and isinstance(window, int) and window > 0:
            fields['context'] = meas({'used_percent': round(100.0 * used / window, 1), 'used_tokens': used,
                                      'window': window}, 'rollout', now, 'partial')
    return fields
