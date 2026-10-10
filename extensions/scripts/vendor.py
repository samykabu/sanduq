#!/usr/bin/env python3
"""Vendor pinned portable skills from sanduq-skills into extension packages.

`vendor.lock.json` (repository root) names, per input, the sanduq-skills commit it was taken from
and the SHA-256 of every vendored file after its transform. Vendored files are build inputs, never
hand edits: change the skill in sanduq-skills, release it, then sync here.

  python extensions/scripts/vendor.py check                      # CI: the tree matches the lock
  python extensions/scripts/vendor.py sync --source <checkout> --input illustrate --ref <tag>

`sync` reads from a local sanduq-skills clone at the tag's commit (`git show`), never its working tree.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / 'vendor.lock.json'
INTERNAL = 'metadata:\n  internal: true\n'


def mark_internal(text):
    """Hide a vendored SKILL.md from `npx skills` discovery in this repository."""
    if not text.startswith('---\n'):
        raise ValueError('SKILL.md without front matter')
    end = text.index('\n---\n', 4)
    head = text[4:end + 1]
    if 'internal: true' in head:
        return text
    if '\nmetadata:\n' in '\n' + head:
        head = head.replace('metadata:\n', INTERNAL, 1) if head.startswith('metadata:\n') else \
            head.replace('\nmetadata:\n', '\n' + INTERNAL, 1)
    else:
        head += INTERNAL
    return '---\n' + head + text[end + 1:]


def transform(name, data, rule):
    if name.endswith('SKILL.md') and rule.get('internal'):
        data = mark_internal(data.decode('utf-8')).encode('utf-8')
    for old, new in rule.get('replace', {}).get(name, []):
        if old.encode() not in data:
            raise ValueError(f'{name}: rewrite source text not found: {old!r}')
        data = data.replace(old.encode(), new.encode())
    return data


def git(source, *args):
    return subprocess.run(['git', '-C', str(source), *args], check=True, capture_output=True).stdout


def planned(source, sha, rule):
    """{target path: bytes} for one input at one commit."""
    files = {}
    for src, dst in rule['map']:
        names = git(source, 'ls-tree', '-r', '--name-only', sha, '--', src).decode().splitlines()
        if not names:
            raise ValueError(f'{src} not found at {sha}')
        for path in names:
            rel = path[len(src):].lstrip('/') if path != src else Path(src).name
            if any(part in ('node_modules', '__pycache__', 'tests', 'test') for part in Path(rel).parts):
                continue
            target = (dst + '/' + rel) if path != src else dst
            files[target] = transform(rel if path != src else Path(src).name, git(source, 'show', f'{sha}:{path}'), rule)
    return files


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sync(lock, source, name, ref):
    rule = lock['inputs'][name]
    sha = git(source, 'rev-parse', ref + '^{commit}').decode().strip()
    files = planned(source, sha, rule)
    for old in set(rule.get('files', {})) - set(files):
        (ROOT / old).unlink(missing_ok=True)
    for target, data in files.items():
        path = ROOT / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    rule.update(ref=ref, sha=sha, files={target: digest(data) for target, data in sorted(files.items())})
    LOCK.write_text(json.dumps(lock, indent=2) + '\n', encoding='utf-8', newline='\n')
    return len(files)


def check(lock):
    errors = []
    for name, rule in lock['inputs'].items():
        for target, expected in rule.get('files', {}).items():
            path = ROOT / target
            if not path.is_file():
                errors.append(f'{name}: {target} is missing')
            elif digest(path.read_bytes()) != expected:
                errors.append(f'{name}: {target} differs from {rule["ref"]}; edit it in sanduq-skills')
        if rule.get('exclusive'):
            owned = set(rule.get('files', {}))
            for dst in {dst for _, dst in rule['map']}:
                for path in (ROOT / dst).rglob('*'):
                    rel = path.relative_to(ROOT).as_posix()
                    if path.is_file() and rel not in owned and not {'node_modules', '__pycache__'} & set(path.parts):
                        errors.append(f'{name}: {rel} is not part of {rule["ref"]}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    run = sub.add_parser('sync')
    run.add_argument('--source', type=Path, required=True)
    run.add_argument('--input', required=True)
    run.add_argument('--ref', required=True)
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    if args.command == 'sync':
        print(f'{args.input}: {sync(lock, args.source, args.input, args.ref)} files from {args.ref}')
        return 0
    errors = check(lock)
    print('\n'.join(errors) or f'vendored inputs match {LOCK.name}')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
