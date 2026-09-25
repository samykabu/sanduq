#!/usr/bin/env python3
"""Policy, task metadata and skill discovery for opt-in workflow delegation."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import yaml

TYPES = ('discovery', 'implementation', 'qa', 'documentation', 'review', 'coordination')
DEFAULT_TIERS = {'discovery': 'high', 'implementation': 'standard', 'qa': 'light',
                 'documentation': 'documentation', 'review': 'review', 'coordination': 'light'}
MODEL_PROFILES = ('high', 'standard', 'light', 'documentation', 'review')
STAGE_TYPES = {
    'scope': 'discovery', 'specify': 'discovery', 'clarify': 'discovery',
    'plan': 'discovery', 'tasks': 'discovery', 'qa_analyze': 'qa',
    'manual_analyze': 'documentation', 'analyze': 'review',
    'taskstoissues': 'coordination', 'execute': 'coordination',
    'verify': 'qa', 'review': 'review', 'qa_document': 'qa',
    'manual_update': 'documentation', 'ready': 'coordination', 'pr': 'coordination',
}
TASK_LINE = re.compile(r'^(\s*- \[([ xX])\]\s+(T\d{3,})\b.*)$')
MARKER = re.compile(r'^\s*<!-- sanduq-delegation (\{[^\n]+\}) -->\s*$')
OVERRIDE_KEY = re.compile(r'^specs/[^/]+/T\d{3,}$')


class DelegationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DelegationError(message)


def validate_candidate(candidate):
    require(isinstance(candidate, dict) and
            set(candidate) in ({'harness', 'tier'}, {'harness', 'model'}),
            'DELEGATION_CANDIDATE_INVALID')
    require(candidate['harness'] in ('selected', 'codex', 'claude'), 'DELEGATION_HARNESS_INVALID')
    if 'tier' in candidate:
        require(candidate['tier'] in MODEL_PROFILES, 'DELEGATION_TIER_INVALID')
    else:
        require(candidate['model'] is None or
                isinstance(candidate['model'], str) and candidate['model'].strip(), 'DELEGATION_MODEL_INVALID')


def validate_route(route):
    require(isinstance(route, dict) and set(route) == {'preferred', 'fallbacks'},
            'DELEGATION_ROUTE_INVALID')
    validate_candidate(route['preferred'])
    require(isinstance(route['fallbacks'], list) and len(route['fallbacks']) <= 5,
            'DELEGATION_FALLBACKS_INVALID')
    for candidate in route['fallbacks']:
        validate_candidate(candidate)


def validate_delegation(config):
    require(isinstance(config, dict) and set(config) ==
            {'enabled', 'install_scope', 'stronger_retry', 'models', 'routes', 'overrides'},
            'DELEGATION_POLICY_INVALID')
    require(type(config['enabled']) is bool, 'DELEGATION_SELECTION_INVALID')
    require(config['install_scope'] in ('project', 'global'), 'DELEGATION_SCOPE_INVALID')
    require(type(config['stronger_retry']) is int and config['stronger_retry'] in (0, 1),
            'DELEGATION_RETRY_INVALID')
    models = config['models']
    require(isinstance(models, dict) and set(models) == {'codex', 'claude'},
            'DELEGATION_MODELS_INVALID')
    for harness in ('codex', 'claude'):
        require(isinstance(models[harness], dict) and
                set(models[harness]) == set(MODEL_PROFILES),
                'DELEGATION_MODELS_INVALID: ' + harness)
        require(all(isinstance(value, str) and value.strip() for value in models[harness].values()),
                'DELEGATION_MODEL_INVALID: ' + harness)
    routes = config['routes']
    require(isinstance(routes, dict) and set(routes) == set(TYPES), 'DELEGATION_ROUTES_INVALID')
    for route in routes.values():
        validate_route(route)
    require(isinstance(config['overrides'], dict), 'DELEGATION_OVERRIDES_INVALID')
    for key, route in config['overrides'].items():
        require(isinstance(key, str) and OVERRIDE_KEY.fullmatch(key),
                'DELEGATION_OVERRIDE_KEY_INVALID: ' + str(key))
        validate_route(route)
    return config


def task_type(description):
    """Classify explicit task markers before using conservative text cues."""
    value = description.casefold()
    if re.search(r'\[(?:qa|test|tdd)\]|\b(?:tests?|screenshots?|browser|evidence)\b', value):
        return 'qa'
    if re.search(r'\[(?:doc|manual)\]|\b(?:documentation|docs?|manual|readme|release notes)\b', value):
        return 'documentation'
    if re.search(r'\[review\]|\b(?:review|audit)\b', value):
        return 'review'
    return 'implementation'


def selected_route(config, work_type, selected_host, identity=None):
    validate_delegation(config)
    require(work_type in TYPES, 'DELEGATION_TASK_TYPE_INVALID')
    require(selected_host in ('codex', 'claude'), 'DELEGATION_SELECTED_HOST_INVALID')
    rule = 'default:' + work_type
    route = config['routes'][work_type]
    if identity and identity in config['overrides']:
        route = config['overrides'][identity]
        rule = 'override:' + identity
    elif route != {'preferred': {'harness': 'selected', 'tier': DEFAULT_TIERS[work_type]},
                   'fallbacks': [{'harness': 'selected', 'model': None}]}:
        rule = 'yaml:' + work_type
    candidates = []
    for index, item in enumerate((route['preferred'], *route['fallbacks'])):
        harness = selected_host if item['harness'] == 'selected' else item['harness']
        model = config['models'][harness][item['tier']] if 'tier' in item else item['model']
        candidates.append({'harness': harness, 'requested_model': model,
                           'tier': item.get('tier'), 'rule': rule,
                           'choice': 'preferred' if index == 0 else 'fallback:' + str(index)})
    return candidates


def stronger_candidate(config, prior, selected_host):
    """One escalation to a stronger configured tier, when one exists."""
    tier = prior.get('tier')
    stronger = {'light': 'standard', 'standard': 'high',
                'documentation': 'high', 'review': 'high'}.get(tier)
    if not stronger:
        return None
    harness = prior['harness'] if prior['harness'] in ('codex', 'claude') else selected_host
    if config['models'][harness][stronger] == prior['requested_model']:
        return None
    return {'harness': harness, 'requested_model': config['models'][harness][stronger],
            'tier': stronger, 'rule': 'stronger-retry:' + tier + '->' + stronger,
            'choice': 'reassignment'}


def read_policy(root):
    from workflow import load_policy
    return load_policy(root)


def active_host(root):
    from workflow import active_host as host
    return host(root)


def ledger_path(root, feature):
    path = (root / feature / 'workflow/delegations.json').resolve()
    require(path.is_relative_to(root.resolve() / 'specs') and
            path.parent.parent == (root / feature).resolve(), 'DELEGATION_FEATURE_INVALID')
    return path


def active_task_ids(root, feature):
    path = ledger_path(root, feature)
    active = set()
    if path.exists():
        ledger = json.loads(path.read_text(encoding='utf-8'))
        active.update(attempt['identity'].rsplit('/', 1)[-1]
                      for attempt in ledger.get('attempts', [])
                      if attempt.get('status') in ('starting', 'running'))
    progress = root / feature / 'workflow/progress/state.json'
    if progress.is_file():
        state = json.loads(progress.read_text(encoding='utf-8'))
        active.update(task['id'] for task in state.get('tasks', [])
                      if task.get('status') == 'running')
    return active


def annotate_tasks(root, feature, config, selected_host=None):
    """Refresh pending task metadata without changing checkbox lines or active work."""
    validate_delegation(config)
    if not config['enabled']:
        return {'changed': False, 'annotated': 0, 'disabled': True}
    selected_host = selected_host or active_host(root)
    path = (root / feature / 'tasks.md').resolve()
    require(path.is_relative_to(root.resolve() / 'specs'), 'DELEGATION_FEATURE_INVALID')
    if not path.is_file():
        return {'changed': False, 'annotated': 0, 'missing_tasks': True}
    raw = path.read_bytes()
    bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
    lines = raw.decode('utf-8-sig').splitlines(keepends=True)
    running = active_task_ids(root, feature)
    output = []
    annotated = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        match = TASK_LINE.match(line.rstrip('\r\n'))
        output.append(line)
        index += 1
        if not match:
            continue
        old_marker = lines[index] if index < len(lines) and MARKER.match(lines[index].rstrip('\r\n')) else None
        if old_marker is not None:
            index += 1
        task_id = match[3]
        if match[2].lower() == 'x' or task_id in running:
            if old_marker is not None:
                output.append(old_marker)
            continue
        work_type = task_type(match[1])
        route = selected_route(config, work_type, selected_host, feature + '/' + task_id)[0]
        metadata = {'task_id': task_id, 'task_type': work_type,
                    'preferred_harness': route['harness'],
                    'preferred_model': route['requested_model'], 'rule': route['rule']}
        newline = '\r\n' if line.endswith('\r\n') else '\n'
        output.append('  <!-- sanduq-delegation ' + json.dumps(metadata, sort_keys=True) + ' -->' + newline)
        annotated += 1
    content = ''.join(output)
    original = ''.join(lines)
    if content != original:
        temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        temp.write_bytes(bom + content.encode('utf-8'))
        os.replace(temp, path)
    return {'changed': content != original, 'annotated': annotated, 'running_unchanged': sorted(running)}


def local_skill_paths(root, host):
    agent = '.agents' if host == 'codex' else '.claude'
    return [root / agent / 'skills/delegate-task',
            global_root() / agent / 'skills/delegate-task',
            global_root() / ('.codex' if host == 'codex' else '.claude') / 'skills/delegate-task']


def global_root():
    return Path.home()


def inspect_skill(root, host):
    override = os.environ.get('SANDUQ_DELEGATE_DRIVER')
    candidates = ([Path(override).parent] if override else []) + local_skill_paths(root, host)
    plugin = os.environ.get('CLAUDE_PLUGIN_ROOT')
    if plugin:
        candidates.append(Path(plugin) / 'skills/delegate-task')
    broken = []
    for folder in dict.fromkeys(candidates):
        if not folder.exists():
            continue
        driver = folder / 'delegate.mjs'
        skill = folder / 'SKILL.md'
        contract = folder / 'contracts/result-schema-v2.md'
        if driver.is_file() and skill.is_file() and contract.is_file():
            node = shutil.which('node')
            if node and subprocess.run([node, '--check', str(driver)],
                                       capture_output=True).returncode:
                broken.append(str(folder))
                continue
            return {'ok': True, 'driver': str(driver.resolve()), 'scope': 'project' if folder.is_relative_to(root) else 'global'}
        broken.append(str(folder))
    return {'ok': False, 'error': 'DELEGATE_SKILL_BROKEN' if broken else 'DELEGATE_SKILL_MISSING',
            'broken': broken}


def bundled_skill():
    folder = Path(__file__).resolve().parents[1] / 'assets/delegate-task'
    if folder.is_dir():
        return folder
    # Canonical source checkout: packaged releases carry the asset instead.
    source = Path(__file__).resolve().parents[3] / 'skills/agent-tools/skills/delegate-task'
    return source if source.is_dir() else None


def install_skill(root, host, scope, force_scope=False):
    require(scope in ('project', 'global'), 'DELEGATION_SCOPE_INVALID')
    agent = '.agents' if host == 'codex' else '.claude'
    target_root = root if scope == 'project' else global_root()
    target = target_root / agent / 'skills/delegate-task'
    existing = inspect_skill(root, host)
    if (existing['ok'] and not force_scope and
            Path(existing['driver']).resolve() == (target / 'delegate.mjs').resolve()):
        return {**existing, 'installed': False}
    source = bundled_skill()
    require(source is not None and (source / 'delegate.mjs').is_file() and
            (source / 'SKILL.md').is_file() and
            (source / 'contracts/result-schema-v2.md').is_file(),
            'DELEGATE_SKILL_PACKAGE_MISSING')
    target.parent.mkdir(parents=True, exist_ok=True)
    require(target.parent.resolve().is_relative_to(target_root.resolve()),
            'DELEGATE_SKILL_TARGET_OUTSIDE_SCOPE')
    backup = None
    if target.exists() or target.is_symlink():
        backup = target.with_name('delegate-task.sanduq-backup-' + uuid.uuid4().hex)
        target.rename(backup)
    try:
        shutil.copytree(source, target, ignore=shutil.ignore_patterns('test', 'runs', 'node_modules'))
        require((target / 'SKILL.md').is_file() and (target / 'delegate.mjs').is_file() and
                (target / 'contracts/result-schema-v2.md').is_file(),
                'DELEGATE_SKILL_INSTALL_FAILED')
    except Exception:
        if target.is_symlink():
            target.unlink()
        elif target.exists():
            require(target.resolve().is_relative_to(target_root.resolve()),
                    'DELEGATE_SKILL_ROLLBACK_OUTSIDE_SCOPE')
            shutil.rmtree(target)
        if backup is not None:
            backup.rename(target)
        raise
    return {'ok': True, 'driver': str((target / 'delegate.mjs').resolve()),
            'scope': scope, 'installed': True, 'backup': str(backup) if backup else None}


def doctor(root, host, install=False, scope='project'):
    node = shutil.which('node')
    if not node:
        return {'ok': False, 'error': 'NODE_MISSING'}
    probe = subprocess.run([node, '--version'], capture_output=True, text=True)
    version = re.search(r'v?(\d+)', probe.stdout)
    if probe.returncode or not version or int(version[1]) < 18:
        return {'ok': False, 'error': 'NODE_18_REQUIRED'}
    status = install_skill(root, host, scope) if install else inspect_skill(root, host)
    if not status['ok']:
        return status
    result = subprocess.run([node, status['driver'], 'doctor'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8')
    if result.returncode and install:
        status = install_skill(root, host, scope, force_scope=True)
        result = subprocess.run([node, status['driver'], 'doctor'], cwd=root,
                                capture_output=True, text=True, encoding='utf-8')
    if result.returncode:
        return {**status, 'ok': False, 'error': 'DELEGATE_SKILL_DOCTOR_FAILED',
                'diagnostic': result.stderr.strip() or result.stdout.strip()}
    available = {}
    cli_errors = {}
    for harness in ('codex', 'claude'):
        line = next((line for line in result.stdout.splitlines()
                     if re.match(r'^' + harness + r'\s', line)), '')
        if not line or 'NOT FOUND on PATH' in line:
            cli_errors[harness] = 'AGENT_CLI_MISSING'
        elif 'UNDECODABLE SHIM' in line or 'BROKEN:' in line:
            cli_errors[harness] = 'AGENT_CLI_BROKEN'
        available[harness] = harness not in cli_errors
    return {**status, 'node': probe.stdout.strip(), 'harnesses': available,
            'cli_errors': cli_errors, 'diagnostic': result.stdout.strip()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('doctor', 'install', 'annotate', 'route'):
        command = sub.add_parser(action)
        if action in ('annotate', 'route'):
            command.add_argument('--feature', required=True)
        if action == 'route':
            command.add_argument('--id', required=True)
            command.add_argument('--type', choices=TYPES, required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        policy = read_policy(root)
        config = policy['delegation']
        host = active_host(root)
        if args.action in ('doctor', 'install'):
            result = doctor(root, host, args.action == 'install', config['install_scope'])
        elif args.action == 'annotate':
            result = annotate_tasks(root, args.feature, config, host)
        else:
            identity = args.feature + '/' + args.id
            result = {'enabled': config['enabled'], 'identity': identity, 'type': args.type,
                      'candidates': selected_route(config, args.type, host, identity) if config['enabled'] else []}
        print(json.dumps(result, indent=2))
        return 0 if result.get('ok', True) else 1
    except (DelegationError, OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
