"""Projection `sanduq.progress.v3`: stages, workstreams, runs, decisions and a curated timeline.

General rule: no inference from proximity. Time gaps, adjacency, matching text, model names and overlapping timestamps never
establish identity, retries, revalidation, rejection, acceptance or membership. A fact that no explicit record supports is
null (or "unknown"), and the field says so.

The v2 document (`model.build(..., schema='v2')`) is built first from the same reads; this module adds the structured views
on top of it and takes the pieces v2 already settled (orchestrator telemetry, blockers, legacy lane aliases) from it.
"""
import hashlib
import os
from pathlib import PurePath
import re

from . import SCHEMA_V3, selfreport
from .collect import clarifications as clarcol, lifecycle as lifecol, workflow as wf
from .hosts import unknown
from .util import clean, iso, parse_time

# Workflow's canonical stage order (workflow.py BASE_STAGES). Used only when the checkpoint carries no `stage_plan`.
BASE_STAGES = ('scope', 'specify', 'clarify', 'plan', 'tasks', 'qa_analyze', 'manual_analyze', 'analyze', 'taskstoissues',
               'execute', 'verify', 'review', 'qa_document', 'manual_update', 'ready', 'pr')
LABELS = {'qa_analyze': 'QA analyze', 'qa_document': 'QA document', 'manual_analyze': 'Manual analyze',
          'manual_update': 'Manual update', 'taskstoissues': 'Tasks to issues', 'pr': 'PR'}
FAILED = ('failed', 'abandoned')
LIVE = wf.ACTIVE
CHILD_STATUS = {'running': 'running', 'done': 'successful', 'failed': 'failed'}
END_EVENTS = ('accepted', 'recovered', 'paused', 'invalidated', 'revalidated', 'revalidation-stale')
OUTCOME = {'accepted': 'accepted', 'rejected-completion': 'rejected-completion', 'recovered': 'recovered', 'paused': 'paused',
           'invalidated': 'invalidated', 'revalidated': 'accepted', 'revalidation-stale': 'invalidated'}
TIMELINE_KIND = {'accepted': 'stage', 'rejected-completion': 'stage', 'paused': 'stage', 'recovered': 'recovery',
                 'invalidated': 'revalidation', 'revalidated': 'revalidation', 'revalidation-stale': 'revalidation'}
NOTE_CAP, TEXT_CAP = 140, 160
EPOCH = parse_time('1970-01-01T00:00:00Z')


def _m(value, source, now, fidelity='exact'):
    return {'value': value, 'source': source, 'observed_at': iso(now), 'fidelity': fidelity}


def _label(stage):
    return LABELS.get(stage) or stage.replace('_', ' ').capitalize()


def _stable(kind, at, key):
    return 'tl-' + hashlib.sha1(f'{kind}|{at}|{key}'.encode('utf-8')).hexdigest()[:10]


def _seconds(start, end):
    return max(0, int((end - start).total_seconds())) if start and end else None


# ---- runs ---------------------------------------------------------------------------------------------------------------

def _prefer(old, new):
    """Two ledger records of one run id: a finished record beats a live one, then the later end wins."""
    old_done, new_done = old.get('status') not in LIVE, new.get('status') not in LIVE
    if old_done != new_done:
        return old if old_done else new
    return new if (new.get('ended_at') or '') >= (old.get('ended_at') or '') else old


def _identity_parts(identity, feature_ids, explicit_tasks):
    """(stage, tasks). The identity's stage and task suffix are read only after its feature prefix matches a feature this
    report knows; an explicit task list on the attempt is kept either way."""
    stage, tasks = None, list(explicit_tasks)
    for fid in feature_ids:
        if identity.startswith(fid + '/'):
            suffix = identity[len(fid) + 1:]
            match = re.fullmatch(r'stage:([A-Za-z0-9_.-]{1,40})', suffix)
            if match:
                stage = match.group(1)
            elif not explicit_tasks:
                tasks = list(dict.fromkeys(re.findall(r'(?<![A-Za-z0-9])T\d+(?![A-Za-z0-9])', suffix)))
            break
    return stage, tasks


def _explicit_tasks(a):
    for key in ('tasks', 'task_ids', 'owned_tasks'):
        if isinstance(a.get(key), list):
            return [str(t) for t in a[key] if re.fullmatch(r'T\d+', str(t))]
    return []


def _duration(a, run, now):
    """Run duration: the harness-recorded duration, else a labelled timestamp-derived wall duration. A running run counts to
    the snapshot time; a finished run with no recorded end stays unknown and never grows with the clock."""
    start, end = parse_time(a.get('started_at')), parse_time(a.get('ended_at') or run.get('ended_at'))
    recorded = a.get('actual_duration_seconds')
    if isinstance(recorded, (int, float)) and not isinstance(recorded, bool) and recorded >= 0:
        return _m(int(recorded), 'harness', now, 'exact')
    if start and end:
        return _m(_seconds(start, end), 'timestamps', now, 'estimated')
    if start and a.get('status') in LIVE:
        return _m(_seconds(start, now), 'timestamps', now, 'estimated')
    elapsed = run.get('elapsed_seconds')
    if isinstance(elapsed, int) and not isinstance(elapsed, bool) and a.get('status') not in LIVE:
        return _m(elapsed, 'run-journal', now, 'estimated')
    return unknown()


def _effort(a, now):
    for key, fidelity in (('actual_effort', 'exact'), ('requested_effort', 'partial'), ('effort', 'partial')):
        if isinstance(a.get(key), str) and a[key].strip():
            return _m(clean(a[key], 40), 'delegation-ledger', now, fidelity)
    return unknown()


