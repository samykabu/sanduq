#!/usr/bin/env python3
"""Explain a workflow gate failure and, only for evidence-only drift, offer to fix it (B13).

Runs the same evidence check `ci_gate.py` runs, then turns a `WorkflowError`
into a structured recovery recipe by reusing `workflow.receipt_status` and
`workflow.recovery_recipe` directly -- the exact functions the gate itself
calls -- rather than re-deriving drift classification. `--auto-fix` never
invents a new classification: it runs `Run.amend` (standing rule 4's own
checked re-hash) and only when every drifted path of the failing stage is
already one of that receipt's declared `evidence` paths *and* is not also a
declared input or a required core artifact of that stage (review round 1,
finding 1: a path can be listed as both `evidence` and a dependency the
stage's conclusion actually rests on -- amending that path's hash under
`unchanged` would silently launder a real semantic change, not just fix a
typo in a proof-of-work write-up). A dependency change, a lane-affecting
source drift, a lane gap or a changed amendment are never eligible; those
always print the recipe only. `--reason` and `--assessment` are both required
for a fix (no default): the caller states, in their own words, why the
assessment holds, and chooses `unchanged` or `changed` deliberately. Refuses
outright inside a delegated worker or orchestrator process
(`SANDUQ_DELEGATED_RUN`/`SANDUQ_DELEGATED_ROLE`, finding 3): this is a
dispatcher-level decision, never a worker's. Every eligible path is
re-validated before any is amended (finding 11), so a fix is all-or-nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_gate
import sanduq_ci
from delegate_dispatch import require_not_worker_context
from workflow import Run, WorkflowError, fingerprint_files, inside, recovery_recipe, require, receipt_status, \
    required_inputs

STALE_RECEIPT = re.compile(r'^STALE_RECEIPT: (?P<stage>[a-z_]+);')


def explain(root, feature, base_ref):
    """Run the gate; on failure, return a structured explanation instead of only a message."""
    root = root.resolve()
    run = Run(root, feature)
    policy = run.policy
    rules = sanduq_ci.gate_config(policy['ci'])['rules']
    try:
        ci_gate.check(root, feature, policy, base_ref, rules)
        return {'ok': True, 'status': 'passed'}
    except WorkflowError as exc:
        message = str(exc)
        code = message.split(':', 1)[0]
        result = {'ok': False, 'status': 'failed', 'error_code': code, 'message': message,
                  'evidence_only_eligible': False}
        match = STALE_RECEIPT.match(message)
        if not match:
            return result
        stage = match.group('stage')
        state = run.load()
        receipt = state.get('receipts', {}).get(stage, {})
        status = receipt_status(root, feature, stage, receipt, policy)
        result['stage'] = stage
        result['recovery'] = recovery_recipe(feature, stage, status, policy, receipt)
        evidence = set(receipt.get('evidence') or [])
        # A path that is also a declared input, or one of the stage's required
        # core artifacts, is never amend-only eligible even if it is listed as
        # evidence too: the stage's conclusion may rest on its content.
        non_amendable = set(receipt.get('inputs') or []) | set(required_inputs(root, feature, stage))
        drifted = set(status.get('paths') or [])
        result['evidence_only_eligible'] = bool(
            status.get('reason') == 'explicit-drift' and drifted
            and drifted <= evidence and not (drifted & non_amendable))
        if result['evidence_only_eligible']:
            result['evidence_only_paths'] = sorted(drifted)
            result['stage_for_fix'] = stage
        return result


def auto_fix(root, feature, explanation, reason, assessment):
    """Apply the amend recipe `explain` found eligible. Refuses anything else.

    Pre-validates every path amend() would itself check (existence, hash
    actually changed) against one loaded state snapshot before amending any
    of them, so a mid-list failure never leaves a partial fix applied.
    """
    require(explanation.get('evidence_only_eligible'), 'GATE_EXPLAIN_NOT_EVIDENCE_ONLY: nothing safe to auto-fix')
    require(isinstance(reason, str) and reason.strip(), 'GATE_EXPLAIN_REASON_REQUIRED')
    require(assessment in ('unchanged', 'changed'), 'GATE_EXPLAIN_ASSESSMENT_INVALID')
    root = root.resolve()
    require_not_worker_context(feature)
    run = Run(root, feature)
    stage = explanation['stage_for_fix']
    state = run.load()
    receipt = state.get('receipts', {}).get(stage) or {}
    paths = explanation['evidence_only_paths']
    # Recompute eligibility from the receipt as it is now, never trusting the
    # earlier explanation: a path that has since become a declared input (or
    # stopped being evidence) is refused. `amend(evidence_only=True)` repeats
    # the check under its own lock immediately before each write.
    non_amendable = set(receipt.get('inputs') or []) | set(required_inputs(root, feature, stage))
    for path in paths:
        require(path in set(receipt.get('evidence') or []) and path not in non_amendable,
                'GATE_EXPLAIN_NO_LONGER_EVIDENCE_ONLY: ' + path)
        inside(root, path)
        new_hash = fingerprint_files(root, [path])[path]
        require(new_hash is not None, 'EVIDENCE_MISSING: ' + path)
        old_hash = (receipt.get('fingerprints') or {}).get(path)
        require(old_hash is not None and new_hash != old_hash, 'AMENDMENT_NOT_NEEDED: ' + path)
    amendments = [run.amend(stage, path, reason, assessment, evidence_only=True) for path in paths]
    return {'ok': True, 'stage': stage, 'amendments': amendments}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--feature', required=True)
    parser.add_argument('--base-ref', required=True)
    parser.add_argument('--auto-fix', action='store_true')
    parser.add_argument('--reason')
    parser.add_argument('--assessment', choices=('unchanged', 'changed'))
    args = parser.parse_args()
    try:
        explanation = explain(args.root, args.feature, args.base_ref)
        fixed = False
        if args.auto_fix and not explanation.get('ok', True):
            require(args.assessment is not None, 'GATE_EXPLAIN_ASSESSMENT_REQUIRED: --assessment unchanged|changed')
            explanation['fix'] = auto_fix(args.root, args.feature, explanation, args.reason, args.assessment)
            fixed = explanation['fix'].get('ok', False)
        print(json.dumps(explanation, indent=2))
        return 0 if explanation.get('ok') or fixed else 1
    except (WorkflowError, ValueError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, indent=2))
        return 1


if __name__ == '__main__':
    sys.exit(main())
