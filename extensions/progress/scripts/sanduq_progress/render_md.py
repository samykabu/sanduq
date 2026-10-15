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
