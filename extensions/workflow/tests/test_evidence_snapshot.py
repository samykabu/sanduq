"""Byte-exact snapshot capture, retained objects and receipt admission regressions."""
import copy
import hashlib
import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import execution_tools as execution
import evidence_snapshot as evidence
import workflow as workflow


class EvidenceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'repository'
        self.root.mkdir()
        self.git('init', '-b', 'main')
        for key, value in {'user.name': 'Snapshot test', 'user.email': 'snapshot@example.invalid',
                           'core.autocrlf': 'false', 'commit.gpgsign': 'false', 'core.hooksPath': '.git/hooks'}.items():
            self.git('config', key, value)
        for name, content in {'clean.md': b'exact\n', 'dirty.md': b'old\n',
                              'crlf.md': b'line one\nline two\n', 'filtered.md': b'canonical\n',
                              'binary.bin': b'\x00\xff\x01'}.items():
            (self.root / name).write_bytes(content)
        self.git('add', '.')
        self.git('commit', '-m', 'Snapshot inputs')

    def git(self, *args):
        result = subprocess.run(['git', *args], cwd=self.root, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
        return result.stdout

    def test_clean_git_and_dirty_untracked_crlf_filter_bytes_recover_exactly(self):
        (self.root / 'dirty.md').write_bytes(b'changed\n')
        (self.root / 'untracked.md').write_bytes('مرحبا\r\n'.encode('utf-8'))
        (self.root / 'crlf.md').write_bytes(b'line one\r\nline two\r\n')
        (self.root / 'filtered.md').write_bytes(b'checkout-filter-expanded\n')
        labels = ['clean.md', 'dirty.md', 'untracked.md', 'crlf.md', 'filtered.md', 'binary.bin']
        originals = {p: (self.root / p).read_bytes() for p in labels}
        result = evidence.capture(self.root, labels, 'evidence/before.json')
        self.assertEqual((result['git_records'], result['file_records']), (2, 4))
        value = json.loads((self.root / 'evidence/before.json').read_text(encoding='utf-8'))
        self.assertEqual([r['kind'] for r in value['records']], ['git', 'file', 'file', 'file', 'file', 'git'])
        for label in labels:
            (self.root / label).write_bytes(b'later stage edits')
        self.assertEqual(evidence.resolve(self.root, 'evidence/before.json'), originals)
        workflow.validate_evidence_snapshots(self.root, {'evidence': ['evidence/before.json'],
                                                       'evidence_snapshots': ['evidence/before.json']})
        with self.assertRaises(ValueError):
            evidence.capture(self.root, ['clean.md'], 'evidence/before.json')

    def test_missing_retention_and_missing_objects_are_refused(self):
        evidence.capture(self.root, ['clean.md'], 'before.json')
        value = json.loads((self.root / 'before.json').read_text(encoding='utf-8'))
        record = value['records'][0]
        retained = record['retention']
        self.git('update-ref', '-d', retained)
        with self.assertRaises(ValueError):
            evidence.resolve(self.root, 'before.json')
        self.git('update-ref', retained, record['commit'])
        with patch.object(evidence, '_blob_content', side_effect=evidence.InputIdentityError('missing retained object')):
            with self.assertRaisesRegex(ValueError, 'missing retained object'):
                evidence.resolve(self.root, 'before.json')
        loose = self.root / '.git/objects' / record['blob'][:2] / record['blob'][2:]
        self.assertTrue(loose.is_file())
        # Git loose objects can be read-only; Windows requires write permission to unlink.
        loose.chmod(loose.stat().st_mode | stat.S_IWUSR)
        loose.unlink()  # loss fixture in this test's disposable repository
        with self.assertRaises(ValueError):
            evidence.resolve(self.root, 'before.json')

    def test_tamper_missing_file_proof_wrong_repository_commit_and_blob_refuse_admission(self):
        (self.root / 'dirty.md').write_bytes(b'dirty')
        evidence.capture(self.root, ['clean.md', 'dirty.md'], 'before.json')
        snapshot = self.root / 'before.json'
        original = snapshot.read_bytes()
        value = json.loads(original)
        for field, invalid in (('repository', 'different-repo'), ('commit', 'HEAD'), ('blob', '0' * 40), ('sha256', '0' * 64)):
            edited = copy.deepcopy(value)
            edited['records'][0][field] = invalid
            snapshot.write_text(json.dumps(edited), encoding='utf-8')
            with self.assertRaises(ValueError):
                evidence.resolve(self.root, 'before.json')
        snapshot.write_bytes(original)
        proof = self.root / value['records'][1]['proof']
        proof.write_bytes(b'tamper')
        receipt = {'evidence': ['before.json'], 'evidence_snapshots': ['before.json']}
        with self.assertRaises(workflow.WorkflowError):
            workflow.validate_evidence_snapshots(self.root, receipt)
        self.assertFalse(workflow.receipt_status(self.root, 'specs/example', 'specify', receipt)['current'])
        proof.unlink()
        with self.assertRaises(ValueError):
            evidence.resolve(self.root, 'before.json')
        with self.assertRaises(workflow.WorkflowError):
            workflow.validate_evidence_snapshots(self.root, {'evidence': ['other'], 'evidence_snapshots': ['before.json']})

    def test_cli_capture_and_resolve_preserve_arabic_and_literal_paths(self):
        label = 'space quote مرحبا $ file.txt'
        original = 'Arabic مرحبا\r\n'.encode('utf-8')
        (self.root / label).write_bytes(original)
        with patch('sys.stdout'):
            self.assertEqual(execution.main(['evidence-capture', '--root', str(self.root), '--path', label, '--out', 'capture.json']), 0)
            self.assertEqual(execution.main(['evidence-resolve', '--root', str(self.root), '--snapshot', 'capture.json',
                                             '--path', label, '--out', str(self.root / 'recovered')]), 0)
        self.assertEqual((self.root / 'recovered').read_bytes(), original)

    def move_repository(self):
        moved = self.root.with_name('moved-repository')
        self.root.rename(moved)
        self.root = moved

    def write_snapshot(self, value):
        (self.root / 'before.json').write_text(json.dumps(value), encoding='utf-8')

    def snapshot(self):
        return json.loads((self.root / 'before.json').read_text(encoding='utf-8'))

    def test_moved_repository_recovers_v1_proofs_without_rewriting_receipt(self):
        (self.root / 'dirty.md').write_bytes(b'changed\r\n')
        expected = {'clean.md': b'exact\n', 'dirty.md': b'changed\r\n'}
        evidence.capture(self.root, list(expected), 'before.json')
        receipt = {'evidence': ['before.json'], 'evidence_snapshots': ['before.json'],
                   'fingerprints': {'before.json': evidence.file_digest(self.root / 'before.json')}}
        (self.root / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
        originals = {p: (self.root / p).read_bytes() for p in ('before.json', 'receipt.json')}
        previous = self.snapshot()['records'][0]['repository']
        self.move_repository()
        self.assertNotEqual(previous, evidence.repository(self.root))
        for label in expected:
            (self.root / label).unlink()
        self.assertEqual(evidence.resolve(self.root, 'before.json'), expected)
        with patch.object(workflow, 'required_inputs', return_value=['before.json']):
            self.assertTrue(workflow.receipt_status(self.root, 'specs/example', 'specify', receipt)['current'])
        self.assertEqual({p: (self.root / p).read_bytes() for p in originals}, originals)

    def test_moved_linked_worktree_recovers_using_shared_retention(self):
        worktree = self.root.with_name('worktree')
        self.git('worktree', 'add', '--detach', str(worktree), 'HEAD')
        evidence.capture(worktree, ['clean.md'], 'before.json')
        original = (worktree / 'before.json').read_bytes()
        moved = worktree.with_name('moved-worktree')
        worktree.rename(moved)
        self.git('worktree', 'repair', str(moved))
        self.assertEqual(evidence.resolve(moved, 'before.json'), {'clean.md': b'exact\n'})
        self.assertEqual((moved / 'before.json').read_bytes(), original)

    def test_moved_repository_requires_exact_retained_ref_commit_blob_and_sha(self):
        evidence.capture(self.root, ['clean.md'], 'before.json')
        original = self.snapshot()
        record = original['records'][0]
        self.move_repository()
        receipt = {'evidence': ['before.json'], 'evidence_snapshots': ['before.json']}

        def refused():
            for read in (evidence.resolve, evidence.validate):
                with self.assertRaises(ValueError):
                    read(self.root, 'before.json')
            with self.assertRaises(workflow.WorkflowError):
                workflow.validate_evidence_snapshots(self.root, receipt)
            self.assertEqual(workflow.receipt_status(self.root, 'specs/example', 'specify', receipt)['reason'],
                             'evidence-snapshot-unrecoverable')

        self.git('update-ref', '-d', record['retention'])
        refused()  # Original commit and blob still exist, but retention is mandatory.
        self.git('commit', '--allow-empty', '-m', 'Another commit')
        other = self.git('rev-parse', 'HEAD').decode('ascii').strip()
        self.git('update-ref', record['retention'], other)
        refused()  # A valid ref pointing to the wrong commit is insufficient.
        self.git('update-ref', record['retention'], record['commit'])
        for field, invalid in (('retention', 'refs/sanduq/evidence/' + '0' * 32),
                               ('retention', 'HEAD'), ('commit', other), ('commit', 'HEAD'),
                               ('blob', '0' * len(record['blob'])), ('sha256', '0' * 64)):
            with self.subTest(field=field, invalid=invalid):
                edited = copy.deepcopy(original)
                edited['records'][0][field] = invalid
                self.write_snapshot(edited)
                refused()
        # Even a ref and descriptor agreeing on an existing non-commit must fail.
        self.git('update-ref', record['retention'], record['blob'])
        edited = copy.deepcopy(original)
        edited['records'][0]['commit'] = record['blob']
        self.write_snapshot(edited)
        refused()

    def test_git_payload_content_is_verified_against_blob_identity(self):
        evidence.capture(self.root, ['clean.md'], 'before.json')
        record = self.snapshot()['records'][0]
        # Git replacement can return different bytes for an otherwise valid OID.
        (self.root / 'replacement').write_bytes(b'other\n')
        replacement = self.git('hash-object', '-w', 'replacement').decode('ascii').strip()
        self.git('replace', record['blob'], replacement)
        for read in (evidence.resolve, evidence.validate):
            with self.assertRaisesRegex(ValueError, 'EVIDENCE_BLOB_IDENTITY_MISMATCH'):
                read(self.root, 'before.json')

    def test_record_count_rejected_before_payload_reads_for_resolve_and_capture(self):
        (self.root / 'dirty.md').write_bytes(b'dirty')
        evidence.capture(self.root, ['dirty.md'], 'before.json')
        record = self.snapshot()['records'][0]
        labels = [f'label-{i}' for i in range(evidence.MAX_RECORDS + 1)]
        self.write_snapshot({'schema': evidence.SCHEMA, 'records': [dict(record, path=p) for p in labels]})
        with patch.object(evidence, '_file_content') as files, patch.object(evidence, '_blob_content') as blobs:
            for read in (evidence.resolve, evidence.validate):
                with self.assertRaisesRegex(ValueError, 'EVIDENCE_TOO_MANY_RECORDS'):
                    read(self.root, 'before.json')
            with patch.object(evidence, '_file_size') as sizes:
                with self.assertRaisesRegex(ValueError, 'EVIDENCE_TOO_MANY_RECORDS'):
                    evidence.capture(self.root, labels, 'too-many.json')
                sizes.assert_not_called()
            files.assert_not_called()
            blobs.assert_not_called()
        self.assertFalse((self.root / 'too-many.json').exists())

    def test_aggregate_budget_counts_repeated_file_proof_before_any_payload_read(self):
        data = b'changed\n'
        (self.root / 'dirty.md').write_bytes(data)
        evidence.capture(self.root, ['dirty.md'], 'before.json')
        record = self.snapshot()['records'][0]
        self.write_snapshot({'schema': evidence.SCHEMA, 'records': [record, dict(record, path='alias.md')]})
        with patch.object(evidence, 'MAX_TOTAL_BYTES', len(data) * 2 - 1), \
                patch.object(evidence, '_file_content') as files, patch.object(evidence, '_blob_content') as blobs:
            for read in (evidence.resolve, evidence.validate):
                with self.assertRaisesRegex(ValueError, 'EVIDENCE_PAYLOAD_TOO_LARGE'):
                    read(self.root, 'before.json')
            files.assert_not_called()
            blobs.assert_not_called()
        with patch.object(evidence, 'MAX_TOTAL_BYTES', len(data) * 2):
            self.assertEqual(evidence.resolve(self.root, 'before.json'), {'dirty.md': data, 'alias.md': data})

    def test_aggregate_budget_counts_repeated_git_blob_before_any_payload_read(self):
        (self.root / 'dirty.md').write_bytes(b'exact\n')
        self.git('add', 'dirty.md')
        self.git('commit', '-m', 'Shared Git blob')
        evidence.capture(self.root, ['clean.md', 'dirty.md'], 'before.json')
        records = self.snapshot()['records']
        self.assertEqual(records[0]['blob'], records[1]['blob'])
        with patch.object(evidence, 'MAX_TOTAL_BYTES', 11), \
                patch.object(evidence, '_file_content') as files, patch.object(evidence, '_blob_content') as blobs:
            for read in (evidence.resolve, evidence.validate):
                with self.assertRaisesRegex(ValueError, 'EVIDENCE_PAYLOAD_TOO_LARGE'):
                    read(self.root, 'before.json')
            files.assert_not_called()
            blobs.assert_not_called()
        with patch.object(evidence, 'MAX_TOTAL_BYTES', 12):
            self.assertEqual(evidence.resolve(self.root, 'before.json'),
                             {'clean.md': b'exact\n', 'dirty.md': b'exact\n'})

    def test_capture_aggregate_preflight_happens_before_proofs_refs_or_payload_reads(self):
        with patch.object(evidence, 'MAX_TOTAL_BYTES', 9), \
                patch.object(evidence, '_file_content') as files, patch.object(evidence, '_blob_content') as blobs:
            with self.assertRaisesRegex(ValueError, 'EVIDENCE_PAYLOAD_TOO_LARGE'):
                evidence.capture(self.root, ['clean.md', 'dirty.md'], 'too-large.json')
            files.assert_not_called()
            blobs.assert_not_called()
        self.assertFalse((self.root / 'too-large.json').exists())
        self.assertFalse((self.root / 'too-large.json.objects').exists())
        self.assertEqual(self.git('for-each-ref', '--format=%(refname)', 'refs/sanduq/evidence/'), b'')

    def test_capture_and_receipt_admission_and_freshness_use_streaming_validation(self):
        (self.root / 'dirty.md').write_bytes(b'dirty\n')
        with patch.object(evidence, 'resolve', side_effect=AssertionError('payload dict is unused')), \
                patch.object(evidence, 'validate', wraps=evidence.validate) as validate:
            evidence.capture(self.root, ['clean.md', 'dirty.md'], 'before.json')
            self.assertEqual(validate.call_count, 1)
            receipt = {'evidence': ['before.json'], 'evidence_snapshots': ['before.json'],
                       'fingerprints': {'before.json': evidence.file_digest(self.root / 'before.json')}}
            with patch.object(evidence, '_file_content', wraps=evidence._file_content) as files, \
                    patch.object(evidence, '_blob_content', wraps=evidence._blob_content) as blobs:
                self.assertIsNone(evidence.validate(self.root, 'before.json'))
                workflow.validate_evidence_snapshots(self.root, receipt)
                with patch.object(workflow, 'required_inputs', return_value=['before.json']):
                    self.assertTrue(workflow.receipt_status(self.root, 'specs/example', 'specify', receipt)['current'])
                self.assertTrue(files.call_args_list)
                self.assertTrue(blobs.call_args_list)
                self.assertTrue(all(call.args[-1] is False for call in files.call_args_list + blobs.call_args_list))

    def test_streaming_reads_are_bounded_and_refuse_size_changes(self):
        class TrackedStream(io.BytesIO):
            def read(self, size=-1):
                self.requests.append(size)
                return super().read(size)

        data = b'12345678'
        stream = TrackedStream(data)
        stream.requests = []
        with patch.object(evidence, 'CHUNK_BYTES', 3):
            self.assertEqual(evidence._consume(stream, len(data), False), (None, hashlib.sha256(data).hexdigest()))
        self.assertTrue(all(0 < size <= 3 for size in stream.requests))
        stream.seek(0)
        with self.assertRaisesRegex(ValueError, 'EVIDENCE_CONTENT_SIZE_MISMATCH'):
            evidence._consume(stream, 4, True)
        self.assertEqual(stream.tell(), 5)
        stream.seek(0)
        with self.assertRaisesRegex(ValueError, 'EVIDENCE_CONTENT_SIZE_MISMATCH'):
            evidence._consume(stream, 9, False)

    def test_budget_errors_become_cli_errors_and_stale_receipts(self):
        evidence.capture(self.root, ['clean.md', 'dirty.md'], 'before.json')
        receipt = {'evidence': ['before.json'], 'evidence_snapshots': ['before.json']}
        with patch.object(evidence, 'MAX_TOTAL_BYTES', 9):
            with self.assertRaisesRegex(workflow.WorkflowError, 'EVIDENCE_PAYLOAD_TOO_LARGE'):
                workflow.validate_evidence_snapshots(self.root, receipt)
            self.assertEqual(workflow.receipt_status(self.root, 'specs/example', 'specify', receipt)['reason'],
                             'evidence-snapshot-unrecoverable')
            with patch('sys.stdout', new_callable=io.StringIO) as output:
                self.assertEqual(execution.main(['evidence-resolve', '--root', str(self.root), '--snapshot', 'before.json',
                                                 '--path', 'clean.md', '--out', str(self.root / 'recovered')]), 2)
                self.assertIn('EVIDENCE_PAYLOAD_TOO_LARGE', json.loads(output.getvalue())['error'])
        self.assertFalse((self.root / 'recovered').exists())
