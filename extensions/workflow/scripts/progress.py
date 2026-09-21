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


def render(state):
    escape = lambda value: html.escape(str(value), quote=True)
    rows = ''.join('<tr>' + ''.join('<td>' + escape(task.get(key, '')) + '</td>'
                   for key in ('id', 'title', 'status', 'agent', 'note')) + '</tr>'
                   for task in state['tasks'])
    events = ''.join('<li>' + escape(event) + '</li>' for event in state['events'])
    phases = ''.join('<li>' + escape(name) + ': ' + escape(value) + '</li>'
                     for name, value in state['phases'].items())
    archived = ''.join('<li>' + escape(json.dumps(task, ensure_ascii=False)) + '</li>'
                       for task in state.get('archived_tasks', []))
    done = sum(task['status'] == 'done' for task in state['tasks'])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="5"><title>Implementation progress</title>
<style>body{{font:16px system-ui;margin:40px auto;max-width:1100px;padding:0 24px;background:#f6f8fc;color:#15233c}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #ccd4df}}td{{overflow-wrap:anywhere}}small{{color:#4f6078}}progress{{width:100%}}</style>
<h1>{escape(state['title'])}</h1><p>{done} of {len(state['tasks'])} tasks complete</p>
<progress value="{done}" max="{max(1, len(state['tasks']))}"></progress>
<p><small>Updated {escape(state['updated'])}. This page refreshes every five seconds.</small></p>
<table><thead><tr><th>Task</th><th>Work</th><th>Status</th><th>Agent</th><th>Evidence or next step</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Phases</h2><ul>{phases}</ul><h2>Pull request</h2><p>{escape(state['pr'])}</p>
<h2>Removed tasks</h2><ul>{archived}</ul>
<h2>Activity</h2><ul>{events}</ul></html>'''


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
            sub.add_argument('--title', default='Implementation progress')
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
        if target.exists():
            state = json.loads(target.read_text(encoding='utf-8'))
            reconcile(state, tasks, phases)
        else:
            state = dict(title=args.title, tasks=tasks, phases=phases, events=[], pr='Not created')
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
    atomic(target, json.dumps(state, indent=2) + '\n')
    atomic(args.output / 'index.html', render(state))
    if getattr(args, 'open', False):
        webbrowser.open((args.output / 'index.html').resolve().as_uri())
    print(args.output / 'index.html')


if __name__ == '__main__':
    main()
