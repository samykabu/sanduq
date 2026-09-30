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
        self.assertIn('PENDING_TARGET_SYMLINK_REFUSED', result['rejected'][0]['reason'])
        self.assertEqual(victim.read_text(encoding='utf-8'), '# Victim\n\n## Sec\n\nOriginal.\n')

    def _symlink_or_skip(self, link, target, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except OSError as exc:
            self.skipTest('cannot create symlinks on this host: ' + str(exc))

    def test_symlinked_contracts_directory_is_rejected(self):
        # Round 3, finding 1: resolving both sides is fooled when `contracts`
        # itself is a symlink to another in-repo directory.
        other = self.directory / 'elsewhere'
        other.mkdir()
        (other / 'api.md').write_text('# API\n\n## Response shape\n\nOriginal elsewhere.\n', encoding='utf-8')
        real = self.directory / 'contracts'
        (real / 'api.md').unlink()
        real.rmdir()
        self._symlink_or_skip(real, other, directory=True)
        self.pending.write_text(ENTRY, encoding='utf-8')
        result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertEqual(len(result['rejected']), 1)
        self.assertIn('PENDING_TARGET_SYMLINK_REFUSED', result['rejected'][0]['reason'])
        self.assertIn('Original elsewhere.', (other / 'api.md').read_text(encoding='utf-8'))

    def test_symlinked_exact_file_is_rejected(self):
        real = self.directory / 'real-model.md'
        real.write_text('# Model\n\n## Sec\n\nOriginal.\n', encoding='utf-8')
        self._symlink_or_skip(self.directory / 'data-model.md', real)
        entry = '## specs/001-example/data-model.md#Sec\nStatus: pending\n```markdown\nPwned.\n```\n'
        self.pending.write_text(entry, encoding='utf-8')
        result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertIn('PENDING_TARGET_SYMLINK_REFUSED', result['rejected'][0]['reason'])
        self.assertIn('Original.', real.read_text(encoding='utf-8'))

    def test_uses_the_shared_link_test_not_a_copy(self):
        import delegation
        self.assertIs(ap.is_link, delegation.is_link)

    @unittest.skipUnless(os.name == 'nt', 'directory junctions are Windows-only')
    def test_junctioned_contracts_directory_is_rejected(self):
        # Round 4, item 1: a junction is not reported by is_symlink (and
        # Path.is_junction is missing before Python 3.12).
        import _winapi
        other = self.directory / 'elsewhere'
        other.mkdir()
        (other / 'api.md').write_text('# API\n\n## Response shape\n\nOriginal elsewhere.\n', encoding='utf-8')
        real = self.directory / 'contracts'
        (real / 'api.md').unlink()
        real.rmdir()
        _winapi.CreateJunction(str(other), str(real))
        self.pending.write_text(ENTRY, encoding='utf-8')
        result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertIn('PENDING_TARGET_SYMLINK_REFUSED', result['rejected'][0]['reason'])
        self.assertIn('Original elsewhere.', (other / 'api.md').read_text(encoding='utf-8'))

    def _swap_contracts_for_a_link(self):
        """Replace contracts/ with a symlink to a directory holding its own api.md."""
        other = self.directory / 'elsewhere'
        other.mkdir(exist_ok=True)
        (other / 'api.md').write_text('# API\n\n## Response shape\n\nOriginal elsewhere.\n', encoding='utf-8')
        moved = self.directory / 'contracts-real'
        (self.directory / 'contracts').rename(moved)
        self._symlink_or_skip(self.directory / 'contracts', other, directory=True)
        return other

    def test_a_parent_swapped_after_validation_is_refused_before_the_temp_file(self):
        # Round 4, item 2(a): re-validation right before the temp file is created.
        self.pending.write_text(ENTRY, encoding='utf-8')
        real_mkstemp = ap.tempfile.mkstemp
        holder = {}

        def swapping(*args, **kwargs):
            if 'other' not in holder:
                holder['other'] = self._swap_contracts_for_a_link()
            return real_mkstemp(*args, **kwargs)
        # The swap fires on the first mkstemp, i.e. after the pre-temp validation
        # passed; the second validation (before os.replace) must refuse.
        with patch.object(ap.tempfile, 'mkstemp', swapping):
            result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertEqual(result['applied'], [])
        self.assertIn('PENDING_TARGET_SYMLINK_REFUSED', result['rejected'][0]['reason'])
        self.assertIn('Original elsewhere.', (holder['other'] / 'api.md').read_text(encoding='utf-8'))
        self.assertEqual([p.name for p in holder['other'].glob('.pending-*')], [])

    def test_a_write_that_lands_elsewhere_is_detected_and_restored(self):
        # Round 4, item 2(b): the swap happens after the last validation, at
        # the moment of the replace; the landed file is put back afterwards.
        self.pending.write_text(ENTRY, encoding='utf-8')
        real_replace = ap.os.replace
        state = {'swapped': False}
        holder = {}

        def swapping(src, dst):
            if not state['swapped'] and str(dst).endswith('.pending-backup'):
                state['swapped'] = True
                holder['other'] = self._swap_contracts_for_a_link()
                import shutil  # keep the temp file reachable through the swapped path
                for temp in (self.directory / 'contracts-real').glob('.pending-*.tmp'):
                    shutil.move(str(temp), str(holder['other'] / temp.name))
            return real_replace(src, dst)
        with patch.object(ap.os, 'replace', swapping):
            result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertEqual(result['applied'], [])
        self.assertIn('PENDING_WRITE_LANDED_ELSEWHERE', result['rejected'][0]['reason'])
        self.assertIn('Original elsewhere.', (holder['other'] / 'api.md').read_text(encoding='utf-8'))
        self.assertNotIn('deprecated', (holder['other'] / 'api.md').read_text(encoding='utf-8'))

    def test_two_headings_in_one_contract_both_land(self):
        # Round 3, finding 2: each entry used to re-read the original and
        # write at once, so the last one silently erased the earlier change.
        contract = self.directory / 'contracts/api.md'
        contract.write_text('# API\n\n## One\n\nold one\n\n## Two\n\nold two\n', encoding='utf-8')
        entries = ''.join(f'## specs/001-example/contracts/api.md#{h}\nStatus: pending\n```markdown\nnew {h}\n```\n'
                          for h in ('One', 'Two'))
        self.pending.write_text(entries, encoding='utf-8')
        result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertEqual(len(result['applied']), 2)
        text = contract.read_text(encoding='utf-8')
        self.assertIn('new One', text)
        self.assertIn('new Two', text)
        self.assertNotIn('old', text)

    def test_entry_is_not_marked_applied_when_its_write_fails(self):
        self.pending.write_text(ENTRY, encoding='utf-8')
        real_write = ap.write_text

        def failing(path, text, **kwargs):
            if path.name == 'api.md':
                raise OSError('disk full')
            return real_write(path, text, **kwargs)
        with patch.object(ap, 'write_text', failing):
            result = ap.apply(self.root, self.feature, apply_changes=True)
        self.assertEqual(result['applied'], [])
        self.assertIn('WRITE_FAILED', result['rejected'][0]['reason'])
        self.assertIn('Status: rejected', self.pending.read_text(encoding='utf-8'))

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
