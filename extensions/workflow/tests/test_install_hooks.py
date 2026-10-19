"""Installer: Illustrate hook ownership (IP5), Progress hook cost class (IP9), presets re-added only when changed."""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import install as installer
import upgrade
import workflow as w
import test_install
import test_workflow as fixture

EXTENSIONS = Path(__file__).resolve().parents[2]
HOOK = EXTENSIONS / 'illustrate/hooks/self_check_hook.py'
PROGRESS_SCRIPTS = EXTENSIONS / 'progress/scripts'
OTHER = {'type': 'command', 'command': 'python other.py'}


def dispatcher(command, interpreter='python3'):
    return f'{shlex.quote(interpreter)} "${{CLAUDE_PROJECT_DIR}}/.specify/events.py" {command} post_tool_use 60'


def toml_block(command, interpreter='python3'):
    line = dispatcher(command, interpreter).replace('"${CLAUDE_PROJECT_DIR}/', '').replace('events.py"', 'events.py')
    return ('[[hooks.PostToolUse]]\nmatcher = "*"\n[[hooks.PostToolUse.hooks]]\ntype = "command"\n'
            f'command = {json.dumps(line)}\ntimeout = 65\nspeckit_marker = true\n\n')


class Apply(unittest.TestCase):
    """A real install() apply with Spec Kit stubbed out and both hosts installed."""
    configure = fixture.WorkflowTests.configure
    setUp_package = test_install.InstallTests.setUp
    version = test_install.InstallTests.version

    def setUp(self):
        self.setUp_package()
        w.write(self.root / '.specify/integration.json', {'integration': 'codex', 'installed_integrations': ['codex', 'claude']})
        hook = self.root / installer.ILLUSTRATE_HOOK
        hook.parent.mkdir(parents=True)
        shutil.copyfile(HOOK, hook)
        for name, value in (('install_aliases', {}), ('doctor', {'ok': True, 'errors': []}), ('skill_errors', [])):
            patcher = patch.object(installer, name, return_value=value); patcher.start(); self.addCleanup(patcher.stop)
        self.claude = self.root / '.claude/settings.json'
        self.codex_hooks = self.root / '.codex/hooks.json'
        self.codex_toml = self.root / '.codex/config.toml'

    def consumer_250(self):
        """What a 2.5.0 install left: Spec Kit dispatcher entries for Illustrate next to unrelated hooks."""
        self.claude.parent.mkdir(exist_ok=True); self.codex_toml.parent.mkdir(exist_ok=True)
        self.claude.write_text(json.dumps({'hooks': {'PostToolUse': [
            {'matcher': 'Write|Edit', 'hooks': [{'type': 'command', 'command': dispatcher('speckit.illustrate.hook'),
                                                 '__speckit_event__': True}]},
            {'matcher': '', 'hooks': [OTHER]}]}}, indent=2), encoding='utf-8')
        self.codex_toml.write_text('model = "gpt"\n\n' + toml_block('speckit.illustrate.hook') + toml_block('speckit.other.hook'),
                                   encoding='utf-8')

    def self_check(self, value):
        self.policy['illustrate'] = {'hooks': {'self_check': value}}
        self.configure()

    def apply(self, runner=lambda *args: None):
        return installer.install(self.root, apply=True, package_root=self.package, runner=runner)

    def host_text(self):
        return {p.name: p.read_bytes() for p in (self.claude, self.codex_hooks, self.codex_toml) if p.exists()}

    def ours(self):
        return self.host_text().get('settings.json', b'').count(b'sanduq-illustrate'), \
            self.host_text().get('hooks.json', b'').count(b'sanduq-illustrate')


