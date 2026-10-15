"""Reporting modes and the legacy progress.py shim over the optional Progress extension (CLI only)."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
PROGRESS_SCRIPT = Path(__file__).resolve().parents[2] / 'progress' / 'scripts' / 'progress.py'
TASKS = Path(__file__).resolve().parents[2] / 'progress' / 'tests' / 'fixtures' / 'tasks.md'
sys.path.insert(0, str(SCRIPTS))
import progress_bridge as bridge  # noqa: E402

SPEC = importlib.util.spec_from_file_location('legacy_progress', SCRIPTS / 'progress.py')
legacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)

FEATURE = 'specs/001-demo'


class Project(unittest.TestCase):
    installed = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / '.specify').mkdir()
        self.feature_dir = self.root / FEATURE
        self.feature_dir.mkdir(parents=True)
        shutil.copyfile(TASKS, self.feature_dir / 'tasks.md')
        self.output = self.feature_dir / 'workflow' / 'progress'
        saved = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(saved)))
        os.environ.pop('SANDUQ_PROGRESS_SCRIPT', None)
        if self.installed:
            os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(PROGRESS_SCRIPT)
        self.cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.cwd)

    def shim(self, *argv):
        """Run the legacy script in-process; return (exit code, stdout, stderr)."""
        out, err, code = io.StringIO(), io.StringIO(), 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                legacy.main(list(argv))
            except SystemExit as exit_:
                code = exit_.code if isinstance(exit_.code, int) else 1
        return code, out.getvalue().strip(), err.getvalue().strip()

    def legacy(self, command, *args):
        return self.shim(command, '--output', str(self.output), *args)

    def progress(self, *args):
        done = subprocess.run([sys.executable, str(PROGRESS_SCRIPT), '--root', str(self.root), *args], capture_output=True,
                              text=True, encoding='utf-8')
        return done.returncode, done.stdout.strip()

    def facts(self, kind=None):
        path = self.feature_dir / 'progress' / 'facts.jsonl'
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.is_file() else []
        return [r for r in rows if kind in (None, r['kind'])]

    def status(self):
        code, text = self.progress('status', '--json', '--feature', FEATURE)
        self.assertEqual(code, 0, text)
        return json.loads(text)

    def init(self):
        code, out, err = self.legacy('init', '--tasks', str(self.feature_dir / 'tasks.md'), '--summary')
        self.assertEqual(code, 0, out + err)
        return out


class ReportingModes(Project):
    def mode(self):
        return bridge.mode(self.root, FEATURE)

    def test_absent_progress_means_legacy(self):
        os.environ.pop('SANDUQ_PROGRESS_SCRIPT')
        self.assertEqual(self.mode()['mode'], 'legacy')
        self.assertIsNone(self.mode()['script'])

    def test_installed_path_is_detected_without_the_override(self):
        os.environ.pop('SANDUQ_PROGRESS_SCRIPT')
        target = self.root / bridge.RELATIVE
        target.parent.mkdir(parents=True)
        shutil.copyfile(PROGRESS_SCRIPT, target)
        self.assertEqual(Path(self.mode()['script']), target)

    def test_installed_without_automatic_collection_means_refresh(self):
        decision = self.mode()
        self.assertEqual((decision['mode'], decision['automatic']), ('refresh', False))

    def test_registered_hooks_mean_projection(self):
        (self.root / '.claude').mkdir()
        (self.root / '.claude' / 'settings.json').write_text(json.dumps({'hooks': {'Stop': [{'hooks': [{
            'type': 'command', 'command': 'python .specify/events.py speckit.progress.hook-stop stop'}]}]}}), encoding='utf-8')
        decision = self.mode()
        self.assertEqual((decision['mode'], decision['automatic'], decision['source']), ('projection', True, 'hooks registered'))

    def test_historical_snapshot_alone_is_not_automatic_collection(self):
        self.init()
        host = self.feature_dir / 'progress' / '.view' / 'host'
        host.mkdir(parents=True, exist_ok=True)
        (host / 'claude-s1.json').write_text(json.dumps({'v': 1, 'host': 'claude', 'session_id': 's1', 'bound_feature': FEATURE,
                                                         'first_seen': '2026-10-15T12:00:00Z',
                                                         'last_observed_at': '2026-10-15T12:00:00Z'}), encoding='utf-8')
        self.assertEqual(self.mode()['mode'], 'refresh')

    def _claude(self, entry):
        (self.root / '.claude').mkdir(exist_ok=True)
        (self.root / '.claude' / 'settings.json').write_text(json.dumps({'hooks': {'Stop': [{'hooks': [entry]}]}}), encoding='utf-8')

    def _yml(self, enabled):
        (self.root / '.specify').mkdir(exist_ok=True)
        (self.root / '.specify' / 'extensions.yml').write_text(
            'hooks:\n  after_implement:\n  - extension: progress\n    command: speckit.progress.hook-stop\n'
            f'    enabled: {enabled}\n    optional: false\n', encoding='utf-8')

    def test_disabled_native_hook_entry_is_not_automatic(self):
        self._claude({'type': 'command', 'enabled': False, 'command': 'python .specify/events.py speckit.progress.hook-stop stop'})
        self.assertEqual(self.mode()['mode'], 'refresh')

    HOOK = 'python .specify/events.py speckit.progress.hook-stop stop'

    def _claude_file(self, name, data):
        (self.root / '.claude').mkdir(exist_ok=True)
        (self.root / '.claude' / name).write_text(json.dumps(data), encoding='utf-8')

    def test_claude_disable_all_hooks_is_not_automatic(self):
        self._claude_file('settings.json', {'disableAllHooks': True, 'hooks': {'Stop': [{'hooks': [
            {'type': 'command', 'command': self.HOOK}]}]}})
        self.assertEqual(self.mode()['mode'], 'refresh')

    def test_local_settings_can_reenable_hooks_the_shared_file_disabled(self):
        self._claude_file('settings.json', {'disableAllHooks': True, 'hooks': {'Stop': [{'hooks': [
            {'type': 'command', 'command': self.HOOK}]}]}})
        self._claude_file('settings.local.json', {'disableAllHooks': False})
        self.assertEqual(self.mode()['mode'], 'projection')

    def test_command_beneath_a_disabled_parent_is_not_automatic(self):
        self._claude_file('settings.json', {'hooks': {'Stop': [{'enabled': False, 'hooks': [
            {'type': 'command', 'command': self.HOOK}]}]}})
        self.assertEqual(self.mode()['mode'], 'refresh')
        self._claude_file('settings.json', {'hooks': {'disabled': True, 'Stop': [{'hooks': [
            {'type': 'command', 'command': self.HOOK}]}]}})
        self.assertEqual(self.mode()['mode'], 'refresh')

    def test_codex_hooks_feature_switched_off_is_not_automatic(self):
        (self.root / '.codex').mkdir()
        (self.root / '.codex' / 'hooks.json').write_text(json.dumps({'features': {'codex_hooks': False}, 'hooks': {
            'Stop': [{'command': self.HOOK}]}}), encoding='utf-8')
        self.assertEqual(self.mode()['mode'], 'refresh')

    def test_codex_config_toml_switch_disables_hooks_json(self):
        (self.root / '.codex').mkdir()
        (self.root / '.codex' / 'hooks.json').write_text(json.dumps({'hooks': {
            'Stop': [{'command': self.HOOK}]}}), encoding='utf-8')
        (self.root / '.codex' / 'config.toml').write_text('[features]\nhooks = false\n', encoding='utf-8')
        self.assertEqual(self.mode()['mode'], 'refresh')
        (self.root / '.codex' / 'config.toml').write_text('[features]\ncodex_hooks = false\n', encoding='utf-8')
        self.assertEqual(self.mode()['mode'], 'refresh')

    def test_disabled_extensions_yml_hook_is_not_automatic(self):
        self._yml('false')
        self.assertEqual(self.mode()['mode'], 'refresh')

    def test_enabled_extensions_yml_hook_is_automatic(self):
        self._yml('true')
        self.assertEqual(self.mode()['mode'], 'projection')

    def test_other_extension_hook_in_extensions_yml_is_ignored(self):
        (self.root / '.specify').mkdir(exist_ok=True)
        (self.root / '.specify' / 'extensions.yml').write_text(
            'hooks:\n  after_implement:\n  - extension: scope\n    command: speckit.scope.plan-guard\n    enabled: true\n',
            encoding='utf-8')
        self.assertEqual(self.mode()['mode'], 'refresh')

    def test_disabled_extension_in_registry_is_not_automatic(self):
        self._claude({'type': 'command', 'command': 'python .specify/events.py speckit.progress.hook-stop stop'})
        reg = self.root / '.specify' / 'extensions' / '.registry'
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text(json.dumps({'schema_version': '1.0', 'extensions': {'progress': {'enabled': False}}}), encoding='utf-8')
        self.assertEqual(self.mode()['mode'], 'refresh')

    def test_codex_toml_hook_is_detected_and_disabled_one_is_not(self):
        (self.root / '.codex').mkdir(exist_ok=True)
        cfg = self.root / '.codex' / 'config.toml'
        cfg.write_text('[[hooks.Stop]]\ncommand = "python x.py speckit.progress.hook-stop"\n', encoding='utf-8')
        self.assertEqual(self.mode()['mode'], 'projection')
        cfg.write_text('[[hooks.Stop]]\nenabled = false\ncommand = "python x.py speckit.progress.hook-stop"\n', encoding='utf-8')
        self.assertEqual(self.mode()['mode'], 'refresh')

    def test_mode_command_prints_one_line(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / 'progress_bridge.py'), 'mode', '--root', str(self.root)],
                              capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual((done.returncode, done.stdout.strip()), (0, 'reporting: refresh'))


class AbsentProgress(Project):
    installed = False

    def test_legacy_reporter_runs_unchanged(self):
        code, out, err = self.legacy('init', '--tasks', str(self.feature_dir / 'tasks.md'), '--summary')
        # The legacy parser also counts the fenced decoy task, so its totals differ from the projection's.
        self.assertEqual((code, out), (0, 'ok done=2 total=6 pending=4 running=0 blocked=0'), err)
        self.assertTrue((self.output / 'state.json').is_file())
        self.assertFalse((self.feature_dir / 'progress').exists())
        code, out, _ = self.legacy('task', '--id', 'T002', '--status', 'running', '--agent', 'w1', '--summary')
        self.assertEqual((code, out), (0, 'ok done=2 total=6 pending=3 running=1 blocked=0'))
        state = json.loads((self.output / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual(next(t for t in state['tasks'] if t['id'] == 'T002')['agent'], 'w1')


class ShimMappings(Project):
    def test_init_forwards_and_keeps_the_summary_line(self):
        self.assertEqual(self.init(), 'ok done=2 total=5 pending=3 running=0 blocked=0')
        self.assertTrue((self.feature_dir / 'progress' / '.view' / 'index.html').is_file())
        self.assertFalse((self.output / 'state.json').exists())  # no legacy state is written
        code, out, _ = self.legacy('init', '--tasks', str(self.feature_dir / 'tasks.md'))
        self.assertEqual(code, 0)
        self.assertTrue(out.replace('\\', '/').endswith('specs/001-demo/progress/.view/index.html'), out)

    def test_task_lifecycle_maps_to_lane_and_attempt_facts(self):
        self.init()
        code, out, err = self.legacy('task', '--id', 'T002', '--status', 'running', '--agent', 'worker-1',
                                     '--note', 'Own parser.py', '--summary')
        self.assertEqual((code, out), (0, 'ok done=2 total=5 pending=2 running=1 blocked=0'), err)
        lane = self.facts('lane')[-1]
        self.assertEqual((lane['owner'], lane['tasks']), ('worker-1', ['T002']))
        attempt = self.facts('attempt')[-1]
        self.assertEqual((attempt['run'], attempt['status'], attempt['origin'], attempt['lane']),
                         ('legacy-T002-worker-1', 'running', 'legacy', lane['id']))
        self.assertTrue(attempt['started_at'] and attempt['ended_at'] is None)
        self.assertEqual(self.facts('note')[-1]['text'], 'T002 running: Own parser.py')
        # same agent takes a second task: still one lane
        self.legacy('task', '--id', 'T003', '--status', 'running', '--agent', 'worker-1', '--summary')
        self.assertEqual(self.facts('lane')[-1]['tasks'], ['T002', 'T003'])
        code, out, _ = self.legacy('task', '--id', 'T002', '--status', 'done', '--agent', 'worker-1', '--summary')
        self.assertEqual(code, 0, out)
        done = [a for a in self.facts('attempt') if a['run'] == 'legacy-T002-worker-1'][-1]
        self.assertEqual((done['status'], bool(done['ended_at']), done['started_at']), ('done', True, attempt['started_at']))
        report = self.status()
        mine = next(l for l in report['lanes'] if l['owner'] == 'worker-1')
        self.assertEqual(mine['attempts'][0]['origin'], 'legacy')

    def test_running_without_agent_never_forwards_an_invalid_lane(self):
        self.init()
        before = self.facts()
        code, out, err = self.legacy('task', '--id', 'T002', '--status', 'running', '--summary')
        if code == 0:  # mapped onto something Progress accepts
            attempts = self.facts('attempt')
            self.assertTrue(attempts, 'running must still record an attempt')
            self.assertRegex(attempts[-1]['lane'] or 'L0', r'^L\d+$')
        else:  # explicit compatibility error, before any mutation
            self.assertIn('compatibility:', out + err)
            self.assertEqual(self.facts(), before)

    def test_agentless_running_tasks_share_one_coordinator_lane(self):
        self.init()
        for task in ('T002', 'T003'):
            code, out, _ = self.legacy('task', '--id', task, '--status', 'running', '--summary')
            self.assertEqual(code, 0, out)
        lanes = {l['id'] for l in self.facts('lane')}
        self.assertEqual(len(lanes), 1, lanes)
        self.assertEqual(self.facts('lane')[-1]['tasks'], ['T002', 'T003'])

    def test_blocked_uses_note_as_external_blocker_unless_a_reference_is_given(self):
        self.init()
        self.legacy('task', '--id', 'T002', '--status', 'blocked', '--agent', 'w1', '--note', 'waiting for API key')
        block = self.facts('block')[-1]
        self.assertEqual((block['target'], block['by'], block['state']), ('T002', {'type': 'external', 'ref': 'waiting for API key'}, 'open'))
        self.legacy('task', '--id', 'T003', '--status', 'blocked', '--agent', 'w2', '--note', 'T002')
        self.assertEqual(self.facts('block')[-1]['by'], {'type': 'task', 'ref': 'T002'})
        self.legacy('task', '--id', 'T004', '--status', 'blocked')
        self.assertEqual(self.facts('block')[-1]['by']['ref'], 'blocked (legacy)')
        code, out, _ = self.legacy('task', '--id', 'T002', '--status', 'pending', '--summary')
        self.assertEqual(code, 0, out)
        self.assertEqual([b['state'] for b in self.facts('block') if b['target'] == 'T002'][-1], 'resolved')
        # a task with no open blocker accepts pending without error
        self.assertEqual(self.legacy('task', '--id', 'T001', '--status', 'pending', '--summary')[0], 0)

    def test_event_phase_and_pr_become_notes(self):
        self.init()
        self.legacy('event', '--message', 'Phase 1 tests passed')
        self.legacy('phase', '--name', 'Phase 1', '--status', 'complete', '--commit', 'abc123')
        self.legacy('pr', '--url', 'https://github.com/a/b/pull/1', '--status', 'merged')
        self.assertEqual([n['text'] for n in self.facts('note')],
                         ['Phase 1 tests passed', 'Phase Phase 1: complete (abc123)', 'PR merged: https://github.com/a/b/pull/1'])

    def test_sync_refreshes_the_projection(self):
        self.init()
        before = self.status()['rev']
        code, out, err = self.legacy('sync', '--summary')
        self.assertEqual((code, out), (0, 'ok done=2 total=5 pending=3 running=0 blocked=0'), err)
        self.assertGreater(self.status()['rev'], before)

    def test_usage_reported_counts_keep_provenance(self):
        self.init()
        self.legacy('task', '--id', 'T002', '--status', 'running', '--agent', 'w1')
        code, out, err = self.legacy('usage', '--id', 'T002', '--agent', 'w1', '--fresh-input', '100', '--cached-input', '40',
                                     '--output-tokens', '7', '--harness', 'codex', '--model', 'gpt-x', '--summary')
        self.assertEqual(code, 0, out + err)
        attempt = [a for a in self.facts('attempt') if a['run'] == 'legacy-T002-w1'][-1]
        self.assertEqual(attempt['status'], 'running')  # usage never changes the attempt's status or window
        self.assertTrue(attempt['started_at'])
        usage = attempt['usage']
        self.assertEqual((usage['fidelity'], usage['fresh_input'], usage['cache_read'], usage['output'], usage['harness'], usage['model']),
                         ('reported', 100, 40, 7, 'codex', 'gpt-x'))
        shown = next(l for l in self.status()['lanes'] if l['owner'] == 'w1')['attempts'][0]
        self.assertEqual((shown['fidelity'], shown['tokens']['fresh_input'], shown['origin']), ('reported', 100, 'legacy'))

    def test_usage_delegate_log_window_and_explicit_path(self):
        self.init()
        self.legacy('task', '--id', 'T002', '--status', 'running', '--agent', 'run-9')
        result = self.root / '.delegate' / 'runs' / 'run-9' / 'result.json'
        result.parent.mkdir(parents=True)
        result.write_text(json.dumps({'run_id': 'run-9', 'harness': 'codex', 'model': 'gpt-6', 'tokens': {
            'fidelity': 'exact', 'input_fresh': 11, 'cache_read': 5, 'cache_write': 0, 'output_total': 3, 'reasoning': 2}}), encoding='utf-8')
        code, out, err = self.legacy('usage', '--id', 'T002', '--agent', 'run-9', '--collect', 'delegate',
                                     '--log', str(result), '--since', '2026-10-15T10:00:00Z', '--until', '2026-10-15T11:00:00Z', '--summary')
        self.assertEqual(code, 0, out + err)
        usage = [a for a in self.facts('attempt') if a['run'] == 'legacy-T002-run-9'][-1]['usage']
        self.assertEqual((usage['fidelity'], usage['fresh_input'], usage['reasoning'], usage['harness'], usage['log']),
                         ('exact', 11, 2, 'codex', '.delegate/runs/run-9/result.json'))
        self.assertEqual((usage['since'], usage['until']), ('2026-10-15T10:00:00Z', '2026-10-15T11:00:00Z'))

    def test_usage_unavailable_is_a_gap_not_a_zero(self):
        self.init()
        self.legacy('task', '--id', 'T002', '--status', 'done', '--agent', 'ghost')
        os.environ['SANDUQ_CLAUDE_PROJECTS'] = str(self.root / 'nowhere')
        code, out, err = self.legacy('usage', '--id', 'T002', '--agent', 'ghost', '--collect', 'claude', '--summary')
        self.assertEqual(code, 0, out + err)
        usage = [a for a in self.facts('attempt') if a['run'] == 'legacy-T002-ghost'][-1]['usage']
        self.assertEqual(usage['fidelity'], 'unavailable')
        self.assertIsNone(usage['fresh_input'])
        self.assertTrue(usage['reason'])
        self.assertIn('Token usage unavailable for ghost', self.facts('note')[-1]['text'])
        self.assertIsNone(next(l for l in self.status()['lanes'] if l['owner'] == 'ghost')['attempts'][0]['tokens'])

    def test_overhead_usage_has_no_lane(self):
        self.init()
        code, out, err = self.legacy('usage', '--overhead', 'orchestrator', '--agent', 'o1', '--fresh-input', '5', '--summary')
        self.assertEqual(code, 0, out + err)
        row = self.facts('attempt')[-1]
        self.assertEqual((row['lane'], row['label']), (None, 'orchestrator'))
        self.assertEqual(self.status()['overhead'][0]['label'], 'orchestrator')

    def test_reused_agent_needs_a_started_task_to_split_its_log(self):
        self.init()
        self.legacy('task', '--id', 'T002', '--status', 'running', '--agent', 'w1')
        code, out, _ = self.legacy('usage', '--id', 'T003', '--agent', 'w1', '--collect', 'claude', '--summary')
        self.assertEqual(code, 2)
        self.assertIn('also worked on other tasks', out)
        self.assertTrue(out.startswith('error '))

    def test_unknown_task_and_missing_progress_state_fail_like_legacy(self):
        self.init()
        code, out, _ = self.legacy('task', '--id', 'T999', '--status', 'done', '--summary')
        self.assertEqual((code, out), (2, 'error Unknown task ID: T999'))


class CompatibilityErrors(Project):
    def test_unsupported_requests_exit_non_zero_with_an_explicit_error_and_write_nothing(self):
        self.init()
        before = self.facts()
        code, out, err = self.legacy('init', '--tasks', str(self.feature_dir / 'tasks.md'), '--title', 'Named')
        self.assertEqual(code, 2)
        self.assertIn('compatibility:', err)
        self.assertIn('--title', err)
        code, out, err = self.legacy('sync', '--json')
        self.assertEqual(code, 2)
        self.assertIn('compatibility:', err)
        code, out, _ = self.legacy('init', '--tasks', str(self.feature_dir / 'tasks.md'), '--title', 'Named', '--summary')
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith('error compatibility:'), out)
        self.assertEqual(self.facts(), before)

    def test_progress_failure_is_never_swallowed(self):
        self.init()
        code, out, err = self.legacy('event', '--message', 'password = hunter2hunter2', '--summary')
        self.assertNotEqual(code, 0)
        self.assertIn('PROGRESS_FORBIDDEN_CONTENT', out)


if __name__ == '__main__':
    unittest.main()
