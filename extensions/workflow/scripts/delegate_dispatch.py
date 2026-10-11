#!/usr/bin/env python3
"""Launch and collect model-aware Sanduq work through the delegate-task driver.

The dispatcher keeps the workflow claim. A successful delegated run is evidence
for its orchestrator to review, never an automatic passed stage or completed task.
"""
from __future__ import annotations

import argparse
import copy
import getpass
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

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
# Terminal ledger outcomes for a run, including the light-tier guard's own
# ``unverified`` (B12): a driver-reported ``successful`` at a light tier with
# no raw counts or produced-file evidence. Only a standard-tier reassignment
# or ``accept`` running the acceptance command independently resolves it; a
# note never does, because there is no ledger path that accepts free text.
TERMINAL_STATUSES = ('successful', 'failed', 'abandoned', 'unverified')
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
    build) counts as foreign too: nothing proves who wrote it. Used only for
    worker-edit attribution (bookkeeping paths, retry decisions); it is
    deliberately broad, since a missing marker is common and not itself
    suspicious there. ``ledger_genuinely_tampered`` below is the narrower
    check for the sticky trust flag (round 3, finding 2).
    """
    return (delegation.ledger_path(root, feature).exists() and
            not ledger_written_by_dispatcher(root, feature))


def ledger_genuinely_tampered(root, feature):
    """True only when the ordinary written marker exists but disagrees with
    the ledger's current bytes -- never merely absent (round 3, findings 1-2).

    A fresh clone or CI checkout has no marker at all and is not itself
    suspicious (see ``delegation.ledger_trust_state``'s ``'unverified-local'``);
    a marker that WAS established and now disagrees means something changed
    the ledger without a tracked dispatcher write since.
    """
    recorded = workflow.read(written_marker(root, feature), {}).get('sha256')
    if recorded is None:
        return False
    return recorded != ledger_bytes_digest(delegation.ledger_path(root, feature))


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
        if ledger_genuinely_tampered(root, feature):
            # A real tamper (not merely a missing marker): persist the sticky
            # flag before this edit's own save would otherwise re-anchor the
            # marker at the new bytes and quietly launder it away (round 3,
            # finding 2). Only trust-reset clears it.
            delegation.record_foreign_write(root, feature)
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


# Appended only for the light-eligible qa_collect route (an explicit [collect]
# marker or a per-task override put it there, never a heuristic): the worker
# must self-report parsable evidence, because a light-tier result without it
# stays unverified and is never accepted on a bare claim of success.
QA_COLLECT_ADDENDUM = (
    'This is a light-tier collection task: run the existing check and report its result; do not '
    'author new tests or code. In your final summary, report either raw reporter counts as JSON '
    '({"total": N, "passed": N, "failed": N}) or your test runner\'s own summary line (for example '
    'pytest\'s "N passed, N failed", Jest\'s "Tests: N failed, N passed, N total", or a JUnit '
    'console summary), or a produced-file list as JSON ({"files": ["<path>", ...]}) with paths '
    'relative to your working directory. Without one of these the result stays unverified and is '
    'not accepted.\n'
)


# Round 4, finding 1: nothing else stops a worker from running the
# dispatcher's own commands on its own or another task's run -- collecting or
# accepting its own light-tier result, reassigning another attempt, or
# resetting a trust flag it has no business seeing, let alone clearing.
# trust-reset in particular is orchestrator-only and human-authorised: it
# records an actor and a reason precisely because only a human reviewing an
# actual diff may decide a detected tamper is benign.
NO_DISPATCHER_COMMANDS = (
    'Never run delegate_dispatch.py yourself (start, collect, accept, reassign, recover, abandon, '
    'adopt or trust-reset) -- not on this run, another run, or another task. Those are the '
    'dispatcher\'s own commands; trust-reset in particular is an orchestrator-only, '
    'human-authorised decision, and adopt is orchestrator-only for the same reason -- a worker must '
    'never be the one judging whether its own unattempted work now counts as verified.\n'
)


# The delegated Execute stage is the one exception (round 10, finding 1):
# its own job is to dispatch and resolve bounded task workers with exactly
# the commands every other brief forbids outright. Its environment
# (SANDUQ_DELEGATED_ROLE=orchestrator plus SANDUQ_DELEGATED_FEATURE, never
# SANDUQ_DELEGATED_RUN; set by driver_env for this launch alone) and
# require_not_worker_context's role-aware check both grant that narrower
# scope, so its brief states the narrower rule instead of the blanket one.
EXECUTE_ORCHESTRATOR_DISPATCHER_COMMANDS = (
    'As the Execute orchestrator you may run delegate_dispatch.py start, collect, recover, abandon, '
    'accept, reassign or adopt for this feature\'s own T### tasks only -- that is how you dispatch and '
    'resolve bounded workers. Never trust-reset, and never a stage:* identity or another feature\'s '
    'tasks; the dispatcher enforces this scope itself (DELEGATION_ORCHESTRATOR_SCOPE) and refuses '
    'anything outside it.\n'
)


def stage_brief(root, feature, stage, token, work_type=None):
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
    text = (
        f'Execute only the Sanduq {stage} stage for {feature}, bound to {state["issue"]}.\n'
        f'The dispatcher already owns claim {token}; do not call workflow claim, complete, next, '
        'migrate, recover or another stage.\n'
        f'Read the installed workflow skill and {command_file or "the workflow stage contract"}; '
        f'invoke {command} once inside this claim. Respect all existing binding, evidence and human '
        'decision gates. If a decision is needed, use the existing GitHub decision adapter and '
        'report the pending decision to the dispatcher.\n'
        'Return the concrete input paths, evidence paths, checks executed and any blocker. '
        'The dispatcher will inspect them and complete the receipt; your own success claim is '
        'not a passed Sanduq stage. ' + ownership +
        (EXECUTE_ORCHESTRATOR_DISPATCHER_COMMANDS if stage == 'execute' else NO_DISPATCHER_COMMANDS)
    )
    return text + QA_COLLECT_ADDENDUM if work_type == 'qa_collect' else text


def task_brief(root, feature, task_id, work_type=None):
    description = task_description(root, feature, task_id)
    text = (
        f'Implement only {task_id} for {feature}: {description}\n'
        f'Read {feature}/spec.md, plan.md and tasks.md, project instructions, and the Sanduq '
        'execution protocol. Respect the assigned files, dependencies and shared resources '
        'provided by the orchestrator. Run relevant checks and return paths to real evidence. '
        'Do not stage, commit, push, change task checkboxes, update the shared progress report, '
        'claim workflow stages or close GitHub issues. The orchestrator will review and integrate '
        'your work.\n' + NO_DISPATCHER_COMMANDS
    )
    return text + QA_COLLECT_ADDENDUM if work_type == 'qa_collect' else text


def brief_file(root, text):
    directory = root / '.delegate/briefs'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (uuid.uuid4().hex + '.txt')
    path.write_text(text, encoding='utf-8')
    return path


def driver_env(root, run_context=None, role=None, feature=None):
    """Environment for the driver subprocess and, through it, every worker it
    spawns underneath.

    Two, mutually exclusive shapes (round 10, finding 1 refines round 9's
    single ``SANDUQ_DELEGATED_RUN``): a plain worker -- any task, and any
    stage other than ``execute`` -- gets ``SANDUQ_DELEGATED_RUN`` set to
    this dispatch's own intent id (``run_context``; the driver, outside
    this project's scope, assigns the eventual ``run_id`` itself, only
    after the worker is already spawned, so the intent id is the
    identifying token available at spawn time). The delegated Execute
    stage is different: its own brief tells it to dispatch and resolve
    bounded task workers with the dispatcher's own commands, so it gets
    ``SANDUQ_DELEGATED_ROLE=orchestrator`` and ``SANDUQ_DELEGATED_FEATURE``
    instead, never ``SANDUQ_DELEGATED_RUN``. Either variant strips the
    other's variables from the *returned* environment (never mutates
    ``os.environ`` itself): a task worker the Execute orchestrator launches
    inherits the orchestrator's own ambient environment via
    ``os.environ.copy()`` below, and must not carry its role forward.

    ``require_not_worker_context`` reads these to refuse a worker outright
    (``DELEGATION_WORKER_CONTEXT``) and to scope the orchestrator to its
    own feature's tasks (``DELEGATION_ORCHESTRATOR_SCOPE``). Defence in
    depth only, not a security boundary: either process could unset its
    variables before invoking the dispatcher, so each brief's own
    instruction remains the primary control.
    """
    env = os.environ.copy()
    env['DELEGATE_RUNS_DIR'] = str(root / '.delegate/runs')
    if role == 'orchestrator':
        env['SANDUQ_DELEGATED_ROLE'] = 'orchestrator'
        env['SANDUQ_DELEGATED_FEATURE'] = feature
        env.pop('SANDUQ_DELEGATED_RUN', None)
    elif run_context:
        env['SANDUQ_DELEGATED_RUN'] = run_context
        env.pop('SANDUQ_DELEGATED_ROLE', None)
        env.pop('SANDUQ_DELEGATED_FEATURE', None)
    return env


def require_not_worker_context(feature=None, task_identity=None):
    """Refuse when this process is itself running inside a delegated
    process tree, worker or orchestrator (round 9, finding 1a; role-aware
    since round 10, finding 1).

    A plain worker (``SANDUQ_DELEGATED_RUN`` set) is refused outright and
    unconditionally: ``DELEGATION_WORKER_CONTEXT``. This is checked first
    and always wins (round 11, finding 1) -- ``SANDUQ_DELEGATED_RUN`` set
    at all means a real worker process tree exists underneath this one,
    whatever ``SANDUQ_DELEGATED_ROLE``/``SANDUQ_DELEGATED_FEATURE`` also
    happen to read, so that combination is never treated as the
    orchestrator. The delegated Execute orchestrator
    (``SANDUQ_DELEGATED_ROLE=orchestrator`` plus
    ``SANDUQ_DELEGATED_FEATURE``, with no ``SANDUQ_DELEGATED_RUN``) is
    allowed through, but only for a ``T###`` ``task_identity`` belonging to
    that same feature; ``trust-reset`` (which has no task to name, so
    always passes ``task_identity=None``), any ``stage:*`` identity, and
    any other feature all refuse with ``DELEGATION_ORCHESTRATOR_SCOPE``.
    Called by ``start``, ``collect``, ``recover``, ``abandon``, ``accept``,
    ``reassign``, ``adopt`` and ``trust-reset`` once ``feature`` and the
    identity in question, if any, are known. With neither variable set --
    an ordinary, undelegated orchestrator call -- both checks pass
    silently.
    """
    delegation.require(not delegation.delegated_run_id(),
                       'DELEGATION_WORKER_CONTEXT: this process is running inside a delegated worker '
                       '(SANDUQ_DELEGATED_RUN is set); only the orchestrator may run this command')
    if delegation.delegated_role() == 'orchestrator':
        role_feature = os.environ.get('SANDUQ_DELEGATED_FEATURE')
        allowed = (task_identity is not None and re.fullmatch(r'T\d{3,}', task_identity) is not None and
                  feature is not None and feature == role_feature)
        delegation.require(allowed,
                           'DELEGATION_ORCHESTRATOR_SCOPE: a delegated Execute orchestrator may only '
                           'start, collect, recover, abandon, accept, reassign or adopt a T### task of '
                           'its own feature (' + str(role_feature) + '); never trust-reset, a stage:* '
                           'identity, or another feature')


class StartFailed(delegation.DelegationError):
    """The driver process exited or never spawned, so its run directory is final."""

    def __init__(self, message, exit_code=None):
        super().__init__(message)
        self.exit_code = exit_code


# delegate.mjs exit code when its supervisor never acknowledged the start.
SUPERVISOR_START_FAILED = 5


def launch(root, driver, candidate, cwd, task, timeout, intent_id=None, orchestrator_feature=None):
    """Start one worker through the driver.

    ``orchestrator_feature``, given only for the ``stage:execute`` launch
    itself (round 10, finding 1), selects the orchestrator environment
    shape from ``driver_env`` in place of the ordinary worker one; every
    other launch -- any task, any other stage -- is unaffected. ``--keep-
    env`` is passed for all three ``SANDUQ_DELEGATED_*`` names regardless
    (round 10, finding 2), so a future ``--clean-env`` launch does not
    silently drop whichever of them this call actually set; it has no
    effect at all without ``--clean-env``, which nothing here passes.
    """
    node = shutil.which('node')
    if node is None:
        raise StartFailed('NODE_MISSING')
    args = [node, driver, 'start', '--harness', candidate['harness'], '--cwd', str(cwd),
            '--timeout', str(timeout), '--task', task,
            '--keep-env', 'SANDUQ_DELEGATED_RUN', '--keep-env', 'SANDUQ_DELEGATED_ROLE',
            '--keep-env', 'SANDUQ_DELEGATED_FEATURE']
    if candidate['requested_model']:
        args += ['--model', candidate['requested_model']]
    if candidate.get('read_only'):
        args.append('--sandbox')
    if candidate.get('allow_commit'):
        args.append('--allow-commit')
    if intent_id:
        args += ['--constraint', 'Sanduq delegation intent: ' + intent_id]
    env = driver_env(root, run_context=intent_id,
                     role='orchestrator' if orchestrator_feature else None,
                     feature=orchestrator_feature)
    try:
        result = subprocess.run(args, cwd=root, env=env,
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
                    timeout, parent_run_id=None, retry_count=0, decision=None, owned_paths=None,
                    claim_token=None, pinned=False):
    config = workflow.load_policy(root)['delegation']
    status = delegation.doctor(root, workflow.active_host(root), install=True,
                               scope=config['install_scope'])
    delegation.require(status['ok'], delegation.health_error(status))
    # An explicit pin never falls back: an unavailable harness is refused
    # before any ledger intent exists, not skipped to another candidate.
    delegation.require(not pinned or status['harnesses'].get(candidates[0]['harness']),
                       'DELEGATION_PINNED_ROUTE_UNAVAILABLE: ' + candidates[0]['harness'] +
                       ' is not available; the explicit choice is not replaced by another route')
    task = task_path.read_text(encoding='utf-8')
    intent_id = uuid.uuid4().hex
    # The owned paths a light-tier result's evidence must resolve inside
    # (finding 8a); recorded at start so accept and the summary-evidence guard
    # in collect share one authoritative record instead of assuming the whole
    # cwd. Carried forward unchanged across a retry or reassignment.
    owned_paths = list(owned_paths) if owned_paths else ['.']
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
                                   'owned_paths': owned_paths, 'route_candidates': candidates,
                                   'driver': relative(root, status['driver']),
                                   'claim_token': claim_token, 'pinned': bool(pinned),
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
            started = launch(root, status['driver'], selected, cwd, task, timeout, intent_id,
                             orchestrator_feature=feature if identity.endswith('/stage:execute') else None)
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
                   'cwd': relative(root, cwd), 'timeout': timeout, 'owned_paths': owned_paths,
                   'claim_token': claim_token, 'pinned': bool(pinned),
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


def pin_candidate(candidates, harness, model):
    """The one candidate an explicit ``--harness``/``--model`` pair names, exactly.

    The pair is checked against the already resolved route (a task override,
    the configured route or the frozen stage snapshot); it never adds a
    candidate and never widens a role allowlist. Returns (candidate, index).
    """
    delegation.require(bool(harness) and bool(model),
                       'DELEGATION_PIN_INCOMPLETE: --harness and --model must be given together')
    for index, candidate in enumerate(candidates):
        if candidate['harness'] == harness and candidate['requested_model'] == model:
            return candidate, index
    allowed = ', '.join(c['harness'] + '/' + str(c['requested_model']) for c in candidates)
    raise delegation.DelegationError(
        'DELEGATION_PIN_NOT_ELIGIBLE: ' + harness + '/' + model + ' is not an eligible candidate '
        'for this work; eligible: ' + allowed + '. Choosing a model for one stage does not '
        'authorise it for another; the role allowlist is unchanged')


def start(root, feature, identity, work_type=None, task_file=None, cwd=None,
          token=None, timeout=None, owned=None, harness=None, model=None):
    root = root.resolve()
    feature = feature_identity(root, feature)
    require_not_worker_context(feature, identity)
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
        stage_type = delegation.stage_work_type(checkpoint.get('commands', {}), stage,
                                                config.get('fixed_collection_commands'))
        delegation.require(work_type in (None, stage_type),
                           'DELEGATION_STAGE_TYPE_MISMATCH: ' + identity + ' is a ' + stage_type +
                           ' stage; --type ' + str(work_type) + ' cannot change it')
        work_type = stage_type
        text = stage_brief(root, feature, stage, token, work_type)
    else:
        description = task_description(root, feature, identity)
        work_type = work_type or delegation.task_type(description)
        delegation.require(work_type in delegation.TYPES, 'DELEGATION_TASK_TYPE_INVALID')
        text = task_brief(root, feature, identity, work_type)
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
    # A light-tier or qa_collect start must declare its owned paths itself
    # (finding 4, round 2): the evidence guard needs a bounded set to check
    # summary or accept file evidence against, not a silent default to the
    # whole working directory. Any candidate in the whole fallback chain
    # being light is enough (round 3, finding 6): a fallback beyond the
    # preferred candidate can still land the run on the light tier.
    pinned = bool(harness or model)
    if pinned:
        chosen, original_index = pin_candidate(candidates, harness, model)
        candidates = [chosen]
    requires_owned = work_type == 'qa_collect' or any(c.get('tier') == 'light' for c in candidates)
    delegation.require(not requires_owned or owned,
                       'DELEGATION_OWNED_PATHS_REQUIRED: a light-tier or qa_collect start must declare '
                       '--owned <path> (repeatable); the light-tier evidence guard checks file evidence '
                       'against a bounded owned-path set, never the whole working directory by default')
    return candidate_start(root, feature, full_identity, work_type, candidates,
                           task_path, cwd, timeout, owned_paths=owned,
                           claim_token=token if identity.startswith('stage:') else None,
                           pinned=pinned,
                           decision={'at': stamp(), 'identity': full_identity,
                                     'requested': candidates[0], 'decision': 'explicit-pin',
                                     'candidate_index': original_index,
                                     'reason': 'Explicit --harness/--model pair matched an eligible '
                                               'candidate; no fallback outside it'} if pinned else None)


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
    if payload['status'] != 'failed' or attempt.get('pinned'):
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


# ---------------------------------------------------------------------------
# Light-tier evidence (B12): a light-tier run is accepted only when its result
# carries raw reporter counts or a produced-file list, never on a bare claim
# of success. The same parsers serve ``collect`` (reading a worker's own
# self-reported summary) and ``accept`` (reading an acceptance command's own
# output, run independently by the orchestrator); only the latter is
# authoritative verification, but both apply the identical, documented schema.
# ---------------------------------------------------------------------------

LIGHT_TIER_EVIDENCE_MISSING_REASON = (
    'LIGHT_TIER_EVIDENCE_MISSING: a light-tier result needs parsable reporter counts '
    '(total > 0, failed = 0) or a produced-file list inside the task\'s owned paths; run '
    '"delegate_dispatch.py accept --run-id <id> --command <acceptance command> --expect '
    'counts|files", or reassign to a standard tier')


def _parse_json_object(text):
    """The whole text, or its single outermost ``{...}`` block, parsed as a JSON object."""
    text = (text or '').strip()
    if not text:
        return None
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except ValueError:
        pass
    match = re.search(r'\{.*\}', text, re.S)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else None
    except ValueError:
        return None


def _as_int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _counts_from_json(obj):
    total, passed, failed = _as_int(obj.get('total')), _as_int(obj.get('passed')), _as_int(obj.get('failed'))
    if total is not None and failed is not None:
        return {'total': total, 'passed': passed if passed is not None else total - failed, 'failed': failed}
    tests, failures, errors = _as_int(obj.get('tests')), _as_int(obj.get('failures')), _as_int(obj.get('errors'))
    if tests is not None and failures is not None:
        failed = failures + (errors or 0)
        return {'total': tests, 'passed': tests - failed, 'failed': failed}
    return None


def _counts_from_block(block):
    """Extract passed/failed/total keyword counts from one span, order-independent.

    A single reporter line or block may list its outcomes in any order (real
    pytest and Jest summaries put failures before passes); this reads every
    ``N <keyword>`` pair in the span regardless of position instead of
    assuming a fixed sequence (finding 2: order-dependent matching silently
    read only the first "N passed" and missed an earlier "N failed").
    """
    found = {}
    for number, word in re.findall(r'(\d+)\s+(passed|failed|errors?|total|skipped)\b', block, re.I):
        found[word.lower()] = found.get(word.lower(), 0) + int(number)
    failed = found.get('failed', 0) + found.get('error', 0) + found.get('errors', 0)
    if 'total' in found:
        total = found['total']
        passed = found.get('passed', total - failed)
    elif 'passed' in found or failed:
        passed = found.get('passed', 0)
        total = passed + failed
    else:
        return None
    if total <= 0:
        return None
    return {'total': total, 'passed': passed, 'failed': failed}


def _block_counts(match):
    return _counts_from_block(match.group(1))


def _counts_from_labeled_block(block):
    """Extract ``Label: N`` pairs (label first, unlike pytest/Jest): JUnit/Maven's
    Tests run/Failures/Errors/Skipped, and dotnet test's Total/Passed/Failed/Skipped.
    An ``[INFO]``/``[ERROR]`` line prefix (Maven's own convention) is not part
    of any label and does not stop it matching.
    """
    found = {}
    for label, number in re.findall(
            r'(Tests(?:\s+run)?|Total\s+tests|Failures|Errors|Skipped|Total|Passed|Failed)\s*:\s*(\d+)',
            block, re.I):
        key = re.sub(r'\s+', ' ', label.strip().lower())
        found[key] = found.get(key, 0) + int(number)
    total = found.get('tests run', found.get('tests', found.get('total tests', found.get('total'))))
    failed = found.get('failures', 0) + found.get('errors', 0) + found.get('failed', 0)
    passed = found.get('passed')
    if total is None:
        if passed is None:
            return None
        total = passed + failed
    if total <= 0:
        return None
    return {'total': total, 'passed': passed if passed is not None else total - failed, 'failed': failed}


def _labeled_block_counts(match):
    return _counts_from_labeled_block(match.group(1))


def _unittest_ok_counts(match):
    total = int(match[1])
    return {'total': total, 'passed': total, 'failed': 0}


def _unittest_failed_counts(match):
    total = int(match[1])
    parts = dict(re.findall(r'(failures|errors)=(\d+)', match[2], re.I))
    failed = int(parts.get('failures', 0)) + int(parts.get('errors', 0))
    if failed <= 0:
        return None
    return {'total': total, 'passed': total - failed, 'failed': failed}


# node's --test runner writes each summary field on its own TAP comment line,
# not necessarily adjacent to the others (real output interleaves "# suites",
# "# cancelled", "# duration_ms" and similar between them), so these are
# matched independently by ``parse_counts`` rather than as one contiguous span.
NODE_TEST_FIELDS = {'total': re.compile(r'^#\s*tests\s+(\d+)\s*$', re.I | re.M),
                    'passed': re.compile(r'^#\s*pass\s+(\d+)\s*$', re.I | re.M),
                    'failed': re.compile(r'^#\s*fail\s+(\d+)\s*$', re.I | re.M)}


def _node_test_counts(text):
    matches = {key: list(pattern.finditer(text)) for key, pattern in NODE_TEST_FIELDS.items()}
    if not all(matches.values()):
        return None
    return {key: int(items[-1][1]) for key, items in matches.items()}


# Every pattern requires the real framing a genuine reporter transcript has,
# never a bare "N passed, N failed" substring that could appear in prose or
# be pasted out of context (finding 2's probes: "3 failed, 10 passed in
# 0.52s" with no "====" bars, a bare "Tests run: 3, Failures: 0" with no
# "Results:" section, and "I ran it: 10 passed, 0 failed" all match nothing
# below and so parse to None, never a false "failed: 0"). See the format list
# documented on QA_COLLECT_ADDENDUM, the README delegation section and here:
#   1. pytest's "===== ... in N.Ns =====" summary bar. Its category prefers
#      any occurrence with failed > 0 over the chronologically last one
#      (round 2, finding 6c): a "rerun failed only" pytest invocation can
#      print an earlier bar with real failures, then a later, clean bar for
#      just the retried subset -- taking the literal last bar would silently
#      report the whole run as passing.
#   2. Jest's "Tests: ..." line.
#   3. JUnit/Maven's aggregate "Results:" section (an "[INFO]"/"[ERROR]" line
#      prefix does not stop it matching), never an earlier per-class
#      "Tests run:" line lacking that header.
#   4. Python unittest's "Ran N tests ..." followed by "OK" or "FAILED (...)".
#   5. dotnet test's "Passed!"/"Failed!" summary line. A multi-project
#      solution prints one such line per project; like pytest, this category
#      prefers any occurrence with failed > 0 over the last one (round 3,
#      finding 4), so one failing project is never hidden behind a later,
#      passing project's clean line.
#   6. dotnet's older VSTest console form, "Total tests: N" with Passed/Failed
#      on the same or following lines.
# node's --test runner "# tests/# pass/# fail" lines are checked separately
# below (they need not be contiguous; see ``_node_test_counts``).
PREFER_FAILED_CATEGORIES = {0, 5}  # pytest's bar, dotnet's Passed!/Failed! line
COUNT_PATTERNS = (
    (re.compile(r'=+([^=\n]*?\bin\s+[\d.]+s[^=\n]*?)=+', re.I), _block_counts),
    (re.compile(r'Tests:([^\n]+)', re.I), _block_counts),
    # A blank line between "Results:" and the aggregate may itself carry a
    # bare log-level prefix ("[INFO]" alone) in real Maven output; skip any
    # number of such blank (optionally bracket-prefixed) lines, not just
    # literally empty ones (round 3, finding 4).
    (re.compile(r'Results:[ \t]*\r?\n(?:[ \t]*(?:\[\w+\])?[ \t]*\r?\n)*[ \t]*([^\n]+)', re.I),
     _labeled_block_counts),
    (re.compile(r'Ran\s+(\d+)\s+tests?\b[^\n]*\r?\n+\s*OK\b', re.I), _unittest_ok_counts),
    (re.compile(r'Ran\s+(\d+)\s+tests?\b[^\n]*\r?\n+\s*FAILED\s*\(([^)]*)\)', re.I), _unittest_failed_counts),
    (re.compile(r'(?:Passed|Failed)!\s*-\s*([^\n]+)', re.I), _labeled_block_counts),
    # dotnet's older VSTest console form, its fields possibly on separate
    # lines; capture "Total tests:" and up to the next few lines.
    (re.compile(r'(Total\s+tests\s*:[^\n]*(?:\r?\n[ \t]*[^\n]*){0,3})', re.I), _labeled_block_counts),
)


def parse_counts(text):
    """Parse total/passed/failed from JSON, or a supported reporter's own framing.

    JSON forms: ``{"total": N, "passed": N, "failed": N}`` (``passed`` optional,
    computed as ``total - failed``), or JUnit-style ``{"tests": N, "failures":
    N, "errors": N}`` (``errors`` optional; ``failed = failures + errors``).

    Text forms (each requires the reporter's own real framing, documented on
    ``COUNT_PATTERNS``; a bare "N passed, N failed" or "Tests run: N,
    Failures: N" without it matches nothing): pytest's summary bar, Jest's
    ``Tests:`` line, a JUnit/Maven ``Results:`` section, Python unittest's
    ``Ran N tests`` plus ``OK``/``FAILED (...)``, dotnet test's
    ``Passed!``/``Failed!`` line, and node ``--test``'s ``# tests``/``#
    pass``/``# fail`` lines.

    Each pattern category is tried independently across the whole text. Most
    categories use only their *last* match (a rerun's final state, not an
    earlier one); pytest's bar and dotnet's ``Passed!``/``Failed!`` line use
    the last match that has ``failed > 0``, if any, else their own last
    match, so a rerun-failed-only pytest invocation, or one failing project
    in a multi-project dotnet solution, cannot hide behind a later, clean
    bar or project. If more than one category produces a match and they
    disagree, the parse is ambiguous and returns ``None`` rather than
    guessing between them.
    """
    obj = _parse_json_object(text)
    if isinstance(obj, dict):
        counts = _counts_from_json(obj)
        if counts:
            return counts
    text = text or ''
    per_category = {}
    for index, (pattern, convert) in enumerate(COUNT_PATTERNS):
        matches = [counts for m in pattern.finditer(text) if (counts := convert(m))]
        if not matches:
            continue
        if index in PREFER_FAILED_CATEGORIES:
            failed_matches = [counts for counts in matches if counts['failed'] > 0]
            per_category[index] = failed_matches[-1] if failed_matches else matches[-1]
        else:
            per_category[index] = matches[-1]
    node_counts = _node_test_counts(text)
    if node_counts:
        per_category['node'] = node_counts
    if not per_category:
        return None
    distinct = {tuple(sorted(counts.items())) for counts in per_category.values()}
    if len(distinct) > 1:
        return None
    return next(iter(per_category.values()))


def parse_files(text):
    """Parse a JSON ``{"files": [...]}`` object, else collect ``FILE: <path>`` lines."""
    obj = _parse_json_object(text)
    if isinstance(obj, dict) and isinstance(obj.get('files'), list):
        items = [str(item) for item in obj['files'] if isinstance(item, str) and item.strip()]
        return items or None
    lines = [line.split(':', 1)[1].strip() for line in (text or '').splitlines()
             if line.strip()[:5].upper() == 'FILE:']
    return lines or None


TRAVERSAL_SEGMENT = re.compile(r'(^|[\\/])\.\.($|[\\/])')


def _path_escapes_relative(text):
    """True when ``text`` is rooted, drive-anchored or otherwise absolute on
    Windows or POSIX, checked explicitly with both flavours rather than the
    host's own ``Path`` class (finding, round 6).

    ``Path.is_absolute()`` alone is not enough on Windows: a root-relative
    path like ``\\x`` (a root but no drive) resolves to the root of whatever
    the *current* drive happens to be, and a drive-relative path like
    ``C:x`` (a drive but no root) resolves relative to that drive's own,
    separately tracked working directory -- both escape the intended
    directory while ``PureWindowsPath.is_absolute()`` requires both a drive
    and a root together and returns ``False`` for each on its own. Checking
    ``PureWindowsPath`` explicitly (not the host's ``Path``) catches this
    even when the code runs on POSIX, where a literal ``C:x`` or ``\\x``
    string would otherwise be treated as an ordinary, safe-looking relative
    path name.
    """
    windows = PureWindowsPath(text)
    if windows.drive or windows.root or windows.is_absolute():
        return True
    return PurePosixPath(text).is_absolute()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def owned_roots(cwd, owned_paths):
    """Resolve each declared owned path relative to ``cwd``; ``None`` on any
    rooted/drive-anchored/absolute path (either flavour) or ``..`` traversal
    in the declaration itself, or on a resolved root that lands outside
    ``cwd`` (for example because the declared name is itself a symlink to
    somewhere else): an owned root is only ever a subdirectory of the task's
    own working directory, never a way to point evidence checks elsewhere.
    """
    cwd = Path(cwd).resolve()
    roots = []
    for raw in (owned_paths or ['.']):
        text = str(raw).strip()
        if not text or _path_escapes_relative(text) or TRAVERSAL_SEGMENT.search(text):
            return None
        try:
            resolved = (cwd / text).resolve()
        except OSError:
            return None
        if not resolved.is_relative_to(cwd):
            return None
        roots.append(resolved)
    return roots or None


def validate_owned_files(cwd, owned_paths, paths):
    """Every path must exist, be non-empty, and resolve inside a declared owned path.

    Defends against rooted/drive-anchored/absolute paths (Windows and POSIX,
    checked explicitly regardless of the host OS -- ``\\x``, ``C:x``,
    ``C:\\x`` and ``//host/x`` are all rejected even though a bare
    ``Path.is_absolute()`` check misses the first two), ``..`` traversal and
    symlink escapes: every remaining candidate is fully resolved (following
    any symlink to its real location) before it is required to stay inside
    both ``cwd`` itself and at least one declared owned path (each resolved
    relative to ``cwd`` and itself required to stay inside it; the whole
    ``cwd`` when none were declared, e.g. a pre-B12-review ledger), so
    neither a symlinked "owned" directory nor a symlinked file can land
    outside the task's own working directory. Any single invalid path fails
    the whole list, matching the guard's "no partial acceptance" rule.
    Returns a list of ``{path, sha256, size}`` records (finding 8a), or
    ``None``.
    """
    cwd = Path(cwd).resolve()
    roots = owned_roots(cwd, owned_paths)
    if roots is None:
        return None
    verified = []
    for raw in paths:
        text = str(raw).strip()
        if not text or _path_escapes_relative(text) or TRAVERSAL_SEGMENT.search(text):
            return None
        try:
            candidate = (cwd / text).resolve()
        except OSError:
            return None
        if not candidate.is_relative_to(cwd) or not any(candidate.is_relative_to(owned) for owned in roots):
            return None
        try:
            if not candidate.is_file():
                return None
            size = candidate.stat().st_size
            if size <= 0:
                return None
        except OSError:
            return None
        verified.append({'path': text, 'sha256': file_sha256(candidate), 'size': size})
    return verified or None


# Size/tier words too generic to prove two model names share a family on
# their own (a "mini" or "pro" variant of two unrelated model lines would
# otherwise look related). Purely numeric tokens (version numbers) are
# excluded the same way in ``model_family_matches``.
# Tokens too generic to prove a family match by themselves: purely numeric
# (version numbers), a bare provider name, or a size/tier word shared across
# an entire, otherwise unrelated model line.
# Words too generic to prove a family match by themselves when they are the
# ONLY non-numeric token in the shorter, contained identifier (checked by
# `model_family_matches` before it even looks at tier qualifiers below).
# "large"/"pro"/"max" live here as bare size/tier words that plenty of
# unrelated model lines reuse, not because they signal a *different* tier the
# way the narrower TIER_QUALIFIER_TOKENS below does -- the two sets serve
# different questions and are not expected to overlap; the round 5 fix that
# narrowed TIER_QUALIFIER_TOKENS to effort words removed 'max'/'pro'/'large'
# from it for exactly that reason.
GENERIC_MODEL_TOKENS = {'gpt', 'claude', 'codex', 'openai', 'anthropic', 'mini', 'small', 'medium',
                        'large', 'pro', 'max', 'lite', 'base', 'preview'}
# A contained run immediately followed by one of these MAY change the
# model's identity rather than merely extend it (round 4, finding 3), but
# unlike a build or date suffix this cannot be told apart from a harmless
# variant by the token alone: "haiku-large-ctx" is still Haiku (a context-
# window variant), while "o4-mini-high" is a genuinely different, more
# expensive reasoning-effort tier of "o4-mini". Limited to actual effort
# words (round 5, finding 1): "large"/"pro"/"max" used to sit here too and
# produced false negatives for real light-tier variants like
# "haiku-large-ctx" or "gpt-6-terra-pro" -- the unsafe direction, since a
# false negative here means a light-tier run's guard is skipped entirely.
# Even for "high"/"xhigh", the exclusion only actually applies when the
# fuller identifier is a policy-configured non-light model (see
# `model_family_matches`'s ``non_light_models``); otherwise the safe
# default is to still match, so the guard is never silently bypassed just
# because a harness-reported name happens to end in an effort word.
TIER_QUALIFIER_TOKENS = {'high', 'xhigh'}


def _model_tokens(model):
    text = re.sub(r'[^a-z0-9]+', '-', str(model or '').strip().lower()).strip('-')
    return [token for token in text.split('-') if token]


def model_family_matches(candidate_model, configured_model, non_light_models=None):
    """True only when the two model identifiers are the same, or one is a
    whole dash-delimited token run inside the other, not immediately followed
    by a *confirmed* tier qualifier (round 3 finding 3, round 4 finding 3,
    round 5 finding 1: a shared-token-anywhere rule was too broad and matched
    unrelated sibling models -- ``claude-opus-4-7`` against
    ``claude-haiku-4-5``, or ``gpt-6-terra-codex`` against
    ``gpt-6-sol-codex`` -- that merely share a provider prefix or a trailing
    qualifier).

    ``"haiku"`` matches ``"claude-haiku-4-5"`` (a whole token inside it);
    ``"claude-haiku-4-5"`` matches ``"claude-haiku-4-5-20251001"`` (a whole
    prefix run of tokens, the harness's own build/date suffix appended). The
    contained run must include at least one token that is not purely a
    version number or a bare provider/size word (``"gpt"``, ``"codex"``,
    ``"openai"``, ``"anthropic"`` and similar), so ``"gpt-6"`` does not match
    ``"gpt-6-sol"`` (every sibling in that family shares that generic
    prefix) and bare ``"codex"`` does not match ``"gpt-6-sol-codex"``.

    A match is rejected for a contained run immediately followed by an
    effort word (``"high"``, ``"xhigh"``) only when ``non_light_models``
    (the policy's own configured models for every tier but light, on the
    same harness) confirms the *fuller* identifier is itself one of them --
    proving it is a deliberately different, non-light tier, not an
    incidental suffix. Without that confirmation the uncertainty is
    resolved the safe way, toward still matching: a false "different
    model" here would let a light-tier run skip the guard entirely, which
    is worse than an unnecessary guard on a genuinely different model.
    ``"o4-mini"`` fails to match ``"o4-mini-high"`` only when policy has
    ``"o4-mini-high"`` configured as some other tier's model.
    """
    a_tokens, b_tokens = _model_tokens(candidate_model), _model_tokens(configured_model)
    if not a_tokens or not b_tokens:
        return False
    if a_tokens == b_tokens:
        return True
    inner, outer = (a_tokens, b_tokens) if len(a_tokens) <= len(b_tokens) else (b_tokens, a_tokens)
    if not any(token not in GENERIC_MODEL_TOKENS and not token.isdigit() for token in inner):
        return False
    confirmed_non_light = {tuple(_model_tokens(model)) for model in (non_light_models or ())}
    span = len(inner)
    for i in range(len(outer) - span + 1):
        if outer[i:i + span] != inner:
            continue
        if (i + span < len(outer) and outer[i + span] in TIER_QUALIFIER_TOKENS and
                tuple(outer) in confirmed_non_light):
            continue
        return True
    return False


def is_light_tier_run(attempt, policy):
    """True when this attempt's guard must apply, by tier, task type or model.

    The selected candidate's own recorded ``tier`` is the usual signal. A
    candidate with no ``tier`` label at all (a fallback configured by
    explicit ``model``, or an override) cannot itself say it is not light, so
    the task's own ``qa_collect`` classification applies only then -- an
    explicit standard-or-above tier is a genuine escalation (for example
    ``reassign`` to standard) and is exempt from the task-type rule (finding
    3a, round 2: task_type never changes on reassignment, so applying it
    unconditionally meant a qa_collect task could never actually resolve
    through a standard-tier reassignment). Independently of tier, the
    requested or harness-reported actual model matching that harness's
    configured light-tier model *by family* (finding 3b) is also sufficient,
    since a fallback candidate can name a model the harness then reports back
    under a different but equivalent full identifier.
    """
    candidate = attempt['route_candidates'][attempt['candidate_index']] or {}
    tier = candidate.get('tier')
    if tier == 'light':
        return True
    if tier is None and attempt.get('task_type') == 'qa_collect':
        return True
    harness = attempt.get('requested_harness')
    tiers = (policy or {}).get('delegation', {}).get('models', {}).get(harness) or {}
    light_model = tiers.get('light')
    non_light_models = [model for name, model in tiers.items() if name != 'light']
    if light_model:
        for observed in (attempt.get('requested_model'), attempt.get('actual_model')):
            if observed and model_family_matches(observed, light_model, non_light_models):
                return True
    return False


def light_tier_evidence(text, root, attempt):
    """Evidence for a light-tier run's own self-reported summary, or ``None``.

    Counts are never accepted from a worker's own summary (finding 3): only
    an independently run ``accept`` command, or a driver-captured command
    transcript, may supply them. A produced-file list is accepted only when
    every path is both declared inside the task's owned paths AND among the
    paths the driver itself measured this run as having changed
    (``worker_changed_paths``): an unrelated, pre-existing file (a checked-in
    README, say) can never pass just because the summary names it.
    """
    paths = parse_files(text)
    if not paths:
        return None
    cwd = (root / attempt['cwd']).resolve()
    valid = validate_owned_files(cwd, attempt.get('owned_paths'), paths)
    if not valid:
        return None
    changed = set(attempt.get('worker_changed_paths') or ())
    if not all(item['path'] in changed for item in valid):
        return None
    return {'expect': 'files', 'source': 'summary', 'files': valid}


def registered_worktrees(root):
    """Every worktree ``git`` itself knows about for the repository at ``root``."""
    result = subprocess.run(['git', 'worktree', 'list', '--porcelain'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        return set()
    found = set()
    for line in result.stdout.splitlines():
        if line.startswith('worktree '):
            try:
                found.add(Path(line[len('worktree '):]).resolve())
            except OSError:
                pass
    return found


def build_command_argv(command):
    """The acceptance command as ``subprocess`` should receive it, per platform.

    On Windows, ``CreateProcess`` (which ``subprocess`` calls directly when
    ``shell=False``, never through ``cmd.exe``) parses its own command-line
    quoting; passing the string through unchanged is the correct, native way
    to preserve quoted arguments such as a path with spaces.
    ``shlex.split(..., posix=False)`` keeps the quote characters themselves in
    each token, which is wrong once that token is one ``argv`` element
    (finding 8c). On POSIX there is no such native parser and no shell here,
    so the string must still be split into an argv list ourselves.
    """
    if os.name == 'nt':
        return command
    args = shlex.split(command)
    delegation.require(args, 'DELEGATION_ACCEPT_COMMAND_REQUIRED')
    return args


def is_windows_host():
    """Whether this process is running on Windows.

    A thin, independently-mockable seam over ``os.name`` used only for shim detection
    (``command_targets_windows_shim``). Tests must patch this function rather
    than ``os.name`` itself: ``os`` is a single shared module object, so
    patching ``os.name`` directly (even via ``patch.object(dispatch.os,
    'name', ...)``) mutates it process-wide and also changes which
    ``pathlib`` flavour every ``Path(...)`` call in this process uses --
    including unrelated ``Path(root).resolve()`` calls made from POSIX test
    code, which then breaks by building a ``WindowsPath`` on a POSIX host.
    """
    return os.name == 'nt'


WINDOWS_SHIM_EXTENSIONS = ('.bat', '.cmd')


def command_target_token(command):
    """The acceptance command's own leading token (its executable), quoted or not."""
    text = command.strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        return text[1:end] if end > 0 else text[1:]
    parts = text.split(None, 1)
    return parts[0] if parts else ''


def command_targets_windows_shim(command):
    """True when the acceptance command's executable is, or would resolve on
    PATH to, a ``.bat``/``.cmd`` shim (finding 5, round 2: the "BatBadBut"
    vulnerability class). Windows' ``CreateProcess`` cannot run a batch file
    directly: it always routes it through ``cmd.exe``, which re-parses
    quoting, even though this module never sets ``shell=True`` and never
    passes the command through a shell itself -- an argument built from
    untrusted content could still be interpreted as a second command.
    """
    if not is_windows_host():
        return False
    token = command_target_token(command)
    if not token:
        return False
    suffix = Path(token).suffix.lower()
    if suffix in WINDOWS_SHIM_EXTENSIONS:
        return True
    if not suffix:
        resolved = shutil.which(token)
        if resolved and Path(resolved).suffix.lower() in WINDOWS_SHIM_EXTENSIONS:
            return True
    return False


def kill_process_tree(proc):
    """Kill the whole process tree, not just the direct child (finding 8d).

    A command that spawns its own children (a shell wrapper, a test runner
    that forks workers) would otherwise survive its parent's termination and
    keep running, and could keep writing to the very file this function's
    caller is about to read.
    """
    if os.name == 'nt':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)], capture_output=True)
        return
    import signal
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()


ACCEPT_OUTPUT_CAP = 200_000  # bytes kept per stream before parsing or storing
ACCEPT_LEDGER_OUTPUT_CAP = 20_000  # characters of that kept in the ledger record


def run_capped(args, cwd, timeout):
    """Run a fixed command with no shell, a wall-clock timeout and a hard output cap.

    ``args`` is an argv list on POSIX or the raw command string on Windows
    (``build_command_argv``), never passed through a shell, so no shell
    metacharacter is special and nothing is interpolated; ``cwd`` is always
    the task's own recorded (or explicitly declared) working directory, never
    an arbitrary caller-supplied path. stdout and stderr are captured to
    spooled temp files rather than in-memory pipes, and only the first
    ``ACCEPT_OUTPUT_CAP`` bytes of each are ever read back, so a runaway or
    hostile command cannot exhaust the dispatcher's own memory. On a timeout
    the whole process tree is killed (``kill_process_tree``), not just the
    immediate child, before its output is read.
    """
    popen_kwargs = {} if os.name == 'nt' else {'start_new_session': True}
    with tempfile.TemporaryFile() as out_file, tempfile.TemporaryFile() as err_file:
        try:
            proc = subprocess.Popen(args, cwd=cwd, stdout=out_file, stderr=err_file, **popen_kwargs)
        except OSError as exc:
            return {'exit_code': None, 'output': str(exc), 'truncated': False, 'timed_out': False}
        timed_out = False
        try:
            exit_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_process_tree(proc)
            try:
                exit_code = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                exit_code = None
        out_file.seek(0)
        err_file.seek(0)
        out = out_file.read(ACCEPT_OUTPUT_CAP + 1)
        err = err_file.read(ACCEPT_OUTPUT_CAP + 1)
    truncated = len(out) > ACCEPT_OUTPUT_CAP or len(err) > ACCEPT_OUTPUT_CAP
    out, err = out[:ACCEPT_OUTPUT_CAP], err[:ACCEPT_OUTPUT_CAP]
    out_text = out.decode('utf-8', errors='replace')
    err_text = err.decode('utf-8', errors='replace')
    text = out_text + ('\n--- stderr ---\n' + err_text if err_text.strip() else '')
    return {'exit_code': exit_code, 'output': text, 'truncated': truncated, 'timed_out': timed_out}


def _recorded_response(attempt):
    """The collect-shaped response for an attempt already fully processed."""
    response = {'run_id': attempt['run_id'], 'status': attempt['status'],
                'requested_model': attempt.get('requested_model'),
                'actual_model': attempt.get('actual_model'),
                'actual_model_evidence': attempt.get('actual_model_evidence'),
                'harness': attempt.get('actual_harness'), 'evidence_location': attempt.get('evidence_location'),
                'token_usage': attempt.get('token_usage'), 'result_summary': attempt.get('result_summary'),
                'changed_paths': attempt.get('changed_paths'),
                'worker_changed_paths': attempt.get('worker_changed_paths'),
                'dispatcher_paths_changed': attempt.get('dispatcher_paths_changed')}
    if attempt.get('unverified_reason'):
        response['unverified_reason'] = attempt['unverified_reason']
    if attempt.get('accepted_evidence'):
        response['accepted_evidence'] = attempt['accepted_evidence']
    return response


def collect(root, feature, run_id, auto_retry=True):
    root = root.resolve()
    feature = feature_identity(root, feature)
    delegation.require_no_maintenance(root)
    policy = workflow.load_policy(root)
    with edit_ledger(root, feature) as ledger:
        attempt = find_run(ledger, run_id)
        delegation.require(attempt is not None, 'DELEGATION_RUN_UNKNOWN: ' + run_id)
        require_not_worker_context(feature, attempt['identity'].removeprefix(feature + '/'))
        linked = replacement_link(ledger, attempt)
        # Already fully processed (finding 3d, round 2): a repeated collect on
        # a terminal run -- especially one accept already resolved -- must
        # return what is on record, never re-run the driver or the light-tier
        # guard a second time and risk downgrading an accepted result back to
        # unverified.
        already_done = (linked is None and attempt.get('status') in TERMINAL_STATUSES and
                        (attempt.get('ended_at') is not None or attempt.get('accepted_evidence') is not None))
        recorded = copy.deepcopy(attempt) if already_done else None
    if linked:
        return linked
    if recorded is not None:
        return _recorded_response(recorded)
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
        # Light-tier guard (B12): a light-tier "successful" result is never
        # taken on trust. Only parsable evidence in the worker's own summary
        # keeps it successful; anything else stays unverified until accept or
        # a standard-tier reassignment supplies it. A note is not a path here:
        # nothing in this ledger accepts free text as evidence.
        if is_light_tier_run(attempt, policy) and attempt['status'] == 'successful':
            evidence = light_tier_evidence(payload.get('summary') or '', root, attempt)
            if evidence:
                attempt['accepted_evidence'] = evidence
                attempt['accepted_at'] = stamp()
            else:
                attempt['status'] = 'unverified'
                attempt['unverified_reason'] = LIGHT_TIER_EVIDENCE_MISSING_REASON
        attempt['evidence_location'] = relative(root, Path((payload.get('artifacts') or {}).get('dir',
                                                        root / '.delegate/runs' / run_id)) / 'result.json')
        linked = replacement_link(ledger, attempt)
        attempt = copy.deepcopy(attempt)
    response = _recorded_response(attempt)
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
                                      retry_count=retry_count, owned_paths=attempt.get('owned_paths'),
                                      claim_token=attempt.get('claim_token'),
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
    # unverified is terminal too: a light-tier "successful" without evidence is
    # exactly the case a standard-tier reassignment is meant to resolve.
    delegation.require(prior is not None and prior.get('status') in TERMINAL_STATUSES,
                       'DELEGATION_PRIOR_RUN_NOT_TERMINAL')
    require_not_worker_context(feature, prior['identity'].removeprefix(feature + '/'))
    # An adopted attempt has no dispatcher route, task file or retry count to
    # escalate from (round 8, finding 2: reassign crashed with a bare
    # KeyError on 'retry_count' trying); adopt is its own, supported recovery.
    delegation.require(not prior.get('adopted'),
                       'DELEGATION_REASSIGN_ADOPTED_UNSUPPORTED: an adopted attempt has no dispatcher '
                       'route to escalate; re-run "delegate_dispatch.py adopt" with a corrected '
                       'acceptance check, or "start" the task normally to create a real dispatched '
                       'attempt reassign can act on')
    delegation.require(not prior.get('pinned'),
                       'DELEGATION_PINNED_ROUTE_NO_ESCALATION: the run was started with an explicit '
                       '--harness/--model pair; start again with another eligible pair instead')
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
                                  owned_paths=prior.get('owned_paths'), claim_token=prior.get('claim_token'),
                                  decision={'at': stamp(), 'identity': prior['identity'],
                                            'requested': attempt_to_candidate(prior),
                                            'decision': 'reassignment', 'reason': reason.strip(),
                                            'after_run_id': run_id})
    with edit_ledger(root, feature) as ledger:
        find_run(ledger, run_id)['replacement_run_id'] = replacement['run_id']
    return replacement


