"""Measured T07 spend: Claude Code host total_cost_usd of every transcript plus external Claude runs'
cost_usd from each clone's .delegate/runs/*/result.json. Codex is subscription-billed (tokens only).

usage: python spend.py            print the per-session table and the total
       python spend.py --check X  exit 1 when the total has reached X USD (run-feature.sh calls this)
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from analyze import claude, codex, load  # noqa: E402

BASE = '<sandbox>'


def host_sessions():
    for path in sorted(glob.glob(BASE + '/logs/transcripts/*.jsonl')):
        name = os.path.basename(path)[:-6]
        rows = load(path)
        if any(str(r.get('type', '')).startswith(('thread.', 'turn.', 'item.')) for r in rows):
            yield name, 'codex', 0.0, codex(rows)
        else:
            s = claude(rows)
            yield name, 'claude', float(s['cost'] or 0), s


def external_runs():
    for path in sorted(glob.glob(BASE + '/runs/*/.delegate/runs/*/result.json')):
        try:
            r = json.load(open(path, encoding='utf-8'))
        except (OSError, ValueError):
            continue
        run = path.replace('\\', '/').split('/runs/')[1].split('/')[0]
        yield run, r.get('run_id'), r.get('harness'), float(r.get('cost_usd') or 0)


def total():
    return (sum(c for _, _, c, _ in host_sessions()) + sum(c for *_, c in external_runs()))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--check':
        spent = total()
        print(f'spent {spent:.2f} USD (stop line {sys.argv[2]})')
        sys.exit(1 if spent >= float(sys.argv[2]) else 0)
    print('| Session | Host | USD |')
    print('| --- | --- | ---: |')
    for name, host, cost, _ in host_sessions():
        print(f'| {name} | {host} | {cost:.2f} |' if host == 'claude' else f'| {name} | codex | subscription |')
    for run, rid, harness, cost in external_runs():
        print(f'| {run} external {rid} | {harness} | {cost:.2f} |')
    print(f'\n**Total measured USD: {total():.2f}**')
