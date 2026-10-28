"""Collect one T07 run's measures and raw ledgers.

usage: python collect.py <run>     e.g. a1, b2, fx-codex   (issue from logs/issues.tsv)
Writes logs/rows/<run>.json and copies the raw evidence to evidence/<run>/:
  delegations.json (the delegation ledger), lifecycle.jsonl, checkpoint.json, every external
  .delegate/runs/<id>/result.json and meta.json, the session start/end stamps.
Tokens for external and native agents are read with the clone's installed Workflow usage.py
(usage.delegate for a driver result, usage.claude / usage.codex for a native agent's own log).
"""
import collections
import glob
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from analyze import claude, codex, load  # noqa: E402
import policy  # noqa: E402

BASE = Path('<sandbox>')
ARMS = {'a': 'in-session', 'b': 'native', 'c': 'external'}


def stamp(path):
    return datetime.fromisoformat(path.read_text().strip().replace('Z', '+00:00'))


def sessions(run):
    out = []
    for path in sorted((BASE / 'logs/transcripts').glob(run + '-*.jsonl')):
        name = path.name[:-6]
        rows = load(path)
        kind = 'codex' if any(str(r.get('type', '')).startswith(('thread.', 'turn.', 'item.')) for r in rows) else 'claude'
        s = codex(rows) if kind == 'codex' else claude(rows)
        start, end = stamp(path.with_suffix('.start')), stamp(path.with_suffix('.end'))
        models = {}
        for r in rows:
            if r.get('type') == 'result' and isinstance(r.get('modelUsage'), dict):
                models = {m: {k: v.get(k) for k in ('inputTokens', 'outputTokens', 'cacheReadInputTokens',
                                                    'cacheCreationInputTokens', 'costUSD')}
                          for m, v in r['modelUsage'].items()}
        out.append({'name': name, 'host': kind, 'start': start.isoformat(), 'end': end.isoformat(),
                    'exit': (path.with_suffix('.exit').read_text().strip() if path.with_suffix('.exit').exists() else None),
                    'usd': float(s.get('cost') or 0) if kind == 'claude' else None,
                    'model_s': s.get('secs') if kind == 'claude' else round((end - start).total_seconds()),
                    'tool_calls': s['tools'], 'tokens': s.get('tokens') if kind == 'claude' else s.get('usage'),
                    'model_usage': models, 'is_error': s.get('is_error')})
    return out


def main(run):
    issue = dict(line.split('\t') for line in (BASE / 'logs/issues.tsv').read_text().split('\n') if line)[run].strip()
    feature = policy.feature_for(int(issue))
    clone = BASE / 'runs' / run
    fdir = clone / feature / 'workflow'
    ev = BASE / 'evidence' / run
    ev.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(clone / '.specify/extensions/workflow/scripts'))
    if (BASE / 'codex-home' / run / 'sessions').is_dir():  # run-codex.sh's isolated CODEX_HOME
        os.environ.setdefault('SANDUQ_CODEX_SESSIONS', str(BASE / 'codex-home' / run / 'sessions'))
    import usage  # the installed Workflow's reader

    for name in ('delegations.json', 'lifecycle.jsonl', 'checkpoint.json'):
        if (fdir / name).exists():
            shutil.copy2(fdir / name, ev / name)
    for f in (BASE / 'logs/transcripts').glob(run + '-*'):
        if f.suffix in ('.start', '.end', '.exit'):
            shutil.copy2(f, ev / f.name)

    ledger = json.loads((fdir / 'delegations.json').read_text(encoding='utf-8')) if (fdir / 'delegations.json').exists() else {'attempts': []}
    attempts = ledger['attempts']
    by = collections.Counter((a.get('kind'), a.get('route_kind', 'unknown'), a.get('route_reason', 'unknown'),
                              a.get('status')) for a in attempts)
    external, native = [], []
    for a in attempts:
        if a.get('kind') == 'native':
            entry = {'identity': a.get('identity'), 'status': a.get('status'), 'agent': a.get('host_agent_id'),
                     'requested_model': a.get('requested_model'), 'actual_model': a.get('actual_model'),
                     'route_reason': a.get('route_reason')}
            if a.get('host_agent_id'):
                harness = 'codex' if run.endswith('codex') else 'claude'
                try:
                    entry['tokens'] = usage.collect(harness, a['host_agent_id'])
                except (usage.UsageUnavailable, ValueError) as exc:
                    entry['tokens'] = {'fidelity': 'unavailable', 'reason': str(exc)}
            native.append(entry)
        elif a.get('run_id'):
            res = clone / '.delegate/runs' / a['run_id'] / 'result.json'
            entry = {'identity': a.get('identity'), 'status': a.get('status'), 'run_id': a['run_id'],
                     'route_reason': a.get('route_reason')}
            if res.exists():
                dest = ev / 'delegate-runs' / a['run_id']
                dest.mkdir(parents=True, exist_ok=True)
                for n in ('result.json', 'meta.json'):
                    if (res.parent / n).exists():
                        shutil.copy2(res.parent / n, dest / n)
                raw = json.loads(res.read_text(encoding='utf-8'))
                entry['usd'] = raw.get('cost_usd')
                try:
                    entry['tokens'] = usage.delegate(res)
                except usage.UsageUnavailable as exc:
                    entry['tokens'] = {'fidelity': 'unavailable', 'reason': str(exc)}
            external.append(entry)

    lifecycle = [json.loads(l) for l in (fdir / 'lifecycle.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()] \
        if (fdir / 'lifecycle.jsonl').exists() else []
    ss = sessions(run)
    host_usd = sum(s['usd'] or 0 for s in ss)
    ext_usd = sum(e.get('usd') or 0 for e in external)
    ext_tok = collections.Counter()
    for e in external:
        for k in ('fresh_input', 'cache_read', 'cache_write', 'output'):
            ext_tok[k] += int((e.get('tokens') or {}).get(k) or 0)
    row = {'run': run, 'arm': ARMS.get(run[0], 'fixture') if not run.startswith('fx') else 'fixture',
           'issue': int(issue), 'feature': feature, 'sessions': len(ss),
           'usd_host': round(host_usd, 2), 'usd_external': round(ext_usd, 2), 'usd_total': round(host_usd + ext_usd, 2),
           'model_s': sum(s['model_s'] or 0 for s in ss),
           'elapsed_s': round((max(datetime.fromisoformat(s['end']) for s in ss) -
                               min(datetime.fromisoformat(s['start']) for s in ss)).total_seconds()) if ss else 0,
           'tool_calls': sum(s['tool_calls'] for s in ss),
           'attempts': len(attempts),
           'attempts_by_kind': {' / '.join(map(str, k)): v for k, v in by.items()},
           'native_attempts': native, 'external_attempts': external, 'external_tokens': dict(ext_tok),
           'rejected_completions': sum(e.get('event') == 'rejected-completion' for e in lifecycle),
           'sessions_detail': ss}
    (BASE / 'logs/rows').mkdir(parents=True, exist_ok=True)
    (BASE / 'logs/rows' / (run + '.json')).write_text(json.dumps(row, indent=1), encoding='utf-8')
    print(json.dumps({k: row[k] for k in ('run', 'arm', 'issue', 'sessions', 'usd_total', 'model_s', 'attempts',
                                          'attempts_by_kind', 'rejected_completions')}, indent=1))


if __name__ == '__main__':
    main(sys.argv[1])
