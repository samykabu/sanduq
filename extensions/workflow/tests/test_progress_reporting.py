"""Reporting modes, Progress wiring, the legacy reporter, and the Progress CLI contract reporting.md names.

Moved from test_progress_shim.py when the forwarder was retired (round 4, D5).
"""
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

    def run_legacy(self, *argv):
        """Run the legacy script in-process; return (exit code, stdout, stderr)."""
        out, err, code = io.StringIO(), io.StringIO(), 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                legacy.main(list(argv))
            except SystemExit as exit_:
                code = exit_.code if isinstance(exit_.code, int) else 1
        return code, out.getvalue().strip(), err.getvalue().strip()

    def legacy(self, command, *args):
        return self.run_legacy(command, '--output', str(self.output), *args)

    def progress(self, *args):
        done = subprocess.run([sys.executable, str(PROGRESS_SCRIPT), '--root', str(self.root), *args], capture_output=True,
                              text=True, encoding='utf-8')
        return done.returncode, done.stdout.strip()

    def facts(self, kind=None):
        path = self.feature_dir / 'progress' / 'facts.jsonl'
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.is_file() else []
        return [r for r in rows if kind in (None, r['kind'])]

    def init(self):
        code, out = self.progress('init', '--feature', FEATURE)
        self.assertEqual(code, 0, out)
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

    def test_native_hook_py_entries_mean_projection(self):
        """`progress hooks install` (progress.hook_wiring: native) writes hook.py entries without the Spec Kit command."""
        self._claude({'type': 'command', 'timeout': 10, 'command': 'python "${CLAUDE_PROJECT_DIR}/.specify/extensions/progress/'
                      'scripts/hook.py" stop --managed-by=progress-report; exit 0'})
        self.assertEqual(self.mode()['mode'], 'projection')


SPECKIT_CLAUDE = {'hooks': {
    'PostToolUse': [{'matcher': '', 'hooks': [
        {'type': 'command', 'command': '"${CLAUDE_PROJECT_DIR}"/.specify/events.py speckit.progress.hook post_tool_use 10',
         'timeout': 15, '__speckit_event__': True},
        {'type': 'command', 'command': 'python other.py'}]}],
    'Stop': [{'hooks': [{'type': 'command', 'command': '"${CLAUDE_PROJECT_DIR}"/.specify/events.py speckit.progress.hook stop 10',
                         'timeout': 15, '__speckit_event__': True}]}]}}
SPECKIT_CODEX = ''.join(
    f'[[hooks.{event}]]\nmatcher = "*"\n\n[[hooks.{event}.hooks]]\ntype = "command"\n'
    f'command = "python3 .specify/events.py speckit.progress.hook {name} 10"\ntimeout = 15\nspeckit_marker = true\n\n'
    for event, name in (('PostToolUse', 'post_tool_use'), ('Stop', 'stop')))


