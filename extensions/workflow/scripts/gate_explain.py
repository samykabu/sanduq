#!/usr/bin/env python3
"""Explain a workflow gate failure and, only for evidence-only drift, offer to fix it (B13).

Runs the same evidence check `ci_gate.py` runs, then turns a `WorkflowError`
into a structured recovery recipe by reusing `workflow.receipt_status` and
`workflow.recovery_recipe` directly -- the exact functions the gate itself
calls -- rather than re-deriving drift classification. `--auto-fix` never
invents a new classification: it runs `Run.amend` (standing rule 4's own
checked re-hash) and only when every drifted path of the failing stage is
already one of that receipt's declared `evidence` paths (`explicit-drift`
whose recovery is amend-only, never a fallback re-record). A dependency
change, a lane-affecting source drift, a lane gap or a changed amendment are
never eligible; those always print the recipe only. `--reason` is required
for a fix and is never fabricated: the caller states, in their own words, why
the assessment holds.
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
from workflow import Run, WorkflowError, recovery_recipe, require, receipt_status

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
        result['evidence_only_eligible'] = bool(
            status.get('reason') == 'explicit-drift' and status.get('paths')
            and set(status['paths']) <= evidence)
        if result['evidence_only_eligible']:
            result['evidence_only_paths'] = sorted(status['paths'])
            result['stage_for_fix'] = stage
        return result


def auto_fix(root, feature, explanation, reason, assessment):
    """Apply the amend recipe `explain` found eligible. Refuses anything else."""
    require(explanation.get('evidence_only_eligible'), 'GATE_EXPLAIN_NOT_EVIDENCE_ONLY: nothing safe to auto-fix')
    require(isinstance(reason, str) and reason.strip(), 'GATE_EXPLAIN_REASON_REQUIRED')
    require(assessment in ('unchanged', 'changed'), 'GATE_EXPLAIN_ASSESSMENT_INVALID')
    run = Run(root.resolve(), feature)
    stage = explanation['stage_for_fix']
    amendments = [run.amend(stage, path, reason, assessment) for path in explanation['evidence_only_paths']]
    return {'ok': True, 'stage': stage, 'amendments': amendments}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--feature', required=True)
    parser.add_argument('--base-ref', required=True)
    parser.add_argument('--auto-fix', action='store_true')
    parser.add_argument('--reason')
    parser.add_argument('--assessment', choices=('unchanged', 'changed'), default='unchanged')
    args = parser.parse_args()
    try:
        explanation = explain(args.root, args.feature, args.base_ref)
        fixed = False
        if args.auto_fix and not explanation.get('ok', True):
            explanation['fix'] = auto_fix(args.root, args.feature, explanation, args.reason, args.assessment)
            fixed = explanation['fix'].get('ok', False)
        print(json.dumps(explanation, indent=2))
        return 0 if explanation.get('ok') or fixed else 1
    except WorkflowError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, indent=2))
        return 1


if __name__ == '__main__':
    sys.exit(main())
