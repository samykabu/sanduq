"""Keep an implementation report beside its durable JSON state.

The orchestrator is the sole writer. Workers send updates to the orchestrator.
Run with --help for the portable CLI; no web server or dependencies are needed.
"""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import tempfile
import os
import sys
import webbrowser

sys.path.insert(0, str(Path(__file__).resolve().parent))
import usage as token_usage  # noqa: E402

DEFAULT_TITLE = 'Implementation progress'


def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


STATUSES = ('pending', 'running', 'done', 'blocked')
LOGOS = ('sanduq-logo.png', 'sanduq-logo-dark.png')
ICON = 'sanduq-icon.png'
ASSETS = Path(__file__).resolve().parent.parent / 'assets' / 'report'

STYLE = """
:root{color-scheme:light dark;--bg:#f6f7f4;--surface:#fff;--text:#1b2a24;--muted:#4e5d56;--line:#d5dcd7;
--brand:#233c32;--accent:#c65b36;--pending:#e9ece9;--running:#dcebf7;--done:#dcefe2;--blocked:#f8e0d6}
@media (prefers-color-scheme:dark){:root{--bg:#121916;--surface:#1a2420;--text:#eef2ef;--muted:#a9b6af;
--line:#2f3d37;--brand:#dfe9e3;--accent:#e07a55;--pending:#2a3430;--running:#1d3444;--done:#1f3a2a;--blocked:#46291e}}
*{box-sizing:border-box}body{font:16px/1.5 system-ui,sans-serif;margin:0;background:var(--bg);color:var(--text)}
main{max-width:1400px;margin:0 auto;padding:32px 24px 48px}
header{display:flex;flex-wrap:wrap;align-items:center;gap:16px 28px;margin-bottom:20px}
header img{height:48px;width:auto;display:block}h1{font-size:1.6rem;margin:0;color:var(--brand)}
.summary{flex:1 1 280px}.summary p{margin:4px 0;color:var(--muted)}
progress{width:100%;height:10px;accent-color:var(--accent)}
[role=tablist]{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:24px 0 16px}
[role=tab]{font:inherit;padding:10px 18px;border:0;border-bottom:3px solid transparent;background:none;color:var(--muted);cursor:pointer}
[role=tab][aria-selected=true]{color:var(--brand);border-bottom-color:var(--accent);font-weight:600}
[role=tab]:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.filters{display:flex;flex-wrap:wrap;gap:12px 20px;align-items:end;margin-bottom:12px}
label{display:flex;flex-direction:column;font-size:.85rem;color:var(--muted);gap:4px}
select{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:var(--text);min-width:200px}
.count{color:var(--muted);font-size:.9rem;margin:0 0 0 auto}
.table{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%}th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.85rem;color:var(--muted);font-weight:600}td{overflow-wrap:anywhere}
tbody td:nth-child(1),tbody td:nth-child(4),tbody td:nth-child(5){white-space:nowrap;overflow-wrap:normal}tbody td:nth-child(3){min-width:160px}tbody td:nth-child(2){min-width:280px}tbody tr:last-child td{border-bottom:0}
.status{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.85rem;white-space:nowrap}
.status-pending{background:var(--pending)}.status-running{background:var(--running)}.status-done{background:var(--done)}.status-blocked{background:var(--blocked)}
h2{font-size:1.05rem;color:var(--brand);margin:28px 0 8px}ul,ol{padding-left:22px}li{margin:4px 0;overflow-wrap:anywhere}
small{color:var(--muted)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}td.num{white-space:nowrap}
#tasks tbody td:last-child{min-width:240px}
.partial::after{content:" *";color:var(--accent)}
tfoot td,tfoot th{font-weight:600;border-top:1px solid var(--line);border-bottom:0}
.tokens{max-width:760px}
"""