class ProgressWiring(Project):
    """install.wire_progress: the `progress:` policy applied to the host files after Spec Kit rendered its entries."""

    def setUp(self):
        super().setUp()
        import install
        self.install = install
        shutil.copytree(PROGRESS_SCRIPT.parent, self.root / '.specify/extensions/progress/scripts',
                        ignore=shutil.ignore_patterns('__pycache__'))
        (self.root / '.claude').mkdir()
        (self.root / '.codex').mkdir()
        self.claude = self.root / '.claude/settings.json'
        self.codex = self.root / '.codex/config.toml'
        self.claude.write_text(json.dumps(SPECKIT_CLAUDE, indent=2), encoding='utf-8')
        self.codex.write_text(SPECKIT_CODEX, encoding='utf-8')

    def wire(self, **progress):
        return self.install.wire_progress(self.root, {'progress': progress} if progress else {}, ['claude', 'codex'])

    def test_defaults_leave_the_spec_kit_entries_alone(self):
        record = self.wire()
        self.assertEqual((record['hook_wiring'], record['post_tool_matcher']), ('speckit', ''))
        self.assertEqual(json.loads(self.claude.read_text(encoding='utf-8')), SPECKIT_CLAUDE)
        self.assertEqual(self.codex.read_text(encoding='utf-8'), SPECKIT_CODEX)

    def test_speckit_matcher_is_set_on_both_hosts(self):
        record = self.wire(post_tool_matcher='Bash|Task')
        self.assertTrue(record['hosts']['claude']['matcher_applied'] and record['hosts']['codex']['matcher_applied'])
        groups = json.loads(self.claude.read_text(encoding='utf-8'))['hooks']['PostToolUse']
        self.assertEqual([(g['matcher'], [h['command'] for h in g['hooks']]) for g in groups],
                         [('', ['python other.py']), ('Bash|Task', [SPECKIT_CLAUDE['hooks']['PostToolUse'][0]['hooks'][0]['command']])])
        hooks = __import__('tomllib').loads(self.codex.read_text(encoding='utf-8'))['hooks']
        self.assertEqual((hooks['PostToolUse'][0]['matcher'], hooks['Stop'][0]['matcher']), ('Bash|Task', '*'))

    def test_native_replaces_the_spec_kit_entries_and_records_it(self):
        record = self.wire(hook_wiring='native', post_tool_matcher='Bash|Task')
        self.assertEqual([record['hosts'][h]['speckit_entries_removed'] for h in ('claude', 'codex')], [2, 2])
        self.assertNotIn('speckit.progress.hook', self.claude.read_text(encoding='utf-8') + self.codex.read_text(encoding='utf-8'))
        settings = json.loads(self.claude.read_text(encoding='utf-8'))['hooks']
        commands = [h['command'] for groups in settings.values() for g in groups for h in g['hooks']]
        self.assertIn('python other.py', commands)
        self.assertTrue(all('scripts/hook.py' in c for c in commands if c != 'python other.py'))
        self.assertTrue((self.root / '.codex/hooks.json').is_file())
        self.assertEqual(record['hosts']['codex']['file'], '.codex/hooks.json')
        script = self.root / self.install.PROGRESS_SCRIPT
        accepted = self.install.progress_accepts(script, '--post-tool-matcher')
        self.assertEqual(record['hosts']['claude']['matcher_applied'], accepted)
        if accepted:
            self.assertIn('Bash|Task', [g.get('matcher') for g in settings['PostToolUse']])
        else:
            self.assertIn('post_tool_matcher not applied', record['hosts']['claude']['note'])
        self.assertEqual(self.mode(), 'projection')
        # Back to the default: hook.py's entries go (Spec Kit renders its own again when install() re-adds progress).
        back = self.wire()
        self.assertIn('removed', back['hosts']['claude']['native_entries_removed'])
        self.assertNotIn('--managed-by=progress-report', self.claude.read_text(encoding='utf-8'))
        self.assertNotIn('--managed-by=progress-report', (self.root / '.codex/hooks.json').read_text(encoding='utf-8'))

    def mode(self):
        return bridge.mode(self.root, FEATURE, host='claude')['mode']


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


LEGACY_CALLS = {
    'init': ['--tasks', 'TASKS'], 'task': ['--id', 'T002', '--status', 'running'], 'event': ['--message', 'hello'],
    'phase': ['--name', 'Setup', '--status', 'done'], 'pr': ['--url', 'https://github.com/acme/app/pull/1', '--status', 'open'],
    'usage': ['--id', 'T002', '--agent', 'w1', '--fresh-input', '10'], 'sync': []}
REPLACEMENT = {'init': 'progress.py init', 'task': 'tasks.md', 'event': 'note', 'phase': 'tasks.md',
               'pr': "note 'PR open: <url>'", 'usage': 'hooks and delegate results', 'sync': 'progress.py refresh'}


class LegacyCallsWithProgress(Project):
    """D5: with Progress installed and enabled a legacy call writes nothing, exits 2 and names the replacement."""

    def args(self, command):
        return [str(self.feature_dir / 'tasks.md') if a == 'TASKS' else a for a in LEGACY_CALLS[command]]

    def assert_nothing_written(self):
        self.assertFalse(self.output.exists())
        self.assertFalse((self.feature_dir / 'progress').exists())

    def test_each_legacy_call_exits_2_with_one_line_naming_its_replacement(self):
        for command in LEGACY_CALLS:
            with self.subTest(command=command):
                code, out, err = self.legacy(command, *self.args(command), '--summary')
                self.assertEqual(code, 2)
                self.assertEqual(len(out.splitlines()), 1, out)
                self.assertTrue(out.startswith('error PROGRESS_INSTALLED: '), out)
                self.assertIn(REPLACEMENT[command], out)
                self.assertEqual(err, '')
                self.assert_nothing_written()

    def test_without_summary_the_line_goes_to_stderr(self):
        for flags in ([], ['--json']):
            code, out, err = self.legacy('sync', *flags)
            self.assertEqual((code, out), (2, ''))
            self.assertIn('PROGRESS_INSTALLED', err)
            self.assert_nothing_written()

    def test_the_forwarder_is_gone(self):
        self.assertFalse((SCRIPTS / 'progress_shim.py').exists())
        self.assertFalse(hasattr(bridge, 'status'))  # the v2 projection reader had no other caller


