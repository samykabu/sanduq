#!/usr/bin/env python3
"""Generate a 3-5 KB worker brief for one task (B13, retrospective F10/F11/T0/T1/T7/S6).

Cuts a worker's orientation reading (retrospective T1: ~44K tokens of spec/plan/
tasks/contracts read by every worker) down to the few thousand it actually
needs: the task's own line, the verbatim requirement lines it implements, a
matching contract excerpt, its owned paths and the execution protocol's fixed
rules -- turn budget (T0), the F1/F2 spawn/blocking-wait rules, the F3
report-on-state-change rule, the T8 read-summary-first rule, forbidden
commands (S6, the same constants `delegate_dispatch.py` uses for its own
delegated briefs) and the structured result template (T7). The protocol text
is never copied by hand into this script: it is read out of
`skills/workflow/references/execution-assign.md` and `execution-report.md` at
brief-generation time, so a rule change there is never silently missed here.

Review round 1, finding 10: `--class` no longer accepts `qa_collect` -- that
route is light-tier eligible only when the task line itself carries a
`[Collect]` marker (or an explicit per-task override), never by an ad hoc CLI
flag (standing rule 5); the brief's work type still comes out `qa_collect`
automatically when `delegation.task_type` detects that marker. The brief is
targeted at 3-5 KB: when the full brief (with its contract excerpt) is over
budget, the excerpt is dropped first; if it is still over, the result is
returned with `oversized: true` rather than silently truncating requirement
lines a worker needs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delegate_dispatch as dd
from delegation import task_lines, task_type
from task_issues import parse_tasks
from workflow import WorkflowError, require

REFERENCES = Path(__file__).resolve().parents[1] / 'skills/workflow/references'
REQUIREMENT_ID = re.compile(r'\b[A-Z]{2,10}-\d{2,4}\b')
SPEC_ARTIFACTS = ('spec.md', 'plan.md', 'data-model.md', 'research.md')
PATH_TOKEN = re.compile(r'`([\w./-]+\.[A-Za-z0-9]{1,5})`')
# CLI-selectable classes; qa_collect is never one of them (finding 10).
CLI_WORK_TYPES = ('implementation', 'qa_author', 'documentation', 'review')
MIN_BYTES, MAX_BYTES = 3 * 1024, 5 * 1024


def read_text(path):
    return path.read_text(encoding='utf-8') if path.is_file() else ''


def task_context(root, feature, task_id):
    """The task's exact line, its description and its classified work type."""
    directory = root / feature
    tasks_text = read_text(directory / 'tasks.md')
    require(tasks_text, 'TASKS_MISSING: ' + feature)
    lines = task_lines(tasks_text)
    require(task_id in lines, 'TASK_NOT_FOUND: ' + task_id)
    descriptions = parse_tasks(tasks_text)
    description = descriptions[task_id]['description']
    return {'line': lines[task_id], 'description': description, 'work_type': task_type(description)}


def requirement_lines(root, feature, description, extra_ids=()):
    """Verbatim lines from spec/plan/data-model/research naming an id the task references."""
    ids = set(REQUIREMENT_ID.findall(description)) | set(extra_ids)
    found = []
    if not ids:
        return found
    for name in SPEC_ARTIFACTS:
        text = read_text(root / feature / name)
        for line in text.splitlines():
            if any(identifier in line for identifier in ids):
                found.append((name, line.strip()))
    return found


def contract_excerpt(root, feature, description, max_bytes=1200):
    """The best-matching contract file's leading bytes, or None when nothing matches."""
    directory = root / feature / 'contracts'
    if not directory.is_dir():
        return None
    words = set(re.findall(r'[A-Za-z][A-Za-z0-9_]{2,}', description))
    best = None
    for path in sorted(directory.rglob('*')):
        if not path.is_file():
            continue
        stem_words = set(re.findall(r'[A-Za-z][A-Za-z0-9_]{2,}', path.stem))
        if stem_words & words:
            best = path
            break
    if best is None:
        return None
    text = read_text(best)
    return {'path': str(best.relative_to(root).as_posix()), 'excerpt': text[:max_bytes]}


def owned_paths(description):
    return sorted(set(PATH_TOKEN.findall(description)))


def turn_budget_row(work_type):
    """The exact turn-budget table row for `work_type`, read from execution-assign.md."""
    text = read_text(REFERENCES / 'execution-assign.md')
    for line in text.splitlines():
        if line.startswith('| ' + work_type + ' |'):
            return line.strip()
    return None


def forbidden_commands_text(work_type):
    """The S6 rule, reusing `delegate_dispatch`'s own constants (finding 10) rather than
    scraping execution-assign.md's prose paragraph -- one source of truth for both the
    delegated brief `delegate_dispatch.task_brief` writes and this one."""
    text = dd.NO_DISPATCHER_COMMANDS
    return text + dd.QA_COLLECT_ADDENDUM if work_type == 'qa_collect' else text


def section_body(text, heading):
    """Everything after `## <heading>` up to the next `## ` heading, or None."""
    match = re.search(r'^## ' + re.escape(heading) + r'\s*\n\n(.*?)(?=\n## |\Z)', text, re.M | re.S)
    return match.group(1).strip() if match else None


def section_paragraph(text, heading, index):
    """The `index`-th paragraph (0-based, split on a blank line) of that section's body."""
    body = section_body(text, heading)
    if body is None:
        return None
    paragraphs = [p.strip() for p in body.split('\n\n')]
    return paragraphs[index] if index < len(paragraphs) else None


