#!/usr/bin/env python3
"""The canonical source key `bunyan-source-key/1` (workflow 1.6.0, B3).

A SHA-256 over the `git ls-tree -r -z --full-tree` records of one explicit
tree, without the paths that carry only words or workflow state. The consumer
contract is Bunyan's `docs/development/verification-plan-contract.md`; its
`eng/ci/source-key.mjs` computes the same value, and both reproduce every case
of the shared `source-key.fixtures.json`.

1. Drop a record whose path starts with an excluded prefix (byte prefix,
   trailing slash included, case-sensitive) or ends in `.md` in any ASCII case.
2. Sort the rest by path bytes (unsigned lexicographic).
3. Serialise each as `<mode> <type> <object> <path>\\n`.
4. Prefix `bunyan-source-key/1\\n`; the key is the lowercase hex SHA-256.

Paths stay bytes from git to the hash: nothing is decoded, so any file name is
safe. The key is distinct from a receipt's `source_fingerprints` (a working-tree
inventory): it binds a receipt, or a CI run, to the source of one commit.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

KEY_VERSION = 'bunyan-source-key/1'
EXCLUDED_PREFIXES = ('.specify/', '.agents/', '.claude/', '.codex/', 'specs/', 'User-Manual/', 'docs/',
                     'graphify-out/', 'artifacts/')
_EXCLUDED = tuple(prefix.encode('utf-8') for prefix in EXCLUDED_PREFIXES)


class SourceKeyError(ValueError):
    """A tree or a record the key cannot be computed from."""


def _bytes(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    return str(value).encode('utf-8')


def is_source_path(path):
    """Whether a path (bytes or str) counts as source for the key."""
    value = _bytes(path)
    if value.startswith(_EXCLUDED):
        return False
    return not (len(value) >= 3 and value[-3] == 0x2e and value[-2] | 0x20 == 0x6d and value[-1] | 0x20 == 0x64)


def _field(entry, name, index):
    return _bytes(entry[name] if isinstance(entry, dict) else entry[index])


def key_from_entries(entries):
    """The key of `{mode, type, object, path}` entries (dicts or 4-tuples; str or bytes fields)."""
    rows = [(_field(e, 'mode', 0), _field(e, 'type', 1), _field(e, 'object', 2), _field(e, 'path', 3))
            for e in entries]
    rows = sorted((row for row in rows if is_source_path(row[3])), key=lambda row: row[3])
    digest = hashlib.sha256((KEY_VERSION + '\n').encode('ascii'))
    for mode, kind, obj, path in rows:
        digest.update(mode + b' ' + kind + b' ' + obj + b' ' + path + b'\n')
    return digest.hexdigest()


def parse_ls_tree(output):
    """Parse `git ls-tree -r -z` output into (mode, type, object, path) byte tuples."""
    entries = []
    for record in bytes(output).split(b'\0'):
        if not record:
            continue
        meta, tab, path = record.partition(b'\t')
        fields = meta.split(b' ')
        if not tab or len(fields) != 3:
            raise SourceKeyError('Unparseable git ls-tree record: ' + repr(record))
        entries.append((fields[0], fields[1], fields[2], path))
    return entries


def _git(root, *args):
    result = subprocess.run(['git', *args], cwd=root, capture_output=True)
    if result.returncode != 0:
        raise SourceKeyError('git ' + ' '.join(args) + ': ' + result.stderr.decode('utf-8', 'replace').strip())
    return result.stdout


def tree_of(root, treeish):
    """The tree object a tree-ish names (a commit's tree, or the tree itself)."""
    if not treeish:
        raise SourceKeyError('A source key needs an explicit tree-ish.')
    return _git(root, 'rev-parse', '--verify', str(treeish) + '^{tree}').decode('ascii').strip()


def source_key(root, treeish='HEAD'):
    """The key of an explicit tree: never the working tree or the index."""
    tree = tree_of(root, treeish)
    return key_from_entries(parse_ls_tree(_git(root, 'ls-tree', '-r', '-z', '--full-tree', tree)))


def dirty_source_paths(root):
    """Working-tree changes the key would count: staged, unstaged or untracked.

    A receipt binds the key of HEAD to a working-tree inventory, which only
    holds while no source path differs from HEAD.
    """
    output = _git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--no-renames')
    paths = []
    for record in output.split(b'\0'):
        if len(record) > 3 and is_source_path(record[3:]):
            paths.append(record[3:].decode('utf-8', 'surrogateescape'))
    return sorted(paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('treeish', help='An explicit tree-ish, such as HEAD or a commit SHA')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        print(source_key(args.root, args.treeish))
    except SourceKeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
