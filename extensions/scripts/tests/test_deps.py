"""Tests for extensions/scripts/shared/deps.py (`deps.py ensure illustrate`), which replaces the
verbatim "Ensure the Illustrate dependency" block previously duplicated in the pr and assure
commands (B9). No network access; the `specify` CLI is replaced by a fake runner.
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shared'))
import deps  # noqa: E402


def write_yaml(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def write_registry(root, entries):
    path = root / '.specify/extensions/.registry'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'extensions': entries}), encoding='utf-8')


DEPENDENCIES_YML = """\
schema_version: "1.0"
dependencies:
  - id: illustrate
    version: ">=2.0.0,<3.0.0"
    required_for: "diagram generation"
defaults:
  update_policy: prompt
  check_interval_hours: 24
"""


class FakeRunner:
    """A drop-in replacement for subprocess.run that never touches the network or a real CLI."""

    def __init__(self, script=None, install_result=None):
        self.calls = []
        self.script = script or {}
        self.install_result = install_result

    def __call__(self, args, capture_output=True, text=True, encoding=None):
        self.calls.append(args)
        key = tuple(args[1:])  # drop the leading 'specify'
        if key in self.script:
            return self.script[key]
        if args[1:3] == ['extension', 'add'] or args[1:3] == ['extension', 'update']:
            if self.install_result is not None:
                return self.install_result
            return deps._FakeCompleted(0, '', '')
        if args[1:3] == ['extension', 'info']:
            return deps._FakeCompleted(0, '{}', '')
        return deps._FakeCompleted(0, '', '')


class VersionRangeTests(unittest.TestCase):
    def test_satisfies_within_range(self):
        self.assertTrue(deps.version_satisfies('2.1.2', '>=2.0.0,<3.0.0'))

    def test_fails_below_range(self):
        self.assertFalse(deps.version_satisfies('1.9.9', '>=2.0.0,<3.0.0'))

    def test_fails_at_upper_bound(self):
        self.assertFalse(deps.version_satisfies('3.0.0', '>=2.0.0,<3.0.0'))

    def test_short_forms_pad_with_zero(self):
        self.assertTrue(deps.version_satisfies('3', '>=2.2,<4'))
        self.assertFalse(deps.version_satisfies('2.1', '>=2.2,<4'))

    def test_rejects_malformed_version(self):
        with self.assertRaises(deps.DepsError):
            deps.version_satisfies('not-a-version', '>=2.0.0')

    def test_rejects_malformed_clause(self):
        with self.assertRaises(deps.DepsError):
            deps.version_satisfies('2.0.0', '~=2.0.0')


class EnsurePresentTests(unittest.TestCase):
    """The dependency is already installed, enabled, and in range: 'ensure' must not mutate."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.deps_file = self.root / 'dependencies.yml'
        write_yaml(self.deps_file, DEPENDENCIES_YML)
        write_registry(self.root, {'illustrate': {'version': '2.1.2', 'enabled': True}})

    def tearDown(self):
        self.tmp.cleanup()

    def test_ok_without_touching_specify(self):
        runner = FakeRunner()
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=runner,
                                   skip_catalog_check=True)
        self.assertTrue(ok)
        self.assertIn('ok (installed 2.1.2', message)
        self.assertEqual(runner.calls, [])  # already compatible: no add/update/info call

    def test_records_dependency_check_when_due(self):
        runner = FakeRunner()
        checks_file = self.root / 'checks.json'
        ok, _ = deps.ensure('illustrate', self.root, self.deps_file, checks_file=checks_file,
                             runner=runner, skip_catalog_check=True)
        self.assertTrue(ok)
        recorded = json.loads(checks_file.read_text(encoding='utf-8'))
        self.assertEqual(recorded['illustrate']['installed_version'], '2.1.2')

    def test_skips_catalog_probe_before_interval_elapses(self):
        runner = FakeRunner()
        checks_file = self.root / 'checks.json'
        checks_file.write_text(json.dumps({'illustrate': {
            'checked_at': datetime.now(timezone.utc).isoformat(), 'installed_version': '2.1.2'}}),
            encoding='utf-8')
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, checks_file=checks_file,
                                   runner=runner)
        self.assertTrue(ok)
        self.assertEqual(runner.calls, [])  # within check_interval_hours: no 'extension info' call
        self.assertNotIn('newer', message)

    def test_reports_newer_compatible_release_without_mutating_under_prompt(self):
        runner = FakeRunner(script={('extension', 'info', 'illustrate'):
                                     deps._FakeCompleted(0, json.dumps({'version': '2.5.0'}), '')})
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=runner)
        self.assertTrue(ok)  # still compatible today; the newer release is advisory only
        self.assertIn('newer compatible release 2.5.0', message)
        self.assertNotIn(('extension', 'update', 'illustrate'), [tuple(c[1:]) for c in runner.calls])