class ProgressCliContract(Project):
    """IP23: the verbs reporting.md tells the coordinator to call, against the real Progress CLI."""

    def call(self, *args):
        code, out = self.progress(*args, '--feature', FEATURE)
        self.assertEqual(code, 0, (args, out))
        self.assertLessEqual(len(out.splitlines()), 1, (args, out))
        return out

    def test_the_seven_verbs_take_the_documented_arguments_and_print_at_most_one_line(self):
        self.assertTrue(self.call('init').startswith('progress: ready '))
        self.assertIn('L1 open', self.call('lane', 'L1', '--tasks', 'T001-T002', '--owner', 'w1', '--harness', 'codex',
                                           '--model', 'm', '--effort', 'high', '--workstream'))
        blocked = self.call('block', 'T002', '--by', 'L1')
        block_id = blocked.split()[1]
        self.assertRegex(block_id, r'^B\d+$')
        self.assertIn('resolved', self.call('unblock', block_id))
        self.assertIn('noted', self.call('note', 'PR open: https://github.com/acme/app/pull/1'))
        self.assertIn('noted', self.call('note', 'Budget overrun T001: tests 3/2: flaky', '--target', 'T001'))
        self.assertEqual(self.call('refresh'), '')  # quiet unless --verbose
        self.assertEqual(self.call('refresh', '--final'), '')
        self.assertTrue(self.call('refresh', '--verbose').startswith('progress: refreshed rev '))
        self.assertIn('self-report', self.call('bind', '--host', 'codex', '--model', 'm', '--effort', 'high'))
        # W21: the text status line `workflow status` carries, one line and no projection schema.
        line = self.call('status')
        self.assertRegex(line, r'^progress: \d+/\d+ tasks, ')
        self.assertEqual(bridge.status_line(self.root, FEATURE), line)

    def test_every_verb_reporting_md_names_is_tested(self):
        text = (SCRIPTS.parent / 'skills/workflow/references/reporting.md').read_text(encoding='utf-8')
        import re
        named = set(re.findall(r'`progress (\w+)', text))
        self.assertEqual(named, {'init', 'lane', 'block', 'unblock', 'note', 'refresh', 'bind'})


class StatusLine(Project):
    """W21: the workflow record carries Progress's line, never a v2 projection."""
    installed = False

    def test_absent_progress_gives_no_line(self):
        self.assertIsNone(bridge.status_line(self.root, FEATURE))

    def test_a_failing_progress_returns_its_line_instead_of_raising(self):
        fake = self.root / 'fake_progress.py'
        fake.write_text("import sys\nprint('progress: error PROGRESS_NOT_INITIALISED run progress init')\nsys.exit(3)\n",
                        encoding='utf-8')
        os.environ['SANDUQ_PROGRESS_SCRIPT'] = str(fake)
        self.assertEqual(bridge.status_line(self.root, FEATURE), 'progress: error PROGRESS_NOT_INITIALISED run progress init')


class DoubledProgressWiring(unittest.TestCase):
    """IP20: doctor and status warn when native Progress wiring sits next to a re-rendered dispatcher entry."""

    def setUp(self):
        import test_workflow as fixture
        self.w = fixture.w
        fixture.WorkflowTests.setUp(self)

    configure = __import__('test_workflow').WorkflowTests.configure

    def test_native_wiring_with_a_dispatcher_entry_is_reported_with_the_fix(self):
        w = self.w
        settings = self.root / '.claude/settings.json'
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(SPECKIT_CLAUDE), encoding='utf-8')
        self.assertEqual(w.progress_wiring_warnings(self.root), [])  # default (speckit) wiring: the entry is expected
        w.write(self.root / '.specify/workflow/install-lock.json', {'progress': {'hook_wiring': 'native'}})
        warnings = w.progress_wiring_warnings(self.root)
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].startswith('PROGRESS_HOOKS_DOUBLE_WIRED: .claude/settings.json '))
        self.assertIn('install.py --apply', warnings[0])
        self.assertIn(warnings[0], w.doctor(self.root, self.policy)['warnings'])
        settings.write_text(json.dumps({'hooks': {}}), encoding='utf-8')
        self.assertEqual(w.progress_wiring_warnings(self.root), [])


if __name__ == '__main__':
    unittest.main()
