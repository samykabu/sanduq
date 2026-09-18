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


def default_policy(qa, manual):
    require(type(qa) is bool and type(manual) is bool, 'Select QA and User Manual explicitly.')
    return {'schema_version': SCHEMA, 'processes': {'qa': qa, 'user_manual': manual},
            'execution': {'engine': 'auto', 'checkpoints': 'required-only'},
            'providers': {'clarification': 'prefer-superspec', 'tasks': 'prefer-superspec'},
            'issue_sync': {'taskstoissues': 'required', 'parent_link': 'native-subissue'},
            'clarification': {'transport': 'github-comments', 'resume_on_reinvoke': 'reread-answers'},
            'context': {'mode': 'measured-with-estimated-fallback', 'max_fraction': .60,
                        'checkpoint_fraction': .50, 'reserve_fraction': .10},
            'finalize': {'create_pr': True, 'merge': False}, 'updates': {'policy': 'reviewed'}}


def validate_policy(policy):
    require(isinstance(policy, dict) and policy.get('schema_version') == SCHEMA, 'POLICY_SCHEMA_UNSUPPORTED')
    for key in ('qa', 'user_manual'):
        require(type(policy.get('processes', {}).get(key)) is bool, 'POLICY_SELECTION_REQUIRED: ' + key)
    require(policy.get('execution', {}).get('engine') in ('auto', 'speckit', 'superspec'), 'EXECUTOR_UNSUPPORTED')
    require(policy.get('execution', {}).get('checkpoints') in ('required-only', 'every-phase'), 'CHECKPOINT_POLICY_INVALID')
    for key in ('clarification', 'tasks'):
        require(policy.get('providers', {}).get(key) in ('prefer-superspec', 'core', 'superspec'), 'PROVIDER_POLICY_INVALID: ' + key)
    context = policy.get('context', {})
    require(context.get('mode') in ('strict', 'measured-with-estimated-fallback'), 'CONTEXT_MODE_INVALID')
    cap, checkpoint, reserve = (context.get(k) for k in ('max_fraction', 'checkpoint_fraction', 'reserve_fraction'))
    require(all(type(v) in (int, float) for v in (cap, checkpoint, reserve)), 'CONTEXT_LIMIT_INVALID')
    require(0 < checkpoint < cap <= .60 and 0 < reserve < cap, 'CONTEXT_LIMIT_INVALID')
    require(policy.get('issue_sync') == {'taskstoissues': 'required', 'parent_link': 'native-subissue'}, 'TASK_ISSUES_REQUIRED')
    require(policy.get('finalize') == {'create_pr': True, 'merge': False}, 'FINALIZE_POLICY_INVALID')
    require(policy.get('clarification', {}).get('resume_on_reinvoke') in ('reread-answers', 'manual-status'), 'CLARIFICATION_POLICY_INVALID')
    band = policy.get('scope', {}).get('keep_together')
    if band:
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


def registry(root):
    return read(root / '.specify/extensions/.registry', {}).get('extensions', {})


def compatible(root, name):
    entry = registry(root).get(name, {})
    try:
        return entry.get('enabled') is True and Version(entry['version']) in SpecifierSet(RANGES[name])
    except (KeyError, ValueError):
        return False


def command_exists(root, command):
    name = command.replace('.', '-')
    return any((root / p / 'skills' / name / 'SKILL.md').is_file() for p in ('.agents', '.claude')) or any(
        (root / '.claude/commands' / (n + '.md')).is_file() for n in (name, command))


def package_digest(root):
    """Ignore install timestamps but detect versions, enablement and source drift."""
    entries = {key: {k: value.get(k) for k in ('version', 'enabled')} for key, value in registry(root).items()}
    paths = []
    for folder in (root / '.specify/extensions', root / '.specify/presets'):
        if folder.is_dir():
            paths += [p.relative_to(root).as_posix() for p in folder.rglob('*') if p.is_file()
                      and p.suffix in ('.py', '.md', '.yml')
                      and not any(part in ('state', '__pycache__', 'tests') for part in p.relative_to(folder).parts)]
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


def doctor(root, policy):
    needed = ['scope', 'project', 'pr'] + (['assure'] if policy['processes']['qa'] else []) + (['user-manual'] if policy['processes']['user_manual'] else [])
    errors = ['DEPENDENCY_UNAVAILABLE: ' + name + ' ' + RANGES[name] for name in needed if not compatible(root, name)]
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
        for event, items in hooks.get('hooks', {}).items():
            for hook in items:
                owned = hook.get('extension') in ('assure', 'user-manual', 'superspec', 'speckit-superpowers-bridge', 'project') or hook.get('command') == 'speckit.scope.after-specify' or (hook.get('extension') == 'pr' and event == 'after_implement')
                if owned and hook.get('enabled', True): errors.append('DUPLICATE_STAGE_OWNER: ' + event + ':' + hook.get('command', ''))
    preset_registry = read(root / '.specify/presets/.registry', {}).get('presets', {})
    for preset in ('workflow', 'scope-gate', 'scope-brainstorm'):
        if not (root / '.specify/presets' / preset / 'preset.yml').is_file():
            errors.append('PRESET_REQUIRED: ' + preset)
        if preset_registry.get(preset, {}).get('enabled') is not True:
            errors.append('PRESET_NOT_ENABLED: ' + preset)
    return {'ok': not errors, 'errors': errors, 'context': 'strict enforcement requires host pre-call bounds; estimated fallback is labelled'}


