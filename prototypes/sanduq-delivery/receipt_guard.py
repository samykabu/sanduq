#!/usr/bin/env python3
"""Static-command receipt gate for the isolated native-workflow experiment."""
import argparse
import json
import sys
from pathlib import Path

source_scripts = Path(__file__).resolve().parents[2] / 'extensions/workflow/scripts'
installed_scripts = Path.cwd() / '.specify/extensions/workflow/scripts'
sys.path.insert(0, str(source_scripts if source_scripts.is_dir() else installed_scripts))
from workflow import Run, WorkflowError, read, receipt_current, require


def check(root, stage):
    active = read(root / '.specify/feature.json', {})
    feature = active.get('feature_directory')
    require(isinstance(feature, str) and feature.startswith('specs/'),
            'PROTOTYPE_FEATURE_NOT_SELECTED')
    run = Run(root, feature)
    state = run.load()
    require(not state.get('active'), 'PROTOTYPE_STAGE_STILL_CLAIMED')
    receipt = state.get('receipts', {}).get(stage, {})
    require(receipt.get('outcome') == 'passed' and receipt.get('evidence'),
            'PROTOTYPE_RECEIPT_MISSING: ' + stage)
    require(receipt_current(root, feature, stage, receipt),
            'PROTOTYPE_RECEIPT_STALE: ' + stage)
    return {'ok': True, 'stage': stage, 'feature': feature}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--stage', required=True, choices=('specify', 'plan', 'tasks'))
    args = parser.parse_args()
    try:
        result = check(args.root.resolve(), args.stage)
        print(json.dumps(result))
        return 0
    except (WorkflowError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
