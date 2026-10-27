"""Receipts and gates: required inputs and roles, drift, CI and diff-review evidence, receipt status,
recovery recipes and the Ready checks."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import sanduq_ci
import source_key as sk
import lean_policy
import verification_plan
import evidence_snapshot
import execution_tools
from datetime import datetime, timezone
from pathlib import Path
from sanduq_hash import portable_content, text_attributes
from wf_core import (BASE_STAGES, INPUT_ROLES, SOURCE_STAGES, LITE_OPTIONAL_INPUTS, SYNC_BINDING_PREFIX, HANDOFF_BEGIN,
                     HANDOFF_END, WORKFLOW_SCRIPT, WorkflowError, require, read, inside, portable_label, canonical_path,
                     run_git, git_ok, git)
import sanduq_fs  # on sys.path once wf_core is imported (packaged beside it, or the source tree's shared folder)
from wf_fingerprints import (sync_state_label, sync_entry, text_fingerprints, fingerprint_files, source_fingerprints,
                             source_fingerprints_of)
from wf_policy import state_tier, feature_tier, task_issue_mode
from wf_health import progress_wiring_warnings, guard_approval_warnings


def verify_sync_binding(root, feature, state):
    """The feature's state entry, refused unless it binds the issue scope-source.json binds for this checkpoint and
    its sub-issues match the task mapping. Item and node ids cannot be checked offline; they stay in the projection."""
    label, slug = sync_state_label(root), feature.rsplit('/', 1)[-1]
    try:
        entry = (read(Path(root) / label, {}) or {}).get(slug)
    except (ValueError, AttributeError):
        entry = None
    require(isinstance(entry, dict), 'SYNC_BINDING_MISMATCH: ' + label + ' has no entry for ' + slug)
    source = read(Path(root) / feature / 'scope-source.json', {})
    require(f"{source.get('repo')}#{source.get('issue')}" == state['issue'],
            'SYNC_BINDING_MISMATCH: scope-source.json does not bind ' + state['issue'])
    require(str(entry.get('issue')) == str(source.get('issue')),
            'SYNC_BINDING_MISMATCH: issue ' + str(entry.get('issue')) + ' in ' + label + ', ' + state['issue'] + ' bound')
    subs = entry.get('subIssues') or {}
    if subs:
        mapping = read(Path(root) / feature / 'workflow/task-issues.json', {})
        repo, parent = state['issue'].split('#')
        require((mapping.get('repo'), mapping.get('parent'), mapping.get('feature')) == (repo, int(parent), feature),
                'SYNC_BINDING_MISMATCH: sub-issues without a matching workflow/task-issues.json')
        tasks = mapping.get('tasks') or {}
        differ = sorted(task for task, sub in subs.items()
                        if not isinstance(sub, dict) or (tasks.get(task) or {}).get('number') != sub.get('number'))
        require(not differ, 'SYNC_BINDING_MISMATCH: sub-issues differ from the task mapping: ' + ', '.join(differ))
    return entry


def same_path(root, label, canonical):
    try:
        return canonical_path(root, label) == canonical
    except WorkflowError:
        return False


def recorded_sync_fields(root, label, feature, old_hash, entry):
    """Entry fields changed since the bytes `old_hash` names, found in the working tree, HEAD or the last 50
    commits that touched the state file. Refused when no version hashes to it: the old binding is unknown."""
    if fingerprint_files(root, [label])[label] == old_hash:
        old = (Path(root) / label).read_bytes()
    else:
        revs = run_git(root, 'rev-list', '-n', '50', 'HEAD', '--', label, text=True).stdout.split()
        old = None
        attribute = text_attributes(root, [label]).get(label)
        for rev in ['HEAD'] + revs:
            shown = run_git(root, 'show', rev + ':' + label)
            # The receipt hashed portable bytes (CRLF folded), so a CRLF blob must be folded the same way.
            if not shown.returncode and hashlib.sha256(
                    portable_content(label, shown.stdout, attribute)).hexdigest() == old_hash:
                old = shown.stdout
                break
        require(old is not None, 'SYNC_BINDING_MISMATCH: no version of ' + label + ' matches the recorded hash; '
                'the old binding is unknown, re-record the stage')
    old = sync_entry(old, feature)
    old = old if isinstance(old, dict) else {}
    return sorted(key for key in set(old) | set(entry) if old.get(key) != entry.get(key))


def handoff_text(existing, block):
    """Replace only the runtime's marked block; everything outside it is the reader's and is kept.

    A file without markers that the runtime wrote before blocks existed (`# Workflow handoff` first) is replaced."""
    begin, end = existing.find(HANDOFF_BEGIN), existing.find(HANDOFF_END)
    if 0 <= begin < end:
        return existing[:begin] + block + existing[end + len(HANDOFF_END):]
    if not existing.strip() or existing.lstrip().startswith('# Workflow handoff'):
        return block + '\n'
    return existing.rstrip('\n') + '\n\n' + block + '\n'


# AHMED-01: a claim whose heartbeat is younger than this has a live owner unless its recorded pid has exited.
CLAIM_HEARTBEAT_SECONDS = 900


def claim_owner(active):
    """Liveness of an active claim's owner: `alive` when the recorded pid runs on this host, `dead` when it has
    exited, `unknown` when no pid is recorded (a CLI claim, whose process exits at once, or a claim from before
    this field) or the claim came from another host. `heartbeat_recent` is the 15-minute activity window."""
    import socket
    from delegation import process_alive
    stamp = active.get('heartbeat_at') or active.get('claimed_at')
    try:
        last = datetime.fromisoformat(stamp) if stamp else None
    except (TypeError, ValueError):
        last = None
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - last).total_seconds() if last else None
    pid, host = active.get('pid'), active.get('host')
    owner = 'unknown' if pid is None or host != socket.gethostname() else 'alive' if process_alive(pid) else 'dead'
    return {'owner': owner, 'pid': pid, 'host': host,
            'last_activity_minutes': int(age // 60) if age is not None else None,
            'heartbeat_recent': bool(active.get('heartbeat_at')) and age is not None and age < CLAIM_HEARTBEAT_SECONDS}


def native_run_status(root, feature, state, roots):
    """Compact run projection enriched with explicit ledger acceptance, never raw logs."""
    try:
        report = execution_tools.progress(roots)
    except execution_tools.InputError as exc:
        raise WorkflowError('RUN_STATUS_INVALID: ' + str(exc)) from exc
    import delegation
    trust = delegation.ledger_trust_state(root, feature)
    projects = {Path(root).resolve()}
    for folder in roots:
        folder = Path(folder).resolve()
        if folder.name == 'runs' and folder.parent.name == '.delegate':
            projects.add(folder.parent.parent)
        elif (folder / 'specs').is_dir():
            projects.add(folder)
    attempts, ledger_conflicts = {}, set()
    for project in sorted(projects):
        if delegation.ledger_trust_state(project, feature) == 'untrusted':
            continue
        ledger = read(inside(project, feature + '/workflow/delegations.json'), {})
        for attempt in ledger.get('attempts', []):
            run_id = attempt.get('run_id')
            if not run_id:
                continue
            projected = {key: attempt.get(key) for key in ('identity', 'status', 'accepted_evidence', 'status_provenance')}
            # DEC-12 B: a confirmed or pending model fallback is visible wherever the run is shown.
            import delegate_dispatch
            projected['fallback'] = delegate_dispatch.fallback_fields(attempt)
            if run_id in attempts and attempts[run_id] != projected:
                ledger_conflicts.add(run_id)
            attempts[run_id] = projected
    for run in report['runs']:
        attempt = attempts.get(run['run_id']) if run['run_id'] not in ledger_conflicts else None
        run['ledger_status'] = attempt.get('status', 'unknown') if attempt else 'unknown'
        fallback = (attempt or {}).get('fallback') or {}
        if fallback.get('fallback_used') or fallback.get('substitute_model'):
            run['fallback'] = fallback
        accepted = (attempt and attempt.get('status') == 'successful' and
                    (attempt.get('accepted_evidence') or {}).get('source') in ('accept', 'adopt'))
        run['acceptance_verdict'] = 'accepted' if accepted else 'unknown'
        run['acceptance_provenance'] = attempt['accepted_evidence']['source'] if accepted else None
        if attempt and (attempt.get('status_provenance') or {}).get('primary') == 'self_report':
            run['task_verdict'] = attempt.get('status', 'unknown')
            run['task_verdict_provenance'] = 'delegate-self-report'
        run['assignment'] = attempt.get('identity') if attempt else None
    active = state.get('active')
    if active:
        active = {key: value for key, value in active.items() if key != 'baseline'}
        liveness = claim_owner(active)
        active['owner'] = liveness['owner']
        active['last_activity'] = ('unknown' if liveness['last_activity_minutes'] is None
                                   else str(liveness['last_activity_minutes']) + ' min ago')
        if active.get('delegation'):
            # SAMY-03: a native attestation of this claim is shown as such, never as a dispatched run.
            import delegate_dispatch
            attempt = delegation.latest_attempt(root, feature, 'stage:' + str(active.get('stage')))
            if (attempt or {}).get('kind') == 'native' and attempt.get('claim_token') == active.get('token'):
                active['native_attestation'] = delegate_dispatch.native_attestation_fields(attempt)
    result = {'feature': feature, 'issue': state['issue'], 'status': state.get('status'), 'active': active,
              'next_action': state.get('next_action'), 'completed': list(state.get('receipts', {})),
              'ledger_trust': trust, 'ledger_conflicts': sorted(ledger_conflicts),
              'progress': report, 'ok': report['ok'] and not ledger_conflicts}
    for key in ('profile', 'skipped', 'pause'):
        if state.get(key):
            result[key] = state[key]
    result['questions'] = waiting_questions(root, feature, state)
    if sync_retry(state, feature):
        result['project_sync'] = sync_retry(state, feature)
    import progress_bridge
    line = progress_bridge.status_line(root, feature)  # W21: Progress's own text line, no v2 projection
    if line is not None:
        result['progress_status'] = line
    warnings = guard_approval_warnings(root) + progress_wiring_warnings(root)
    if warnings:
        result['warnings'] = warnings
    return result


def waiting_questions(root, feature, state):
    """Where this feature's questions are answered and which ones still wait (REQ-21): the decision ledger's
    pending or conflicting ids, plus, with the local transport, the unanswered questions in clarifications.md."""
    from decisions import LOCAL_FILE, local_sections
    local = state.get('clarification_transport') == 'local'
    ledger = read(Path(root) / feature / 'workflow/decisions.json', {})
    pending = [item['id'] for item in ledger.get('decisions', []) if item.get('status') in ('pending', 'conflict')]
    file = Path(root) / feature / LOCAL_FILE
    if local and file.is_file():
        pending += [qid for qid, section in local_sections(file.read_text(encoding='utf-8-sig')).items()
                    if qid.startswith('C') and not (section['ticked'] or section['answers'])]
    return {'transport': 'local' if local else 'github-comments',
            'answered_in': feature + '/' + LOCAL_FILE if local else 'comments on ' + state['issue'],
            'waiting': pending}


def sync_retry(state, feature):
    """A pending or failed `project-sync` with the command that retries it, else None."""
    record = state.get('project_sync') or {}
    if record.get('state') not in ('pending', 'failed'):
        return None
    return {**record, 'retry': WORKFLOW_SCRIPT + ' project-sync --feature ' + feature + ' --phase ' + record['phase']}


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


def feature_skipped(root, feature):
    """The stages the feature's checkpoint records as skipped (the tier's, the board mode's), else none."""
    try:
        state = read(Path(root) / feature / 'workflow/checkpoint.json', {})
    except (OSError, ValueError):
        return {}
    return (state.get('skipped') or {}) if isinstance(state, dict) else {}


