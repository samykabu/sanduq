"""B13: speckit-workflow-apply-pending applies workflow/pending-artifact-updates.md (F15) --
the mechanical half only; it never judges wording, and it reports staleness with the gate's
own recovery recipe rather than re-validating anything itself."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import apply_pending as ap
import workflow as w
import test_workflow as fixture

ENTRY = '''## specs/001-example/contracts/api.md#Response shape
Source: T012 (adds the deprecated field)
Status: pending
```markdown
The response includes a `deprecated` boolean field.
```
'''
SECOND_ENTRY = '''## specs/001-example/contracts/api.md#Missing section
Source: T013 (typo)
Status: pending
```markdown
No such heading exists.
```
'''


class ApplyPendingTests(unittest.TestCase):
    configure = fixture.WorkflowTests.configure

    def setUp(self):
        fixture.WorkflowTests.setUp(self)
        self.directory = self.root / self.feature
        (self.directory / 'contracts').mkdir(parents=True)
        (self.directory / 'contracts/api.md').write_text(
            '# API\n\n## Response shape\n\nThe response includes an `id` field.\n\n## Other\n\nUnrelated.\n',
            encoding='utf-8')
        (self.directory / 'workflow').mkdir(exist_ok=True)
        self.pending = self.directory / 'workflow/pending-artifact-updates.md'

    def test_dry_run_reports_would_apply_without_writing(self):
        self.pending.write_text(ENTRY, encoding='utf-8')
        result = ap.apply(self.root, self.feature, apply_changes=False)
        self.assertEqual(result['applied'], ['specs/001-example/contracts/api.md#Response shape'])
        self.assertNotIn('deprecated', (self.directory / 'contracts/api.md').read_text(encoding='utf-8'))

    def test_apply_replaces_the_named_section_body(self):
        self.pending.write_text(ENTRY, encoding='utf-8')
        ap.apply(self.root, self.feature, apply_changes=True)
        text = (self.directory / 'contracts/api.md').read_text(encoding='utf-8')
        self.assertIn('The response includes a `deprecated` boolean field.', text)
        self.assertNotIn('an `id` field', text)
        self.assertIn('## Other', text)

    def test_apply_marks_the_entry_applied_and_is_idempotent(self):
        self.pending.write_text(ENTRY, encoding='utf-8')
        ap.apply(self.root, self.feature, apply_changes=True)
        pending_text = self.pending.read_text(encoding='utf-8')
        self.assertIn('Status: applied', pending_text)
        result = ap.apply(self.root, self.feature, apply_changes=False)
        self.assertEqual(result['applied'], [])

    def test_missing_anchor_is_rejected_with_a_reason(self):
        self.pending.write_text(SECOND_ENTRY, encoding='utf-8')
        result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertEqual(len(result['rejected']), 1)
        self.assertIn('ANCHOR_NOT_FOUND', result['rejected'][0]['reason'])

    def test_missing_target_file_is_rejected(self):
        self.pending.write_text(ENTRY.replace('contracts/api.md', 'contracts/missing.md'), encoding='utf-8')
        result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertEqual(len(result['rejected']), 1)
        self.assertIn('TARGET_FILE_MISSING', result['rejected'][0]['reason'])

    def test_apply_reports_staleness_of_a_receipt_that_fingerprinted_the_target(self):
        self.policy = w.default_policy(False, False)
        self.configure()
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        contract_path = self.feature + '/contracts/api.md'
        evidence_path = self.feature + '/evidence/plan.txt'
        (run.feature / 'evidence').mkdir(exist_ok=True)
        (run.feature / 'evidence/plan.txt').write_text('evidence', encoding='utf-8')
        (run.feature / 'spec.md').write_text('# Spec', encoding='utf-8')
        w.write(run.feature / 'scope-source.json', {'repo': 'acme/app', 'issue': 10})
        (run.feature / 'plan.md').write_text('# Plan', encoding='utf-8')
        all_paths = [self.feature + '/spec.md', self.feature + '/scope-source.json', self.feature + '/plan.md',
                    contract_path, evidence_path]
        state = run.load()
        state['receipts']['plan'] = {'stage': 'plan', 'summary': 'planned', 'outcome': 'passed',
                                     'inputs': all_paths, 'evidence': [evidence_path],
                                     'fingerprints': w.fingerprint_files(self.root, all_paths)}
        run.save(state)
        self.pending.write_text(ENTRY, encoding='utf-8')
        result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertTrue(result['stale'])
        self.assertEqual(result['stale'][0]['stage'], 'plan')
        self.assertTrue(result['stale'][0]['recovery'])


if __name__ == '__main__':
    unittest.main()
