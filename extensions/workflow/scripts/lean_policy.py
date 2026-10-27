"""Opt-in lean execution admission. No model routing or evidence shortcuts."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path


class LeanPolicyError(ValueError):
    pass


DEFAULTS = {'enabled': False, 'timeout_min_seconds': 300, 'timeout_max_seconds': 7200,
            'finalization_seconds': 120, 'max_attempts': 3}
KEYS = set(DEFAULTS) | {'verification_plan', 'preflight_manifest', 'scope_analysis'}
COORDINATOR_STAGES = {'taskstoissues', 'execute', 'ready', 'pr'}
FAILURE_CATEGORIES = ('provider-rejection', 'harness-failure', 'timeout',
                      'task-failure', 'evidence-missing', 'abandoned', 'unknown')


def require(condition, message):
    if not condition:
        raise LeanPolicyError(message)


def validate(config):
    require(isinstance(config, dict) and set(config) <= KEYS and
            type(config.get('enabled')) is bool, 'LEAN_POLICY_INVALID')
    value = {**DEFAULTS, **config}
    for key in ('timeout_min_seconds', 'timeout_max_seconds', 'finalization_seconds', 'max_attempts'):
        require(type(value[key]) is int and value[key] > 0, 'LEAN_POLICY_INVALID: ' + key)
    require(value['finalization_seconds'] < value['timeout_min_seconds'] <=
            value['timeout_max_seconds'] <= 28800, 'LEAN_TIMEOUT_BOUNDS_INVALID')
    for key in ('verification_plan', 'preflight_manifest', 'scope_analysis'):
        if key in value:
            require(isinstance(value[key], str) and value[key].strip(), 'LEAN_PATH_INVALID: ' + key)
    return value


def settings(policy):
    return validate(policy['lean_execution']) if 'lean_execution' in policy else dict(DEFAULTS)


def feature_tier(root, feature):
    """The tier frozen in a feature's checkpoint (`profile.tier`), or None when none is fixed or readable."""
    try:
        state = json.loads((Path(root) / feature / 'workflow/checkpoint.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError, TypeError):
        return None
    profile = state.get('profile') if isinstance(state, dict) else None
    return profile.get('tier') if isinstance(profile, dict) else None


def enabled(policy, tier=None):
    """Lean execution is on when the policy enables it, and by default for a lite or standard
    feature unless the policy sets `lean_execution.enabled: false` explicitly."""
    if tier in ('lite', 'standard') and (policy.get('lean_execution') or {}).get('enabled') is not False:
        return True
    return settings(policy)['enabled']


def coordinator_owned(policy, stage, commands, tier=None):
    if not enabled(policy, tier):
        return False
    if stage in COORDINATOR_STAGES:
        return True
    from delegation import stage_work_type
    return stage_work_type(commands, stage,
                           policy.get('delegation', {}).get('fixed_collection_commands')) == 'qa_collect'


def coding_tasks(text):
    """Classify original task lines, retaining explicit REVIEW markers."""
    from delegation import task_lines, task_type
    return {task: line for task, line in task_lines(text).items()
            if task_type(line, True) in ('implementation', 'qa_author', 'qa_collect')}


def concrete_text(value):
    # A present, non-blank string. The 12-character/3-word bar measured nothing (AHMED-28) and was dropped.
    return isinstance(value, str) and bool(value.strip())


def admit(policy, attempts, identity, work_type, deliverable, correction_plan=None, diagnosis=None, tier=None):
    if not enabled(policy, tier):
        return {}
    require(work_type != 'coordination', 'LEAN_NESTED_COORDINATOR_FORBIDDEN')
    require(concrete_text(deliverable), 'LEAN_CONCRETE_DELIVERABLE_REQUIRED')
    previous = [a for a in attempts if a.get('identity') == identity and
                a.get('status') not in ('blocked', 'intent-abandoned')]
    limit = settings(policy)['max_attempts']
    require(len(previous) < limit,
            'LEAN_ATTEMPT_LIMIT_REACHED: ' + str(identity) + ' already has ' + str(len(previous)) + ' attempts '
            '(lean_execution.max_attempts: ' + str(limit) + '). Stop and ask the owner: raise '
            'lean_execution.max_attempts in .specify/workflow.yml, or do the work natively and record it with '
            '"python .specify/extensions/workflow/scripts/delegate_dispatch.py adopt --feature ' +
            str(identity).rsplit('/', 1)[0] + ' --id ' + str(identity).rsplit('/', 1)[-1] +
            ' --command \"<acceptance command>\" --expect counts"')
    if previous:
        require(concrete_text(correction_plan), 'LEAN_CORRECTION_PLAN_REQUIRED')
        if len(previous) > 1:
            require(isinstance(diagnosis, dict) and set(diagnosis) == {'cause', 'evidence', 'change'}
                    and concrete_text(diagnosis['cause']) and concrete_text(diagnosis['change'])
                    and isinstance(diagnosis['evidence'], str) and diagnosis['evidence'].strip(),
                    'LEAN_CONCRETE_DIAGNOSIS_REQUIRED')
    return {'deliverable': deliverable.strip(), 'correction_plan': correction_plan,
            'diagnosis': diagnosis, 'attempt_number': len(previous) + 1}


def failure_category(payload, rejected=False):
    """Prefer measured harness facts; do not infer causes from a worker's prose."""
    status = payload.get('status')
    if status == 'successful':
        return None
    if rejected:
        return 'provider-rejection'
    if status == 'unverified':
        return 'evidence-missing'
    primary = (payload.get('status_provenance') or {}).get('primary')
    if (payload.get('timed_out') is True or payload.get('state') in ('timed_out', 'timeout') or
            primary == 'timeout'):
        return 'timeout'
    if primary in ('spawn_error', 'signal', 'exit_code', 'parse_error', 'telemetry_incomplete',
                   'supervisor_lost', 'relay_aborted'):
        return 'harness-failure'
    if status == 'abandoned':
        return 'abandoned'
    if primary in ('harness_telemetry', 'harness_exit') and status == 'failed':
        return 'harness-failure'
    if primary in ('task_result', 'result_block', 'delegation_result', 'self_report',
                   'head_moved', 'index_moved') and status == 'failed':
        return 'task-failure'
    return 'unknown'


FAILURE_DOMAINS = ('product', 'test', 'environment', 'workflow', 'owner-interruption', 'unknown')


def failure_attribution(value):
    """Explicit, attributed domain; independent of measured technical provenance."""
    if value is None:
        return {'domain': 'unknown', 'attribution': None}
    require(isinstance(value, dict) and set(value) == {'domain', 'actor', 'reason', 'evidence'} and
            value['domain'] in FAILURE_DOMAINS and isinstance(value['actor'], str) and value['actor'].strip()
            and concrete_text(value['reason']) and isinstance(value['evidence'], str) and value['evidence'],
            'LEAN_FAILURE_ATTRIBUTION_INVALID')
    return {'domain': value['domain'], 'attribution': value}


def timeout_guidance(policy, attempts, work_type, candidates):
    config = settings(policy)
    comparable = []
    pair = {(c['harness'], c['requested_model']) for c in candidates}
    for attempt in attempts:
        if (attempt.get('task_type') != work_type or attempt.get('status') != 'successful' or
                (attempt.get('requested_harness'), attempt.get('requested_model')) not in pair):
            continue
        try:
            elapsed = attempt.get('actual_duration_seconds')
            if type(elapsed) not in (int, float):
                elapsed = (datetime.fromisoformat(attempt['ended_at']) -
                           datetime.fromisoformat(attempt['started_at'])).total_seconds()
        except (KeyError, TypeError, ValueError):
            continue
        if elapsed > 0 and math.isfinite(elapsed):
            comparable.append(elapsed)
    # A conservative upper sample, bounded by explicit project limits.
    estimate = math.ceil(max(comparable) * 1.5) if comparable else 1800
    timeout = min(config['timeout_max_seconds'], max(config['timeout_min_seconds'],
                  estimate + config['finalization_seconds']))
    return {'timeout_seconds': timeout, 'finalization_seconds': config['finalization_seconds'],
            'comparable_runs': len(comparable), 'usage': 'measured' if comparable else 'unknown',
            'next_action': 'Reserve finalization time; return partial files, checks and remaining work. '
                           'On observation timeout collect the same run; do not launch a replacement.'}
