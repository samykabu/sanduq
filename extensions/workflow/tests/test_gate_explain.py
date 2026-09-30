"""B13: speckit-workflow-gate-explain explains STALE_RECEIPT with the gate's own recipe, and
--auto-fix touches only drift the existing rules already classify as evidence-only (standing rule 4).

Review round 1, finding 1: a path listed as both `evidence` and a declared
input (or a required core artifact) of the stage must never be eligible --
amending it under `unchanged` would silently launder a real semantic change.
`make_evidence_only` builds a receipt where the touched path is evidence
*only*, never a declared input, to test the genuinely safe case separately
from the overlap case the default fixture (`receipt()`, which lists the same
path as both) now exercises."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ci_gate as c
import gate_explain as ge
import workflow as w
import test_workflow as fixture


class GateExplainTests(unittest.TestCase):
    setUp = fixture.WorkflowTests.setUp
    configure = fixture.WorkflowTests.configure
    usage = fixture.WorkflowTests.usage
    receipt = fixture.WorkflowTests.receipt

    def ready(self):
        self.policy = w.default_policy(False, False)
        # Keep this fixture offline: live_answers hits the real GitHub API
        # (see ci_gate.check), which this unit test has no business needing.
        self.policy['ci']['gate']['rules']['live_answers'] = False
        self.configure()
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        w.write(run.feature / 'scope-source.json', {'repo': 'acme/app', 'issue': 10})
        (run.feature / 'tasks.md').write_text('- [x] T001 Done behavior', encoding='utf-8')
        w.write(run.feature / 'workflow/task-issues.json', {'repo': 'acme/app', 'parent': 10, 'feature': self.feature,
                'tasks': {'T001': {'number': 11, 'linked': True}}})
        for stage in w.stages(self.policy):
            if stage == 'pr':
                break
            claim = run.claim(self.usage())
            run.complete(claim['token'], self.receipt(stage))
        return run

    def make_evidence_only(self, run, stage='plan'):
        """Remove the evidence path from the stage's declared `inputs` (fingerprints,
        core required paths and `evidence` are untouched), so it is evidence *only*."""
        evidence_path = self.feature + '/evidence/' + stage + '.txt'
        state = run.load()
        receipt = state['receipts'][stage]
        receipt['inputs'] = [p for p in receipt['inputs'] if p != evidence_path]
        run.save(state)
        return evidence_path

    def test_passing_gate_reports_ok(self):
        self.ready()
        self.assertEqual(ge.explain(self.root, self.feature, None), {'ok': True, 'status': 'passed'})

    def test_true_evidence_only_drift_is_eligible_with_amend_recovery(self):
        run = self.ready()
        evidence_path = self.make_evidence_only(run)
        (self.root / evidence_path).write_text('a clarified sentence, not a behavior change', encoding='utf-8')
        result = ge.explain(self.root, self.feature, None)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error_code'], 'STALE_RECEIPT')
        self.assertEqual(result['stage'], 'plan')
        self.assertTrue(result['evidence_only_eligible'])
        self.assertEqual(result['evidence_only_paths'], [evidence_path])
        self.assertTrue(any('amend' in step for step in result['recovery']))

    def test_path_declared_as_both_input_and_evidence_is_never_eligible(self):
        # Review round 1, finding 1: this is exactly the shape the default
        # `receipt()` fixture builds (the same path in both `inputs` and
        # `evidence`) -- amending it under `unchanged` would silently
        # launder a real change to content the stage's conclusion rests on.
        self.ready()
        evidence = self.root / self.feature / 'evidence/plan.txt'
        evidence.write_text('a change to the very thing plan.md concluded from', encoding='utf-8')
        result = ge.explain(self.root, self.feature, None)
        self.assertFalse(result['ok'])
        self.assertEqual(result['stage'], 'plan')
        self.assertFalse(result['evidence_only_eligible'])
        self.assertNotIn('evidence_only_paths', result)

    def test_dependency_only_drift_is_not_eligible(self):
        run = self.ready()
        other = run.feature / 'other-dependency.txt'
        other.write_text('v1', encoding='utf-8')
        other_path = self.feature + '/other-dependency.txt'
        state = run.load()
        plan_receipt = state['receipts']['plan']
        plan_receipt['inputs'].append(other_path)
        plan_receipt['fingerprints'][other_path] = w.fingerprint_files(self.root, [other_path])[other_path]
        run.save(state)
        other.write_text('v2', encoding='utf-8')
        result = ge.explain(self.root, self.feature, None)
        self.assertEqual(result['stage'], 'plan')
        self.assertFalse(result['evidence_only_eligible'])

    def test_auto_fix_requires_a_reason(self):
        run = self.ready()
        evidence_path = self.make_evidence_only(run)
        (self.root / evidence_path).write_text('typo fix', encoding='utf-8')
        explanation = ge.explain(self.root, self.feature, None)
        with self.assertRaises(w.WorkflowError):
            ge.auto_fix(self.root, self.feature, explanation, reason='', assessment='unchanged')

    def test_auto_fix_refuses_when_not_evidence_only(self):
        self.ready()
        explanation = {'evidence_only_eligible': False}
        with self.assertRaises(w.WorkflowError) as ctx:
            ge.auto_fix(self.root, self.feature, explanation, reason='ok', assessment='unchanged')
        self.assertIn('GATE_EXPLAIN_NOT_EVIDENCE_ONLY', str(ctx.exception))

    def test_auto_fix_amends_and_the_gate_passes_again(self):
        run = self.ready()
        evidence_path = self.make_evidence_only(run)
        (self.root / evidence_path).write_text('a clarified sentence', encoding='utf-8')
        explanation = ge.explain(self.root, self.feature, None)
        fix = ge.auto_fix(self.root, self.feature, explanation, reason='editorial clarification only',
                          assessment='unchanged')
        self.assertTrue(fix['ok'])
        self.assertEqual(ge.explain(self.root, self.feature, None), {'ok': True, 'status': 'passed'})

    def test_missing_evidence_file_still_refuses_a_blind_auto_fix(self):
        # Coarse eligibility (drift confined to the receipt's own evidence
        # paths, none of them also a declared input) says yes, but `amend`
        # re-hashes the real file and refuses when it is gone -- standing
        # rule 4 holds even when the first check would have let it through.
        run = self.ready()
        evidence_path = self.make_evidence_only(run)
        (self.root / evidence_path).unlink()
        result = ge.explain(self.root, self.feature, None)
        self.assertFalse(result['ok'])
        self.assertTrue(result['evidence_only_eligible'])
        with self.assertRaises(w.WorkflowError) as ctx:
            ge.auto_fix(self.root, self.feature, result, reason='ok', assessment='unchanged')
        self.assertIn('EVIDENCE_MISSING', str(ctx.exception))

    def test_auto_fix_is_all_or_nothing_across_multiple_paths(self):
        # Finding 11: two evidence-only paths are eligible by the coarse
        # check; one of them fails amend's own re-hash (file deleted). Even
        # though the other path is genuinely fixable, neither must be
        # amended -- the whole fix is refused before any amend() call runs.
        run = self.ready()
        plan_evidence = self.make_evidence_only(run)
        state = run.load()
        second_path = self.feature + '/evidence/second.txt'
        (self.root / second_path).write_text('v1', encoding='utf-8')
        state['receipts']['plan']['evidence'].append(second_path)
        state['receipts']['plan']['fingerprints'][second_path] = w.fingerprint_files(
            self.root, [second_path])[second_path]
        run.save(state)
        (self.root / plan_evidence).write_text('a real, fixable clarification', encoding='utf-8')
        (self.root / second_path).write_text('v2', encoding='utf-8')
        (self.root / second_path).unlink()  # this one will fail amend's EVIDENCE_MISSING check
        explanation = ge.explain(self.root, self.feature, None)
        self.assertTrue(explanation['evidence_only_eligible'])
        self.assertEqual(set(explanation['evidence_only_paths']), {plan_evidence, second_path})
        with self.assertRaises(w.WorkflowError) as ctx:
            ge.auto_fix(self.root, self.feature, explanation, reason='ok', assessment='unchanged')
        self.assertIn('EVIDENCE_MISSING', str(ctx.exception))
        # Neither path was amended: the receipt is unchanged and still stale.
        after = ge.explain(self.root, self.feature, None)
        self.assertFalse(after['ok'])
        self.assertEqual(after.get('recovery'), explanation.get('recovery'))

    def test_auto_fix_requires_an_explicit_assessment_via_cli(self):
        # Finding 2: --assessment has no default; omitting it with --auto-fix
        # is refused rather than silently treated as "unchanged".
        run = self.ready()
        evidence_path = self.make_evidence_only(run)
        (self.root / evidence_path).write_text('typo fix', encoding='utf-8')
        import contextlib
        import io
        output = io.StringIO()
        with patch.object(sys, 'argv', ['gate_explain.py', '--root', str(self.root), '--feature', self.feature,
                                        '--base-ref', 'HEAD', '--auto-fix', '--reason', 'ok']), \
             contextlib.redirect_stdout(output):
            code = ge.main()
        self.assertEqual(code, 1)
        self.assertIn('GATE_EXPLAIN_ASSESSMENT_REQUIRED', output.getvalue())
        # Nothing was amended by the failed CLI invocation.
        self.assertFalse(ge.explain(self.root, self.feature, None)['ok'])

    def test_auto_fix_refuses_inside_a_delegated_worker(self):
        # Finding 3: gate-explain's auto-fix is a dispatcher-level decision,
        # never a worker's, matching amend()'s own guard.
        run = self.ready()
        evidence_path = self.make_evidence_only(run)
        (self.root / evidence_path).write_text('typo fix', encoding='utf-8')
        explanation = ge.explain(self.root, self.feature, None)
        with patch.dict(os.environ, {'SANDUQ_DELEGATED_RUN': 'spec/001-example/T001'}):
            with self.assertRaises(ValueError) as ctx:
                ge.auto_fix(self.root, self.feature, explanation, reason='ok', assessment='unchanged')
        self.assertIn('DELEGATION_WORKER_CONTEXT', str(ctx.exception))
        # Nothing was amended: the gate is still failing the same way.
        self.assertEqual(ge.explain(self.root, self.feature, None)['ok'], False)


if __name__ == '__main__':
    unittest.main()
