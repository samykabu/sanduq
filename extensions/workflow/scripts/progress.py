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
import webbrowser

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
td:nth-child(1),td:nth-child(4),td:nth-child(5){white-space:nowrap;overflow-wrap:normal}td:nth-child(3){min-width:160px}td:nth-child(2){min-width:280px}tbody tr:last-child td{border-bottom:0}
.status{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.85rem;white-space:nowrap}
.status-pending{background:var(--pending)}.status-running{background:var(--running)}.status-done{background:var(--done)}.status-blocked{background:var(--blocked)}
h2{font-size:1.05rem;color:var(--brand);margin:28px 0 8px}ul,ol{padding-left:22px}li{margin:4px 0;overflow-wrap:anywhere}
small{color:var(--muted)}
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
  function filter(){var shown=0;rows.forEach(function(r){var ok=(!status.value||r.dataset.status===status.value)&&(!phase.value||r.dataset.phase===phase.value);r.hidden=!ok;if(ok)shown++;});count.textContent=shown;}
  function option(el,value){return [].some.call(el.options,function(o){return o.value===value;})?value:'';}
  var q=read();status.value=option(status,q.status||'');phase.value=option(phase,q.phase||'');select(q.tab==='activity'?'activity':'tasks');filter();
  tabs.forEach(function(t,i){t.addEventListener('click',function(){select(t.dataset.tab);write();});
    t.addEventListener('keydown',function(e){var d=e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0;if(!d)return;e.preventDefault();var n=tabs[(i+d+tabs.length)%tabs.length];n.focus();select(n.dataset.tab);write();});});
  [status,phase].forEach(function(el){el.addEventListener('change',function(){filter();write();});});
  setTimeout(function(){location.reload();},5000);
})();
"""


def render(state):
    escape = lambda value: html.escape(str(value), quote=True)
    # Offer only phases that have tasks, in plan order, so the filter never empties the table.
    phase_names = list(dict.fromkeys(t['phase'] for t in state['tasks'] if t.get('phase')))
    rows = ''.join(
        f'<tr data-status="{escape(task["status"])}" data-phase="{escape(task.get("phase", ""))}">'
        f'<td>{escape(task["id"])}</td><td>{escape(task["title"])}</td><td>{escape(task.get("phase", ""))}</td>'
        f'<td><span class="status status-{escape(task["status"])}">{escape(task["status"])}</span></td>'
        f'<td>{escape(task.get("agent", ""))}</td><td>{escape(task.get("note", ""))}</td></tr>'
        for task in state['tasks'])
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
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<noscript><meta http-equiv="refresh" content="5"></noscript><title>{escape(state['title'])}</title>
<style>{STYLE}</style></head><body><main>
<header>{logo}<div class="summary"><h1>{escape(state['title'])}</h1>
<p>{done} of {total} tasks complete</p><progress value="{done}" max="{max(1, total)}" aria-label="Tasks complete"></progress>
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
<th scope="col">Status</th><th scope="col">Agent</th><th scope="col">Evidence or next step</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>Phases</h2><ul>{phases}</ul><h2>Pull request</h2><p>{escape(state['pr'])}</p>
<h2>Removed tasks</h2><ul>{archived}</ul></section>
<section id="activity-panel" role="tabpanel" aria-labelledby="activity-tab" hidden>
<h2>Activity</h2><p><small>Newest first.</small></p><ol reversed>{events}</ol></section>
</main><script>{SCRIPT}</script></body></html>"""


def copy_logos(output):
    """Place the Sanduq logo beside the report; the report still renders without it."""
    for name in LOGOS:
        if not (ASSETS / name).is_file():
            return False
    for name in LOGOS:
        data = (ASSETS / name).read_bytes()
        target = output / name
        if not target.is_file() or target.read_bytes() != data:
            target.write_bytes(data)
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'task', 'event', 'phase', 'pr'):
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
        for key in ('agent', 'note'):
            if getattr(args, key) is not None:
                task[key] = getattr(args, key)
    elif args.command == 'event':
        state['events'].append(args.message)
    elif args.command == 'phase':
        state['phases'][args.name] = args.status + (' (' + args.commit + ')' if args.commit else '')
    elif args.command == 'pr':
        state['pr'] = args.status + ': ' + args.url
    state['updated'] = datetime.now(timezone.utc).isoformat()
    args.output.mkdir(parents=True, exist_ok=True)
    state['logo'] = copy_logos(args.output)
    atomic(target, json.dumps(state, indent=2) + '\n')
    atomic(args.output / 'index.html', render(state))
    if getattr(args, 'open', False):
        webbrowser.open((args.output / 'index.html').resolve().as_uri())
    print(args.output / 'index.html')


if __name__ == '__main__':
    main()
