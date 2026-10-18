#!/usr/bin/env python3
"""Sanduq Progress CLI. One-line output per verb; exit 0 ok, 2 usage, 3 refused, 4 lock busy.

Run `progress.py --help`. The report is a projection rebuilt from producers on every refresh."""
import argparse
import json
import os
import posixpath
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sanduq_progress import facts as factslib, hook as hooklib, model, refresh as refreshlib, render_md  # noqa: E402
from sanduq_progress import selfreport, snapshot, statusline as statuslib  # noqa: E402
from sanduq_progress.collect import plan as plancol, runs as runscol, tasks as taskscol  # noqa: E402
from sanduq_progress.lock import Lock, LockBusy  # noqa: E402
from sanduq_progress.paths import (ASSETS, NAME, PLAN_REGISTRY, PLAN_ROOT, RESERVED_ID, TASK_REF, Ctx, ProgressError, find_root, is_default_plan_dir,  # noqa: E402
                                   default_excludes, git_exclude, list_plans, normalise_plan_dir, plan_info, resolve_feature, resolve_target, slugify)
from sanduq_progress.util import atomic_write, diag, ensure_local_dir, iso, parse_time, read_json, refuse_link, utcnow, write_json  # noqa: E402

FALLBACK_CSS = (':root{--bg:#f6f7f4;--surface:#fff;--text:#1b2a24;--muted:#4e5d56;--line:#d5dcd7;--brand:#233c32;'
                '--accent:#c65b36;--active:#dcebf7;--waiting:#e9ece9;--blocked:#f8e0d6;--done:#dcefe2;--failed:#f4c7c0}\n')


ATTEMPT_STATUSES = ('pending', 'running', 'done', 'blocked', 'failed', 'successful')
USAGE_COUNTERS = ('fresh_input', 'cache_read', 'cache_write', 'output', 'reasoning')
RUNS_SCHEMA = 'progress.runs.v1'
RUNS_CAVEATS = ('elapsed_seconds is wall time between start and end (or now), not active work time',
                'phase "stalled" is a heuristic: no journal event for stall_seconds; a quiet worker may be healthy',
                'harness_status is the harness verdict, not acceptance; Workflow records acceptance in its ledger')


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ProgressError('PROGRESS_USAGE', message.replace('\n', ' '), 2)


def now():
    stamp = os.environ.get('SANDUQ_PROGRESS_NOW')
    if stamp:
        return datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(timezone.utc)
    return utcnow()


