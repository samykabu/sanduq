"""Deterministic Markdown export of a projection. Same document in, same bytes out: no clock, no rev, stable order."""


def _m(measure):
    if not measure or measure.get('value') is None:
        return 'unknown'
    value = measure['value']
    if isinstance(value, dict):
        value = ', '.join(f'{k} {v}' for k, v in value.items() if v is not None)
    suffix = '' if measure.get('fidelity') == 'exact' else f" ({measure.get('fidelity')})"
    return f'{value}{suffix}'


def _cell(text):
    return str(text if text is not None else '').replace('|', '\\|').replace('\n', ' ')


def render(report):
    """Markdown for either projection: v3 (default) or the v2 compatibility document, chosen by its `schema`."""
    return render_v3(report) if report.get('schema') == 'sanduq.progress.v3' else render_v2(report)


def _t(value):
    return _cell(value if value is not None else 'unknown')


def _tasks_v3(report):
    """Every task grouped by phase, with its workstream and state (done, active, blocked or waiting). The checklist is the
    list a reader of the Markdown export has no other way to get."""
    state, label = {}, {}
    for w in report['workstreams']:
        label[w['id']] = w['label']
        for name, ids in w['tasks'].items():
            for tid in ids:
                state[tid] = name
    out, phase = ['', '## Tasks', ''], object()
    for tid, t in report['tasks'].items():
        if t['phase'] != phase:
            phase = t['phase']
            out += [f"### {phase or 'No phase'}", '']
        deps = f" (after {', '.join(t['depends_on'])})" if t['depends_on'] else ''
        where = label.get(t['workstream']) or t['workstream']
        out.append(f"- [{'x' if t['done'] else ' '}] {tid} {t['title']}{deps} - {where}, {state.get(tid) or ('done' if t['done'] else 'waiting')}")
    if not report['tasks']:
        out.append('None.')
    return out


def render_v3(report):
    f, s = report['feature'], report['summary']
    stage = f.get('stage')
    out = [f"# {f['title']}", '',
           f"{'Plan' if f.get('mode') == 'plan' else 'Feature'} `{f['id']}`" + (f", branch `{f['branch']}`" if f.get('branch') else '')
           + (f", stage {stage['value']} ({stage.get('status')}, {stage.get('validity')})" if stage else '')
           + (f", issue #{f['issue']['number']}" if f.get('issue') else '') + '.', '',
           f"Tasks {s['tasks_done']}/{s['tasks_total']} done, {s['stages_accepted']}/{s['stages_selected']} stages accepted, "
           f"{s['runs_total']} runs ({s['runs_failed']} failed), {s['blockers_open']} open blockers, "
           f"{s['decisions_pending']} pending decisions.", '']
    if f.get('next_action'):
        n = f['next_action']
        out += [f"Next: {n['text']} (evaluated {n.get('evaluated_at') or 'at an unknown time'})", '']
    o = report['orchestrator']
    out += ['## Orchestrator', '', f"- Host: {o.get('host') or 'unknown'}", f"- Model: {_m(o['model'])} ({o['provenance']['model']})",
            f"- Effort: {_m(o['effort'])} ({o['provenance']['effort']})", f"- Context: {_m(o['context'])}",
            f"- Host elapsed: {_m(o['host_elapsed'])}"] + ([f"- Note: {o['note']}"] if o.get('note') else []) + ['']
    if report['attention']:
        out += ['## Needs attention', ''] + [f"- {a['severity']} {a['kind']}: {a['text']}" for a in report['attention']] + ['']
    if report['stages']:
        out += ['## Stages', '', '| Stage | Status | Validity | Accepted | Runs | Failed | Episodes |', '|---|---|---|---|---|---|---|']
        for st in report['stages']:
            out.append('| ' + ' | '.join(_cell(x) for x in (st['label'], st['status'], st['validity'], st['accepted_at'] or '', st['run_count'],
                                                              st['failed_runs'], len(st['episodes']))) + ' |')
        out.append('')
    out += ['## Workstreams', '']
    for w in report['workstreams']:
        t = w['tasks']
        out.append(f"- {w['label']} ({w['origin']}): done {' '.join(t['done']) or '-'}; active {' '.join(t['active']) or '-'}; "
                   f"waiting {' '.join(t['waiting']) or '-'}; blocked {' '.join(t['blocked']) or '-'}")
    out += _tasks_v3(report)
    out += ['', '## Decisions', '']
    for label, key in (('Pending', 'pending'), ('Made', 'made')):
        for d in report['decisions'][key]:
            answer = d['answer']['value'] if d['answer'] else None
            who = d['decided_by'] or 'editor not recorded'
            out.append(f"- {label} {d['source_id']} [{d['source']}, {d['state']}]: {d['question'] or 'question not recorded'}"
                       + (f" -> {', '.join(answer) if isinstance(answer, list) else answer} ({who})" if answer else ''))
    if not (report['decisions']['pending'] or report['decisions']['made']):
        out.append('None recorded in: ' + (', '.join(x['name'] for x in report['decisions']['sources'] if x['state'] == 'available') or 'no readable source') + '.')
    unavailable = [x['name'] + ' ' + x['state'] for x in report['decisions']['sources'] if x['state'] != 'available']
    if unavailable:
        out.append('Not available: ' + ', '.join(unavailable) + '.')
    out += ['', '## Runs', '', '| Run | Identity | Stage | Worker status | Candidate accepted | Model | Duration |', '|---|---|---|---|---|---|---|']
    for r in report['runs']:
        out.append('| ' + ' | '.join(_cell(x) for x in (r['run_id'], r['identity'], r['stage'] or 'unknown', r['worker_status'],
                                                          {True: 'yes', False: 'no', None: 'unknown'}[r['candidate_accepted']],
                                                          _m(r['actual_model']), _m(r['duration']))) + ' |')
    if report['dispatch']:
        out += ['', 'Dispatch intents without a run: ' + ', '.join(d['intent_id'] for d in report['dispatch'])]
    out += ['', '## Timeline', '']
    out += [f"- {e['at']} {e['kind']}: {e['text']}" + ('' if e['fidelity'] == 'recorded' else f" ({e['fidelity']})") for e in report['timeline']] or ['None.']
    return '\n'.join(out) + '\n'


