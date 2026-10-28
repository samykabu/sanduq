"""Results table from logs/rows/*.json (collect.py + postmerge.sh). Prints Markdown for the benchmark page.
usage: python report.py > ../results.md"""
import glob
import json
import os
import statistics

BASE = '<sandbox>/logs/rows'
rows = []
for path in sorted(glob.glob(BASE + '/*.json')):
    if path.endswith('.heldout.json'):
        continue
    r = json.load(open(path, encoding='utf-8'))
    h = BASE + '/' + r['run'] + '.heldout.json'
    r['held'] = json.load(open(h)) if os.path.exists(h) else {}
    rows.append(r)

def valid(r):
    v = r.get('validity')
    return 'not checked' if v is None else 'yes' if v['valid'] else 'INVALID: ' + '; '.join(v['reasons'])


print('| Run | Arm | Issue | PR | Sessions | USD host | USD external | USD total | Model s | Elapsed s | Tool calls '
      '| Attempts (native / external) | Rejected completions | Held-out failed / ran | Valid (validate.py) |')
print('| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | --- |')
for r in rows:
    h = r['held']
    print(f"| {r['run']} | {r['arm']} | #{r['issue']} | {('#' + str(h['pr'])) if h.get('pr') else '-'} | {r['sessions']} "
          f"| {r['usd_host']:.2f} | {r['usd_external']:.2f} | {r['usd_total']:.2f} | {r['model_s']} | {r['elapsed_s']} "
          f"| {r['tool_calls']} | {len(r['native_attempts'])} / {len(r['external_attempts'])} | {r['rejected_completions']} "
          f"| {h.get('heldout_failed', '-')} / {h.get('heldout_ran', '-')} | {valid(r)} |")

print('\n| Arm | n | USD total, median (range) | Model s, median (range) | Elapsed s, median | Attempts, median '
      '| External tokens in/out (sum) | Rejected completions (sum) | Held-out failures (sum) |')
print('| --- | ---: | --- | --- | ---: | ---: | --- | ---: | ---: |')
for arm in ('in-session', 'native', 'external', 'fixture'):
    g = [r for r in rows if r['arm'] == arm and (r.get('validity') or {}).get('valid')]
    if not g:
        continue
    usd = [r['usd_total'] for r in g]; ms = [r['model_s'] for r in g]
    tin = sum(r['external_tokens'].get('fresh_input', 0) + r['external_tokens'].get('cache_read', 0) +
              r['external_tokens'].get('cache_write', 0) for r in g)
    tout = sum(r['external_tokens'].get('output', 0) for r in g)
    print(f"| {arm} | {len(g)} | {statistics.median(usd):.2f} ({min(usd):.2f} to {max(usd):.2f}) "
          f"| {statistics.median(ms):.0f} ({min(ms)} to {max(ms)}) | {statistics.median(r['elapsed_s'] for r in g):.0f} "
          f"| {statistics.median(r['attempts'] for r in g):.0f} | {tin:,} / {tout:,} "
          f"| {sum(r['rejected_completions'] for r in g)} | {sum(r['held'].get('heldout_failed', 0) for r in g)} |")
