"""B13: speckit-workflow-gate-explain explains STALE_RECEIPT with the gate's own recipe, and
--auto-fix touches only drift the existing rules already classify as evidence-only (standing rule 4)."""
import sys
import unittest
from pathlib import Path

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

    def test_passing_gate_reports_ok(self):
        self.ready()
        self.assertEqual(ge.explain(self.root, self.feature, None), {'ok': True, 'status': 'passed'})

    def test_evidence_only_drift_is_eligible_with_amend_recovery(self):
        self.ready()
        evidence = self.root / self.feature / 'evidence/plan.txt'
        evidence.write_text('a clarified sentence, not a behavior change', encoding='utf-8')
        result = ge.explain(self.root, self.feature, None)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error_code'], 'STALE_RECEIPT')
        self.assertEqual(result['stage'], 'plan')
        self.assertTrue(result['evidence_only_eligible'])
        self.assertEqual(result['evidence_only_paths'], [self.feature + '/evidence/plan.txt'])
        self.assertTrue(any('amend' in step for step in result['recovery']))

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
        self.ready()
        (self.root / self.feature / 'evidence/plan.txt').write_text('typo fix', encoding='utf-8')
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
        self.ready()
        (self.root / self.feature / 'evidence/plan.txt').write_text('a clarified sentence', encoding='utf-8')
        explanation = ge.explain(self.root, self.feature, None)
        fix = ge.auto_fix(self.root, self.feature, explanation, reason='editorial clarification only',
                          assessment='unchanged')
        self.assertTrue(fix['ok'])
        self.assertEqual(ge.explain(self.root, self.feature, None), {'ok': True, 'status': 'passed'})

    def test_missing_evidence_file_still_refuses_a_blind_auto_fix(self):
        # Coarse eligibility (drift confined to the receipt's own evidence
        # paths) says yes, but `amend` re-hashes the real file and refuses
        # when it is gone -- standing rule 4 holds even when the first check
        # would have let it through.
        run = self.ready()
        (run.feature / 'evidence/plan.txt').unlink()
        result = ge.explain(self.root, self.feature, None)
        self.assertFalse(result['ok'])
        self.assertTrue(result['evidence_only_eligible'])
        with self.assertRaises(w.WorkflowError) as ctx:
            ge.auto_fix(self.root, self.feature, result, reason='ok', assessment='unchanged')
        self.assertIn('EVIDENCE_MISSING', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
