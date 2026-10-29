#!/usr/bin/env python3
"""Render benchmark_front_half.py results side by side: n, median, spread (min-max) and the delta of medians.

    python benchmark_compare.py --before a1.json [a2.json ...] --after b1.json [b2.json ...] [--md out.md]

Pass every run of an arm (wall time: at least five, alternating before and after on one machine).
"""
from __future__ import annotations

import argparse
import json
import statistics
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


def runs(values):
    """(median, spread) of one metric's values over the runs of an arm; spread is min-max, '-' for one run."""
    values = [v for v in values if v is not None]
    if not values:
        return None, '-'
    median = statistics.median(values)
    median = round(median, 1) if isinstance(median, float) else median
    return median, (f'{min(values)}-{max(values)}' if len(values) > 1 else '-')


def arm(results):
    """{metric: (median, spread)} over one arm's runs, in first-seen metric order."""
    flat = [metrics(r) for r in results]
    return {key: runs([f.get(key) for f in flat]) for key in dict.fromkeys(k for f in flat for k in f)}


def header(label, results):
    meta = results[0]['meta']
    return (f'{label}: {meta["repo"]} @ {meta["repo_head"]} (tier {meta["tier_requested"]}, '
            f'recovery {meta["recovery_path"]}), n={len(results)}')


def render(before, after):
    """`before` and `after` are one result each or a list of runs of the same arm."""
    before, after = [before] if isinstance(before, dict) else before, [after] if isinstance(after, dict) else after
    a, b = arm(before), arm(after)
    stages = a.get('stages_run', (None,))[0], b.get('stages_run', (None,))[0]
    kind = ('like-for-like (same stages run)' if stages[0] == stages[1] else
            f'process change (stages run {stages[0]} -> {stages[1]}): deltas mix fewer stages with cheaper ones')
    lines = [header('Before', before), header('After', after), 'Comparison: ' + kind, '',
             f'| metric | before median (n={len(before)}) | before spread | after median (n={len(after)}) | '
             'after spread | delta |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for key in dict.fromkeys([*a, *b]):
        (am, aspread), (bm, bspread) = a.get(key, (None, '-')), b.get(key, (None, '-'))
        lines.append(f'| {key} | {"-" if am is None else am} | {aspread} | {"-" if bm is None else bm} | {bspread} | '
                     f'{delta(am, bm)} |')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--before', type=Path, nargs='+', required=True, help='One or more runs of the before arm')
    parser.add_argument('--after', type=Path, nargs='+', required=True, help='One or more runs of the after arm')
    parser.add_argument('--md', type=Path, help='Also write the table to this Markdown file')
    args = parser.parse_args(argv)
    before = [json.loads(path.read_text(encoding='utf-8')) for path in args.before]
    text = render(before, [json.loads(path.read_text(encoding='utf-8')) for path in args.after])
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(text, encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
