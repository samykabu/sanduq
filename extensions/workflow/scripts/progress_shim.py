"""Forward the legacy `progress.py` subcommands to the Progress CLI when that extension is installed.

Used only by `scripts/progress.py` after `progress_bridge` found the Progress script. Everything here goes through
the Progress command line; no Progress code is imported. Legacy records are labelled origin legacy by Progress and
never override producer state. A legacy request with no faithful Progress mapping prints a compatibility error and
exits non-zero; it never succeeds silently.
"""
import json
import re
import sys
import tempfile
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import progress_bridge as bridge
import usage as token_usage

COMPAT_EXIT = 2
TASK_ID = re.compile(r'[A-Za-z]+\d+')
REF = re.compile(r'[LTWC]\d+', re.I)


class Compat(Exception):
    """A request that cannot be served; `code` is the process exit status. `plain` keeps a message verbatim
    (Progress' own error line or a legacy phrase); otherwise it is reported as a compatibility error."""

    def __init__(self, message, code=COMPAT_EXIT, plain=False):
        super().__init__(message)
        self.code, self.plain = code, plain


def stamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def feature_of(args, root):
    """`specs/<feature>` from --output (`specs/<feature>/workflow/progress`) or the init --tasks path."""
    for candidate in (getattr(args, 'output', None), getattr(args, 'tasks', None)):
        if candidate is None:
            continue
        path = Path(candidate)
        if not path.is_absolute():
            path = Path.cwd() / path
        try:
            parts = path.resolve().relative_to(root).parts
        except ValueError:
            parts = path.parts
        if 'specs' in parts:
            index = len(parts) - 1 - parts[::-1].index('specs')
            if len(parts) > index + 1:
                return 'specs/' + parts[index + 1]
    return None


class Forward:
    def __init__(self, root, feature):
        self.root, self.feature = root, feature

    def call(self, verb, *args, sub=None, tolerate=()):
        """Run one Progress verb; return its one-line stdout. Raise Compat with Progress' own exit code on failure."""
        argv = [verb] + (['--feature', self.feature] if self.feature else []) + ([sub] if sub else []) + list(args)
        result = bridge.run(self.root, argv)
        if result is None:
            raise Compat('Sanduq Progress is no longer installed', 70, plain=True)
        code, out, err = result
        line = (out.strip() or err.strip()).splitlines()[0] if (out.strip() or err.strip()) else ''
        if code != 0:
            if any(token in line for token in tolerate):
                return ''
            raise Compat(line or f'progress exited {code}', code, plain=True)
        return line

    def status(self):
        report = bridge.status(self.root, self.feature)
        if report is None:
            raise Compat('progress status is unavailable; run progress init for this feature', 2, plain=True)
        return report

    def ensure_init(self):
        if bridge.status(self.root, self.feature) is None:
            self.call('init')
        return self.status()


# ---- lookups over the status projection (JSON only) ---------------------------------------------------------------

def lane_task_ids(lane):
    tasks = lane.get('tasks') or {}
    found = list(tasks.get('active') or []) + list(tasks.get('waiting') or []) + list(tasks.get('done') or [])
    found += [b['task'] for b in tasks.get('blocked') or []]
    return found


def find_attempt(report, run):
    for lane in report.get('lanes') or []:
        for attempt in lane.get('attempts') or []:
            if attempt.get('run_id') == run:
                return lane, attempt
    return None, None


def summary_counts(report):
    tasks = report.get('tasks') or {}
    running, blocked = set(), set()
    groups = [lane.get('tasks') or {} for lane in report.get('lanes') or []] + [report.get('unassigned_tasks') or {}]
    for group in groups:
        running |= set(group.get('active') or [])
        blocked |= {b['task'] for b in group.get('blocked') or []}
    total = len(tasks)
    done = sum(1 for t in tasks.values() if t.get('done'))
    running -= {t for t, v in tasks.items() if v.get('done')}
    blocked -= {t for t, v in tasks.items() if v.get('done')}
    return {'done': done, 'total': total, 'running': len(running), 'blocked': len(blocked),
            'pending': max(0, total - done - len(running) - len(blocked))}


def summary_line(report):
    counts = summary_counts(report)
    return 'ok done={done} total={total} pending={pending} running={running} blocked={blocked}'.format(**counts)