ACCEPT_EXPECTS = ('counts', 'files')
ACCEPT_TIMEOUT_DEFAULT = 1800


def accept(root, feature, run_id, command, expect, timeout=None, owned=None):
    """Independently run and judge an acceptance command for an unverified run.

    The only new dispatcher command in B12: it resolves a light-tier
    ``unverified`` outcome without a standard-tier reassignment, by running a
    fixed command the orchestrator supplies and inspecting its own output --
    never the worker's self-report a second time. The command runs with no
    shell (``build_command_argv``: argv via ``shlex.split`` on POSIX, the raw
    string for Windows' own ``CreateProcess`` quoting; finding 8c) in the
    task's own recorded working directory -- its original ``cwd``, or, when
    that is outside ``root``, a worktree ``git worktree list`` itself
    confirms belongs to this repository (finding 8b; a caller-supplied path is
    never accepted) -- under a bounded timeout and a hard output cap with the
    whole process tree killed on timeout (``run_capped``).

    It accepts only when the command exits 0 and its output satisfies the
    requested schema: ``counts`` needs parsable total > 0 and failed == 0;
    ``files`` needs every path to exist, be non-empty and resolve inside the
    task's owned paths (``--owned``, or the paths recorded at ``start``, or
    the whole ``cwd`` when neither declared any), rejecting absolute paths,
    ``..`` traversal and symlink escapes; each accepted file's evidence
    records its sha256 and size (finding 8a). Exit-zero empty output,
    unparsable output (including a bare free-text note with no structured
    evidence), a missing or empty file, a path outside the owned set, a
    failed command or a timeout all leave the attempt ``unverified``; every
    attempt is recorded in the ledger regardless of outcome.
    """
    root = root.resolve()
    feature = feature_identity(root, feature)
    delegation.require(expect in ACCEPT_EXPECTS, 'DELEGATION_ACCEPT_EXPECT_INVALID')
    delegation.require(isinstance(command, str) and command.strip(),
                       'DELEGATION_ACCEPT_COMMAND_REQUIRED')
    timeout = timeout if timeout is not None else ACCEPT_TIMEOUT_DEFAULT
    delegation.require(type(timeout) is int and 0 < timeout <= 28800, 'DELEGATION_TIMEOUT_INVALID')
    delegation.require_no_maintenance(root)
    ledger = read_ledger(root, feature)
    attempt = find_run(ledger, run_id)
    delegation.require(attempt is not None, 'DELEGATION_RUN_UNKNOWN: ' + run_id)
    require_not_worker_context(feature, attempt['identity'].removeprefix(feature + '/'))
    delegation.require(attempt.get('status') == 'unverified',
                       'DELEGATION_RUN_NOT_UNVERIFIED: only an unverified light-tier result can be accepted')
    cwd = (root / attempt['cwd']).resolve()
    delegation.require(cwd.is_dir() and (cwd.is_relative_to(root) or cwd in registered_worktrees(root)),
                       'DELEGATION_ACCEPT_CWD_INVALID')
    delegation.require(not command_targets_windows_shim(command),
                       'DELEGATION_ACCEPT_COMMAND_IS_SHIM: the acceptance command targets a .bat/.cmd '
                       'shim; Windows always runs it through cmd.exe even though this dispatcher never '
                       'uses a shell, reopening the class of injection shell=False is meant to close. '
                       'Run the underlying executable directly instead (for example "node <script>.js" '
                       'rather than an npx.cmd shim)')
    args = build_command_argv(command)
    # --owned may only narrow what was declared at start, never widen it
    # (finding 4, round 2): otherwise a task started with a bounded owned set
    # could have that bound quietly lifted for one acceptance call.
    owned_paths = attempt.get('owned_paths')
    if owned:
        recorded_roots = owned_roots(cwd, owned_paths) or [Path(cwd).resolve()]
        narrowed_roots = owned_roots(cwd, owned)
        delegation.require(narrowed_roots is not None and all(
            any(candidate.is_relative_to(recorded) for recorded in recorded_roots)
            for candidate in narrowed_roots),
            'DELEGATION_ACCEPT_OWNED_MUST_NARROW: --owned may only narrow the paths recorded at '
            'start, never widen them')
        owned_paths = owned
    run = run_capped(args, cwd, timeout)
    text = run['output']
    evidence = None
    if run['exit_code'] == 0:
        if expect == 'counts':
            counts = parse_counts(text)
            if counts and counts['total'] > 0 and counts['failed'] == 0:
                evidence = {'expect': 'counts', 'source': 'accept', 'counts': counts}
        else:
            paths = parse_files(text)
            valid = validate_owned_files(cwd, owned_paths, paths) if paths else None
            if valid:
                evidence = {'expect': 'files', 'source': 'accept', 'files': valid}
    with edit_ledger(root, feature) as ledger:
        attempt = find_run(ledger, run_id)
        delegation.require(attempt is not None and attempt.get('status') == 'unverified',
                           'DELEGATION_RUN_NOT_UNVERIFIED: only an unverified light-tier result can be accepted')
        record = {'at': stamp(), 'command': command, 'expect': expect, 'exit_code': run['exit_code'],
                  'timed_out': run.get('timed_out', False), 'output_truncated': run.get('truncated', False),
                  'accepted': evidence is not None, 'output': text[:ACCEPT_LEDGER_OUTPUT_CAP]}
        attempt.setdefault('acceptance_attempts', []).append(record)
        if evidence:
            attempt['status'] = 'successful'
            attempt['accepted_evidence'] = evidence
            attempt['accepted_at'] = stamp()
            attempt.pop('unverified_reason', None)
        result = copy.deepcopy(attempt)
    return {'run_id': run_id, 'status': result['status'], 'accepted': evidence is not None,
            'expect': expect, 'exit_code': run['exit_code'], 'timed_out': run.get('timed_out', False),
            'output_truncated': run.get('truncated', False), 'evidence': evidence}


