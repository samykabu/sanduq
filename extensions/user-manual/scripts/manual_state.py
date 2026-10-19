#!/usr/bin/env python3
"""Record or verify content and output freshness; noncurrent status exits 1."""
import sys
from pathlib import Path
try:
    from sanduq_freshness import cli, record_or_status
except ModuleNotFoundError:
    # Source checkout only; release archives bundle the canonical helper.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/shared'))
    from sanduq_freshness import cli, record_or_status


def manual_outputs(root):
    """Every file under User-Manual/ except build output and state."""
    return [p.relative_to(root).as_posix() for p in (root / 'User-Manual').rglob('*') if p.is_file() and not any(part in ('.state', 'site', 'pdf', '__pycache__') for part in p.relative_to(root / 'User-Manual').parts)]


def main():
    return cli(__doc__, record_or_status, kind='manual', default_outputs=manual_outputs,
               state_path=lambda root, feature, kind: root / 'User-Manual/.state/features' / f'{feature.name}.json')


if __name__ == '__main__':
    sys.exit(main())