def build_runs(ctx, now, x, episodes_by_run, claim_episodes, ws_at):
    """(runs, dispatch, diagnostics). Keyed by the feature-scoped delegation run id."""
    from . import model as base
    feature_ids = [f for f in dict.fromkeys([ctx.feature, (x['cp'] or {}).get('feature'), x['ledger_feature']]) if f]
    by_id, conflicts, intents = {}, {}, {}
    dispatch_rows = []
    for a in x['attempts']:
        rid = a.get('run_id')
        if not rid:
            if a.get('intent_id'):
                dispatch_rows.append(a)
            continue
        rid = str(rid)
        if rid in by_id:
            diff = [k for k in ('identity', 'status', 'started_at', 'ended_at') if by_id[rid].get(k) != a.get(k)]
            if diff:
                conflicts.setdefault(rid, set()).update(diff)
            by_id[rid] = _prefer(by_id[rid], a)
        else:
            by_id[rid] = a
    held_intents = {str(a.get('intent_id')) for a in by_id.values() if a.get('intent_id')}
    for a in dispatch_rows:
        intent = str(a['intent_id'])
        if intent not in held_intents:
            intents.setdefault(intent, a)
    runs = []
    for rid, a in by_id.items():
        journal = x['run_by_id'].get(rid) or {}
        identity = str(a['identity'])
        stage, tasks = _identity_parts(identity, feature_ids, _explicit_tasks(a))
        claim = a.get('claim_id') if isinstance(a.get('claim_id'), str) and a['claim_id'] else None
        episode = episodes_by_run.get(rid)
        if episode is None and claim and len(claim_episodes.get(claim, [])) == 1:
            episode = claim_episodes[claim][0]
        known_stage = stage or (episode['stage'] if episode else None)
        if known_stage is None and claim and len({e['stage'] for e in claim_episodes.get(claim, [])}) == 1:
            known_stage = claim_episodes[claim][0]['stage']
        retry = next((str(a[k]) for k in ('replaces_run_id', 'parent_run_id') if a.get(k)), None)
        summary = clean(a.get('result_summary'), 160) or None
        run = {'run_id': rid, 'identity': identity, 'stage': known_stage, 'tasks': tasks,
               'episode_id': episode['id'] if episode else None, 'workstream': ws_at(tasks, a.get('started_at'), a),
               'harness': a.get('actual_harness') or a.get('requested_harness') or journal.get('harness'),
               'requested_model': a.get('requested_model') or journal.get('model'),
               'actual_model': base._model_measure(a, journal, now), 'effort': _effort(a, now),
               'started_at': a.get('started_at'), 'ended_at': a.get('ended_at') or journal.get('ended_at'),
               'duration': _duration(a, journal, now), 'worker_status': a.get('status') or 'unknown',
               'evidence_accepted': True if a.get('accepted_at') else None,  # no acceptance evidence stays null, a failed worker included
               'candidate_accepted': None, 'retry_of': retry, 'summary': summary}
        if rid in conflicts:
            run['conflict'] = sorted(conflicts[rid])
        runs.append(run)
    index = {r['run_id']: r for r in runs}
    # Host-session children: namespaced identity, merged with a delegation run only through an explicit run id.
    seen = set()
    for snap, key, child in x['host_children']:
        ident = f"host:{snap.get('session_id')}:{child.get('agent_id') or key}"
        if ident in seen:
            continue
        seen.add(ident)
        link = child.get('run_id')
        if isinstance(link, str) and link in index:
            target = index[link]
            model = child.get('model')
            if model and model.get('value') and model.get('fidelity') != 'partial' and target['actual_model'].get('value') is None:
                target['actual_model'] = model
            continue
        model, effort = child.get('model'), child.get('effort')
        start, end = parse_time(child.get('started_at')), parse_time(child.get('ended_at'))
        status = CHILD_STATUS.get(child.get('status'), 'unknown')
        duration = (_m(_seconds(start, end), 'hook', now, 'estimated') if start and end
                    else _m(_seconds(start, now), 'hook', now, 'estimated') if start and status == 'running' else unknown())
        runs.append({'run_id': ident, 'identity': ident, 'stage': None, 'tasks': [], 'episode_id': None, 'workstream': None,
                     'harness': snap.get('host'),
                     'requested_model': model['value'] if model and model.get('fidelity') == 'partial' else None,
                     'actual_model': model if model and model.get('fidelity') != 'partial' and model.get('value') else unknown(),
                     'effort': effort if effort and effort.get('value') else unknown(),
                     'started_at': child.get('started_at'), 'ended_at': child.get('ended_at'), 'duration': duration,
                     'worker_status': status, 'evidence_accepted': None, 'candidate_accepted': None, 'retry_of': None,
                     'summary': clean(child.get('description') or child.get('subagent_type'), 160) or None})
    runs.sort(key=lambda r: (r['started_at'] or '', r['run_id']))
    dispatch = [{'intent_id': i, 'identity': str(a['identity']), 'created_at': a.get('started_at') or a.get('created_at'),
                 'state': a.get('status') or 'unknown'} for i, a in sorted(intents.items())]
    return runs, dispatch


# ---- lifecycle episodes and stages ------------------------------------------------------------------------------------

def _episodes(events, active_stage):
    """Episodes from lifecycle events. An event joins an episode through its explicit `episode_id`, or, for a claim or resume
    event, through its own `claim_id`. Every other event (a claim-time `invalidated`, a feature-level `paused`, an event
    that names only a claim) is loose: it feeds validity and the timeline but creates no episode, and an invalidation never
    sets an episode start. Starts come from claim and resume events only."""
    groups, loose = {}, []
    for e in events:
        key = e['episode_id'] or (f"claim:{e['claim_id']}" if e['claim_id'] and e['event'] in lifecol.STARTS else None)
        if key and e['stage']:
            groups.setdefault((e['stage'], key), []).append(e)
        else:
            loose.append(e)
    out = []
    for (stage, key), rows in groups.items():
        last = rows[-1]
        ended = next((e for e in reversed(rows) if e['event'] in END_EVENTS), None)
        if last['event'] in lifecol.STARTS:
            outcome = 'running' if active_stage == stage else 'unknown'
        else:
            outcome = OUTCOME[last['event']]
        runs = list(dict.fromkeys(r for e in rows for r in e['delegation_run_ids']))
        start = next((e for e in rows if e['event'] in lifecol.STARTS), None)
        out.append({'id': f'{stage}#{key}', 'stage': stage, 'source': 'workflow-lifecycle', 'fidelity': 'exact',
                    'claim_id': next((e['claim_id'] for e in reversed(rows) if e['claim_id']), None),
                    'started_at': start['at'] if start else None, 'ended_at': ended['at'] if ended else None, 'outcome': outcome,
                    'runs': runs, 'reason': next((e['reason'] for e in reversed(rows) if e['reason']), None)})
    return out, loose