def build_parser():
    p = Parser(prog='progress', description=__doc__)
    p.add_argument('--root', help=argparse.SUPPRESS)
    common = Parser(add_help=False)
    common.add_argument('--feature', help='Spec Kit feature directory, e.g. specs/001-name')
    common.add_argument('--plan', help='plan report by name or path (init: the Markdown checklist file to read)')
    common.add_argument('--actor', default=os.environ.get('SANDUQ_PROGRESS_ACTOR', 'agent:coordinator'))
    sub = p.add_subparsers(dest='verb', parser_class=Parser, required=True)

    def verb(name, **kw):
        return sub.add_parser(name, parents=[common], **kw)

    s = verb('init')
    s.add_argument('--statusline', choices=('yes', 'no'), default='no')
    s.add_argument('--theme')
    s.add_argument('--name', help='plan mode: report name (default: the plan file name, slugified)')
    s.add_argument('--dir', help='plan mode: report directory inside the repository (default .progress/<name>)')
    s.add_argument('--rebind', action='store_true', help='plan mode: let an existing report follow a different plan file')
    s = verb('bind')
    s.add_argument('--session')
    s.add_argument('--host', choices=('claude', 'codex'), default='claude')
    s.add_argument('--model', help='coordinator self-report: the model this session runs (shown as self-reported)')
    s.add_argument('--effort', help='coordinator self-report: the reasoning effort this session runs (shown as self-reported)')
    s = verb('refresh')
    s.add_argument('--final', action='store_true', help='accepted for compatibility; every refresh is a full one')
    s.add_argument('--verbose', action='store_true')
    s = verb('status')
    s.add_argument('--json', action='store_true')
    s.add_argument('--schema', choices=('v2', 'v3'), default='v3', help='projection schema for --json (default v3)')
    s = verb('lane')
    s.add_argument('id')
    s.add_argument('--tasks')
    s.add_argument('--owner')
    s.add_argument('--label')
    s.add_argument('--harness')
    s.add_argument('--model')
    s.add_argument('--effort')
    s.add_argument('--close', action='store_true')
    s.add_argument('--workstream', action='store_true', help='mark the lane as a workstream (assignment of tasks to an owner)')
    s = verb('block')
    s.add_argument('target')
    s.add_argument('--by', required=True)
    s = verb('unblock')
    s.add_argument('id', nargs='?')
    s.add_argument('--all-for')
    s = verb('decide')
    d = s.add_subparsers(dest='action', parser_class=Parser, required=True)
    ask = d.add_parser('ask')
    ask.add_argument('question')
    ask.add_argument('--options', required=True)
    made = d.add_parser('made')
    made.add_argument('id')
    made.add_argument('selected')
    made.add_argument('--by', choices=('user', 'agent-recommendation', 'assumption'), required=True)
    made.add_argument('--evidence')
    s = verb('note')
    s.add_argument('text')
    s.add_argument('--target')
    s = verb('attempt')
    d = s.add_subparsers(dest='action', parser_class=Parser, required=True)
    rec = d.add_parser('record')
    where = rec.add_mutually_exclusive_group(required=True)
    where.add_argument('--lane')
    where.add_argument('--overhead', metavar='LABEL')
    rec.add_argument('--run', required=True)
    rec.add_argument('--status', required=True, choices=ATTEMPT_STATUSES)
    rec.add_argument('--started')
    rec.add_argument('--ended')
    rec.add_argument('--usage-json', metavar='PATH')
    s = verb('runs')
    s.add_argument('--json', action='store_true')
    s.add_argument('--runs-dir', action='append', default=[])
    s.add_argument('--now')
    s.add_argument('--stall-seconds', type=int, default=runscol.DEFAULT_STALL_SECONDS)
    verb('theme', add_help=False)  # every other token goes to the theme module
    s = verb('export')
    s.add_argument('--format', choices=('md', 'json'), default='md')
    s.add_argument('--schema', choices=('v2', 'v3'), default='v3', help='projection schema to export (default v3)')
    s.add_argument('--out')
    s = verb('hook')
    s.add_argument('event')
    s.add_argument('--host', choices=('claude', 'codex'))
    s = verb('statusline')
    s.add_argument('action', nargs='?', choices=('run', 'install', 'uninstall'), default='run')
    s = sub.add_parser('hooks')
    s.add_argument('action', choices=('install', 'uninstall', 'status'))
    s.add_argument('--host', choices=('claude', 'codex'))
    s.add_argument('--scope', choices=('project', 'user'), default='project')
    s.add_argument('--force-both', action='store_true', help='install even when this installer already registered the hooks in the other scope')
    s.add_argument('--python', help='interpreter command written into the hook (default: python on Windows, python3 elsewhere)')
    return p


def target_ctx(a, root):
    """The report this invocation works on: --plan, --feature, or the one active report."""
    return Ctx(root, resolve_target(root, a.plan, a.feature))


def require_init(ctx):
    if not ctx.dir.is_dir():
        raise ProgressError('PROGRESS_NOT_INITIALIZED', 'run progress init first', 2)


class locked:
    """Feature lock for verbs: 3 retries at 200 ms, then exit 4."""

    def __init__(self, ctx):
        self.lock = Lock(ctx.lock, retries=3, delay=0.2)

    def __enter__(self):
        try:
            return self.lock.acquire()
        except LockBusy:
            raise ProgressError('PROGRESS_LOCK_BUSY', 'another progress command is running; retry', 4) from None

    def __exit__(self, *exc):
        self.lock.release()
        return False


def write_theme_css(ctx):
    """Generate theme.css through the theme module (owned by the UI lane); minimal fallback otherwise."""
    try:
        from sanduq_progress import theme
        theme.write_assets(ctx.view, theme.resolve(ctx.root))
    except Exception as exc:
        diag(ctx.diag, f'theme unavailable, wrote fallback css: {type(exc).__name__}', now())
        atomic_write(ctx.view / 'theme.css', FALLBACK_CSS)


def copy_assets(ctx):
    if not ASSETS.is_dir():
        diag(ctx.diag, f'ui assets not found at {ASSETS.name}; view not installed', now())
        return False
    for src in sorted(p for p in ASSETS.rglob('*') if p.is_file() and p.name != 'theme.css'):
        target = ctx.view / src.relative_to(ASSETS)
        target.parent.mkdir(parents=True, exist_ok=True)
        refuse_link(target)  # copyfile would write through a link
        import shutil
        shutil.copyfile(src, target)
    return True


def refresh_now(ctx):
    return refreshlib.refresh(ctx, now())


# ---- verbs ----------------------------------------------------------------------------------------------------

