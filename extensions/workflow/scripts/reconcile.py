#!/usr/bin/env python3
"""Reconcile managed hook ownership. Dry-run default; restore only unchanged managed entries."""
import argparse
import copy
import json
from pathlib import Path

import yaml
from workflow import load_policy, require, write, read, WorkflowError, locked

OWNED = {'assure', 'user-manual', 'superspec', 'speckit-superpowers-bridge', 'project'}


def managed_hook(event, hook):
    """The one hook-ownership rule, for reconcile and doctor. check_docs.py evaluates the `managed` expression with
    only OWNED in scope, so keep it one assignment with inline literals."""
    managed = hook.get('extension') in OWNED or (hook.get('extension') == 'pr' and event == 'after_implement') or (hook.get('command') == 'speckit.scope.after-specify') or (hook.get('extension') == 'memory' and hook.get('command') in ('speckit.memory.session', 'speckit.memory.prepare'))
    return managed


def reconcile(root, apply=False, restore=False):
    with locked(root / '.specify/workflow/runtime/reconcile.lock'):
        return _reconcile(root, apply, restore)


def _reconcile(root, apply=False, restore=False):
    policy = load_policy(root)
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
            if not managed_hook(event, hook): continue
            before = copy.deepcopy(hook)
            record = journal['entries'].get(key)
            # Spec Kit's register_hooks (extension add/update) and Memory's installer write an owned hook back
            # enabled: a fresh registration, not an edit. A disabled entry that differs was edited after
            # reconcile and is refused. The entry holds no provenance, so a deliberate re-enable looks the same.
            fresh = bool(record) and hook != record['managed'] and hook.get('enabled', True) is not False
            if record and not fresh:
                require(hook == record['managed'], 'HOOK_CHANGED_SINCE_RECONCILE: ' + key)
            if restore:
                if record and not fresh:
                    hook.clear(); hook.update(record['original'])
                # A fresh registration is the extension's current entry: keep it; the journal goes below.
            else:
                if not record or fresh:
                    journal['entries'][key] = {'original': before}
                hook['enabled'] = False
                journal['entries'][key]['managed'] = copy.deepcopy(hook)
            if before != hook: changes.append({'hook': key, 'before': before, 'after': copy.deepcopy(hook)})
    if apply:
        if not restore: write(backup, journal)
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding='utf-8')
        if restore: backup.unlink(missing_ok=True)
    host_files = None
    if apply and not restore:
        from hosts import apply_host_files  # hidden hook-only skills, guard hook, role agents
        host_files = apply_host_files(root, policy)
    return {'applied': apply, 'restore': restore, 'changes': changes, 'host_files': host_files,
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