# Filters and the selected tab live in the URL fragment, so the five-second reload keeps them.
SCRIPT = """
(function(){
  var tabs=[].slice.call(document.querySelectorAll('[role=tab]'));
  var status=document.getElementById('status-filter'), phase=document.getElementById('phase-filter');
  var rows=[].slice.call(document.querySelectorAll('#tasks tbody tr')), count=document.getElementById('shown');
  function read(){var q={};location.hash.slice(1).split('&').forEach(function(p){var kv=p.split('=');if(kv[0])q[decodeURIComponent(kv[0])]=decodeURIComponent(kv[1]||'');});return q;}
  function current(){return tabs.filter(function(t){return t.getAttribute('aria-selected')==='true';})[0].dataset.tab;}
  function write(){var q={tab:current(),status:status.value,phase:phase.value};
    history.replaceState(null,'','#'+Object.keys(q).map(function(k){return encodeURIComponent(k)+'='+encodeURIComponent(q[k]);}).join('&'));}
  function select(name){tabs.forEach(function(t){var on=t.dataset.tab===name;t.setAttribute('aria-selected',on?'true':'false');t.tabIndex=on?0:-1;
    document.getElementById(t.getAttribute('aria-controls')).hidden=!on;});}
  var sums=[].slice.call(document.querySelectorAll('#tasks tfoot [data-sum]'));
  function filter(){var shown=0,total={};rows.forEach(function(r){var ok=(!status.value||r.dataset.status===status.value)&&(!phase.value||r.dataset.phase===phase.value);r.hidden=!ok;if(ok){shown++;
    sums.forEach(function(c){var v=r.dataset[c.dataset.sum];if(v){total[c.dataset.sum]=(total[c.dataset.sum]||0)+Number(v);}});}});
    count.textContent=shown;sums.forEach(function(c){var v=total[c.dataset.sum];c.textContent=v===undefined?'\u2014':v.toLocaleString('en-US');});}
  function option(el,value){return [].some.call(el.options,function(o){return o.value===value;})?value:'';}
  var q=read();status.value=option(status,q.status||'');phase.value=option(phase,q.phase||'');select(q.tab==='activity'?'activity':'tasks');filter();
  tabs.forEach(function(t,i){t.addEventListener('click',function(){select(t.dataset.tab);write();});
    t.addEventListener('keydown',function(e){var d=e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0;if(!d)return;e.preventDefault();var n=tabs[(i+d+tabs.length)%tabs.length];n.focus();select(n.dataset.tab);write();});});
  [status,phase].forEach(function(el){el.addEventListener('change',function(){filter();write();});});
  setTimeout(function(){location.reload();},5000);
})();
"""


TOKEN_COLUMNS = (('fresh', 'fresh_input', 'Fresh input'), ('cached', 'cached', 'Cached input'),
                 ('out', 'output', 'Output'))
DASH = '\u2014'


def tally(entries):
    """Sum recorded usage. None means nothing was measured, which is not zero."""
    measured = [e for e in entries if e.get('fidelity') != 'unavailable']
    if not measured:
        return None
    total = {name: sum(int(e.get(name) or 0) for e in measured) for name in token_usage.FIELDS}
    total['cached'] = total['cache_read'] + total['cache_write']
    total['partial'] = len(measured) < len(entries) or any(e.get('fidelity') == 'reported' for e in measured)
    return total


def combine(totals):
    present = [t for t in totals if t is not None]
    if not present:
        return None
    merged = {name: sum(t[name] for t in present) for name in (*token_usage.FIELDS, 'cached')}
    merged['partial'] = any(t['partial'] for t in present) or len(present) < len(totals)
    return merged


def number(total, field):
    return DASH if total is None else f'{total[field]:,}'


def detail(entries):
    """Tooltip: which agent, harness and model produced a figure, and how it was measured."""
    parts = []
    for e in entries:
        if e.get('fidelity') == 'unavailable':
            parts.append(f"{e.get('agent')}: unavailable ({e.get('reason') or 'no record'})")
            continue
        who = ' '.join(str(v) for v in (e.get('agent'), e.get('harness'), e.get('model')) if v)
        parts.append(who + f": cache read {int(e.get('cache_read') or 0):,}, cache write {int(e.get('cache_write') or 0):,}"
                     + (f", reasoning {int(e['reasoning']):,}" if e.get('reasoning') is not None else '')
                     + ('' if e.get('fidelity') == 'exact' else ' (self-reported)'))
    return '; '.join(parts)


def token_class(total):
    return 'num partial' if total and total['partial'] else 'num'


def token_cells(entries, escape):
    total = tally(entries)
    title = escape(detail(entries))
    return ''.join(f'<td class="{token_class(total)}" title="{title}">{number(total, field)}</td>'
                   for _, field, _ in TOKEN_COLUMNS)


