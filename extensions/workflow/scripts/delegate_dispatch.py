#!/usr/bin/env python3
"""Launch and collect model-aware Sanduq work through the delegate-task driver.

The dispatcher keeps the workflow claim. A successful delegated run is evidence
for its orchestrator to review, never an automatic passed stage or completed task.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from contextlib import contextmanager
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


ACTIVE = ('starting', 'running')
# Replacement intents that never produced a run and no longer block a retry.
INACTIVE_INTENTS = ('blocked', 'intent-abandoned')
LOCK_TIMEOUT = 15.0
# An intent without a recorded launch outcome may still belong to a dispatcher
# that is inside its driver start; the driver acknowledges within 15 seconds.
ABANDON_GRACE_SECONDS = 300


# One specs/<name> identity for every --feature spelling, shared with delegation.py.
feature_identity = delegation.feature_identity


def load_ledger(root, feature):
    path = delegation.ledger_path(root, feature)
    value = workflow.read(path, {'schema_version': 1, 'feature': feature,
                                 'attempts': [], 'route_decisions': []})
    stored = value.get('feature')
    if isinstance(stored, str) and stored != feature:
        # Ledgers written before spellings were normalised keep their history.
        try:
            stored = feature_identity(root, stored)
        except delegation.DelegationError:
            pass
    delegation.require(value.get('schema_version') == 1 and stored == feature and
                       isinstance(value.get('attempts'), list) and
                       isinstance(value.get('route_decisions'), list), 'DELEGATION_LEDGER_INVALID')
    value['feature'] = feature
    return value


@contextmanager
def ledger_lock(root, feature):
    """Serialise ledger read-modify-write across dispatcher processes.

    Critical sections never include node or agent CLI launches, so a busy lock
    means another dispatcher is mid-write; waiting is bounded and the error is
    retryable rather than a silently lost attempt. A lock left by a dispatcher
    that died on this host is recovered; a live owner's lock is never taken.
    """
    path = root / '.specify/workflow/runtime' / ('delegation-' + workflow.digest(feature) + '.lock')
    with delegation.file_lock(path, LOCK_TIMEOUT, 'DELEGATION_LEDGER_BUSY') as token:
        yield path, token


def written_marker(root, feature):
    """Runtime record of the ledger bytes this dispatcher last wrote."""
    return root / '.specify/workflow/runtime' / ('delegation-' + workflow.digest(feature) + '.written')


def ledger_bytes_digest(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def ledger_written_by_dispatcher(root, feature):
    """True when the ledger still holds exactly the bytes a dispatcher last saved.

    Call it under the ledger lock. Any other writer since that save, such as
    a worker or a rollback, leaves different bytes and the answer is False.
    """
    recorded = workflow.read(written_marker(root, feature), {}).get('sha256')
    return recorded is not None and recorded == ledger_bytes_digest(delegation.ledger_path(root, feature))


def ledger_foreign_write(root, feature):
    """True when the ledger exists and no dispatcher save accounts for its bytes.

    A ledger with no record of a dispatcher save (a fresh clone or an older
    build) counts as foreign too: nothing proves who wrote it.
    """
    return (delegation.ledger_path(root, feature).exists() and
            not ledger_written_by_dispatcher(root, feature))


def maintenance_allows(ledger, key):
    """While an upgrade or install runs, only records it has already seen may change.

    Its preflight takes every ledger lock after creating its own lock and
    refuses while any attempt is starting or running. So an attempt that is
    still active here existed before that scan and the upgrade has refused;
    finishing its bookkeeping is safe. New reservations and changes to
    terminal records would be lost to a rollback and are refused.
    """
    if key is None:
        return False
    field, value = key
    attempt = next((a for a in ledger['attempts'] if a.get(field) == value), None)
    return attempt is not None and attempt.get('status') in ACTIVE


@contextmanager
def edit_ledger(root, feature, active=None):
    """Re-read, mutate and save the ledger atomically; an exception saves nothing.

    ``active`` names the ``(field, value)`` of the one active attempt this edit
    finishes; only such an edit may proceed while an upgrade or install runs.
    """
    with ledger_lock(root, feature) as (path, token):
        value = load_ledger(root, feature)
        if not maintenance_allows(value, active):
            delegation.require_no_maintenance(root)
        original = copy.deepcopy(value)
        if ledger_foreign_write(root, feature):
            # Someone other than a dispatcher wrote the ledger since the last
            # save. This save would absorb that write and re-mark it as the
            # dispatcher's bytes, so every live run durably records that its
            # ledger change can no longer be attributed to Sanduq.
            seen = stamp()
            for attempt in value['attempts']:
                if attempt.get('status') in ACTIVE:
                    attempt.setdefault('ledger_foreign_write_seen', seen)
        yield value
        if value == original:
            # Nothing to record. Rewriting unchanged history would also re-mark
            # someone else's edit to the file as the dispatcher's own bytes.
            return
        # A lock recovered from under this process (only possible if it was
        # judged dead) must never let it overwrite a newer owner's ledger.
        delegation.require(delegation.lock_held(path, token),
                           'DELEGATION_LEDGER_BUSY: the ledger lock was lost; retry the command')
        ledger = delegation.ledger_path(root, feature)
        save(ledger, value)
        workflow.write(written_marker(root, feature), {'sha256': ledger_bytes_digest(ledger)})


def maintenance_preflight(root):
    """Refuse an upgrade or install while any delegation attempt is still active.

    The caller already holds its upgrade or install lock, so every dispatcher
    critical section that starts after this point is refused. Draining the
    project skill-install lock and taking each feature's ledger lock in turn
    waits out those that began earlier, so the scan misses no reservation.
    """
    root = Path(root).resolve()
    with delegation.file_lock(delegation.install_lock_path(root, 'project'),
                              delegation.INSTALL_LOCK_TIMEOUT, 'DELEGATE_SKILL_INSTALL_BUSY'):
        pass
    active = []
    for folder in sorted(path for path in (root / 'specs').glob('*') if path.is_dir()):
        feature = 'specs/' + folder.name
        with ledger_lock(root, feature):
            ledger = workflow.read(delegation.ledger_path(root, feature), {})
            active += [feature + ' ' + (a.get('run_id') or 'intent ' + str(a.get('intent_id'))) +
                       ' (' + str(a.get('status')) + ')'
                       for a in ledger.get('attempts', []) if a.get('status') in ACTIVE]
    delegation.require(not active, 'DELEGATION_ATTEMPTS_ACTIVE: collect, recover or abandon ' +
                       ', '.join(active) + ' before upgrading or reinstalling')


def read_ledger(root, feature):
    with ledger_lock(root, feature):
        return load_ledger(root, feature)


def find_intent(ledger, intent_id):
    return next((a for a in ledger['attempts'] if a.get('intent_id') == intent_id), None)


def find_run(ledger, run_id):
    return next((a for a in ledger['attempts'] if a.get('run_id') == run_id), None)


def live_children(ledger, run_id):
    return [a for a in ledger['attempts'] if a.get('parent_run_id') == run_id and
            a.get('status') not in INACTIVE_INTENTS]


def reserve(ledger, identity, parent_run_id):
    delegation.require(not any(a.get('identity') == identity and a.get('status') in ACTIVE
                               for a in ledger['attempts']), 'DELEGATION_ALREADY_RUNNING: ' + identity)
    if parent_run_id:
        delegation.require(not live_children(ledger, parent_run_id),
                           'DELEGATION_ALREADY_REASSIGNED: ' + parent_run_id)


def skill_folders(root):
    """Every location inspect_skill may select a driver from; nothing else runs."""
    folders = []
    override = os.environ.get('SANDUQ_DELEGATE_DRIVER')
    if override:
        folders.append(Path(override).parent)
    for host in ('codex', 'claude'):
        folders += delegation.local_skill_paths(root, host)
    plugin = os.environ.get('CLAUDE_PLUGIN_ROOT')
    if plugin:
        folders.append(Path(plugin) / 'skills/delegate-task')
    return list(dict.fromkeys(folders))


def pinned_driver(root, attempt):
    """Use the installed driver copy that started this attempt."""
    stored = attempt.get('driver')
    if not stored:
        status = delegation.inspect_skill(root, workflow.active_host(root))
        delegation.require(status['ok'], delegation.health_error(status))
        return status['driver']
    path = Path(stored)
    path = (path if path.is_absolute() else root / path).resolve()
    for folder in skill_folders(root):
        if (folder / 'delegate.mjs').resolve() == path:
            delegation.require(path.is_file() and (folder / 'SKILL.md').is_file() and
                               (folder / 'contracts/result-schema-v2.md').is_file(),
                               'DELEGATION_DRIVER_MISSING: reinstall the delegate-task skill at ' +
                               str(folder))
            return str(path)
    raise delegation.DelegationError('DELEGATION_DRIVER_UNTRUSTED: ' + str(stored))


def intent_run_dirs(root, intent_id):
    """Every driver run directory whose meta.json carries this intent's marker."""
    marker = 'Sanduq delegation intent: ' + intent_id
    found = []
    for path in (root / '.delegate/runs').glob('*/meta.json'):
        meta = workflow.read(path, {})
        if marker in (meta.get('constraint') or []):
            found.append((path.parent, meta))
    return found


