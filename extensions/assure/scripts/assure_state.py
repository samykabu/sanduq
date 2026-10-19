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


KEY = 'require_document_before_pr'


def gate_on(config):
    """True when the config sets lifecycle.require_document_before_pr to true; a missing file or key is off.
    A parsed value is authoritative. The comment-aware text reader runs only when YAML parsing fails;
    a file that names the key where neither reader finds it fails closed (on) with one message."""
    if not config.is_file():
        return False
    text = config.read_text(encoding='utf-8-sig')
    try:
        import yaml
        doc = yaml.safe_load(text) or {}
        lifecycle = doc.get('lifecycle') or {}
        if not isinstance(lifecycle, dict):
            raise ValueError('lifecycle is not a mapping')
        return str(lifecycle.get(KEY)).lower() == 'true'
    except Exception:  # no PyYAML (CI runs this before any pip install) or a layout it rejects, such as tabs
        pass
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from assure_scan import read_config
    lifecycle = read_config(config).get('lifecycle') or {}
    if KEY in lifecycle:
        return str(lifecycle[KEY]).lower() == 'true'
    if any(KEY in line.split(' #')[0] for line in text.splitlines() if not line.lstrip().startswith('#')):
        print(f'{config}: cannot be parsed; treating the documentation gate as on', file=sys.stderr)
        return True
    return False


def main():
    return cli(__doc__, record_or_status, kind=('analyze', 'document'),
               state_path=lambda root, feature, kind: root / '.specify/extensions/assure/state' / f'{feature.name}-{kind}.json',
               gate=('status only: print "skipped gate=off" and exit 0 unless assure-config.yml sets '
                     'lifecycle.require_document_before_pr to true',
                     lambda root: gate_on(root / '.specify/extensions/assure/assure-config.yml')))


if __name__ == '__main__':
    sys.exit(main())