def token_data(entries):
    total = tally(entries)
    return ''.join(f' data-{key}="{"" if total is None else total[field]}"' for key, field, _ in TOKEN_COLUMNS)


def token_summary(state, escape):
    """Per-phase, overhead and feature totals, computed on every render so they cannot drift."""
    groups = {}
    for task in state['tasks']:
        groups.setdefault(task.get('phase') or 'No phase', []).append(tally(task.get('usage', [])))
    removed = [tally(t.get('usage', [])) for t in state.get('archived_tasks', []) if t.get('usage')]
    lines = [(name, combine(values)) for name, values in groups.items()]
    if removed:
        lines.append(('Removed tasks', combine(removed)))
    lines.append(('Orchestration and review overhead', tally(state.get('overhead', []))))
    feature = combine([value for _, value in lines])
    head = ''.join(f'<th scope="col" class="num">{label}</th>' for _, _, label in TOKEN_COLUMNS)
    body = ''.join(f'<tr><th scope="row">{escape(name)}</th>'
                   + ''.join(f'<td class="{token_class(value)}">{number(value, field)}</td>' for _, field, _ in TOKEN_COLUMNS)
                   + '</tr>' for name, value in lines)
    foot = ''.join(f'<td class="{token_class(feature)}">{number(feature, field)}</td>' for _, field, _ in TOKEN_COLUMNS)
    measured = sum(1 for t in state['tasks'] if tally(t.get('usage', [])) is not None)
    headline = ('No token usage recorded yet.' if feature is None else
                f'Implementation tokens: {feature["fresh_input"]:,} fresh input, '
                f'{feature["cached"]:,} cached input, {feature["output"]:,} output.')
    section = f"""<h2>Token usage</h2>
<p><small>Implementation only: scoping, specification, clarification and planning happen before this report
exists and are not counted. Figures come from the agents' own harness logs. {measured} of {len(state['tasks'])}
tasks have a measurement. {DASH} means nothing was measured, not zero; * marks a partial or self-reported figure.
Totals from different harnesses or models are not comparable.</small></p>
<div class="table tokens"><table><thead><tr><th scope="col">Scope</th>{head}</tr></thead><tbody>{body}</tbody>
<tfoot><tr><th scope="row">Feature total</th>{foot}</tr></tfoot></table></div>"""
    return headline, section


