"""B13: speckit-workflow-verify-affected runs a project's own hooks, never Sanduq-invented ones."""
import json
import os
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
RUN_LANES_REPORTS_PGID = textwrap.dedent('''\
    import json, os, sys
    payload = json.loads(sys.stdin.read())
    with open(payload["results_path"], "w", encoding="utf-8") as handle:
        json.dump({"lanes": {}, "child_pgid": os.getpgid(0) if hasattr(os, "getpgid") else None}, handle)
''')
RUN_LANES_LIST_RESULT = textwrap.dedent('''\
    import json, sys
    payload = json.loads(sys.stdin.read())
    with open(payload["results_path"], "w", encoding="utf-8") as handle:
        json.dump([1, 2, 3], handle)
''')
RUN_LANES_NOISY = textwrap.dedent('''\
    import json, sys
    payload = json.loads(sys.stdin.read())
    sys.stderr.write("E" * 5_000_000)
    sys.exit(2)
''')
RUN_LANES_EMPTY = textwrap.dedent('''    import json, sys
    payload = json.loads(sys.stdin.read())
    with open(payload["results_path"], "w", encoding="utf-8") as handle:
        json.dump({"lanes": {}}, handle)
''')
RUN_LANES_ONE_FAILED = textwrap.dedent('''    import json, sys
    payload = json.loads(sys.stdin.read())
    with open(payload["results_path"], "w", encoding="utf-8") as handle:
        json.dump({"lanes": {lane: {"outcome": "failed" if lane == "laneB" else "passed"}
                             for lane in payload["lanes"]}}, handle)
''')
RUN_LANES_FLOOD = textwrap.dedent('''    import sys
    sys.stdin.read()
    chunk = "F" * 100_000
    while True:
        sys.stdout.write(chunk)
        sys.stdout.flush()
''')
RUN_LANES_HANGS = textwrap.dedent('''\
    import sys, time
    sys.stdin.read()
    time.sleep(60)
''')


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
        # Commit the baseline policy so a "no diff" test starts from a clean
        # tree: an untracked .specify/workflow.yml would otherwise itself
        # count as a diffed path once diffed_paths() includes the working
        # tree and untracked files (finding 6).
        subprocess.run(['git', 'add', '.specify/workflow.yml'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-qm', 'policy'], cwd=self.root, check=True, capture_output=True)

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

    def test_uncommitted_edit_is_diffed_without_a_commit(self):
        # Review round 1, finding 6: base_ref..HEAD alone gives a false
        # green for a real, uncommitted change.
        base = self._base_ref()
        (self.root / 'uncommitted.py').write_text('y = 2\n', encoding='utf-8')  # untracked, never committed
        self.policy['ci']['gate']['affected_command'] = self._script('classify.py', CLASSIFY_LANE_A)
        self._write_policy()
        paths = va.diffed_paths(self.root, base)
        self.assertIn('uncommitted.py', paths)
        lanes = va.affected_lane_set(self.root, self.policy, paths)
        self.assertEqual(lanes, {'laneA'})

    def test_staged_edit_is_also_diffed(self):
        base = self._base_ref()
        (self.root / 'staged.py').write_text('z = 3\n', encoding='utf-8')
        subprocess.run(['git', 'add', 'staged.py'], cwd=self.root, check=True, capture_output=True)
        paths = va.diffed_paths(self.root, base)
        self.assertIn('staged.py', paths)

    def test_results_are_stamped_local_and_not_ci_grade(self):
        base = self._base_ref()
        self._commit_change()
        self.policy['ci']['gate']['affected_command'] = self._script('classify.py', CLASSIFY_LANE_A)
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_OK)
        self._write_policy()
        result = va.run(self.root, self.feature, base, results_path='out/results.json')
        self.assertEqual(result['source'], 'local')
        self.assertIs(result['ci_grade'], False)
        on_disk = json.loads((self.root / 'out/results.json').read_text(encoding='utf-8'))
        self.assertEqual(on_disk['source'], 'local')
        self.assertIs(on_disk['ci_grade'], False)

    def test_results_path_outside_repo_is_rejected(self):
        base = self._base_ref()
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_OK)
        self._write_policy()
        with self.assertRaises(w.WorkflowError) as ctx:
            va.run(self.root, self.feature, base, extra_lanes=['always'], results_path='../outside-results.json')
        self.assertIn('PATH_OUTSIDE_PROJECT', str(ctx.exception))

    def test_verify_command_timeout_kills_the_process(self):
        base = self._base_ref()
        self._commit_change()
        self.policy['ci']['gate']['affected_command'] = self._script('classify.py', CLASSIFY_LANE_A)
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_HANGS)
        self._write_policy()
        with self.assertRaises(w.WorkflowError) as ctx:
            va.run(self.root, self.feature, base, results_path='out/results.json', timeout=1)
        self.assertIn('VERIFY_COMMAND_TIMEOUT', str(ctx.exception))

    @unittest.skipIf(os.name == 'nt', 'process groups are a POSIX concept')
    def test_verify_command_runs_in_its_own_process_group(self):
        # Round 2, blocker 1: without start_new_session the child shares the
        # caller's group, so kill_process_tree's killpg on a timeout would
        # SIGKILL the caller (the test runner itself) too.
        base = self._base_ref()
        self._commit_change()
        self.policy['ci']['gate']['affected_command'] = self._script('classify.py', CLASSIFY_LANE_A)
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_REPORTS_PGID)
        self._write_policy()
        va.run(self.root, self.feature, base, results_path='out/results.json')
        child_pgid = json.loads((self.root / 'out/results.json').read_text(encoding='utf-8'))['child_pgid']
        self.assertNotEqual(child_pgid, os.getpgid(0))

    def test_non_object_results_are_wrapped_and_stamped(self):
        base = self._base_ref()
        self._commit_change()
        self.policy['ci']['gate']['affected_command'] = self._script('classify.py', CLASSIFY_LANE_A)
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_LIST_RESULT)
        self._write_policy()
        result = va.run(self.root, self.feature, base, results_path='out/results.json')
        self.assertEqual(result['source'], 'local')
        on_disk = json.loads((self.root / 'out/results.json').read_text(encoding='utf-8'))
        self.assertEqual(on_disk, {'results': [1, 2, 3], 'source': 'local', 'ci_grade': False})

    def test_runaway_output_is_capped_in_the_error(self):
        base = self._base_ref()
        self._commit_change()
        self.policy['ci']['gate']['affected_command'] = self._script('classify.py', CLASSIFY_LANE_A)
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_NOISY)
        self._write_policy()
        with self.assertRaises(w.WorkflowError) as ctx:
            va.run(self.root, self.feature, base)
        self.assertIn('VERIFY_COMMAND_FAILED', str(ctx.exception))
        self.assertLess(len(str(ctx.exception)), 1000)

    def _ran(self, script, extra_lanes=None):
        base = self._base_ref()
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', script)
        self._write_policy()
        return va.run(self.root, self.feature, base, extra_lanes=extra_lanes or ['laneA'],
                      results_path='out/results.json')

    def test_empty_results_with_a_requested_lane_is_not_ok(self):
        # Round 3, finding 4: exit 0 plus any JSON is not a pass.
        result = self._ran(RUN_LANES_EMPTY)
        self.assertFalse(result['ok'])
        self.assertEqual(result['missing_lanes'], ['laneA'])
        self.assertEqual(result['status'], 'failed')

    def test_a_failed_lane_is_not_ok_and_is_listed(self):
        result = self._ran(RUN_LANES_ONE_FAILED, extra_lanes=['laneA', 'laneB'])
        self.assertFalse(result['ok'])
        self.assertEqual(result['failed_lanes'], ['laneB'])
        self.assertEqual(result['missing_lanes'], [])

    def test_non_object_results_are_not_ok(self):
        result = self._ran(RUN_LANES_LIST_RESULT)
        self.assertFalse(result['ok'])
        self.assertFalse(result['results_schema_valid'])

    def test_all_requested_lanes_passing_is_ok(self):
        result = self._ran(RUN_LANES_OK)
        self.assertTrue(result['ok'])

    def test_cli_exits_non_zero_when_a_lane_failed(self):
        base = self._base_ref()
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_ONE_FAILED)
        self._write_policy()
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'scripts/verify_affected.py'),
                               '--root', str(self.root), '--feature', self.feature, '--base-ref', base,
                               '--lane', 'laneB', '--results', 'out/results.json'], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(json.loads(proc.stdout)['ok'])

    def test_sustained_output_is_stopped_while_the_command_runs(self):
        # Round 3, finding 5: the cap is enforced during the run, not only
        # when the output is read back, so a runaway spool cannot fill a disk.
        import time
        from unittest.mock import patch
        base = self._base_ref()
        self.policy['ci']['gate']['verify_command'] = self._script('run_lanes.py', RUN_LANES_FLOOD)
        self._write_policy()
        started = time.monotonic()
        with patch.object(va, 'HARD_OUTPUT_LIMIT', 300_000), patch.object(va, 'POLL_SECONDS', 0.05):
            with self.assertRaises(w.WorkflowError) as ctx:
                va.run(self.root, self.feature, base, extra_lanes=['laneA'], results_path='out/results.json')
        self.assertIn('VERIFY_COMMAND_OUTPUT_LIMIT', str(ctx.exception))
        self.assertLess(time.monotonic() - started, 30)

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