def dismissed_runs(intent):
    """Runs this intent already proved never launched an agent."""
    return {item['run_id'] for item in (intent or {}).get('start_failures', []) if item.get('run_id')}


def intent_runs(root, intent_id, dismissed=()):
    return [meta for _, meta in intent_run_dirs(root, intent_id) if meta.get('run_id') not in dismissed]


def journal_states(directory):
    states = set()
    try:
        lines = (directory / 'journal.jsonl').read_text(encoding='utf-8').splitlines()
    except OSError:
        return states
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            states.add(entry.get('state'))
    return states


def never_launched(directory, meta):
    """True only when a driver run provably never reached an agent CLI.

    The driver exits 5 when its supervisor did not acknowledge within the start
    window; it then finalises a failed result saying the harness never
    launched and kills the supervisor. The supervisor journals
    ``supervisor_started`` before anything else and is the only process that
    starts the agent, so a missing acknowledgement from a supervisor that is no
    longer alive proves no agent ran. Anything else stays uncertain.
    """
    result = workflow.read(directory / 'result.json', None)
    if not isinstance(result, dict) or result.get('run_id') != meta.get('run_id'):
        return False
    if (result.get('status') != 'failed' or result.get('permission_mode_applied') is not None or
            result.get('containment_evidence') != 'the harness never launched'):
        return False
    # The start command journals only "created" and, via the finaliser,
    # "terminal". Any other event means a supervisor ran.
    if not journal_states(directory) <= {'created', 'terminal'}:
        return False
    return not delegation.process_alive(meta.get('supervisor_pid'))


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


