#!/usr/bin/env python3
"""Record or verify content and output freshness; noncurrent status exits 1."""
import argparse
import json
import sys
from pathlib import Path
try:
    from sanduq_freshness import record_or_status
except ModuleNotFoundError:
    # Source checkout only; release archives bundle the canonical helper.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/shared'))
    from sanduq_freshness import record_or_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('record', 'status'))
    parser.add_argument('--feature', required=True, type=Path)
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--base-ref')
    parser.add_argument('--output', action='append', default=[])
    parser.add_argument('--kind', choices=('analyze', 'document'), required=True)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    feature = args.feature if args.feature.is_absolute() else root / args.feature
    kind = args.kind
    state = root / '.specify/extensions/assure/state' / f'{feature.name}-{kind}.json'
    outputs = args.output
    try:
        result = record_or_status(root, feature, kind, state, args.action, outputs, args.base_ref)
    except (ValueError, OSError) as exc:
        result = {'current': False, 'reason': str(exc)}
    print(json.dumps(result))
    return 0 if result['current'] else 1


if __name__ == '__main__':
    sys.exit(main())