def required_inputs(root, feature, stage, tier=None):
    """Minimum artifact coverage is enforced even if an agent omits a path.

    `tier` None reads the tier frozen in the feature's checkpoint. A lite feature treats
    research, data model, quickstart and contracts as optional consulted inputs. A feature whose
    checkpoint skips Tasks-to-Issues (`issue_sync.taskstoissues: off`) needs no task-issue journal."""
    tier = tier or feature_tier(root, feature)
    index = BASE_STAGES.index(stage)
    paths = []
    if index >= BASE_STAGES.index('specify'):
        paths += [feature + '/spec.md', feature + '/scope-source.json']
    if index >= BASE_STAGES.index('plan'):
        paths += [feature + '/plan.md']
    if index >= BASE_STAGES.index('tasks'):
        paths += [feature + '/tasks.md']
    if index >= BASE_STAGES.index('taskstoissues') and 'taskstoissues' not in feature_skipped(root, feature):
        paths += [feature + '/workflow/task-issues.json']
    constitution = '.specify/memory/constitution.md'
    if (root / constitution).is_file(): paths.append(constitution)
    if index >= BASE_STAGES.index('plan') and tier != 'lite':
        for name in LITE_OPTIONAL_INPUTS:
            if (root / feature / name).is_file(): paths.append(feature + '/' + name)
        contracts = root / feature / 'contracts'
        if contracts.is_dir():
            paths += [p.relative_to(root).as_posix() for p in contracts.rglob('*') if p.is_file()]
    return sorted(set(paths))


