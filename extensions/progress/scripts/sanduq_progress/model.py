"""Projection builder: producers in, `sanduq.progress.v3` (default) or the `sanduq.progress.v2` compatibility document out. Pure apart from reading files; `now` is injected so
the same inputs give the same document (golden-testable)."""
import re
from datetime import timedelta
from pathlib import Path

from . import SCHEMA_V2, facts as factslib
from .collect import hosts as hostscol, plan as plancol, runs as runscol, tasks as taskscol, workflow as wf
from .hosts import unknown
from .paths import current_branch, plan_info
from .util import clean, count_lines, diag, iso, parse_time

DONE_STATES = ('accepted',)
WAIT_STATES = ('successful', 'unverified')
FAIL_STATES = ('failed', 'abandoned')
CHILD_STATUS = {'running': 'active', 'done': 'done', 'failed': 'failed'}


def measure(value, source, now, fidelity='exact'):
    return {'value': value, 'source': source, 'observed_at': iso(now), 'fidelity': fidelity}


def natural(ident):
    match = re.fullmatch(r'([A-Za-z]+)(\d+)', str(ident))
    return (match.group(1), int(match.group(2))) if match else (str(ident), 0)


def seconds(start, end):
    return max(0, int((end - start).total_seconds())) if start and end else None


def _heading(path):
    try:
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            if line.startswith('# '):
                return clean(line[2:], 160)
    except OSError:
        pass
    return None


def _observed_seconds(intervals, now):
    """Seconds covered by explicit {start, end} intervals (an open end counts to `now`); None when there are none."""
    total = None
    for item in intervals if isinstance(intervals, list) else []:
        if not isinstance(item, dict):
            continue
        begin, finish = parse_time(item.get('start')), parse_time(item.get('end')) or now
        if begin and finish >= begin:
            total = (total or 0) + int((finish - begin).total_seconds())
    return total


def _lane_from_attempts(rows, run_by_id, now):
    """Status, elapsed, active, attempts, observed model from one delegation identity's attempts.

    `active_s` is the sum of work intervals a producer observed (`active_intervals` on an attempt) and is None
    otherwise: an attempt's start-to-end span is wall time and is never reported as active work time."""
    rows = sorted(rows, key=lambda a: (a.get('started_at') or '', str(a.get('run_id') or '')))
    shown, active_total, running, spent = [], None, False, None
    for a in rows:
        run = run_by_id.get(a.get('run_id')) or {}
        start = parse_time(a.get('started_at'))
        end = parse_time(a.get('ended_at') or run.get('ended_at'))
        live = a.get('status') in wf.ACTIVE
        running = running or live
        # An attempt's own duration: start to its end, or to now while it runs. A finished attempt with no recorded end
        # falls back to the harness-measured duration, never to now. Durations are summed, so a lane that was reused
        # hours later does not show the gap between its attempts as work.
        if start and end:
            length = seconds(start, end)
        elif start and live:
            length = seconds(start, now)
        else:
            length = a.get('actual_duration_seconds')
            length = length if isinstance(length, (int, float)) and not isinstance(length, bool) else None
            length = int(length) if length is not None and length >= 0 else None
        if length is not None:
            spent = (spent or 0) + length
        usage = run.get('usage')
        tokens = None if not usage else {'fresh_input': usage['input_fresh'], 'cache_read': usage['cache_read'],
                                         'cache_write': usage['cache_write'], 'output': usage['output_total'],
                                         'reasoning': usage['reasoning'], 'total': usage['total']}
        shown.append({'run_id': a.get('run_id'), 'status': a.get('status') or 'unknown', 'started_at': a.get('started_at'),
                      'ended_at': a.get('ended_at') or run.get('ended_at'), 'tokens': tokens,
                      'fidelity': 'exact' if tokens else 'unknown', 'phase': run.get('phase')})
        observed = _observed_seconds(a.get('active_intervals'), now)
        if observed is not None:
            active_total = (active_total or 0) + observed
    final = rows[-1].get('status') if rows else None
    status = ('active' if final in wf.ACTIVE else 'done' if final in DONE_STATES or rows[-1].get('accepted_at')
              else 'waiting' if final in WAIT_STATES else 'failed' if final in FAIL_STATES
              else 'blocked' if final == 'blocked' else 'pending')
    return {'status': status, 'attempts': shown, 'elapsed_s': spent,
            'active_s': active_total, 'row': rows[-1], 'running': running}


