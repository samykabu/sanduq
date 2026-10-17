"""Workflow's local Memory adapter. Never verifies, synthesizes or archives a feature."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys


class HandoffError(Exception):
    pass


def helper(root, *args):
    argv = [sys.executable, '-B', str(root / '.specify/extensions/memory/scripts/archive.py'),
            '--root', str(root), *args]
    result = subprocess.run(argv, cwd=root, capture_output=True, text=True, encoding='utf-8')
    try:
        body = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise HandoffError('MEMORY_HELPER_MALFORMED: ' + ' '.join(args)) from None
    if result.returncode != 0 or not isinstance(body, dict) or body.get('success') is not True:
        error = body.get('error', 'unsuccessful result') if isinstance(body, dict) else 'invalid envelope'
        raise HandoffError(f'MEMORY_HELPER_FAILED ({result.returncode}): {error}')
    if not isinstance(body.get('data'), dict):
        raise HandoffError('MEMORY_HELPER_MALFORMED: missing data object')
    return body['data']


def action(command, arguments, reason):
    return {'command': command, 'arguments': arguments, 'reason': reason}


def handoff(w, root, transition, feature=None, checks=None, report=None):
    """Persist a recoverable result separately from accepted product stage receipts.

    One host dispatcher invokes returned registered commands. Subprocess argv are
    argument arrays, and the installed Memory CLI remains the eligibility authority.
    """
    root = root.resolve()
    key = w.digest([transition, feature])
    path = root / '.specify/workflow/runtime/memory-handoffs' / (key + '.json')
    result = {'transition': transition, 'feature': feature, 'status': 'pending',
              'ok': True, 'actions': [], 'updated_at': w.now()}

    def finish(status, reason, actions=(), ok=True):
        missing = [item['command'] for item in actions if not w.command_exists(root, item['command'])]
        if missing:
            status, reason, ok = 'blocked', 'MEMORY_COMMAND_UNAVAILABLE: ' + ', '.join(missing), False
        result.update(status=status, reason=reason, actions=list(actions), ok=ok)
        w.write(path, result)
        result['state_file'] = path.relative_to(root).as_posix()
        return result

    def session(reason, arguments=None):
        return action('speckit.memory.session', arguments or [], reason)

    try:
        with w.locked(root / '.specify/workflow/runtime/dispatch.lock'):
            entry = w.registry(root).get('memory')
            if not entry or entry.get('enabled') is not True:
                return finish('pending', 'MEMORY_DEPENDENCY_MISSING_OR_DISABLED')
            if not (root / '.specify/extensions/memory/scripts/archive.py').is_file():
                return finish('blocked', 'MEMORY_HELPER_MISSING', ok=False)
            pending = helper(root, 'pending')
            if (not isinstance(pending.get('enabled'), bool)
                    or not isinstance(pending.get('ready'), list)
                    or not isinstance(pending.get('blocked'), list)
                    or not all(k in pending for k in ('active_run', 'writer', 'guard_blockers'))):
                raise HandoffError('MEMORY_HELPER_MALFORMED: pending contract')
            result['pending'] = pending
            # Recovery is required even after automatic approval has been disabled.
            if pending.get('active_run'):
                run_id = pending['active_run']
                if not isinstance(run_id, str) or not re.fullmatch('[a-f0-9]{32}', run_id):
                    raise HandoffError('MEMORY_HELPER_MALFORMED: active_run')
                result['recovery'] = helper(root, 'status')
                return finish('blocked', 'MEMORY_ACTIVE_RECOVERY_REQUIRED',
                              [session('Resume the active transaction before new work.', ['--run', run_id])], False)
            if pending.get('writer') or pending.get('guard_blockers'):
                return finish('blocked', 'MEMORY_WRITER_OR_NUMBER_GUARD_BLOCKED',
                              [session('Inspect pending writer/guard blockers; never remove a live lock.')], False)
            if not pending['enabled']:
                return finish('pending', pending.get('reason') or 'MEMORY_AUTOMATIC_MODE_DISABLED')
            policy_data = helper(root, 'policy')
            policy = policy_data.get('policy')
            if not isinstance(policy, dict) or not isinstance(policy.get('target_branch'), str):
                raise HandoffError('MEMORY_HELPER_MALFORMED: policy contract')
            common = Path(w.git(root, 'rev-parse', '--git-common-dir'))
            memory_state = (common if common.is_absolute() else root / common).resolve() / 'sanduq-memory'
            approval = w.read(memory_state / 'approval.json', {})
            # Memory 2.1.x validates its hash, but not approval.root, on queue.
            if approval.get('root') != str(root):
                return finish('pending', 'MEMORY_APPROVAL_CHECKOUT_MISMATCH')
            if not policy_data.get('policy_hash') or approval.get('policy_hash') != policy_data['policy_hash']:
                return finish('pending', 'Automatic mode is disabled or needs policy/implementation review and renewal.')
            queue = w.read(memory_state / 'pending.json', {})
            if not isinstance(queue, dict):
                raise HandoffError('MEMORY_HELPER_MALFORMED: queue contract')
            if transition == 'execute':
                run = w.Run(root, feature)
                state = run.load()
                if not state.get('receipts', {}).get('execute'):
                    return finish('blocked', 'MEMORY_EXECUTE_RECEIPT_REQUIRED', ok=False)
                existing = queue.get(feature)
                if existing is not None:
                    if (existing.get('root') != str(root)
                            or existing.get('enabled_at') != approval.get('enabled_at')):
                        return finish('pending', 'Queue entry predates current enablement or belongs to another worktree.')
                    # A hook or an earlier handoff already queued it. Never reset its
                    # timestamps, checks, merge inputs or verification lineage.
                    return finish('queued', 'MEMORY_ALREADY_QUEUED')
                selected = checks if checks is not None else policy.get('default_checks', [])
                if (not isinstance(selected, list) or not selected
                        or any(not isinstance(c, str) or not c for c in selected)
                        or len(set(selected)) != len(selected)):
                    return finish('pending', 'MEMORY_CHECK_SELECTION_REQUIRED',
                                  [action('speckit.memory.prepare', ['--spec', feature],
                                          'Select configured checks covering this implementation and retry the native handoff.')])
                # Write intent before the mutating helper. On retry its durable
                # pending entry resolves an interrupted response without requeueing.
                finish('pending', 'MEMORY_QUEUE_IN_PROGRESS')
                queued = helper(root, 'queue', '--spec', feature,
                                *[arg for check in selected for arg in ('--check', check)])
                if queued.get('queued') != feature or queued.get('deletion') is not False:
                    raise HandoffError('MEMORY_HELPER_MALFORMED: queue result')
                return finish('queued', 'MEMORY_QUEUED')
            if transition == 'postmerge':
                if not isinstance(report, dict):
                    return finish('blocked', 'MEMORY_POSTMERGE_REPORT_REQUIRED', ok=False)
                run = w.Run(root, feature)
                state = run.load(allow_branch_change=True)
                repo = w.github_repository(root)
                pr = state.get('receipts', {}).get('pr', {}).get('pr_url')
                target = policy['target_branch']
                if (report.get('feature') != feature or not isinstance(report.get('repository'), str)
                        or not w.same_github_repository(report.get('repository'), repo)
                        or not pr or report.get('pr_url') != pr or report.get('target_branch') != target
                        or state.get('target_branch') != target or report.get('verified') is not True
                        or any(not re.fullmatch('[a-f0-9]{40}', str(report.get(k, '')))
                               for k in ('head_sha', 'merge_sha'))):
                    return finish('blocked', 'MEMORY_POSTMERGE_BINDING_MISMATCH', ok=False)
                result['binding'] = report
                if report.get('report_only') is True:
                    return finish('pending', 'MEMORY_REPORT_ONLY_FOLLOWUP')
                if w.git(root, 'branch', '--show-current') != target:
                    return finish('pending', 'Awaiting local merge/check-out of the configured target branch.')
                w.git(root, 'merge-base', '--is-ancestor', report['merge_sha'], 'HEAD')
            elif transition != 'session':
                raise HandoffError('MEMORY_TRANSITION_INVALID')
            if w.git(root, 'branch', '--show-current') != policy['target_branch']:
                return finish('pending', 'Awaiting local merge/check-out of the configured target branch.')
            selected = [feature] if feature else list(queue)
            actions = []
            reasons = []
            for spec in selected:
                blocked = [item['reason'] for item in pending['blocked'] if item.get('spec') == spec]
                reasons.extend(blocked)
                item = queue.get(spec)
                if item is None:
                    reasons.append('MEMORY_FEATURE_NOT_QUEUED: ' + spec)
                    continue
                if item.get('root') != str(root) or item.get('enabled_at') != approval.get('enabled_at'):
                    reasons.append('Queue entry predates current enablement or belongs to another worktree.')
                    continue
                selected_checks = item.get('checks')
                if not isinstance(selected_checks, list) or not selected_checks:
                    raise HandoffError('MEMORY_HELPER_MALFORMED: queued checks')
                arguments = ['--spec', spec, '--automatic',
                             *[arg for check in selected_checks for arg in ('--check', check)]]
                if spec in pending['ready']:
                    actions.append(action('speckit.memory.run', arguments,
                                          'Approved eligible work; synthesis and independent review still required.'))
                elif any(item.get('spec') == spec for item in pending.get('needs_verification', [])):
                    actions.append(session('Inspect completion and execute approved checks before the registered run.',
                                           ['--spec', spec]))
            if actions:
                return finish('dispatch', 'MEMORY_REGISTERED_ACTION_REQUIRED', actions)
            return finish('pending' if reasons else 'idle', '; '.join(dict.fromkeys(reasons)) or 'MEMORY_NO_ELIGIBLE_WORK')
    except (HandoffError, w.WorkflowError, OSError, ValueError, KeyError, TypeError) as error:
        return finish('blocked', str(error), ok=False)
