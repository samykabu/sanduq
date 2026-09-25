#!/usr/bin/env python3
"""Upgrade the workflow package and its integrations inside an outer rollback boundary."""
import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path
import yaml
from packaging.version import Version
from workflow import WorkflowError, ensure_local_excludes, load_policy, locked, read, registry, require, write
from install import command, managed_files, restore, snapshot

REPOSITORY = 'https://github.com/samykabu/sanduq'


def upgrade(root, version, apply=False, packages=None, runner=command, preserve_ci=False):
    root = root.resolve()
    require(re.fullmatch(r'\d+\.\d+\.\d+', version), 'EXPLICIT_RELEASE_VERSION_REQUIRED')
    current = registry(root).get('workflow', {})
    require(current.get('version') and Version(version) >= Version(current['version']), 'WORKFLOW_DOWNGRADE_UNSUPPORTED')
    url = f'{REPOSITORY}/releases/download/workflow-v{version}/workflow.zip'
    if packages:
        source = packages.resolve() / 'workflow'
        meta = yaml.safe_load((source / 'extension.yml').read_text(encoding='utf-8-sig'))['extension']
        require((meta['id'], str(meta['version']), meta['repository']) == ('workflow', version, REPOSITORY), 'WORKFLOW_PACKAGE_IDENTITY_MISMATCH')
        args = ['specify', 'extension', 'add', '--dev', str(source), '--force']
    else:
        args = ['specify', 'extension', 'add', 'workflow', '--from', url, '--force']
    result = {'applied': False, 'from': current['version'], 'to': version, 'source': url,
              'distribution': 'local-development' if packages else 'release', 'command': args,
              'preserve_ci_requested': preserve_ci, 'preserved_ci': None}
    if not apply: return result
    ensure_local_excludes(root)
    with locked(root / '.specify/workflow/runtime/upgrade.lock'):
        with locked(root / '.specify/workflow/runtime/dispatch.lock'):
            for path in (root / 'specs').glob('*/workflow/checkpoint.json'):
                require(not read(path, {}).get('active'), 'ACTIVE_STAGE_MUST_BE_RESOLVED')
            require(read(root / '.specify/superpowers-handoff.json', {}).get('status') not in ('executing', 'blocked'), 'LEGACY_EXECUTOR_OWNS_FEATURE')
            backup = root / '.specify/workflow/backups/upgrades' / uuid.uuid4().hex
            before = snapshot(root, backup)
            delegation_before = load_policy(root)['delegation']
            history_before = {path: content for path, content in before.items()
                              if path.startswith('specs/') and path.endswith('/workflow/delegations.json')}
            ci_path = '.github/workflows/sanduq-workflow-gates.yml'
            ci_before = before.get(ci_path) if preserve_ci else None
        log = []
        try:
            with locked(root / '.specify/workflow/runtime/dispatch.lock'):
                runner(root, args, log)
                meta = yaml.safe_load((root / '.specify/extensions/workflow/extension.yml').read_text(encoding='utf-8-sig'))['extension']
                require((meta['id'], str(meta['version']), meta['repository']) == ('workflow', version, REPOSITORY), 'INSTALLED_WORKFLOW_IDENTITY_MISMATCH')
            # Run the new package's installer; do not assume the old adapter knows its contract.
            tail = ['--packages', str(packages.resolve())] if packages else []
            if preserve_ci:
                tail.append('--preserve-ci')
            if ci_before is not None:
                # A target installer may check CI health before it records the
                # preserved file, and older ones read only the git-excluded
                # receipt, which a fresh clone or worktree lacks (#22). Record
                # the choice there first; the snapshot restores it on rollback.
                receipt_path = root / '.specify/workflow/install-receipt.json'
                receipt = read(receipt_path, {})
                if (receipt.get('preserved_ci') or {}).get('path') != ci_path:
                    write(receipt_path, {**receipt, 'preserved_ci': {
                        'path': ci_path, 'sha256': hashlib.sha256(ci_before).hexdigest()}})
            runner(root, [sys.executable, str(root / '.specify/extensions/workflow/scripts/install.py'),
                          '--root', str(root), '--apply', '--upgrade-owner', str(os.getpid()), *tail], log)
            require(load_policy(root)['delegation'] == delegation_before,
                    'DELEGATION_POLICY_PRESERVATION_FAILED')
            after = managed_files(root)
            require({path: content for path, content in after.items()
                     if path.startswith('specs/') and path.endswith('/workflow/delegations.json')}
                    == history_before, 'DELEGATION_HISTORY_PRESERVATION_FAILED')
            if ci_before is not None:
                require((root / ci_path).read_bytes() == ci_before, 'PROJECT_CI_PRESERVATION_FAILED')
                result['preserved_ci'] = {'path': ci_path, 'sha256': hashlib.sha256(ci_before).hexdigest()}
            result.update(applied=True, backup=str(backup), commands=log)
            write(backup / 'result.json', {'ok': True, **result})
            return result
        except Exception as error:
            write(backup / 'result.json', {'ok': False, 'error': str(error), 'commands': log})
            with locked(root / '.specify/workflow/runtime/dispatch.lock'):
                restore(root, before, managed_files(root))
            raise WorkflowError('WORKFLOW_UPGRADE_ROLLED_BACK: ' + str(error) + '; backup: ' + str(backup)) from error


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--version', required=True)
    parser.add_argument('--packages', type=Path, help='Verified extracted packages for development')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--preserve-ci', action='store_true', help='Retain the project workflow-gates CI file during the upgrade')
    args = parser.parse_args()
    try:
        print(json.dumps(upgrade(args.root, args.version, args.apply, args.packages, preserve_ci=args.preserve_ci), indent=2))
    except (WorkflowError, ValueError, OSError, KeyError) as error:
        print(json.dumps({'ok': False, 'error': str(error)})); sys.exit(1)
