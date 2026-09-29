"""F16: manual_state.py defaults --base-ref to the feature's bound target
branch recorded by `workflow.py start` (workflow.py:previous_branch), the same
default assure_state.py gets (see test_assure_state.py in the workflow suite).
An explicit --base-ref still wins, and a feature with no checkpoint (or no
recorded target) falls back to today's default (sanduq_freshness.base_ref's
origin/HEAD lookup).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MANUAL_STATE = Path(__file__).resolve().parents[2] / 'user-manual/scripts/manual_state.py'


class ManualStateFixture:
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
        manual = self.root / 'User-Manual'
        manual.mkdir()
        (manual / 'guide.md').write_text('Guide', encoding='utf-8')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-qm', 'feature work'], cwd=self.root, check=True, capture_output=True)

    def checkpoint(self, target_branch):
        # A minimal fixture checkpoint: only the field F16 reads is required.
        path = self.feature / 'workflow/checkpoint.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'target_branch': target_branch}), encoding='utf-8')

    def run_state(self, action, base_ref=None):
        command = [sys.executable, str(MANUAL_STATE), action, '--feature', str(self.feature),
                   '--repo-root', str(self.root), '--output', 'User-Manual/guide.md']
        if base_ref:
            command += ['--base-ref', base_ref]
        result = subprocess.run(command, cwd=self.root, text=True, capture_output=True, encoding='utf-8')
        return json.loads(result.stdout), result


class ManualStateBaseRefDefaultTests(ManualStateFixture, unittest.TestCase):
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


class ManualStateSummaryTests(ManualStateFixture, unittest.TestCase):
    """B7: --summary prints one ok/error line instead of the full JSON."""

    def run_summary(self, action, base_ref=None):
        command = [sys.executable, str(MANUAL_STATE), action, '--feature', str(self.feature),
                   '--repo-root', str(self.root), '--output', 'User-Manual/guide.md', '--summary']
        if base_ref:
            command += ['--base-ref', base_ref]
        return subprocess.run(command, cwd=self.root, text=True, capture_output=True, encoding='utf-8')

    def test_summary_success_line_on_record(self):
        self.checkpoint('develop')
        proc = self.run_summary('record')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), 'ok action=record kind=manual outputs=1 recorded=1')

    def test_summary_error_line_when_stale(self):
        proc = self.run_summary('status')
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertTrue(proc.stdout.strip().startswith('error action=status kind=manual outputs=1 reason='), proc.stdout)

    def test_summary_and_json_together_is_rejected(self):
        command = [sys.executable, str(MANUAL_STATE), 'status', '--feature', str(self.feature),
                   '--repo-root', str(self.root), '--summary', '--json']
        proc = subprocess.run(command, cwd=self.root, text=True, capture_output=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn('--summary and --json cannot be combined', proc.stderr)


if __name__ == '__main__':
    unittest.main()