def _fallback_episodes(cp, events):
    """Episodes older producers leave evidence for: a passed receipt (with its creation time when it has one) and each
    recorded recovery. Their start is unknown unless the record states it, and their fidelity says so.

    History is kept when a stage also has lifecycle events. A checkpoint record is dropped only when a lifecycle event of the
    same stage and kind (`accepted`/`revalidated` for a receipt, `recovered` for a recovery) carries the same `claim_id`: the
    id Workflow 1.12.0 writes on both. A record with no claim id (legacy) is always kept, and neither a shared stage nor a
    shared timestamp ever suppresses anything."""
    out = []
    if not cp:
        return out
    seen = {(e['stage'], 'accepted' if e['event'] in ('accepted', 'revalidated') else e['event'], e['claim_id'])
            for e in events if e['stage'] and e['claim_id']}
    for rec in wf.accepted_receipts(cp.get('_receipts')):
        if rec.get('claim_id') and (rec['stage'], 'accepted', rec['claim_id']) in seen:
            continue
        out.append({'id': f"{rec['stage']}#receipt", 'stage': rec['stage'], 'source': 'checkpoint-receipt', 'fidelity': 'partial',
                    'claim_id': rec.get('claim_id'), 'started_at': rec.get('created_at'), 'ended_at': rec['at'], 'outcome': 'accepted', 'runs': [],
                    'reason': 'revalidation receipt' if rec.get('mode') == 'revalidate' else None})
    for index, rec in enumerate(cp.get('recoveries') or []):
        if rec['stage'] and not (rec.get('claim_id') and (rec['stage'], 'recovered', rec['claim_id']) in seen):
            out.append({'id': f"{rec['stage']}#recovery-{index + 1}", 'stage': rec['stage'], 'source': 'checkpoint-recovery',
                        'fidelity': 'partial', 'claim_id': rec.get('claim_id'), 'started_at': rec.get('started_at'), 'ended_at': rec['at'],
                        'outcome': 'recovered', 'runs': [], 'reason': rec['reason'] or None,
                        **({'identity': rec['identity']} if rec.get('identity') else {})})
    return out


def _selected(stage, plan, cp, evidence):
    if plan['state'] == 'available':
        return stage in {s['id'] for s in plan['stages']}
    if stage.startswith('qa_') or stage.startswith('manual_'):
        flag = (cp or {}).get('processes', {}).get('qa' if stage.startswith('qa_') else 'user_manual')
        return flag if flag is not None else stage in evidence
    return True


def build_stages(now, x, lifecycle, runs):
    cp = x['cp']
    if not x['workflow_mode']:
        return [], [], {}, {}
    plan = (cp or {}).get('stage_plan') or {'state': 'absent', 'stages': []}
    receipts = {r['stage']: r for r in wf.accepted_receipts(x['receipts'])}
    active_stage = (cp or {}).get('stage')
    events = lifecycle['events']
    episodes, loose = _episodes(events, active_stage)
    with_lifecycle = {e['stage'] for e in events if e['stage']}
    episodes += _fallback_episodes(dict(cp or {}, _receipts=x['receipts']), events)
    evidence = set(receipts) | {r['stage'] for r in runs if r['stage']} | with_lifecycle | ({active_stage} if active_stage else set())
    if plan['state'] == 'available':
        order = [(s['id'], s['label']) for s in plan['stages']]
    else:
        order = [(s, None) for s in BASE_STAGES]
    known = {s for s, _ in order}
    order += [(s, None) for s in BASE_STAGES if s not in known]  # not in the plan: listed as excluded, never dropped
    known = {s for s, _ in order}
    order += [(s, None) for s in sorted(evidence - known)]
    # Attribute runs to episodes only through an explicit record: a lifecycle event naming the run, or a claim id shared
    # with exactly one episode (settled in build_runs). Everything else is listed as an unknown run.
    by_episode = {}
    for r in runs:
        if r['episode_id']:
            by_episode.setdefault(r['episode_id'], []).append(r['run_id'])
    stage_rows = []
    for position, (sid, label) in enumerate(order):
        selected = _selected(sid, plan, cp, evidence)
        mine = [r for r in runs if r['stage'] == sid]
        eps = sorted((e for e in episodes if e['stage'] == sid), key=lambda e: (parse_time(e['started_at'] or e['ended_at']) or EPOCH, e['id']))
        for n, e in enumerate(eps, 1):
            e['n'] = n
            e['runs'] = list(dict.fromkeys([*e['runs'], *by_episode.get(e['id'], [])]))
        unknown_runs = [r['run_id'] for r in mine if r['episode_id'] is None]
        stage_events = [e for e in events if e['stage'] == sid]
        times = ([receipts[sid]['at']] if sid in receipts else []) + [e['at'] for e in stage_events if e['event'] in ('accepted', 'revalidated')]
        accepted_at = max(times, key=parse_time) if times else None
        marks = [e['event'] for e in stage_events if e['event'] in ('accepted', 'revalidated', 'invalidated', 'revalidation-stale')]
        flagged = (cp or {}).get('receipt_flags', {}).get(sid, {}).get('stale')
        if flagged or (marks and marks[-1] in ('invalidated', 'revalidation-stale')):
            validity = 'stale'
        elif marks and marks[-1] in ('accepted', 'revalidated'):
            validity = 'current'
        else:
            validity = 'unknown'  # a recorded receipt alone does not prove it is current
        if not selected:
            status = 'excluded'
        elif active_stage == sid or any(e['outcome'] == 'running' for e in eps):
            status = 'running'
        elif accepted_at:
            status = 'accepted'
        else:
            status = 'pending'
        durations = [r['duration']['value'] for r in mine if r['duration'].get('value') is not None]
        starts = [t for t in [*(r['started_at'] for r in mine), *(e['started_at'] for e in eps)] if parse_time(t)]
        ends = [t for t in [*(r['ended_at'] for r in mine), *(e['ended_at'] for e in eps)] if parse_time(t)]
        # `open` means something confirms the stage is running now: a live run, a running episode or the active claim.
        # A stage whose last end is simply not recorded is not open; the UI draws it as "end unknown", never to now.
        is_open = selected and (active_stage == sid or any(r['worker_status'] in LIVE for r in mine)
                                or any(e['outcome'] == 'running' for e in eps))
        first_start = min(starts, key=parse_time) if starts else None
        last_end = None if is_open or not ends else max(ends, key=parse_time)
        # Completeness: a known end closes the stage only when every relevant run and episode has a resolved end, whatever its
        # start. A run that is not live and records no end is unresolved unless its episode has an end (a lifecycle accepted,
        # recovered or invalidated event bounds it). An episode that is neither running nor ended is unresolved. `last_end`
        # keeps the last end that was recorded.
        ended_episodes = {e['id'] for e in eps if e['ended_at']}
        partial = (any(r['worker_status'] not in LIVE and not parse_time(r['ended_at']) and r['episode_id'] not in ended_episodes for r in mine)
                   or any(e['outcome'] in ('unknown', 'rejected-completion') and not e['ended_at'] for e in eps))
        timing = ('open' if is_open else 'unknown' if not first_start else 'end-unknown' if (not last_end or partial) else 'closed')
        stage_rows.append({
            'id': sid, 'label': label or _label(sid), 'order': position + 1, 'selected': selected, 'status': status,
            'validity': validity, 'accepted_at': accepted_at, 'episodes': eps, 'unknown_runs': unknown_runs,
            'run_count': len(mine), 'failed_runs': sum(1 for r in mine if r['worker_status'] in FAILED),
            'run_time': {**_m(sum(durations), 'delegation-ledger', now, 'partial'), 'complete': len(durations) == len(mine),
                         'sources': ['delegation-ledger'], 'label': 'summed, may overlap'} if mine else unknown(),
            'models': sorted({r['actual_model']['value'] for r in mine if r['actual_model'].get('value')}),
            'first_start': first_start, 'last_end': last_end, 'open': bool(is_open), 'timing': timing})
    return stage_rows, loose, {e['id']: e for e in episodes}, plan