def spawn_and_wait_rules():
    """F1 (route results straight to the spawner, blocking not backgrounded) and F2 (never end
    a turn owning running background work), the first two paragraphs of their shared section."""
    text = read_text(REFERENCES / 'execution-assign.md')
    heading = 'Spawn pattern, blocking waits and turn budgets (F1, F2, T0)'
    return section_paragraph(text, heading, 0), section_paragraph(text, heading, 1)


def report_on_state_change_rule():
    """F3: no message beyond the minimum unless something actually changed."""
    text = read_text(REFERENCES / 'execution-report.md')
    return section_body(text, 'Report only on state change (F3)')


def read_summary_first_rule():
    """T8: read a verification summary before opening any raw reporter output."""
    text = read_text(REFERENCES / 'execution-report.md')
    return section_body(text, 'Read verification summaries before raw output (T8)')


def t7_template():
    """The exact ten-line structured-result fence from execution-report.md."""
    text = read_text(REFERENCES / 'execution-report.md')
    match = re.search(r'## Structured worker results \(T7\)\n\n.*?```text\n(.*?)```', text, re.S)
    return match.group(1).strip() if match else None


def render_brief(feature, task_id, context, requirements, contract, owned, budget_row, forbidden, spawn_rules,
                 f3_rule, t8_rule, template):
    lines = [f'# Worker brief: {task_id}', '', f'Feature: {feature}', f'Task line: {context["line"]}',
              f'Work type: {context["work_type"]}', '']
    lines.append('## Owned paths')
    lines += ([f'- `{path}`' for path in owned] or ['- (none extracted; confirm with the orchestration agent)'])
    lines.append('')
    lines.append('## Verbatim requirements')
    if requirements:
        lines += [f'- ({source}) {line}' for source, line in requirements]
    else:
        lines.append('- No requirement id referenced in the task line; read only what the orchestrator scoped.')
    lines.append('')
    if contract:
        lines += ['## Contract excerpt', f'From `{contract["path"]}`:', '```', contract['excerpt'], '```', '']
    lines.append('## Turn budget (T0)')
    lines.append(budget_row or f'No turn-budget row found for `{context["work_type"]}`; use the implementation default.')
    lines.append('')
    lines.append('## Spawn and wait rules (F1, F2)')
    f1, f2 = spawn_rules
    lines.append(f1 or 'Route results straight to whoever spawned you; never through the dispatcher for relay.')
    lines.append(f2 or 'Never end your turn while you still own running background work; block and report once.')
    lines.append('')
    lines.append('## Report only on state change (F3)')
    lines.append(f3_rule or 'Report a state change only (task accepted, commit pushed, blocker, decision needed).')
    lines.append('')
    lines.append('## Read summaries before raw output (T8)')
    lines.append(t8_rule or 'Read a verification summary first; open raw reporter output only for a failed lane.')
    lines.append('')
    lines.append('## Forbidden commands (S6)')
    lines.append(forbidden)
    lines.append('')
    lines.append('## Consumers checklist')
    lines.append('Before returning: e2e/integration specs, the lane registry, QA capture specs, manual/'
                 'User-Manual pages, contract docs (via pending-artifact-updates.md), PR image pins.')
    lines.append('')
    lines.append('## Result template (T7)')
    lines += ['```text', template or 'Task / Status / Files touched / Tests / Evidence / Diff / '
                                    'Consumers checked / Tokens / Blockers / Next', '```']
    return '\n'.join(lines) + '\n'


def build(root, feature, task_id, work_type=None):
    root = root.resolve()
    context = task_context(root, feature, task_id)
    if work_type:
        context['work_type'] = work_type
    requirements = requirement_lines(root, feature, context['description'])
    contract = contract_excerpt(root, feature, context['description'])
    owned = owned_paths(context['description'])
    budget_row = turn_budget_row(context['work_type'])
    forbidden = forbidden_commands_text(context['work_type'])
    spawn_rules = spawn_and_wait_rules()
    f3_rule = report_on_state_change_rule()
    t8_rule = read_summary_first_rule()
    template = t7_template()
    args = (feature, task_id, context, requirements, contract, owned, budget_row, forbidden, spawn_rules,
            f3_rule, t8_rule, template)
    brief = render_brief(*args)
    # Finding 10: enforce the 3-5 KB target. Drop the contract excerpt first
    # (the one section that is a nice-to-have, never a fixed protocol rule);
    # if it is still over budget, warn rather than silently cut a
    # requirement line or a protocol rule a worker actually needs.
    if len(brief.encode('utf-8')) > MAX_BYTES and contract is not None:
        brief = render_brief(feature, task_id, context, requirements, None, owned, budget_row, forbidden,
                             spawn_rules, f3_rule, t8_rule, template)
    oversized = len(brief.encode('utf-8')) > MAX_BYTES
    return brief, context, oversized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--feature', required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--class', dest='work_type', choices=CLI_WORK_TYPES,
                        help='qa_collect is never a CLI choice (finding 10): it is only ever '
                             'detected automatically from a [Collect] task marker.')
    parser.add_argument('--output')
    args = parser.parse_args()
    try:
        brief, context, oversized = build(args.root, args.feature, args.task, args.work_type)
    except WorkflowError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1
    output = Path(args.output) if args.output else args.root / args.feature / 'workflow/briefs' / (args.task + '.md')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(brief, encoding='utf-8')
    # json.dumps, not manual string formatting (finding 10): a Windows path
    # like the default --output has backslashes, which break hand-built JSON.
    print(json.dumps({'ok': True, 'path': str(output), 'bytes': len(brief.encode('utf-8')),
                      'work_type': context['work_type'], 'oversized': oversized}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