class StartFailed(delegation.DelegationError):
    """The driver process exited or never spawned, so its run directory is final."""

    def __init__(self, message, exit_code=None):
        super().__init__(message)
        self.exit_code = exit_code


# delegate.mjs exit code when its supervisor never acknowledged the start.
SUPERVISOR_START_FAILED = 5


def launch(root, driver, candidate, cwd, task, timeout, intent_id=None):
    node = shutil.which('node')
    if node is None:
        raise StartFailed('NODE_MISSING')
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
    try:
        result = subprocess.run(args, cwd=root, env=driver_env(root),
                                capture_output=True, text=True, encoding='utf-8')
    except OSError as exc:
        raise StartFailed('DELEGATE_START_FAILED: ' + str(exc)[:500]) from exc
    if result.returncode:
        raise StartFailed('DELEGATE_START_FAILED: ' +
                          (result.stderr.strip() or result.stdout.strip())[:500], result.returncode)
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise delegation.DelegationError('DELEGATE_START_RESPONSE_INVALID') from exc
    delegation.require(payload.get('run_id') and payload.get('state') in ('starting', 'running'),
                       'DELEGATE_START_RESPONSE_INVALID')
    return payload


def candidate_start(root, feature, identity, work_type, candidates, task_path, cwd,
                    timeout, parent_run_id=None, retry_count=0, decision=None):
    config = workflow.load_policy(root)['delegation']
    status = delegation.doctor(root, workflow.active_host(root), install=True,
                               scope=config['install_scope'])
    delegation.require(status['ok'], delegation.health_error(status))
    task = task_path.read_text(encoding='utf-8')
    intent_id = uuid.uuid4().hex
    dismissed = set()
    with edit_ledger(root, feature) as ledger:
        # The reservation and the route decision that justifies it are one
        # write, so a concurrent start or collect cannot launch the work twice.
        reserve(ledger, identity, parent_run_id)
        if decision:
            ledger['route_decisions'].append(decision)
        ledger['attempts'].append({'intent_id': intent_id, 'identity': identity,
                                   'task_type': work_type, 'status': 'starting',
                                   'started_at': stamp(), 'task_file': relative(root, task_path),
                                   'cwd': relative(root, cwd), 'timeout': timeout,
                                   'route_candidates': candidates,
                                   'driver': relative(root, status['driver']),
                                   'parent_run_id': parent_run_id, 'retry_count': retry_count})
    for index, candidate in enumerate(candidates):
        if not status['harnesses'].get(candidate['harness']):
            with edit_ledger(root, feature, ('intent_id', intent_id)) as ledger:
                ledger['route_decisions'].append({
                    'at': stamp(), 'identity': identity, 'requested': candidate, 'decision': 'skip',
                    'reason': status.get('cli_errors', {}).get(candidate['harness'],
                                                              'AGENT_CLI_UNAVAILABLE')})
            continue
        selected = copy.deepcopy(candidate)
        # Route type chooses a model, never filesystem permission: a delegated
        # review writes its evidence and may run checks or schedule fixes.
        selected['read_only'] = False
        selected['allow_commit'] = identity.endswith('/stage:execute')
        try:
            started = launch(root, status['driver'], selected, cwd, task, timeout, intent_id)
        except delegation.DelegationError as error:
            # The driver writes meta.json before it spawns a worker. An exited
            # driver with no run for this intent proves nothing started, and so
            # does exit 5 with a finalised never-launched run whose supervisor
            # is gone. Only then may the next configured candidate run;
            # anything else is uncertain.
            runs = [(directory, meta) for directory, meta in intent_run_dirs(root, intent_id)
                    if meta.get('run_id') not in dismissed]
            not_launched = None
            if (isinstance(error, StartFailed) and error.exit_code == SUPERVISOR_START_FAILED and
                    len(runs) == 1 and never_launched(*runs[0])):
                not_launched = runs[0][1]['run_id']
            confirmed = isinstance(error, StartFailed) and (not runs or not_launched is not None)
            with edit_ledger(root, feature, ('intent_id', intent_id)) as ledger:
                intent = find_intent(ledger, intent_id)
                if confirmed:
                    failure = {'at': stamp(), 'candidate_index': index, 'reason': str(error)}
                    if not_launched:
                        failure.update(run_id=not_launched, evidence='driver exit 5; result says the '
                                       'harness never launched; supervisor never started and is gone')
                        dismissed.add(not_launched)
                    intent.setdefault('start_failures', []).append(failure)
                else:
                    intent['start_error'] = str(error)
                ledger['route_decisions'].append({'at': stamp(), 'identity': identity,
                                                  'requested': candidate,
                                                  'decision': 'start-failed' if confirmed
                                                  else 'start-uncertain',
                                                  'reason': str(error), 'intent_id': intent_id,
                                                  **({'run_id': not_launched} if not_launched else {})})
            if confirmed:
                continue
            # A lost start response does not prove the driver failed to launch.
            # Keep the intent for recovery instead of starting a second worker.
            raise delegation.DelegationError(
                'DELEGATION_START_UNCERTAIN: recover intent ' + intent_id +
                ', or abandon it with a reason once no driver run exists') from error
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
        with edit_ledger(root, feature, ('intent_id', intent_id)) as ledger:
            find_intent(ledger, intent_id).update(attempt)
            if index:
                ledger['route_decisions'].append({'at': stamp(), 'identity': identity,
                                                  'requested': candidates[0], 'actual_route': selected,
                                                  'decision': 'fallback',
                                                  'reason': 'Earlier candidates unavailable or '
                                                            'failed before a run existed'})
        response = {'enabled': True, 'run_id': started['run_id'], 'state': started['state'],
                    'route': selected, 'evidence_location': attempt['evidence_location'],
                    'intent_id': intent_id}
        if status.get('notices'):
            # A replaced customised copy or moved legacy backup is reported, not hidden.
            response['notices'] = status['notices']
        return response
    with edit_ledger(root, feature, ('intent_id', intent_id)) as ledger:
        find_intent(ledger, intent_id).update(status='blocked', ended_at=stamp(),
                                              result_summary='No configured route could start')
    raise delegation.DelegationError('DELEGATION_ROUTES_UNAVAILABLE: ' + identity)