def _model_measure(row, run, now):
    """Observed model: only explicit evidence counts (the ledger's actual_model, or a model the run result reports it
    ran). A launch request, from the ledger or from meta/result `model`, is never an observation."""
    if row.get('actual_model'):
        pending = row.get('actual_model_evidence') in (None, 'pending')
        return measure(row['actual_model'], 'delegation-ledger', now, 'partial' if pending else 'exact')
    if run.get('model_reported'):
        return measure(run['model_reported'], 'run-result', now, 'partial')
    return unknown()


def _diagnose(ctx, message, now):
    """Record a diagnostic once (the projection is rebuilt often)."""
    try:
        if message in ctx.diag.read_text(encoding='utf-8', errors='replace'):
            return
    except OSError:
        pass
    diag(ctx.diag, message, now)


def _newer_measure(new, old):
    """Whether `new` is a better observation than `old`: newest observed_at wins; a first value always wins."""
    if old is None or old.get('value') is None:
        return True
    return (new.get('observed_at') or '') > (old.get('observed_at') or '')


def _child_end(lane):
    """(status, ended_at) from the terminal evidence of an assigned lane's merged children, or None while any child
    is still running or has no recorded end. The child that ended last decides (a retry that succeeded clears a failure)."""
    children = [c for _, c in lane.get('children', [])]
    if not children or any(c.get('status') not in ('done', 'failed') or not parse_time(c.get('ended_at')) for c in children):
        return None
    last = max(children, key=lambda c: parse_time(c['ended_at']))
    return last['status'], parse_time(last['ended_at'])


def _child_numbers(child):
    return [n for n in [child.get('lane_no'), *(child.get('lane_aliases') or [])] if isinstance(n, int) and not isinstance(n, bool)]


TASK_IDENTITY = re.compile(r'/(T\d+)$')


def link_attempts(lanes, grouped):
    """Attach delegation attempts to the facts lane that describes the same run, so one run is one lane.

    Only durable ids link them, never labels, time windows or matching model requests:
      1. the lane owner is a delegation identity            -> all of that identity's attempts
      2. the lane owner is a delegation run id              -> that attempt
    A run no lane names keeps its own `W<n>` lane. An attempt is never in two lanes and never lost."""
    facts = [l for l in lanes if l['origin'] == 'facts']
    by_run = {str(a['run_id']): (identity, a) for identity, rows in grouped.items() for a in rows if a.get('run_id')}

    def take(lane, identity, row):
        grouped[identity] = [r for r in grouped[identity] if r is not row]
        lane.setdefault('rows', []).append(row)

    # Find every lane that names an identity before draining its attempts: the first takes them, the others are marked
    # so fold_lanes still recognises them as the same work and folds them in.
    named = {}
    for lane in facts:
        owner = str(lane['owner'] or '')
        if owner in grouped:
            named.setdefault(owner, []).append(lane)
    for owner, owners in named.items():
        for row in list(grouped[owner]):
            take(owners[0], owner, row)
        for lane in owners[1:]:
            lane['fold_identity'] = owner
    for lane in facts:
        owner = str(lane['owner'] or '')
        if not lane.get('rows') and owner in by_run:
            identity, row = by_run[owner]
            if any(r is row for r in grouped.get(identity, [])):
                take(lane, identity, row)


KEEP_KINDS = ('stage', 'failure', 'decision', 'block', 'workflow')
KEEP_LIMIT, OTHER_LIMIT, NOTE_LIMIT = 50, 30, 15


def bounded_events(events):
    """Events stay bounded but are not just the newest lines: stage acceptances, failures, decisions, blockers and
    workflow pauses keep their own budget, so a burst of delegation lines cannot push them out."""
    important = [e for e in events if e['kind'] in KEEP_KINDS][-KEEP_LIMIT:]
    notes = [e for e in events if e['kind'] == 'note'][-NOTE_LIMIT:]  # the coordinator's own record: its own budget
    rest = [e for e in events if e['kind'] not in KEEP_KINDS and e['kind'] != 'note'][-OTHER_LIMIT:]
    return sorted(important + notes + rest, key=lambda e: (e['at'], e['kind'], e['text']))


