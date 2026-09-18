#!/usr/bin/env python3
"""Reconcile managed hook ownership. Dry-run default; restore only unchanged managed entries."""
import argparse
import copy
import json
from pathlib import Path

import yaml
from workflow import load_policy, require, write, read, WorkflowError, locked

OWNED = {'assure', 'user-manual', 'superspec', 'speckit-superpowers-bridge', 'project'}


def reconcile(root, apply=False, restore=False):
    with locked(root / '.specify/workflow/runtime/reconcile.lock'):
        return _reconcile(root, apply, restore)


def _reconcile(root, apply=False, restore=False):
    load_policy(root)
    path = root / '.specify/extensions.yml'
    require(path.is_file(), 'EXTENSIONS_CONFIG_REQUIRED')
    document = yaml.safe_load(path.read_text(encoding='utf-8-sig'))
    require(isinstance(document, dict) and isinstance(document.get('hooks'), dict), 'INVALID_HOOK_CONFIG')
    backup = root / '.specify/workflow/integration-backup.json'
    journal = read(backup, {'schema_version': 1, 'entries': {}})
    changes = []
    for event, hooks in document['hooks'].items():
        require(isinstance(hooks, list), 'INVALID_HOOK_LIST: ' + event)
        seen = set()
        for hook in hooks:
            require(isinstance(hook, dict), 'INVALID_HOOK_ENTRY')
            key = event + ':' + hook.get('command', '')
            require(key not in seen, 'DUPLICATE_HOOK: ' + key)
            seen.add(key)
            managed = hook.get('extension') in OWNED or (hook.get('extension') == 'pr' and event == 'after_implement') or (hook.get('command') == 'speckit.scope.after-specify') or (hook.get('extension') == 'project' and event == 'after_tasks')
            if not managed: continue
            before = copy.deepcopy(hook)
            if restore:
                record = journal['entries'].get(key)
                if record:
                    require(hook == record['managed'], 'HOOK_CHANGED_SINCE_RECONCILE: ' + key)
                    hook.clear(); hook.update(record['original'])
            else:
                if key in journal['entries']:
                    require(hook == journal['entries'][key]['managed'], 'HOOK_CHANGED_SINCE_RECONCILE: ' + key)
                else:
                    journal['entries'][key] = {'original': before}
                hook['enabled'] = False
                journal['entries'][key]['managed'] = copy.deepcopy(hook)
            if before != hook: changes.append({'hook': key, 'before': before, 'after': copy.deepcopy(hook)})
    if apply:
        if not restore: write(backup, journal)
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding='utf-8')
        if restore: backup.unlink(missing_ok=True)
    return {'applied': apply, 'restore': restore, 'changes': changes,
            'note': 'Domain commands remain installed. Managed dispatcher owns sequencing; scope guard/bind and unrelated hooks remain intact.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--apply', action='store_true'); p.add_argument('--restore', action='store_true')
    a = p.parse_args()
    try:
        print(json.dumps(reconcile(a.root.resolve(), a.apply, a.restore), indent=2))
    except (WorkflowError, yaml.YAMLError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)})); raise SystemExit(1)