def render(state):
    escape = lambda value: html.escape(str(value), quote=True)
    # Offer only phases that have tasks, in plan order, so the filter never empties the table.
    phase_names = list(dict.fromkeys(t['phase'] for t in state['tasks'] if t.get('phase')))
    rows = ''.join(
        f'<tr data-status="{escape(task["status"])}" data-phase="{escape(task.get("phase", ""))}"{token_data(task.get("usage", []))}>'
        f'<td>{escape(task["id"])}</td><td>{escape(task["title"])}</td><td>{escape(task.get("phase", ""))}</td>'
        f'<td><span class="status status-{escape(task["status"])}">{escape(task["status"])}</span></td>'
        f'<td>{escape(task.get("agent", ""))}</td>{token_cells(task.get("usage", []), escape)}'
        f'<td>{escape(task.get("note", ""))}</td></tr>'
        for task in state['tasks'])
    headline, tokens = token_summary(state, escape)
    token_heads = ''.join(f'<th scope="col" class="num">{label}</th>' for _, _, label in TOKEN_COLUMNS)
    token_foot = ''.join(f'<td class="num" data-sum="{key}">{DASH}</td>' for key, _, _ in TOKEN_COLUMNS)
    status_options = ''.join(f'<option value="{s}">{s.capitalize()}</option>' for s in STATUSES)
    phase_options = ''.join(f'<option value="{escape(name)}">{escape(name)}</option>' for name in phase_names)
    events = ''.join('<li>' + escape(event) + '</li>' for event in reversed(state['events']))
    phases = ''.join('<li>' + escape(name) + ': ' + escape(value) + '</li>'
                     for name, value in state['phases'].items())
    archived = ''.join('<li>' + escape(json.dumps(task, ensure_ascii=False)) + '</li>'
                       for task in state.get('archived_tasks', []))
    done = sum(task['status'] == 'done' for task in state['tasks'])
    total = len(state['tasks'])
    logo = ('<picture><source srcset="sanduq-logo-dark.png" media="(prefers-color-scheme: dark)">'
            '<img src="sanduq-logo.png" alt="Sanduq" width="150" height="48"></picture>') if state.get('logo') else ''
    icon = f'<link rel="icon" type="image/png" sizes="128x128" href="{ICON}">' if state.get('icon') else ''
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<noscript><meta http-equiv="refresh" content="5"></noscript>{icon}<title>{escape(state['title'])}</title>
<style>{STYLE}</style></head><body><main>
<header>{logo}<div class="summary"><h1>{escape(state['title'])}</h1>
<p>{done} of {total} tasks complete. {escape(headline)}</p><progress value="{done}" max="{max(1, total)}" aria-label="Tasks complete"></progress>
<p><small>Updated {escape(state['updated'])}. This page refreshes every five seconds.</small></p></div></header>
<div role="tablist" aria-label="Report sections">
<button type="button" role="tab" id="tasks-tab" data-tab="tasks" aria-controls="tasks-panel" aria-selected="true">Tasks</button>
<button type="button" role="tab" id="activity-tab" data-tab="activity" aria-controls="activity-panel" aria-selected="false" tabindex="-1">Activity ({len(state['events'])})</button>
</div>
<section id="tasks-panel" role="tabpanel" aria-labelledby="tasks-tab">
<div class="filters">
<label for="status-filter">Status<select id="status-filter"><option value="">All statuses</option>{status_options}</select></label>
<label for="phase-filter">Phase<select id="phase-filter"><option value="">All phases</option>{phase_options}</select></label>
<p class="count" aria-live="polite">Showing <span id="shown">{total}</span> of {total} tasks</p></div>
<div class="table"><table id="tasks"><thead><tr><th scope="col">Task</th><th scope="col">Work</th><th scope="col">Phase</th>
<th scope="col">Status</th><th scope="col">Agent</th>{token_heads}<th scope="col">Evidence or next step</th></tr></thead><tbody>{rows}</tbody>
<tfoot><tr><th scope="row" colspan="5">Shown tasks</th>{token_foot}<td></td></tr></tfoot></table></div>
{tokens}
<h2>Phases</h2><ul>{phases}</ul><h2>Pull request</h2><p>{escape(state['pr'])}</p>
<h2>Removed tasks</h2><ul>{archived}</ul></section>
<section id="activity-panel" role="tabpanel" aria-labelledby="activity-tab" hidden>
<h2>Activity</h2><p><small>Newest first.</small></p><ol reversed>{events}</ol></section>
</main><script>{SCRIPT}</script></body></html>"""


def place(output, name):
    data = (ASSETS / name).read_bytes()
    target = output / name
    if not target.is_file() or target.read_bytes() != data:
        target.write_bytes(data)


def copy_icon(output):
    """The square Sanduq mark as the page icon; a missing asset only drops the icon."""
    if not (ASSETS / ICON).is_file():
        return False
    place(output, ICON)
    return True


def copy_logos(output):
    """Place the Sanduq logo beside the report; the report still renders without it."""
    for name in LOGOS:
        if not (ASSETS / name).is_file():
            return False
    for name in LOGOS:
        place(output, name)
    return True


def plan_title(path):
    """The feature name from the plan's '# Tasks: <feature>' heading, if it has one."""
    for line in path.read_text(encoding='utf-8').splitlines():
        heading = re.match(r'^\s*#\s+Tasks:\s*(.+?)\s*#*\s*$', line, re.IGNORECASE)
        if heading:
            return heading.group(1)
    return None


def read_plan(path, parser):
    tasks, phases, identities = [], {}, set()
    phase = None
    for line in path.read_text(encoding='utf-8').splitlines():
        heading = re.match(r'^\s*#{2,3}\s+(Phase\b.*?)\s*#*\s*$', line, re.IGNORECASE)
        if heading:
            phase = heading.group(1).strip()
            phases.setdefault(phase, 'pending')
        match = re.match(r'\s*- \[([ xX])\]\s+(\S+)\s+(.+)', line)
        if match:
            check, identity, title = match.groups()
            if identity in identities:
                parser.error('Duplicate task ID: ' + identity)
            identities.add(identity)
            task = dict(id=identity, title=title, status='done' if check.lower() == 'x' else 'pending')
            if phase:
                task['phase'] = phase
            tasks.append(task)
    if not tasks:
        parser.error('No checkbox tasks found. Use: - [ ] T001 Description')
    return tasks, phases


