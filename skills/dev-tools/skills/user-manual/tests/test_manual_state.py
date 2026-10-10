"""Portable manual_state: record/status freshness, exit codes and --summary output."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MANUAL_STATE = Path(__file__).resolve().parents[1] / 'scripts/manual_state.py'


def git(root, *args):
    subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)


class ManualStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        git(self.root, 'init', '-q', '-b', 'main')
        git(self.root, 'config', 'user.name', 'Test')
        git(self.root, 'config', 'user.email', 'test@example.invalid')
        (self.root / 'README.md').write_text('base\n', encoding='utf-8')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'baseline')
        git(self.root, 'switch', '-qc', 'refunds')
        self.feature = self.root / 'work/refunds'
        self.feature.mkdir(parents=True)
        (self.feature / 'notes.md').write_text('# Refunds', encoding='utf-8')
        (self.root / 'User-Manual').mkdir()
        (self.root / 'User-Manual/guide.md').write_text('Guide', encoding='utf-8')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'feature work')

    def run_state(self, action, *extra):
        command = [sys.executable, str(MANUAL_STATE), action, '--feature', str(self.feature),
                   '--repo-root', str(self.root), '--output', 'User-Manual/guide.md', *extra]
        return subprocess.run(command, cwd=self.root, text=True, capture_output=True, encoding='utf-8')

    def test_record_then_status_is_current(self):
        record = self.run_state('record', '--base-ref', 'main')
        self.assertEqual(0, record.returncode, record.stdout + record.stderr)
        status = self.run_state('status')
        self.assertEqual(0, status.returncode, status.stdout + status.stderr)
        self.assertTrue(json.loads(status.stdout)['current'])

    def test_a_changed_input_or_output_makes_status_exit_1(self):
        self.run_state('record', '--base-ref', 'main')
        (self.root / 'src.py').write_text('print(1)\n', encoding='utf-8')
        self.assertEqual(1, self.run_state('status').returncode)
        (self.root / 'src.py').unlink()
        self.assertEqual(0, self.run_state('status').returncode)
        (self.root / 'User-Manual/guide.md').write_text('Edited', encoding='utf-8')
        status = self.run_state('status')
        self.assertEqual(1, status.returncode)
        self.assertEqual('stale-input-or-output', json.loads(status.stdout)['reason'])

    def test_missing_state_and_unknown_default_branch_fail_closed(self):
        status = self.run_state('status')
        self.assertEqual(1, status.returncode)
        self.assertIn('base-ref', json.loads(status.stdout)['reason'])

    def test_summary_prints_one_line(self):
        record = self.run_state('record', '--base-ref', 'main', '--summary')
        self.assertEqual('ok action=record kind=manual outputs=1 recorded=1', record.stdout.strip())
        rejected = self.run_state('status', '--summary', '--json')
        self.assertEqual(2, rejected.returncode)


if __name__ == '__main__':
    unittest.main()