def plan_source_ref(root, path):
    """(reference stored in tracked files, absolute path or None). A plan inside the repository is stored repo-relative; any
    other is `external:<file name>` and its absolute path stays in the git-ignored `.host/plan-source.json`."""
    resolved = Path(os.path.realpath(str(path)))
    try:
        return resolved.relative_to(Path(os.path.realpath(str(root)))).as_posix(), None
    except ValueError:
        return 'external:' + resolved.name, str(resolved)


def register_plan_dir(root, directory):
    """Record a report directory outside .progress/ in the tracked registry so --plan NAME finds it."""
    if is_default_plan_dir(directory):
        return
    registry = Path(root) / PLAN_REGISTRY
    data = read_json(registry, {})
    dirs = data.get('dirs') if isinstance(data, dict) and isinstance(data.get('dirs'), list) else []
    if directory not in dirs:
        write_json(registry, {'dirs': sorted([*dirs, directory])})


def init_plan(a, root):
    """Create (or refresh) the report of a Markdown checklist. The plan file is only ever read."""
    wanted = Path(a.plan)
    candidates = [wanted] if wanted.is_absolute() else [Path.cwd() / wanted, Path(root) / wanted]
    path = next((c for c in candidates if c.is_file()), None)
    if path is None:
        known = plancol_find(root, a.plan)
        if known and not (a.name or a.dir):
            return Ctx(root, known), None, None
        raise ProgressError('PROGRESS_PLAN_MISSING', f'plan file not found: {str(a.plan)[:80]}', 2)
    source, absolute = plan_source_ref(root, path)
    name = a.name if a.name else slugify(path.stem)
    if not NAME.fullmatch(name):
        raise ProgressError('PROGRESS_USAGE', '--name takes lowercase letters, digits, dot, dash and underscore (64 at most)', 2)
    if a.dir is not None:
        directory = normalise_plan_dir(root, a.dir)
        if not directory or directory == PLAN_ROOT or directory.startswith(PLAN_ROOT + '/.'):
            raise ProgressError('PROGRESS_USAGE', '--dir must be a directory inside the repository (not .git, nothing under specs/)', 2)
    else:
        directory = f'{PLAN_ROOT}/{name}'
    ctx = Ctx(root, directory)
    check_plan_dir(ctx)
    existing = plan_info(root, directory)
    if existing.get('source') and not a.rebind:
        if existing['source'] != source or (absolute and known_external_identity(ctx) not in (None, source_identity(absolute))):
            raise ProgressError('PROGRESS_PLAN_EXISTS', f"{directory} already reports {existing['source'][:60]}; pass --name or --dir, or --rebind to follow this plan", 3)
    return ctx, {'schema': PLAN_SCHEMA, 'name': existing.get('name') or name, 'source': source,
                 'ids': existing.get('ids') or [], 'next': existing.get('next') or 0}, absolute


PLAN_SCHEMA = 'progress.plan.v1'


def source_identity(absolute):
    """Fingerprint of a resolved plan path: what tells two plan files with the same name apart."""
    import hashlib
    return hashlib.sha256(os.path.normcase(os.path.realpath(str(absolute))).encode('utf-8')).hexdigest()[:16]


def known_external_identity(ctx):
    data = read_json(ctx.plan_source_file, {})
    if not isinstance(data, dict):
        return None
    return data.get('fingerprint') or (source_identity(data['path']) if isinstance(data.get('path'), str) else None)


def check_plan_dir(ctx):
    """Refuse, before any write, a report directory that holds something that is not a Progress plan report."""
    if ctx.plan_file.exists() or ctx.plan_file.is_symlink():
        data = read_json(ctx.plan_file, None)
        if not (isinstance(data, dict) and data.get('schema') == PLAN_SCHEMA):
            raise ProgressError('PROGRESS_DIR_CONFLICT', f'{ctx.feature}/plan.json is not a Progress plan report; pick another --dir', 3)
    elif ctx.facts.exists() or ctx.dir.is_file():
        raise ProgressError('PROGRESS_DIR_CONFLICT', f'{ctx.feature} already holds other files of its own; pick another --dir', 3)


def plancol_find(root, value):
    from sanduq_progress.paths import find_plan
    return find_plan(root, value)


