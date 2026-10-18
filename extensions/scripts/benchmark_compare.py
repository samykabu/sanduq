#!/usr/bin/env python3
"""Render two benchmark_front_half.py results side by side with percentage deltas.

    python benchmark_compare.py --before a.json --after b.json [--md out.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def metrics(result):
    """Flatten one result into ordered {metric: number}."""
    values = {k: v for k, v in result['totals'].items() if isinstance(v, (int, float)) or v is None}
    for action in sorted({c['action'] for c in result['commands']}):
        cmds = [c for c in result['commands'] if c['action'] == action]
        values[action + '.count'] = len(cmds)
        values[action + '.ms'] = round(sum(c['ms'] for c in cmds), 1)
        values[action + '.stdout_bytes'] = sum(c['stdout_bytes'] for c in cmds)
    for stage, entry in result['instructions']['per_stage'].items():
        values['instructions.' + stage] = entry['bytes']
    values['instructions.pointer_set_once'] = sum(result['instructions']['pointer_set_once'].values())
    values['instructions.linked_once'] = sum(result['instructions']['linked_once'].values())
    return values


def delta(before, after):
    if before is None or after is None:
        return 'n/a'
    if before == 0:
        return '0%' if after == 0 else 'new'
    return f'{(after - before) / before * 100:+.1f}%'


def render(before, after):
    a, b = metrics(before), metrics(after)
    lines = [f'Before: {before["meta"]["repo"]} @ {before["meta"]["repo_head"]} (tier {before["meta"]["tier_requested"]}, '
             f'recovery {before["meta"]["recovery_path"]})',
             f'After: {after["meta"]["repo"]} @ {after["meta"]["repo_head"]} (tier {after["meta"]["tier_requested"]}, '
             f'recovery {after["meta"]["recovery_path"]})', '',
             '| metric | before | after | delta |', '| --- | ---: | ---: | ---: |']
    for key in list(dict.fromkeys([*a, *b])):
        lines.append(f'| {key} | {a.get(key, "-")} | {b.get(key, "-")} | {delta(a.get(key), b.get(key))} |')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--md', type=Path, help='Also write the table to this Markdown file')
    args = parser.parse_args(argv)
    text = render(json.loads(args.before.read_text(encoding='utf-8')), json.loads(args.after.read_text(encoding='utf-8')))
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(text, encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
