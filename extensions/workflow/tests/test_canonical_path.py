"""W19: `canonical_path` checks containment with one `lstat` per component and resolves fully at any link."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import workflow as w  # noqa: E402


class CanonicalPathTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name).resolve()
        self.root, self.outside = base / 'repo', base / 'outside'
        (self.root / 'src/pkg').mkdir(parents=True)
        (self.root / 'src/pkg/app.py').write_text('x', encoding='utf-8')
        (self.outside / 'pkg').mkdir(parents=True)
        (self.outside / 'pkg/app.py').write_text('secret', encoding='utf-8')
        (self.outside / 'secret.txt').write_text('secret', encoding='utf-8')

    def symlink(self, link, target, directory=False):
        try:
            os.symlink(target, link, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest('symlinks unavailable here: ' + str(exc))

    def junction(self, link, target):
        if os.name != 'nt':
            self.skipTest('directory junctions are Windows-only')
        import _winapi
        _winapi.CreateJunction(str(target), str(link))

    def refused(self, label):
        with self.assertRaisesRegex(w.WorkflowError, 'PATH_OUTSIDE_PROJECT'):
            w.canonical_path(self.root, label)

    def test_plain_and_missing_labels_are_accepted_as_forward_slash_labels(self):
        self.assertEqual(w.canonical_path(self.root, 'src\\pkg\\app.py'), 'src/pkg/app.py')
        self.assertEqual(w.canonical_path(self.root, './src//pkg/new/deeper.py'), 'src/pkg/new/deeper.py')
        self.assertEqual(w.canonical_path(self.root, 'src/pkg/app.py/below'), 'src/pkg/app.py/below')

    def test_dot_dot_absolute_drive_and_unc_labels_are_still_refused(self):
        for label in ('../outside/secret.txt', 'src/../../outside', '/etc/passwd', 'C:/Windows', 'c:x',
                      '//server/share/x', '\\\\server\\share\\x'):
            self.refused(label)

    def test_a_symlinked_leaf_outside_the_root_is_refused(self):
        self.symlink(self.root / 'src/pkg/leak.txt', self.outside / 'secret.txt')
        self.refused('src/pkg/leak.txt')

    def test_a_symlinked_directory_outside_the_root_is_refused(self):
        self.symlink(self.root / 'src/linked', self.outside / 'pkg', directory=True)
        self.refused('src/linked/app.py')
        self.refused('src/linked')

    def test_a_link_inside_the_root_is_still_accepted(self):
        self.symlink(self.root / 'src/alias', self.root / 'src/pkg', directory=True)
        self.assertEqual(w.canonical_path(self.root, 'src/alias/app.py'), 'src/alias/app.py')

    def test_a_junction_outside_the_root_is_refused(self):
        self.junction(self.root / 'src/joined', self.outside / 'pkg')
        self.refused('src/joined/app.py')
        self.refused('src/joined')

    @unittest.skipUnless(os.name == 'nt', 'case-insensitive paths are a Windows property here')
    def test_a_case_differing_label_on_windows_is_judged_like_the_full_resolve(self):
        self.assertEqual(w.canonical_path(self.root, 'SRC/Pkg/APP.py'), 'SRC/Pkg/APP.py')
        self.junction(self.root / 'src/joined', self.outside / 'pkg')
        self.refused('SRC/JOINED/app.py')

    def test_names_windows_rewrites_fall_back_to_the_full_resolve(self):
        for label in ('src/pkg/app.py:stream', 'src/pkg./app.py', 'src/pkg /app.py'):
            try:
                expected = w.inside(self.root, label.replace('\\', '/')) and label
            except w.WorkflowError:
                expected = None
            try:
                actual = w.canonical_path(self.root, label)
            except w.WorkflowError:
                actual = None
            self.assertEqual(actual, expected, label)

    def test_an_ancestor_replaced_by_a_link_between_two_calls_in_one_operation_is_refused(self):
        for make in (lambda link, target: self.symlink(link, target, directory=True), self.junction):
            with self.subTest(make=make):
                with w.operation():
                    self.assertEqual(w.canonical_path(self.root, 'src/pkg/app.py'), 'src/pkg/app.py')
                    moved = self.outside / 'moved-src'
                    shutil.move(str(self.root / 'src'), str(moved))
                    try:
                        make(self.root / 'src', moved)
                    except unittest.SkipTest:
                        shutil.move(str(moved), str(self.root / 'src'))
                        raise
                    try:
                        self.refused('src/pkg/app.py')
                    finally:
                        os.rmdir(self.root / 'src') if os.name == 'nt' else os.unlink(self.root / 'src')
                        shutil.move(str(moved), str(self.root / 'src'))

    def test_the_fast_check_agrees_with_the_full_resolve(self):
        self.symlink(self.root / 'src/linked', self.outside / 'pkg', directory=True)
        for label in ('src/pkg/app.py', 'src/pkg', 'src/linked/app.py', 'missing/a/b', 'src/pkg/app.py/x'):
            try:
                w.inside(self.root, label)
                expected = True
            except w.WorkflowError:
                expected = False
            try:
                w.canonical_path(self.root, label)
                actual = True
            except w.WorkflowError:
                actual = False
            self.assertEqual(actual, expected, label)


if __name__ == '__main__':
    unittest.main()
