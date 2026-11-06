#!/usr/bin/env python3
"""Record or verify content and output freshness; noncurrent status exits 1."""
import json
import os
import sys
from pathlib import Path
try:
    from sanduq_freshness import cli, record_or_status as shared_record_or_status
except ModuleNotFoundError:
    # Source checkout only; release archives bundle the canonical helper.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/shared'))
    from sanduq_freshness import cli, record_or_status as shared_record_or_status
sys.path.insert(0, str(Path(__file__).resolve().parent))
import assure_readiness

CONTRACT = 2  # 1 = analyses recorded before the structured readiness record; they carry no assureContract


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


def record_or_status(root, feature, kind, state_path, action, outputs, base=None):
    """Shared freshness plus the analysis contract: analyze records only after the readiness checks pass, and a
    state recorded under contract 1 is reported needs-reanalysis without being rewritten."""
    if kind != 'analyze':
        return shared_record_or_status(root, feature, kind, state_path, action, outputs, base)
    root, feature = Path(root).resolve(), Path(feature)
    if action == 'record':
        errors, warnings, _ = assure_readiness.check(root, feature)
        if errors:
            return {'current': False, 'reason': 'readiness-invalid', 'errors': errors, 'warnings': warnings}
        rel = lambda p: Path(p).resolve().relative_to(root).as_posix() if Path(p).is_absolute() else Path(p).as_posix()
        record = (feature if feature.is_absolute() else root / feature) / assure_readiness.RECORD
        outputs = sorted({*map(rel, outputs), rel(record.parent.parent / 'tasks.md'), rel(record),
                          *assure_readiness.proof_paths(root, feature)})
    result = shared_record_or_status(root, feature, kind, state_path, action, outputs, base)
    path = Path(state_path) if Path(state_path).is_absolute() else root / state_path
    if action == 'record':
        state = json.loads(path.read_text(encoding='utf-8'))
        state.update(assureContract=CONTRACT, readiness=rel(record))
        path.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
        return {**result, 'contract': CONTRACT, 'warnings': warnings}
    if not path.is_file() or result.get('reason') in ('missing', 'legacy-state-regenerate'):
        return result
    saved = json.loads(path.read_text(encoding='utf-8-sig'))
    if 'assureContract' not in saved:
        return {**result, 'current': False, 'reason': 'needs-reanalysis', 'contract': 1, 'legacy_current': result['current']}
    if not saved.get('readiness'):
        return {**result, 'current': False, 'reason': 'needs-reanalysis', 'contract': saved['assureContract']}
    return {**result, 'contract': saved['assureContract']}


def main():
    return cli(__doc__, record_or_status, kind=('analyze', 'document'),
               state_path=lambda root, feature, kind: root / '.specify/extensions/assure/state' / f'{feature.name}-{kind}.json',
               gate=('status only: print "skipped gate=off" and exit 0 unless assure-config.yml sets '
                     'lifecycle.require_document_before_pr to true',
                     lambda root: gate_on(config_root(root) / CONFIG)))


CONFIG = '.specify/extensions/assure/assure-config.yml'


def config_root(root):
    """The PR base checkout (`SANDUQ_POLICY_ROOT`, set by the CI gate) when it has a config, so a PR cannot
    switch its own gate off (SEC-03); otherwise `root`, as on a first install."""
    trusted = Path(os.environ.get('SANDUQ_POLICY_ROOT') or root)
    return trusted if (trusted / CONFIG).is_file() else root


if __name__ == '__main__':
    sys.exit(main())
