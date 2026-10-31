# SPDX-License-Identifier: MIT
"""Shared package-time source for QA/manual freshness (never hashes its own state)."""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
from pathlib import Path
import sys

# Installed packages carry this module beside the state script; canonical tests
# load the same implementation from Workflow without copying consumer files.
if not (Path(__file__).parent / 'sanduq_hash.py').exists():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'workflow/scripts'))
from sanduq_hash import portable_files

EXCLUDED = {'.git', 'node_modules', 'bin', 'obj', 'dist', 'build', 'coverage', '__pycache__'}


def git(root, *args):
    result = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, encoding='utf-8')
    if result.returncode: raise ValueError('Git freshness input unavailable: ' + result.stderr.strip())
    return result.stdout


def relative(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()): raise ValueError('Path outside project: ' + str(value))
    return path.relative_to(root.resolve()).as_posix()


# The User Manual's task block (speckit.user-manual.analyze), with the blank lines before it. Its
# tasks do not change QA coverage, so the analyze kind ignores it.
MANUAL_TASKS = re.compile(rb'(?ms)(?:^[ \t]*\r?\n)*^[ \t]*<!-- user-manual-tasks:start -->.*?'
                          rb'<!-- user-manual-tasks:end -->[ \t]*(?:\r?\n|\Z)')


def task_bytes(content, kind=None):
    """tasks.md as hashed: checkbox state is bookkeeping, and analyze also drops the manual block."""
    content = re.sub(rb'(?m)^(\s*- )\[[ xX]\]', rb'\1[ ]', content)
    return MANUAL_TASKS.sub(b'', content) if kind == 'analyze' else content


def fingerprints(root, paths, kind=None):
    result = {}
    paths = [relative(root, value) for value in sorted(set(paths))]
    # Checkout-independent bytes: see sanduq_hash.portable_files.
    for key, content in portable_files(root, paths).items():
        if content is not None and Path(key).name == 'tasks.md':
            content = task_bytes(content, kind)
        result[key] = hashlib.sha256(content).hexdigest() if content is not None else None
    return result


def checkpoint_target_branch(feature):
    """The feature's bound target branch recorded by `workflow.py start`, or
    None when there is no checkpoint or no branch was captured. An explicit
    --base-ref always wins over this; callers fall back to today's default
    (the origin HEAD symbolic ref via base_ref()) when this is None.
    """
    checkpoint = Path(feature) / 'workflow/checkpoint.json'
    if not checkpoint.is_file():
        return None
    try:
        state = json.loads(checkpoint.read_text(encoding='utf-8-sig'))
    except (ValueError, OSError):
        return None
    branch = state.get('target_branch')
    return branch if isinstance(branch, str) and branch else None


def base_ref(root, explicit=None):
    if explicit: return git(root, 'merge-base', 'HEAD', explicit).strip()
    try:
        ref = git(root, 'symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD').strip()
    except ValueError:
        raise ValueError('Default remote branch unknown; supply --base-ref explicitly.')
    return git(root, 'merge-base', 'HEAD', ref).strip()


def inputs(root, feature, kind, base=None, outputs=()):
    feature = relative(root, feature)
    outputs = {relative(root, p) for p in outputs}
    paths = {relative(root, p) for p in (root / feature).rglob('*') if p.is_file()}
    if kind != 'analyze':
        comparison = base_ref(root, base)
        # name-only includes deleted files; diff against the working tree includes
        # staged and unstaged edits. No HEAD^ fallback can hide earlier commits.
        paths.update(filter(None, git(root, 'diff', '--name-only', '-z', comparison).split('\0')))
        # A sibling feature's untracked notes are local debris, not this feature's input (issue #113);
        # its committed files still arrive through the diff, and other untracked sources stay inputs.
        siblings = Path(feature).parent.as_posix() + '/'
        paths.update(p for p in git(root, 'ls-files', '--others', '--exclude-standard', '-z').split('\0')
                     if p and not (p.startswith(siblings) and '/' in p[len(siblings):]
                                   and not p.startswith(feature + '/')))
    else:
        comparison = None
    def included(value):
        parts = Path(value).parts
        # Reports are metadata, including other features reached by the document
        # diff. Product directories such as src/progress remain semantic inputs.
        report = len(parts) > 3 and parts[0] == 'specs' and parts[2] == 'progress'
        return not (report or any(p in EXCLUDED for p in parts) or value.startswith((feature + '/workflow/',
            feature + '/evidence/', feature + '/progress/', '.specify/progress/',
            '.specify/workflow/', '.specify/scope/', '.specify/extensions/',
            'graphify-out/', 'User-Manual/', 'docs/' + Path(feature).name + '/')) or Path(value).name in
            {'.env', 'workflow.yml', 'feature.json', 'project-sync-state.json'})
    result = fingerprints(root, [p for p in paths if included(p) and p not in outputs], kind)
    # The feature's own tasks.md is hashed from its working-tree text (kept for recorded hashes).
    task = feature + '/tasks.md'
    if task in result and (root / task).is_file():
        content = (root / task).read_bytes().replace(b'\r\n', b'\n')
        result[task] = hashlib.sha256(task_bytes(content, kind)).hexdigest()
    return {'base_commit': comparison, 'files': result}


