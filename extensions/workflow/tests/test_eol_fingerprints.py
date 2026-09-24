"""Byte-sensitive fingerprints must not depend on how Git checked the file out.

A Windows clone with core.autocrlf=true writes an LF-committed .sql file as
CRLF. The committed content is identical to what a Linux CI checkout holds, so
local receipts and the CI gate must agree on its fingerprint. The fixtures build
that working-tree state explicitly (CRLF bytes that Git itself reports as
unchanged) so the same tests run on Linux and Windows.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/shared'))
import sanduq_freshness as f
import sanduq_hash as h
import workflow as w

ROOT = Path(__file__).resolve().parents[3]
LF = b'CREATE TABLE t (\n  id int\n);\n'
CRLF = LF.replace(b'\n', b'\r\n')
FINGERPRINTS = (('workflow', w.fingerprint_files), ('freshness', f.fingerprints))


def sha(content):
    return hashlib.sha256(content).hexdigest()


def git(root, *args, check=True):
    return subprocess.run(['git', *args], cwd=root, check=check, capture_output=True)


class EolFingerprintTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root = self.base / 'windows'
        self.root.mkdir()
        for args in [('init', '-q'), ('config', 'user.name', 'Test'), ('config', 'user.email', 'test@example.invalid'),
                     ('config', 'core.autocrlf', 'false')]:
            git(self.root, *args)
        (self.root / 'db').mkdir()
        (self.root / 'db/schema.sql').write_bytes(LF)
        (self.root / 'db/legacy.sql').write_bytes(CRLF)  # committed CRLF on purpose
        (self.root / 'notes.md').write_bytes(b'one\ntwo\n')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'baseline')
        self.names = ['db/schema.sql', 'db/legacy.sql', 'notes.md']
        # A clean LF checkout of the same commit, as Linux CI sees it.
        self.clean = self.base / 'ci'
        git(self.base, '-c', 'core.autocrlf=false', 'clone', '-q', str(self.root), str(self.clean))
        # Turn the author's tree into a Windows autocrlf checkout. autocrlf=true
        # converts LF to CRLF on checkout on every platform, so this is the real
        # state on Linux CI too: CRLF on disk and Git reports no change.
        self.autocrlf_checkout(self.root, self.names)

    @staticmethod
    def autocrlf_checkout(tree, names):
        git(tree, 'config', 'core.autocrlf', 'true')
        for name in names:
            (tree / name).unlink()
        git(tree, 'checkout', '--', *names)

    def test_fixture_is_the_windows_autocrlf_state(self):
        self.assertEqual(git(self.root, 'status', '--porcelain').stdout, b'')
        self.assertEqual((self.root / 'db/schema.sql').read_bytes(), CRLF)
        self.assertEqual((self.root / 'notes.md').read_bytes(), b'one\r\ntwo\r\n')
        eol = git(self.root, 'ls-files', '--eol', 'db/schema.sql').stdout.decode()
        self.assertIn('i/lf', eol); self.assertIn('w/crlf', eol)
        self.assertEqual((self.clean / 'db/schema.sql').read_bytes(), LF)

    def test_unchanged_sql_fingerprint_matches_a_clean_lf_checkout(self):
        for label, fingerprint in FINGERPRINTS:
            with self.subTest(label):
                local, ci = fingerprint(self.root, self.names), fingerprint(self.clean, self.names)
                self.assertEqual(local, ci)
                self.assertEqual(local['db/schema.sql'], sha(LF))

    def test_source_inventory_matches_a_clean_lf_checkout(self):
        self.assertEqual(w.source_fingerprints(self.root), w.source_fingerprints(self.clean))

    def test_genuinely_modified_sql_still_changes_the_fingerprint(self):
        edited = CRLF.replace(b'id int', b'id bigint')
        (self.root / 'db/schema.sql').write_bytes(edited)
        for label, fingerprint in FINGERPRINTS:
            with self.subTest(label):
                local = fingerprint(self.root, self.names)
                self.assertNotEqual(local['db/schema.sql'], fingerprint(self.clean, self.names)['db/schema.sql'])
                self.assertEqual(local['db/schema.sql'], sha(edited))  # working-tree bytes, never normalized

    def test_line_ending_only_edit_to_a_crlf_committed_sql_is_a_change(self):
        (self.root / 'db/legacy.sql').write_bytes(LF)
        for label, fingerprint in FINGERPRINTS:
            with self.subTest(label):
                self.assertEqual(fingerprint(self.root, ['db/legacy.sql'])['db/legacy.sql'], sha(LF))

    def test_crlf_committed_sql_keeps_its_crlf_hash(self):
        for label, fingerprint in FINGERPRINTS:
            with self.subTest(label):
                for tree in (self.root, self.clean):
                    self.assertEqual(fingerprint(tree, ['db/legacy.sql'])['db/legacy.sql'], sha(CRLF))

    def test_untracked_sql_hashes_its_working_tree_bytes(self):
        (self.root / 'db/new.sql').write_bytes(CRLF)
        for label, fingerprint in FINGERPRINTS:
            with self.subTest(label):
                self.assertEqual(fingerprint(self.root, ['db/new.sql'])['db/new.sql'], sha(CRLF))

    def test_non_sql_text_normalization_is_unchanged(self):
        for label, fingerprint in FINGERPRINTS:
            with self.subTest(label):
                self.assertEqual(fingerprint(self.root, ['notes.md'])['notes.md'], sha(b'one\ntwo\n'))

    def test_binary_attribute_file_follows_the_same_rule(self):
        (self.root / '.gitattributes').write_bytes(b'*.dat -text\n')
        (self.clean / '.gitattributes').write_bytes(b'*.dat -text\n')
        for tree in (self.root, self.clean):
            (tree / 'fixture.dat').write_bytes(b'a\nb\n')
            git(tree, 'add', '.gitattributes', 'fixture.dat')
        # -text means Git never converts, so any CRLF on disk is a real edit.
        (self.root / 'fixture.dat').write_bytes(b'a\r\nb\r\n')
        for label, fingerprint in FINGERPRINTS:
            with self.subTest(label):
                self.assertEqual(fingerprint(self.root, ['fixture.dat'])['fixture.dat'], sha(b'a\r\nb\r\n'))
                self.assertEqual(fingerprint(self.clean, ['fixture.dat'])['fixture.dat'], sha(b'a\nb\n'))

    def test_git_calls_are_batched_for_large_inventories(self):
        names = []
        for number in range(40):
            name = f'db/m{number:03}.sql'; names.append(name)
            (self.clean / name).write_bytes(LF)
        git(self.clean, 'add', 'db')
        self.autocrlf_checkout(self.clean, names)
        self.assertEqual((self.clean / names[-1]).read_bytes(), CRLF)
        real = subprocess.run
        with mock.patch.object(h.subprocess, 'run', side_effect=real) as spy:
            result = w.fingerprint_files(self.clean, names)
        self.assertTrue(all(value == sha(LF) for value in result.values()), result)
        self.assertLessEqual(spy.call_count, 6)

    def test_doctor_warns_about_byte_sensitive_eol_drift_with_a_remedy(self):
        report = w.doctor(self.root, w.default_policy(False, False))
        warnings = [item for item in report.get('warnings', []) if item.startswith('BYTE_SENSITIVE_EOL_DRIFT')]
        self.assertEqual(len(warnings), 1, report)
        self.assertIn('1 tracked', warnings[0])
        self.assertIn('core.autocrlf=false checkout', warnings[0])
        self.assertIn('-text', warnings[0])
        self.assertFalse(any('EOL' in error for error in report['errors']))
        clean = w.doctor(self.clean, w.default_policy(False, False))
        self.assertFalse(any(item.startswith('BYTE_SENSITIVE_EOL_DRIFT') for item in clean.get('warnings', [])))


class PackagedHashTests(unittest.TestCase):
    def test_documentation_packages_ship_the_canonical_hash_helper(self):
        spec = __import__('importlib.util').util.spec_from_file_location('eol_package', ROOT / 'extensions/scripts/package.py')
        packager = __import__('importlib.util').util.module_from_spec(spec); spec.loader.exec_module(packager)
        canonical = (ROOT / 'extensions/workflow/scripts/sanduq_hash.py').read_bytes()
        freshness = (ROOT / 'extensions/scripts/shared/sanduq_freshness.py').read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            for extension in ('assure', 'user-manual'):
                with self.subTest(extension):
                    archive = packager.package(extension, output=Path(folder) / (extension + '.zip'))['archive']
                    with zipfile.ZipFile(archive) as bundle:
                        self.assertEqual(bundle.read(extension + '/scripts/sanduq_hash.py'), canonical)
                        self.assertEqual(bundle.read(extension + '/scripts/sanduq_freshness.py'), freshness)
                        inventory = json.loads(bundle.read(extension + '/package-inventory.json'))
                        self.assertEqual(inventory[extension + '/scripts/sanduq_hash.py'], sha(canonical))
        # No extension carries its own hand-maintained copy that could drift.
        copies = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'extensions').rglob('sanduq_hash.py'))
        self.assertEqual(copies, ['extensions/workflow/scripts/sanduq_hash.py'])


if __name__ == '__main__':
    unittest.main()