def fold_lanes(lanes, grouped):
    """One delegation identity is one lane. Facts lanes whose attempts all belong to one identity are the same work seen
    twice (a stage run, or a task run), so they fold into a single lane per identity, keeping the lowest lane id; the
    other ids stay resolvable through the returned alias map (a blocker on L4 still lands on the folded lane). A lane
    holding attempts of several identities is a real workstream and stays as it is."""
    members, order = {}, []
    for lane in lanes:
        names = {str(r['identity']) for r in lane.get('rows') or []} or ({lane['fold_identity']} if lane.get('fold_identity') else set())
        if lane['origin'] == 'facts' and len(names) == 1:
            name = next(iter(names))
            members.setdefault(name, []).append(lane)
            order.append(name if len(members[name]) == 1 else None)
        else:
            order.append(lane)
    out, aliases = [], {}
    for item in order:
        if item is None:
            continue
        if not isinstance(item, str):
            out.append(item)
            continue
        group = members[item]
        head, rest = group[0], grouped.get(item) or []
        if len(group) == 1 and not rest:
            out.append(head)
            continue
        rows = [r for lane in group for r in lane.get('rows') or []] + list(rest)
        grouped[item] = []
        tasks = list(dict.fromkeys(t for lane in group for t in lane['tasks']))
        closed = all(lane['closed'] for lane in group)
        ends = [lane['ended'] for lane in group]
        starts = [lane['since'] for lane in group if lane['since']]
        merged = dict(head, rows=rows, fold_identity=None, tasks=tasks, closed=closed, owner=item, requested=group[-1]['requested'],
                      label=head['label'] if TASK_IDENTITY.search(item) and head['label'] != head['id']
                      else clean(item.rsplit('/', 1)[-1], 60),
                      since=min(starts) if starts else None, ended=max(ends) if closed and all(ends) else None)
        for lane in group[1:]:
            aliases[lane['id']] = head['id']
        out.append(merged)
    return out, aliases


def build(ctx, now, rev=1, state=None, plan=None):
    """The v3 projection. It is built on the internal base document (`build_v2`); no command prints that one."""
    from . import model_v3
    from .util import tracking
    with tracking() as reads:  # every producer file read below is remembered by hash, size and read time
        base, aux = _build_v2(ctx, now, rev, state, plan)
        aux['reads'] = reads
        v3 = model_v3.build(ctx, now, rev, state or {}, base, aux)
    if v3['collection'].get('inconsistent_sources') and state is not None:
        state['dirty'] = True  # a file changed while the others were read: the next refresh must run again
    return v3


