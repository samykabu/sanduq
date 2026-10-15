"""Host adapters turn raw hook or statusline payloads into observations. Every measured value carries
{value, source, observed_at, fidelity}; fields a host does not provide stay absent and render as unknown."""
import re

from ..util import clean, iso

EVENTS = ('session_start', 'pre_tool_use', 'post_tool_use', 'user_prompt_submit', 'stop', 'session_end')
SUBAGENT_TOOLS = ('Task', 'Agent')
ASYNC_TOOLS = ('spawn_agent',)
SAFE = re.compile(r'[^A-Za-z0-9._-]')


def meas(value, source, now, fidelity='exact'):
    if value is None or value == '':
        return None
    return {'value': value, 'source': source, 'observed_at': iso(now), 'fidelity': fidelity}


def unknown():
    return {'value': None, 'source': 'none', 'observed_at': None, 'fidelity': 'unknown'}


def normalise_event(name):
    text = re.sub(r'(?<!^)(?=[A-Z])', '_', str(name or '')).lower().replace('-', '_')
    return text if text in EVENTS else str(name or '').lower()


def detect_host(payload, env=None):
    """Claude and Codex payloads share most field names; explicit markers win, Claude is the default."""
    env = env or {}
    path = str(payload.get('transcript_path') or '').replace('\\', '/')
    if 'turn_id' in payload or '/.codex/' in path or 'rollout-' in path or env.get('CODEX_HOME') and 'permission_mode' not in payload:
        return 'codex'
    return 'claude'


def session_key(host, session_id):
    return f'{host}-{SAFE.sub("_", str(session_id))}'[:160]


def text_of(value, limit=4000):
    """Bounded text of a tool input or response, used only to find the binding nonce."""
    import json
    try:
        return json.dumps(value, ensure_ascii=False)[:limit] if not isinstance(value, str) else value[:limit]
    except (TypeError, ValueError):
        return ''


def subagent_child(payload, event, now, source, host):
    """Child update for a subagent-launching tool call seen in the parent: started on pre_tool_use, terminal on a
    non-background tool result. An asynchronous launch (`run_in_background`, or Codex `spawn_agent`, whose response only
    says the agent exists) stays running until the child's own stop is observed: a launch response is never completion."""
    tool_input = payload.get('tool_input') if isinstance(payload.get('tool_input'), dict) else {}
    response = payload.get('tool_response')
    key = str(payload.get('tool_use_id') or '')
    if not key:
        return None
    background = bool(tool_input.get('run_in_background')) or payload.get('tool_name') in ASYNC_TOOLS
    update = {'kind': 'subagent', 'subagent_type': clean(tool_input.get('subagent_type') or tool_input.get('agent_type') or 'unknown', 60),
              'description': clean(tool_input.get('description') or '', 80), 'background': background,
              'last_observed_at': iso(now)}
    requested = meas(tool_input.get('model'), source, now, 'partial')
    if requested:
        update['model'] = requested  # requested alias from the launch call, not an observation of the child
    if event == 'pre_tool_use':
        update.update(status='running', started_at=iso(now))
    elif event == 'post_tool_use':
        agent_id = None
        if isinstance(response, dict):
            agent_id = response.get('agentId') or response.get('agent_id')
            if not agent_id and payload.get('tool_name') in ASYNC_TOOLS:
                agent_id = response.get('id')  # Codex spawn_agent names the new agent `id`; no other tool's `id` is an agent
        if agent_id:
            update['agent_id'] = str(agent_id)
        failed = isinstance(response, dict) and bool(response.get('is_error') or response.get('error'))
        if background and not failed:
            update['status'] = 'running'
        else:
            update.update(status='failed' if failed else 'done', ended_at=iso(now))
    return {'key': key, 'update': update}