def cmd_init(a, root):
    if a.theme:
        check_theme_preset(a.theme)  # before anything is created
    if a.plan and a.feature:
        raise ProgressError('PROGRESS_USAGE', 'give --plan or --feature, not both', 2)
    if (a.name or a.dir) and not a.plan:
        raise ProgressError('PROGRESS_USAGE', '--name and --dir belong to init --plan PATH', 2)
    plan_doc = absolute = None
    if a.plan:
        ctx, plan_doc, absolute = init_plan(a, root)
        feature = ctx.feature
    else:
        feature = resolve_target(root, None, a.feature, creating=True)
        ctx = Ctx(root, feature)
    rel = ctx.dir.relative_to(Path(root)).as_posix()
    extra = (feature,) if plan_doc is not None and not is_default_plan_dir(feature) else ()  # `.progress/<name>` is covered by the wildcards
    git_exclude(root, default_excludes(root, extra))
    preflight_local_dirs(ctx, root, rel)  # before anything is registered or written
    ctx.dir.mkdir(parents=True, exist_ok=True)
    ensure_local_dir(ctx.view)
    ctx.cfg_dir.mkdir(parents=True, exist_ok=True)
    if plan_doc is not None:
        register_plan_dir(root, feature)
        write_json(ctx.plan_file, plan_doc)
        if absolute:
            ensure_local_dir(ctx.host_dir)
            write_json(ctx.plan_source_file, {'path': absolute, 'fingerprint': source_identity(absolute)})
    if not ctx.config.exists():
        write_json(ctx.config, ctx.config_data())
    if not ctx.facts.exists():
        ctx.facts.touch()
    git_exclude(root)
    copy_assets(ctx)
    with locked(ctx):
        state = refreshlib.read_state(ctx)
        state.setdefault('started_at', iso(now()))
        write_json(ctx.state, state)
        write_theme_css(ctx)
        if a.theme:
            run_theme(ctx, ['--preset', a.theme], quiet=True)
        refresh_now(ctx)
    if a.statusline == 'yes':
        statuslib.install(root)
    nonce = snapshot.create_pending(ctx, now())
    print(f'progress: ready {ctx.feature}{"" if ctx.is_plan else "/progress"}/.view/index.html bind={nonce}')
    return 0


def check_plan_excluded(root, directory):
    from sanduq_progress.paths import check_excluded
    check_excluded(root, directory)


def preflight_local_dirs(ctx, root, directory):
    """Create .host/ and .view/ with their nested `*` .gitignore, then check git ignores every local-only file, so the
    check sees what git will really see (the nested file wins over parent re-include rules). A refused check removes
    exactly what this call created: files, then directories, deepest first. Nothing is registered at this point."""
    made = []
    probe = ctx.dir
    while not probe.exists() and probe != Path(root):
        made.append(probe)
        probe = probe.parent
    for leaf in (ctx.host_dir, ctx.view):
        if not leaf.exists():
            made.append(leaf)
        if not (leaf / '.gitignore').exists():
            made.append(leaf / '.gitignore')
    try:
        ensure_local_dir(ctx.host_dir)
        ensure_local_dir(ctx.view)
        check_plan_excluded(root, directory)
    except BaseException:
        for item in sorted(set(made), key=lambda q: len(q.parts), reverse=True):
            try:
                item.unlink() if item.is_file() or item.is_symlink() else item.rmdir()
            except OSError:
                pass
        raise


def check_theme_preset(name):
    try:
        from sanduq_progress import theme
    except Exception:
        raise ProgressError('PROGRESS_THEME_UNAVAILABLE', 'theme module not available', 2) from None
    if name not in theme.PRESETS:
        raise ProgressError('PROGRESS_THEME_INVALID', f'unknown preset {name[:40]}', 2)


def run_theme(ctx, rest, quiet=False):
    try:
        from sanduq_progress import theme
    except Exception:
        atomic_write(ctx.view / 'theme.css', FALLBACK_CSS)
        raise ProgressError('PROGRESS_THEME_UNAVAILABLE', '', 2) from None
    if quiet:
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            code = theme.cli(rest, project_root=ctx.root)
    else:
        code = theme.cli(rest, project_root=ctx.root)
    if code == 0:
        write_theme_css(ctx)
    return code


def cmd_theme(a, root):
    # theme.json is project-level; theme.cli rewrites theme.css/layout.js only in feature views that exist.
    try:
        from sanduq_progress import theme
    except Exception:
        raise ProgressError('PROGRESS_THEME_UNAVAILABLE', '', 2) from None
    return theme.cli(a.rest, project_root=root)


