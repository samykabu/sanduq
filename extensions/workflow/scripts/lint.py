#!/usr/bin/env python3
"""Deterministic Analyze (`workflow:lint`): requirement coverage, task ids, dependencies,
headlines, open clarifications, contract references and artifact byte budgets."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import workflow

TIERS = ('lite', 'standard', 'full')
ENFORCE = ('lite-standard', 'all', 'warn')
TASK = re.compile(r'^\s*- \[([ xX])\]\s+(T\d{3,})\b(.*)$')
REQUIREMENT = re.compile(r'\b(?:FR-\d+[a-z]?|SC-\d+)\b')
# Any requirement reference a task may carry: an FR/SC id or a user-story label.
REFERENCE = re.compile(r'\b(?:FR-\d+[a-z]?|SC-\d+|US\d+)\b')
DEPENDS = re.compile(r'(?i)\b(?:depends on|after|dependencies:)\s*((?:T\d{3,}(?:\s*(?:,|and|&)\s*)?)+)')
HEADLINE_LIMIT = 200  # GitHub caps titles at 256 and the adapter prefixes `T001: `
BUDGET_FILES = {'spec_kb': 'spec.md', 'plan_kb': 'plan.md', 'research_kb': 'research.md'}
# Semantic flags lint cannot judge, so a model Analyze must: an uncovered FR- id
# (an uncovered SC- id is a plain warning) and contradictory status markers.
SEMANTIC = {'REQUIREMENT_UNCOVERED:FR', 'TASK_STATUS_CONTRADICTORY'}
# `## Phase ...` headings whose tasks legitimately cite no requirement.
UNREFERENCED_PHASES = ('setup', 'foundational', 'polish', 'cross-cutting')


def parse_tasks(text):
    """[(id, done, headline, detail_lines, phase)] in file order; detail lines are the indented
    non-blank lines under the task up to the next task or unindented line; phase is the
    enclosing `## ` heading text ('' when none)."""
    tasks, current, phase = [], None, ''
    for line in text.splitlines():
        heading = re.match(r'^(#{1,2})(?!#)\s+(.*?)\s*$', line)
        if heading:
            phase = heading[2] if heading[1] == '##' else ''
        match = TASK.match(line)
        if match:
            current = (match[2], match[1].lower() == 'x', line.split(']', 1)[1].strip(), [], phase)
            tasks.append(current)
        elif current and line.strip():
            if line[:1] in (' ', '\t'):
                current[3].append(line.strip())
            else:
                current = None
    return tasks


def cycle(graph):
    """The first dependency cycle found as a list of task ids, or None."""
    state, stack = {}, []
    def visit(node):
        state[node] = 'open'; stack.append(node)
        for parent in graph.get(node, ()):
            if state.get(parent) == 'open':
                return stack[stack.index(parent):] + [parent]
            if parent not in state and (found := visit(parent)):
                return found
        state[node] = 'done'; stack.pop()
        return None
    for node in graph:
        if node not in state and (found := visit(node)):
            return found
    return None


def run(root, feature, policy, tier):
    workflow.require(tier in TIERS, 'LINT_TIER_INVALID: ' + str(tier))
    root = Path(root).resolve()
    directory = workflow.inside(root, feature)
    label = directory.relative_to(root).as_posix()
    findings, flags = [], set()
    def add(code, severity, name, message, flag=None):
        findings.append({'code': code, 'severity': severity, 'path': label + '/' + name, 'message': message})
        flags.add(flag or code)
    texts = {}
    for name in ('spec.md', 'plan.md', 'tasks.md'):
        path = directory / name
        if path.is_file():
            texts[name] = path.read_text(encoding='utf-8-sig')
        else:
            texts[name] = ''
            add('ARTIFACT_MISSING', 'error', name, name + ' is missing')
    spec, plan, tasks_text = texts['spec.md'], texts['plan.md'], texts['tasks.md']
    tasks = parse_tasks(tasks_text)

    # shortcut: ranges such as `FR-001..FR-003` count only their endpoints; expand them if specs use ranges.
    covered = set(REQUIREMENT.findall(tasks_text))
    for requirement in dict.fromkeys(REQUIREMENT.findall(spec)):
        if requirement not in covered:
            add('REQUIREMENT_UNCOVERED', 'warning', 'tasks.md', requirement + ' from spec.md is not referenced by any task',
                'REQUIREMENT_UNCOVERED:' + requirement[:2])

    seen, numbers = {}, []
    for task, done, headline, details, phase in tasks:
        if task in seen:
            add('TASK_ID_DUPLICATE', 'error', 'tasks.md', task + ' appears more than once')
            if seen[task] != done:
                add('TASK_STATUS_CONTRADICTORY', 'warning', 'tasks.md', task + ' is both checked and unchecked')
        else:
            seen[task] = done
            numbers.append(int(task[1:]))
        if len(headline) > HEADLINE_LIMIT:
            add('TASK_HEADLINE_TOO_LONG', 'error', 'tasks.md',
                f'{task} headline is {len(headline)} characters; keep it at most {HEADLINE_LIMIT} and move detail below it')
        exempt = phase.casefold().startswith('phase') and any(word in phase.casefold() for word in UNREFERENCED_PHASES)
        if not exempt and not REFERENCE.search(' '.join([headline, *details])):
            add('TASK_WITHOUT_REQUIREMENT', 'warning', 'tasks.md', task + ' references no FR-, SC- or US id')
    if not tasks and (directory / 'tasks.md').is_file():
        add('NO_TASKS', 'error', 'tasks.md', 'tasks.md has no `- [ ] T001 ...` task lines')
    for number in sorted(set(range(1, max(numbers, default=0) + 1)) - set(numbers)):
        add('TASK_ID_GAP', 'warning', 'tasks.md', f'T{number:03d} is missing from the sequence starting at T001')
    if numbers != sorted(numbers):
        add('TASK_ID_ORDER', 'warning', 'tasks.md', 'task ids are not in ascending order')

    graph = {}
    for task, _, headline, details, _ in tasks:
        for line in [headline, *details]:
            for match in DEPENDS.finditer(line):
                graph.setdefault(task, []).extend(re.findall(r'T\d{3,}', match[1]))
    mapping_path = directory / 'workflow/task-dependencies.json'
    if mapping_path.is_file():
        try:
            mapping = json.loads(mapping_path.read_text(encoding='utf-8-sig'))
            workflow.require(isinstance(mapping, dict) and all(isinstance(v, list) for v in mapping.values()), 'shape')
        except (ValueError, workflow.WorkflowError):
            findings.append({'code': 'TASK_DEPENDENCIES_INVALID', 'severity': 'error',
                             'path': label + '/workflow/task-dependencies.json',
                             'message': 'expected a JSON object mapping task ids to lists of task ids'})
            mapping = {}
        for task, parents in mapping.items():
            graph.setdefault(task, []).extend(parents)
    for task, parents in graph.items():
        for parent in [task, *parents]:
            if parent not in seen:
                add('TASK_DEPENDENCY_UNKNOWN', 'error', 'tasks.md', f'{task} depends on unknown task {parent}')
    loop = cycle(graph)
    if loop:
        add('TASK_DEPENDENCY_CYCLE', 'error', 'tasks.md', 'dependency cycle: ' + ' -> '.join(loop))

    open_questions = spec.count('[NEEDS CLARIFICATION')
    if open_questions:
        add('SPEC_NEEDS_CLARIFICATION', 'error', 'spec.md', f'{open_questions} [NEEDS CLARIFICATION] marker(s) remain')

    contracts = directory / 'contracts'
    if contracts.is_dir():
        for path in sorted(p for p in contracts.rglob('*') if p.is_file()):
            relative = path.relative_to(directory).as_posix()
            if not any(relative in text or path.name in text for text in (plan, tasks_text)):
                add('CONTRACT_UNREFERENCED', 'warning', relative, relative + ' is referenced by neither plan.md nor tasks.md')

    artifacts = (policy or {}).get('artifacts') or {}
    limits = artifacts.get('budgets') or {}
    enforce = artifacts.get('enforce', 'lite-standard')
    workflow.require(enforce in ENFORCE, 'LINT_ENFORCE_INVALID: ' + str(enforce))
    severity = 'error' if enforce == 'all' or (enforce == 'lite-standard' and tier != 'full') else 'warning'
    budgets = {}
    for key, name in BUDGET_FILES.items():
        path = directory / name
        if key in limits and path.is_file():
            size, limit = path.stat().st_size, int(limits[key] * 1024)
            budgets[name] = {'bytes': size, 'limit_bytes': limit, 'over': size > limit}
            if size > limit:
                add('BUDGET_EXCEEDED', severity, name, f'{name} is {size} bytes; the {tier} budget is {limit} bytes')
    if 'tasks_detail_lines' in limits:
        for task, _, _, details, _ in tasks:
            if len(details) > limits['tasks_detail_lines']:
                add('BUDGET_TASK_DETAIL', severity, 'tasks.md',
                    f'{task} has {len(details)} detail lines; the budget is {limits["tasks_detail_lines"]}')

    return {'ok': not any(f['severity'] == 'error' for f in findings), 'findings': findings,
            'needs_model_analyze': bool(flags & SEMANTIC), 'budgets': budgets}


def record(root, feature, result, token):
    """Write the lint evidence and complete the claimed Analyze stage with it."""
    run = workflow.Run(root, feature)
    label = run.relative
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    evidence = f'{label}/evidence/lint-{stamp}.json'
    path = workflow.inside(run.root, evidence)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    receipt = {'stage': 'analyze', 'outcome': 'passed',
               'summary': f'workflow:lint passed with {len(result["findings"])} non-blocking finding(s)',
               'inputs': [label + '/spec.md', label + '/plan.md', label + '/tasks.md'],
               'evidence': [evidence], 'lint': {'ok': True, 'findings': len(result['findings'])}}
    return run.complete(token, receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--feature', required=True)
    parser.add_argument('--tier', choices=TIERS, help='Default: the tier frozen in the checkpoint, else full')
    parser.add_argument('--json', action='store_true', help='Print the full JSON result (default: one summary line)')
    parser.add_argument('--record', action='store_true', help='Complete the claimed analyze stage when ok and no model Analyze is needed')
    parser.add_argument('--token', help='The analyze claim token (required with --record)')
    args = parser.parse_args(argv)
    if args.record and not args.token:
        parser.error('--record requires --token')
    try:
        root = args.root.resolve()
        policy = workflow.load_policy(root)
        tier = args.tier
        if tier is None:
            checkpoint = workflow.read(workflow.inside(root, args.feature) / 'workflow/checkpoint.json', {}) or {}
            tier = (checkpoint.get('profile') or {}).get('tier') or 'full'
        result = run(root, args.feature, policy, tier)
        if args.record:
            if not result['ok'] or result['needs_model_analyze']:
                print(json.dumps({**result, 'recorded': False,
                                  'reason': 'lint errors remain' if not result['ok'] else 'needs_model_analyze'}, indent=2))
                return 1
            print(json.dumps(record(root, args.feature, result, args.token), indent=2))
            return 0
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            counts = {s: sum(f['severity'] == s for f in result['findings']) for s in ('error', 'warning', 'info')}
            print(('ok' if result['ok'] else 'error') + f' errors={counts["error"]} warnings={counts["warning"]}'
                  f' needs_model_analyze={int(result["needs_model_analyze"])}')
            for finding in result['findings']:
                print(f'{finding["severity"]} {finding["code"]} {finding["path"]}: {finding["message"]}')
        return 0 if result['ok'] else 1
    except (workflow.WorkflowError, ValueError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
