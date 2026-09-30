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
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow import Run, WorkflowError, default_actor, now, receipt_status, recovery_recipe, require, stages

ENTRY = re.compile(
    r'^## (?P<target>\S+)#(?P<anchor>.+?)\s*\n'
    r'(?:Source: (?P<source>.*?)\s*\n)?'
    r'Status: (?P<status>pending|applied|rejected)(?P<statusrest>[^\n]*)\n'
    r'```[a-zA-Z]*\n(?P<body>.*?)\n```',
    re.M | re.S)
DEFAULT_PENDING = 'workflow/pending-artifact-updates.md'


def parse_entries(text):
    return [match.groupdict() | {'span': match.span()} for match in ENTRY.finditer(text)]


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
    pending_path = root / (pending_path or (feature + '/' + DEFAULT_PENDING))
    text = read_text(pending_path)
    require(text.strip(), 'PENDING_FILE_EMPTY: ' + str(pending_path))
    entries = parse_entries(text)
    require(entries, 'PENDING_FILE_NO_ENTRIES: ' + str(pending_path))
    decided, touched = [], set()
    for entry in entries:
        if entry['status'] != 'pending':
            continue
        target = root / entry['target']
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
        except WorkflowError:
            # No checkpoint (or no policy) yet for this feature: nothing to
            # stale-check. Applying is still safe; there is simply no receipt
            # to warn about.
            result['stale'] = []
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
    except WorkflowError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, indent=2))
        return 1


if __name__ == '__main__':
    sys.exit(main())
