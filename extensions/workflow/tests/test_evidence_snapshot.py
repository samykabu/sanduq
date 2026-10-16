"""Byte-exact snapshot capture, retained objects and receipt admission regressions."""
import copy
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
        self.root = Path(self.tmp.name).resolve()
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
        actual = evidence.git
        def missing(root, *args):
            if args[:2] == ('cat-file', 'blob'):
                raise evidence.InputIdentityError('missing retained object')
            return actual(root, *args)
        with patch.object(evidence, 'git', side_effect=missing):
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