def start(root, feature, identity, work_type=None, task_file=None, cwd=None,
          token=None, timeout=None):
    root = root.resolve()
    feature = feature_identity(root, feature)
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
    delegation.require_no_maintenance(root)
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
    full_identity = feature + '/' + identity
    # Fast rejection only; candidate_start re-checks inside the ledger lock.
    reserve(read_ledger(root, feature), full_identity, None)
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


# Wording the supported agent CLIs and their provider APIs use when a
# requested model is unknown, retired or not available to the account.
MODEL_ERROR = re.compile(
    r'unknown model|invalid model|unsupported model|model_not_found|'
    r'\bmodel\b[^\n]{0,160}?(?:not found|does not exist|may not exist|(?:is )?not available|'
    r'(?:is )?not supported|unavailable)|'
    r'not_found_error[^\n]{0,200}?\bmodel\b|\bmodel\b[^\n]{0,200}?not_found_error', re.I)


# Provider error codes that only ever mean the requested model was refused.
MODEL_ERROR_CODE = re.compile(r'"(?:code|type)"\s*:\s*"model_not_found"|'
                              r'not_found_error[^\n]{0,200}?\bmodel\b', re.I)
STDERR_TAIL_LINES = 40


def model_rejected(result, requested_model=None):
    """True when the CLI refused the requested model, not when work merely mentions one.

    Worker output such as "Model matching query does not exist" from a test run
    must not count. When a model was requested, a wording match must name that
    model; a structured provider code needs no name. stderr is read only from
    its tail, where a CLI prints its terminal error.
    """
    texts = [str(result.get('status_reason') or '')]
    stderr = (result.get('artifacts') or {}).get('stderr')
    if stderr and Path(stderr).is_file():
        lines = Path(stderr).read_text(encoding='utf-8', errors='replace').splitlines()
        texts += lines[-STDERR_TAIL_LINES:]
    name = str(requested_model or '').casefold()
    for index, text in enumerate(texts):
        if MODEL_ERROR_CODE.search(text):
            return True
        if not MODEL_ERROR.search(text):
            continue
        if name:
            if name in text.casefold():
                return True
        elif index == 0:
            # No model was requested: only the driver's own status reason can
            # say the CLI default was refused.
            return True
    return False


