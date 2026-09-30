#!/usr/bin/env python3
"""Apply `workflow/pending-artifact-updates.md` to contracts/data-model/research (B13, F15).

Formalises the convention the retrospective found working ad hoc: a worker
appends a proposed wording change instead of editing a shared contract file
mid-execute (avoiding a Plan/Analyze receipt cascade for every append), and a
dispatcher step applies every still-`pending` entry once, at the end of
Execute or Review. This script only performs the mechanical half (locate the
named heading, replace its body, mark the entry applied or rejected); judging
whether the proposed wording still matches the shipped code is the calling
agent's job before it runs `--apply`, never this script's.

Entry format (the file this script reads and rewrites)::

    ## <repo-relative target path>#<exact heading text>
    Source: T012 (why)
    Status: pending
    ```markdown
    <the new body of that heading, verbatim>
    ```

`Status` becomes `applied` (with `Applied: <utc>` and `Actor:`) or `rejected`
(with `Reason:`) after `--apply`; an already-decided entry is left untouched.

Every target is confined to `<feature>/contracts/**`, `<feature>/data-model.md`
or `<feature>/research.md` (review round 1, finding 4): an absolute path,
`..`, or a symlink anywhere on the way that would resolve outside those
locations is rejected per-entry, never silently normalised or followed. The
pending file itself is contained the same way. `--apply` refuses outright
inside a delegated worker or orchestrator process
(`SANDUQ_DELEGATED_RUN`/`SANDUQ_DELEGATED_ROLE`, finding 3, matching
`Run.amend`'s own guard) and while a claim is active for the feature.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from delegate_dispatch import require_not_worker_context
from workflow import Run, WorkflowError, default_actor, inside, now, receipt_status, recovery_recipe, require, stages

ENTRY = re.compile(
    r'^## (?P<target>\S+)#(?P<anchor>.+?)\s*\n'
    r'(?:Source: (?P<source>.*?)\s*\n)?'
    r'Status: (?P<status>pending|applied|rejected)(?P<statusrest>[^\n]*)\n'
    r'```[a-zA-Z]*\n(?P<body>.*?)\n```',
    re.M | re.S)
DEFAULT_PENDING = 'workflow/pending-artifact-updates.md'


def parse_entries(text):
    return [match.groupdict() | {'span': match.span()} for match in ENTRY.finditer(text)]


def resolve_target(root, feature, relative):
    """The allowed absolute path for a pending entry's target, or raises.

    Only `<feature>/contracts/**`, `<feature>/data-model.md` and
    `<feature>/research.md` are writable targets. An absolute path is
    refused before any resolution; `inside()` then resolves the path (which
    follows every symlink on the way) and requires the *result* stay inside
    the repository, catching `..` and a symlink escape identically. The
    allow-list check below runs on that fully-resolved path too, so a
    symlink that stays inside the repo but points at, say, another
    feature's spec.md is still refused.
    """
    require(relative and not Path(relative).is_absolute(), 'PENDING_TARGET_ABSOLUTE_REFUSED: ' + str(relative))
    resolved = inside(root, relative)
    feature_dir = inside(root, feature)
    contracts_dir = (feature_dir / 'contracts').resolve()
    allowed_exact = {(feature_dir / 'data-model.md').resolve(), (feature_dir / 'research.md').resolve()}
    require(resolved.is_relative_to(contracts_dir) or resolved in allowed_exact,
            'PENDING_TARGET_NOT_ALLOWED: ' + str(relative))
    return resolved


def replace_section(text, anchor, new_body):
    """Replace the body of the heading whose text is exactly `anchor`.

    The body runs from just after the heading line to the next heading of the
    same or shallower level (or end of file). Returns (new_text, found).
    """
    lines = text.splitlines(keepends=True)
    start = end = None
    level = None
    for index, line in enumerate(lines):
        match = re.match(r'^(#{1,6})\s+(.*?)\s*$', line)
        if not match:
            continue
        if start is None and match.group(2).strip() == anchor.strip():
            start = index + 1
            level = len(match.group(1))
            continue
        if start is not None and len(match.group(1)) <= level:
            end = index
            break
    if start is None:
        return text, False
    end = len(lines) if end is None else end
    replacement = new_body.strip() + '\n\n'
    return ''.join(lines[:start]) + replacement + ''.join(lines[end:]), True


def stale_after(root, feature, policy, touched_paths):
    """Which currently-passed receipts a touched path stales, with the recovery recipe."""
    run = Run(root, feature)
    state = run.load()
    report = []
    for stage in stages(policy):
        receipt = state.get('receipts', {}).get(stage)
        if not receipt or receipt.get('outcome') != 'passed':
            continue
        if not (set(receipt.get('fingerprints', {})) & set(touched_paths)):
            continue
        status = receipt_status(root, feature, stage, receipt, policy)
        if not status['current']:
            report.append({'stage': stage, 'recovery': recovery_recipe(feature, stage, status, policy, receipt)})
    return report


def apply(root, feature, pending_path=None, apply_changes=False, actor=None):
    root = root.resolve()
    if apply_changes:
        require_not_worker_context(feature)
        try:
            active_state = Run(root, feature).load()
        except WorkflowError:
            active_state = None
        require(not (active_state and active_state.get('active')),
                'APPLY_PENDING_ACTIVE_CLAIM_MUST_BE_RESOLVED: resolve the active claim before applying')
    pending_relative = pending_path or (feature + '/' + DEFAULT_PENDING)
    pending_path = inside(root, pending_relative)
    text = read_text(pending_path)
    require(text.strip(), 'PENDING_FILE_EMPTY: ' + str(pending_path))
    entries = parse_entries(text)
    require(entries, 'PENDING_FILE_NO_ENTRIES: ' + str(pending_path))
    decided, touched = [], set()
    for entry in entries:
        if entry['status'] != 'pending':
            continue
        try:
            target = resolve_target(root, feature, entry['target'])
        except WorkflowError as exc:
            decided.append({**entry, 'outcome': 'rejected', 'reason': str(exc)})
            continue
        target_text = read_text(target)
        if not target_text:
            decided.append({**entry, 'outcome': 'rejected', 'reason': 'TARGET_FILE_MISSING: ' + entry['target']})
            continue
        replaced, found = replace_section(target_text, entry['anchor'], entry['body'])
        if not found:
            decided.append({**entry, 'outcome': 'rejected', 'reason': 'ANCHOR_NOT_FOUND: ' + entry['anchor']})
            continue
        decided.append({**entry, 'outcome': 'applied', 'target': entry['target']})
        touched.add(entry['target'])
        if apply_changes:
            write_text(target, replaced)
    if apply_changes:
        write_text(pending_path, rewrite_pending(text, entries, decided, root, actor))
    result = {'ok': True, 'entries': len(entries),
              'applied': [item['target'] + '#' + item['anchor'] for item in decided if item['outcome'] == 'applied'],
              'rejected': [{'entry': item['target'] + '#' + item['anchor'], 'reason': item.get('reason')}
                          for item in decided if item['outcome'] == 'rejected']}
    if apply_changes and touched:
        try:
            run = Run(root, feature)
            result['stale'] = stale_after(root, feature, run.policy, touched)
        except WorkflowError as exc:
            # Never silently claim "nothing stale" when the check itself
            # could not run (finding 5): null is distinct from an empty
            # list, and the error is reported so the caller can investigate
            # rather than assume the touched paths are receipt-free.
            result['stale'] = None
            result['stale_error'] = str(exc)
    return result


def rewrite_pending(text, entries, decided, root, actor):
    decisions = {(item['target'], item['anchor']): item for item in decided}
    resolved_actor = actor or default_actor(root)
    out = []
    cursor = 0
    for entry in entries:
        start, end = entry['span']
        out.append(text[cursor:start])
        key = (entry['target'], entry['anchor'])
        if key in decisions and entry['status'] == 'pending':
            item = decisions[key]
            block = text[start:end]
            if item['outcome'] == 'applied':
                block = re.sub(r'Status: pending[^\n]*', 'Status: applied  Applied: ' + now() +
                               '  Actor: ' + resolved_actor, block)
            else:
                block = re.sub(r'Status: pending[^\n]*', 'Status: rejected  Reason: ' + item['reason'], block)
            out.append(block)
        else:
            out.append(text[start:end])
        cursor = end
    out.append(text[cursor:])
    return ''.join(out)


def read_text(path):
    return path.read_text(encoding='utf-8') if path.is_file() else ''


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--feature', required=True)
    parser.add_argument('--pending-file')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--actor')
    args = parser.parse_args()
    try:
        result = apply(args.root, args.feature, args.pending_file, args.apply, args.actor)
        print(json.dumps(result, indent=2))
        return 0
    except (WorkflowError, ValueError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, indent=2))
        return 1


if __name__ == '__main__':
    sys.exit(main())
