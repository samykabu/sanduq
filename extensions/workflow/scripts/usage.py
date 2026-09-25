"""Read token usage from the logs agent harnesses already write.

Only token counters are read; message content never leaves the log. Every
reader returns the same shape, so the report never has to know which harness
did the work:

    fresh_input   input tokens sent without a cache hit or cache write
    cache_read    input tokens served from the prompt cache
    cache_write   input tokens written to the prompt cache
    output        output tokens, reasoning included
    reasoning     the reasoning share of output, when the harness reports it

Harnesses disagree on what "input" means. Claude reports input, cache write and
cache read as disjoint counters; Codex reports input inclusive of cached input.
The readers normalise both to the fields above.

Log formats are not a public contract. A reader that cannot find or parse its
log raises UsageUnavailable, and the caller records the entry as unavailable
rather than as zero.
"""
from datetime import datetime
import json
import os
from pathlib import Path

HARNESSES = ('claude', 'codex', 'delegate')
FIELDS = ('fresh_input', 'cache_read', 'cache_write', 'output', 'reasoning')


class UsageUnavailable(Exception):
    """The harness left no usable token record for this agent or window."""


def instant(value):
    """Parse an ISO-8601 timestamp, including the trailing Z the harnesses write."""
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp needs a time zone: ' + str(value))
    return parsed


def inside(stamp, since, until):
    moment = instant(stamp) if stamp else None
    if moment is None:
        return since is None and until is None
    return (since is None or moment >= since) and (until is None or moment <= until)


def lines(path):
    try:
        with open(path, encoding='utf-8') as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue  # a partially written final line while the agent is still running
                if isinstance(entry, dict):
                    yield entry
    except OSError as exc:
        raise UsageUnavailable('Cannot read ' + str(path) + ': ' + exc.strerror) from exc


def claude(path, since=None, until=None):
    """Sum a Claude Code transcript's per-response usage.

    Claude Code writes one line per content block, and every line repeats the
    response's usage with the output count growing as it streams. Keep one
    record per message id, the one with the largest output count.
    """
    responses, model = {}, None
    for entry in lines(path):
        message = entry.get('message') if isinstance(entry.get('message'), dict) else {}
        usage = message.get('usage')
        if entry.get('type') != 'assistant' or not isinstance(usage, dict):
            continue
        key = message.get('id') or entry.get('uuid')
        first = responses.get(key)
        stamp = first['stamp'] if first else entry.get('timestamp')
        if first is None or (usage.get('output_tokens') or 0) >= (first['usage'].get('output_tokens') or 0):
            responses[key] = {'stamp': stamp, 'usage': usage}
        model = message.get('model') or model
    chosen = [r['usage'] for r in responses.values() if inside(r['stamp'], since, until)]
    if not chosen:
        raise UsageUnavailable('No Claude responses with usage in ' + str(path))
    total = lambda name: sum(int(u.get(name) or 0) for u in chosen)
    return {'fresh_input': total('input_tokens'), 'cache_read': total('cache_read_input_tokens'),
            'cache_write': total('cache_creation_input_tokens'), 'output': total('output_tokens'),
            'reasoning': None, 'model': model, 'harness': 'claude'}


def codex(path, since=None, until=None):
    """Difference of a Codex rollout's running totals across the window."""
    baseline, last, model = None, None, None
    for entry in lines(path):
        payload = entry.get('payload') if isinstance(entry.get('payload'), dict) else {}
        if entry.get('type') == 'turn_context':
            model = payload.get('model') or model
        if payload.get('type') != 'token_count' or not isinstance(payload.get('info'), dict):
            continue
        totals = payload['info'].get('total_token_usage')
        if not isinstance(totals, dict):
            continue
        moment = instant(entry['timestamp']) if entry.get('timestamp') else None
        if since is not None and moment is not None and moment < since:
            baseline = totals
        elif until is None or moment is None or moment <= until:
            last = totals
    if last is None:
        raise UsageUnavailable('No Codex token counts in ' + str(path))
    start = baseline or {}
    delta = lambda name: int(last.get(name) or 0) - int(start.get(name) or 0)
    cached = delta('cached_input_tokens')
    return {'fresh_input': delta('input_tokens') - cached, 'cache_read': cached,
            'cache_write': delta('cache_write_input_tokens'), 'output': delta('output_tokens'),
            'reasoning': delta('reasoning_output_tokens'), 'model': model, 'harness': 'codex'}


def delegate(path, since=None, until=None):
    """A delegate-task result.json, already normalised by its driver."""
    try:
        result = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise UsageUnavailable('Cannot read delegate result ' + str(path)) from exc
    tokens = result.get('tokens') if isinstance(result.get('tokens'), dict) else {}
    if tokens.get('fidelity') not in ('exact', 'partial') or tokens.get('input_fresh') is None:
        raise UsageUnavailable('Delegate run ' + str(result.get('run_id')) + ' reported no token counts')
    return {'fresh_input': int(tokens['input_fresh']), 'cache_read': int(tokens.get('cache_read') or 0),
            'cache_write': int(tokens.get('cache_write') or 0), 'output': int(tokens.get('output_total') or 0),
            'reasoning': tokens.get('reasoning'), 'model': result.get('model'),
            'harness': result.get('harness') or 'delegate'}


def claude_root():
    return Path(os.environ.get('SANDUQ_CLAUDE_PROJECTS') or Path.home() / '.claude' / 'projects')


def codex_root():
    return Path(os.environ.get('SANDUQ_CODEX_SESSIONS') or Path.home() / '.codex' / 'sessions')


def locate(harness, agent):
    """Find an agent's own log by its host ID; ambiguity is an error, not a guess."""
    if harness == 'claude':
        name = agent if agent.startswith('agent-') else 'agent-' + agent
        found = sorted(claude_root().glob('*/*/subagents/' + name + '.jsonl'))
    elif harness == 'codex':
        found = sorted(codex_root().glob('**/rollout-*' + agent + '.jsonl'))
    else:
        raise UsageUnavailable('A delegate result has no default location; pass --log')
    if not found:
        raise UsageUnavailable('No ' + harness + ' log found for agent ' + agent)
    if len(found) > 1:
        raise UsageUnavailable('Several ' + harness + ' logs match agent ' + agent + '; pass --log')
    return found[0]


READERS = {'claude': claude, 'codex': codex, 'delegate': delegate}


def collect(harness, agent, log=None, since=None, until=None):
    path = Path(log) if log else locate(harness, agent)
    return READERS[harness](path, instant(since), instant(until))