def reconcile(state, tasks, phases):
    """Keep accepted evidence while requiring review of changed task definitions."""
    previous = {task['id']: task for task in state['tasks']}
    current = []
    changed_phases = set()
    for task in tasks:
        old = previous.pop(task['id'], None)
        if old is None:
            task['status'] = 'pending'
            state['events'].append('Added task ' + task['id'] + ': ' + task['title'])
        elif old['title'] != task['title'] or old.get('phase') != task.get('phase'):
            state['events'].append('Revised task; previous evidence: ' + json.dumps(old, ensure_ascii=False))
            has_phase = 'phase' in task
            task = {**old, **task, 'status': 'pending'}
            if not has_phase:
                task.pop('phase', None)
        else:
            current.append(old)
            continue
        if task.get('phase'):
            changed_phases.add(task['phase'])
        current.append(task)
    for task in previous.values():
        state.setdefault('archived_tasks', []).append(dict(task, removed_at=datetime.now(timezone.utc).isoformat()))
        state['events'].append('Removed task; previous evidence: ' + json.dumps(task, ensure_ascii=False))
    state['tasks'] = current
    for name, value in phases.items():
        state['phases'].setdefault(name, value)
    for name in changed_phases:
        if state['phases'][name] != 'pending':
            state['events'].append('Reopened phase ' + name + '; previous state: ' + state['phases'][name])
            state['phases'][name] = 'pending'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def reused(state, agent, task):
    """Whether this worker also served another task, so its log must be split by time."""
    for other in [*state['tasks'], *state.get('archived_tasks', [])]:
        if other is not task and (other.get('agent') == agent
                                  or any(e.get('agent') == agent for e in other.get('usage', []))):
            return True
    return False


