"""assure_state.py status --gate: off (missing file, missing key, false) prints "skipped gate=off" and
exits 0; on, in any indentation or quoting, runs the freshness status as today. A parsed value is
authoritative (a comment never turns it on); a config no reader can parse fails closed with one message."""
import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/assure_state.py'
SPEC = importlib.util.spec_from_file_location('assure_state', SCRIPT)
assure_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assure_state)


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

    def test_parsed_false_is_authoritative_whatever_the_comment_says(self):
        # D4: the old substring fallback turned this gate on.
        self.config.write_text('lifecycle:\n  require_document_before_pr: false  # set to true to require\n',
                               encoding='utf-8')
        result = self.status('--gate')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, 'skipped gate=off\n', ''))

    def test_text_fallback_without_pyyaml_ignores_comments(self):
        cases = {'lifecycle:\n  require_document_before_pr: false  # set to true\n': False,
                 '# require_document_before_pr: true\nlifecycle:\n  mode: manual\n': False,
                 'lifecycle:\n  require_document_before_pr: true  # gate\n': True}
        for text, expected in cases.items():
            with self.subTest(text), mock.patch.dict(sys.modules, {'yaml': None}):
                self.config.write_text(text, encoding='utf-8')
                self.assertIs(assure_state.gate_on(self.config), expected)

    def test_malformed_config_fails_closed_with_one_message(self):
        self.config.write_text('lifecycle: [require_document_before_pr: false\n', encoding='utf-8')
        result = self.status('--gate')
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith('error action=status kind=document'), result.stdout)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
        self.assertIn('cannot be parsed; treating the documentation gate as on', result.stderr)

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


class SummaryCountsTest(unittest.TestCase):
    """D7: a stale --summary line names the changed counts, as manual_state.py's does."""

    def test_stale_summary_carries_the_counts(self):
        stale = {'current': False, 'reason': 'stale-input-or-output', 'changed_inputs': ['a', 'b'],
                 'changed_outputs': ['c']}
        argv = ['assure_state.py', 'status', '--feature', 'specs/001-x', '--kind', 'document',
                '--output', 'docs/QA.md', '--summary']
        out = io.StringIO()
        with mock.patch.object(assure_state, 'record_or_status', return_value=stale), \
             mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(out):
            self.assertEqual(assure_state.main(), 1)
        self.assertEqual(out.getvalue(), 'error action=status kind=document outputs=1 '
                         'reason=stale-input-or-output changed_inputs=2 changed_outputs=1\n')


if __name__ == '__main__':
    unittest.main()