def recover_intent(root, feature, intent_id):
    """Recover a driver run created just before its Sanduq ledger write."""
    root = root.resolve()
    feature = feature_identity(root, feature)
    delegation.require_no_maintenance(root)
    with edit_ledger(root, feature) as ledger:
        intent = find_intent(ledger, intent_id)
        delegation.require(intent is not None, 'DELEGATION_INTENT_UNKNOWN')
        require_not_worker_context(feature, intent['identity'].removeprefix(feature + '/'))
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
        require_not_worker_context(feature, intent['identity'].removeprefix(feature + '/'))
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


def trust_reset(root, feature, reason):
    """Explicitly clear a persisted ledger tamper flag (round 3, findings 1-2).

    Only a human decision resolves genuine tampering: this records who, when
    and why, and the exact bytes on both sides, then re-anchors the ordinary
    written marker at the ledger's current bytes so normal dispatcher
    operation is read as trusted again from this point forward. It does not
    (and cannot) prove the current bytes are correct -- only that a human
    reviewed and accepted them; CI integrity ultimately rests on review, not
    on this mechanism (see the README's local-only trust limit).

    This is an orchestrator-only, human-authorised command (round 4, finding
    1): a worker brief explicitly forbids running it (or any other
    delegate_dispatch.py command). It refuses outright when there is nothing
    to reset (``DELEGATION_TRUST_RESET_NOTHING_TO_RESET``): with no persisted
    tamper on record, this call would not be clearing a detected tamper, it
    would be blessing whatever the ledger's current bytes happen to be --
    exactly the laundering path this command exists to close, not open. A
    prior probe: hand-edit the ledger, delete the local ``.written`` marker
    (so no mismatch is ever detected), then call trust-reset -- with this
    check, that now refuses instead of minting a fresh "trusted" marker over
    the unreviewed edit. It also refuses while any attempt for the feature is
    ``starting`` or ``running``, so a reset can never race a live dispatch
    that might still change the very bytes being reviewed.
    """
    root = root.resolve()
    feature = feature_identity(root, feature)
    require_not_worker_context(feature, None)
    delegation.require(isinstance(reason, str) and reason.strip(),
                       'DELEGATION_TRUST_RESET_REASON_REQUIRED')
    delegation.require_no_maintenance(root)
    with ledger_lock(root, feature):
        marker = delegation.foreign_write_marker(root, feature)
        record = workflow.read(marker, None)
        delegation.require(record is not None,
                           'DELEGATION_TRUST_RESET_NOTHING_TO_RESET: no persisted tamper is recorded '
                           'for ' + feature + '; trust-reset only clears an already-detected tamper, it '
                           'never blesses the ledger\'s current bytes on its own')
        ledger = load_ledger(root, feature)
        active = [a.get('run_id') or ('intent ' + str(a.get('intent_id')))
                 for a in ledger['attempts'] if a.get('status') in ACTIVE]
        delegation.require(not active, 'DELEGATION_TRUST_RESET_ATTEMPTS_ACTIVE: ' +
                           ', '.join(sorted(str(item) for item in active)) +
                           ' is starting or running; collect, recover or abandon it before trust-reset')
        new_sha = ledger_bytes_digest(delegation.ledger_path(root, feature))
        try:
            actor = getpass.getuser()
        except Exception:
            actor = None
        entry = {'at': stamp(), 'actor': actor, 'reason': reason.strip(),
                'old_sha256': record.get('digest_at_detection'), 'new_sha256': new_sha}
        log_path = delegation.trust_reset_log_path(root, feature)
        log = workflow.read(log_path, [])
        log.append(entry)
        workflow.write(log_path, log)
        marker.unlink(missing_ok=True)
        workflow.write(written_marker(root, feature), {'sha256': new_sha})
    return {'feature': feature, 'trust': 'trusted', **entry}