def first_phase_tasks(text):
    """Task ids of the first phase: the tasks up to the second `#`/`##` heading that follows a task."""
    selected = []
    for line in text.splitlines():
        if re.match(r'^#{1,2}(?!#)\s', line):
            if selected:
                break
            continue
        match = re.match(r'^\s*- \[[ xX]\]\s+(T\d{3,})\b', line)
        if match:
            selected.append(match[1])
    return selected


def consulted_inputs(receipt):
    """Inputs the receipt declared as read for context only.

    A receipt without `input_roles` (every receipt written before 1.6.0) has
    none, so every input stays a dependency: never weaker than before.
    """
    roles = receipt.get('input_roles') or {}
    return {path for path, entry in roles.items()
            if isinstance(entry, dict) and entry.get('role') == 'consulted'}


def without_required(paths, required):
    """`paths` minus the required inputs, comparing legacy backslash labels as their forward-slash form."""
    keep = {portable_label(path) for path in required}
    return {path for path in paths if portable_label(path) not in keep}


def canonical_receipt(root, receipt):
    """A copy of a new receipt whose inputs, evidence and input_roles use canonical forward-slash paths.
    Duplicates merge; two role entries for one file must be identical or the receipt is refused."""
    receipt = copy.deepcopy(receipt)
    for field in ('inputs', 'evidence'):
        values = receipt.get(field)
        if isinstance(values, list):
            receipt[field] = list(dict.fromkeys(canonical_path(root, value) for value in values))
    roles = receipt.get('input_roles')
    if isinstance(roles, dict):
        merged = {}
        for path, entry in roles.items():
            key = canonical_path(root, path)
            require(key not in merged or merged[key] == entry, 'INPUT_ROLE_COLLISION: ' + key)
            merged[key] = entry
        receipt['input_roles'] = merged
    return receipt


def dependency_fingerprints(receipt, required=()):
    """The recorded hashes a receipt's conclusion rests on. Consulted inputs keep
    their hash for provenance but do not decide whether the receipt is current;
    a required input of the stage is always a dependency."""
    consulted = without_required(consulted_inputs(receipt), required)
    return {path: value for path, value in receipt.get('fingerprints', {}).items() if path not in consulted}


def role_exempt(feature, path):
    """Feature artifacts and project memory are dependencies without a declaration."""
    path = portable_label(path)
    return path.startswith(feature + '/') or path.startswith('.specify/memory/')


def require_input_roles(policy):
    return (policy.get('receipts') or {}).get('require_input_roles') is True