class IllustrateHook(Apply):
    def test_key_off_removes_the_250_dispatcher_entries_and_keeps_unrelated_hooks(self):
        self.consumer_250()
        result = self.apply()
        text = b''.join(self.host_text().values())
        self.assertNotIn(b'speckit.illustrate.hook', text)
        self.assertIn(b'python other.py', text)
        self.assertIn(b'speckit.other.hook', text)
        self.assertEqual(self.ours(), (0, 0))
        lock = w.read(self.root / '.specify/workflow/install-lock.json')['illustrate']
        self.assertEqual(lock, result['illustrate'])
        self.assertEqual((lock['action'], lock['self_check']), ('uninstall', False))
        self.assertEqual({h: e['removed'] for h, e in lock['hosts'].items()}, {'claude': 1, 'codex': 1})
        self.assertNotIn('illustrate_hook_approval', result)

    def test_key_on_installs_one_entry_per_host_asks_for_codex_approval_and_reruns_unchanged(self):
        self.consumer_250()
        self.self_check(True)
        result = self.apply()
        self.assertEqual(self.ours(), (1, 1))
        self.assertNotIn(b'speckit.illustrate.hook', b''.join(self.host_text().values()))
        hosts = w.read(self.root / '.specify/workflow/install-lock.json')['illustrate']['hosts']
        self.assertEqual({h: (e['file'], e['added'], e['needs_approval']) for h, e in hosts.items()},
                         {'claude': ('.claude/settings.json', 1, False), 'codex': ('.codex/hooks.json', 1, True)})
        self.assertEqual(result['illustrate_hook_approval'], installer.ILLUSTRATE_HOOK_APPROVAL)
        before = self.host_text()
        again = self.apply()
        self.assertEqual(self.host_text(), before)
        self.assertEqual({h: (e['added'], e['removed']) for h, e in again['illustrate']['hosts'].items()},
                         {'claude': (0, 0), 'codex': (0, 0)})
        self.assertNotIn('illustrate_hook_approval', again)
        # Turning the key off again removes both entries.
        self.self_check(False)
        self.apply()
        self.assertEqual(self.ours(), (0, 0))
        self.assertIn(b'python other.py', self.claude.read_bytes())

    def test_failure_mid_apply_rolls_back_both_host_files(self):
        self.consumer_250()
        self.self_check(True)
        before = self.host_text()
        lock = self.root / '.specify/workflow/install-lock.json'
        run = subprocess.run

        def codex_fails(args, *rest, **kwargs):
            if 'install' in args and '--host' in args and args[args.index('--host') + 1] == 'codex':
                return subprocess.CompletedProcess(args, 2, '', 'boom')
            return run(args, *rest, **kwargs)
        with patch.object(installer.subprocess, 'run', side_effect=codex_fails):
            with self.assertRaisesRegex(w.WorkflowError, 'INSTALL_ROLLED_BACK: ILLUSTRATE_HOOK_INSTALL_FAILED: codex'):
                self.apply()
        self.assertEqual(self.host_text(), before)
        self.assertFalse(lock.exists())
        # A failure after both host files changed rolls back just the same.
        with patch.object(installer, 'skill_errors', return_value=['LATE_FAILURE']):
            with self.assertRaisesRegex(w.WorkflowError, 'LATE_FAILURE'):
                self.apply()
        self.assertEqual(self.host_text(), before)

    def test_an_illustrate_without_the_management_cli_fails_instead_of_passing_silently(self):
        (self.root / installer.ILLUSTRATE_HOOK).write_text('import sys\nsys.stdin.read()\n', encoding='utf-8')
        with self.assertRaisesRegex(w.WorkflowError, 'ILLUSTRATE_HOOK_UNINSTALL_FAILED'):
            self.apply()

    def test_missing_script_is_skipped_when_off_and_refused_when_on(self):
        (self.root / installer.ILLUSTRATE_HOOK).unlink()
        self.assertEqual(installer.wire_illustrate(self.root, {}, ['claude'])['skipped'], 'hook script not installed')
        with self.assertRaisesRegex(w.WorkflowError, 'ILLUSTRATE_HOOK_SCRIPT_MISSING'):
            installer.wire_illustrate(self.root, {'illustrate': {'hooks': {'self_check': True}}}, ['claude'])