# ---- workstreams --------------------------------------------------------------------------------------------------------

def build_membership(x):
    """Per task: (workstream id, origin). Explicit marked assignment, then the author's legend tag, then Shared. Returns the
    mapping plus the marked lanes' dated assignment records and any task two marked lanes both claim."""
    tk, loaded = x['tk'], x['loaded']
    tasks = {t['id'] for t in tk['tasks']}
    lanes = {}
    for rec in loaded['all']:
        if rec['kind'] == 'lane':
            lanes.setdefault(rec['id'], []).append(rec)
    marked = {lid: recs for lid, recs in lanes.items() if recs[-1].get('semantics') == 'workstream'}
    claims = {}
    for lid, recs in marked.items():
        for tid in recs[-1].get('tasks') or []:
            if tid in tasks:
                claims.setdefault(tid, []).append((recs[-1].get('ts') or '', lid))
    member, conflicts = {}, {}
    legend = tk.get('legend') or {}
    for t in tk['tasks']:
        tid = t['id']
        if tid in claims:
            ordered = sorted(claims[tid])
            member[tid] = (ordered[-1][1], 'facts-marked')  # an explicit later assignment supersedes an earlier one
            if len(ordered) > 1:
                conflicts[tid] = [lid for _, lid in ordered]
        elif t.get('workstream') in legend:
            member[tid] = (f"tag:{t['workstream']}", 'tasks-tag')
        else:
            member[tid] = ('shared', 'shared')
    return member, marked, conflicts


def make_ws_at(member, marked):
    """workstream(tasks, start, attempt): the one workstream every task of a run belonged to at the run's start, else None.
    A run with no valid start time has no moment to place against the dated assignments, so its workstream is unknown
    unless the attempt itself names a marked workstream (`workstream` or `lane_id`) that holds all of its tasks."""
    def lane_at(tid, moment):
        found = []
        for lid, recs in marked.items():
            current = None
            for rec in recs:
                stamp = parse_time(rec.get('ts'))
                if stamp and stamp <= moment:
                    current = rec
            if current and tid in (current.get('tasks') or []):
                found.append(lid)
        return found

    def explicit(tasks, attempt):
        ref = next((attempt.get(k) for k in ('workstream', 'lane_id') if isinstance(attempt.get(k), str)), None) if attempt else None
        if ref in marked and all(t in (marked[ref][-1].get('tasks') or []) for t in tasks):
            return ref
        return None

    def ws_at(tasks, start, attempt=None):
        if not tasks:
            return None
        moment = parse_time(start)
        if moment is None:
            return explicit(tasks, attempt)
        ids = set()
        for tid in tasks:
            if tid not in member:
                return None
            lanes = lane_at(tid, moment)
            if len(lanes) > 1:
                return None
            ids.add(lanes[0] if lanes else (member[tid][0] if member[tid][1] != 'facts-marked' else None))
        return ids.pop() if len(ids) == 1 and None not in ids else None
    return ws_at