# ---- lane handling ---------------------------------------------------------------------------------------------------

def ensure_lane(fwd, report, task, agent, attempt_wanted=False):
    """The facts lane owned by `agent` that carries `task`. The latest agent owns the task, as in the legacy state."""
    lanes = [lane for lane in report.get('lanes') or [] if lane.get('origin') == 'facts']
    mine = next((lane for lane in lanes if agent and lane.get('owner') == agent), None)
    if mine is None and agent is None:
        mine = next((lane for lane in report.get('lanes') or [] if task in lane_task_ids(lane)), None)
        if mine is not None and not FACTS_LANE.fullmatch(mine['id']):
            # A derived lane (coordinator, host child, delegation) is not addressable by lane/attempt facts: give the
            # task an ownerless facts lane so the attempt targets an id Progress accepts.
            return fwd.call('lane', 'new', '--tasks', task, '--label', mine.get('label') or 'coordinator').split()[1]
        if mine is None and attempt_wanted:
            return fwd.call('lane', 'new', '--tasks', task, '--label', 'coordinator').split()[1]
        return mine['id'] if mine else None
    for other in lanes:
        if other is not mine and task in lane_task_ids(other):
            rest = [t for t in lane_task_ids(other) if t != task]
            fwd.call('lane', other['id'], '--tasks', ','.join(rest))
            if not rest:
                fwd.call('lane', other['id'], '--close')
    if mine is None:
        line = fwd.call('lane', 'new', '--tasks', task, '--owner', agent, '--label', agent)
        return line.split()[1]
    held = lane_task_ids(mine)
    if task not in held:
        fwd.call('lane', mine['id'], '--tasks', ','.join(held + [task]))
    return mine['id']


FACTS_LANE = re.compile(r'L\d+')


def attempt_status(status):
    return {'running': 'running', 'done': 'done', 'blocked': 'blocked'}.get(status)


# ---- subcommands ----------------------------------------------------------------------------------------------------

def do_init(fwd, args):
    if args.title:
        raise Compat('init --title is not supported when Sanduq Progress is installed; Progress titles the report from '
                     'the tasks.md "# Tasks:" heading')
    fwd.call('init')
    if args.open:
        webbrowser.open(index_of(fwd, fwd.status()).resolve().as_uri())


def index_of(fwd, report):
    return fwd.root / ((report.get('feature') or {}).get('dir') or fwd.feature or 'specs') / 'progress' / '.view' / 'index.html'


def do_task(fwd, args):
    report = fwd.ensure_init()
    task = args.id
    if task not in (report.get('tasks') or {}):
        raise Compat(f'Unknown task ID: {task}', 2, plain=True)
    agent = args.agent
    note = args.note
    if args.status == 'pending':
        fwd.call('unblock', '--all-for', task, tolerate=('PROGRESS_NOT_FOUND',))
    lane = ensure_lane(fwd, report, task, agent, bool(attempt_status(args.status))) if args.status != 'pending' else None
    owner = agent
    if lane and not owner:
        owner = next((l.get('owner') for l in report['lanes'] if l['id'] == lane and l.get('owner')), None)
    if args.status == 'blocked':
        if note and REF.fullmatch(note.strip()):
            by = note.strip().upper()
        else:
            by = 'ext:"' + (note or 'blocked (legacy)').replace('"', "'") + '"'
        fwd.call('block', task, '--by', by)
    elif args.status == 'running':
        fwd.call('unblock', '--all-for', task, tolerate=('PROGRESS_NOT_FOUND',))
    elif args.status == 'done':
        fwd.call('unblock', '--all-for', task, tolerate=('PROGRESS_NOT_FOUND',))
    if note and args.status != 'blocked':
        fwd.call('note', f'{task} {args.status}: {note}', '--target', task)
    elif args.status in ('done', 'pending') and not lane:
        fwd.call('note', f'{task} {args.status}', '--target', task)
    if lane and attempt_status(args.status):
        run = f'legacy-{task}-{owner or "unassigned"}'
        argv = ['--lane', lane, '--run', run, '--status', args.status]
        if args.status == 'running':  # a new attempt window: reset the end, as the legacy command did
            argv += ['--started', stamp(), '--ended', '']
        else:
            argv += ['--ended', stamp()]
        fwd.call('attempt', *argv, sub='record')