def cmd_bind(a, root):
    ctx = target_ctx(a, root)
    require_init(ctx)
    if a.model or a.effort:
        # Self-report: stored in .host/ (durable, git-ignored), scoped to this worktree and feature, and to the session when
        # one is given (otherwise an explicit "session unknown" report). Host observations always win per field.
        values = {k: factslib.sanitise(v, ctx.root, 80) for k, v in (('model', a.model), ('effort', a.effort)) if v}
        with locked(ctx):
            selfreport.write(ctx, a.host, a.session, values, now(), actor=a.actor)
            if a.session:
                snapshot.bind_session(ctx, a.host, a.session, now())
            refresh_now(ctx)
        print(f"progress: self-report {', '.join(sorted(values))} ({a.host}{', session ' + a.session if a.session else ', session unknown'})")
        return 0
    if a.session:
        snapshot.bind_session(ctx, a.host, a.session, now())
        print(f'progress: bound {a.session}')
    else:
        print(f'progress: pending bind={snapshot.create_pending(ctx, now())}')
    return 0


def cmd_refresh(a, root):
    ctx = target_ctx(a, root)
    require_init(ctx)
    with locked(ctx):
        report = refresh_now(ctx)
    if a.verbose:
        print(f"progress: refreshed rev {report['rev']}")
    return 0


def summary_line(report):
    """The one-line status. It reads the v2 summary keys (the line is a long-standing consumer contract)."""
    s = report['summary']
    return (f"progress: {s['tasks_done']}/{s['tasks_total']} tasks, {s['lanes_active']} lanes active, "
            f"{s['blocked']} blocked, {s['decisions_pending']} decisions pending (rev {report['rev']})")


def cmd_status(a, root):
    ctx = target_ctx(a, root)
    require_init(ctx)
    state = refreshlib.read_state(ctx)
    wanted = model.schema_name(a.schema)
    v3, v2 = model.build_pair(ctx, now(), int(state.get('rev') or 0), state, want_v3=a.json and wanted == model.SCHEMA_V3)
    if a.json:
        print(json.dumps(v3 if wanted == model.SCHEMA_V3 else v2, indent=2, ensure_ascii=False))
    else:
        print(summary_line(v2) + codex_hint(root))
    return 0


def codex_hint(root):
    """Cheap: only when no Codex session is bound, and then one small read of the user's Codex config."""
    try:
        from sanduq_progress import hooks_install
        sessions = snapshot._load(snapshot.project_dir(root) / 'bindings.json').get('sessions', {})
        if any(str(k).startswith('codex:') for k in sessions):
            return ''
        return ' no bound session (codex hooks not approved?)' if hooks_install.codex_unapproved(root) else ''
    except Exception:
        return ''


def mutate(ctx, a, make):
    """Run `make(loaded_facts) -> (records, output_line)` under the lock, append, refresh."""
    require_init(ctx)
    with locked(ctx):
        loaded = factslib.load(ctx.facts)
        records, line = make(loaded)
        for record in records:
            factslib.check(record, ctx.root)
        for record in records:
            factslib.append(ctx.facts, record, root=ctx.root)
        refresh_now(ctx)
    print(line)
    return 0


def cmd_lane(a, root):
    ctx = target_ctx(a, root)

    def make(loaded):
        current = {r['id']: r for r in loaded['current']}
        ident = factslib.next_id(loaded['all'], 'lane') if a.id.lower() == 'new' else a.id.upper()
        if not re.fullmatch(r'L\d+', ident):
            raise ProgressError('PROGRESS_USAGE', 'lane id must look like L1 (or "new")', 2)
        old = current.get(ident, {})
        try:
            tasks = taskscol.expand(a.tasks) if a.tasks is not None else old.get('tasks', [])
        except ValueError as exc:
            raise ProgressError('PROGRESS_USAGE', f'bad task range {exc}', 2) from None
        requested = dict(old.get('requested') or {'harness': None, 'model': None, 'effort': None})
        for key in ('harness', 'model', 'effort'):
            if getattr(a, key) is not None:
                requested[key] = factslib.sanitise(getattr(a, key), ctx.root, 60)
        extra = {'semantics': 'workstream'} if a.workstream else {k: old[k] for k in ('semantics',) if k in old}
        record = factslib.make(
            'lane', ident, a.actor, now=now(), tasks=tasks, **extra,
            owner=factslib.sanitise(a.owner, ctx.root, 80) if a.owner is not None else old.get('owner'),
            label=factslib.sanitise(a.label, ctx.root, 60) if a.label is not None else old.get('label') or ident,
            requested=requested, state='closed' if a.close else 'open' if (a.tasks is not None or not old) else old.get('state', 'open'))
        return [record], f"progress: {ident} {record['state']} {len(tasks)} tasks"
    return mutate(ctx, a, make)


