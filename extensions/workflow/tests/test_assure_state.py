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
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ASSURE_STATE = Path(__file__).resolve().parents[2] / 'assure/scripts/assure_state.py'


class AssureStateBaseRefDefaultTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