def build_workstreams(x, member, marked, conflicts, runs, blockers):
    tk = x['tk']
    legend = tk.get('legend') or {}
    done = {t['id'] for t in tk['tasks'] if t['done']}
    blocked_targets = {b['target'] for b in blockers if b.get('source') == 'facts'}
    live_tasks = {tid for r in runs if r['worker_status'] in LIVE for tid in r['tasks']}
    # every marked workstream is listed, including one that lost all its tasks to a later assignment: it keeps its owners and
    # the conflict, while each task's bucket stays on the winner
    groups = {lid: {'origin': 'facts-marked', 'tasks': []} for lid in marked}
    for t in tk['tasks']:
        ws_id, origin = member[t['id']]
        groups.setdefault(ws_id, {'origin': origin, 'tasks': []})['tasks'].append(t['id'])
    out = []
    for ws_id, group in sorted(groups.items(), key=lambda kv: (kv[1]['origin'] == 'shared', kv[0])):
        if ws_id in marked:
            latest = marked[ws_id][-1]
            label = clean(latest.get('label') or ws_id, 60)
            owners, previous = [], None
            for rec in marked[ws_id]:
                agent = rec.get('owner')
                if agent and agent != previous:
                    if owners:
                        owners[-1]['to'] = rec.get('ts')
                    owners.append({'agent': agent, 'from': rec.get('ts'), 'to': None})
                    previous = agent
            if latest.get('state') == 'closed' and owners and owners[-1]['to'] is None:
                owners[-1]['to'] = latest.get('ts')
            lane_blocked = ws_id in blocked_targets
            description = None
        elif ws_id.startswith('tag:'):
            info = legend.get(ws_id[4:]) or {}
            label, owners, lane_blocked, description = info.get('label') or ws_id, [], False, info.get('description')
        else:
            label, owners, lane_blocked, description = 'Shared', [], False, 'Tasks no workstream claims'
        buckets = {'done': [], 'blocked': [], 'active': [], 'waiting': []}
        for tid in group['tasks']:
            if tid in done:
                buckets['done'].append(tid)
            elif tid in blocked_targets or lane_blocked:
                buckets['blocked'].append(tid)
            elif tid in live_tasks:
                buckets['active'].append(tid)
            else:
                buckets['waiting'].append(tid)
        out.append({'id': ws_id, 'label': label, 'description': description, 'origin': group['origin'], 'tasks': buckets,
                    'owners': owners, 'run_ids': [r['run_id'] for r in runs if r['workstream'] == ws_id],
                    'conflicts': [{'task': tid, 'workstreams': lanes} for tid, lanes in sorted(conflicts.items())
                                  if ws_id in lanes]})
    return out


# ---- decisions ----------------------------------------------------------------------------------------------------------

def _answer(kind, value, options):
    """An answer as option text plus its explicit index when known (`index` is an int, a list for multiple, or null). The UI
    highlights by that index, or by exact option text; it never decodes a letter. A value that names no option keeps
    `index: null` and highlights nothing."""
    def one(v):
        return options.index(v) if isinstance(v, str) and v in options else None
    if isinstance(value, list):
        idx = [one(v) for v in value]
        return {'kind': kind, 'value': value, 'index': None if None in idx else idx}
    return {'kind': kind, 'value': value, 'index': one(value)}


def _decision(fid, source, source_id, **kw):
    base = {'key': f'{fid}:{source}:{source_id}', 'source': source, 'source_id': source_id, 'question': None, 'options': [],
            'answer': None, 'state': 'pending', 'revision': 1, 'answer_digest': None, 'evidence': [], 'evidence_links': [], 'url': None,
            'decided_by': None, 'observed_at': None, 'answered_at': None, 'applied': None, 'stage': None}
    base.update(kw)
    return base


def build_decisions(ctx, now, x, fid, clar):
    loaded = x['loaded']
    out, sources = [], []
    revisions = {}
    for rec in loaded['all']:
        if rec['kind'] == 'decision':
            revisions[rec['id']] = revisions.get(rec['id'], 0) + 1
    for rec in sorted((r for r in loaded['current'] if r['kind'] == 'decision'), key=lambda r: (len(r['id']), r['id'])):
        status = rec.get('status')
        evidence = rec.get('evidence') or ''
        answered = status == 'made' and rec.get('selected')
        out.append(_decision(
            fid, 'facts', rec['id'], question=clean(rec.get('question'), 200) or None, options=rec.get('options') or [],
            answer=_answer('single', rec['selected'], rec.get('options') or []) if answered else None,
            state='withdrawn' if status == 'withdrawn' else 'answered' if answered else 'pending', revision=revisions.get(rec['id'], 1),
            evidence=[clean(evidence, 200)] if evidence else [], url=evidence if evidence.startswith('http') else None,
            decided_by=rec.get('decided_by') if answered else None, observed_at=rec.get('ts'),
            answered_at=rec.get('ts') if answered else None))
    sources.append({'name': 'facts', 'state': 'available' if ctx.facts.exists() else 'absent'})
    raw = ctx.feature_dir / 'workflow' / 'decisions.json'
    if x['wf_decisions_exist']:
        for d in x['wf_decisions']:
            raw_status = d['raw_status'] if d['raw_status'] in ('pending', 'conflict', 'answered', 'applied') else 'pending'
            answered = raw_status in ('answered', 'applied') and d['selected'] is not None
            out.append(_decision(
                fid, 'workflow', d['id'], question=d['question'], options=d['options'],
                answer={'kind': 'multiple' if d['multiple'] else 'single', 'value': d['selected'], 'index': d['selected_index']} if answered else None,
                state=raw_status, revision=max(1, d['revision']), answer_digest=d['answer_digest'],
                evidence=d['applied_evidence'], url=d['url'], decided_by=d['author'] if answered else None,
                observed_at=iso(now), answered_at=d['at'] if answered else None,
                applied={'at': None, 'evidence': d['applied_evidence']} if raw_status == 'applied' else None))
        sources.append({'name': 'workflow', 'state': 'available'})
    else:
        sources.append({'name': 'workflow', 'state': 'invalid' if raw.is_file() else 'absent'})
    top = {}
    for item in clar['items']:
        top[item['source_id']] = max(top.get(item['source_id'], 0), item['revision'])
    for item in sorted(clar['items'], key=lambda i: (i['source_id'], i['revision'])):
        current = item['revision'] == top[item['source_id']]
        out.append(_decision(
            fid, 'clarification', item['source_id'] if current else f"{item['source_id']}@r{item['revision']}",
            question=item['question'], options=item['options'], answer=item['answer'],
            state=item['state'] if current else 'superseded', revision=item['revision'], evidence=item['evidence'],
            evidence_links=item['evidence_links'], url=item['url'],
            decided_by=item['editor'] if item['answer'] else None, observed_at=item['observed_at'], answered_at=item['answered_at'],
            applied=item['applied'], stage='clarify'))
    note = ', '.join(p for p in (f"{clar['skipped']} unreadable item(s) skipped" if clar.get('skipped') else '',
                                 'file over the size cap, not read' if clar.get('truncated') else '') if p) or None
    sources.append({'name': 'clarification', 'state': clar['state'], **({'note': note} if note else {})})
    pending = [d for d in out if d['state'] in ('pending', 'conflict')]
    made = [d for d in out if d['state'] not in ('pending', 'conflict')]
    return {'pending': pending, 'made': made, 'sources': sources}