def parse_by(text, root):
    text = text.strip()
    if text.lower().startswith('ext:'):
        return {'type': 'external', 'ref': factslib.sanitise(text[4:].strip().strip('"'), root, 120)}
    ident = text.upper()
    if re.fullmatch(r'[LWC]\d+', ident):
        return {'type': 'lane', 'ref': ident}
    if re.fullmatch(r'(SD|D)\d+', ident):
        return {'type': 'decision', 'ref': ident}
    if re.fullmatch(TASK_REF, ident) and not RESERVED_ID.fullmatch(ident):
        return {'type': 'task', 'ref': ident}
    raise ProgressError('PROGRESS_USAGE', '--by takes a lane (L2), task (T003 or P003), decision (SD2) or ext:"text"', 2)


def cmd_block(a, root):
    ctx = target_ctx(a, root)
    target = a.target.upper()

    def make(loaded):
        if not (re.fullmatch(r'[LWC]\d+', target) or (re.fullmatch(TASK_REF, target) and not RESERVED_ID.fullmatch(target))):
            raise ProgressError('PROGRESS_USAGE', 'block target is a task or lane id', 2)
        by = parse_by(a.by, ctx.root)
        for item in loaded['current']:
            if item['kind'] == 'block' and item.get('state') == 'open' and item.get('target') == target and item.get('by') == by:
                return [], f"progress: {item['id']} open {target} by {by['ref']}"
        ident = factslib.next_id(loaded['all'], 'block')
        record = factslib.make('block', ident, a.actor, now=now(), target=target, by=by, state='open', resolved_at=None)
        return [record], f"progress: {ident} open {target} by {by['ref']}"
    return mutate(ctx, a, make)


def cmd_unblock(a, root):
    ctx = target_ctx(a, root)

    def make(loaded):
        if bool(a.id) == bool(a.all_for):
            raise ProgressError('PROGRESS_USAGE', 'give a blocker id or --all-for TARGET', 2)
        opened = [r for r in loaded['current'] if r['kind'] == 'block' and r.get('state') == 'open'
                  and (r['id'] == (a.id or '').upper() or r.get('target') == (a.all_for or '').upper())]
        if not opened:
            raise ProgressError('PROGRESS_NOT_FOUND', 'no matching open blocker', 2)
        stamp = iso(now())
        records = [factslib.make('block', r['id'], a.actor, now=now(), target=r['target'], by=r['by'], state='resolved', resolved_at=stamp)
                   for r in opened]
        return records, 'progress: ' + (f"{opened[0]['id']} resolved" if len(opened) == 1 else f'{len(opened)} resolved')
    return mutate(ctx, a, make)


def cmd_decide(a, root):
    ctx = target_ctx(a, root)
    if (ctx.feature_dir / 'workflow' / 'decisions.json').is_file():
        raise ProgressError('PROGRESS_DECISION_AUTHORITY', 'Workflow owns decisions for this feature', 3)

    def make(loaded):
        if a.action == 'ask':
            options = [factslib.sanitise(o, ctx.root, 80) for o in a.options.split(',') if o.strip()]
            if len(options) < 2:
                raise ProgressError('PROGRESS_USAGE', '--options needs at least two comma separated values', 2)
            ident = factslib.next_id(loaded['all'], 'decision')
            record = factslib.make('decision', ident, a.actor, now=now(), question=factslib.sanitise(a.question, ctx.root),
                                   options=options, status='pending', selected=None, decided_by=None, evidence=None)
            return [record], f'progress: {ident} pending'
        old = next((r for r in loaded['current'] if r['kind'] == 'decision' and r['id'] == a.id.upper()), None)
        if old is None:
            raise ProgressError('PROGRESS_NOT_FOUND', f'no decision {a.id}', 2)
        match = next((o for o in old.get('options') or [] if o.lower() == a.selected.strip().lower()), None)
        if match is None:
            raise ProgressError('PROGRESS_USAGE', 'selected must be one of: ' + ', '.join(old.get('options') or []), 2)
        evidence = factslib.sanitise(a.evidence, ctx.root) if a.evidence else None
        record = {**factslib.make('decision', old['id'], a.actor, now=now()), 'question': old['question'], 'options': old['options'],
                  'status': 'made', 'selected': match, 'decided_by': a.by, 'evidence': evidence}
        return [record], f"progress: {old['id']} made {match}"
    return mutate(ctx, a, make)


def cmd_note(a, root):
    ctx = target_ctx(a, root)

    def make(loaded):
        target = a.target.upper() if a.target else None
        if target and not (re.fullmatch(r'[LWC]\d+', target) or (re.fullmatch(TASK_REF, target) and not RESERVED_ID.fullmatch(target))):
            raise ProgressError('PROGRESS_USAGE', 'note target is a task or lane id', 2)
        ident = factslib.next_id(loaded['all'], 'note')
        record = factslib.make('note', ident, a.actor, now=now(), text=factslib.sanitise(a.text, ctx.root), target=target)
        return [record], f'progress: {ident} noted'
    return mutate(ctx, a, make)


