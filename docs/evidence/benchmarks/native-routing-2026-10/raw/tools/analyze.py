"""Summarize a Claude stream-json or Codex --json transcript: tools, turns, tokens, cost."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import collections, json, sys
from datetime import datetime

def load(path):
    rows = []
    for line in open(path, encoding='utf-8', errors='replace'):
        try: rows.append(json.loads(line))
        except ValueError: pass
    return rows

def claude(rows):
    tools = collections.Counter(); model = None; res = {}
    for r in rows:
        if r.get('type') == 'system' and r.get('subtype') == 'init': model = r.get('model')
        if r.get('type') == 'assistant':
            for c in r['message'].get('content', []):
                if c.get('type') == 'tool_use': tools[c['name']] += 1
        if r.get('type') == 'result': res = r
    u = res.get('usage', {})
    return dict(model=model, tools=sum(tools.values()), by_tool=dict(tools.most_common()),
                turns=res.get('num_turns'), secs=round((res.get('duration_ms') or 0)/1000),
                cost=res.get('total_cost_usd'), is_error=res.get('is_error'),
                tokens=[u.get('input_tokens'), u.get('cache_creation_input_tokens'),
                        u.get('cache_read_input_tokens'), u.get('output_tokens')],
                models=res.get('modelUsage') and {k: round(v.get('costUSD', 0), 2) for k, v in res['modelUsage'].items()},
                result=(res.get('result') or '')[-600:])

def codex(rows):
    tools = collections.Counter(); usage = collections.Counter(); last = ''
    for r in rows:
        t = r.get('type'); item = r.get('item') or {}
        if t == 'item.completed' and item.get('type') not in (None, 'agent_message', 'reasoning'):
            tools[item.get('type')] += 1
        if t == 'item.completed' and item.get('type') == 'agent_message': last = item.get('text', '')
        if t == 'turn.completed':
            for k, v in (r.get('usage') or {}).items(): usage[k] += v
    return dict(tools=sum(tools.values()), by_tool=dict(tools), usage=dict(usage), result=last[-600:])

if __name__ == '__main__':
    rows = load(sys.argv[1])
    kind = 'codex' if any(r.get('type', '').startswith(('thread.', 'turn.', 'item.')) for r in rows) else 'claude'
    print(json.dumps((codex if kind == 'codex' else claude)(rows), indent=1, ensure_ascii=False))