# ---- sources, attention, timeline, history ------------------------------------------------------------------------------

def build_sources(ctx, reads):
    """The producer files this report was built from. Each entry describes the bytes the collectors actually parsed (hash,
    size and read time come from the read itself, never from a second read). `consistent` is false when the file changed on
    disk after it was read, or was read twice with different bytes, so the report may mix generations."""
    out = []
    known = {os.path.normpath(str(p)): n for n, p in (
        ('workflow-checkpoint', ctx.feature_dir / 'workflow' / 'checkpoint.json'),
        ('workflow-delegations', ctx.feature_dir / 'workflow' / 'delegations.json'),
        ('workflow-decisions', ctx.feature_dir / 'workflow' / 'decisions.json'),
        ('workflow-lifecycle', ctx.feature_dir / 'workflow' / 'lifecycle.jsonl'),
        ('clarifications', ctx.feature_dir / 'workflow' / 'clarifications.json'),
        ('tasks', ctx.feature_dir / 'tasks.md'), ('facts', ctx.facts), ('self-report', selfreport.path_of(ctx)))}
    changed = reads.changed() if reads else set()
    root = os.path.normpath(str(ctx.root))
    # Every file the build read is a source, not a fixed list: host snapshots, delegate run journals, project config and so on.
    # A file the report knows by name keeps it; any other is named by its repository-relative path (a file outside the
    # repository by `external:<file name>`, never an absolute path).
    for key, row in sorted((reads.rows if reads else {}).items()):
        inside = os.path.commonpath([root, key]) == root if os.path.splitdrive(root)[0] == os.path.splitdrive(key)[0] else False
        rel = PurePath(os.path.relpath(key, root)).as_posix() if inside else 'external:' + os.path.basename(key)
        entry = {'name': known.get(key) or rel, 'path': rel, 'fingerprint': row['sha'][:16], 'generation': None,
                 'read_at': row['read_at'], 'bytes': row['size'], 'consistent': key not in changed}
        if row['truncated']:
            entry['note'] = f"only {row['bytes']} of {row['size']} bytes read"
        out.append(entry)
    order = list(known.values())
    out.sort(key=lambda e: (order.index(e['name']) if e['name'] in order else len(order), e['name']))
    return out


def build_history(x):
    """Legacy lane ids and where they went. A lane resolves to a run, a delegation identity or a workstream only through an
    explicit link; every other legacy id is listed as unresolved with its owner history, so a note or blocker that names it
    stays navigable."""
    lanes = x['lanes']
    aliases, unresolved = {}, []
    all_lane_records = {}
    for rec in x['loaded']['all']:
        if rec['kind'] == 'lane':
            all_lane_records.setdefault(rec['id'], []).append(rec)
    marked = {lid for lid, recs in all_lane_records.items() if recs[-1].get('semantics') == 'workstream'}
    for lane in lanes:
        rows = lane.get('rows') or []
        ids = [lane['id']]
        target = None
        if lane['id'] in marked:
            target = f"workstream:{lane['id']}"
        elif rows:
            target = f"run:{rows[0]['run_id']}" if len(rows) == 1 and rows[0].get('run_id') else f"identity:{lane['owner']}"
        elif lane['origin'] == 'host-child':
            target = f"run:host:{lane.get('host')}:{lane['owner']}"
        if target:
            aliases.update({i: target for i in ids})
        elif lane['origin'] == 'facts':
            owners, previous = [], None
            for rec in all_lane_records.get(lane['id'], []):
                if rec.get('owner') and rec['owner'] != previous:
                    if owners:
                        owners[-1]['to'] = rec.get('ts')
                    owners.append({'agent': clean(rec['owner'], 80), 'from': rec.get('ts'), 'to': None})
                    previous = rec['owner']
            unresolved.append({'id': lane['id'], 'label': clean(lane['label'], 60), 'owners': owners,
                               'reason': 'no run id or delegation identity names this lane'})
    for old, new in x['folded'].items():
        if old != new and new in aliases:
            aliases[old] = aliases[new]
        elif old != new and new:
            aliases[old] = f'lane:{new}'
    for old, new in x['identity'].items():
        if old != new:
            aliases.setdefault(old, aliases.get(new) or f'lane:{new}')
    for wid, name in x['retired'].items():
        aliases.setdefault(wid, f'identity:{name}')
    return {'lane_aliases': dict(sorted(aliases.items())), 'unresolved': unresolved}


def build_attention(runs, decisions, blockers, orchestrator, ctx, x):
    items = []
    for b in blockers:
        by = b.get('by') or {}
        items.append({'id': f"blocker:{b['id']}", 'kind': 'blocker', 'severity': 'high',
                      'text': clean(f"{b['id']} on {b['target']}: {by.get('type')} {by.get('ref')}", 160),
                      'refs': [b['target']], 'since': b.get('since')})
    for d in decisions['pending']:
        items.append({'id': f"decision:{d['key']}", 'kind': 'decision', 'severity': 'medium',
                      'text': clean(('Conflicting answers: ' if d['state'] == 'conflict' else 'Needs an answer: ') + (d['question'] or d['source_id']), 160),
                      'refs': [d['key']], 'since': d['observed_at']})
    healed = {}
    for r in runs:
        if r['worker_status'] == 'successful' and r['started_at']:
            healed.setdefault(r['identity'], []).append(r['started_at'])
    for r in runs:
        if r['worker_status'] not in FAILED:
            continue
        later = any(s > (r['started_at'] or '') for s in healed.get(r['identity'], []))
        if not later:
            items.append({'id': f"failure:{r['run_id']}", 'kind': 'failure', 'severity': 'medium',
                          'text': clean(f"Run {r['run_id']} {r['worker_status']}; no recovery recorded", 160),
                          'refs': [r['run_id']], 'since': r['ended_at'] or r['started_at']})
    if orchestrator['host'] is None and not ctx.is_plan:
        cause = None
        try:
            from . import hooks_install
            cause = 'codex hooks not approved' if hooks_install.codex_unapproved(ctx.root) else None
        except Exception:
            cause = None
        if cause:
            items.append({'id': 'telemetry:codex-hooks', 'kind': 'telemetry', 'severity': 'info',
                          'text': 'No host telemetry: ' + cause, 'refs': [], 'since': None})
    rank = {'high': 0, 'medium': 1, 'info': 2}
    return sorted(items, key=lambda i: (rank[i['severity']], i['since'] or '', i['id']))