WINDOWS_ABSOLUTE = re.compile(r'[A-Za-z]:/|//[^/]')


def _log_path(value, root):
    """Repo-relative path for a log inside the repository, `external:<name>` for any other absolute path, the text
    unchanged for a relative one. Windows (drive, UNC) and POSIX absolute forms are recognised on every platform."""
    text = str(value).replace(chr(92), '/')
    windows = bool(WINDOWS_ABSOLUTE.match(text))
    if not (windows or text.startswith('/')):
        return text
    name = text.rstrip('/').rsplit('/', 1)[-1] or 'log'
    if text.startswith('//'):
        return 'external:' + name
    root_text = Path(root).as_posix()
    if factslib._is_inside(text, root_text) and posixpath.normpath(text) != posixpath.normpath(root_text):
        base = len(posixpath.normpath(root_text).rstrip('/'))
        return posixpath.normpath(text)[base:].lstrip('/')
    return 'external:' + name


def _usage_record(path, root):
    """Whitelist a legacy usage measurement: counters, window, provenance. Nothing else is stored."""
    raw = read_json(path, None)
    if not isinstance(raw, dict):
        raise ProgressError('PROGRESS_USAGE', '--usage-json must be a JSON object', 2)
    fidelity = raw.get('fidelity')
    if fidelity not in ('exact', 'reported', 'unavailable'):
        raise ProgressError('PROGRESS_USAGE', 'usage fidelity must be exact, reported or unavailable', 2)
    out = {'fidelity': fidelity}
    for key, cap in (('agent', 80), ('harness', 40), ('model', 80), ('reason', 200)):
        if raw.get(key) is not None:
            out[key] = factslib.sanitise(raw[key], root, cap)
    for key in USAGE_COUNTERS:
        value = raw.get(key)
        out[key] = value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    for key in ('since', 'until'):
        if raw.get(key) is not None:
            moment = parse_time(raw[key])
            if moment is None:
                raise ProgressError('PROGRESS_USAGE', f'usage {key} is not an ISO-8601 time', 2)
            out[key] = iso(moment)
    if raw.get('log'):
        out['log'] = factslib.sanitise(_log_path(raw['log'], root), root, 200)
    return out


def cmd_attempt(a, root):
    ctx = target_ctx(a, root)

    def make(loaded):
        lane = a.lane.upper() if a.lane else None
        if lane and not re.fullmatch(r'[LWC]\d+', lane):
            raise ProgressError('PROGRESS_USAGE', 'lane id must look like L1', 2)
        label = factslib.sanitise(a.overhead, ctx.root, 60) if a.overhead else None
        run = factslib.sanitise(a.run, ctx.root, 80)
        same = next((r for r in loaded['current'] if r['kind'] == 'attempt' and r.get('run') == run
                     and r.get('lane') == lane and r.get('label') == label), None)
        # A re-record keeps what it does not restate: times and usage. An empty --started/--ended clears that time.
        times = {}
        for key, value in (('started_at', a.started), ('ended_at', a.ended)):
            moment = parse_time(value) if value else None
            if value and moment is None:
                raise ProgressError('PROGRESS_USAGE', f'--{key.split("_")[0]} is not an ISO-8601 time', 2)
            times[key] = (same or {}).get(key) if value is None else iso(moment)
        usage = _usage_record(a.usage_json, ctx.root) if a.usage_json else (same or {}).get('usage')
        ident = same['id'] if same else factslib.next_id(loaded['all'], 'attempt')
        record = factslib.make('attempt', ident, 'legacy', source='workflow-shim', now=now(), lane=lane, label=label, run=run,
                               status=a.status, usage=usage, origin='legacy', **times)
        return [record], f"progress: {ident} {a.status} {lane or label} run {run}"
    return mutate(ctx, a, make)