class EnsureMissingTests(unittest.TestCase):
    """The dependency is absent; policy must decide whether 'ensure' may mutate the project."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.deps_file = self.root / 'dependencies.yml'
        write_yaml(self.deps_file, DEPENDENCIES_YML)
        # No .registry file at all: illustrate has never been installed.

    def tearDown(self):
        self.tmp.cleanup()

    def test_manual_policy_never_mutates_and_reports_recipe(self):
        write_yaml(self.root / '.specify/extension-dependencies.yml',
                    'update_policy: manual\ncheck_interval_hours: 24\n')
        runner = FakeRunner()
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=runner)
        self.assertFalse(ok)
        self.assertIn('absent', message)
        self.assertIn('run: specify extension add illustrate', message)
        self.assertEqual(runner.calls, [])  # manual: never mutates

    def test_prompt_policy_without_approval_never_mutates(self):
        runner = FakeRunner()
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=runner)
        self.assertFalse(ok)
        self.assertIn('policy prompt', message)
        self.assertIn('run: specify extension add illustrate', message)
        self.assertEqual(runner.calls, [])

    def test_prompt_policy_with_explicit_approval_installs(self):
        write_registry_after_install = self.root

        def install_then_register(args, capture_output=True, text=True, encoding=None):
            if args[1:3] == ['extension', 'add']:
                write_registry(write_registry_after_install, {'illustrate': {'version': '2.1.2', 'enabled': True}})
                return deps._FakeCompleted(0, '', '')
            return deps._FakeCompleted(0, '{}', '')

        ok, message = deps.ensure('illustrate', self.root, self.deps_file, approve=True,
                                   runner=install_then_register, skip_catalog_check=True)
        self.assertTrue(ok)
        self.assertIn('ok (installed 2.1.2', message)

    def test_auto_policy_installs_without_approval(self):
        write_yaml(self.root / '.specify/extension-dependencies.yml', 'update_policy: auto\n')

        def install_then_register(args, capture_output=True, text=True, encoding=None):
            if args[1:3] == ['extension', 'add']:
                write_registry(self.root, {'illustrate': {'version': '2.1.2', 'enabled': True}})
                return deps._FakeCompleted(0, '', '')
            return deps._FakeCompleted(0, '{}', '')

        ok, message = deps.ensure('illustrate', self.root, self.deps_file,
                                   runner=install_then_register, skip_catalog_check=True)
        self.assertTrue(ok)
        self.assertIn('ok (installed 2.1.2', message)


class EnsureFailureTests(unittest.TestCase):
    """Installed but out of range, or the mutating command itself fails: 'ensure' must fail closed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.deps_file = self.root / 'dependencies.yml'
        write_yaml(self.deps_file, DEPENDENCIES_YML)
        write_yaml(self.root / '.specify/extension-dependencies.yml', 'update_policy: auto\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_disabled_entry_is_reported_before_any_mutation_under_manual(self):
        write_yaml(self.root / '.specify/extension-dependencies.yml', 'update_policy: manual\n')
        write_registry(self.root, {'illustrate': {'version': '2.1.2', 'enabled': False}})
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=FakeRunner())
        self.assertFalse(ok)
        self.assertIn('disabled', message)
        self.assertIn('run: specify extension update illustrate', message)

    def test_out_of_range_entry_recipe_is_update_not_add(self):
        write_yaml(self.root / '.specify/extension-dependencies.yml', 'update_policy: manual\n')
        write_registry(self.root, {'illustrate': {'version': '1.5.0', 'enabled': True}})
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=FakeRunner())
        self.assertFalse(ok)
        self.assertIn('outside >=2.0.0,<3.0.0', message)
        self.assertIn('run: specify extension update illustrate', message)

    def test_install_command_exits_nonzero(self):
        write_registry(self.root, {})
        runner = FakeRunner(install_result=deps._FakeCompleted(1, '', 'network unreachable'))
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=runner,
                                   skip_catalog_check=True)
        self.assertFalse(ok)
        self.assertIn('did not produce a compatible install', message)
        self.assertIn('exit 1', message)
        self.assertIn('network unreachable', message)

    def test_install_reports_success_but_registry_still_incompatible(self):
        # 'specify' exits 0 but the registry was not actually updated (e.g. a stale cache):
        # ensure must not report ok on the strength of the exit code alone.
        write_registry(self.root, {'illustrate': {'version': '1.0.0', 'enabled': True}})
        runner = FakeRunner(install_result=deps._FakeCompleted(0, 'updated', ''))
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=runner,
                                   skip_catalog_check=True)
        self.assertFalse(ok)
        self.assertIn('did not produce a compatible install', message)

    def test_missing_dependency_declaration(self):
        write_yaml(self.deps_file, 'schema_version: "1.0"\ndependencies: []\n')
        write_registry(self.root, {'illustrate': {'version': '2.1.2', 'enabled': True}})
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=FakeRunner())
        self.assertFalse(ok)
        self.assertIn('no dependency declaration', message)


class MainCliTests(unittest.TestCase):
    """The CLI entry point prints exactly one line and returns the documented exit codes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.deps_file = self.root / 'dependencies.yml'
        write_yaml(self.deps_file, DEPENDENCIES_YML)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exit_zero_when_present(self, capsys=None):
        write_registry(self.root, {'illustrate': {'version': '2.1.2', 'enabled': True}})
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = deps.main(['ensure', 'illustrate', '--root', str(self.root),
                               '--dependencies-file', str(self.deps_file), '--skip-catalog-check'])
        self.assertEqual(code, 0)
        lines = buffer.getvalue().strip('\n').split('\n')
        self.assertEqual(len(lines), 1)
        self.assertIn('ok (installed 2.1.2', lines[0])

    def test_exit_nonzero_when_missing(self):
        write_yaml(self.root / '.specify/extension-dependencies.yml', 'update_policy: manual\n')
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = deps.main(['ensure', 'illustrate', '--root', str(self.root),
                               '--dependencies-file', str(self.deps_file)])
        self.assertEqual(code, 1)
        lines = buffer.getvalue().strip('\n').split('\n')
        self.assertEqual(len(lines), 1)
        self.assertIn('run: specify extension add illustrate', lines[0])


if __name__ == '__main__':
    unittest.main()