def context_gate(policy, usage):
    require(isinstance(usage, dict) and usage.get('session_id'), 'CONTEXT_USAGE_REQUIRED')
    require(usage.get('method') in ('measured', 'estimated'), 'CONTEXT_METHOD_REQUIRED')
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

    def migrate(self, reason):
        """Reviewed upgrade invalidates receipts; it never rewrites old evidence as fresh."""
        with locked(self.lock):
            state = self.load()
            require(not state['active'], 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_UPGRADE')
            health = doctor(self.root, self.policy)
            require(health['ok'], '; '.join(health['errors']))
            write(self.path.parent / 'backups' / (uuid.uuid4().hex + '.json'), state)
            state.setdefault('migrations', []).append({'reason': reason, 'from': state['dependency_digest'], 'at': now()})
            state['dependency_digest'] = package_digest(self.root)
            state['commands'] = resolve_commands(self.root, self.policy)
            state['receipts'] = {}
            self.save(state)
            return {'migrated': True, 'next': self.next(state)}

    def start(self, issue):
        require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9]\d*', issue), 'EXPLICIT_ISSUE_REQUIRED')
        with locked(self.lock):
            if self.path.exists():
                state = self.load()
                require(state['issue'] == issue, 'ISSUE_BINDING_CONFLICT')
                return state
            commands = resolve_commands(self.root, self.policy)
            state = {'schema_version': SCHEMA, 'run_id': uuid.uuid4().hex, 'repo_path': str(self.root),
                     'branch': git(self.root, 'branch', '--show-current'), 'feature': self.relative,
                     'issue': issue, 'policy_digest': digest(self.policy), 'commands': commands,
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
        if state['policy_digest'] != digest(self.policy):
            return {'stage': 'scope', 'reason': 'policy-changed', 'invalidates': list(state['receipts'])}
        for stage in stages(self.policy):
            receipt = state['receipts'].get(stage)
            if receipt:
                if fingerprint_files(self.root, receipt['fingerprints']) == receipt['fingerprints']:
                    continue
                return {'stage': stage, 'reason': 'inputs-or-evidence-changed'}
            if stage == 'pr' and not finalize:
                return {'stage': None, 'status': 'ready_to_finalize', 'command': 'speckit.workflow.finalize'}
            return {'stage': stage, 'command': state['commands'][stage], 'reason': 'pending'}
        return {'stage': None, 'status': 'pr_open'}

    def claim(self, usage, finalize=False):
        with locked(self.lock):
            state = self.load()
            require(not state['active'], 'STAGE_ALREADY_ACTIVE: recover or finish the recorded claim')
            require(state['dependency_digest'] == package_digest(self.root), 'DEPENDENCY_CHANGED: review upgrade and migrate the checkpoint before execution')
            health = doctor(self.root, self.policy)
            require(health['ok'], '; '.join(health['errors']))
            gate = context_gate(self.policy, usage)
            if gate['pause']:
                return self.checkpoint(state, 'context-budget', gate)
            nxt = self.next(state, finalize)
            if not nxt.get('stage'):
                return nxt
            stage = nxt['stage']
            if state['policy_digest'] != digest(self.policy):
                state['policy_digest'] = digest(self.policy)
                state['commands'] = resolve_commands(self.root, self.policy)
            for downstream in BASE_STAGES[BASE_STAGES.index(stage):]:
                state['receipts'].pop(downstream, None)
            state['active'] = {'stage': stage, 'token': uuid.uuid4().hex, 'claimed_at': now(),
                               'session_id': usage['session_id'], 'context': gate}
            state['active']['baseline'] = fingerprint_files(self.root, [p for r in state['receipts'].values() for p in r['fingerprints']])
            state['status'] = 'in-progress'
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
            stored['fingerprints'] = fingerprint_files(self.root, receipt['inputs'] + receipt['evidence'])
            require(all(v is not None for v in stored['fingerprints'].values()), 'INPUT_MISSING')
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
    sub.add_parser('doctor')
    for name in ('start', 'next', 'claim', 'complete', 'pause', 'recover', 'bind', 'migrate'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--feature', required=True)
        if name == 'start': cmd.add_argument('--issue', required=True)
        if name in ('next', 'claim'): cmd.add_argument('--finalize', action='store_true')
        if name == 'claim': cmd.add_argument('--usage', type=Path, required=True)
        if name == 'complete':
            cmd.add_argument('--token', required=True)
            cmd.add_argument('--receipt', type=Path, required=True)
        if name in ('pause', 'recover', 'migrate'): cmd.add_argument('--reason', required=True)
        if name in ('recover', 'bind'): cmd.add_argument('--token', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.action == 'init':
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
            result = doctor(root, load_policy(root))
        else:
            run = Run(root, args.feature)
            if args.action == 'start': result = run.start(args.issue)
            elif args.action == 'next': result = run.next(run.load(), args.finalize)
            elif args.action == 'claim': result = run.claim(read(args.usage), args.finalize)
            elif args.action == 'complete': result = run.complete(args.token, read(args.receipt, {}))
            elif args.action == 'bind': result = run.bind(args.token)
            elif args.action == 'migrate': result = run.migrate(args.reason)
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
