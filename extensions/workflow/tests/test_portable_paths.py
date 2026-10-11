"""Legacy receipts may label files with Windows separators (`dir\\file`). Those labels must keep their identity
and hash the real file on every platform, while new receipts carry forward-slash identifiers and no label can
reach outside the project or merge two inputs silently."""
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'scripts'), str(Path(__file__).resolve().parents[2] / 'scripts/shared')]
import workflow as w

FEATURE = 'specs/001-demo'
TASKS = b'- [ ] T001 first\n- [x] T002 second <!-- sanduq-delegation {"route":"a"} -->\n'
LEGACY_SPEC = 'specs\\001-demo\\spec.md'
LEGACY_PLAN = 'specs\\001-demo\\plan.md'


def sha(content):
    return hashlib.sha256(content).hexdigest()


class PortablePathTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        (self.root / FEATURE).mkdir(parents=True)
        for name, content in {'spec.md': b'spec\n', 'plan.md': b'plan\n', 'tasks.md': TASKS}.items():
            (self.root / FEATURE / name).write_bytes(content)

    def test_legacy_label_keeps_identity_and_hashes_the_real_file(self):
        result = w.fingerprint_files(self.root, [LEGACY_SPEC, FEATURE + '/plan.md'])
        self.assertEqual(result, {LEGACY_SPEC: sha(b'spec' + chr(10).encode()), FEATURE + '/plan.md': sha(b'plan' + chr(10).encode())})
        saved = w.fingerprint_files(self.root, [LEGACY_SPEC])
        (self.root / FEATURE / 'spec.md').write_bytes(b'changed\n')
        self.assertNotEqual(w.fingerprint_files(self.root, [LEGACY_SPEC]), saved)
        self.assertEqual(w.fingerprint_files(self.root, [LEGACY_SPEC])[LEGACY_SPEC], sha(b'changed\n'))

    def test_missing_file_is_none_not_an_error(self):
        self.assertEqual(w.fingerprint_files(self.root, ['specs\\001-demo\\nope.md']), {'specs\\001-demo\\nope.md': None})

    def test_unsafe_labels_are_refused(self):
        for label in ('..\\outside.md', '../outside.md', 'specs/../../x', '/etc/passwd', 'C:\\Windows\\win.ini', 'c:/x',
                      '\\\\server\\share\\f', '', '.', 'a\0b'):
            with self.subTest(label=label):
                with self.assertRaises(w.WorkflowError):
                    w.fingerprint_files(self.root, [label])

    def test_two_labels_for_one_file_keep_separate_entries_with_one_hash(self):
        result = w.fingerprint_files(self.root, [LEGACY_SPEC, FEATURE + '/spec.md'])
        spec = sha(b'spec' + chr(10).encode())
        self.assertEqual(result, {LEGACY_SPEC: spec, FEATURE + '/spec.md': spec})

    def test_task_checkbox_and_routing_normalization_applies_under_an_alias(self):
        alias = 'specs\\001-demo\\tasks.md'
        before = w.fingerprint_files(self.root, [alias])[alias]
        (self.root / FEATURE / 'tasks.md').write_bytes(
            b'- [x] T001 first\n- [ ] T002 second <!-- sanduq-delegation {"route":"b"} -->\n')
        self.assertEqual(w.fingerprint_files(self.root, [alias])[alias], before)
        (self.root / FEATURE / 'tasks.md').write_bytes(b'- [ ] T001 changed\n- [x] T002 second\n')
        self.assertNotEqual(w.fingerprint_files(self.root, [alias])[alias], before)

    def test_new_receipts_are_canonicalized(self):
        receipt = {'inputs': [LEGACY_SPEC, FEATURE + '/spec.md', FEATURE + '/./plan.md'], 'evidence': ['specs\\001-demo\\plan.md'],
                   'input_roles': {LEGACY_SPEC: {'role': 'dependency'}, FEATURE + '/spec.md': {'role': 'dependency'}}}
        result = w.canonical_receipt(self.root, receipt)
        self.assertEqual(result['inputs'], [FEATURE + '/spec.md', FEATURE + '/plan.md'])
        self.assertEqual(result['evidence'], [FEATURE + '/plan.md'])
        self.assertEqual(list(result['input_roles']), [FEATURE + '/spec.md'])
        self.assertIn(LEGACY_SPEC, receipt['inputs'])  # the caller's receipt is not mutated

    def test_conflicting_roles_for_one_file_are_refused(self):
        receipt = {'inputs': [FEATURE + '/spec.md'], 'evidence': [FEATURE + '/plan.md'],
                   'input_roles': {LEGACY_SPEC: {'role': 'dependency'},
                                   FEATURE + '/spec.md': {'role': 'consulted', 'because': 'context'}}}
        with self.assertRaisesRegex(w.WorkflowError, 'INPUT_ROLE_COLLISION'):
            w.canonical_receipt(self.root, receipt)

    def test_canonical_receipt_refuses_escaping_paths(self):
        for field in ('inputs', 'evidence'):
            with self.subTest(field=field):
                with self.assertRaises(w.WorkflowError):
                    w.canonical_receipt(self.root, {'inputs': [FEATURE + '/spec.md'], 'evidence': [FEATURE + '/plan.md'],
                                                   field: ['..\\x']})

    def test_consulted_alias_of_a_required_input_stays_a_dependency(self):
        receipt = {'fingerprints': {LEGACY_PLAN: 'h', FEATURE + '/other.md': 'o'},
                   'input_roles': {LEGACY_PLAN: {'role': 'consulted', 'because': 'x'},
                                   FEATURE + '/other.md': {'role': 'consulted', 'because': 'x'}}}
        kept = w.dependency_fingerprints(receipt, [FEATURE + '/plan.md'])
        self.assertEqual(kept, {LEGACY_PLAN: 'h'})

    def test_legacy_receipt_drift_reports_only_real_changes(self):
        plan = FEATURE + '/plan.md'
        (self.root / FEATURE / 'scope-source.json').write_bytes(b'{}')
        receipt = {'fingerprints': {LEGACY_SPEC: sha(b'spec\n'), LEGACY_PLAN: sha(b'plan\n'),
                                    FEATURE + '/scope-source.json': sha(b'{}')}}
        self.assertEqual(w.receipt_drift(self.root, FEATURE, 'plan', receipt), [])
        (self.root / FEATURE / 'plan.md').write_bytes(b'new plan\n')
        self.assertEqual(w.receipt_drift(self.root, FEATURE, 'plan', receipt), [plan])


if __name__ == '__main__':
    unittest.main()