class Presets(Apply):
    def setUp(self):
        super().setUp()
        lock = w.read(self.package / 'dependencies.json')
        versions = {**lock['required'], **{k: v for group in lock['selected'].values() for k, v in group.items()}}
        w.write(self.root / '.specify/extensions/.registry',
                {'extensions': {n: {'version': v, 'enabled': True} for n, v in versions.items()}})
        for name, version in versions.items():
            manifest = self.root / '.specify/extensions' / name / 'extension.yml'
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({'extension': {'id': name, 'version': version,
                                                          'repository': 'https://github.com/samykabu/sanduq'}}), encoding='utf-8')
        w.write(self.root / '.specify/presets/.registry', {'presets': {
            name: {'enabled': True, 'priority': int(priority)}
            for name, priority in (('scope-gate', '2'), ('scope-brainstorm', '2'), ('workflow', '1'))}})

    def preset_commands(self):
        seen = []
        self.apply(runner=lambda root, args, log: seen.append(args))
        return [args[2] + ' ' + args[-1 if args[2] == 'remove' else 4] for args in seen if args[:2] == ['specify', 'preset']]

    def test_a_no_op_apply_runs_no_preset_command_and_a_changed_preset_is_re_added(self):
        first = self.preset_commands()  # no digest recorded yet: every preset is re-added once
        self.assertEqual(len(first), 6)
        self.assertEqual(self.preset_commands(), [])
        self.assertEqual(w.read(self.root / '.specify/workflow/install-receipt.json')['skipped_presets'],
                         ['scope-gate', 'scope-brainstorm', 'workflow'])
        (self.package / 'presets/workflow/preset.yml').write_text('schema_version: "1.1"', encoding='utf-8')
        changed = self.preset_commands()
        self.assertEqual(changed, ['remove workflow', 'add ' + str(self.package / 'presets/workflow')])

    def test_an_extension_update_still_re_adds_every_preset(self):
        self.preset_commands()
        self.version('pr', '0.0.1')
        self.assertEqual(len(self.preset_commands()), 6)

    def test_a_preset_removed_from_the_project_is_re_added(self):
        self.preset_commands()
        shutil.rmtree(self.root / '.specify/presets/scope-gate')
        self.assertEqual(self.preset_commands(), ['add ' + str(self.package / 'presets/scope-gate')])