def render_v2(report):
    f, s = report['feature'], report['summary']
    out = [f"# {f['title']}", '',
           f"{'Plan' if f.get('mode') == 'plan' else 'Feature'} `{f['id']}`" + (f", branch `{f['branch']}`" if f.get('branch') else '')
           + (f", stage {f['stage']['value']}" if f.get('stage') else '')
           + (f", issue #{f['issue']['number']}" if f.get('issue') else '') + '.', '',
           f"Tasks {s['tasks_done']}/{s['tasks_total']} done, {s['lanes_active']} active lanes, "
           f"{s['blocked']} open blockers, {s['decisions_pending']} pending decisions.", '']
    o = report['orchestrator']
    out += ['## Orchestrator', '', f"- Host: {o.get('host') or 'unknown'}", f"- Model: {_m(o['model'])}",
            f"- Effort: {_m(o['effort'])}", f"- Context: {_m(o['context'])}", f"- Elapsed: {_m(o['elapsed'])}", '']
    out += ['## Lanes', '', '| Lane | Label | Status | Requested | Observed model | Done | Active | Waiting | Blocked |',
            '|---|---|---|---|---|---|---|---|---|']
    for lane in report['lanes']:
        r, t = lane['requested'], lane['tasks']
        req = '/'.join(str(r.get(k)) for k in ('harness', 'model', 'effort') if r.get(k)) or 'unknown'
        out.append('| ' + ' | '.join(_cell(x) for x in (
            lane['id'], lane['label'], lane['status'], req, _m(lane['observed']['model']), ' '.join(t['done']),
            ' '.join(t['active']), ' '.join(t['waiting']), ' '.join(b['task'] for b in t['blocked']))) + ' |')
    un = report['unassigned_tasks']
    if any(un.values()):
        out += ['', 'Unassigned: ' + '; '.join(f"{k} {' '.join(x['task'] if isinstance(x, dict) else x for x in v)}"
                                               for k, v in un.items() if v)]
    out += ['', '## Tasks', '']
    phase = object()
    for tid, t in report['tasks'].items():
        if t['phase'] != phase:
            phase = t['phase']
            out += ['', f"### {phase or 'No phase'}", '']
        deps = f" (after {', '.join(t['depends_on'])})" if t['depends_on'] else ''
        out.append(f"- [{'x' if t['done'] else ' '}] {tid} {t['title']}{deps}" + (f" [{t['lane']}]" if t['lane'] else ''))
    out += ['', '## Decisions', '']
    for label, key in (('Pending', 'pending'), ('Made', 'made')):
        for d in report['decisions'][key]:
            out.append(f"- {label} {d['id']}: {d['question']}" + (f" -> {', '.join(d['selected']) if isinstance(d['selected'], list) else d['selected']} ({d['decided_by']})"
                                                                 if d.get('selected') else ''))
    if not (report['decisions']['pending'] or report['decisions']['made']):
        out.append('None.')
    out += ['', '## Blockers', '']
    out += [f"- {b['id']} on {b['target']} by {b['by'].get('type')} {b['by'].get('ref')}" for b in report['blockers']] or ['None.']
    out += ['', '## Recent events', '']
    out += [f"- {e['at']} {e['kind']}: {e['text']}" for e in report['events']] or ['None.']
    return '\n'.join(out) + '\n'
