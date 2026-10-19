#!/usr/bin/env python3
"""Record or verify content and output freshness; noncurrent status exits 1."""
import argparse
import json
import sys
from pathlib import Path
try:
    from sanduq_freshness import record_or_status, checkpoint_target_branch
except ModuleNotFoundError:
    # Source checkout only; release archives bundle the canonical helper.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/shared'))
    from sanduq_freshness import record_or_status, checkpoint_target_branch


def gate_on(config):
    """True when the config sets lifecycle.require_document_before_pr; a missing file or key is off."""
    if not config.is_file():
        return False
    try:
        import yaml
        value = ((yaml.safe_load(config.read_text(encoding='utf-8-sig')) or {}).get('lifecycle') or {}).get('require_document_before_pr')
    except Exception:  # no PyYAML (CI runs this before any pip install) or a layout it rejects, such as tabs
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from assure_scan import read_config
        value = (read_config(config).get('lifecycle') or {}).get('require_document_before_pr')
    if str(value).lower() == 'true':
        return True
    # Fail closed: a layout neither reader understood but which names the key with true still gates.
    return any('require_document_before_pr' in line and 'true' in line.lower()
               for line in config.read_text(encoding='utf-8-sig').splitlines() if not line.lstrip().startswith('#'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('record', 'status'))
    parser.add_argument('--feature', required=True, type=Path)
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--base-ref')
    parser.add_argument('--output', action='append', default=[])
    parser.add_argument('--kind', choices=('analyze', 'document'), required=True)
    parser.add_argument('--summary', action='store_true', help='Print one line (ok/error, counts) instead of the full JSON result')
    parser.add_argument('--json', action='store_true', help="Print the full JSON result (today's default output)")
    parser.add_argument('--gate', action='store_true',
                        help='status only: print "skipped gate=off" and exit 0 unless assure-config.yml sets '
                             'lifecycle.require_document_before_pr to true')
    args = parser.parse_args()
    if args.summary and args.json:
        parser.error('--summary and --json cannot be combined')
    if args.gate and args.action != 'status':
        parser.error('--gate applies to status only')
    root = args.repo_root.resolve()
    if args.gate and not gate_on(root / '.specify/extensions/assure/assure-config.yml'):
        print('skipped gate=off')
        return 0
    feature = args.feature if args.feature.is_absolute() else root / args.feature
    kind = args.kind
    state = root / '.specify/extensions/assure/state' / f'{feature.name}-{kind}.json'
    outputs = args.output
    base_ref = args.base_ref or checkpoint_target_branch(feature)
    try:
        result = record_or_status(root, feature, kind, state, args.action, outputs, base_ref)
    except (ValueError, OSError) as exc:
        result = {'current': False, 'reason': str(exc)}
    if args.summary:
        word = 'ok' if result['current'] else 'error'
        # A raised exception's message can itself carry embedded newlines; a
        # summary line must still be exactly one line.
        reason = ' '.join(str(result.get('reason', 'n/a')).split())
        detail = ' recorded=1' if result.get('recorded') else f' reason={reason}'
        print(f'{word} action={args.action} kind={kind} outputs={len(outputs)}{detail}')
    else:
        print(json.dumps(result))
    return 0 if result['current'] else 1


if __name__ == '__main__':
    sys.exit(main())
