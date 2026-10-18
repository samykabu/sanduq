"""Structural validation of a projection document, for tests and for consumers that want a check before they render.

    problems = validate(document)    # [] when the document is well formed

`validate` picks the check from the document's `schema` (`sanduq.progress.v3` or `sanduq.progress.v2`). It checks shape,
enums, id uniqueness, text bounds and the cross-references the Timeline view relies on; it never repairs a document."""
from . import SCHEMA_V2, SCHEMA_V3
from .util import parse_time

V2_KEYS = ('schema', 'rev', 'generated_at', 'stale_after_seconds', 'collection', 'feature', 'orchestrator', 'lanes',
           'unassigned_tasks', 'tasks', 'decisions', 'blockers', 'events', 'summary')
V3_KEYS = ('schema', 'rev', 'generated_at', 'stale_after_seconds', 'collection', 'feature', 'orchestrator', 'attention', 'stages',
           'workstreams', 'tasks', 'runs', 'dispatch', 'decisions', 'timeline', 'history', 'sources', 'summary')
V3_SUMMARY = ('tasks_total', 'tasks_done', 'stages_selected', 'stages_accepted', 'runs_total', 'runs_failed', 'decisions_pending',
              'blockers_open')
V2_SUMMARY = ('tasks_total', 'tasks_done', 'lanes_active', 'blocked', 'decisions_pending')
STAGE_STATUS = ('pending', 'running', 'accepted', 'excluded')
VALIDITY = ('current', 'stale', 'unknown')
OUTCOMES = ('accepted', 'rejected-completion', 'recovered', 'paused', 'invalidated', 'running', 'unknown')
DECISION_STATES = ('pending', 'conflict', 'answered', 'applied', 'waived', 'superseded', 'withdrawn')
ATTENTION_KINDS = ('blocker', 'decision', 'failure', 'stale', 'telemetry')
SEVERITIES = ('high', 'medium', 'info')
TIMELINE_KINDS = ('stage', 'decision', 'failure', 'recovery', 'revalidation', 'note', 'blocker')
SOURCE_STATES = ('available', 'absent', 'unsupported', 'invalid')
BUCKETS = ('done', 'blocked', 'active', 'waiting')


def _measure(problems, where, value):
    if not isinstance(value, dict) or not {'value', 'source', 'observed_at', 'fidelity'} <= set(value):
        problems.append(f'{where}: not a measurement')


def _unique(problems, where, values):
    seen = set()
    for v in values:
        if v in seen:
            problems.append(f'{where}: duplicate {v!r}')
        seen.add(v)


def _bounded(problems, where, text, cap):
    if text is not None and (not isinstance(text, str) or len(text) > cap):
        problems.append(f'{where}: text longer than {cap}')


def validate(doc):
    if not isinstance(doc, dict):
        return ['document is not an object']
    schema = doc.get('schema')
    if schema == SCHEMA_V3:
        return validate_v3(doc)
    if schema == SCHEMA_V2:
        return validate_v2(doc)
    return [f'unknown schema {schema!r}']


def validate_v2(doc):
    problems = [f'missing {k}' for k in V2_KEYS if k not in doc]
    if problems:
        return problems
    problems += [f'summary missing {k}' for k in V2_SUMMARY if k not in doc['summary']]
    _unique(problems, 'lanes', [lane.get('id') for lane in doc['lanes']])
    for lane in doc['lanes']:
        for k in ('observed', 'status', 'elapsed', 'active', 'attempts', 'tasks'):
            if k not in lane:
                problems.append(f"lane {lane.get('id')}: missing {k}")
    return problems


def validate_v3(doc):
    problems = [f'missing {k}' for k in V3_KEYS if k not in doc]
    if problems:
        return problems
    problems += [f'summary missing {k}' for k in V3_SUMMARY if k not in doc['summary']]
    for name in ('model', 'effort', 'context', 'host_elapsed', 'active'):
        _measure(problems, f'orchestrator.{name}', doc['orchestrator'].get(name))
    if 'started_at' in doc['feature']:
        _measure(problems, 'feature.started_at', doc['feature']['started_at'])
    stages = doc['stages']
    _unique(problems, 'stages', [s['id'] for s in stages])
    run_ids = [r['run_id'] for r in doc['runs']]
    _unique(problems, 'runs', run_ids)
    held = set(run_ids)
    for s in stages:
        if s['status'] not in STAGE_STATUS or s['validity'] not in VALIDITY:
            problems.append(f"stage {s['id']}: bad status or validity")
        if (s['status'] == 'excluded') == s['selected']:
            problems.append(f"stage {s['id']}: excluded must mean not selected")
        for e in s['episodes']:
            if e['outcome'] not in OUTCOMES:
                problems.append(f"episode {e['id']}: bad outcome")
            problems += [f"episode {e['id']}: unknown run {r}" for r in e['runs'] if r not in held]
        problems += [f"stage {s['id']}: unknown run {r}" for r in s['unknown_runs'] if r not in held]
    for r in doc['runs']:
        for k in ('actual_model', 'effort', 'duration'):
            _measure(problems, f"run {r['run_id']}.{k}", r.get(k))
        for k in ('evidence_accepted', 'candidate_accepted'):
            if r.get(k) not in (True, False, None):
                problems.append(f"run {r['run_id']}: {k} must be true, false or null")
        _bounded(problems, f"run {r['run_id']}.summary", r.get('summary'), 160)
    task_ids = set(doc['tasks'])
    placed = []
    for w in doc['workstreams']:
        for b in BUCKETS:
            placed += w['tasks'][b]
        problems += [f"workstream {w['id']}: unknown run {r}" for r in w['run_ids'] if r not in held]
    _unique(problems, 'workstream task placement', placed)
    if set(placed) != task_ids:
        problems.append('workstreams do not place every task exactly once')
    for d in doc['decisions']['pending'] + doc['decisions']['made']:
        if d['state'] not in DECISION_STATES:
            problems.append(f"decision {d['key']}: bad state")
        _bounded(problems, f"decision {d['key']}.question", d.get('question'), 200)
    _unique(problems, 'decisions', [d['key'] for d in doc['decisions']['pending'] + doc['decisions']['made']])
    if any(d['state'] not in ('pending', 'conflict') for d in doc['decisions']['pending']):
        problems.append('decisions.pending holds a resolved decision')
    for s in doc['decisions']['sources']:
        if s['state'] not in SOURCE_STATES:
            problems.append(f"decision source {s['name']}: bad state")
    for a in doc['attention']:
        if a['kind'] not in ATTENTION_KINDS or a['severity'] not in SEVERITIES:
            problems.append(f"attention {a['id']}: bad kind or severity")
        _bounded(problems, f"attention {a['id']}", a['text'], 160)
    _unique(problems, 'timeline', [e['id'] for e in doc['timeline']])
    for e in doc['timeline']:
        if e['kind'] not in TIMELINE_KINDS:
            problems.append(f"timeline {e['id']}: bad kind")
        _bounded(problems, f"timeline {e['id']}", e['text'], 140)
    times = [parse_time(e['at']) for e in doc['timeline']]
    if None in times or times != sorted(times):
        problems.append('timeline is not in time order')
    for s in doc['sources']:
        if not {'name', 'path', 'fingerprint', 'generation', 'read_at'} <= set(s):
            problems.append(f"source {s.get('name')}: missing fields")
    return problems
