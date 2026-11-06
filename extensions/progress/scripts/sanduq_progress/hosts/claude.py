"""Claude Code adapter (hooks and statusline).

Verified against https://code.claude.com/docs/en/hooks and /statusline (2026-10-15):
  * hook payload: session_id, transcript_path, cwd, hook_event_name, agent_id and agent_type (only inside a
    subagent), effort {level}, permission_mode, tool_name, tool_input, tool_response, tool_use_id.
  * statusline stdin: model {id, display_name}, effort {level} (absent when unsupported), context_window
    {used_percentage, context_window_size, total_input_tokens (cumulative, unused), current_usage}, cost {total_duration_ms,
    total_api_duration_ms}, session_id, transcript_path, workspace.
Fields the docs do not guarantee (the Task/Agent tool_response shape, a model on hook payloads) are read
defensively and stay unknown when absent.
"""
from ..util import clean, iso
from . import SUBAGENT_TOOLS, meas, subagent_child, text_of


def _model_value(model):
    if isinstance(model, dict):
        return model.get('id') or model.get('display_name')
    return model if isinstance(model, str) else None


def parse_hook(payload, event, now):
    sid = str(payload.get('session_id') or '')
    agent_id = str(payload.get('agent_id') or '') or None
    obs = {'host': 'claude', 'session_id': sid, 'agent_id': agent_id, 'parent_session_id': None,
           'cwd': payload.get('cwd'), 'transcript_path': payload.get('transcript_path'), 'fields': {}, 'child': None,
           'tool_input_text': text_of(payload.get('tool_input')), 'tool_response_text': text_of(payload.get('tool_response'))}
    model = meas(_model_value(payload.get('model')), 'hook', now)
    effort = payload.get('effort')
    effort = meas(effort.get('level') if isinstance(effort, dict) else effort, 'hook', now)
    if agent_id:
        update = {'kind': 'subagent', 'last_observed_at': iso(now)}
        if payload.get('agent_type'):
            update['subagent_type'] = clean(payload['agent_type'], 60)
        if model:
            update['model'] = model
        if effort:
            update['effort'] = effort
        if event == 'stop':
            update.update(status='done', ended_at=iso(now))
        else:
            update['status'] = 'running'
        obs['child'] = {'key': agent_id, 'update': update, 'by_agent': True}
        return obs
    obs['fields'] = {k: v for k, v in (('model', model), ('effort', effort)) if v}
    if payload.get('tool_name') in SUBAGENT_TOOLS:
        obs['child'] = subagent_child(payload, event, now, 'hook', 'claude')
    return obs


CURRENT_INPUT_KEYS = ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')


def _current_tokens(usage):
    """Tokens in the context right now: the last request's input, cache writes and cache reads. `total_input_tokens`
    is a session-cumulative counter and is never used. No counter present means unknown, not zero."""
    if not isinstance(usage, dict):
        return None
    parts = [usage[k] for k in CURRENT_INPUT_KEYS if isinstance(usage.get(k), int) and not isinstance(usage.get(k), bool)]
    return sum(parts) if parts else None


def parse_statusline(payload, now):
    """Session-level measurements from the statusline JSON; nothing is guessed when a field is absent."""
    fields = {}
    model = payload.get('model')
    value = _model_value(model)
    if value:
        fields['model'] = meas(value, 'statusline', now)
    effort = payload.get('effort')
    level = effort.get('level') if isinstance(effort, dict) else None
    if level:
        fields['effort'] = meas(level, 'statusline', now)
    window = payload.get('context_window') if isinstance(payload.get('context_window'), dict) else {}
    percent = window.get('used_percentage')
    if isinstance(percent, (int, float)) and not isinstance(percent, bool):
        fields['context'] = meas({'used_percent': round(float(percent), 1),
                                  'used_tokens': _current_tokens(window.get('current_usage')),
                                  'window': window.get('context_window_size') if isinstance(window.get('context_window_size'), int) else None},
                                 'statusline', now)
    cost = payload.get('cost') if isinstance(payload.get('cost'), dict) else {}
    for name, key in (('elapsed_ms', 'total_duration_ms'), ('api_ms', 'total_api_duration_ms')):
        if isinstance(cost.get(key), (int, float)) and not isinstance(cost.get(key), bool):
            fields[name] = meas(int(cost[key]), 'statusline', now)
    return {'host': 'claude', 'session_id': str(payload.get('session_id') or ''), 'cwd': (payload.get('workspace') or {}).get('project_dir')
            if isinstance(payload.get('workspace'), dict) else payload.get('cwd'), 'fields': fields}
