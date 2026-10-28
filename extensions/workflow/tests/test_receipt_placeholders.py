"""OMAR-01: the receipt template prints every gating field as a placeholder, and `complete` refuses a placeholder
left in place with RECEIPT_PLACEHOLDER naming the field, for every stage that has one."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow as w  # noqa: E402
from test_front_half_runtime import Base  # noqa: E402

FILLS = {'outcome': 'passed', 'effort_score': 13, 'unresolved': 0, 'answers_applied': True,
         'native_links_verified': True, 'blocking_findings': 0, 'images_verified': True,
         'lint': {'ok': True, 'findings': 0}, 'pr_url': 'https://github.com/acme/app/pull/11'}


class ReceiptPlaceholderTests(Base):
    def test_an_unmodified_template_is_refused_naming_each_gating_field(self):
        self.profiles()
        self.policy['issue_sync'] = {'taskstoissues': 'phase-lazy', 'parent_link': 'native-subissue'}
        self.configure()
        run = self.run_object()
        refused = set()
        while True:
            claim = self.claim_any(run)
            stage, template = claim['stage'], claim['receipt_template']
            self.assertEqual(template['outcome'], '<passed|failed|blocked>')
            fixture = self.receipt(stage)
            # Only what the template leaves blank is filled: the unedited gating fields must refuse.
            unmodified = {**template, 'summary': fixture['summary'], 'evidence': fixture['evidence'],
                          'inputs': template['inputs'] + fixture['inputs']}
            with self.subTest(stage=stage), self.assertRaisesRegex(w.WorkflowError, 'RECEIPT_PLACEHOLDER: outcome '):
                run.complete(claim['token'], unmodified)
            filled = {**unmodified, **{key: FILLS[key] for key in template if key in FILLS}}
            for field in [key for key in template if key in FILLS]:
                with self.subTest(stage=stage, field=field), \
                        self.assertRaisesRegex(w.WorkflowError, 'RECEIPT_PLACEHOLDER: ' + field + r'\b'):
                    run.complete(claim['token'], {**filled, field: template[field]})
                refused.add(field)
            run.complete(claim['token'], filled)
            if stage == 'pr':
                break
        self.assertEqual(refused, set(FILLS) - {'lint'})  # score 13 is the full tier: Analyze is a model stage

    def test_the_evidence_placeholder_is_refused_and_lite_plan_names_its_lint_file(self):
        """R2: no template shows `"evidence": []`, which EVIDENCE_REQUIRED refuses; lite Plan names the lint output."""
        self.profiles()
        run = self.run_object()
        claim = self.claim_any(run)
        template = claim['receipt_template']
        self.assertEqual(template['evidence'], ['<existing file that proves the work>'])
        receipt = {**self.receipt('scope'), 'effort_score': 2, 'evidence': template['evidence']}
        with self.assertRaisesRegex(w.WorkflowError, '^RECEIPT_PLACEHOLDER: evidence '):
            run.complete(claim['token'], receipt)
        run.complete(claim['token'], {**receipt, 'evidence': self.receipt('scope')['evidence']})
        self.advance(run, 'clarify')
        claim = run.claim(self.usage())
        self.assertEqual(claim['receipt_template']['evidence'], [self.feature + '/evidence/plan-lint.json'])

    def test_receipt_refusals_explain_themselves(self):
        """R2, R3: the two completion refusals the lite runs met print what, why and the next step."""
        for code in ('EVIDENCE_REQUIRED', 'INPUT_ROLE_NOT_IN_MANIFEST: specs/1-x/scope-analysis.json'):
            with self.subTest(code=code):
                result = w.explain(code, 'specs/1-x')
                self.assertTrue(result['explain'].endswith('.') and result['next'], result)
        self.assertIn('lint.py --feature specs/1-x', w.explain('EVIDENCE_REQUIRED', 'specs/1-x')['next'])


if __name__ == '__main__':
    unittest.main()