def do_event(fwd, args):
    fwd.ensure_init()
    fwd.call('note', args.message)


def do_phase(fwd, args):
    fwd.ensure_init()
    fwd.call('note', f'Phase {args.name}: {args.status}' + (f' ({args.commit})' if args.commit else ''))


def do_pr(fwd, args):
    fwd.ensure_init()
    fwd.call('note', f'PR {args.status}: {args.url}')


def do_sync(fwd, args):
    fwd.ensure_init()
    fwd.call('refresh')


def usage_entry(args):
    """The legacy measurement, produced by Workflow's own usage reader exactly as the legacy command did."""
    since, until = args.since, args.until
    entry = {'agent': args.agent, 'since': since, 'until': until}
    if args.collect:
        try:
            measured = token_usage.collect(args.collect, args.agent, args.log, since, until)
            entry.update(measured, fidelity='exact')
        except (token_usage.UsageUnavailable, ValueError) as exc:
            entry.update(harness=args.collect, fidelity='unavailable', reason=str(exc))
    else:
        entry.update(fresh_input=args.fresh_input, cache_read=args.cached_input or 0, cache_write=args.cache_write or 0,
                     output=args.output_tokens or 0, reasoning=args.reasoning, harness=args.harness, model=args.model,
                     fidelity='reported')
    if args.log is not None:
        entry['log'] = str(args.log)
    return entry


def do_usage(fwd, args):
    report = fwd.ensure_init()
    lane, run, started, ended, status = None, None, None, None, 'done'
    since, until = args.since, args.until
    if args.id is not None:
        task = args.id
        if task not in (report.get('tasks') or {}):
            raise Compat(f'Unknown task ID: {task}', 2, plain=True)
        run = f'legacy-{task}-{args.agent}'
        owner_lane, known = find_attempt(report, run)
        lane = (owner_lane or {}).get('id') or ensure_lane(fwd, report, task, args.agent)
        if known:
            started, ended, status = known.get('started_at'), known.get('ended_at'), known.get('status') or status
        current = next((l for l in fwd.status().get('lanes') or [] if l.get('id') == lane), {})
        reused = len(set(lane_task_ids(current))) > 1
        if args.collect in ('claude', 'codex') and since is None and until is None and reused:
            if not started:
                raise Compat(f'Agent {args.agent} also worked on other tasks. Mark {task} running before assigning it, '
                             'or pass --since, so its log can be split.', 2, plain=True)
            args.since, args.until = started, ended
    else:
        run = re.sub(r'[^A-Za-z0-9._-]+', '-', f'legacy-overhead-{args.overhead}-{args.agent}')[:80]
    entry = usage_entry(args)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'usage.json'
        path.write_text(json.dumps(entry), encoding='utf-8')
        argv = ['--run', run, '--status', status, '--usage-json', str(path)]
        argv += ['--lane', lane] if lane else ['--overhead', args.overhead]
        if started:
            argv += ['--started', started]
        if ended:
            argv += ['--ended', ended]
        fwd.call('attempt', *argv, sub='record')
    if entry.get('fidelity') == 'unavailable':
        fwd.call('note', f"Token usage unavailable for {args.agent}: {entry.get('reason')}", *(['--target', args.id] if args.id else []))


HANDLERS = {'init': do_init, 'task': do_task, 'event': do_event, 'phase': do_phase, 'pr': do_pr, 'usage': do_usage,
            'sync': do_sync}


def forward(args, root):
    """Run one legacy subcommand against Progress. Returns the process exit code."""
    quiet = args.summary
    try:
        if args.json:
            raise Compat('--json is not supported when Sanduq Progress is installed; use progress.py status --json')
        fwd = Forward(root, feature_of(args, root))
        HANDLERS[args.command](fwd, args)
        report = fwd.status()
    except Compat as exc:
        message = str(exc) if exc.plain else f'compatibility: {exc}'
        print(('error ' + message) if quiet else message, file=None if quiet else sys.stderr)
        return exc.code or COMPAT_EXIT
    if quiet:
        print(summary_line(report))
    else:
        print(index_of(fwd, report))
    return 0