class ProgressCost(unittest.TestCase):
    """IP9: wire_progress reports which dispatcher path Progress hooks take and hints at native wiring."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        shutil.copytree(PROGRESS_SCRIPTS, self.root / '.specify/extensions/progress/scripts',
                        ignore=shutil.ignore_patterns('__pycache__'))
        (self.root / '.claude').mkdir(); (self.root / '.codex').mkdir()
        (self.root / '.claude/settings.json').write_text(json.dumps({'hooks': {'PostToolUse': [{'matcher': '*', 'hooks': [
            {'type': 'command', 'command': dispatcher('speckit.progress.hook', sys.executable), '__speckit_event__': True}]}]}}),
            encoding='utf-8')
        (self.root / '.codex/config.toml').write_text(toml_block('speckit.progress.hook', sys.executable), encoding='utf-8')
        # A stub specify_cli on PYTHONPATH shadows any installed one, with or without its events module.
        self.stub = self.root / 'stub/specify_cli'
        self.stub.mkdir(parents=True); (self.stub / '__init__.py').write_text('', encoding='utf-8')
        environ = patch.dict(os.environ, {'PYTHONPATH': str(self.stub.parent)}); environ.start(); self.addCleanup(environ.stop)

    def wire(self, **progress):
        return installer.wire_progress(self.root, {'progress': progress}, ['claude', 'codex'])

    def test_an_interpreter_that_imports_specify_cli_is_the_slow_class_with_a_hint(self):
        (self.stub / 'events.py').write_text('', encoding='utf-8')
        record = self.wire()
        self.assertEqual(record['hint'], installer.SLOW_DISPATCHER_HINT)
        for host in ('claude', 'codex'):
            self.assertEqual(record['hosts'][host]['cost_class'], 'dispatcher-specify-cli')
            self.assertEqual(record['hosts'][host]['dispatcher'], {
                'path': '.specify/events.py', 'interpreter': sys.executable, 'imports_specify_cli': True})

    def test_a_plain_interpreter_is_the_dispatcher_class_without_a_hint(self):
        record = self.wire()
        self.assertNotIn('hint', record)
        self.assertEqual([record['hosts'][h]['cost_class'] for h in ('claude', 'codex')], ['dispatcher', 'dispatcher'])
        self.assertFalse(record['hosts']['claude']['dispatcher']['imports_specify_cli'])

    def test_native_wiring_has_no_hint(self):
        (self.stub / 'events.py').write_text('', encoding='utf-8')
        record = self.wire(hook_wiring='native')
        self.assertNotIn('hint', record)
        self.assertEqual([record['hosts'][h]['cost_class'] for h in ('claude', 'codex')], ['native', 'native'])


class UpgradeHooks(unittest.TestCase):
    """upgrade.py runs the new installer, so a failure there restores every host file the hook touched."""
    configure = fixture.WorkflowTests.configure
    setUp_upgrade = __import__('test_upgrade').UpgradeCITests.setUp

    def setUp(self):
        self.setUp_upgrade()
        (self.root / '.codex').mkdir(); (self.root / '.claude').mkdir()
        self.files = {self.root / '.claude/settings.json': b'{"hooks": {}}\n', self.root / '.codex/config.toml': toml_block(
            'speckit.illustrate.hook').encode()}
        for path, content in self.files.items():
            path.write_bytes(content)

    def installer(self, fail):
        def runner(root, args, log):
            if args[0] != sys.executable:
                return
            (root / '.claude/settings.json').write_text('{"hooks": {"PostToolUse": []}}', encoding='utf-8')
            (root / '.codex/config.toml').write_text('', encoding='utf-8')
            (root / '.codex/hooks.json').write_text('{}', encoding='utf-8')
            if fail:
                raise w.WorkflowError('INSTALL_ROLLED_BACK: boom')
            log.append({'args': args, 'stdout': json.dumps({
                'illustrate': {'action': 'install', 'hosts': {'codex': {'needs_approval': True}}},
                'illustrate_hook_approval': installer.ILLUSTRATE_HOOK_APPROVAL})})
        return runner

    def test_a_failed_installer_step_restores_the_host_files(self):
        with self.assertRaisesRegex(w.WorkflowError, 'WORKFLOW_UPGRADE_ROLLED_BACK'):
            upgrade.upgrade(self.root, '1.1.1', apply=True, runner=self.installer(True))
        self.assertEqual({p: p.read_bytes() for p in self.files}, self.files)
        self.assertFalse((self.root / '.codex/hooks.json').exists())

    def test_the_hook_record_and_codex_step_reach_the_upgrade_result(self):
        result = upgrade.upgrade(self.root, '1.1.1', apply=True, runner=self.installer(False))
        self.assertEqual(result['illustrate']['action'], 'install')
        self.assertEqual(result['illustrate_hook_approval'], installer.ILLUSTRATE_HOOK_APPROVAL)



@unittest.skipUnless(shutil.which('node'), 'node is required to verify the delegate-task driver')
class DelegateRuntimeOnly(unittest.TestCase):
    """W7: the delegate-task copy in a host skill folder carries the runtime, not the README images or READMEs."""
    setUp = fixture.WorkflowTests.setUp
    configure = fixture.WorkflowTests.configure
    isolated_skills = __import__('test_delegation').DelegationTests.isolated_skills

    def test_the_installed_copy_has_no_readme_assets_and_still_passes_check_copy(self):
        import delegation
        self.isolated_skills()
        self.assertTrue(delegation.install_skill(self.root, 'codex', 'project')['installed'])
        folder = self.root / '.agents/skills/delegate-task'
        self.assertFalse((folder / 'assets').exists())
        self.assertEqual(list(folder.glob('README*')), [])
        self.assertTrue((folder / 'contracts').is_dir() and (folder / 'references').is_dir())
        self.assertEqual(delegation.check_copy(folder, shutil.which('node')), (None, None))
        self.assertTrue((delegation.bundled_skill() / 'README.md').is_file())  # the package keeps it

if __name__ == '__main__':
    unittest.main()
