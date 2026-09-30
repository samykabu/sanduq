"""B13: speckit-workflow-verify-affected runs a project's own hooks, never Sanduq-invented ones."""
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_affected as va
import workflow as w
import yaml

CLASSIFY_LANE_A = textwrap.dedent('''\
    import json, sys
    paths = json.loads(sys.stdin.read())
    print(json.dumps({"paths": {p: ["laneA"] for p in paths}}))
''')
CLASSIFY_NO_LANE = textwrap.dedent('''\
    import json, sys
    paths = json.loads(sys.stdin.read())
    print(json.dumps({"paths": {p: [] for p in paths}}))
''')
RUN_LANES_OK = textwrap.dedent('''\
    import json, sys
    payload = json.loads(sys.stdin.read())
    with open(payload["results_path"], "w", encoding="utf-8") as handle:
        json.dump({"lanes": {lane: {"outcome": "passed"} for lane in payload["lanes"]}}, handle)
''')
RUN_LANES_FAIL = 'import sys\nsys.exit(3)\n'


class VerifyAffectedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for args in [('init', '-q'), ('config', 'user.name', 'Test'), ('config', 'user.email', 't@example.invalid'),
                    ('commit', '--allow-empty', '-qm', 'init')]:
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        self.feature = 'specs/001-example'
        self.policy = w.default_policy(False, False)
        self._write_policy()

    def _write_policy(self):
        (self.root / '.specify').mkdir(exist_ok=True)
        (self.root / '.specify/workflow.yml').write_text(yaml.safe_dump(self.policy), encoding='utf-8')

    def _script(self, name, content):
        path = self.root / name
        path.write_text(content, encoding='utf-8')
        return [sys.executable, str(path)]

    def _base_ref(self):
        base = w.git(self.root, 'rev-parse', 'HEAD')
        subprocess.run(['git', 'branch', 'base', base], cwd=self.root, check=True, capture_output=True)
        return 'base'

    def _commit_change(self, name='changed.py'):
        (self.root / name).write_text('x = 1\n', encoding='utf-8')
        subprocess.run(['git', 'add', name], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-qm', 'change'], cwd=self.root, check=True, capture_output=True)

    def test_no_diff_reports_no_affected_lanes(self):
        base = self._base_ref()
        result = va.run(self.root, self.feature, base)
        self.assertEqual(result['status'], 'no_affected_lanes')
        self.assertEqual(result['lanes'], [])

    def test_lane_free_diff_never_calls_verify_command(self):
        base = self._base_ref()
        self._commit_change()
        self.policy['ci']['gate']['affected_command'] = self._script('classify.py', CLASSIFY_NO_LANE)
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_FAIL)
        self._write_policy()
        result = va.run(self.root, self.feature, base)
        self.assertEqual(result['status'], 'no_affected_lanes')

    def test_affected_lane_runs_and_reads_results(self):
        base = self._base_ref()
        self._commit_change()
        self.policy['ci']['gate']['affected_command'] = self._script('classify.py', CLASSIFY_LANE_A)
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_OK)
        self._write_policy()
        result = va.run(self.root, self.feature, base, results_path='out/results.json')
        self.assertEqual(result['status'], 'ran')
        self.assertEqual(result['lanes'], ['laneA'])
        self.assertEqual(result['results_summary'], {'lanes': 1, 'passed': 1, 'failed': 0})
        self.assertTrue((self.root / 'out/results.json').is_file())

    def test_extra_lane_always_runs_even_with_no_diff(self):
        base = self._base_ref()
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_OK)
        self._write_policy()
        result = va.run(self.root, self.feature, base, extra_lanes=['always'], results_path='out/results.json')
        self.assertEqual(result['lanes'], ['always'])

    def test_missing_verify_command_is_a_clear_error(self):
        base = self._base_ref()
        self._commit_change()
        self.policy['ci']['gate']['affected_command'] = self._script('classify.py', CLASSIFY_LANE_A)
        self._write_policy()
        with self.assertRaises(w.WorkflowError) as ctx:
            va.run(self.root, self.feature, base)
        self.assertIn('VERIFY_COMMAND_UNSET', str(ctx.exception))

    def test_diff_with_no_hook_and_no_lane_is_a_clear_error(self):
        base = self._base_ref()
        self._commit_change()
        with self.assertRaises(w.WorkflowError) as ctx:
            va.run(self.root, self.feature, base)
        self.assertIn('AFFECTED_COMMAND_UNSET', str(ctx.exception))

    def test_verify_command_failure_is_reported(self):
        base = self._base_ref()
        self._commit_change()
        self.policy['ci']['gate']['affected_command'] = self._script('classify.py', CLASSIFY_LANE_A)
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_FAIL)
        self._write_policy()
        with self.assertRaises(w.WorkflowError) as ctx:
            va.run(self.root, self.feature, base)
        self.assertIn('VERIFY_COMMAND_FAILED', str(ctx.exception))

    def test_cli_prints_json_and_exits_zero_on_success(self):
        base = self._base_ref()
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_OK)
        self._write_policy()
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'scripts/verify_affected.py'),
                                 '--root', str(self.root), '--feature', self.feature, '--base-ref', base,
                                 '--lane', 'always', '--results', 'out/results.json'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'ran')


if __name__ == '__main__':
    unittest.main()