def build_timeline(x, stages, loose, runs, decisions, blockers, history, fid):
    out = []

    def add(kind, at, text, refs, fidelity, key):
        if at and parse_time(at):
            out.append({'id': _stable(kind, at, key), 'at': at, 'kind': kind, 'text': clean(text, NOTE_CAP), 'refs': refs, 'fidelity': fidelity})
    for e in x['lifecycle']['events']:
        if e['event'] in lifecol.STARTS:
            continue
        extra = f": {e['reason']}" if e['reason'] else ''
        cause = f" (caused by claim {e['caused_by_claim_id']})" if e['caused_by_claim_id'] and not e['reason'] else ''
        subject = _label(e['stage']) if e['stage'] else 'Feature'  # a pause or recovery with no claim held is feature-level
        add(TIMELINE_KIND[e['event']], e['at'], f"{subject} {e['event'].replace('-', ' ')}{extra}{cause}",
            [*([e['stage']] if e['stage'] else []), *e['delegation_run_ids']], 'recorded', e['event_id'])
    for s in stages:
        for ep in s['episodes']:
            if ep['source'] == 'checkpoint-receipt':
                add('stage', ep['ended_at'], f"{s['label']} accepted" + (' (revalidation)' if ep['reason'] else ''), [s['id']], 'partial', ep['id'])
            elif ep['source'] == 'checkpoint-recovery':
                add('recovery', ep['ended_at'], f"{s['label']} recovered: {ep['reason'] or 'reason not recorded'}", [s['id']], 'partial', ep['id'])
    retried = {r['retry_of']: r for r in runs if r['retry_of']}
    by_identity = {}
    for r in runs:
        by_identity.setdefault(r['identity'], []).append(r)
    for r in runs:
        if r['worker_status'] in FAILED:
            add('failure', r['ended_at'] or r['started_at'], f"Run {r['run_id']} {r['worker_status']}", [r['run_id']], 'recorded', r['run_id'])
            fix = retried.get(r['run_id'])
            if fix:
                add('recovery', fix['started_at'], f"Run {fix['run_id']} retried {r['run_id']} (recorded link)", [fix['run_id'], r['run_id']], 'recorded', 'retry:' + fix['run_id'])
            else:
                later = [o for o in by_identity.get(r['identity'], []) if o['worker_status'] == 'successful'
                         and (o['started_at'] or '') > (r['started_at'] or '')]
                if later:
                    add('recovery', later[0]['started_at'], f"Later successful run {later[0]['run_id']} for {r['run_id']} (no retry link recorded)",
                        [later[0]['run_id'], r['run_id']], 'inferred', 'infer:' + r['run_id'])
    for d in decisions['made']:
        add('decision', d['answered_at'] or d['observed_at'], f"{d['source_id']} {d['state']}" + ('' if d['answered_at'] else ' (time not recorded)'),
            [d['key']], 'recorded' if d['answered_at'] else 'observed', d['key'])
    resolved = {}
    for rec in x['loaded']['all']:
        kind = rec['kind']
        if kind == 'note' and rec.get('ts'):
            target = rec.get('target')
            add('note', rec['ts'], f"{rec['id']}: {rec.get('text') or ''}",
                [history['lane_aliases'].get(target) or target] if target else [], 'recorded', rec['id'])
        elif kind == 'block':
            if rec.get('state') == 'open':
                add('blocker', rec.get('ts'), f"{rec['id']} opened on {rec.get('target')}", [t for t in [rec.get('target')] if t], 'recorded', f"{rec['id']}:open")
            elif rec.get('state') == 'resolved':
                add('blocker', rec.get('resolved_at') or rec.get('ts'), f"{rec['id']} resolved", [t for t in [rec.get('target')] if t], 'recorded', f"{rec['id']}:closed")
    out.sort(key=lambda e: (parse_time(e['at']), e['id']))
    return out


# ---- assembly -----------------------------------------------------------------------------------------------------------

