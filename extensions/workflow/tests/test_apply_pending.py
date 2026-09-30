"""B13: speckit-workflow-apply-pending applies workflow/pending-artifact-updates.md (F15) --
the mechanical half only; it never judges wording, and it reports staleness with the gate's
own recovery recipe rather than re-validating anything itself."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_parent_traversal_target_is_rejected(self):
        # Review round 1, finding 4: a `..` target must never escape
        # <feature>/contracts, data-model.md or research.md.
        victim = self.root / 'outside-victim.md'
        victim.write_text('# Victim\n\n## Sec\n\nOriginal.\n', encoding='utf-8')
        entry = ('## specs/001-example/contracts/../../../outside-victim.md#Sec\n'
                 'Status: pending\n```markdown\nPwned.\n```\n')
        self.pending.write_text(entry, encoding='utf-8')
        result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertEqual(len(result['rejected']), 1)
        reason = result['rejected'][0]['reason']
        self.assertTrue(reason.startswith('PENDING_TARGET_ABSOLUTE_REFUSED') or
                        reason.startswith('PATH_OUTSIDE_PROJECT') or
                        reason.startswith('PENDING_TARGET_NOT_ALLOWED'), reason)
        self.assertEqual(victim.read_text(encoding='utf-8'), '# Victim\n\n## Sec\n\nOriginal.\n')

    def test_absolute_path_target_is_rejected(self):
        victim = self.root / 'outside-victim.md'
        victim.write_text('# Victim\n\n## Sec\n\nOriginal.\n', encoding='utf-8')
        absolute = str(victim).replace('\\', '/')
        entry = f'## {absolute}#Sec\nStatus: pending\n```markdown\nPwned.\n```\n'
        self.pending.write_text(entry, encoding='utf-8')
        result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertEqual(len(result['rejected']), 1)
        self.assertIn('PENDING_TARGET_ABSOLUTE_REFUSED', result['rejected'][0]['reason'])
        self.assertEqual(victim.read_text(encoding='utf-8'), '# Victim\n\n## Sec\n\nOriginal.\n')

    def test_symlinked_target_escaping_contracts_is_rejected(self):
        victim = self.root / 'outside-victim.md'
        victim.write_text('# Victim\n\n## Sec\n\nOriginal.\n', encoding='utf-8')
        link = self.directory / 'contracts' / 'link.md'
        try:
            link.symlink_to(victim)
        except OSError:
            self.skipTest('symlinks unsupported (no privilege) on this host')
        entry = '## specs/001-example/contracts/link.md#Sec\nStatus: pending\n```markdown\nPwned.\n```\n'
        self.pending.write_text(entry, encoding='utf-8')
        result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertEqual(len(result['rejected']), 1)
        self.assertIn('PENDING_TARGET_NOT_ALLOWED', result['rejected'][0]['reason'])
        self.assertEqual(victim.read_text(encoding='utf-8'), '# Victim\n\n## Sec\n\nOriginal.\n')

    def test_pending_file_itself_must_stay_inside_the_repo(self):
        outside = self.root.parent / 'outside-pending.md'
        try:
            outside.write_text(ENTRY, encoding='utf-8')
            with self.assertRaises(w.WorkflowError) as ctx:
                ap.apply(self.root, self.feature, pending_path='../outside-pending.md', apply_changes=False)
            self.assertIn('PATH_OUTSIDE_PROJECT', str(ctx.exception))
        finally:
            outside.unlink(missing_ok=True)

    def test_apply_refuses_inside_a_delegated_worker(self):
        self.pending.write_text(ENTRY, encoding='utf-8')
        with patch.dict(os.environ, {'SANDUQ_DELEGATED_RUN': 'specs/001-example/T001'}):
            with self.assertRaises(ValueError) as ctx:
                ap.apply(self.root, self.feature, apply_changes=True)
        self.assertIn('DELEGATION_WORKER_CONTEXT', str(ctx.exception))
        self.assertNotIn('deprecated', (self.directory / 'contracts/api.md').read_text(encoding='utf-8'))

    def test_apply_refuses_while_a_claim_is_active(self):
        self.policy = w.default_policy(False, False)
        self.configure()
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        w.write(run.feature / 'scope-source.json', {'repo': 'acme/app', 'issue': 10})
        run.claim({'session_id': 's', 'observed_at': w.now(), 'method': 'estimated', 'fraction': .1,
                  'next_fraction': .05})
        self.pending.write_text(ENTRY, encoding='utf-8')
        with self.assertRaises(w.WorkflowError) as ctx:
            ap.apply(self.root, self.feature, apply_changes=True)
        self.assertIn('APPLY_PENDING_ACTIVE_CLAIM_MUST_BE_RESOLVED', str(ctx.exception))
        self.assertNotIn('deprecated', (self.directory / 'contracts/api.md').read_text(encoding='utf-8'))

    def test_stale_check_failure_is_reported_not_swallowed(self):
        # Review round 1, finding 5: a real error computing staleness must
        # surface as `stale: null` + `stale_error`, never a bare `[]` that
        # looks identical to "confirmed nothing is stale".
        self.policy = w.default_policy(False, False)
        self.configure()
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        contract_path = self.feature + '/contracts/api.md'
        state = run.load()
        state['receipts']['plan'] = {'stage': 'plan', 'summary': 'planned', 'outcome': 'passed',
                                     'inputs': [contract_path], 'evidence': [contract_path],
                                     'fingerprints': w.fingerprint_files(self.root, [contract_path])}
        run.save(state)
        with patch('apply_pending.stale_after', side_effect=w.WorkflowError('BOOM: simulated failure')):
            self.pending.write_text(ENTRY, encoding='utf-8')
            result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertIsNone(result['stale'])
        self.assertIn('BOOM', result['stale_error'])

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
