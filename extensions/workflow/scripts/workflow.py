#!/usr/bin/env python3
"""Sanduq workflow state machine. Commands dispatch agents; this runtime never simulates them."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import yaml
from packaging.specifiers import SpecifierSet
from packaging.version import Version

SCHEMA = 1
RANGES = {'scope': '>=1.4,<2', 'assure': '>=2.1,<3', 'user-manual': '>=1.1,<2',
          'pr': '>=4.1,<5', 'superspec': '>=1.0.2,<2', 'project': '>=2.1,<3'}
BASE_STAGES = ['scope', 'specify', 'clarify', 'plan', 'tasks', 'qa_analyze',
               'manual_analyze', 'analyze', 'taskstoissues', 'execute', 'verify',
               'review', 'qa_document', 'manual_update', 'ready', 'pr']
COMMANDS = {'scope': 'speckit.scope.run', 'specify': 'speckit.specify',
            'clarify': 'speckit.clarify', 'plan': 'speckit.plan', 'tasks': 'speckit.tasks',
            'qa_analyze': 'speckit.assure.analyze', 'manual_analyze': 'speckit.user-manual.analyze',
            'analyze': 'speckit.analyze', 'taskstoissues': 'speckit.taskstoissues',
            'execute': 'speckit.implement', 'qa_document': 'speckit.assure.document',
            'manual_update': 'speckit.user-manual.update', 'pr': 'speckit.pr.generate',
            'verify': 'workflow:verification', 'review': 'workflow:review', 'ready': 'workflow:gates'}
CORE_INPUTS = ['spec.md', 'plan.md', 'tasks.md', 'data-model.md', 'research.md', 'quickstart.md']


class WorkflowError(Exception):
    pass


def require(value, message):
    if not value:
        raise WorkflowError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temp, path)


def inside(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), 'PATH_OUTSIDE_PROJECT: ' + str(relative))
    return path


def git(root, *args):
    result = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, encoding='utf-8')
    require(result.returncode == 0, 'GIT_ERROR: ' + result.stderr.strip())
    return result.stdout.strip()


def github_repository(root):
    remote = git(root, 'config', '--get', 'remote.origin.url')
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?/?', remote)
    require(match, 'GITHUB_REMOTE_REQUIRED')
    return match[1]


def default_policy(qa, manual):
    require(type(qa) is bool and type(manual) is bool, 'Select QA and User Manual explicitly.')
    return {'schema_version': SCHEMA, 'processes': {'qa': qa, 'user_manual': manual},
            'execution': {'engine': 'auto', 'checkpoints': 'required-only'},
            'providers': {'clarification': 'prefer-superspec', 'tasks': 'prefer-superspec'},
            'issue_sync': {'taskstoissues': 'required', 'parent_link': 'native-subissue'},
            'clarification': {'transport': 'github-comments', 'resume_on_reinvoke': 'reread-answers'},
            'context': {'mode': 'measured-only', 'max_fraction': .60,
                        'checkpoint_fraction': .50, 'reserve_fraction': .10},
            'finalize': {'create_pr': True, 'merge': False}, 'updates': {'policy': 'reviewed'}}


def validate_policy(policy):
    require(isinstance(policy, dict) and policy.get('schema_version') == SCHEMA, 'POLICY_SCHEMA_UNSUPPORTED')
    for section in ('processes','execution','providers','issue_sync','clarification','context','finalize','updates'):
        require(isinstance(policy.get(section), dict), 'POLICY_SECTION_INVALID: ' + section)
    for key in ('qa', 'user_manual'):
        require(type(policy.get('processes', {}).get(key)) is bool, 'POLICY_SELECTION_REQUIRED: ' + key)
    require(policy.get('execution', {}).get('engine') in ('auto', 'speckit', 'superspec'), 'EXECUTOR_UNSUPPORTED')
    require(policy.get('execution', {}).get('checkpoints') in ('required-only', 'every-phase'), 'CHECKPOINT_POLICY_INVALID')
    for key in ('clarification', 'tasks'):
        require(policy.get('providers', {}).get(key) in ('prefer-superspec', 'core', 'superspec'), 'PROVIDER_POLICY_INVALID: ' + key)
    context = policy.get('context', {})
    require(context.get('mode') in ('strict', 'measured-only', 'measured-with-estimated-fallback'), 'CONTEXT_MODE_INVALID')
    cap, checkpoint, reserve = (context.get(k) for k in ('max_fraction', 'checkpoint_fraction', 'reserve_fraction'))
    require(all(type(v) in (int, float) for v in (cap, checkpoint, reserve)), 'CONTEXT_LIMIT_INVALID')
    require(0 < checkpoint < cap <= .60 and 0 < reserve < cap, 'CONTEXT_LIMIT_INVALID')
    require(policy.get('issue_sync') == {'taskstoissues': 'required', 'parent_link': 'native-subissue'}, 'TASK_ISSUES_REQUIRED')
    require(policy.get('finalize') == {'create_pr': True, 'merge': False}, 'FINALIZE_POLICY_INVALID')
    require(policy.get('clarification', {}).get('resume_on_reinvoke') in ('reread-answers', 'manual-status'), 'CLARIFICATION_POLICY_INVALID')
    scope = policy.get('scope', {})
    require(isinstance(scope, dict), 'POLICY_SECTION_INVALID: scope')
    status_names = scope.get('statuses', {})
    require(isinstance(status_names, dict) and all(isinstance(k, str) and isinstance(v, str) and v for k, v in status_names.items())
            and len(set(status_names.values())) == len(status_names), 'SCOPE_STATUS_MAPPING_INVALID')
    band = scope.get('keep_together')
    if band:
        require(isinstance(band, dict), 'SCOPE_BAND_INVALID')
        require(type(band.get('target')) in (int, float) and type(band.get('tolerance')) in (int, float), 'SCOPE_BAND_INVALID')
        require(band['target'] >= 0 and band['tolerance'] >= 0 and bool(band.get('unit')), 'SCOPE_UNIT_REQUIRED')
        require(band.get('inclusive') is True, 'SCOPE_BAND_MUST_BE_INCLUSIVE')
    return policy


def load_policy(root):
    path = root / '.specify/workflow.yml'
    require(path.is_file(), 'WORKFLOW_INIT_REQUIRED')
    return validate_policy(yaml.safe_load(path.read_text(encoding='utf-8-sig')))


def scope_decision(policy, estimate, unit):
    band = policy.get('scope', {}).get('keep_together')
    if not band:
        return {'decision': 'needs-assessment', 'reason': 'No project keep-together preference'}
    require(unit == band['unit'], 'SCOPE_UNIT_MISMATCH')
    require(type(estimate) in (int, float) and estimate >= 0, 'SCOPE_ESTIMATE_INVALID')
    keep = band['target'] - band['tolerance'] <= estimate <= band['target'] + band['tolerance']
    return {'decision': 'keep-together' if keep else 'needs-assessment', 'automatic': keep,
            'estimate': estimate, 'unit': unit, 'policy_digest': digest(band)}


def stages(policy):
    return [s for s in BASE_STAGES if not (s.startswith('qa_') and not policy['processes']['qa'])
            and not (s.startswith('manual_') and not policy['processes']['user_manual'])]


def policy_cutoff(previous, current):
    if not previous: return 0
    affected = []
    for key, stage in {'scope':'scope','clarification':'clarify','providers':'clarify',
                       'processes':'tasks','issue_sync':'taskstoissues','execution':'execute',
                       'finalize':'ready'}.items():
        if previous.get(key) != current.get(key): affected.append(BASE_STAGES.index(stage))
    # Context and update scheduling do not retroactively invalidate semantic work.
    return min(affected, default=len(BASE_STAGES))


def registry(root):
    return read(root / '.specify/extensions/.registry', {}).get('extensions', {})


def compatible(root, name):
    entry = registry(root).get(name, {})
    try:
        return entry.get('enabled') is True and Version(entry['version']) in SpecifierSet(RANGES[name])
    except (KeyError, ValueError):
        return False


def active_host(root):
    integration = read(root / '.specify/integration.json', {})
    options = read(root / '.specify/init-options.json', {})
    return integration.get('default_integration') or integration.get('integration') or options.get('integration') or options.get('ai')


def command_exists(root, command):
    name = command.replace('.', '-')
    host = active_host(root)
    if host == 'codex': return (root / '.agents/skills' / name / 'SKILL.md').is_file()
    if host == 'claude': return (root / '.claude/skills' / name / 'SKILL.md').is_file()
    return False


def package_digest(root):
    """Ignore install timestamps but detect versions, enablement and source drift."""
    entries = {key: {k: value.get(k) for k in ('version', 'enabled')} for key, value in registry(root).items()}
    paths = []
    for folder in (root / '.specify/extensions', root / '.specify/presets'):
        if folder.is_dir():
            paths += [p.relative_to(root).as_posix() for p in folder.rglob('*') if p.is_file()
                      and p.suffix in ('.py', '.md', '.yml')
                      and not any(part in ('state', '__pycache__', 'tests') for part in p.relative_to(folder).parts)]
    paths += [p.relative_to(root).as_posix() for p in (root / '.agents/skills').glob('speckit-*/SKILL.md')]
    paths += [p.relative_to(root).as_posix() for p in (root / '.claude/skills').glob('speckit-*/SKILL.md')]
    paths += ['.specify/integration.json', '.specify/init-options.json']
    return digest({'registrations': entries, 'sources': fingerprint_files(root, paths)})


def resolve_commands(root, policy):
    commands = dict(COMMANDS)
    for stage, suffix, choice in [('clarify', 'brainstorm', policy['providers']['clarification']),
                                  ('tasks', 'tasks', policy['providers']['tasks']),
                                  ('execute', 'execute', policy['execution']['engine'])]:
        candidate = 'speckit.superspec.' + suffix
        available = compatible(root, 'superspec') and command_exists(root, candidate)
        if choice == 'superspec':
            require(available, 'REQUIRED_PROVIDER_UNAVAILABLE: ' + candidate)
        if available and choice not in ('core', 'speckit'):
            commands[stage] = candidate
    if compatible(root, 'superspec') and command_exists(root, 'speckit.superspec.review'):
        commands['review'] = 'speckit.superspec.review'
    return commands


def project_errors(root, policy):
    config = read(root / '.specify/extensions/project/config.json', {})
    if not isinstance(config, dict): return ['PROJECT_CONFIG_INVALID: expected a JSON object']
    errors = []
    for key in ('owner', 'projectId', 'statusFieldId', 'stateFile'):
        if not isinstance(config.get(key), str) or not config[key]: errors.append('PROJECT_CONFIG_REQUIRED: ' + key)
    if type(config.get('projectNumber')) is not int or config['projectNumber'] < 1: errors.append('PROJECT_CONFIG_REQUIRED: projectNumber')
    if config.get('hookMode') != 'required': errors.append('PROJECT_SYNC_MUST_BE_REQUIRED: managed workflow updates the board automatically')
    options, phases = config.get('statusOptions', {}), config.get('phaseToStatus', {})
    if not isinstance(options, dict) or not options or not all(isinstance(v, str) and v for v in options.values()):
        errors.append('PROJECT_STATUS_OPTIONS_REQUIRED'); options = {}
    if not isinstance(phases, dict): phases = {}
    logical = ('Backlog', 'Feature Specification', 'Need Clarifications', 'Ready', 'In progress', 'In review', 'Done')
    mapping = policy.get('scope', {}).get('statuses', {})
    for status in logical:
        if mapping.get(status, status) not in options: errors.append('PROJECT_SCOPE_STATUS_MISSING: ' + mapping.get(status, status))
    for phase in ('open', 'analysis', 'engineer-review', 'ready', 'in-progress', 'in-review', 'done'):
        if phases.get(phase) not in options: errors.append('PROJECT_PHASE_UNMAPPED: ' + phase)
    if config.get('stateFile'):
        try: inside(root, config['stateFile'])
        except (WorkflowError, TypeError): errors.append('PROJECT_STATE_PATH_INVALID')
    return errors


def project_defaults(root, policy):
    mapping = policy.get('scope', {}).get('statuses', {})
    phases = {'open': 'Feature Specification', 'analysis': 'Ready', 'engineer-review': 'Ready',
              'ready': 'Ready', 'in-progress': 'In progress', 'in-review': 'In review', 'done': 'Done'}
    phases = {phase: mapping.get(status, status) for phase, status in phases.items()}
    existing = read(root / '.specify/extensions/project/config.json', {})
    require(isinstance(existing, dict), 'PROJECT_CONFIG_INVALID: expected a JSON object')
    if existing.get('projectId') and isinstance(existing.get('phaseToStatus'), dict):
        phases.update({phase: status for phase, status in existing['phaseToStatus'].items() if phase in phases and isinstance(status, str) and status})
    return {'phaseToStatus': phases, 'source': 'managed policy with preserved configured phase choices'}


def doctor(root, policy, project=False):
    needed = ['scope', 'project', 'pr'] + (['assure'] if policy['processes']['qa'] else []) + (['user-manual'] if policy['processes']['user_manual'] else [])
    errors = ['DEPENDENCY_UNAVAILABLE: ' + name + ' ' + RANGES[name] for name in needed if not compatible(root, name)]
    if active_host(root) not in ('codex','claude'):
        errors.append('HOST_UNSUPPORTED: this release supports Codex and Claude skills mode')
    bridge = read(root / '.specify/superpowers-handoff.json', {})
    if bridge.get('status') in ('executing', 'blocked'):
        errors.append('LEGACY_EXECUTOR_OWNS_FEATURE: reconcile the recorded bridge handoff before managed execution')
    agent = '.agents' if active_host(root) == 'codex' else '.claude'
    alias = root / agent / 'skills/speckit-superpowers-bridge/SKILL.md'
    if alias.is_file() and '<!-- sanduq-workflow-alias:v1 -->' not in alias.read_text(encoding='utf-8-sig'):
        errors.append('LEGACY_ALIAS_RECONCILIATION_REQUIRED: run the workflow installer; do not patch the upstream command')
    for name in needed:
        manifest = root / '.specify/extensions' / name / 'extension.yml'
        doc = yaml.safe_load(manifest.read_text(encoding='utf-8-sig')) if manifest.exists() else {}
        if (doc or {}).get('extension', {}).get('repository', '').rstrip('/') != 'https://github.com/samykabu/sanduq':
            errors.append('DEPENDENCY_SOURCE_MISMATCH: ' + name + ' must come from samykabu/sanduq')
    try:
        commands = resolve_commands(root, policy)
        errors += ['COMMAND_UNAVAILABLE: ' + commands[s] for s in stages(policy)
                   if not commands[s].startswith('workflow:') and not command_exists(root, commands[s])]
    except WorkflowError as exc:
        errors.append(str(exc))
    hooks_path = root / '.specify/extensions.yml'
    if not hooks_path.exists():
        errors.append('HOOK_RECONCILIATION_REQUIRED')
    else:
        hooks = yaml.safe_load(hooks_path.read_text(encoding='utf-8-sig')) or {}
        require(isinstance(hooks, dict) and isinstance(hooks.get('hooks'), dict), 'HOOK_CONFIG_INVALID')
        for event, items in hooks.get('hooks', {}).items():
            require(isinstance(items, list) and all(isinstance(item, dict) for item in items), 'HOOK_LIST_INVALID: ' + event)
            for hook in items:
                owned = hook.get('extension') in ('assure', 'user-manual', 'superspec', 'speckit-superpowers-bridge', 'project') or hook.get('command') == 'speckit.scope.after-specify' or (hook.get('extension') == 'pr' and event == 'after_implement')
                if owned and hook.get('enabled', True): errors.append('DUPLICATE_STAGE_OWNER: ' + event + ':' + hook.get('command', ''))
    preset_registry = read(root / '.specify/presets/.registry', {}).get('presets', {})
    for preset in ('workflow', 'scope-gate', 'scope-brainstorm'):
        if not (root / '.specify/presets' / preset / 'preset.yml').is_file():
            errors.append('PRESET_REQUIRED: ' + preset)
        if preset_registry.get(preset, {}).get('enabled') is not True:
            errors.append('PRESET_NOT_ENABLED: ' + preset)
    if project: errors += project_errors(root, policy)
    return {'ok': not errors, 'errors': errors, 'project_checked': project,
            'context': 'Only fresh reliable measurements can trigger context pauses; unavailable or estimated usage is nonblocking outside explicit strict mode'}


def context_gate(policy, usage):
    require(isinstance(usage, dict) and usage.get('session_id'), 'CONTEXT_USAGE_REQUIRED')
    try:
        return measured_context_gate(policy, usage)
    except WorkflowError as exc:
        if policy['context']['mode'] == 'strict':
            raise
        return {'pause': False, 'method': 'unavailable', 'guaranteed': False,
                'session_id': usage['session_id'], 'reason': 'context-monitoring-unavailable: ' + str(exc)}


def measured_context_gate(policy, usage):
    require(usage.get('method') in ('measured', 'estimated'), 'CONTEXT_METHOD_REQUIRED')
    require(usage.get('method') == 'measured' and usage.get('reliable', True) is True,
            'CONTEXT_LIMIT_UNENFORCEABLE: reliable host measurement unavailable')
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(usage['observed_at'])).total_seconds()
    except (KeyError, ValueError, TypeError):
        raise WorkflowError('CONTEXT_TIMESTAMP_INVALID')
    require(0 <= age <= 120, 'CONTEXT_TELEMETRY_STALE')
    measured = usage['method'] == 'measured'
    require(policy['context']['mode'] != 'strict' or (measured and usage.get('pre_call_bound') is True), 'CONTEXT_LIMIT_UNENFORCEABLE')
    fraction, next_fraction = usage.get('fraction'), usage.get('next_fraction')
    require(all(type(n) in (float, int) and 0 <= n <= 1 for n in (fraction, next_fraction)), 'CONTEXT_FRACTION_INVALID')
    reserve = policy['context']['reserve_fraction']
    pause = fraction >= policy['context']['checkpoint_fraction'] or fraction + next_fraction + reserve >= policy['context']['max_fraction']
    return {'pause': pause, 'method': usage['method'], 'guaranteed': measured and usage.get('pre_call_bound') is True,
            'fraction': fraction, 'session_id': usage['session_id'], 'reason': 'checkpoint-required' if pause else 'within-budget'}


def fingerprint_files(root, paths):
    result = {}
    for relative in sorted(set(paths)):
        path = inside(root, relative)
        if path.is_file():
            content = path.read_bytes()
            if path.suffix.lower() in ('.md', '.txt', '.json', '.yml', '.yaml', '.py', '.ts', '.js', '.tsx', '.cs', '.html', '.css'):
                content = content.replace(b'\r\n', b'\n')
            # Checkbox bookkeeping must not invalidate task publication or planning.
            if path.name == 'tasks.md':
                content = re.sub(rb'(?m)^(\s*- )\[[ xX]\]', rb'\1[ ]', content)
            result[relative] = hashlib.sha256(content).hexdigest()
        else:
            result[relative] = None
    return result


def required_inputs(root, feature, stage):
    """Minimum artifact coverage is enforced even if an agent omits a path."""
    index = BASE_STAGES.index(stage)
    paths = []
    if index >= BASE_STAGES.index('specify'):
        paths += [feature + '/spec.md', feature + '/scope-source.json']
    if index >= BASE_STAGES.index('plan'):
        paths += [feature + '/plan.md']
    if index >= BASE_STAGES.index('tasks'):
        paths += [feature + '/tasks.md']
    if index >= BASE_STAGES.index('taskstoissues'):
        paths += [feature + '/workflow/task-issues.json']
    constitution = '.specify/memory/constitution.md'
    if (root / constitution).is_file(): paths.append(constitution)
    if index >= BASE_STAGES.index('plan'):
        for name in ('research.md', 'data-model.md', 'quickstart.md'):
            if (root / feature / name).is_file(): paths.append(feature + '/' + name)
        contracts = root / feature / 'contracts'
        if contracts.is_dir():
            paths += [p.relative_to(root).as_posix() for p in contracts.rglob('*') if p.is_file()]
    return sorted(set(paths))


def source_fingerprints(root):
    """Inventory code and build inputs, including additions and deletion tombstones."""
    paths = git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0')
    excluded = {'.git', 'node_modules', '__pycache__', 'dist', 'build', 'coverage', 'obj'}
    operational = {'.specify', '.agents', '.claude', '.codex', 'specs', 'User-Manual', 'docs', 'graphify-out', 'keys_cert'}
    selected = []
    for path in filter(None, paths):
        parts = Path(path).parts
        if parts[0] in operational or any(p in excluded for p in parts): continue
        if Path(path).name.startswith('.env') or Path(path).suffix.lower() in ('.pem', '.key', '.p12', '.pfx'): continue
        selected.append(path)
    return fingerprint_files(root, selected)


def receipt_current(root, feature, stage, receipt):
    saved = receipt.get('fingerprints', {})
    if not saved or not set(required_inputs(root, feature, stage)) <= set(saved): return False
    if fingerprint_files(root, saved) != saved: return False
    if stage in ('verify', 'review', 'ready'):
        return receipt.get('source_fingerprints') == source_fingerprints(root)
    return True


def ensure_local_excludes(root):
    """Keep runtime/backup files local, including preserved consumer credentials."""
    value = git(root, 'rev-parse', '--git-path', 'info/exclude')
    path = Path(value)
    if not path.is_absolute(): path = root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.read_text(encoding='utf-8') if path.exists() else ''
    patterns = ('/.specify/workflow/backups/', '/.specify/workflow/runtime/',
                '/.specify/workflow/install-receipt.json', '/specs/*/workflow/backups/')
    missing = [pattern for pattern in patterns if pattern not in current.splitlines()]
    if missing:
        path.write_text(current.rstrip('\n') + '\n# Sanduq local backups and runtime\n' + '\n'.join(missing) + '\n', encoding='utf-8')


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise WorkflowError('WORKFLOW_BUSY: inspect owner before removing ' + str(path))
    try:
        os.write(fd, json.dumps({'pid': os.getpid(), 'created': now()}).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


class Run:
    def __init__(self, root, feature):
        self.root = root.resolve()
        self.feature = inside(self.root, feature)
        require(self.feature.is_relative_to(self.root / 'specs') and self.feature != self.root / 'specs', 'FEATURE_PATH_INVALID')
        self.relative = self.feature.relative_to(self.root).as_posix()
        self.path = self.feature / 'workflow/checkpoint.json'
        self.lock = self.root / '.specify/workflow/runtime' / (digest(self.relative) + '.lock')
        self.policy = load_policy(self.root)

    def load(self, allow_branch_change=False):
        state = read(self.path)
        require(state and state.get('schema_version') == SCHEMA, 'WORKFLOW_START_REQUIRED')
        require(state['repo_path'] == str(self.root) and state['feature'] == self.relative, 'CHECKPOINT_IDENTITY_MISMATCH')
        require(allow_branch_change or state['branch'] == git(self.root, 'branch', '--show-current'), 'CHECKPOINT_BRANCH_MISMATCH')
        return state

    def bind(self, token):
        with locked(self.lock):
            state = self.load(allow_branch_change=True)
            require(state['active'] and state['active']['stage'] == 'specify' and state['active']['token'] == token, 'SPECIFY_CLAIM_REQUIRED')
            source = read(self.feature / 'scope-source.json', {})
            require(f"{source.get('repo')}#{source.get('issue')}" == state['issue'], 'FEATURE_BINDING_MISMATCH')
            require((self.feature / 'spec.md').is_file(), 'SPECIFICATION_MISSING')
            branch = git(self.root, 'branch', '--show-current')
            require(branch, 'DETACHED_HEAD_UNSUPPORTED')
            state.setdefault('branch_history', []).append({'from': state['branch'], 'to': branch, 'at': now()})
            state['branch'] = branch
            self.save(state)
            return {'bound': True, 'branch': branch, 'feature': self.relative}

    def migrate(self, reason, invalidate_from=None):
        """Preserve immutable historical evidence; invalidate changed command contracts."""
        with locked(self.lock):
            state = self.load()
            require(not state['active'], 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_UPGRADE')
            health = doctor(self.root, self.policy)
            require(health['ok'], '; '.join(health['errors']))
            ensure_local_excludes(self.root)
            write(self.path.parent / 'backups' / (uuid.uuid4().hex + '.json'), state)
            old_digest = state['dependency_digest']
            commands = resolve_commands(self.root, self.policy)
            changed = [stage for stage in stages(self.policy) if state['commands'].get(stage) != commands[stage]]
            if invalidate_from:
                require(invalidate_from in BASE_STAGES, 'INVALID_MIGRATION_STAGE')
                changed.append(invalidate_from)
            cutoff = min((BASE_STAGES.index(stage) for stage in changed), default=len(BASE_STAGES))
            invalidated = [stage for stage in state['receipts'] if BASE_STAGES.index(stage) >= cutoff]
            state.setdefault('migrations', []).append({'reason': reason, 'from': old_digest, 'at': now(),
                                                      'invalidated': invalidated, 'preserved_as_historical': [s for s in state['receipts'] if s not in invalidated]})
            state['dependency_digest'] = package_digest(self.root)
            state['commands'] = commands
            for stage in invalidated: state['receipts'].pop(stage)
            self.save(state)
            return {'migrated': True, 'next': self.next(state)}

    def refresh(self, stage, reason):
        """Explicit invocation rereads remote requirements even when local files are unchanged."""
        require(stage in ('scope', 'clarify'), 'REFRESH_STAGE_UNSUPPORTED')
        with locked(self.lock):
            state = self.load()
            require(not state['active'], 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_REFRESH')
            require(reason.strip(), 'REFRESH_REASON_REQUIRED')
            cutoff = BASE_STAGES.index(stage)
            affected = {name: receipt for name, receipt in state['receipts'].items() if BASE_STAGES.index(name) >= cutoff}
            if affected:
                ensure_local_excludes(self.root)
                backup = self.path.parent / 'backups' / (uuid.uuid4().hex + '.json')
                write(backup, state)
                state.setdefault('refreshes', []).append({'stage': stage, 'reason': reason, 'at': now(),
                                                         'invalidated': list(affected), 'backup': str(backup.relative_to(self.root))})
                for name in affected: state['receipts'].pop(name)
                self.save(state)
            return {'refreshed': list(affected), 'next': self.next(state)}

    def start(self, issue):
        require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9]\d*', issue), 'EXPLICIT_ISSUE_REQUIRED')
        require(github_repository(self.root) == issue.split('#')[0], 'ISSUE_REPOSITORY_MISMATCH')
        source = read(self.feature / 'scope-source.json', {})
        require(not source or f"{source.get('repo')}#{source.get('issue')}" == issue, 'FEATURE_BINDING_MISMATCH')
        with locked(self.lock):
            if self.path.exists():
                state = self.load()
                require(state['issue'] == issue, 'ISSUE_BINDING_CONFLICT')
                return state
            commands = resolve_commands(self.root, self.policy)
            state = {'schema_version': SCHEMA, 'run_id': uuid.uuid4().hex, 'repo_path': str(self.root),
                     'branch': git(self.root, 'branch', '--show-current'), 'feature': self.relative,
                     'issue': issue, 'policy_digest': digest(self.policy), 'commands': commands,
                     'policy': copy.deepcopy(self.policy),
                     'receipts': {}, 'generation': 0, 'active': None, 'status': 'in-progress'}
            state['dependency_digest'] = package_digest(self.root)
            self.save(state)
            return state

    def save(self, state):
        state['generation'] += 1
        state['updated_at'] = now()
        state['head'] = git(self.root, 'rev-parse', 'HEAD')
        write(self.path, state)

    def next(self, state, finalize=False):
        policy_changed = state['policy_digest'] != digest(self.policy)
        cutoff = policy_cutoff(state.get('policy'), self.policy) if policy_changed else len(BASE_STAGES)
        for stage in stages(self.policy):
            receipt = state['receipts'].get(stage)
            if receipt and BASE_STAGES.index(stage) >= cutoff:
                return {'stage':stage,'command':state['commands'][stage],'reason':'policy-changed'}
            if receipt:
                if receipt_current(self.root, self.relative, stage, receipt):
                    continue
                return {'stage': stage, 'reason': 'inputs-or-evidence-changed'}
            if stage == 'pr' and not finalize:
                return {'stage': None, 'status': 'ready_to_finalize', 'command': 'speckit.workflow.finalize'}
            return {'stage': stage, 'command': state['commands'][stage], 'reason': 'pending'}
        return {'stage': None, 'status': 'pr_open'}

    def claim(self, usage, finalize=False):
        with locked(self.root / '.specify/workflow/runtime/dispatch.lock'), locked(self.lock):
            require(not (self.root / '.specify/workflow/runtime/upgrade.lock').exists(), 'WORKFLOW_UPGRADE_IN_PROGRESS')
            state = self.load()
            require(not state['active'], 'STAGE_ALREADY_ACTIVE: recover or finish the recorded claim')
            for path in (self.root / 'specs').glob('*/workflow/checkpoint.json'):
                require(path == self.path or not read(path, {}).get('active'), 'OTHER_FEATURE_STAGE_ACTIVE: ' + str(path))
            require(state['dependency_digest'] == package_digest(self.root), 'DEPENDENCY_CHANGED: review upgrade and migrate the checkpoint before execution')
            health = doctor(self.root, self.policy, project=True)
            require(health['ok'], '; '.join(health['errors']))
            gate = context_gate(self.policy, usage)
            if gate['pause']:
                return self.checkpoint(state, 'context-budget', gate)
            nxt = self.next(state, finalize)
            if not nxt.get('stage'):
                return nxt
            stage = nxt['stage']
            if state['policy_digest'] != digest(self.policy):
                state.setdefault('policy_changes', []).append({'from':state['policy_digest'],'to':digest(self.policy),'at':now()})
                state['policy_digest'] = digest(self.policy)
                state['policy'] = copy.deepcopy(self.policy)
                state['commands'] = resolve_commands(self.root, self.policy)
            for downstream in BASE_STAGES[BASE_STAGES.index(stage):]:
                state['receipts'].pop(downstream, None)
            state['active'] = {'stage': stage, 'token': uuid.uuid4().hex, 'claimed_at': now(),
                               'session_id': usage['session_id'], 'context': gate}
            source = read(self.feature / 'scope-source.json', {})
            existing = (self.feature / 'spec.md').is_file() and f"{source.get('repo')}#{source.get('issue')}" == state['issue']
            state['active']['mode'] = 'revalidate' if existing and stage in ('scope', 'specify', 'clarify', 'plan', 'tasks') else 'initial'
            state['active']['baseline'] = fingerprint_files(self.root, [p for r in state['receipts'].values() for p in r['fingerprints']])
            state['status'] = 'in-progress'
            write(self.root / '.specify/feature.json', {'feature_directory': self.relative})
            self.save(state)
            return {**state['active'], 'command': state['commands'][stage], 'feature': self.relative, 'issue': state['issue']}

    def complete(self, token, receipt):
        with locked(self.lock):
            state = self.load()
            active = state['active']
            require(active and active['token'] == token, 'CLAIM_TOKEN_MISMATCH')
            stage = active['stage']
            require(receipt.get('stage') == stage and receipt.get('outcome') == 'passed', 'STAGE_NOT_PASSED')
            require(receipt.get('summary') and receipt.get('evidence'), 'EVIDENCE_REQUIRED')
            require(isinstance(receipt.get('inputs'), list) and receipt['inputs'], 'INPUT_MANIFEST_REQUIRED')
            for path in receipt['evidence']:
                require(inside(self.root, path).is_file(), 'EVIDENCE_MISSING: ' + path)
            if stage == 'clarify':
                require(receipt.get('unresolved') == 0 and receipt.get('answers_applied') is True, 'CLARIFICATION_UNRESOLVED')
            if BASE_STAGES.index(stage) >= BASE_STAGES.index('specify'):
                source = read(self.feature / 'scope-source.json', {})
                require(f"{source.get('repo')}#{source.get('issue')}" == state['issue'], 'FEATURE_BINDING_MISMATCH')
            if stage == 'taskstoissues':
                require(receipt.get('parent_issue') == state['issue'] and receipt.get('native_links_verified') is True, 'TASK_PARENT_NOT_VERIFIED')
            if stage in ('verify', 'review', 'ready'):
                require(receipt.get('blocking_findings') == 0, 'BLOCKING_FINDINGS_REMAIN')
            if stage == 'pr':
                require(receipt.get('images_verified') is True and receipt.get('pr_url', '').startswith('https://github.com/' + state['issue'].split('#')[0] + '/pull/'), 'PR_EVIDENCE_INCOMPLETE')
            # Known semantic transformations advance upstream artifact snapshots with an
            # explicit lineage record. They do not pretend the old artifact remained current.
            permitted = {'clarify': ['spec.md'], 'qa_analyze': ['tasks.md'], 'manual_analyze': ['tasks.md']}.get(stage, [])
            after = fingerprint_files(self.root, active['baseline'])
            changed = [p for p, before in active['baseline'].items() if after[p] != before]
            unexpected = [p for p in changed if p not in [self.relative + '/' + f for f in permitted]]
            require(not unexpected, 'UPSTREAM_INPUT_CHANGED_DURING_STAGE: ' + ', '.join(unexpected))
            if changed:
                state.setdefault('lineage', []).append({'stage': stage, 'changes': {p: {'before': active['baseline'][p], 'after': after[p]} for p in changed}, 'at': now()})
                for prior in state['receipts'].values():
                    for path in changed:
                        if path in prior['fingerprints']:
                            prior['fingerprints'][path] = after[path]
            stored = copy.deepcopy(receipt)
            stored['command'] = state['commands'][stage]
            stored['dependency_digest'] = state['dependency_digest']
            stored['fingerprints'] = fingerprint_files(self.root, receipt['inputs'] + receipt['evidence'] + required_inputs(self.root, self.relative, stage))
            require(all(v is not None for v in stored['fingerprints'].values()), 'INPUT_MISSING')
            if stage in ('verify', 'review', 'ready'):
                stored['source_fingerprints'] = source_fingerprints(self.root)
            stored['completed_at'] = now()
            state['receipts'][stage] = stored
            state['active'] = None
            self.save(state)
            return self.next(state)

    def checkpoint(self, state, reason, context=None):
        state['status'] = 'paused'
        state['pause'] = {'reason': reason, 'context': context, 'at': now()}
        self.save(state)
        pending = self.next(state)
        task_path = self.feature / 'tasks.md'
        pending_tasks = re.findall(r'(?m)^\s*- \[ \]\s+(T\d{3,})\b', task_path.read_text(encoding='utf-8-sig')) if task_path.is_file() else []
        active_summary = {k: state['active'].get(k) for k in ('stage', 'session_id', 'claimed_at')} if state['active'] else None
        text = '# Workflow handoff\n\n' + '\n'.join([
            '- Feature: ' + self.relative, '- Issue: ' + state['issue'], '- Branch: ' + state['branch'],
            '- Head: ' + state['head'], '- Reason: ' + reason, '- Next: ' + str(pending),
            '- Completed stages: ' + ', '.join(state['receipts']),
            '- Active claim: ' + str(active_summary),
            '- Pending task IDs: ' + ', '.join(pending_tasks[:100]) + (' (more in tasks.md)' if len(pending_tasks) > 100 else ''),
            '\nRead evidence paths and summaries in checkpoint.json; do not infer skipped tests passed.',
            '\nInspect git status before continuing; do not discard uncommitted files.'])
        (self.path.parent / 'handoff.md').write_text(text + '\n', encoding='utf-8')
        prompt = f'Continue the Sanduq workflow in {self.root}. Read {self.relative}/workflow/checkpoint.json and handoff.md. Invoke speckit.workflow.continue for {self.relative}; validate inputs and resolve any active claim before resuming. Preserve policy and unresolved approvals.\n'
        (self.path.parent / 'resume-prompt.md').write_text(prompt, encoding='utf-8')
        return {'status': 'paused', 'checkpoint': str(self.path), 'prompt': prompt}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='action', required=True)
    init = sub.add_parser('init')
    init.add_argument('--qa', choices=['on', 'off'], required=True)
    init.add_argument('--manual', choices=['on', 'off'], required=True)
    init.add_argument('--replace', action='store_true')
    doctor_parser = sub.add_parser('doctor')
    doctor_parser.add_argument('--project', action='store_true', help='Also validate configured board identities, phase/status mapping and required sync')
    sub.add_parser('project-defaults')
    for name in ('start', 'next', 'claim', 'complete', 'pause', 'recover', 'bind', 'migrate', 'refresh'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--feature', required=True)
        if name == 'start': cmd.add_argument('--issue', required=True)
        if name in ('next', 'claim'): cmd.add_argument('--finalize', action='store_true')
        if name == 'claim': cmd.add_argument('--usage', type=Path, required=True)
        if name == 'complete':
            cmd.add_argument('--token', required=True)
            cmd.add_argument('--receipt', type=Path, required=True)
        if name in ('pause', 'recover', 'migrate', 'refresh'): cmd.add_argument('--reason', required=True)
        if name in ('recover', 'bind'): cmd.add_argument('--token', required=True)
        if name == 'migrate': cmd.add_argument('--invalidate-from', choices=BASE_STAGES)
        if name == 'refresh': cmd.add_argument('--from-stage', choices=('scope', 'clarify'), required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.action == 'init':
            ensure_local_excludes(root)
            path = root / '.specify/workflow.yml'
            policy = default_policy(args.qa == 'on', args.manual == 'on')
            if path.exists():
                old = load_policy(root)
                require(args.replace or old['processes'] == policy['processes'], 'POLICY_EXISTS: use --replace after reviewing changed selections')
                policy = old
                policy['processes'] = {'qa': args.qa == 'on', 'user_manual': args.manual == 'on'}
                write(root / '.specify/workflow/backups' / (uuid.uuid4().hex + '.json'), load_policy(root))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(validate_policy(policy), sort_keys=False), encoding='utf-8')
            result = {'configured': True, 'processes': policy['processes'], 'doctor': doctor(root, policy)}
        elif args.action == 'doctor':
            result = doctor(root, load_policy(root), project=args.project)
        elif args.action == 'project-defaults':
            result = project_defaults(root, load_policy(root))
        else:
            run = Run(root, args.feature)
            if args.action == 'start': result = run.start(args.issue)
            elif args.action == 'next': result = run.next(run.load(), args.finalize)
            elif args.action == 'claim': result = run.claim(read(args.usage), args.finalize)
            elif args.action == 'complete': result = run.complete(args.token, read(args.receipt, {}))
            elif args.action == 'bind': result = run.bind(args.token)
            elif args.action == 'migrate': result = run.migrate(args.reason, args.invalidate_from)
            elif args.action == 'refresh': result = run.refresh(args.from_stage, args.reason)
            else:
                with locked(run.lock):
                    state = run.load()
                    if args.action == 'recover':
                        require(state['active'] and state['active']['token'] == args.token, 'CLAIM_TOKEN_MISMATCH')
                        state.setdefault('recoveries', []).append({'claim': state['active'], 'reason': args.reason, 'at': now()})
                        state['active'] = None
                    result = run.checkpoint(state, args.reason)
        print(json.dumps(result, indent=2))
        return 1 if result.get('ok') is False else 0
    except (WorkflowError, ValueError, KeyError, yaml.YAMLError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