def validate_input_roles(root, feature, stage, receipt, policy, tier=None):
    """Check declared roles against the receipt's own input manifest.

    Evidence and the stage's required inputs can never be consulted: the
    stage's conclusion rests on them by definition. When the policy sets
    `receipts.require_input_roles`, every input outside the feature directory
    and `.specify/memory/` must carry a declared role, so nothing becomes
    advisory by omission.
    """
    roles = receipt.get('input_roles')
    if roles is None:
        roles = {}
    require(isinstance(roles, dict), 'INPUT_ROLES_INVALID: expected a map of input path to role')
    inputs = receipt['inputs']
    protected = set(receipt['evidence']) | set(required_inputs(root, feature, stage, tier))
    for path, entry in roles.items():
        require(path in inputs, 'INPUT_ROLE_NOT_IN_MANIFEST: ' + str(path))
        require(isinstance(entry, dict) and entry.get('role') in INPUT_ROLES and set(entry) <= {'role', 'because'},
                'INPUT_ROLE_INVALID: ' + path + ' (expected {role: dependency|consulted, because: text})')
        because = entry.get('because')
        require(because is None or (isinstance(because, str) and because.strip()), 'INPUT_ROLE_REASON_INVALID: ' + path)
        if entry['role'] == 'consulted':
            require(because, 'INPUT_ROLE_REASON_REQUIRED: a consulted input states why the conclusion '
                             'does not depend on its current content: ' + path)
            require(path not in protected, 'INPUT_ROLE_CONSULTED_NOT_ALLOWED: ' + path +
                    ' is evidence or a required input of ' + stage)
    if require_input_roles(policy):
        missing = [path for path in inputs if path not in roles and not role_exempt(feature, path)]
        require(not missing, 'INPUT_ROLE_UNDECLARED: ' + ', '.join(missing))


def consulted_drift(root, feature, receipts, tier=None):
    """Changed consulted inputs: reported as advisory drift, never as staleness."""
    drift = []
    for stage, receipt in receipts.items():
        consulted = without_required(consulted_inputs(receipt), required_inputs(root, feature, stage, tier))
        saved = {path: receipt['fingerprints'][path] for path in consulted
                 if path in receipt.get('fingerprints', {})}
        if not saved:
            continue
        current = fingerprint_files(root, saved, feature=feature, like=saved)
        for path in sorted(p for p in saved if current[p] != saved[p]):
            drift.append({'stage': stage, 'path': path, 'because': receipt['input_roles'][path].get('because')})
    return drift


def gate_settings(policy):
    """The gate section of a policy, or {} when none (legacy or no policy)."""
    ci = (policy or {}).get('ci') or {}
    return ci.get('gate') if isinstance(ci.get('gate'), dict) else {}


def affected_command(policy):
    try:
        return sanduq_ci.affected_command(gate_settings(policy))
    except sanduq_ci.CIPolicyError as exc:
        raise WorkflowError(str(exc)) from exc


def verification_check(policy):
    try:
        return sanduq_ci.verification_check(gate_settings(policy))
    except sanduq_ci.CIPolicyError as exc:
        raise WorkflowError(str(exc)) from exc


