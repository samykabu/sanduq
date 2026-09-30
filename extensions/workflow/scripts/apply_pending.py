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
import os
import tempfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from delegate_dispatch import require_not_worker_context
from delegation import is_link
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
    `<feature>/research.md` are writable targets, judged on the *lexical*
    (unresolved) path: resolving both sides is fooled by a symlinked
    `contracts` directory or a symlinked `data-model.md`, whose resolved
    target would equal itself. So an absolute path, a `..` segment, a target
    outside the allow-list and any symlink (or junction) on the way from the
    repository root to the target are all refused before anything is read or
    written; `inside()` then still requires the resolved path to stay in the
    repository.
    """
    require(relative and not Path(relative).is_absolute(), 'PENDING_TARGET_ABSOLUTE_REFUSED: ' + str(relative))
    parts = PurePosixPath(str(relative).replace('\\', '/')).parts
    require('..' not in parts, 'PENDING_TARGET_NOT_ALLOWED: parent traversal: ' + str(relative))
    lexical = PurePosixPath(*parts) if parts else PurePosixPath('.')
    base = PurePosixPath(PurePosixPath(str(feature).replace('\\', '/')).as_posix())
    allowed = (lexical == base / 'data-model.md' or lexical == base / 'research.md'
               or (len(lexical.parts) > len(base.parts) + 1 and lexical.parts[:len(base.parts) + 1] ==
                   (*base.parts, 'contracts')))
    require(allowed, 'PENDING_TARGET_NOT_ALLOWED: ' + str(relative))
    node = Path(root)
    for part in lexical.parts:
        node = node / part
        # `is_link` is the repo's one symlink-or-junction test; its
        # `is_junction` falls back to the reparse tag on Windows Python < 3.12.
        require(not is_link(node), 'PENDING_TARGET_SYMLINK_REFUSED: ' + str(relative))
    return inside(root, relative)


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
    # Replacements accumulate per target so several headings of one file all
    # land (each entry re-reading the original and writing at once would
    # keep only the last one); each file is then written once, atomically,
    # and an entry is marked applied only after its file's write succeeded.
    working, by_target = {}, {}
    for entry in entries:
        if entry['status'] != 'pending':
            continue
        try:
            target = resolve_target(root, feature, entry['target'])
        except WorkflowError as exc:
            decided.append({**entry, 'outcome': 'rejected', 'reason': str(exc)})
            continue
        if target not in working:
            working[target] = read_text(target)
        if not working[target]:
            decided.append({**entry, 'outcome': 'rejected', 'reason': 'TARGET_FILE_MISSING: ' + entry['target']})
            continue
        replaced, found = replace_section(working[target], entry['anchor'], entry['body'])
        if not found:
            decided.append({**entry, 'outcome': 'rejected', 'reason': 'ANCHOR_NOT_FOUND: ' + entry['anchor']})
            continue
        working[target] = replaced
        item = {**entry, 'outcome': 'applied', 'target': entry['target']}
        decided.append(item)
        by_target.setdefault(target, []).append(item)
    if apply_changes:
        for target, items in by_target.items():
            relative = items[0]['target']
            try:
                # The whole chain is re-validated immediately before the temp
                # file is created and again immediately before it replaces
                # the target (see write_text).
                write_text(target, working[target], expected=target,
                           revalidate=lambda relative=relative: resolve_target(root, feature, relative))
            except (OSError, WorkflowError) as exc:
                for item in items:
                    item['outcome'] = 'rejected'
                    item['reason'] = 'WRITE_FAILED: ' + str(exc)
    touched = {item['target'] for item in decided if item['outcome'] == 'applied'}
    if apply_changes:
        write_text(pending_path, rewrite_pending(text, entries, decided, root, actor), expected=pending_path,
                   revalidate=lambda: inside(root, pending_relative))
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
                # A callable replacement is literal; a string would be parsed for
                # backslash escapes and a Windows path in the reason would raise.
                block = re.sub(r'Status: pending[^\n]*', lambda _m: 'Status: rejected  Reason: ' + item['reason'],
                               block)
            out.append(block)
        else:
            out.append(text[start:end])
        cursor = end
    out.append(text[cursor:])
    return ''.join(out)


def read_text(path):
    return path.read_text(encoding='utf-8') if path.is_file() else ''


def _same_file(a, b):
    # `b` is the real path captured at validation time; it is compared as the
    # string it was, never re-resolved (re-resolving would follow a swapped link too).
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(str(b))


def write_text(path, text, expected=None, revalidate=None):
    """Write atomically: a temp file in the same directory, then `os.replace`.

    `revalidate` (raises if the path chain is no longer acceptable) runs
    immediately before the temp file is created and again immediately before
    it replaces the target, so a parent swapped for a symlink or junction
    after the first validation is refused. `expected` is the real path the
    caller validated; after the replace the written file's real path must
    still be it, else the previous content is put back and an error raised.
    This narrows the race, it does not close it: a swap between the last
    `revalidate` and the replace itself (a few instructions) is detected
    afterwards only, and a swap between the backup and the replace cannot be
    undone (see the reference doc's "Residual race").
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if revalidate:
        revalidate()
    descriptor, temp = tempfile.mkstemp(dir=str(path.parent), prefix='.pending-', suffix='.tmp')
    backup = None
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as handle:
            handle.write(text)
        if revalidate:
            revalidate()
        if os.path.exists(path):
            backup = str(path) + '.pending-backup'
            os.replace(path, backup)
        os.replace(temp, path)
        if expected is not None and not _same_file(path, expected):
            landed = os.path.realpath(path)
            if backup:
                os.replace(backup, path)  # put the landed file's own content back
                backup = None
            raise WorkflowError('PENDING_WRITE_LANDED_ELSEWHERE: wrote through a swapped path to ' + landed +
                                '; the previous content was restored')
        if backup:
            os.unlink(backup)
            backup = None
    except BaseException:
        if backup and os.path.exists(backup) and not os.path.exists(path):
            os.replace(backup, path)
        for leftover in (temp,):
            try:
                os.unlink(leftover)
            except OSError:
                pass
        raise


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