def measured_no_edits(payload):
    """True only when the driver measured the whole run window and saw no change."""
    if payload.get('coverage_complete') is not True:
        return False
    return (payload.get('dirty_paths_changed') == [] and
            isinstance(payload.get('dirty_paths_changed'), list) and
            payload.get('head_changed') is False and payload.get('index_changed') is False)


def bookkeeping_paths(root, feature, attempt, payload):
    """Repository-relative paths only the dispatcher writes while a run is live.

    The driver reports paths relative to the repository of the run's cwd. The
    ledger belongs to that repository only when the run works in this checkout;
    in a separate worktree its copy of the ledger is ordinary worker output.
    """
    repo = payload.get('repo_root')
    if not repo:
        found = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=root / attempt['cwd'],
                               capture_output=True, text=True, encoding='utf-8')
        repo = found.stdout.strip() if found.returncode == 0 else None
    if not repo:
        return set()
    ledger = delegation.ledger_path(root, feature)
    repo = Path(repo).resolve()
    return {ledger.relative_to(repo).as_posix()} if ledger.is_relative_to(repo) else set()


def worker_measurement(payload, internal, verified):
    """The driver measurement with verified dispatcher bookkeeping removed.

    Unverified bookkeeping stays in place, so it still counts as a worker
    edit; an unknown measurement is never turned into "no edits".
    """
    changed = payload.get('dirty_paths_changed')
    if not verified or not internal or not isinstance(changed, list):
        return payload
    return {**payload, 'dirty_paths_changed': [path for path in changed if path not in internal]}


