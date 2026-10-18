#!/usr/bin/env python3
"""Check SKILL.md and SKILL.ext.md files against the Agent Skills frontmatter rules.

    python validate_skills.py <file or directory>... [--json]

A directory is searched for SKILL.md and SKILL.ext.md files (node_modules and results skipped).
Errors (exit 1): missing or unparsable frontmatter; `name` not 1-64 characters of [a-z0-9-] or
with a leading, trailing or double hyphen; `name` not equal to its directory; `description` not
1-1,024 characters; `compatibility` over 500 characters; `metadata` not a map of strings.
Warnings: a body of 500 lines or more; a `metadata` value that is a YAML number or boolean
(quote it). Only the source folders in DIRECTORY_EXCEPTIONS may differ from their skill name.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

NAME = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
NAMES = ('SKILL.md', 'SKILL.ext.md')
SKIP = {'node_modules', 'results', '.git'}
# (folder, name) source layouts whose folder never becomes a host skill folder. The workflow
# dispatcher is read by path from .specify/extensions/workflow/skills/workflow/SKILL.md; the
# vendored copies live in a generic `skill/` folder and install under their own name.
DIRECTORY_EXCEPTIONS = {('workflow', 'speckit-workflow'), ('skill', 'illustrate'), ('skill', 'progress-report')}


def frontmatter(text):
    """(mapping, body) or raise ValueError."""
    text = text.lstrip('﻿').replace('\r\n', '\n')
    if not text.startswith('---\n'):
        raise ValueError('no YAML frontmatter (the file must start with ---)')
    end = text.find('\n---', 3)
    if end < 0 or text[end + 4:end + 5] not in ('', '\n'):
        raise ValueError('frontmatter is not closed with ---')
    try:
        data = yaml.safe_load(text[4:end + 1])
    except yaml.YAMLError as exc:
        raise ValueError('frontmatter is not valid YAML: ' + str(exc).splitlines()[0]) from None
    if not isinstance(data, dict):
        raise ValueError('frontmatter is not a mapping')
    return data, text[end + 5:]


def check(path):
    """{'path', 'errors', 'warnings'} for one skill file."""
    errors, warnings = [], []
    try:
        data, body = frontmatter(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return {'path': path.as_posix(), 'errors': [str(exc)], 'warnings': []}
    metadata = data.get('metadata')
    if metadata is not None and not isinstance(metadata, dict):
        errors.append('metadata must be a map of string keys to string values')
        metadata = {}
    metadata = metadata or {}
    for key, value in metadata.items():
        if not isinstance(key, str) or isinstance(value, (dict, list)) or value is None:
            errors.append(f'metadata.{key} must be a string')
        elif not isinstance(value, str):
            warnings.append(f'metadata.{key} is {type(value).__name__}; quote it as a string')
    name = data.get('name')
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or not NAME.match(name):
        errors.append(f'name {name!r} must be 1-64 characters of a-z, 0-9 and single inner hyphens')
    elif name != path.parent.name and (path.parent.name, name) not in DIRECTORY_EXCEPTIONS:
        errors.append(f'name {name!r} does not match its directory {path.parent.name!r}')
    description = data.get('description')
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        size = len(description) if isinstance(description, str) else 0
        errors.append(f'description must be 1-1,024 characters (found {size})')
    compatibility = data.get('compatibility')
    if compatibility is not None and (not isinstance(compatibility, str) or len(compatibility) > 500):
        errors.append('compatibility must be a string of at most 500 characters')
    lines = len(body.splitlines())
    if lines >= 500:
        warnings.append(f'body is {lines} lines; keep it under 500 and move detail into references')
    return {'path': path.as_posix(), 'errors': errors, 'warnings': warnings}


def skill_files(target):
    target = Path(target)
    if target.is_file():
        return [target]
    found = []
    for name in NAMES:
        found += [p for p in target.rglob(name) if not SKIP.intersection(p.relative_to(target).parts)]
    return sorted(found)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    files = []
    for target in args.paths:
        if not Path(target).exists():
            parser.error('no such path: ' + target)
        files += skill_files(target)
    results = [check(path) for path in dict.fromkeys(files)]
    errors = sum(len(r['errors']) for r in results)
    if args.json:
        print(json.dumps({'ok': not errors, 'files': len(results), 'results': results}, indent=2))
    else:
        for result in results:
            for kind in ('errors', 'warnings'):
                for message in result[kind]:
                    print(f"{result['path']}: {kind[:-1]}: {message}")
        print(f'{len(results)} skill files, {errors} errors, {sum(len(r["warnings"]) for r in results)} warnings')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
