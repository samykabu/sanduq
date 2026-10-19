"""assure_state.py status --gate: off (missing file, missing key, false) prints "skipped gate=off" and
exits 0; on, in any indentation or quoting, runs the freshness status as today."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/assure_state.py'


class GateTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / 'specs/001-x').mkdir(parents=True)
        (self.root / 'specs/001-x/spec.md').write_text('# x\n', encoding='utf-8')
        self.config = self.root / '.specify/extensions/assure/assure-config.yml'
        self.config.parent.mkdir(parents=True)

    def status(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), 'status', '--kind', 'document', '--feature', 'specs/001-x',
                               '--repo-root', str(self.root), '--summary', *extra],
                              capture_output=True, text=True, cwd=self.root)

    def test_gate_off_skips(self):
        for text in (None, 'lifecycle:\n  mode: manual\n', 'lifecycle:\n  require_document_before_pr: false\n'):
            with self.subTest(text):
                if text is None:
                    self.config.unlink(missing_ok=True)
                else:
                    self.config.write_text(text, encoding='utf-8')
                result = self.status('--gate')
                self.assertEqual((result.returncode, result.stdout), (0, 'skipped gate=off\n'))

    def test_gate_on_runs_status_whatever_the_formatting(self):
        for text in ('lifecycle:\n  require_document_before_pr: true\n',
                     'lifecycle:\n    mode: integrated\n    require_document_before_pr: "true"  # gate\n',
                     "lifecycle:\n\trequire_document_before_pr: 'true'\n"):
            with self.subTest(text):
                self.config.write_text(text, encoding='utf-8')
                result = self.status('--gate')
                self.assertEqual(result.returncode, 1)
                self.assertTrue(result.stdout.startswith('error action=status kind=document'), result.stdout)

    def test_gate_is_status_only(self):
        result = subprocess.run([sys.executable, str(SCRIPT), 'record', '--gate', '--kind', 'document',
                                 '--feature', 'specs/001-x', '--repo-root', str(self.root)],
                                capture_output=True, text=True, cwd=self.root)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