def measured_change(payload):
    return bool(payload.get('dirty_paths_changed') or payload.get('head_changed') is True or
                payload.get('index_changed') is True)


def retry_plan(policy, attempt, payload, rejected, host):
    """Return (candidates, reason, decision, retry_count) for an automatic retry."""
    if payload['status'] != 'failed':
        return None
    if rejected:
        # A rejected model did no work; keep the configured fallback order
        # rather than trading it for a stronger-tier retry.
        remaining = attempt['route_candidates'][attempt['candidate_index'] + 1:]
        if not remaining or measured_change(payload):
            return None
        return remaining, 'requested model rejected by CLI', 'fallback', attempt['retry_count']
    if (not measured_no_edits(payload) or
            attempt['retry_count'] >= policy['delegation']['stronger_retry']):
        return None
    stronger = delegation.stronger_candidate(policy['delegation'], attempt_to_candidate(attempt), host)
    if not stronger:
        return None
    return ([stronger], 'failed work eligible for one stronger reassignment', 'reassignment',
            attempt['retry_count'] + 1)


def replacement_link(ledger, attempt):
    """Describe an existing replacement so collect never launches a second one."""
    children = live_children(ledger, attempt['run_id'])
    if children:
        child = children[0]
        if child.get('run_id'):
            attempt['replacement_run_id'] = child['run_id']
            return {'run_id': attempt['run_id'], 'status': attempt['status'],
                    'replacement_run_id': child['run_id'], 'decision': 'already re-routed'}
        return {'run_id': attempt['run_id'], 'status': attempt['status'],
                'replacement_intent_id': child['intent_id'], 'decision': 'recover replacement intent'}
    if attempt.get('replacement_run_id'):
        return {'run_id': attempt['run_id'], 'status': attempt['status'],
                'replacement_run_id': attempt['replacement_run_id'],
                'decision': 'already re-routed'}
    if (attempt['status'] not in ACTIVE and
            any(a.get('parent_run_id') == attempt['run_id'] for a in ledger['attempts'])):
        return {'run_id': attempt['run_id'], 'status': attempt['status'],
                'decision': 'replacement intent ended without a run; use start or reassign'}
    return None


