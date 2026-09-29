"""F16: assure_state.py defaults --base-ref to the feature's bound target
branch recorded by `workflow.py start` (workflow.py:previous_branch), so a
feature whose real target is not the origin HEAD default still compares
freshness against the branch it actually forked from. An explicit --base-ref
still wins, and a feature with no checkpoint (or no recorded target) falls
back to today's default (sanduq_freshness.base_ref's origin/HEAD lookup).

assure_state.py has no dedicated tests/ directory of its own (see
test_assure_init.py in this same directory for the established pattern), so
its CLI is exercised here, matching the workflow suite the regression matrix
in ci.yml already runs.
"""
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ASSURE_STATE = Path(__file__).resolve().parents[2] / 'assure/scripts/assure_state.py'

SPEC = importlib.util.spec_from_file_location('assure_state', ASSURE_STATE)
assure_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assure_state)


class AssureStateFixture:
    """Shared fixture (not a TestCase itself) so the --summary tests below do
    not re-run the base-ref tests through inheritance."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for args in [('init', '-q', '-b', 'develop'), ('config', 'user.name', 'Test'),
                     ('config', 'user.email', 'test@example.invalid')]:
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        (self.root / 'README.md').write_text('base\n', encoding='utf-8')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-qm', 'baseline'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'switch', '-qc', '42-example'], cwd=self.root, check=True, capture_output=True)
        self.feature = self.root / 'specs/001-example'
        self.feature.mkdir(parents=True)
        (self.feature / 'spec.md').write_text('# Example', encoding='utf-8')
        output = self.root / 'docs/001-example/QA.md'
        output.parent.mkdir(parents=True)
        output.write_text('Evidence', encoding='utf-8')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-qm', 'feature work'], cwd=self.root, check=True, capture_output=True)

    def checkpoint(self, target_branch):
        # A minimal fixture checkpoint: only the field F16 reads is required.
        path = self.feature / 'workflow/checkpoint.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'target_branch': target_branch}), encoding='utf-8')

    def run_state(self, action, base_ref=None):
        command = [sys.executable, str(ASSURE_STATE), action, '--feature', str(self.feature),
                   '--repo-root', str(self.root), '--kind', 'document',
                   '--output', 'docs/001-example/QA.md']
        if base_ref:
            command += ['--base-ref', base_ref]
        result = subprocess.run(command, cwd=self.root, text=True, capture_output=True, encoding='utf-8')
        return json.loads(result.stdout), result


class AssureStateBaseRefDefaultTests(AssureStateFixture, unittest.TestCase):
    def test_defaults_to_the_checkpoints_bound_target_branch(self):
        self.checkpoint('develop')
        result, proc = self.run_state('record')
        self.assertTrue(result['current'], proc.stderr)
        status, proc = self.run_state('status')
        self.assertTrue(status['current'], proc.stderr)

    def test_explicit_base_ref_still_wins_over_the_checkpoint(self):
        # The checkpoint names a branch that does not exist; an explicit
        # --base-ref must never even consult it.
        self.checkpoint('no-such-branch')
        result, proc = self.run_state('record', base_ref='develop')
        self.assertTrue(result['current'], proc.stderr)

    def test_a_checkpoint_without_a_recorded_target_branch_is_ignored(self):
        self.checkpoint(None)
        result, proc = self.run_state('status')
        self.assertFalse(result['current'])
        self.assertIn('base-ref', result['reason'])

    def test_falls_back_to_todays_default_without_a_checkpoint(self):
        result, proc = self.run_state('status')
        self.assertFalse(result['current'])
        self.assertIn('base-ref', result['reason'])


class AssureStateSummaryTests(AssureStateFixture, unittest.TestCase):
    """B7: --summary prints one ok/error line instead of the full JSON, on the
    same setUp fixture as the base-ref tests above."""

    def run_summary(self, action, base_ref=None):
        command = [sys.executable, str(ASSURE_STATE), action, '--feature', str(self.feature),
                   '--repo-root', str(self.root), '--kind', 'document',
                   '--output', 'docs/001-example/QA.md', '--summary']
        if base_ref:
            command += ['--base-ref', base_ref]
        return subprocess.run(command, cwd=self.root, text=True, capture_output=True, encoding='utf-8')

    def test_summary_success_line_on_record(self):
        self.checkpoint('develop')
        proc = self.run_summary('record')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), 'ok action=record kind=document outputs=1 recorded=1')

    def test_summary_error_line_when_stale(self):
        proc = self.run_summary('status')
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertTrue(proc.stdout.strip().startswith('error action=status kind=document outputs=1 reason='), proc.stdout)

    def test_summary_and_json_together_is_rejected(self):
        command = [sys.executable, str(ASSURE_STATE), 'status', '--feature', str(self.feature),
                   '--repo-root', str(self.root), '--kind', 'document', '--summary', '--json']
        proc = subprocess.run(command, cwd=self.root, text=True, capture_output=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn('--summary and --json cannot be combined', proc.stderr)

    def test_json_flag_matches_the_unflagged_default_byte_for_byte(self):
        # F8: --json is not a new format for this script; it is the same
        # `json.dumps(result)` the no-flag default already printed.
        self.checkpoint('develop')
        self.run_summary('record')  # record once so `status` below is deterministic either way
        default_proc = subprocess.run([sys.executable, str(ASSURE_STATE), 'status', '--feature', str(self.feature),
                                        '--repo-root', str(self.root), '--kind', 'document',
                                        '--output', 'docs/001-example/QA.md'],
                                       cwd=self.root, text=True, capture_output=True, encoding='utf-8')
        json_proc = subprocess.run([sys.executable, str(ASSURE_STATE), 'status', '--feature', str(self.feature),
                                     '--repo-root', str(self.root), '--kind', 'document',
                                     '--output', 'docs/001-example/QA.md', '--json'],
                                    cwd=self.root, text=True, capture_output=True, encoding='utf-8')
        self.assertEqual(default_proc.stdout, json_proc.stdout)
        self.assertEqual(default_proc.returncode, json_proc.returncode)


class AssureStateSummaryWhitespaceTests(unittest.TestCase):
    """F6: a reason with embedded newlines/whitespace still prints as one
    line under --summary. Exercised by importing the module directly and
    monkeypatching record_or_status, since a real multi-line freshness
    failure is not easy to reproduce deterministically through the CLI."""

    def test_reason_with_embedded_newlines_collapses_to_one_line(self):
        messy = {'current': False, 'reason': 'first line\nsecond   line\twith\ttabs\n'}
        argv = ['assure_state.py', 'status', '--feature', 'specs/001-example', '--kind', 'document',
                '--output', 'docs/001-example/QA.md', '--summary']
        buf = io.StringIO()
        with mock.patch.object(assure_state, 'record_or_status', return_value=messy), \
             mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(buf):
            code = assure_state.main()
        self.assertEqual(code, 1)
        line = buf.getvalue()
        self.assertEqual(len(line.splitlines()), 1, repr(line))
        self.assertEqual(line.strip(), 'error action=status kind=document outputs=1 reason=first line second line with tabs')


if __name__ == '__main__':
    unittest.main()