def cmd_runs(a, root):
    stamp = parse_time(a.now) if a.now else now()
    if stamp is None:
        raise ProgressError('PROGRESS_USAGE', '--now must be an ISO timestamp', 2)
    merged, malformed, duplicates, conflicts = {}, [], [], {}
    for entry in a.runs_dir or [str(root / '.delegate' / 'runs')]:
        folder = Path(entry)
        found = runscol.collect_runs(folder if folder.is_absolute() else root / folder, now=stamp, stall_seconds=a.stall_seconds)
        malformed += runscol.last_malformed()
        duplicates += runscol.last_duplicates()
        for run in found:
            known = merged.get(run['run_id'])
            if known:
                duplicates.append(run['run_id'])
                # Conflicts accumulate per run id and attach to whichever record is retained, so a discarded
                # incoming record cannot take the disagreement with it.
                conflicts.setdefault(run['run_id'], set()).update(runscol._conflicts(known, run), known.get('conflict') or [],
                                                                  run.get('conflict') or [])
                if run['phase'] != 'done' and known['phase'] == 'done':
                    continue
            merged[run['run_id']] = run
    for run_id, fields in conflicts.items():
        if fields:
            merged[run_id]['conflict'] = sorted(fields)
    runs = sorted(merged.values(), key=lambda r: (r['started_at'] or '', r['run_id']))
    if a.json:
        print(json.dumps({'schema': RUNS_SCHEMA, 'generated_at': iso(stamp), 'stall_seconds': a.stall_seconds,
                          'runs': runs, 'duplicates': sorted(set(duplicates)), 'malformed': malformed, 'caveats': list(RUNS_CAVEATS)}, ensure_ascii=False))
    else:
        live = sum(1 for r in runs if r['phase'] != 'done')
        print(f'progress: {len(runs)} runs, {live} live, {len(malformed)} malformed')
    return 0


def cmd_export(a, root):
    ctx = target_ctx(a, root)
    require_init(ctx)
    report = read_json(ctx.report)
    if not isinstance(report, dict):
        with locked(ctx):
            report = refresh_now(ctx)
    if model.schema_name(a.schema) != report.get('schema'):
        # The stored report is v3. The other schema is built fresh from the producers, at the stored revision.
        state = refreshlib.read_state(ctx)
        report = model.build(ctx, now(), int(state.get('rev') or 0), state, schema=a.schema)
    text = json.dumps(report, indent=2, ensure_ascii=False) + '\n' if a.format == 'json' else render_md.render(report)
    if a.out:
        atomic_write(Path(a.out), text)
        print(f'progress: exported {a.out}')
    else:
        sys.stdout.write(text)
    return 0


def cmd_hook(a, root):
    hooklib.handle(a.event, sys.stdin.read() if not sys.stdin.isatty() else '', root=root, host=a.host)
    return 0


def cmd_hooks(a, root):
    from sanduq_progress import hooks_install
    line = hooks_install.execute(a, root)
    if a.action == 'install':
        line += pending_bind(root)
    print(line)
    return 0


def pending_bind(root):
    """When exactly one report exists already, open a bind for it: the hooks just installed complete it on the next tool call,
    so installing hooks after `init` needs no separate `bind` step. Empty when there is nothing to bind."""
    try:
        ctx = Ctx(root, resolve_target(root))
        if not ctx.dir.is_dir() or not ctx.facts.exists():
            return ''
        return f' bind={snapshot.create_pending(ctx, now())}'
    except (ProgressError, OSError):
        return ''


def cmd_statusline(a, root):
    if a.action == 'install':
        statuslib.install(root)
        print('progress: statusline installed')
    elif a.action == 'uninstall':
        statuslib.uninstall(root)
        print('progress: statusline removed')
    else:
        statuslib.main_stdin(root)
    return 0


VERBS = {'init': cmd_init, 'bind': cmd_bind, 'refresh': cmd_refresh, 'status': cmd_status, 'lane': cmd_lane,
         'block': cmd_block, 'unblock': cmd_unblock, 'decide': cmd_decide, 'note': cmd_note, 'theme': cmd_theme,
         'export': cmd_export, 'attempt': cmd_attempt, 'runs': cmd_runs, 'hook': cmd_hook, 'statusline': cmd_statusline, 'hooks': cmd_hooks}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ('hook', 'statusline'):
        # The host must never see output or failures from the automatic paths.
        try:
            args = build_parser().parse_args(argv)
            root = Path(args.root).resolve() if args.root else find_root()
            return VERBS[args.verb](args, root) if args.verb == 'statusline' and args.action != 'run' else _quiet(args, root)
        except Exception:
            return 0
    try:
        args, extra = build_parser().parse_known_args(argv)
        if extra and args.verb != 'theme':
            raise ProgressError('PROGRESS_USAGE', 'unrecognized arguments: ' + ' '.join(extra), 2)
        args.rest = extra
        root = Path(args.root).resolve() if args.root else find_root()
        return VERBS[args.verb](args, root)
    except ProgressError as error:
        print(error.line())
        return error.exit_code
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 2


def _quiet(args, root):
    try:
        return VERBS[args.verb](args, root)
    except Exception:
        return 0


if __name__ == '__main__':
    sys.exit(main())