def adopt(root, feature, task_id, command, expect, timeout=None, owned=None):
    """Bring a checked task that has no delegation attempt at all under the
    ledger's own evidence, by independently running an acceptance check --
    never by asserting an exemption (round 7, findings 1-2 removed both
    prior bypasses: a worker could self-certify with the now-deleted
    ``orchestrator-executed`` command, and the stage-wide
    ``delegation_enabled_for_execute: false`` checkpoint field was a mutable,
    unfingerprinted flag the Ready gate trusted outright).

    Adoption is for work legitimately done before delegation was enabled for
    this feature -- a task that has never been started, accepted or
    reassigned through the dispatcher. Before running anything it requires
    ``task_id`` to name a task that actually exists in ``tasks.md`` and is
    currently checked (round 8, finding 1: Codex adopted an absent task,
    then a different, later task added under the same id rode the earlier
    adoption to Ready) -- ``DELEGATION_ADOPT_TASK_UNKNOWN`` or
    ``DELEGATION_ADOPT_TASK_NOT_CHECKED`` otherwise -- and it records on the
    attempt a binding to that task's current content: a sha256 of the task
    line's text with the checkbox state removed and whitespace normalised
    (``delegation.task_line_content_sha256``). The Ready gate re-hashes the
    live line at completion time and refuses with
    ``DELEGATION_ADOPT_TASK_CHANGED`` on a mismatch, so editing the task
    (including swapping in different work under the same id) after adoption
    cannot ride the earlier check to Ready.

    It refuses outright with ``DELEGATION_ADOPT_HAS_ATTEMPT`` unless every
    existing attempt for the task is itself an unverified adoption (round 8,
    finding 2: a fresh task has none at all; a task whose only history is a
    failed ``adopt`` may be re-adopted with a corrected check, since that is
    the supported recovery reassign cannot offer an adopted attempt). Any
    other existing attempt -- started, accepted, or a successful adoption
    already on record -- already has its own resolution path (``accept`` for
    an unverified dispatched result, ``reassign`` for a stuck one, a fresh
    ``adopt`` call is pointless once one has already succeeded), and adopt
    must never offer a second, easier route around it.

    Runs ``command`` with exactly ``accept``'s own machinery: no shell
    (``build_command_argv``), the BatBadBut shim refusal
    (``command_targets_windows_shim``), a bounded timeout, a hard output cap
    with the whole process tree killed on timeout (``run_capped``), and the
    same ``counts``/``files`` evidence schema, including owned-path
    containment (``validate_owned_files``) and per-file sha256. Only a
    passing check records a new, ``successful`` attempt with ``adopted:
    True``, the command, exit code, capped output and evidence; a failing
    command, a timeout, or an exit-zero run with no parsable or in-bounds
    evidence records ``unverified`` instead -- the Ready gate then treats
    the result exactly like any other attempt, never as an exemption.

    Runs from the repo root, never the feature directory (round 9, finding
    2): the acceptance command is the orchestrator's own, already-trusted
    check, and pinning its cwd to a subdirectory the task happens to live
    under serves no purpose an attacker could exploit that running from
    root does not already close off just as well -- while a repo-root
    check (for example an aggregate test command) previously had no way to
    run at all. The feature directory remains the *default* owned root for
    ``--expect files``, unchanged in effect from before.
    """
    root = root.resolve()
    feature = feature_identity(root, feature)
    delegation.require(re.fullmatch(r'T\d{3,}', task_id) is not None, 'DELEGATION_IDENTITY_INVALID')
    require_not_worker_context(feature, task_id)
    delegation.require(expect in ACCEPT_EXPECTS, 'DELEGATION_ACCEPT_EXPECT_INVALID')
    delegation.require(isinstance(command, str) and command.strip(),
                       'DELEGATION_ACCEPT_COMMAND_REQUIRED')
    timeout = timeout if timeout is not None else ACCEPT_TIMEOUT_DEFAULT
    delegation.require(type(timeout) is int and 0 < timeout <= 28800, 'DELEGATION_TIMEOUT_INVALID')
    delegation.require_no_maintenance(root)
    tasks_path = root / feature / 'tasks.md'
    delegation.require(tasks_path.is_file(), 'DELEGATION_TASKS_MISSING')
    matches = [line.strip() for line in tasks_path.read_text(encoding='utf-8-sig').splitlines()
              if (found := delegation.TASK_LINE.match(line)) and found[3] == task_id]
    delegation.require(len(matches) == 1,
                       'DELEGATION_ADOPT_TASK_UNKNOWN: ' + task_id + ' is not a task in ' +
                       relative(root, tasks_path))
    task_line = matches[0]
    delegation.require(task_line[:5].lower() == '- [x]',
                       'DELEGATION_ADOPT_TASK_NOT_CHECKED: ' + task_id + ' must be checked off in '
                       'tasks.md before it can be adopted')
    task_line_sha256 = delegation.task_line_content_sha256(task_line)
    full_identity = feature + '/' + task_id
    ledger = read_ledger(root, feature)
    existing = [a for a in ledger.get('attempts', []) if a.get('identity') == full_identity]
    delegation.require(all(a.get('adopted') and a.get('status') == 'unverified' for a in existing),
                       'DELEGATION_ADOPT_HAS_ATTEMPT: an attempt already exists for ' + task_id +
                       '; resolve it with accept or reassign instead of adopting it')
    delegation.require(not command_targets_windows_shim(command),
                       'DELEGATION_ACCEPT_COMMAND_IS_SHIM: the acceptance command targets a .bat/.cmd '
                       'shim; Windows always runs it through cmd.exe even though this dispatcher never '
                       'uses a shell, reopening the class of injection shell=False is meant to close. '
                       'Run the underlying executable directly instead (for example "node <script>.js" '
                       'rather than an npx.cmd shim)')
    cwd = root
    args = build_command_argv(command)
    owned_paths = list(owned) if owned else [feature]
    run = run_capped(args, cwd, timeout)
    text = run['output']
    evidence = None
    if run['exit_code'] == 0:
        if expect == 'counts':
            counts = parse_counts(text)
            if counts and counts['total'] > 0 and counts['failed'] == 0:
                evidence = {'expect': 'counts', 'source': 'adopt', 'counts': counts}
        else:
            paths = parse_files(text)
            valid = validate_owned_files(cwd, owned_paths, paths) if paths else None
            if valid:
                evidence = {'expect': 'files', 'source': 'adopt', 'files': valid}
    run_id = 'adopt-' + uuid.uuid4().hex
    with edit_ledger(root, feature) as ledger:
        existing = [a for a in ledger.get('attempts', []) if a.get('identity') == full_identity]
        delegation.require(all(a.get('adopted') and a.get('status') == 'unverified' for a in existing),
                           'DELEGATION_ADOPT_HAS_ATTEMPT: an attempt already exists for ' + task_id +
                           '; resolve it with accept or reassign instead of adopting it')
        attempt = {'identity': full_identity, 'task_type': 'adopted', 'run_id': run_id,
                  'adopted': True, 'status': 'successful' if evidence is not None else 'unverified',
                  'started_at': stamp(), 'ended_at': stamp(), 'cwd': relative(root, cwd),
                  'timeout': timeout, 'owned_paths': owned_paths, 'command': command, 'expect': expect,
                  'exit_code': run['exit_code'], 'timed_out': run.get('timed_out', False),
                  'output_truncated': run.get('truncated', False),
                  'output': text[:ACCEPT_LEDGER_OUTPUT_CAP], 'task_line_sha256': task_line_sha256}
        if evidence:
            attempt['accepted_evidence'] = evidence
            attempt['accepted_at'] = stamp()
        else:
            attempt['unverified_reason'] = 'DELEGATION_ADOPT_CHECK_DID_NOT_PASS'
        ledger['attempts'].append(attempt)
        result = copy.deepcopy(attempt)
    return {'run_id': run_id, 'task_id': task_id, 'status': result['status'],
           'adopted': evidence is not None, 'expect': expect, 'exit_code': run['exit_code'],
           'timed_out': run.get('timed_out', False), 'output_truncated': run.get('truncated', False),
           'evidence': evidence, 'task_line_sha256': task_line_sha256}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='action', required=True)
    start_cmd = sub.add_parser('start')
    start_cmd.add_argument('--feature', required=True)
    start_cmd.add_argument('--id', required=True)
    start_cmd.add_argument('--type', choices=delegation.TYPES)
    start_cmd.add_argument('--harness', choices=('codex', 'claude'))
    start_cmd.add_argument('--model')
    start_cmd.add_argument('--task-file', type=Path)
    start_cmd.add_argument('--cwd', type=Path)
    start_cmd.add_argument('--claim-token')
    start_cmd.add_argument('--timeout', type=int)
    start_cmd.add_argument('--owned', action='append',
                           help='A path (repeatable) this task owns, relative to --cwd; '
                                'defaults to the whole cwd when omitted')
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
    accept_cmd = sub.add_parser('accept')
    accept_cmd.add_argument('--feature', required=True)
    accept_cmd.add_argument('--run-id', required=True)
    accept_cmd.add_argument('--command', required=True)
    accept_cmd.add_argument('--expect', choices=ACCEPT_EXPECTS, required=True)
    accept_cmd.add_argument('--timeout', type=int)
    accept_cmd.add_argument('--owned', action='append',
                            help='A path (repeatable) to check "files" evidence against for this '
                                 'call, overriding the paths recorded at start')
    trust_reset_cmd = sub.add_parser('trust-reset')
    trust_reset_cmd.add_argument('--feature', required=True)
    trust_reset_cmd.add_argument('--reason', required=True)
    adopt_cmd = sub.add_parser('adopt')
    adopt_cmd.add_argument('--feature', required=True)
    adopt_cmd.add_argument('--id', required=True)
    adopt_cmd.add_argument('--command', required=True)
    adopt_cmd.add_argument('--expect', choices=ACCEPT_EXPECTS, required=True)
    adopt_cmd.add_argument('--timeout', type=int)
    adopt_cmd.add_argument('--owned', action='append',
                           help='A path (repeatable), relative to the repo root, to check "files" '
                                'evidence against; defaults to the feature directory when omitted')
    args = parser.parse_args(argv)
    try:
        if args.action == 'start':
            result = start(args.root, args.feature, args.id, args.type, args.task_file,
                           args.cwd, args.claim_token, args.timeout, args.owned,
                           args.harness, args.model)
        elif args.action == 'collect':
            result = collect(args.root, args.feature, args.run_id, not args.no_auto_retry)
        elif args.action == 'recover':
            result = recover_intent(args.root, args.feature, args.intent_id)
        elif args.action == 'abandon':
            result = abandon_intent(args.root, args.feature, args.intent_id, args.reason)
        elif args.action == 'accept':
            result = accept(args.root, args.feature, args.run_id, args.command, args.expect,
                            args.timeout, args.owned)
        elif args.action == 'trust-reset':
            result = trust_reset(args.root, args.feature, args.reason)
        elif args.action == 'adopt':
            result = adopt(args.root, args.feature, args.id, args.command, args.expect,
                           args.timeout, args.owned)
        else:
            result = reassign(args.root, args.feature, args.run_id, args.reason, args.task_file)
        print(json.dumps(result, indent=2))
        return 0
    except (delegation.DelegationError, workflow.WorkflowError, OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