def record_or_status(root, feature, kind, state_path, action, outputs, base=None):
    feature = relative(root, feature)
    state_path = root / relative(root, state_path)
    saved = json.loads(state_path.read_text(encoding='utf-8-sig')) if state_path.is_file() else None
    # Pin the verified merge-base for repeatable local/CI comparisons, unless the
    # caller explicitly supplies a new target branch (which can invalidate state).
    comparison = base or ((saved or {}).get('inputs', {}).get('base_commit'))
    # Document kinds hash declared outputs as outputs only, never also as implicit inputs; Analyze keeps
    # them (tasks.md is both). Status follows the saved rule, so a 1.15.0 state (no marker) compares unchanged.
    if action == 'record':
        exclude = outputs if kind != 'analyze' else ()
    else:
        exclude = (saved.get('outputs') or ()) if (saved or {}).get('outputsNotInputs') else ()
    current = inputs(root, feature, kind, comparison, exclude)
    if action == 'record':
        if not outputs: raise ValueError('At least one actual output file is required.')
        output_hashes = fingerprints(root, outputs, kind)
        if any(value is None for value in output_hashes.values()): raise ValueError('A declared output is missing.')
        payload = {'schemaVersion': 2, 'feature': feature, 'kind': kind, 'inputs': current, 'outputs': output_hashes,
                   'gitHead': git(root, 'rev-parse', 'HEAD').strip()}
        if exclude: payload['outputsNotInputs'] = True
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        return {'current': True, 'recorded': True, 'state': relative(root, state_path)}
    if not saved: return {'current': False, 'reason': 'missing'}
    if saved.get('schemaVersion') != 2: return {'current': False, 'reason': 'legacy-state-regenerate'}
    saved_outputs = saved.get('outputs') or {}
    # Same kind rule as record. A state recorded before the manual block was ignored, over a tasks.md
    # that already held the block, goes stale once; any other earlier state hashes as it did.
    current_outputs = fingerprints(root, saved_outputs, kind)
    matches = (saved.get('feature') == feature and saved.get('kind') == kind and saved.get('inputs') == current
               and bool(saved_outputs) and current_outputs == saved_outputs)
    if matches: return {'current': True, 'reason': 'current'}
    # Sorted repository-relative paths that are new, changed or deleted since `record`.
    delta = lambda before, after: sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    return {'current': False, 'reason': 'stale-input-or-output',
            'changed_inputs': delta(saved.get('inputs', {}).get('files', {}), current['files']),
            'changed_outputs': delta(saved_outputs, current_outputs)}


def cli(description, record, state_path, kind, default_outputs=lambda root: [], gate=None):
    """The record/status command line shared by assure_state.py and manual_state.py; noncurrent exits 1.

    `record` is the caller's record_or_status (tests patch it there); `kind` is a fixed kind or a tuple
    of --kind choices; `state_path(root, feature, kind)` names the state file; `gate=(help, on(root))`
    adds --gate, which prints "skipped gate=off" and exits 0 unless on(root) is true.
    """
    import argparse
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('action', choices=('record', 'status'))
    parser.add_argument('--feature', required=True, type=Path)
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--base-ref')
    parser.add_argument('--output', action='append', default=[])
    if isinstance(kind, tuple):
        parser.add_argument('--kind', choices=kind, required=True)
    parser.add_argument('--summary', action='store_true', help='Print one line (ok/error, counts) instead of the full JSON result')
    parser.add_argument('--json', action='store_true', help="Print the full JSON result (today's default output)")
    if gate:
        parser.add_argument('--gate', action='store_true', help=gate[0])
    args = parser.parse_args()
    if args.summary and args.json:
        parser.error('--summary and --json cannot be combined')
    if gate and args.gate and args.action != 'status':
        parser.error('--gate applies to status only')
    root = args.repo_root.resolve()
    if gate and args.gate and not gate[1](root):
        print('skipped gate=off')
        return 0
    feature = args.feature if args.feature.is_absolute() else root / args.feature
    kind = args.kind if isinstance(kind, tuple) else kind
    # Status compares the outputs saved in the state, so only record walks for the default list.
    outputs = args.output or (default_outputs(root) if args.action == 'record' else [])
    base_ref = args.base_ref or checkpoint_target_branch(feature)
    try:
        result = record(root, feature, kind, state_path(root, feature, kind), args.action, outputs, base_ref)
    except (ValueError, OSError) as exc:
        result = {'current': False, 'reason': str(exc)}
    if args.summary:
        word = 'ok' if result['current'] else 'error'
        # A raised exception's message can itself carry embedded newlines; a
        # summary line must still be exactly one line.
        reason = ' '.join(str(result.get('reason', 'n/a')).split())
        detail = ' recorded=1' if result.get('recorded') else f' reason={reason}'
        if 'changed_inputs' in result:
            detail += f" changed_inputs={len(result['changed_inputs'])} changed_outputs={len(result['changed_outputs'])}"
        print(f'{word} action={args.action} kind={kind} outputs={len(outputs)}{detail}')
    else:
        print(json.dumps(result))
    return 0 if result['current'] else 1
