#!/usr/bin/env python3
"""Generate a 3-5 KB worker brief for one task (B13, retrospective F10/F11/T0/T1/T7/S6).

Cuts a worker's orientation reading (retrospective T1: ~44K tokens of spec/plan/
tasks/contracts read by every worker) down to the few thousand it actually
needs: the task's own line, the verbatim requirement lines it implements, a
matching contract excerpt, its owned paths and the execution protocol's fixed
rules -- turn budget (T0), forbidden commands (S6) and the structured result
template (T7). The protocol text is never copied by hand into this script: it
is read out of `skills/workflow/references/execution-assign.md` and
`execution-report.md` at brief-generation time, so a rule change there is
never silently missed here.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from delegation import task_lines, task_type
from task_issues import parse_tasks
from workflow import WorkflowError, require

REFERENCES = Path(__file__).resolve().parents[1] / 'skills/workflow/references'
REQUIREMENT_ID = re.compile(r'\b[A-Z]{2,10}-\d{2,4}\b')
SPEC_ARTIFACTS = ('spec.md', 'plan.md', 'data-model.md', 'research.md')
PATH_TOKEN = re.compile(r'`([\w./-]+\.[A-Za-z0-9]{1,5})`')


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


def forbidden_commands_paragraph():
    """The S6 paragraph (git stash / git add -A / delegate_dispatch ledger commands), verbatim."""
    text = read_text(REFERENCES / 'execution-assign.md')
    for paragraph in text.split('\n\n'):
        if '`git stash`' in paragraph:
            return paragraph.strip()
    return None


def t7_template():
    """The exact ten-line structured-result fence from execution-report.md."""
    text = read_text(REFERENCES / 'execution-report.md')
    match = re.search(r'## Structured worker results \(T7\)\n\n.*?```text\n(.*?)```', text, re.S)
    return match.group(1).strip() if match else None


def render_brief(feature, task_id, context, requirements, contract, owned, budget_row, forbidden, template):
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
    lines.append('## Forbidden commands (S6)')
    lines.append(forbidden or 'Never `git stash`, `git add -A`/`git add .`, or the ledger-trust '
                              'delegate_dispatch.py commands (accept/reassign/trust-reset/adopt).')
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
    forbidden = forbidden_commands_paragraph()
    template = t7_template()
    brief = render_brief(feature, task_id, context, requirements, contract, owned, budget_row, forbidden, template)
    return brief, context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--feature', required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--class', dest='work_type', choices=('implementation', 'qa_author', 'qa_collect',
                        'documentation', 'review'))
    parser.add_argument('--output')
    args = parser.parse_args()
    try:
        brief, context = build(args.root, args.feature, args.task, args.work_type)
    except WorkflowError as exc:
        print('{"ok": false, "error": "' + str(exc) + '"}')
        return 1
    output = Path(args.output) if args.output else args.root / args.feature / 'workflow/briefs' / (args.task + '.md')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(brief, encoding='utf-8')
    print(f'{{"ok": true, "path": "{output}", "bytes": {len(brief.encode("utf-8"))}, '
          f'"work_type": "{context["work_type"]}"}}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