def _build_v2(ctx, now, rev=1, state=None, plan=None):
    state = {} if state is None else state
    cfg = ctx.config_data()
    stale_after = int(cfg.get('stale_after_seconds') or 600)
    tk = (plan or plancol.collect(ctx)) if ctx.is_plan else taskscol.collect(ctx.feature_dir)
    cp = wf.checkpoint(ctx.feature_dir)
    attempts = wf.attempts(ctx.feature_dir)
    wf_decisions_exist, wf_decisions = wf.decisions(ctx.feature_dir)
    referenced = {str(a['run_id']) for a in attempts if a.get('run_id')}
    run_list = runscol.collect_runs(ctx.root / '.delegate' / 'runs', now=now, only=referenced)
    run_by_id = {r['run_id']: r for r in run_list}
    loaded = factslib.load(ctx.facts)
    fact_rows = loaded['current']
    snaps = hostscol.collect(ctx)
    workflow_mode = bool(cp or attempts or wf_decisions_exist)
    task_ids = [t['id'] for t in tk['tasks']]
    tmap = {t['id']: t for t in tk['tasks']}

    # ---- orchestrator -----------------------------------------------------------------------------------
    sessions = [s for s in snaps if not s.get('parent_session_id') and not s.get('agent_id')]
    main = sessions[0] if sessions else None
    started = [parse_time(x) for x in (state.get('started_at'), cp and cp.get('started_at'),
                                       main and main.get('first_seen'), min((r['ts'] for r in loaded['all']), default=None))]
    started = min((s for s in started if s), default=None)
    elapsed_ms = main.get('elapsed_ms') if main else None
    elapsed = (measure(int(elapsed_ms['value'] // 1000), elapsed_ms['source'], parse_time(elapsed_ms['observed_at']) or now)
               if elapsed_ms else measure(seconds(started, now), 'wall-clock', now, 'estimated') if started else unknown())
    orchestrator = {'host': main.get('host') if main else None, 'session_id': main.get('session_id') if main else None,
                    'model': (main or {}).get('model') or unknown(), 'effort': (main or {}).get('effort') or unknown(),
                    'context': (main or {}).get('context') or unknown(), 'elapsed': elapsed, 'active': unknown(),
                    'since': iso(started)}

    # ---- lanes --------------------------------------------------------------------------------------------
    lanes = []
    history = {}
    for rec in loaded['all']:
        if rec['kind'] == 'lane':
            history.setdefault(rec['id'], []).append(rec)
    for rec in sorted((r for r in fact_rows if r['kind'] == 'lane'), key=lambda r: natural(r['id'])):
        # A lane id is reused for new owners. Its current assignment began with the first record of the unbroken tail
        # that names the current owner, not when the id first appeared, so a reused lane does not span the gap.
        tail = []
        for earlier in reversed(history.get(rec['id'], [])):
            if earlier.get('owner') != rec.get('owner'):
                break
            tail.append(earlier)
        began = (tail[-1] if tail else rec).get('ts')
        lane = {'id': rec['id'], 'label': clean(rec.get('label') or rec['id'], 60), 'owner': rec.get('owner'), 'origin': 'facts',
                'requested': {k: (rec.get('requested') or {}).get(k) for k in ('harness', 'model', 'effort')},
                'tasks': [t for t in rec.get('tasks') or [] if t in tmap], 'closed': rec.get('state') == 'closed',
                'since': parse_time(began), 'ended': parse_time(rec.get('ts')) if rec.get('state') == 'closed' else None}
        lanes.append(lane)
    grouped = {}
    for a in sorted(attempts, key=lambda a: (a.get('started_at') or '', str(a.get('run_id')))):
        grouped.setdefault(str(a['identity']), []).append(a)
    link_attempts(lanes, grouped)
    lanes, folded = fold_lanes(lanes, grouped)
    retired = {}
    for number, (identity, rows) in enumerate(grouped.items(), 1):
        if not rows:
            retired[f'W{number}'] = identity
            continue
        lane = {'id': f'W{number}', 'label': clean(identity.rsplit('/', 1)[-1], 60), 'owner': identity,
                'origin': 'workflow-delegation', 'requested': {}, 'tasks': [], 'closed': False, 'since': None, 'rows': rows}
        lanes.append(lane)
    for lane in lanes:
        for row in lane.get('rows') or []:
            for tid in wf.identity_tasks(row):
                if tid in tmap and tid not in lane['tasks']:
                    lane['tasks'].append(tid)
    host_children = []
    for snap in snaps:
        for key, child in sorted((snap.get('children') or {}).items(), key=lambda kv: (kv[1].get('started_at') or '', kv[0])):
            host_children.append((snap, key, child))
    host_children.sort(key=lambda x: (x[2].get('started_at') or x[2].get('last_observed_at') or '', x[1]))
    # A host child belongs to an assigned lane when that lane's owner names it by a stable id: the child's agent id or the
    # tool_use id it was launched with (its snapshot key). Matching children add their observations to that lane. A
    # description label is only a fallback, and only when exactly one child carries that label for the lane; an ambiguous
    # label merges nothing (the children stay separate C<n> lanes) and a diagnostic says so.
    owned = {str(l['owner']).strip().lower(): l for l in lanes if l.get('owner') and l['origin'] != 'host-child'}
    unmatched, by_label, merged = [], {}, []
    for snap, key, child in host_children:
        target = next((owned[str(n).strip().lower()] for n in (child.get('agent_id'), key)
                       if n and str(n).strip().lower() in owned), None)
        if target is not None:
            target.setdefault('children', []).append((snap, child))
            merged.append((child, target))
            continue
        label = str(child.get('description') or '').strip().lower()
        if label in owned:
            by_label.setdefault(label, []).append((snap, key, child))
        else:
            unmatched.append((snap, key, child))
    for label, group in sorted(by_label.items()):
        if len(group) == 1:
            owned[label].setdefault('children', []).append((group[0][0], group[0][2]))
            merged.append((group[0][2], owned[label]))
        else:
            unmatched.extend(group)
            _diagnose(ctx, f"description '{clean(label, 60)}' matches {len(group)} children; not merged into lane "
                           f"{owned[label]['id']} (use the agent id or tool_use id as the lane owner)", now)
    unmatched.sort(key=lambda x: (x[2].get('started_at') or x[2].get('last_observed_at') or '', x[1]))
    # A child's lane number is durable host data: the snapshot entry carries `lane_no` (assigned once, never reused) and
    # `lane_aliases` (numbers of entries later found to be the same child). Deleting the disposable view or re-keying
    # an entry (agent id <-> tool_use id) therefore changes no id, and a blocker on a retired number still resolves.
    # An entry written before numbers existed gets one above every known number, in start order (not persisted).
    numbers = [n for _, _, c in unmatched for n in ([c.get('lane_no')] + list(c.get('lane_aliases') or [])) if isinstance(n, int)]
    top = max(numbers + [0])
    unmatched.sort(key=lambda x: (not isinstance(x[2].get('lane_no'), int), x[2].get('lane_no') if isinstance(x[2].get('lane_no'), int) else 0,
                                  x[2].get('started_at') or x[2].get('last_observed_at') or '', x[1]))
    identity = {f'C{n}': lane['id'] for child, lane in merged for n in _child_numbers(child)}
    for snap, key, child in unmatched:
        if not isinstance(child.get('lane_no'), int):
            top += 1
            child = dict(child, lane_no=top)
        for number in _child_numbers(child):
            identity[f'C{number}'] = f"C{child['lane_no']}"
        lanes.append({'id': f"C{child['lane_no']}", 'label': clean(child.get('description') or child.get('subagent_type') or key, 60),
                      'owner': child.get('agent_id') or key, 'origin': 'host-child', 'child': child, 'host': snap.get('host'),
                      'requested': {}, 'tasks': [], 'closed': False, 'since': parse_time(child.get('started_at'))})
    claimed = {t for lane in lanes for t in lane['tasks']}
    if not workflow_mode:
        lanes.append({'id': 'coordinator', 'label': 'Coordinator', 'owner': orchestrator['session_id'], 'origin': 'coordinator',
                      'requested': {}, 'tasks': [t for t in task_ids if t not in claimed], 'closed': False, 'since': started})
    task_lane = {}
    for lane in lanes:
        for tid in lane['tasks']:
            task_lane.setdefault(tid, lane['id'])
    for lane in lanes:
        lane['tasks'] = [t for t in lane['tasks'] if task_lane.get(t) == lane['id']]

    # ---- blockers -----------------------------------------------------------------------------------------
    shown_in = {str(r['identity']): lane['id'] for lane in lanes for r in lane.get('rows') or []}
    for wid, name in retired.items():  # a retired W lane id keeps meaning the lane its identity's attempts are shown in
        if name in shown_in:
            folded.setdefault(wid, shown_in[name])

    def resolve(ref):
        """A reference to a child (its C<n> number or a retired alias) means the lane that child is displayed in now."""
        ref = folded.get(ref) or identity.get(ref, ref)
        return folded.get(ref) or ref

    blockers = []
    for rec in sorted((r for r in fact_rows if r['kind'] == 'block' and r.get('state') == 'open'), key=lambda r: natural(r['id'])):
        by = rec.get('by') or {}
        by = dict(by, ref=resolve(by.get('ref'))) if by.get('type') == 'lane' else by
        blockers.append({'id': rec['id'], 'target': resolve(rec.get('target')), 'by': by,
                         'since': rec.get('ts'), 'source': 'facts'})
    if cp and cp.get('pause') and not cp['pause'].get('superseded'):
        blockers.append({'id': 'WP', 'target': 'feature', 'by': {'type': 'external', 'ref': cp['pause']['reason']},
                         'since': cp['pause']['at'], 'source': 'workflow-pause'})

    # ---- lane state ---------------------------------------------------------------------------------------
    for lane in lanes:
        lane.update(observed={'model': unknown(), 'effort': unknown()}, attempts=[], elapsed=unknown(), active=unknown(),
                    last_observed_at=None)
        derived = None
        if lane.get('rows'):
            derived = _lane_from_attempts(lane['rows'], run_by_id, now)
            lane['attempts'] = derived['attempts']
            lane['observed']['model'] = _model_measure(derived['row'], run_by_id.get(derived['row'].get('run_id')) or {}, now)
            row = derived['row']
            lane['requested'] = {'harness': row.get('requested_harness') or lane['requested'].get('harness'),
                                 'model': row.get('requested_model') or lane['requested'].get('model')
                                 or (run_by_id.get(row.get('run_id')) or {}).get('model'),
                                 'effort': row.get('requested_effort') or lane['requested'].get('effort')}
            if derived['elapsed_s'] is not None:
                lane['elapsed'] = measure(derived['elapsed_s'], 'delegation-ledger', now)
            lane['active'] = measure(derived['active_s'], 'delegation-ledger', now, 'partial') if derived['active_s'] is not None else unknown()
            lane['last_observed_at'] = max((a['ended_at'] or a['started_at'] or '' for a in derived['attempts']), default=None) or None
            if derived['status'] == 'blocked':
                blockers.append({'id': f"WB:{lane['id']}", 'target': lane['id'], 'by': {'type': 'external', 'ref': 'delegation blocked'},
                                 'since': row.get('ended_at') or row.get('started_at'), 'source': 'delegation'})
        own = [(lane['host'], lane['child'])] if lane['origin'] == 'host-child' else []
        merged = [(snap.get('host'), child) for snap, child in lane.get('children', [])]
        for tag, child in own + merged:
            for slot, field in (('model', 'model'), ('effort', 'effort')):
                m = child.get(field)
                if not m or m.get('value') is None:
                    continue
                if slot == 'model' and m.get('fidelity') == 'partial':
                    # the launch call's requested alias: not an observation of the child
                    if not lane['requested'].get('model'):
                        lane['requested'] = {'harness': tag, 'model': m['value'], 'effort': lane['requested'].get('effort')}
                elif _newer_measure(m, lane['observed'][slot]):
                    lane['observed'][slot] = m
            if child.get('last_observed_at') and (lane['last_observed_at'] or '') < child['last_observed_at']:
                lane['last_observed_at'] = child['last_observed_at']
            if lane['origin'] == 'host-child':
                lane['elapsed'] = (measure(seconds(parse_time(child.get('started_at')), parse_time(child.get('ended_at')) or now), 'hook', now)
                                   if child.get('started_at') else unknown())
        if lane['origin'] == 'coordinator':
            lane['elapsed'], lane['last_observed_at'] = orchestrator['elapsed'], (main or {}).get('last_observed_at')
        elif lane['origin'] == 'facts' and not lane.get('rows') and lane['since']:
            # Frozen at the last terminal evidence: the lane's close record, else the merged children's end, else it is
            # still running and the clock is now.
            ended = lane['ended'] or (_child_end(lane) or (None, None))[1]
            lane['elapsed'] = measure(seconds(lane['since'], ended or now), 'facts', now)
        lane['_derived'] = derived

    # Legacy supplemental attempts (Workflow shim). They are labelled origin 'legacy', appended after producer
    # attempts, and never change a lane's status or replace a producer's attempt of the same run.
    overhead = []
    for rec in sorted((r for r in fact_rows if r['kind'] == 'attempt'), key=lambda r: natural(r['id'])):
        usage = rec.get('usage') or {}
        measured = usage.get('fidelity') in ('exact', 'reported')
        tokens = ({k: usage.get(k) for k in ('fresh_input', 'cache_read', 'cache_write', 'output', 'reasoning')} | {'total': None}
                  if measured else None)
        shown = {'run_id': rec.get('run'), 'status': rec.get('status') or 'unknown', 'started_at': rec.get('started_at'),
                 'ended_at': rec.get('ended_at'), 'tokens': tokens, 'fidelity': usage.get('fidelity') or 'unknown',
                 'origin': 'legacy'}
        target = next((l for l in lanes if l['id'] == resolve(rec.get('lane'))), None)
        if target is not None:
            if not any(x.get('run_id') == shown['run_id'] and x.get('origin') != 'legacy' for x in target['attempts']):
                target['attempts'].append(shown)
        elif rec.get('lane') is None:
            overhead.append({**shown, 'label': rec.get('label'), 'agent': usage.get('agent')})

    lane_blockers = {}
    for b in blockers:
        lane_blockers.setdefault(b['target'], []).append(b)
    report_lanes, unassigned = [], {'active': [], 'waiting': [], 'blocked': [], 'done': []}

    def _later_activity(lane):
        """An attempt still active after the lane closed: it ended after the close, or is still running."""
        if not lane['ended']:
            return False

        def last_activity(row):
            began = parse_time(row.get('started_at'))
            if row.get('status') == 'running' and not row.get('ended_at'):
                return now
            return parse_time(row.get('ended_at')) or began or lane['ended']
        return any(last_activity(r) > lane['ended'] for r in lane.get('rows') or [])

    def status_of(lane):
        todo = [t for t in lane['tasks'] if not tmap[t]['done']]
        if lane['origin'] == 'host-child':
            child = lane['child']
            stale = (parse_time(child.get('last_observed_at')) or now) + timedelta(seconds=stale_after) < now
            base = CHILD_STATUS.get(child.get('status'), 'waiting')
            return 'waiting' if base == 'active' and stale else base
        if lane['tasks'] and not todo:
            return 'done'
        if lane['origin'] == 'coordinator':
            recent = main and (parse_time(main.get('last_observed_at')) or now) + timedelta(seconds=stale_after) >= now
            return 'active' if recent else ('pending' if not lane['tasks'] else 'waiting')
        if lane['closed'] and not _later_activity(lane):
            return 'done'  # historical closure never outranks an attempt still active after the lane closed
        if lane_blockers.get(lane['id']):  # an open blocker outranks terminal child evidence
            return 'blocked'
        ended = None if lane['_derived'] else _child_end(lane)
        if ended:  # the delegated child finished: failed, or waiting for its unchecked tasks to be ticked
            return 'failed' if ended[0] == 'failed' else 'waiting'
        if lane['_derived'] and lane['_derived']['status'] == 'blocked':
            return 'blocked'
        if lane['_derived']:
            derived = lane['_derived']['status']
            return 'waiting' if derived == 'done' and todo else derived
        return 'active'

    for lane in lanes:
        lane['status'] = status_of(lane)
        states = {'active': [], 'waiting': [], 'blocked': [], 'done': []}
        started_here = set()
        if lane['_derived'] and lane['_derived']['running']:
            started_here = set(wf.identity_tasks(lane['_derived']['row']))
        first_open = True
        for tid in lane['tasks']:
            if tmap[tid]['done']:
                states['done'].append(tid)
                continue
            by = [{'type': b['by'].get('type'), 'ref': b['by'].get('ref'), 'blocker': b['id']}
                  for b in lane_blockers.get(tid, []) + lane_blockers.get(lane['id'], [])]
            if by:
                states['blocked'].append({'task': tid, 'by': by})
            elif lane['status'] == 'active' and (first_open or tid in started_here):
                states['active'].append(tid)
                first_open = False
            else:
                states['waiting'].append(tid)
        lane['task_states'] = states
        report_lanes.append({'id': lane['id'], 'label': lane['label'], 'owner': lane['owner'], 'origin': lane['origin'],
                             'requested': {k: lane['requested'].get(k) for k in ('harness', 'model', 'effort')},
                             'observed': lane['observed'], 'status': lane['status'], 'elapsed': lane['elapsed'],
                             'active': lane['active'], 'last_observed_at': lane['last_observed_at'],
                             'attempts': lane['attempts'], 'tasks': states})
    for tid in task_ids:
        if tid in task_lane:
            continue
        if tmap[tid]['done']:
            unassigned['done'].append(tid)
        else:
            by = [{'type': b['by'].get('type'), 'ref': b['by'].get('ref'), 'blocker': b['id']} for b in lane_blockers.get(tid, [])]
            (unassigned['blocked'].append({'task': tid, 'by': by}) if by else unassigned['waiting'].append(tid))

    # ---- decisions ----------------------------------------------------------------------------------------
    pending, made = [], []
    for rec in sorted((r for r in fact_rows if r['kind'] == 'decision'), key=lambda r: natural(r['id'])):
        if rec.get('status') == 'withdrawn':
            continue
        evidence = rec.get('evidence') or ''
        item = {'id': rec['id'], 'question': rec.get('question'), 'options': rec.get('options') or [], 'selected': rec.get('selected'),
                'decided_by': rec.get('decided_by'), 'at': rec.get('ts'), 'url': evidence if evidence.startswith('http') else None,
                'source': 'facts'}
        (made if rec.get('status') == 'made' else pending).append(item)
    for d in wf_decisions:
        item = {k: d[k] for k in ('id', 'question', 'options', 'selected', 'decided_by', 'at', 'url', 'source')}
        (pending if d['pending'] else made).append(item)

    # ---- events -------------------------------------------------------------------------------------------
    events = []
    for rec in loaded['all']:
        kind, ident = rec['kind'], rec['id']
        text = {'lane': f"{ident} {len(rec.get('tasks') or [])} tasks" + (' closed' if rec.get('state') == 'closed' else ''),
                'block': f"{ident} {rec.get('state')} on {rec.get('target')}",
                'decision': f"{ident} {rec.get('status')}: {rec.get('question') or ''}",
                'note': f"{ident}: {rec.get('text') or ''}",
                'attempt': f"{ident} {rec.get('status')} {rec.get('lane') or rec.get('label')} run {rec.get('run')} (legacy)"}.get(kind)
        if text and rec.get('ts'):
            events.append({'at': rec['ts'], 'kind': kind, 'text': clean(text, 120)})
    for a in attempts:
        if a.get('started_at'):
            events.append({'at': a['started_at'], 'kind': 'delegation', 'text': clean(f"run {a.get('run_id')} started for {a['identity']}", 120)})
        if a.get('ended_at'):
            failed = a.get('status') in FAIL_STATES
            events.append({'at': a['ended_at'], 'kind': 'failure' if failed else 'delegation',
                           'text': clean(f"run {a.get('run_id')} {a.get('status')} ({str(a['identity']).rsplit('/', 1)[-1]})", 120)})
    for snap, key, child in host_children:
        label = child.get('description') or child.get('subagent_type') or key
        if child.get('started_at'):
            events.append({'at': child['started_at'], 'kind': 'subagent', 'text': clean(f'{label} started', 120)})
        if child.get('ended_at'):
            events.append({'at': child['ended_at'], 'kind': 'subagent', 'text': clean(f"{label} {child.get('status')}", 120)})
    if cp and cp.get('pause') and cp['pause'].get('at'):
        resolved = f" (superseded: {cp['pause']['superseded']})" if cp['pause'].get('superseded') else ''
        events.append({'at': cp['pause']['at'], 'kind': 'workflow', 'text': clean('paused' + resolved + ': ' + cp['pause']['reason'], 120)})
    for receipt in (cp or {}).get('receipts') or []:
        events.append({'at': receipt['at'], 'kind': 'stage', 'text': clean(f"{receipt['stage']} accepted", 120)})
    events.sort(key=lambda e: (e['at'], e['kind'], e['text']))
    events = bounded_events(events)

    # ---- feature, collection, summary ---------------------------------------------------------------------
    stage = None
    if cp:
        # The active claim names the stage. With no claim the last accepted receipt does (the stage the feature is at),
        # and the checkpoint status says whether it is finished; only without receipts does the status stand in.
        last = cp.get('last_accepted')
        if cp['stage']:
            stage = {'value': cp['stage'], 'source': 'workflow-checkpoint'}
        elif last:
            stage = {'value': last['stage'], 'source': 'workflow-receipts', 'status': cp['status']}
        elif cp['status'] not in (None, 'in-progress'):
            stage = {'value': cp['status'], 'source': 'workflow-checkpoint'}
    plan_name = plan_info(ctx.root, ctx.feature).get('name') or Path(ctx.feature).name if ctx.is_plan else None
    title = tk['title'] or (plan_name if ctx.is_plan else _heading(ctx.feature_dir / 'spec.md')) or Path(ctx.feature).name
    feature = {'id': plan_name if ctx.is_plan else Path(ctx.feature).name, 'title': title, 'dir': ctx.feature,
               'branch': (cp or {}).get('branch') or current_branch(ctx.root), 'issue': (cp or {}).get('issue'),
               'stage': stage, 'started_at': iso(started), 'workflow': workflow_mode}
    if ctx.is_plan:
        feature.update(mode='plan', source=plan_info(ctx.root, ctx.feature).get('source'))
    task_out = {t['id']: {'title': t['title'], 'phase': t['phase'], 'done': t['done'], 'parallel': t['parallel'],
                          'depends_on': t['depends_on'], 'lane': task_lane.get(t['id'])} for t in tk['tasks']}
    extra = {'overhead': overhead} if overhead else {}
    doc = {'schema': SCHEMA_V2, 'rev': rev, 'generated_at': iso(now), 'stale_after_seconds': stale_after,
            'collection': {'automatic': bool(snaps), 'hosts': sorted({s.get('host') for s in snaps if s.get('host')}),
                           'dirty': bool(state.get('dirty')), 'last_event_at': state.get('last_event_at'),
                           'diagnostics': count_lines(ctx.diag)},
            'feature': feature, 'orchestrator': orchestrator, 'lanes': report_lanes, 'unassigned_tasks': unassigned,
            'tasks': task_out, 'decisions': {'pending': pending, 'made': made}, 'blockers': blockers, 'events': events,
            'summary': {'tasks_total': len(task_ids), 'tasks_done': sum(1 for t in tk['tasks'] if t['done']),
                        'lanes_active': sum(1 for l in report_lanes if l['status'] == 'active'),
                        'blocked': len(blockers), 'decisions_pending': len(pending)}, **extra}
    aux = {'tk': tk, 'cp': cp, 'attempts': attempts, 'run_by_id': run_by_id, 'loaded': loaded, 'snaps': snaps,
           'main': main, 'started': started, 'lanes': lanes, 'folded': folded, 'retired': retired, 'identity': identity,
           'host_children': host_children, 'blockers': blockers, 'workflow_mode': workflow_mode, 'stale_after': stale_after,
           'wf_decisions_exist': wf_decisions_exist, 'wf_decisions': wf_decisions, 'orchestrator': orchestrator,
           'pending_v2': pending, 'made_v2': made, 'events_v2': events}
    return doc, aux


def build_v2(ctx, now, rev=1, state=None, plan=None):
    """The internal base document v3 is built on. The one-line status reads its `summary`; no command prints it."""
    return _build_v2(ctx, now, rev, state, plan)[0]
