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
from sanduq_hash import portable_content, text_attributes

EXCLUDED = {'.git', 'node_modules', 'bin', 'obj', 'dist', 'build', 'coverage', '__pycache__'}


def git(root, *args):
    result = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, encoding='utf-8')
    if result.returncode: raise ValueError('Git freshness input unavailable: ' + result.stderr.strip())
    return result.stdout


def relative(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()): raise ValueError('Path outside project: ' + str(value))
    return path.relative_to(root.resolve()).as_posix()


def fingerprints(root, paths):
    result = {}
    paths = [relative(root, value) for value in sorted(set(paths))]
    attributes = text_attributes(root, paths)
    for value in paths:
        key = relative(root, value)
        path = root / key
        content = path.read_bytes() if path.is_file() else None
        if content is not None:
            content = portable_content(path, content, attributes.get(key))
        if content is not None and path.name == 'tasks.md':
            content = re.sub(rb'(?m)^(\s*- )\[[ xX]\]', rb'\1[ ]', content)
        result[key] = hashlib.sha256(content).hexdigest() if content is not None else None
    return result


def base_ref(root, explicit=None):
    if explicit: return git(root, 'merge-base', 'HEAD', explicit).strip()
    try:
        ref = git(root, 'symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD').strip()
    except ValueError:
        raise ValueError('Default remote branch unknown; supply --base-ref explicitly.')
    return git(root, 'merge-base', 'HEAD', ref).strip()


def inputs(root, feature, kind, base=None):
    feature = relative(root, feature)
    paths = {relative(root, p) for p in (root / feature).rglob('*') if p.is_file()}
    if kind != 'analyze':
        comparison = base_ref(root, base)
        # name-only includes deleted files; diff against the working tree includes
        # staged and unstaged edits. No HEAD^ fallback can hide earlier commits.
        paths.update(filter(None, git(root, 'diff', '--name-only', '-z', comparison).split('\0')))
        paths.update(filter(None, git(root, 'ls-files', '--others', '--exclude-standard', '-z').split('\0')))
    else:
        comparison = None
    def included(value):
        parts = Path(value).parts
        return not (any(p in EXCLUDED for p in parts) or value.startswith((feature + '/workflow/',
            feature + '/evidence/', '.specify/workflow/', '.specify/scope/', '.specify/extensions/',
            'graphify-out/', 'User-Manual/', 'docs/' + Path(feature).name + '/')) or Path(value).name in
            {'.env', 'workflow.yml', 'feature.json', 'project-sync-state.json'})
    result = fingerprints(root, [p for p in paths if included(p)])
    # Task completion bookkeeping is not a requirements change.
    task = feature + '/tasks.md'
    if task in result and (root / task).is_file():
        import re
        content = (root / task).read_bytes().replace(b'\r\n', b'\n')
        content = re.sub(rb'(?m)^(\s*- )\[[ xX]\]', rb'\1[ ]', content)
        result[task] = hashlib.sha256(content).hexdigest()
    return {'base_commit': comparison, 'files': result}


def record_or_status(root, feature, kind, state_path, action, outputs, base=None):
    feature = relative(root, feature)
    state_path = root / relative(root, state_path)
    saved = json.loads(state_path.read_text(encoding='utf-8-sig')) if state_path.is_file() else None
    # Pin the verified merge-base for repeatable local/CI comparisons, unless the
    # caller explicitly supplies a new target branch (which can invalidate state).
    comparison = base or ((saved or {}).get('inputs', {}).get('base_commit'))
    current = inputs(root, feature, kind, comparison)
    if action == 'record':
        if not outputs: raise ValueError('At least one actual output file is required.')
        output_hashes = fingerprints(root, outputs)
        if any(value is None for value in output_hashes.values()): raise ValueError('A declared output is missing.')
        payload = {'schemaVersion': 2, 'feature': feature, 'kind': kind, 'inputs': current, 'outputs': output_hashes,
                   'gitHead': git(root, 'rev-parse', 'HEAD').strip()}
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        return {'current': True, 'recorded': True, 'state': relative(root, state_path)}
    if not saved: return {'current': False, 'reason': 'missing'}
    if saved.get('schemaVersion') != 2: return {'current': False, 'reason': 'legacy-state-regenerate'}
    matches = (saved.get('feature') == feature and saved.get('kind') == kind and saved.get('inputs') == current
               and bool(saved.get('outputs')) and fingerprints(root, saved['outputs']) == saved['outputs'])
    return {'current': matches, 'reason': 'current' if matches else 'stale-input-or-output'}
