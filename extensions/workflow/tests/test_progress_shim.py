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
        for name in bridge.HOST_ENV_CLAUDE + bridge.HOST_ENV_CODEX:
            os.environ.pop(name, None)
        # Keep the real user-level host configs out of every test.
        self.user_home = self.root / '.user-home'
        os.environ['CODEX_HOME'] = str(self.user_home / 'codex')
        os.environ['CLAUDE_CONFIG_DIR'] = str(self.user_home / 'claude')
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
    def mode(self, host='claude'):
        return bridge.mode(self.root, FEATURE, host=host)

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
        self.assertEqual(self.mode('codex')['mode'], 'refresh')

    def test_codex_config_toml_switch_disables_hooks_json(self):
        (self.root / '.codex').mkdir()
        (self.root / '.codex' / 'hooks.json').write_text(json.dumps({'hooks': {
            'Stop': [{'command': self.HOOK}]}}), encoding='utf-8')
        (self.root / '.codex' / 'config.toml').write_text('[features]\nhooks = false\n', encoding='utf-8')
        self.assertEqual(self.mode('codex')['mode'], 'refresh')
        (self.root / '.codex' / 'config.toml').write_text('[features]\ncodex_hooks = false\n', encoding='utf-8')
        self.assertEqual(self.mode('codex')['mode'], 'refresh')

    def test_user_level_switches_disable_project_hooks(self):
        (self.root / '.codex').mkdir()
        (self.root / '.codex' / 'hooks.json').write_text(json.dumps({'hooks': {
            'Stop': [{'command': self.HOOK}]}}), encoding='utf-8')
        self._codex_user(approve=[(self.root / '.codex' / 'hooks.json', 'stop', 0, 0)])
        self.assertEqual(self.mode('codex')['mode'], 'projection')
        codex_home = Path(os.environ['CODEX_HOME'])
        with open(codex_home / 'config.toml', 'a', encoding='utf-8') as handle:
            handle.write('\n[features]\nhooks = false\n')
        self.assertEqual(self.mode('codex')['mode'], 'refresh')
        (codex_home / 'config.toml').unlink()
        self._claude({'type': 'command', 'command': 'python .specify/events.py speckit.progress.hook-stop stop'})
        (self.root / '.codex' / 'hooks.json').unlink()
        self.assertEqual(self.mode()['mode'], 'projection')
        claude_home = Path(os.environ['CLAUDE_CONFIG_DIR'])
        claude_home.mkdir(parents=True)
        (claude_home / 'settings.json').write_text(json.dumps({'disableAllHooks': True}), encoding='utf-8')
        self.assertEqual(self.mode()['mode'], 'refresh')

    def test_extensions_yml_command_hooks_are_not_collection_evidence(self):
        # spec-kit writes only the manifest's after_* command hooks there, never the host event handlers.
        (self.root / '.specify' / 'extensions.yml').write_text(
            'hooks:\n  after_implement:\n  - extension: progress\n    command: speckit.progress.hook-stop\n'
            '    enabled: true\n', encoding='utf-8')
        self.assertEqual(self.mode()['mode'], 'refresh')
        self.assertFalse(hasattr(bridge, '_yml_hooks'))

    def test_disabled_extension_in_registry_is_legacy_and_does_not_forward(self):
        self._claude({'type': 'command', 'command': 'python .specify/events.py speckit.progress.hook-stop stop'})
        reg = self.root / '.specify' / 'extensions' / '.registry'
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text(json.dumps({'schema_version': '1.0', 'extensions': {'progress': {'enabled': False}}}), encoding='utf-8')
        decision = self.mode()
        self.assertEqual((decision['mode'], decision['script']), ('legacy', None))
        self.assertIsNone(bridge.script(self.root))
        code, out, err = self.legacy('init', '--tasks', str(self.feature_dir / 'tasks.md'), '--summary')
        self.assertEqual(code, 0, out + err)
        self.assertTrue((self.output / 'state.json').is_file())  # the legacy reporter ran
        self.assertFalse((self.feature_dir / 'progress').exists())

    def test_mode_runs_no_progress_process(self):
        calls = []
        real = bridge.run
        bridge.run = lambda *a, **k: calls.append(a) or real(*a, **k)
        self.addCleanup(setattr, bridge, 'run', real)
        self.assertEqual(self.mode()['mode'], 'refresh')
        self._claude({'type': 'command', 'command': self.HOOK})
        self.assertEqual(self.mode()['mode'], 'projection')
        self.assertEqual(calls, [])

    def _both_hosts(self):
        self._claude({'type': 'command', 'command': self.HOOK})
        (self.root / '.codex').mkdir(exist_ok=True)
        (self.root / '.codex' / 'hooks.json').write_text(json.dumps({'features': {'codex_hooks': False}, 'hooks': {
            'Stop': [{'command': self.HOOK}]}}), encoding='utf-8')

    def test_only_the_active_hosts_hooks_count(self):
        self._both_hosts()  # Claude hooks registered, Codex hooks switched off
        self.assertEqual(self.mode('claude')['mode'], 'projection')
        self.assertEqual(self.mode('codex')['mode'], 'refresh')
        self.assertEqual(self.mode('claude')['host'], 'claude')

    def test_active_host_is_detected_from_the_environment(self):
        self._both_hosts()
        self.assertEqual(self.mode(None)['mode'], 'refresh')  # unknown host
        os.environ['CLAUDECODE'] = '1'
        self.assertEqual(self.mode(None)['mode'], 'projection')
        os.environ['CODEX_THREAD_ID'] = 'abc'
        self.assertEqual(self.mode(None)['mode'], 'refresh')  # both signals: ambiguous
        os.environ.pop('CLAUDECODE')
        self.assertEqual(self.mode(None)['mode'], 'refresh')  # Codex only, and its hooks are off
        self.assertEqual(self.mode(None)['host'], 'codex')

    def test_codex_home_alone_does_not_identify_the_host(self):
        self._both_hosts()
        os.environ['CODEX_HOME'] = str(self.user_home / 'codex')
        self.assertIsNone(self.mode(None)['host'])

    def test_mode_command_takes_a_host(self):
        self._both_hosts()
        for host, expected in (('claude', 'projection'), ('codex', 'refresh')):
            done = subprocess.run([sys.executable, str(SCRIPTS / 'progress_bridge.py'), 'mode', '--root', str(self.root),
                                   '--host', host], capture_output=True, text=True, env=os.environ.copy())
            self.assertEqual((done.returncode, done.stdout.strip()), (0, 'reporting: ' + expected), done.stderr)

    def test_codex_toml_hook_is_detected_and_disabled_one_is_not(self):
        (self.root / '.codex').mkdir(exist_ok=True)
        cfg = self.root / '.codex' / 'config.toml'
        cfg.write_text('[[hooks.Stop]]\ncommand = "python x.py speckit.progress.hook-stop"\n', encoding='utf-8')
        self._codex_user(approve=[(cfg, 'stop', 0, 0)])
        self.assertEqual(self.mode('codex')['mode'], 'projection')
        cfg.write_text('[[hooks.Stop]]\nenabled = false\ncommand = "python x.py speckit.progress.hook-stop"\n', encoding='utf-8')
        self.assertEqual(self.mode('codex')['mode'], 'refresh')

    # --- Codex trust: a hook counts only for a trusted project with an approval for that exact hook ---
    def _codex_user(self, trusted=True, approve=(), quote="'"):
        """Write $CODEX_HOME/config.toml. `approve` holds (file, event, group, hook) tuples."""
        home = Path(os.environ['CODEX_HOME'])
        home.mkdir(parents=True, exist_ok=True)
        lines = []
        if trusted:
            path = str(self.root).lower()
            path = path.replace('\\', '\\\\') if quote == '"' else path
            lines.append(f'[projects.{quote}{path}{quote}]\ntrust_level = "trusted"\n')
        for file, event, group, hook in approve:
            key = f'{file}:{event}:{group}:{hook}'.replace('\\', '\\\\')
            lines.append(f'[hooks.state."{key}"]\ntrusted_hash = "sha256:abc"\n')
        (home / 'config.toml').write_text('\n'.join(lines), encoding='utf-8')

    def _codex_project_hook(self):
        (self.root / '.codex').mkdir(exist_ok=True)
        cfg = self.root / '.codex' / 'config.toml'
        cfg.write_text('[[hooks.Stop]]\n[[hooks.Stop.hooks]]\ntype = "command"\n'
                       'command = "python3 .specify/events.py speckit.progress.hook-stop stop 10"\n', encoding='utf-8')
        return cfg

    def test_codex_trusted_project_with_approved_hook_is_projection(self):
        cfg = self._codex_project_hook()
        self._codex_user(approve=[(cfg, 'stop', 0, 0)])
        decision = self.mode('codex')
        self.assertEqual((decision['mode'], decision['automatic']), ('projection', True))

    def test_codex_double_quoted_project_key_is_accepted(self):
        cfg = self._codex_project_hook()
        self._codex_user(approve=[(cfg, 'stop', 0, 0)], quote='"')
        self.assertEqual(self.mode('codex')['mode'], 'projection')

    def test_codex_untrusted_project_is_refresh_with_reason(self):
        cfg = self._codex_project_hook()
        self._codex_user(trusted=False, approve=[(cfg, 'stop', 0, 0)])
        decision = self.mode('codex')
        self.assertEqual((decision['mode'], decision['reason']), ('refresh', 'codex hooks not approved'))

    def test_codex_trusted_project_without_hook_state_is_refresh(self):
        self._codex_project_hook()
        self._codex_user()
        self.assertEqual(self.mode('codex')['mode'], 'refresh')
        self.assertEqual(self.mode('codex')['reason'], 'codex hooks not approved')

    def test_codex_approval_for_another_event_or_index_is_refresh(self):
        cfg = self._codex_project_hook()
        for other in ((cfg, 'session_start', 0, 0), (cfg, 'stop', 1, 0), (cfg, 'stop', 0, 1),
                      (self.root / '.codex' / 'other.toml', 'stop', 0, 0)):
            self._codex_user(approve=[other])
            self.assertEqual(self.mode('codex')['mode'], 'refresh', other)

    def test_codex_blank_trusted_hash_is_not_approval(self):
        cfg = self._codex_project_hook()
        self._codex_user()
        key = str(cfg).replace('\\', '\\\\')
        with open(Path(os.environ['CODEX_HOME']) / 'config.toml', 'a', encoding='utf-8') as handle:
            handle.write(f'\n[hooks.state."{key}:stop:0:0"]\ntrusted_hash = ""\n')
        self.assertEqual(self.mode('codex')['mode'], 'refresh')

    @unittest.skipUnless(os.name == 'nt', 'Windows path rules')
    def test_codex_state_key_path_case_and_separators_do_not_matter_on_windows(self):
        cfg = self._codex_project_hook()
        self._codex_user(approve=[(str(cfg).upper().replace('\\', '/'), 'stop', 0, 0)])
        self.assertEqual(self.mode('codex')['mode'], 'projection')

    def test_codex_user_level_hooks_json_needs_its_own_approval(self):
        home = Path(os.environ['CODEX_HOME'])
        home.mkdir(parents=True, exist_ok=True)
        hooks = home / 'hooks.json'
        hooks.write_text(json.dumps({'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': self.HOOK}]}]}}),
                         encoding='utf-8')
        self._codex_user(trusted=False)
        self.assertEqual(self.mode('codex')['mode'], 'refresh')
        self._codex_user(trusted=False, approve=[(hooks, 'stop', 0, 0)])
        self.assertEqual(self.mode('codex')['mode'], 'projection')

    def test_mode_command_text_carries_the_reason_and_json_has_it(self):
        self._codex_project_hook()
        self._codex_user()
        base = [sys.executable, str(SCRIPTS / 'progress_bridge.py'), 'mode', '--root', str(self.root), '--host', 'codex']
        text = subprocess.run(base, capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(text.stdout.strip(), 'reporting: refresh (codex hooks not approved)')
        data = subprocess.run(base + ['--json'], capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(json.loads(data.stdout)['reason'], 'codex hooks not approved')

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

    def test_a_new_worker_for_the_same_task_updates_the_lane_instead_of_adding_one(self):
        self.init()
        for agent in ('scope-worker', 'specify-worker', 'clarify-worker'):
            code, out, err = self.legacy('task', '--id', 'T002', '--status', 'running', '--agent', agent, '--summary')
            self.assertEqual(code, 0, out + err)
        self.assertEqual(len({l['id'] for l in self.facts('lane')}), 1)
        self.assertEqual(self.facts('lane')[-1]['owner'], 'clarify-worker')
        self.assertEqual(self.facts('lane')[-1]['tasks'], ['T002'])
        lanes = [l for l in self.status()['lanes'] if l.get('origin') == 'facts']
        self.assertEqual(len(lanes), 1)

    def test_reassigning_one_task_of_a_shared_lane_splits_it_out(self):
        self.init()
        for task in ('T002', 'T003'):
            code, out, err = self.legacy('task', '--id', task, '--status', 'running', '--agent', 'worker-a', '--summary')
            self.assertEqual(code, 0, out + err)
        code, out, err = self.legacy('task', '--id', 'T003', '--status', 'running', '--agent', 'worker-b', '--summary')
        self.assertEqual(code, 0, out + err)
        lanes = {l['owner']: l for l in self.status()['lanes'] if l.get('origin') == 'facts'}
        self.assertEqual(lanes['worker-a']['tasks']['active'], ['T002'])
        self.assertEqual(lanes['worker-b']['tasks']['active'], ['T003'])

    def test_reassigning_an_open_task_leaves_the_done_task_with_its_worker(self):
        self.init()
        for task in ('T002', 'T003'):
            code, out, err = self.legacy('task', '--id', task, '--status', 'running', '--agent', 'worker-a', '--summary')
            self.assertEqual(code, 0, out + err)
        code, out, err = self.legacy('task', '--id', 'T002', '--status', 'done', '--agent', 'worker-a', '--summary')
        self.assertEqual(code, 0, out + err)
        tasks = self.feature_dir / 'tasks.md'
        tasks.write_text(tasks.read_text(encoding='utf-8').replace('- [ ] T002', '- [x] T002'), encoding='utf-8', newline='')
        code, out, err = self.legacy('task', '--id', 'T003', '--status', 'running', '--agent', 'worker-b', '--summary')
        self.assertEqual(code, 0, out + err)
        lanes = {l['owner']: l for l in self.status()['lanes'] if l.get('origin') == 'facts'}
        self.assertIn('T002', lanes['worker-a']['tasks']['done'])
        self.assertEqual(lanes['worker-b']['tasks']['active'], ['T003'])
        self.assertNotIn('T002', lanes['worker-b']['tasks']['done'])

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


class ProcessCounts(Project):
    """Each forwarded legacy call spawns as few Progress processes as it needs."""

    def counted(self, *argv):
        calls, real = [], bridge.run
        bridge.run = lambda root, args, *a, **k: calls.append(args[0]) or real(root, args, *a, **k)
        try:
            code, out, err = self.legacy(*argv)
        finally:
            bridge.run = real
        self.assertEqual(code, 0, out + err)
        return calls

    # command -> (processes without --summary, with --summary)
    EXPECTED = {
        'event': (['status', 'note'], ['status', 'note', 'status']),
        'phase': (['status', 'note'], ['status', 'note', 'status']),
        'pr': (['status', 'note'], ['status', 'note', 'status']),
        'sync': (['status', 'refresh'], ['status', 'refresh', 'status']),
    }
    ARGS = {'event': ('--message', 'm'), 'phase': ('--name', 'P1', '--status', 'complete'),
            'pr': ('--url', 'https://github.com/a/b/pull/1', '--status', 'open'), 'sync': ()}

    def test_notes_and_sync_skip_redundant_status_calls(self):
        self.init()
        for command, (plain, summary) in self.EXPECTED.items():
            with self.subTest(command=command):
                self.assertEqual(self.counted(command, *self.ARGS[command]), plain)
                self.assertEqual(self.counted(command, *self.ARGS[command], '--summary'), summary)

    def test_first_call_for_a_feature_initialises_once(self):
        self.assertEqual(self.counted('event', '--message', 'm'), ['status', 'init', 'status', 'note'])

    def test_task_running_needs_one_status_before_and_none_after_without_summary(self):
        self.init()
        calls = self.counted('task', '--id', 'T002', '--status', 'running', '--agent', 'w1')
        self.assertEqual(calls.count('status'), 1, calls)
        self.assertEqual(self.counted('task', '--id', 'T002', '--status', 'running', '--agent', 'w1', '--summary').count('status'), 2)

    def test_usage_without_a_split_needs_no_extra_status(self):
        self.init()
        self.legacy('task', '--id', 'T002', '--status', 'running', '--agent', 'w1')
        calls = self.counted('usage', '--id', 'T002', '--agent', 'w1', '--fresh-input', '1')
        self.assertEqual(calls.count('status'), 1, calls)

    def test_init_prints_the_index_without_asking_status(self):
        calls = self.counted('init', '--tasks', str(self.feature_dir / 'tasks.md'))
        self.assertEqual(calls, ['init'])


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


class WorkstreamMarker(Project):
    """New lane facts carry `--workstream` only from Progress 1.2.0; older Progress gets no flag."""

    def fake_progress(self, version):
        folder = self.root / 'fake-progress'
        (folder / 'scripts').mkdir(parents=True, exist_ok=True)
        (folder / 'scripts' / 'progress.py').write_text('# fake', encoding='utf-8')
        (folder / 'extension.yml').write_text('extension:\n  id: progress\n  version: "%s"\n' % version, encoding='utf-8')
        os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(folder / 'scripts' / 'progress.py')

    def new_lane_argv(self):
        import progress_shim
        calls = []
        forward = progress_shim.Forward(self.root, FEATURE)
        forward.call = lambda *argv, **kwargs: calls.append(argv) or 'progress: L1 open 1 tasks'
        forward.new_lane('--tasks', 'T001', '--owner', 'worker', '--label', 'worker')
        return calls[0]

    def test_progress_1_2_0_gets_the_marker(self):
        self.fake_progress('1.2.0')
        argv = self.new_lane_argv()
        self.assertEqual(argv[:2], ('lane', 'new'))
        self.assertEqual(argv[-1], '--workstream')
        self.fake_progress('1.10.1')
        self.assertEqual(self.new_lane_argv()[-1], '--workstream')

    def test_older_progress_gets_no_flag_and_an_unreadable_version_is_probed(self):
        for version in ('1.1.3', '1.0.0'):
            self.fake_progress(version)
            self.assertNotIn('--workstream', self.new_lane_argv())
        self.assertEqual(bridge.progress_version(self.root), (1, 0, 0))
        (self.root / 'fake-progress' / 'extension.yml').unlink()
        self.assertIsNone(bridge.progress_version(self.root))  # no extension.yml and no package VERSION

    def fake_source_tree(self, version):
        """A script folder with no extension.yml beside it, only the package's VERSION."""
        folder = self.root / 'source-tree'
        (folder / 'sanduq_progress').mkdir(parents=True, exist_ok=True)
        (folder / 'progress.py').write_text('# fake', encoding='utf-8')
        (folder / 'sanduq_progress' / '__init__.py').write_text("VERSION = '%s'\n" % version, encoding='utf-8')
        os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(folder / 'progress.py')

    def test_a_source_tree_without_extension_yml_is_versioned_from_the_package(self):
        self.fake_source_tree('1.2.0')
        self.assertEqual(bridge.progress_version(self.root), (1, 2, 0))
        self.assertEqual(self.new_lane_argv()[-1], '--workstream')
        self.fake_source_tree('1.1.0')
        self.assertNotIn('--workstream', self.new_lane_argv())

    def test_extension_yml_wins_over_the_package_version(self):
        self.fake_source_tree('1.0.0')
        (self.root / 'extension.yml').write_text('extension:\n  id: progress\n  version: "1.5.0"\n', encoding='utf-8')
        self.assertEqual(bridge.progress_version(self.root), (1, 5, 0))

    PROBE = r"""import json, sys
open(LOG, "a").write(json.dumps(sys.argv[1:]) + "\n")
if "--workstream" in sys.argv and not ACCEPTS:
    print("PROGRESS_USAGE: unrecognized arguments: --workstream", file=sys.stderr)
    sys.exit(2)
print("progress: L1 open 1 tasks")
"""

    def unversioned(self, accepts):
        import progress_shim
        progress_shim.WORKSTREAM_PROBE.clear()
        script = self.root / 'unversioned.py'
        script.write_text(self.PROBE.replace('LOG', repr(str(self.root / 'probe.log'))).replace('ACCEPTS', repr(accepts)),
                          encoding='utf-8')
        os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(script)
        log = self.root / 'probe.log'
        if log.exists():
            log.unlink()
        return progress_shim, log

    def lines(self, log):
        return [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]

    def test_an_unversioned_progress_is_probed_once_per_process(self):
        shim, log = self.unversioned(True)
        forward = shim.Forward(self.root, FEATURE)
        forward.new_lane('--tasks', 'T001')
        forward.new_lane('--tasks', 'T002')
        calls = self.lines(log)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(c[-1] == '--workstream' for c in calls))

    def test_an_unversioned_progress_that_rejects_the_flag_is_retried_without_it_then_remembered(self):
        shim, log = self.unversioned(False)
        forward = shim.Forward(self.root, FEATURE)
        forward.new_lane('--tasks', 'T001')
        forward.new_lane('--tasks', 'T002')
        calls = self.lines(log)
        self.assertEqual([c[-1] for c in calls], ['--workstream', 'T001', 'T002'])  # one probe, then no flag at all
        self.assertNotIn('--workstream', calls[1] + calls[2])


class StatusSchemaFlag(Project):
    """`bridge.status` asks for v2 and falls back once for a Progress that does not know `--schema`."""

    FAKE = r"""import json, sys
open(LOG, "a").write(json.dumps(sys.argv[1:]) + "\n")
if "--schema" in sys.argv and not ACCEPTS:
    print("PROGRESS_USAGE: unrecognized arguments: --schema", file=sys.stderr)
    sys.exit(2)
print(json.dumps({"schema": "v2" if "--schema" in sys.argv else "legacy"}))
"""

    def fake(self, accepts_schema):
        script = self.root / 'fake_progress.py'
        text = self.FAKE.replace('LOG', repr(str(self.root / 'calls.log'))).replace('ACCEPTS', repr(accepts_schema))
        script.write_text(text, encoding='utf-8')
        os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(script)

    def calls(self):
        return [json.loads(line) for line in (self.root / 'calls.log').read_text(encoding='utf-8').splitlines()]

    def test_a_progress_that_accepts_the_flag_is_asked_once_for_v2(self):
        self.fake(True)
        self.assertEqual(bridge.status(self.root, FEATURE), {'schema': 'v2'})
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][-2:], ['--schema', 'v2'])

    def test_a_progress_that_names_another_usage_error_is_not_retried(self):
        # Exit 2 also reports an uninitialised feature; retrying without --schema cannot fix that.
        script = self.root / 'fake_progress.py'
        script.write_text("import json, sys\nopen(%r, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
                          "print('PROGRESS_NOT_INITIALISED: run progress init', file=sys.stderr)\nsys.exit(2)\n"
                          % str(self.root / 'calls.log'), encoding='utf-8')
        os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(script)
        self.assertIsNone(bridge.status(self.root, FEATURE))
        self.assertEqual(len(self.calls()), 1)

    def test_the_exact_call_sequence_for_an_uninitialised_unversioned_feature(self):
        script = self.root / 'fake_progress.py'
        script.write_text(
            "import json, os, sys\nlog = %r\nopen(log, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "verb = [a for a in sys.argv[3:] if not a.startswith('-')][0]\n"
            "marker = log + '.init'\n"
            "if verb == 'init':\n    open(marker, 'w').write('x')\n    print('progress: initialised')\n    sys.exit(0)\n"
            "if verb == 'status' and not os.path.exists(marker):\n"
            "    print('PROGRESS_NOT_INITIALISED: run progress init', file=sys.stderr)\n    sys.exit(2)\n"
            "print(json.dumps({'schema': 'v2'}))\n" % str(self.root / 'calls.log'), encoding='utf-8')
        os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(script)
        import progress_shim
        forward = progress_shim.Forward(self.root, FEATURE)
        forward.ensure_init()
        verbs = [[a for a in c[2:] if not a.startswith('-')][0] for c in self.calls()]
        self.assertEqual(verbs, ['status', 'init', 'status'])  # no extra status between the failure and init
        self.assertEqual([c for c in self.calls() if 'status' in c][0][-2:], ['--schema', 'v2'])

    def test_an_older_progress_is_retried_once_without_the_flag(self):
        self.fake(False)
        self.assertEqual(bridge.status(self.root, FEATURE), {'schema': 'legacy'})
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        self.assertIn('--schema', calls[0])
        self.assertNotIn('--schema', calls[1])


if __name__ == '__main__':
    unittest.main()