def affected_lanes(root, command, paths):
    """Classify paths through the project's affected-lane hook (`ci.gate.affected_command`).

    The hook reads a JSON list of paths on stdin and prints
    `{"paths": {"<path>": ["<lane>", ...]}}`. Any failure -- a non-zero exit,
    output that is not that shape, or a path left unclassified -- raises, so
    every caller fails closed.
    """
    try:
        result = subprocess.run(command, cwd=root, input=json.dumps(sorted(paths)), capture_output=True,
                                text=True, encoding='utf-8', timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkflowError('AFFECTED_COMMAND_FAILED: ' + str(exc)) from exc
    require(result.returncode == 0, 'AFFECTED_COMMAND_FAILED: exit ' + str(result.returncode) + ': ' +
            (result.stderr or result.stdout).strip()[:300])
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        raise WorkflowError('AFFECTED_COMMAND_OUTPUT_INVALID: not JSON') from exc
    mapping = data.get('paths') if isinstance(data, dict) else None
    require(isinstance(mapping, dict), 'AFFECTED_COMMAND_OUTPUT_INVALID: expected {"paths": {"<path>": [lanes]}}')
    missing = [path for path in paths if path not in mapping]
    require(not missing, 'AFFECTED_COMMAND_OUTPUT_INVALID: no lanes for ' + ', '.join(sorted(missing)[:5]))
    lanes = {}
    for path in paths:
        value = mapping[path]
        require(isinstance(value, list) and all(isinstance(lane, str) and lane for lane in value),
                'AFFECTED_COMMAND_OUTPUT_INVALID: lanes of ' + path)
        lanes[path] = sorted(set(value))
    return lanes


def source_drift(receipt, current, root=None, feature=None):
    """Source paths added, removed or changed since the receipt's inventory."""
    old = source_fingerprints_of(root, receipt, feature)
    return sorted(path for path in set(old) | set(current)
                  if path not in old or path not in current or old[path] != current[path])


def current_source_key(root):
    """HEAD and its source key, or (None, None) when HEAD does not describe the working tree.

    The key is of a commit; a receipt inventories the working tree, so the two
    are bound only while no source path the key counts differs from HEAD.
    """
    try:
        if sk.dirty_source_paths(root):
            return None, None
        return git(root, 'rev-parse', 'HEAD'), sk.source_key(root, 'HEAD')
    except (sk.SourceKeyError, WorkflowError):
        return None, None


_HEX40 = re.compile(r'[0-9a-f]{40}')
_HEX64 = re.compile(r'[0-9a-f]{64}')


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def diff_review_command(base, head):
    """The one command whose output a recorded incremental review is bound to (`Diff sha256:`).

    `git diff-tree` is plumbing, so user diff configuration (prefixes, colour,
    renames, algorithm, external drivers, textconv) cannot change its bytes;
    `--binary` puts binary changes in the hash; the pathspec keeps exactly the
    paths the source key counts (`source_key.is_source_path`): no excluded
    prefix and no `*.md` in any ASCII case.
    """
    pathspec = ['.'] + [':(exclude)' + prefix for prefix in sk.EXCLUDED_PREFIXES] + [':(exclude,glob,icase)**/*.md']
    return ['git', '-c', 'core.quotePath=true', 'diff-tree', '-r', '-p', '--binary', '--no-renames', base, head,
            '--', *pathspec]


def diff_review_shell(base, head):
    """`diff_review_command` spelled for a POSIX shell (Git Bash on Windows)."""
    return shlex.join(diff_review_command(base, head))


def diff_review_sha256(root, base, head, timeout=300):
    """The SHA-256 of the bytes `diff_review_command(base, head)` prints; a run past `timeout` s raises
    DIFF_REVIEW_TIMEOUT (it can run under the feature lock, SAMY-02)."""
    env = {key: value for key, value in os.environ.items()
           if key not in ('GIT_LITERAL_PATHSPECS', 'GIT_GLOB_PATHSPECS', 'GIT_NOGLOB_PATHSPECS', 'GIT_ICASE_PATHSPECS')}
    result = sanduq_fs.run_bounded(
        diff_review_command(base, head), timeout=timeout, error_code='DIFF_REVIEW_TIMEOUT',
        error=WorkflowError, next_step='run "' + diff_review_shell(base, head) + '" to see why git is slow, '
        'then rerun the Workflow command', cwd=root, capture_output=True, env=env)
    require(result.returncode == 0,
            'DIFF_REVIEW_DIFF_FAILED: ' + result.stderr.decode('utf-8', 'replace').strip()[:300])
    return hashlib.sha256(result.stdout).hexdigest()


def ci_evidence_complete(receipt):
    """Whether a receipt's `ci_evidence` is the complete record `revalidate --stage verify` writes.

    `ci_evidence` lives in a committed checkpoint, so a hand-edited or partial
    record must never pass: every field the runtime writes is required and
    well-formed (fail closed), not defaulted.
    """
    evidence = receipt.get('ci_evidence')
    if not isinstance(evidence, dict):
        return False
    head, key = evidence.get('head'), evidence.get('source_key')
    return (_positive_int(evidence.get('run_id')) and _positive_int(evidence.get('attempt'))
            and isinstance(head, str) and bool(_HEX40.fullmatch(head))
            and isinstance(receipt.get('head'), str) and bool(_HEX40.fullmatch(receipt['head']))
            and isinstance(key, str) and bool(_HEX64.fullmatch(key))
            and isinstance(evidence.get('tier'), str) and bool(evidence['tier'].strip())
            and _string_list(evidence.get('lanes')) and _string_list(evidence.get('required_lanes'))
            and evidence.get('conclusion') == 'success'
            and 'lane_gap' in evidence and evidence['lane_gap'] == []
            and set(evidence['required_lanes']) <= set(evidence['lanes']))


def ci_evidence_current(root, receipt):
    """A Verify receipt's recorded CI run still covers the current source.

    The record is complete (`ci_evidence_complete`); the run concluded success
    with no lane gap and covered every lane the drift it was accepted for
    required; its head is the receipt's head or a commit of it (revalidate
    accepts a run on an ancestor with the same source key); and its source key
    (the receipt's own) is the key of the current, clean HEAD.
    """
    if not ci_evidence_complete(receipt):
        return False
    evidence = receipt['ci_evidence']
    if evidence['head'] != receipt['head']:
        if not git_ok(root, 'merge-base', '--is-ancestor', evidence['head'], receipt['head']):
            return False
    head, _ = current_source_key(root)
    if head is None:
        return False
    # Either key may predate the current key version; each version keys the same tree.
    keys = set(sk.source_keys(root, 'HEAD').values())
    return evidence['source_key'] in keys and receipt.get('source_key') in keys


def validate_evidence_snapshots(root, receipt):
    snapshots = receipt.get('evidence_snapshots', [])
    require(isinstance(snapshots, list) and all(isinstance(p, str) for p in snapshots)
            and len(set(snapshots)) == len(snapshots)
            and set(snapshots) <= set(receipt.get('evidence', [])), 'EVIDENCE_SNAPSHOTS_INVALID')
    for path in snapshots:
        try:
            evidence_snapshot.validate(root, path)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise WorkflowError('EVIDENCE_SNAPSHOT_UNRECOVERABLE: ' + path + ': ' + str(exc)) from exc


def receipt_status(root, feature, stage, receipt, policy=None, tier=None):
    """Whether a receipt is current, and why not.

    Explicit fingerprints (inputs and evidence) always keep their byte-hash
    check. For Verify, Review and Ready the source inventory is compared next:
    identical is current. A drifted inventory stays current only for a receipt
    that records a `source_key` (1.6.0 and later) when, with no drifted path
    among its explicit fingerprints, either (Verify only) its recorded CI run
    covers the current source key, or the project's affected-lane hook maps
    every drifted path to no lane. A legacy receipt without `source_key`, or a
    project without the hook, keeps the identity rule; a failing hook fails closed.
    """
    if receipt.get('stale'):
        return {'current': False, 'reason': 'marked-stale', 'stale': receipt['stale']}
    tier = tier or feature_tier(root, feature) or 'full'
    try:
        validate_evidence_snapshots(root, receipt)
    except (WorkflowError, ValueError, OSError, KeyError, TypeError) as exc:
        return {'current': False, 'reason': 'evidence-snapshot-unrecoverable', 'paths': receipt.get('evidence_snapshots', []),
                'detail': str(exc)}
    saved = receipt.get('fingerprints', {})
    required = set(required_inputs(root, feature, stage, tier))
    if not saved or not required <= {portable_label(path) for path in saved}:
        return {'current': False, 'reason': 'explicit-drift', 'paths': sorted(required - set(saved))}
    dependencies = dependency_fingerprints(receipt, required)
    now_hashes = fingerprint_files(root, dependencies, feature=feature, like=dependencies)
    if now_hashes != dependencies:
        return {'current': False, 'reason': 'explicit-drift',
                'paths': sorted(path for path in dependencies if now_hashes.get(path) != dependencies[path])}
    if stage not in SOURCE_STAGES:
        return {'current': True, 'via': 'identity'}
    if stage == 'verify' and policy and lean_policy.enabled(policy, tier):
        selected_plan = lean_policy.settings(policy).get('verification_plan')
        if selected_plan:
            selected = verification_plan.current(root, selected_plan, receipt.get('verification_snapshot'))
            if not selected['current']:
                return {'current': False, 'reason': 'verification-plan-drift', **selected}
            return {'current': True, 'via': 'verification-plan'}
    try:
        recorded = source_fingerprints_of(root, receipt, feature)
    except WorkflowError as exc:
        return {'current': False, 'reason': 'source-inventory-invalid', 'detail': str(exc)}
    current = source_fingerprints(root)
    if recorded == current:
        return {'current': True, 'via': 'identity'}
    drift = source_drift({'source_fingerprints': recorded}, current)
    stale = {'current': False, 'reason': 'source-drift', 'paths': drift}
    if not receipt.get('source_key'):
        return {**stale, 'rule': 'identity'}
    explicit = sorted(set(drift) & set(saved))
    if explicit:
        return {**stale, 'rule': 'explicit-fingerprint', 'explicit': explicit}
    if stage == 'verify' and ci_evidence_current(root, receipt):
        return {'current': True, 'via': 'ci-evidence', 'paths': drift, 'run_id': receipt['ci_evidence'].get('run_id')}
    command = affected_command(policy)
    if not command:
        return {**stale, 'rule': 'identity'}
    try:
        lanes = affected_lanes(root, command, drift)
    except WorkflowError as exc:
        return {**stale, 'rule': 'classification-failed', 'error': str(exc)}
    laned = {path: value for path, value in lanes.items() if value}
    if not laned:
        return {'current': True, 'via': 'lane-free-drift', 'paths': drift}
    return {**stale, 'rule': 'affected-lanes', 'lanes': laned}


def receipt_current(root, feature, stage, receipt, policy=None):
    return receipt_status(root, feature, stage, receipt, policy)['current']


def recovery_recipe(feature, stage, status, policy, receipt, root=None):
    """The exact commands that make a stale receipt current again (G6).

    Offers `sync-amend` first when (with `root`) the drift is a pre-1.16.0 raw hash of the Project Sync state,
    `amend` for changed evidence, `revalidate` when a checked route exists for source drift, and otherwise the
    claim/complete re-record.
    """
    at = ' --feature ' + feature
    rerecord = (f'{WORKFLOW_SCRIPT} claim{at} --usage <usage.json> (it claims {stage}; if a claim is active, '
                f'{WORKFLOW_SCRIPT} recover{at} --token <token> --reason "<why>" first), re-run {stage}, then '
                f'{WORKFLOW_SCRIPT} complete{at} --token <token> --receipt <receipt.json>')
    reason = status.get('reason')
    if reason == 'marked-stale':
        mark = status.get('stale') or {}
        if mark.get('reason') == 'ci-lane-gap':
            return [f'Run the verification check on a commit with the current source key covering lanes '
                    f'{", ".join(mark.get("lanes") or [])}, then {WORKFLOW_SCRIPT} revalidate{at} --stage verify '
                    f'--check-run <run id>', 'or re-record: ' + rerecord]
        return ['Re-record (a changed amendment undermined this receipt): ' + rerecord]
    if reason == 'explicit-drift':
        evidence = set(receipt.get('evidence') or [])
        state_file = sync_state_label(root) if root is not None else None
        raw = str((receipt.get('fingerprints') or {}).get(state_file, SYNC_BINDING_PREFIX))
        if state_file in status.get('paths', []) and not raw.startswith(SYNC_BINDING_PREFIX):
            # W20: the runtime names the step, so the per-session reading no longer has to.
            return [f'{WORKFLOW_SCRIPT} sync-amend{at} --reason "<why>" (a receipt recorded before 1.16.0 holds a '
                    f'raw hash of {state_file}; with no active claim)', 'or re-record: ' + rerecord]
        steps = [f'{WORKFLOW_SCRIPT} amend{at} --stage {stage} --evidence {path} --reason "<why>" '
                 f'--assessment unchanged|changed' for path in status.get('paths', []) if path in evidence]
        if any(path not in evidence for path in status.get('paths', [])):
            steps.append('An input changed, which no amendment covers; re-record: ' + rerecord)
        return steps or [rerecord]
    steps = []
    if status.get('rule') == 'classification-failed':
        steps.append('The affected-lane hook failed and the gate fails closed (' + str(status.get('error')) +
                     '); fix ci.gate.affected_command, or continue below.')
    if stage == 'verify':
        check = verification_check(policy)
        if check:
            steps.append(f'Push HEAD, wait for the "{check["name"]}" check to pass on it, then '
                         f'{WORKFLOW_SCRIPT} revalidate{at} --stage verify --check-run <run id>')
    elif stage == 'review' and receipt.get('head'):
        steps.append(f'Review the source diff {receipt["head"]}..HEAD and record it in {feature}/evidence/<file>.md '
                     f'with the lines "Diff reviewed: {receipt["head"]}..<HEAD sha>", "Diff sha256: <hash>" (the '
                     f'SHA-256 of the exact bytes of: {diff_review_shell(receipt["head"], "HEAD")} | sha256sum), '
                     f'"Reviewer: <who reviewed it>" and "Blocking findings: 0", then '
                     f'{WORKFLOW_SCRIPT} revalidate{at} --stage review --diff-reviewed <that file>')
    elif stage == 'ready':
        steps.append(f'Once Verify and Review are current: {WORKFLOW_SCRIPT} revalidate{at} --stage ready')
    steps.append(('or re-record: ' if steps else '') + rerecord)
    return steps


def upstream_drift(root, feature, stage, receipt, tier=None):
    """Changed dependency paths of a receipt, where a Markdown input whose only change is CRLF or trailing
    spaces counts as unchanged (compared through `text_fingerprints`; the stored hash stays the byte hash).
    A required input the receipt never fingerprinted counts as changed."""
    required = required_inputs(root, feature, stage, tier)
    saved = dependency_fingerprints(receipt, required)
    current = fingerprint_files(root, saved, feature=feature, like=saved)
    drifted = [path for path in saved if current[path] != saved[path]]
    recorded = receipt.get('text_fingerprints') or {}
    text_now = text_fingerprints(root, [path for path in drifted if current[path] is not None and path in recorded])
    changed = {path for path in drifted if not (path in text_now and text_now[path] == recorded[path])}
    changed.update(set(required) - {portable_label(path) for path in receipt.get('fingerprints', {})})
    return sorted(changed)


def receipt_drift(root, feature, stage, receipt, tier=None):
    """Explain staleness without printing source content or weakening the gate."""
    required = required_inputs(root, feature, stage, tier)
    saved = {portable_label(p): v for p, v in dependency_fingerprints(receipt, required).items()}
    current = fingerprint_files(root, set(saved) | set(required), feature=feature, like=saved)
    changed = {p for p in set(saved) | set(current) if saved.get(p) != current.get(p)}
    changed.update(set(required) - {portable_label(p) for p in receipt.get('fingerprints', {})})
    if stage in SOURCE_STAGES:
        try:
            old = source_fingerprints_of(root, receipt, feature)
        except WorkflowError:
            old = {}  # an unreadable inventory leaves every current source path reported as changed
        new = source_fingerprints(root)
        changed.update(p for p in set(old) | set(new) if p not in old or p not in new or old[p] != new[p])
    return sorted(changed)


def ready_checks(root, feature, policy, state, base=None, rules=None, warnings=None, coding_only=False):
    """Task completion, task-issue mapping and selected documentation freshness.

    The Ready stage's automated checks, shared by `ci_gate.py` (under the
    project's gate rules) and `revalidate --stage ready` (all of them).
    Returns the names of the checks that ran. When given, `warnings` collects
    non-fatal advisories in place (for example a local-only trust read on a
    fresh checkout or CI runner, round 3 finding 1); the caller decides how
    to surface them.
    """
    rules = rules or {'tasks': True, 'task_links': True, 'documentation': True}
    directory = inside(root, feature)
    ran = []
    tasks = None
    if rules.get('tasks') or rules.get('task_links'):
        from task_issues import parse_tasks
        tasks = parse_tasks((directory / 'tasks.md').read_text(encoding='utf-8-sig'))
    if rules.get('tasks'):
        if coding_only and lean_policy.enabled(policy, state_tier(state)):
            coding = lean_policy.coding_tasks((directory / 'tasks.md').read_text(encoding='utf-8-sig'))
            completion_tasks = {key: task for key, task in tasks.items() if key in coding}
        else:
            completion_tasks = tasks
        require(all(t['done'] for t in completion_tasks.values()), 'INCOMPLETE_TASKS')
        if policy.get('delegation', {}).get('enabled'):
            # A checked task delegated through the dispatcher must have a
            # verified, successful outcome, not merely a checkbox (finding 1):
            # a light-tier result the guard left unverified, or any other
            # non-successful status (running, starting, failed, abandoned --
            # finding 2c, round 2), never earns Ready on its own. The ledger
            # itself must still be trustworthy: 'untrusted' (a genuine,
            # persisted tamper, or a marker that disagrees with the current
            # bytes) refuses; 'unverified-local' (no local write marker at
            # all -- the normal state for a CI checkout or a fresh clone,
            # since delegations.json is committed but the marker is local
            # runtime state) is a warning only, and status is still enforced
            # (round 3, findings 1-2).
            from delegation import latest_attempt, ledger_trust_state, task_line_content_sha256, task_lines
            trust = ledger_trust_state(root, feature)
            require(trust != 'untrusted',
                    'DELEGATION_LEDGER_UNTRUSTED: the delegation ledger for ' + feature + ' was tampered '
                    'with (a hand-edit, or one not yet cleared by trust-reset); run '
                    '"delegate_dispatch.py trust-reset --feature ' + feature + ' --reason <text>" only '
                    'after reviewing exactly what changed')
            if trust == 'unverified-local' and warnings is not None:
                warnings.append('DELEGATION_LEDGER_TRUST_UNVERIFIED_LOCAL: no local dispatcher-write '
                                'marker for ' + feature + ' (expected on a fresh checkout or CI runner); '
                                'delegated task status is still enforced, but local tamper detection '
                                'cannot vouch for this ledger on this machine')
            # A checked task with NO attempt at all previously slipped through
            # unnoticed (round 6, finding 2): the previous check only rejected
            # a task whose latest attempt *existed* and had failed, never one
            # missing outright. Fixed by requiring 'successful' from an empty
            # record too. Round 7 removed two exemptions reviewed as bypasses:
            # a stage-wide 'delegation_enabled_for_execute: false' checkpoint
            # field (mutable, unfingerprinted, and never read here again), and
            # a per-task 'orchestrator-executed' self-certification a worker
            # could invoke. There is now exactly one way a checked task
            # without its own dispatcher attempt earns Ready: run
            # "delegate_dispatch.py adopt" to independently verify it with a
            # real acceptance check, which records an ordinary successful
            # attempt latest_attempt reads like any other -- except that an
            # adopted attempt also carries a binding (round 8, finding 1): a
            # sha256 of the task line's content (minus its checkbox state,
            # whitespace normalised) at the moment it was adopted. A task
            # whose current line no longer matches that digest -- edited,
            # or a different task entirely reusing the same id -- must not
            # ride the earlier adoption to Ready.
            current_lines = task_lines((directory / 'tasks.md').read_text(encoding='utf-8-sig'))
            not_verified, changed = [], []
            for task_id in completion_tasks:
                attempt = latest_attempt(root, feature, task_id) or {}
                if attempt.get('status') != 'successful':
                    not_verified.append(task_id)
                    continue
                if (attempt.get('adopted') and attempt.get('task_line_sha256') and
                        task_line_content_sha256(current_lines[task_id]) != attempt['task_line_sha256']):
                    changed.append(task_id)
                    continue
                # An orchestrator-run check resolving a task -- adopt for one
                # with no dispatcher attempt at all, accept for an unverified
                # light-tier one -- is exactly the kind of self-certification
                # this whole guard exists to police everywhere else; a
                # reviewer must be able to see every task that reached Ready
                # this way, not only ones a worker actually attempted (round
                # 9, finding 1b). Advisory only: status is already enforced
                # above, and ci_gate already forwards every warning here to
                # stderr and $GITHUB_STEP_SUMMARY.
                if warnings is None:
                    continue
                source = (attempt.get('accepted_evidence') or {}).get('source')
                if source == 'adopt':
                    warnings.append('DELEGATION_TASK_ADOPTED: ' + task_id + ' via "' +
                                    str(attempt.get('command')) + '" (' + str(attempt.get('expect')) +
                                    ', exit ' + str(attempt.get('exit_code')) + ')')
                elif source == 'accept':
                    resolved = next((a for a in attempt.get('acceptance_attempts', []) if a.get('accepted')),
                                    None)
                    if resolved:
                        warnings.append('DELEGATION_TASK_ACCEPTED: ' + task_id + ' via "' +
                                        str(resolved.get('command')) + '" (' + str(resolved.get('expect')) +
                                        ', exit ' + str(resolved.get('exit_code')) + ')')
            require(not not_verified, 'DELEGATION_TASK_UNVERIFIED: ' + ', '.join(sorted(not_verified)) +
                    ' - resolve with delegate_dispatch.py accept or reassign, or adopt it with an '
                    'acceptance check, before Ready')
            require(not changed, 'DELEGATION_ADOPT_TASK_CHANGED: ' + ', '.join(sorted(changed)) +
                    ' - the task line changed since it was adopted; re-run delegate_dispatch.py adopt '
                    'with a fresh acceptance check before Ready')
        ran.append('tasks')
    if rules.get('task_links') and task_issue_mode(policy) == 'off':
        ran.append('task_links:skipped (issue_sync.taskstoissues off)')
    elif rules.get('task_links'):
        mapping = read(directory / 'workflow/task-issues.json', {})
        repo, parent = state['issue'].split('#')
        require((mapping.get('repo'), mapping.get('parent'), mapping.get('feature')) == (repo, int(parent), feature),
                'TASK_MAPPING_IDENTITY_MISMATCH')
        unmapped = sorted(t for t in tasks if not (mapping.get('tasks', {}).get(t) or {}).get('linked'))
        lazy = ('; phase-lazy issue sync maps a phase when it starts: run task_issues.py --phase "<Phase heading>" '
                'for each phase still unmapped before Ready' if task_issue_mode(policy) == 'phase-lazy' else '')
        require(not unmapped, 'TASK_MAPPING_INCOMPLETE: ' + ', '.join(unmapped[:20]) + lazy)
        ran.append('task_links')
    checks = []
    if rules.get('documentation') and policy['processes']['qa']:
        checks.append(['.specify/extensions/assure/scripts/assure_state.py', 'status', '--kind', 'document'])
    if rules.get('documentation') and policy['processes']['user_manual']:
        checks.append(['.specify/extensions/user-manual/scripts/manual_state.py', 'status'])
    for args in checks:
        require((root / args[0]).is_file(), 'SELECTED_PROCESS_MISSING: ' + args[0])
        command = [sys.executable, *args, '--feature', feature, '--repo-root', str(root)]
        if base: command += ['--base-ref', base]
        result = subprocess.run(command, cwd=root, text=True, encoding='utf-8', capture_output=True)
        require(result.returncode == 0, 'DOCUMENTATION_GATE_FAILED: ' + result.stdout + result.stderr)
        require(json.loads(result.stdout).get('current') is True, 'DOCUMENTATION_NOT_CURRENT')
        ran.append('documentation:' + Path(args[0]).stem)
    return ran


def coding_review_checks(root, feature, policy, state):
    """Final coding review waits for coding/testing; artifact analysis remains available."""
    if not lean_policy.enabled(policy, state_tier(state)):
        return []
    return ready_checks(root, feature, policy, state,
                        rules={'tasks': True, 'task_links': False, 'documentation': False},
                        coding_only=True)