def _orchestrator(ctx, now, x, v2):
    o = dict(v2['orchestrator'])
    main = x['main']
    report = selfreport.applicable(selfreport.read(ctx), o['session_id'])
    provenance = {}
    for name in ('model', 'effort'):
        observed = o.get(name)
        if observed and observed.get('value') is not None:
            provenance[name] = 'host-hook'
        elif name in report:
            o[name] = {'value': report[name]['value'], 'source': 'self-report', 'observed_at': report[name]['at'], 'fidelity': 'estimated'}
            provenance[name] = 'self-report'
        else:
            provenance[name] = 'none'
    provenance['context'] = 'host-hook' if o['context'].get('value') is not None else 'none'
    elapsed = main.get('elapsed_ms') if main else None
    host_elapsed = (_m(int(elapsed['value'] // 1000), elapsed['source'], parse_time(elapsed['observed_at']) or now, elapsed.get('fidelity') or 'exact')
                    if elapsed else unknown())
    provenance['host_elapsed'] = 'host-hook' if elapsed else 'none'
    provenance['active'] = 'host-hook' if o['active'].get('value') is not None else 'none'
    reported = [n for n, p in provenance.items() if p == 'self-report']
    note = (f"{' and '.join(reported)} self-reported by the coordinator, not observed by the host" if reported else
            'no host telemetry recorded' if o['host'] is None else None)
    return {'host': o['host'], 'session_id': o['session_id'], 'model': o['model'], 'effort': o['effort'], 'context': o['context'],
            'host_elapsed': host_elapsed, 'active': o['active'], 'since': o['since'], 'provenance': provenance, 'note': note}


def build(ctx, now, rev, state, v2, aux):
    x = dict(aux)
    cp = x['cp']
    fid = v2['feature']['id']
    x['receipts'] = _raw_receipts(ctx)
    x['ledger_feature'] = wf.ledger_feature(ctx.feature_dir)
    x['lifecycle'] = lifecycle = lifecol.collect(ctx.feature_dir)
    clar = clarcol.collect(ctx.feature_dir)
    x['workflow_mode'] = x['workflow_mode'] or lifecycle['state'] != 'absent' or (cp or {}).get('stage_plan', {}).get('state') == 'available'
    member, marked, conflicts = build_membership(x)
    ws_at = make_ws_at(member, marked)
    # episodes are needed before runs (a run joins an episode through an explicit claim/event link), and runs before stages
    active_stage = (cp or {}).get('stage')
    pre_episodes, _ = _episodes(lifecycle['events'], active_stage)
    episodes_by_run, claim_episodes = {}, {}
    for ep in pre_episodes:
        for rid in ep['runs']:
            episodes_by_run.setdefault(rid, ep)
        if ep['claim_id']:
            claim_episodes.setdefault(ep['claim_id'], []).append(ep)
    runs, dispatch = build_runs(ctx, now, x, episodes_by_run, claim_episodes, ws_at)
    # Acceptance names the exact validated run (`candidate_run_id`). `delegation_run_ids` is claim membership: it puts a run
    # in an episode and never makes it the accepted candidate. The latest event for a run wins.
    candidate = {}
    for e in lifecycle['events']:
        if e['event'] in ('accepted', 'rejected-completion') and e['candidate_run_id']:
            candidate[e['candidate_run_id']] = e['event'] == 'accepted'
    for r in runs:
        r['candidate_accepted'] = candidate.get(r['run_id'])
    stages, loose, _, plan = build_stages(now, x, lifecycle, runs)
    decisions = build_decisions(ctx, now, x, fid, clar)
    workstreams = build_workstreams(x, member, marked, conflicts, runs, x['blockers'])
    history = build_history(x)
    orchestrator = _orchestrator(ctx, now, x, v2)
    attention = build_attention(runs, decisions, x['blockers'], orchestrator, ctx, x)
    timeline = build_timeline(x, stages, loose, runs, decisions, x['blockers'], history, fid)
    sources = build_sources(ctx, aux.get('reads'))
    for s in sources:
        if s['name'] == 'workflow-checkpoint':
            s['generation'] = (cp or {}).get('generation')
        elif s['name'] == 'workflow-lifecycle':
            s['generation'] = max([e['generation'] for e in lifecycle['events'] if e['generation'] is not None], default=None)
    if lifecycle['state'] != 'absent':
        notes = ', '.join(p for p in (
            'torn final line ignored' if lifecycle['torn'] else '', f"{lifecycle['corrupt']} corrupt line(s) skipped" if lifecycle['corrupt'] else '',
            f"{lifecycle['skipped']} unusable record(s) skipped" if lifecycle['skipped'] else '',
            f"{len(lifecycle['conflicts'])} conflicting duplicate event id(s)" if lifecycle['conflicts'] else '',
            f"older events not read: {lifecycle['bytes']} bytes, newest {lifecol.READ_CAP} read" if lifecycle['truncated'] else '') if p)
        for s in sources:
            if s['name'] == 'workflow-lifecycle' and notes:
                s['note'] = notes
    unstable = [s['name'] for s in sources if not s['consistent']]
    if unstable:  # a file moved on while the others were read: do not certify this snapshot as current
        v2['collection']['dirty'] = True
        v2['collection']['inconsistent_sources'] = unstable
    # feature
    feature = dict(v2['feature'])
    stage_row = next((s for s in stages if s['id'] == (feature.get('stage') or {}).get('value')), None)
    if feature.get('stage'):
        feature['stage'] = {'value': feature['stage']['value'], 'status': stage_row['status'] if stage_row else None,
                            'validity': stage_row['validity'] if stage_row else 'unknown', 'source': feature['stage']['source'],
                            'checkpoint_status': feature['stage'].get('status')}
    recorded = parse_time((cp or {}).get('started_at'))
    evidence_starts = [t for t in [parse_time(v2['feature']['started_at']), *map(parse_time, (r['started_at'] for r in runs))] if t]
    earliest = min(evidence_starts, default=None)
    if recorded and (earliest is None or recorded <= earliest):
        feature['started_at'] = _m(iso(recorded), 'workflow-checkpoint', now, 'exact')
    elif earliest:
        feature['started_at'] = _m(iso(earliest), 'earliest-evidence', now, 'estimated')
    else:
        feature['started_at'] = unknown()
    na = (cp or {}).get('next_action')
    feature['next_action'] = {**na, 'source': 'workflow-checkpoint'} if na else None
    tasks = {t['id']: {'title': t['title'], 'phase': t['phase'], 'done': t['done'], 'parallel': t['parallel'],
                       'depends_on': t['depends_on'], 'workstream': member[t['id']][0]} for t in x['tk']['tasks']}
    selected = [s for s in stages if s['selected']]
    return {'schema': SCHEMA_V3, 'rev': rev, 'generated_at': iso(now), 'stale_after_seconds': x['stale_after'],
            'collection': v2['collection'], 'feature': feature, 'orchestrator': orchestrator, 'attention': attention,
            'stages': stages, 'workstreams': workstreams, 'tasks': tasks, 'runs': runs, 'dispatch': dispatch,
            'decisions': decisions, 'timeline': timeline, 'history': history, 'sources': sources,
            'summary': {'tasks_total': len(tasks), 'tasks_done': sum(1 for t in tasks.values() if t['done']),
                        'stages_selected': len(selected), 'stages_accepted': sum(1 for s in selected if s['accepted_at']),
                        'runs_total': len(runs), 'runs_failed': sum(1 for r in runs if r['worker_status'] in FAILED),
                        'decisions_pending': len(decisions['pending']), 'blockers_open': len(x['blockers'])}}


def _raw_receipts(ctx):
    from .util import read_json
    data = read_json(ctx.feature_dir / 'workflow' / 'checkpoint.json')
    return data.get('receipts') if isinstance(data, dict) else None
