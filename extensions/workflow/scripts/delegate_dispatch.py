#!/usr/bin/env python3
"""Launch and collect model-aware Sanduq work through the delegate-task driver.

The dispatcher keeps the workflow claim. A successful delegated run is evidence
for its orchestrator to review, never an automatic passed stage or completed task.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import delegation
import workflow


def stamp():
    return datetime.now(timezone.utc).isoformat()


def relative(root, path):
    path = Path(path).resolve()
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def save(path, value):
    workflow.write(path, value)


def load_ledger(root, feature):
    path = delegation.ledger_path(root, feature)
    value = workflow.read(path, {'schema_version': 1, 'feature': feature,
                                 'attempts': [], 'route_decisions': []})
    delegation.require(value.get('schema_version') == 1 and value.get('feature') == feature and
                       isinstance(value.get('attempts'), list) and
                       isinstance(value.get('route_decisions'), list), 'DELEGATION_LEDGER_INVALID')
    return value


def task_description(root, feature, task_id):
    source = root / feature / 'tasks.md'
    delegation.require(source.is_file(), 'DELEGATION_TASKS_MISSING')
    matches = [line.strip() for line in source.read_text(encoding='utf-8-sig').splitlines()
               if (found := delegation.TASK_LINE.match(line)) and found[3] == task_id]
    delegation.require(len(matches) == 1, 'DELEGATION_TASK_NOT_UNIQUE: ' + task_id)
    delegation.require(not matches[0].startswith('- [x]') and not matches[0].startswith('- [X]'),
                       'DELEGATION_TASK_ALREADY_DONE: ' + task_id)
    return matches[0]


def stage_brief(root, feature, stage, token):
    state = workflow.read(root / feature / 'workflow/checkpoint.json', {})
    active = state.get('active') or {}
    delegation.require(active.get('stage') == stage and active.get('token') == token,
                       'DELEGATION_STAGE_CLAIM_MISMATCH')
    command = state.get('commands', {}).get(stage)
    delegation.require(command, 'DELEGATION_STAGE_COMMAND_MISSING')
    host = workflow.active_host(root)
    command_file = (root / ('.agents' if host == 'codex' else '.claude') / 'skills' /
                    command.replace('.', '-') / 'SKILL.md') if not command.startswith('workflow:') else None
    if command_file is not None:
        delegation.require(command_file.is_file(), 'DELEGATION_COMMAND_MISSING: ' + command)
    ownership = (
        'For Execute, you are the dedicated orchestration agent: assign bounded workers, '
        'integrate verified results, maintain the progress report, and commit and push only '
        'accepted phase work as the installed execution protocol directs. Never complete the '
        'dispatcher claim yourself.\n' if stage == 'execute' else
        'Do not commit, push or alter the progress report.\n'
    )
    return (
        f'Execute only the Sanduq {stage} stage for {feature}, bound to {state["issue"]}.\n'
        f'The dispatcher already owns claim {token}; do not call workflow claim, complete, next, '
        'migrate, recover or another stage.\n'
        f'Read the installed workflow skill and {command_file or "the workflow stage contract"}; '
        f'invoke {command} once inside this claim. Respect all existing binding, evidence and human '
        'decision gates. If a decision is needed, use the existing GitHub decision adapter and '
        'report the pending decision to the dispatcher.\n'
        'Return the concrete input paths, evidence paths, checks executed and any blocker. '
        'The dispatcher will inspect them and complete the receipt; your own success claim is '
        'not a passed Sanduq stage. ' + ownership
    )


def task_brief(root, feature, task_id):
    description = task_description(root, feature, task_id)
    return (
        f'Implement only {task_id} for {feature}: {description}\n'
        f'Read {feature}/spec.md, plan.md and tasks.md, project instructions, and the Sanduq '
        'execution protocol. Respect the assigned files, dependencies and shared resources '
        'provided by the orchestrator. Run relevant checks and return paths to real evidence. '
        'Do not stage, commit, push, change task checkboxes, update the shared progress report, '
        'claim workflow stages or close GitHub issues. The orchestrator will review and integrate '
        'your work.\n'
    )


def brief_file(root, text):
    directory = root / '.delegate/briefs'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (uuid.uuid4().hex + '.txt')
    path.write_text(text, encoding='utf-8')
    return path


def driver_env(root):
    env = os.environ.copy()
    env['DELEGATE_RUNS_DIR'] = str(root / '.delegate/runs')
    return env


def launch(root, driver, candidate, cwd, task, timeout, intent_id=None):
    node = shutil.which('node')
    delegation.require(node is not None, 'NODE_MISSING')
    args = [node, driver, 'start', '--harness', candidate['harness'], '--cwd', str(cwd),
            '--timeout', str(timeout), '--task', task]
    if candidate['requested_model']:
        args += ['--model', candidate['requested_model']]
    if candidate.get('read_only'):
        args.append('--sandbox')
    if candidate.get('allow_commit'):
        args.append('--allow-commit')
    if intent_id:
        args += ['--constraint', 'Sanduq delegation intent: ' + intent_id]
    result = subprocess.run(args, cwd=root, env=driver_env(root),
                            capture_output=True, text=True, encoding='utf-8')
    if result.returncode:
        raise delegation.DelegationError('DELEGATE_START_FAILED: ' +
                                         (result.stderr.strip() or result.stdout.strip())[:500])
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise delegation.DelegationError('DELEGATE_START_RESPONSE_INVALID') from exc
    delegation.require(payload.get('run_id') and payload.get('state') in ('starting', 'running'),
                       'DELEGATE_START_RESPONSE_INVALID')
    return payload


def candidate_start(root, feature, identity, work_type, candidates, task_path, cwd,
                    timeout, parent_run_id=None, retry_count=0):
    config = workflow.load_policy(root)['delegation']
    status = delegation.doctor(root, workflow.active_host(root), install=True,
                               scope=config['install_scope'])
    delegation.require(status['ok'], status.get('error', 'DELEGATE_SKILL_UNAVAILABLE'))
    ledger = load_ledger(root, feature)
    task = task_path.read_text(encoding='utf-8')
    intent = {'intent_id': uuid.uuid4().hex, 'identity': identity,
              'task_type': work_type, 'status': 'starting', 'started_at': stamp(),
              'task_file': relative(root, task_path), 'cwd': relative(root, cwd),
              'timeout': timeout, 'route_candidates': candidates,
              'parent_run_id': parent_run_id, 'retry_count': retry_count}
    ledger['attempts'].append(intent)
    save(delegation.ledger_path(root, feature), ledger)
    for index, candidate in enumerate(candidates):
        if not status['harnesses'].get(candidate['harness']):
            ledger['route_decisions'].append({'at': stamp(), 'identity': identity,
                                              'requested': candidate, 'decision': 'skip',
                                              'reason': status.get('cli_errors', {}).get(candidate['harness'],
                                                                                       'AGENT_CLI_UNAVAILABLE')})
            save(delegation.ledger_path(root, feature), ledger)
            continue
        selected = copy.deepcopy(candidate)
        selected['read_only'] = work_type == 'review'
        selected['allow_commit'] = identity.endswith('/stage:execute')
        try:
            started = launch(root, status['driver'], selected, cwd, task, timeout,
                             intent['intent_id'])
        except delegation.DelegationError as error:
            # A lost start response does not prove the driver failed to launch.
            # Keep the intent for recovery instead of starting a second worker.
            intent['start_error'] = str(error)
            ledger['route_decisions'].append({'at': stamp(), 'identity': identity,
                                              'requested': candidate, 'decision': 'start-uncertain',
                                              'reason': str(error)})
            save(delegation.ledger_path(root, feature), ledger)
            raise delegation.DelegationError('DELEGATION_START_UNCERTAIN: recover intent ' +
                                             intent['intent_id']) from error
        attempt = {'identity': identity, 'task_type': work_type, 'run_id': started['run_id'],
                   'parent_run_id': parent_run_id, 'requested_harness': selected['harness'],
                   'requested_model': selected['requested_model'], 'actual_model': None,
                   'actual_model_evidence': 'pending', 'rule': selected['rule'],
                   'choice': selected['choice'], 'candidate_index': index,
                   'route_candidates': candidates, 'retry_count': retry_count,
                   'read_only': selected['read_only'], 'status': 'running',
                   'allow_commit': selected['allow_commit'],
                   'started_at': stamp(), 'task_file': relative(root, task_path),
                   'cwd': relative(root, cwd), 'timeout': timeout,
                   'evidence_location': '.delegate/runs/' + started['run_id'] + '/result.json'}
        intent.update(attempt)
        if index:
            ledger['route_decisions'].append({'at': stamp(), 'identity': identity,
                                              'requested': candidates[0], 'actual_route': selected,
                                              'decision': 'fallback',
                                              'reason': 'Earlier candidates unavailable'})
        save(delegation.ledger_path(root, feature), ledger)
        return {'enabled': True, 'run_id': started['run_id'], 'state': started['state'],
                'route': selected, 'evidence_location': attempt['evidence_location'],
                'intent_id': intent['intent_id']}
    intent.update(status='blocked', ended_at=stamp(),
                  result_summary='No configured route could start')
    save(delegation.ledger_path(root, feature), ledger)
    raise delegation.DelegationError('DELEGATION_ROUTES_UNAVAILABLE: ' + identity)


def start(root, feature, identity, work_type=None, task_file=None, cwd=None,
          token=None, timeout=None):
    root = root.resolve()
    policy = workflow.load_policy(root)
    config = policy['delegation']
    claimed_route = None
    if identity.startswith('stage:'):
        checkpoint = workflow.read(root / feature / 'workflow/checkpoint.json', {})
        active = checkpoint.get('active') or {}
        if active.get('stage') == identity.removeprefix('stage:') and active.get('token') == token:
            claimed_route = active.get('delegation', {}).get('candidates')
    if not config['enabled'] and not claimed_route:
        return {'enabled': False, 'identity': identity, 'action': 'run-in-selected-host'}
    delegation.require(re.fullmatch(r'T\d{3,}|stage:[a-z_]+', identity) is not None,
                       'DELEGATION_IDENTITY_INVALID')
    timeout = timeout if timeout is not None else (7200 if identity == 'stage:execute' else 1800)
    delegation.require(type(timeout) is int and 0 < timeout <= 28800,
                       'DELEGATION_TIMEOUT_INVALID')
    feature_path = (root / feature).resolve()
    delegation.require(feature_path.is_relative_to(root / 'specs') and
                       feature_path.parent == root / 'specs', 'DELEGATION_FEATURE_INVALID')
    if identity.startswith('stage:'):
        stage = identity.removeprefix('stage:')
        delegation.require(stage in delegation.STAGE_TYPES and token, 'DELEGATION_STAGE_INVALID')
        work_type = delegation.STAGE_TYPES[stage]
        text = stage_brief(root, feature, stage, token)
    else:
        description = task_description(root, feature, identity)
        text = task_brief(root, feature, identity)
        work_type = work_type or delegation.task_type(description)
        delegation.require(work_type in delegation.TYPES, 'DELEGATION_TASK_TYPE_INVALID')
    if task_file:
        provided = Path(task_file).resolve()
        delegation.require(provided.is_file() and provided.is_relative_to(root),
                           'DELEGATION_TASK_FILE_INVALID')
        text += '\nAdditional assignment and acceptance details:\n' + provided.read_text(encoding='utf-8')
    cwd = Path(cwd).resolve() if cwd else root
    delegation.require(cwd.is_dir(), 'DELEGATION_CWD_INVALID')
    ledger = load_ledger(root, feature)
    full_identity = feature + '/' + identity
    delegation.require(not any(a['identity'] == full_identity and a['status'] in ('starting', 'running')
                               for a in ledger['attempts']), 'DELEGATION_ALREADY_RUNNING')
    workflow.ensure_local_excludes(root)
    task_path = brief_file(root, text)
    if identity.startswith('stage:'):
        candidates = claimed_route
        delegation.require(isinstance(candidates, list) and candidates,
                           'DELEGATION_STAGE_ROUTE_SNAPSHOT_MISSING')
    else:
        candidates = delegation.selected_route(config, work_type, workflow.active_host(root),
                                                full_identity)
    return candidate_start(root, feature, full_identity, work_type, candidates,
                           task_path, cwd, timeout)


MODEL_ERROR = re.compile(r'unknown model|model (?:not found|is not available|not supported|unavailable)|'
                         r'invalid model|unsupported model', re.I)


def model_rejected(result):
    reason = str(result.get('status_reason') or '')
    stderr = (result.get('artifacts') or {}).get('stderr')
    if stderr and Path(stderr).is_file():
        reason += '\n' + Path(stderr).read_text(encoding='utf-8', errors='replace')[-4000:]
    return bool(MODEL_ERROR.search(reason))


def collect(root, feature, run_id, auto_retry=True):
    root = root.resolve()
    policy = workflow.load_policy(root)
    ledger = load_ledger(root, feature)
    attempt = next((a for a in ledger['attempts'] if a['run_id'] == run_id), None)
    delegation.require(attempt is not None, 'DELEGATION_RUN_UNKNOWN: ' + run_id)
    child = next((a for a in ledger['attempts'] if a.get('parent_run_id') == run_id), None)
    if child:
        if child.get('run_id'):
            attempt['replacement_run_id'] = child['run_id']
            save(delegation.ledger_path(root, feature), ledger)
            return {'run_id': run_id, 'status': attempt['status'],
                    'replacement_run_id': child['run_id'], 'decision': 'already re-routed'}
        return {'run_id': run_id, 'status': attempt['status'],
                'replacement_intent_id': child['intent_id'], 'decision': 'recover replacement intent'}
    if attempt.get('replacement_run_id'):
        return {'run_id': run_id, 'status': attempt['status'],
                'replacement_run_id': attempt['replacement_run_id'],
                'decision': 'already re-routed'}
    status = delegation.inspect_skill(root, workflow.active_host(root))
    delegation.require(status['ok'], status['error'] if not status['ok'] else '')
    node = shutil.which('node')
    delegation.require(node is not None, 'NODE_MISSING')
    result = subprocess.run([node, status['driver'], 'collect', run_id, '--json'],
                            cwd=root, env=driver_env(root), capture_output=True,
                            text=True, encoding='utf-8')
    if result.returncode == 3:
        return {'run_id': run_id, 'status': 'running'}
    delegation.require(result.returncode == 0, 'DELEGATE_COLLECT_FAILED: ' +
                       (result.stderr.strip() or result.stdout.strip())[:500])
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise delegation.DelegationError('DELEGATE_RESULT_INVALID') from exc
    delegation.require(payload.get('run_id') == run_id and
                       payload.get('status') in ('successful', 'failed', 'abandoned'),
                       'DELEGATE_RESULT_INVALID')
    delegation.require(payload.get('harness') == attempt['requested_harness'],
                       'DELEGATE_HARNESS_MISMATCH')
    attempt['status'] = payload['status']
    attempt['ended_at'] = stamp()
    attempt['result_summary'] = str(payload.get('summary') or '')[:2000]
    attempt['status_provenance'] = payload.get('status_provenance')
    attempt['actual_harness'] = payload.get('harness')
    attempt['actual_model'] = payload.get('actual_model') if payload.get('model_observed') is True else None
    attempt['actual_model_evidence'] = 'harness-reported' if attempt['actual_model'] else 'unverified'
    attempt['token_usage'] = payload.get('tokens') if (payload.get('tokens') or {}).get('fidelity') in ('exact', 'partial') else None
    attempt['changed_paths'] = payload.get('dirty_paths_changed')
    attempt['evidence_location'] = relative(root, Path((payload.get('artifacts') or {}).get('dir',
                                                    root / '.delegate/runs' / run_id)) / 'result.json')
    save(delegation.ledger_path(root, feature), ledger)
    response = {'run_id': run_id, 'status': attempt['status'],
                'requested_model': attempt['requested_model'],
                'actual_model': attempt['actual_model'],
                'actual_model_evidence': attempt['actual_model_evidence'],
                'harness': attempt['actual_harness'], 'evidence_location': attempt['evidence_location'],
                'token_usage': attempt['token_usage'], 'result_summary': attempt['result_summary']}
    if (not auto_retry or payload['status'] != 'failed' or payload.get('head_changed') or
            payload.get('index_changed') or payload.get('dirty_paths_changed')):
        return response
    candidates = attempt['route_candidates']
    if model_rejected(payload):
        remaining = candidates[attempt['candidate_index'] + 1:]
        reason = 'requested model rejected by CLI'
    elif attempt['retry_count'] < policy['delegation']['stronger_retry']:
        stronger = delegation.stronger_candidate(policy['delegation'], attempt_to_candidate(attempt),
                                                 workflow.active_host(root))
        remaining = [stronger] if stronger else []
        reason = 'failed work eligible for one stronger reassignment'
    else:
        remaining = []
        reason = ''
    if remaining:
        task_path = root / attempt['task_file']
        delegation.require(task_path.is_file(), 'DELEGATION_BRIEF_MISSING_FOR_RETRY')
        ledger['route_decisions'].append({'at': stamp(), 'identity': attempt['identity'],
                                          'requested': attempt_to_candidate(attempt),
                                          'decision': 'fallback' if model_rejected(payload) else 'reassignment',
                                          'reason': reason, 'after_run_id': run_id})
        save(delegation.ledger_path(root, feature), ledger)
        replacement = candidate_start(root, feature, attempt['identity'], attempt['task_type'],
                                      remaining, task_path, root / attempt['cwd'],
                                      attempt['timeout'], parent_run_id=run_id,
                                      retry_count=attempt['retry_count'] + (0 if model_rejected(payload) else 1))
        ledger = load_ledger(root, feature)
        original = next(a for a in ledger['attempts'] if a['run_id'] == run_id)
        original['replacement_run_id'] = replacement['run_id']
        save(delegation.ledger_path(root, feature), ledger)
        return {**response, 'replacement': replacement, 'decision': reason}
    return response


def attempt_to_candidate(attempt):
    return {'harness': attempt['requested_harness'],
            'requested_model': attempt['requested_model'],
            'tier': next((c.get('tier') for c in attempt['route_candidates']
                          if c['harness'] == attempt['requested_harness'] and
                          c['requested_model'] == attempt['requested_model']), None),
            'rule': attempt['rule'], 'choice': attempt['choice']}


def reassign(root, feature, run_id, reason, task_file=None):
    """Let the orchestrator escalate complex or partly changed terminal work."""
    root = root.resolve()
    delegation.require(isinstance(reason, str) and reason.strip(),
                       'DELEGATION_REASSIGN_REASON_REQUIRED')
    policy = workflow.load_policy(root)
    config = policy['delegation']
    delegation.require(config['enabled'], 'DELEGATION_DISABLED')
    ledger = load_ledger(root, feature)
    prior = next((a for a in ledger['attempts'] if a.get('run_id') == run_id), None)
    delegation.require(prior is not None and prior.get('status') in
                       ('successful', 'failed', 'abandoned'), 'DELEGATION_PRIOR_RUN_NOT_TERMINAL')
    delegation.require(prior['retry_count'] < config['stronger_retry'],
                       'DELEGATION_RETRY_LIMIT_REACHED')
    delegation.require(not prior.get('replacement_run_id') and
                       not any(a.get('parent_run_id') == run_id for a in ledger['attempts']) and
                       not any(a['identity'] == prior['identity'] and a['status'] in ('starting', 'running')
                               for a in ledger['attempts']), 'DELEGATION_ALREADY_REASSIGNED')
    stronger = delegation.stronger_candidate(config, attempt_to_candidate(prior),
                                             workflow.active_host(root))
    delegation.require(stronger is not None, 'DELEGATION_STRONGER_ROUTE_UNAVAILABLE')
    original = (root / prior['task_file']).read_text(encoding='utf-8')
    text = original + '\nOrchestrator reassignment reason: ' + reason.strip() + '\n'
    if task_file:
        extra = Path(task_file).resolve()
        delegation.require(extra.is_file() and extra.is_relative_to(root),
                           'DELEGATION_TASK_FILE_INVALID')
        text += '\nUpdated assignment:\n' + extra.read_text(encoding='utf-8')
    brief = brief_file(root, text)
    ledger['route_decisions'].append({'at': stamp(), 'identity': prior['identity'],
                                      'requested': attempt_to_candidate(prior),
                                      'decision': 'reassignment', 'reason': reason.strip(),
                                      'after_run_id': run_id})
    save(delegation.ledger_path(root, feature), ledger)
    replacement = candidate_start(root, feature, prior['identity'], prior['task_type'],
                                  [stronger], brief, root / prior['cwd'], prior['timeout'],
                                  parent_run_id=run_id, retry_count=prior['retry_count'] + 1)
    ledger = load_ledger(root, feature)
    next(a for a in ledger['attempts'] if a['run_id'] == run_id)['replacement_run_id'] = replacement['run_id']
    save(delegation.ledger_path(root, feature), ledger)
    return replacement


def recover_intent(root, feature, intent_id):
    """Recover a driver run created just before its Sanduq ledger write."""
    root = root.resolve()
    ledger = load_ledger(root, feature)
    intent = next((a for a in ledger['attempts'] if a.get('intent_id') == intent_id), None)
    delegation.require(intent is not None, 'DELEGATION_INTENT_UNKNOWN')
    if intent.get('run_id'):
        return {'found': True, 'run_id': intent['run_id'], 'status': intent['status']}
    delegation.require(intent['status'] == 'starting', 'DELEGATION_INTENT_NOT_STARTING')
    found = []
    for path in (root / '.delegate/runs').glob('*/meta.json'):
        meta = workflow.read(path, {})
        if 'Sanduq delegation intent: ' + intent_id in meta.get('constraint', []):
            found.append(meta)
    delegation.require(len(found) <= 1, 'DELEGATION_INTENT_AMBIGUOUS')
    if not found:
        return {'found': False, 'status': 'starting', 'intent_id': intent_id}
    meta = found[0]
    candidate_index = next((index for index, item in enumerate(intent['route_candidates'])
                            if item['harness'] == meta.get('harness') and
                            item['requested_model'] == meta.get('model')), None)
    delegation.require(candidate_index is not None, 'DELEGATION_INTENT_ROUTE_MISMATCH')
    candidate = intent['route_candidates'][candidate_index]
    intent.update(run_id=meta['run_id'], requested_harness=meta['harness'],
                  requested_model=meta.get('model'), actual_model=None,
                  actual_model_evidence='pending', rule=candidate['rule'],
                  choice=candidate['choice'], candidate_index=candidate_index,
                  status='running', read_only=meta.get('permission') == 'sandbox',
                  allow_commit=bool(meta.get('allow_commit')),
                  evidence_location='.delegate/runs/' + meta['run_id'] + '/result.json')
    save(delegation.ledger_path(root, feature), ledger)
    return {'found': True, 'run_id': meta['run_id'], 'status': 'running'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='action', required=True)
    start_cmd = sub.add_parser('start')
    start_cmd.add_argument('--feature', required=True)
    start_cmd.add_argument('--id', required=True)
    start_cmd.add_argument('--type', choices=delegation.TYPES)
    start_cmd.add_argument('--task-file', type=Path)
    start_cmd.add_argument('--cwd', type=Path)
    start_cmd.add_argument('--claim-token')
    start_cmd.add_argument('--timeout', type=int)
    collect_cmd = sub.add_parser('collect')
    collect_cmd.add_argument('--feature', required=True)
    collect_cmd.add_argument('--run-id', required=True)
    collect_cmd.add_argument('--no-auto-retry', action='store_true')
    recover_cmd = sub.add_parser('recover')
    recover_cmd.add_argument('--feature', required=True)
    recover_cmd.add_argument('--intent-id', required=True)
    reassign_cmd = sub.add_parser('reassign')
    reassign_cmd.add_argument('--feature', required=True)
    reassign_cmd.add_argument('--run-id', required=True)
    reassign_cmd.add_argument('--reason', required=True)
    reassign_cmd.add_argument('--task-file', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == 'start':
            result = start(args.root, args.feature, args.id, args.type, args.task_file,
                           args.cwd, args.claim_token, args.timeout)
        elif args.action == 'collect':
            result = collect(args.root, args.feature, args.run_id, not args.no_auto_retry)
        elif args.action == 'recover':
            result = recover_intent(args.root, args.feature, args.intent_id)
        else:
            result = reassign(args.root, args.feature, args.run_id, args.reason, args.task_file)
        print(json.dumps(result, indent=2))
        return 0
    except (delegation.DelegationError, workflow.WorkflowError, OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