def record_usage(state, args, parser):
    if args.id is not None:
        task = next((t for t in state['tasks'] if t['id'] == args.id), None)
        if task is None:
            parser.error('Unknown task ID: ' + args.id)
        since, until = args.since, args.until
        # A delegate result covers one run already; harness logs may span several tasks.
        if args.collect in ('claude', 'codex') and since is None and until is None                 and reused(state, args.agent, task):
            if not task.get('started_at'):
                parser.error('Agent ' + args.agent + ' also worked on other tasks. Mark ' + args.id +
                             ' running before assigning it, or pass --since, so its log can be split.')
            since, until = task['started_at'], task.get('ended_at')
        entries = task.setdefault('usage', [])
        # One entry per agent attempt. An unwindowed figure covers the whole log, so
        # it and any windowed figure for the same agent supersede each other.
        same = lambda e, n: e.get('agent') == n.get('agent') and (
            e.get('since') == n.get('since') or e.get('since') is None or n.get('since') is None)
    else:
        since, until = args.since, args.until
        entries = state.setdefault('overhead', [])
        same = lambda e, n: (e.get('agent'), e.get('label')) == (n.get('agent'), n.get('label'))
    entry = {'agent': args.agent, 'since': since, 'until': until, 'recorded_at': stamp()}
    if args.overhead is not None:
        entry['label'] = args.overhead
    if args.collect:
        try:
            measured = token_usage.collect(args.collect, args.agent, args.log, since, until)
            entry.update(measured, fidelity='exact')
        except (token_usage.UsageUnavailable, ValueError) as exc:
            # Keep the gap visible instead of recording a zero.
            entry.update(harness=args.collect, fidelity='unavailable', reason=str(exc))
            state['events'].append('Token usage unavailable for ' + args.agent + ': ' + str(exc))
    else:
        entry.update(fresh_input=args.fresh_input, cache_read=args.cached_input or 0,
                     cache_write=args.cache_write or 0, output=args.output_tokens or 0,
                     reasoning=args.reasoning, harness=args.harness, model=args.model, fidelity='reported')
    # Collecting the same agent and window again replaces the earlier figure; it never adds to it.
    entries[:] = [e for e in entries if not same(e, entry)] + [entry]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'task', 'event', 'phase', 'pr', 'usage'):
        sub = subs.add_parser(name)
        sub.add_argument('--output', required=True, type=Path)
        if name == 'init':
            sub.add_argument('--tasks', required=True, type=Path)
            sub.add_argument('--title', help="Report title; defaults to the plan's '# Tasks: <feature>' heading")
            sub.add_argument('--open', action='store_true')
        elif name == 'task':
            sub.add_argument('--id', required=True)
            sub.add_argument('--status', required=True, choices=('pending', 'running', 'done', 'blocked'))
            sub.add_argument('--agent')
            sub.add_argument('--note')
        elif name == 'event':
            sub.add_argument('--message', required=True)
        elif name == 'phase':
            sub.add_argument('--name', required=True)
            sub.add_argument('--status', required=True)
            sub.add_argument('--commit', default='')
        elif name == 'usage':
            scope = sub.add_mutually_exclusive_group(required=True)
            scope.add_argument('--id', help='Task the usage belongs to')
            scope.add_argument('--overhead', metavar='LABEL',
                               help='Work outside any task, such as "orchestrator" or "final review"')
            sub.add_argument('--agent', required=True, help='Host agent ID whose log is read')
            source = sub.add_mutually_exclusive_group(required=True)
            source.add_argument('--collect', choices=token_usage.HARNESSES,
                                help="Read the agent's own harness log")
            source.add_argument('--fresh-input', type=int, help='Self-reported counts when no log exists')
            sub.add_argument('--log', type=Path, help='Explicit log or delegate result.json path')
            sub.add_argument('--since', help='ISO-8601 window start; defaults to the task attempt when the agent is reused')
            sub.add_argument('--until', help='ISO-8601 window end')
            for flag in ('--cached-input', '--cache-write', '--output-tokens', '--reasoning'):
                sub.add_argument(flag, type=int)
            sub.add_argument('--harness')
            sub.add_argument('--model')
        else:
            sub.add_argument('--url', required=True)
            sub.add_argument('--status', required=True, choices=('open', 'merged'))
    args = parser.parse_args(argv)
    target = args.output / 'state.json'
    if args.command == 'init':
        tasks, phases = read_plan(args.tasks, parser)
        derived = plan_title(args.tasks)
        if target.exists():
            state = json.loads(target.read_text(encoding='utf-8'))
            reconcile(state, tasks, phases)
            # An explicit title always renames; the plan heading only replaces the generic default.
            title = args.title or (derived if state.get('title', DEFAULT_TITLE) == DEFAULT_TITLE else None)
            if title and title != state.get('title'):
                state['events'].append('Renamed report from ' + json.dumps(state.get('title')) + ' to ' + json.dumps(title))
                state['title'] = title
        else:
            state = dict(title=args.title or derived or DEFAULT_TITLE, tasks=tasks, phases=phases, events=[], pr='Not created')
    else:
        if not target.exists():
            parser.error('Initialize the report before updating it.')
        state = json.loads(target.read_text(encoding='utf-8'))
    if args.command == 'task':
        task = next((t for t in state['tasks'] if t['id'] == args.id), None)
        if task is None:
            parser.error('Unknown task ID: ' + args.id)
        task['status'] = args.status
        # Attempt timestamps split one reused worker's log between its tasks.
        if args.status == 'running':
            task['started_at'] = stamp()
            task.pop('ended_at', None)
        elif args.status in ('done', 'blocked'):
            task['ended_at'] = stamp()
        for key in ('agent', 'note'):
            if getattr(args, key) is not None:
                task[key] = getattr(args, key)
    elif args.command == 'event':
        state['events'].append(args.message)
    elif args.command == 'phase':
        state['phases'][args.name] = args.status + (' (' + args.commit + ')' if args.commit else '')
    elif args.command == 'pr':
        state['pr'] = args.status + ': ' + args.url
    elif args.command == 'usage':
        record_usage(state, args, parser)
    state['updated'] = stamp()
    args.output.mkdir(parents=True, exist_ok=True)
    state['logo'] = copy_logos(args.output)
    state['icon'] = copy_icon(args.output)
    atomic(target, json.dumps(state, indent=2) + '\n')
    atomic(args.output / 'index.html', render(state))
    if getattr(args, 'open', False):
        webbrowser.open((args.output / 'index.html').resolve().as_uri())
    print(args.output / 'index.html')


if __name__ == '__main__':
    main()