def collect(root, feature, run_id, auto_retry=True):
    root = root.resolve()
    feature = feature_identity(root, feature)
    delegation.require_no_maintenance(root)
    policy = workflow.load_policy(root)
    with edit_ledger(root, feature) as ledger:
        attempt = find_run(ledger, run_id)
        delegation.require(attempt is not None, 'DELEGATION_RUN_UNKNOWN: ' + run_id)
        linked = replacement_link(ledger, attempt)
    if linked:
        return linked
    driver = pinned_driver(root, attempt)
    node = shutil.which('node')
    delegation.require(node is not None, 'NODE_MISSING')
    result = subprocess.run([node, driver, 'collect', run_id, '--json'],
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
    rejected = model_rejected(payload, attempt['requested_model'])
    raw_changed = payload.get('dirty_paths_changed')
    internal = []
    if isinstance(raw_changed, list) and any(str(path).endswith('/workflow/delegations.json')
                                             for path in raw_changed):
        owned = bookkeeping_paths(root, feature, attempt, payload)
        internal = sorted(path for path in raw_changed if path in owned)
    with edit_ledger(root, feature) as ledger:
        attempt = find_run(ledger, run_id)
        # Under the ledger lock, before this edit saves: the ledger is Sanduq's
        # bookkeeping only if nothing but a dispatcher has written it since
        # this run started. edit_ledger marks a live run the moment it sees a
        # foreign write, even when a later dispatcher save has hidden it.
        verified = (bool(internal) and ledger_written_by_dispatcher(root, feature) and
                    not attempt.get('ledger_foreign_write_seen'))
        measured = worker_measurement(payload, internal, verified)
        attempt['status'] = payload['status']
        attempt.setdefault('ended_at', stamp())
        attempt['result_summary'] = str(payload.get('summary') or '')[:2000]
        attempt['status_provenance'] = payload.get('status_provenance')
        attempt['actual_harness'] = payload.get('harness')
        attempt['actual_model'] = payload.get('actual_model') if payload.get('model_observed') is True else None
        attempt['actual_model_evidence'] = 'harness-reported' if attempt['actual_model'] else 'unverified'
        attempt['token_usage'] = payload.get('tokens') if (payload.get('tokens') or {}).get('fidelity') in ('exact', 'partial') else None
        # The raw driver measurement stays on record next to the attribution.
        attempt['changed_paths'] = raw_changed
        attempt['dispatcher_paths_changed'] = internal if verified else []
        attempt['unattributed_bookkeeping_paths'] = [] if verified else internal
        attempt['worker_changed_paths'] = measured.get('dirty_paths_changed')
        attempt['model_rejected'] = rejected
        attempt['evidence_location'] = relative(root, Path((payload.get('artifacts') or {}).get('dir',
                                                        root / '.delegate/runs' / run_id)) / 'result.json')
        linked = replacement_link(ledger, attempt)
        attempt = copy.deepcopy(attempt)
    response = {'run_id': run_id, 'status': attempt['status'],
                'requested_model': attempt['requested_model'],
                'actual_model': attempt['actual_model'],
                'actual_model_evidence': attempt['actual_model_evidence'],
                'harness': attempt['actual_harness'], 'evidence_location': attempt['evidence_location'],
                'token_usage': attempt['token_usage'], 'result_summary': attempt['result_summary'],
                'changed_paths': attempt['changed_paths'],
                'worker_changed_paths': attempt['worker_changed_paths'],
                'dispatcher_paths_changed': attempt['dispatcher_paths_changed']}
    if linked:
        return {**response, **linked}
    plan = retry_plan(policy, attempt, measured, rejected, workflow.active_host(root)) if auto_retry else None
    if not plan:
        return response
    remaining, reason, kind, retry_count = plan
    task_path = root / attempt['task_file']
    delegation.require(task_path.is_file(), 'DELEGATION_BRIEF_MISSING_FOR_RETRY')
    try:
        replacement = candidate_start(root, feature, attempt['identity'], attempt['task_type'],
                                      remaining, task_path, root / attempt['cwd'],
                                      attempt['timeout'], parent_run_id=run_id,
                                      retry_count=retry_count,
                                      decision={'at': stamp(), 'identity': attempt['identity'],
                                                'requested': attempt_to_candidate(attempt),
                                                'decision': kind, 'reason': reason,
                                                'after_run_id': run_id})
    except delegation.DelegationError as error:
        if not str(error).startswith(('DELEGATION_ALREADY_REASSIGNED', 'DELEGATION_ALREADY_RUNNING')):
            raise
        # A concurrent collect or reassign re-routed this run first.
        return {**response, **(replacement_link(read_ledger(root, feature), attempt) or
                               {'decision': 'already re-routed'})}
    with edit_ledger(root, feature) as ledger:
        find_run(ledger, run_id)['replacement_run_id'] = replacement['run_id']
    return {**response, 'replacement': replacement, 'decision': reason}


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
    feature = feature_identity(root, feature)
    delegation.require(isinstance(reason, str) and reason.strip(),
                       'DELEGATION_REASSIGN_REASON_REQUIRED')
    delegation.require_no_maintenance(root)
    policy = workflow.load_policy(root)
    config = policy['delegation']
    delegation.require(config['enabled'], 'DELEGATION_DISABLED')
    ledger = read_ledger(root, feature)
    prior = find_run(ledger, run_id)
    delegation.require(prior is not None and prior.get('status') in
                       ('successful', 'failed', 'abandoned'), 'DELEGATION_PRIOR_RUN_NOT_TERMINAL')
    delegation.require(prior['retry_count'] < config['stronger_retry'],
                       'DELEGATION_RETRY_LIMIT_REACHED')
    delegation.require(not prior.get('replacement_run_id') and not live_children(ledger, run_id) and
                       not any(a['identity'] == prior['identity'] and a['status'] in ACTIVE
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
    replacement = candidate_start(root, feature, prior['identity'], prior['task_type'],
                                  [stronger], brief, root / prior['cwd'], prior['timeout'],
                                  parent_run_id=run_id, retry_count=prior['retry_count'] + 1,
                                  decision={'at': stamp(), 'identity': prior['identity'],
                                            'requested': attempt_to_candidate(prior),
                                            'decision': 'reassignment', 'reason': reason.strip(),
                                            'after_run_id': run_id})
    with edit_ledger(root, feature) as ledger:
        find_run(ledger, run_id)['replacement_run_id'] = replacement['run_id']
    return replacement


def recover_intent(root, feature, intent_id):
    """Recover a driver run created just before its Sanduq ledger write."""
    root = root.resolve()
    feature = feature_identity(root, feature)
    delegation.require_no_maintenance(root)
    with edit_ledger(root, feature) as ledger:
        intent = find_intent(ledger, intent_id)
        delegation.require(intent is not None, 'DELEGATION_INTENT_UNKNOWN')
        if intent.get('run_id'):
            return {'found': True, 'run_id': intent['run_id'], 'status': intent['status']}
        delegation.require(intent['status'] == 'starting', 'DELEGATION_INTENT_NOT_STARTING')
        found = intent_runs(root, intent_id, dismissed_runs(intent))
        delegation.require(len(found) <= 1, 'DELEGATION_INTENT_AMBIGUOUS')
        if not found:
            return {'found': False, 'status': 'starting', 'intent_id': intent_id,
                    'next': 'abandon the intent with a reason, then dispatch the work again'}
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
    return {'found': True, 'run_id': meta['run_id'], 'status': 'running'}


def abandon_intent(root, feature, intent_id, reason):
    """Close a start intent that provably has no driver run so the work can be dispatched again."""
    root = root.resolve()
    feature = feature_identity(root, feature)
    delegation.require(isinstance(reason, str) and reason.strip(),
                       'DELEGATION_ABANDON_REASON_REQUIRED')
    delegation.require_no_maintenance(root)
    with edit_ledger(root, feature) as ledger:
        intent = find_intent(ledger, intent_id)
        delegation.require(intent is not None, 'DELEGATION_INTENT_UNKNOWN')
        delegation.require(intent.get('status') == 'starting' and not intent.get('run_id'),
                           'DELEGATION_INTENT_NOT_STARTING')
        delegation.require(not intent_runs(root, intent_id, dismissed_runs(intent)),
                           'DELEGATION_INTENT_HAS_RUN: recover intent ' + intent_id)
        if not intent.get('start_error'):
            # No launch outcome was recorded: a dispatcher may still be inside
            # its driver start, and the run's meta.json could appear any moment.
            age = datetime.now(timezone.utc) - datetime.fromisoformat(intent['started_at'])
            delegation.require(age.total_seconds() >= ABANDON_GRACE_SECONDS,
                               'DELEGATION_INTENT_START_IN_PROGRESS: retry after ' +
                               str(ABANDON_GRACE_SECONDS) + ' seconds')
        intent.update(status='intent-abandoned', ended_at=stamp(), abandon_reason=reason.strip())
        ledger['route_decisions'].append({'at': stamp(), 'identity': intent['identity'],
                                          'decision': 'intent-abandoned', 'intent_id': intent_id,
                                          'reason': reason.strip()})
    return {'intent_id': intent_id, 'identity': intent['identity'], 'status': 'intent-abandoned'}


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
    abandon_cmd = sub.add_parser('abandon')
    abandon_cmd.add_argument('--feature', required=True)
    abandon_cmd.add_argument('--intent-id', required=True)
    abandon_cmd.add_argument('--reason', required=True)
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
        elif args.action == 'abandon':
            result = abandon_intent(args.root, args.feature, args.intent_id, args.reason)
        else:
            result = reassign(args.root, args.feature, args.run_id, args.reason, args.task_file)
        print(json.dumps(result, indent=2))
        return 0
    except (delegation.DelegationError, workflow.WorkflowError, OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
