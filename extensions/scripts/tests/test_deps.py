"""Tests for extensions/scripts/shared/deps.py (`deps.py ensure illustrate`), which replaces the
verbatim "Ensure the Illustrate dependency" block previously duplicated in the pr and assure
commands (B9). No network access; the `specify` CLI is replaced by a fake runner.
"""
import json
import subprocess
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

# The real, plain-text `specify extension info <id>` output (specify_cli 1.0.11, the commit
# pinned in .github/workflows/ci.yml: 8147943512404afb9d99c6252cb9bf84369fd0b0). Captured by
# driving `specify_cli.extensions.command_info` through Typer's CliRunner with a mocked catalog
# entry: there is no --json option, and Rich renders plain text (no ANSI/markup) when stdout is
# not a tty, exactly as it is here under subprocess.PIPE.
def real_info_text(name='Illustrate', version='2.5.0', installed=True):
    lines = ['', name + ' (v' + version + ')', 'ID: illustrate', '', 'Diagrams.', '',
             'Author: Unknown', 'License: Unknown', '', 'Links:', '']
    if installed:
        lines += ['✓ Installed', 'Priority: 10', '', 'To remove: specify extension remove illustrate']
    return '\n'.join(lines) + '\n'


class FakeRunner:
    """A drop-in replacement for subprocess.run that never touches the network or a real CLI."""

    def __init__(self, script=None, install_result=None, raise_on=None):
        self.calls = []
        self.script = script or {}
        self.install_result = install_result
        self.raise_on = raise_on or {}

    def __call__(self, args, **kwargs):
        key = tuple(args[1:])  # drop the leading 'specify'
        self.calls.append({'args': args, 'kwargs': kwargs})
        if key in self.raise_on:
            raise self.raise_on[key]
        if key in self.script:
            return self.script[key]
        if args[1:3] == ['extension', 'add'] or args[1:3] == ['extension', 'update']:
            if self.install_result is not None:
                return self.install_result
            return deps._FakeCompleted(0, '', '')
        if args[1:3] == ['extension', 'info']:
            return deps._FakeCompleted(0, real_info_text(version='2.1.2'), '')
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
            deps.version_satisfies('2.0.0', '$=2.0.0')

    def test_space_separated_clauses(self):
        self.assertTrue(deps.version_satisfies('2.1.2', '>=2.0.0 <3.0.0'))
        self.assertFalse(deps.version_satisfies('3.0.0', '>=2.0.0 <3.0.0'))

    def test_v_prefix_on_installed_and_bound(self):
        self.assertTrue(deps.version_satisfies('v2.1.2', '>=v2.0.0,<v3.0.0'))

    def test_release_outranks_its_own_prereleases(self):
        # A release has higher precedence than any of its own pre-releases (only exercised when
        # the installed side has no pre-release tag, so the npm eligibility gate below does not
        # apply to it).
        self.assertTrue(deps.version_satisfies('2.1.0', '>=2.1.0-beta.1'))

    def test_prerelease_never_satisfies_a_plain_range_even_numerically_inside_it(self):
        # npm-semver rule, reproduced findings: a pre-release only satisfies a range if some
        # comparator shares its exact major.minor.patch AND itself carries a pre-release tag.
        # '>=2.0.0,<3.0.0' has neither, so no pre-release of any version satisfies it — including
        # one numerically inside the range ('2.5.0-rc.1') and one at the excluded upper bound's
        # own tuple ('3.0.0-rc.1'), both of which used to incorrectly satisfy it.
        self.assertFalse(deps.version_satisfies('3.0.0-rc.1', '>=2.0.0,<3.0.0'))
        self.assertFalse(deps.version_satisfies('2.5.0-rc.1', '>=2.0.0,<3.0.0'))
        self.assertFalse(deps.version_satisfies('2.1.0-beta.1', '>=2.0.0,<2.1.0'))
        self.assertFalse(deps.version_satisfies('2.1.0-beta.1', '>=2.1.0'))

    def test_prerelease_satisfies_a_range_that_explicitly_grants_its_own_tuple(self):
        # The npm-semver counter-example: a range comparator with the SAME major.minor.patch and
        # its own pre-release tag does admit a pre-release.
        self.assertTrue(deps.version_satisfies('1.2.3-alpha.7', '>=1.2.3-alpha.1,<1.3.0'))
        self.assertFalse(deps.version_satisfies('1.2.3-alpha.0', '>=1.2.3-alpha.1,<1.3.0'))
        # A different tuple than any comparator's bound still never qualifies.
        self.assertFalse(deps.version_satisfies('1.2.4-alpha.7', '>=1.2.3-alpha.1,<1.3.0'))

    def test_build_metadata_is_ignored_for_precedence(self):
        self.assertTrue(deps.version_satisfies('2.1.2+build.5', '>=2.1.2,<3.0.0'))
        self.assertEqual(deps.compare_versions('2.1.2+build.1', '2.1.2+build.2'), 0)

    def test_caret_operator(self):
        self.assertTrue(deps.version_satisfies('2.9.9', '^2.0.0'))
        self.assertFalse(deps.version_satisfies('3.0.0', '^2.0.0'))
        self.assertFalse(deps.version_satisfies('1.9.9', '^2.0.0'))

    def test_tilde_equals_operator(self):
        self.assertTrue(deps.version_satisfies('2.2.9', '~=2.2'))
        self.assertFalse(deps.version_satisfies('3.0.0', '~=2.2'))
        self.assertTrue(deps.version_satisfies('2.2.5', '~=2.2.0'))
        self.assertFalse(deps.version_satisfies('2.3.0', '~=2.2.0'))


class CatalogVersionTests(unittest.TestCase):
    """`specify extension info` prints plain text, not JSON (no --json option exists)."""

    def test_parses_real_text_header(self):
        runner = FakeRunner(script={('extension', 'info', 'illustrate'):
                                     deps._FakeCompleted(0, real_info_text(version='2.5.0'), '')})
        self.assertEqual(deps.catalog_version('illustrate', runner), '2.5.0')

    def test_parses_prerelease_header(self):
        runner = FakeRunner(script={('extension', 'info', 'illustrate'):
                                     deps._FakeCompleted(0, real_info_text(version='2.6.0-beta.1'), '')})
        self.assertEqual(deps.catalog_version('illustrate', runner), '2.6.0-beta.1')

    def test_json_stdout_is_not_understood_as_a_version(self):
        # Regression guard: a fake runner that "helpfully" returns JSON (as the pre-fix tests
        # did) must not be mistaken for the real CLI's plain-text output.
        runner = FakeRunner(script={('extension', 'info', 'illustrate'):
                                     deps._FakeCompleted(0, json.dumps({'version': '9.9.9'}), '')})
        self.assertIsNone(deps.catalog_version('illustrate', runner))

    def test_nonzero_exit_returns_none(self):
        runner = FakeRunner(script={('extension', 'info', 'illustrate'):
                                     deps._FakeCompleted(1, '', "Error: Extension 'illustrate' not found")})
        self.assertIsNone(deps.catalog_version('illustrate', runner))

    def test_unparseable_header_returns_none_not_raise(self):
        runner = FakeRunner(script={('extension', 'info', 'illustrate'):
                                     deps._FakeCompleted(0, '\nIllustrate (vlatest)\n', '')})
        self.assertIsNone(deps.catalog_version('illustrate', runner))


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

    def test_skipped_probe_never_writes_checks_file(self):
        runner = FakeRunner()
        checks_file = self.root / 'checks.json'
        ok, _ = deps.ensure('illustrate', self.root, self.deps_file, checks_file=checks_file,
                             runner=runner, skip_catalog_check=True)
        self.assertTrue(ok)
        self.assertFalse(checks_file.exists())  # nothing was actually checked

    def test_records_dependency_check_on_a_successful_probe(self):
        runner = FakeRunner(script={('extension', 'info', 'illustrate'):
                                     deps._FakeCompleted(0, real_info_text(version='2.1.2'), '')})
        checks_file = self.root / 'checks.json'
        ok, _ = deps.ensure('illustrate', self.root, self.deps_file, checks_file=checks_file, runner=runner)
        self.assertTrue(ok)
        recorded = json.loads(checks_file.read_text(encoding='utf-8'))
        self.assertEqual(recorded['illustrate']['installed_version'], '2.1.2')

    def test_failed_probe_does_not_write_checks_file(self):
        # The probe ran but told us nothing (not found / bad output): don't stamp checked_at,
        # or a working install would look "recently checked" without having learned anything.
        runner = FakeRunner(script={('extension', 'info', 'illustrate'):
                                     deps._FakeCompleted(1, '', 'boom')})
        checks_file = self.root / 'checks.json'
        ok, _ = deps.ensure('illustrate', self.root, self.deps_file, checks_file=checks_file, runner=runner)
        self.assertTrue(ok)  # the dependency itself is still fine
        self.assertFalse(checks_file.exists())

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
                                     deps._FakeCompleted(0, real_info_text(version='2.5.0'), '')})
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=runner)
        self.assertTrue(ok)  # still compatible today; the newer release is advisory only
        self.assertIn('newer compatible release 2.5.0', message)
        self.assertNotIn(('extension', 'update', 'illustrate'), [tuple(c['args'][1:]) for c in runner.calls])

    def test_prerelease_catalog_version_is_never_reported_as_newer(self):
        # A pre-release catalog release must never be surfaced as "newer" — only a stable
        # compatible release should be. (It also happens to no longer raise: a still-unparseable
        # format is separately covered by test_unparseable_catalog_version_is_ignored_not_fatal.)
        runner = FakeRunner(script={('extension', 'info', 'illustrate'):
                                     deps._FakeCompleted(0, real_info_text(version='2.6.0-beta.1'), '')})
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=runner)
        self.assertTrue(ok)
        self.assertNotIn('newer', message)

    def test_unparseable_catalog_version_is_ignored_not_fatal(self):
        runner = FakeRunner(script={('extension', 'info', 'illustrate'):
                                     deps._FakeCompleted(0, '\nIllustrate (vlatest)\n', '')})
        checks_file = self.root / 'checks.json'
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, checks_file=checks_file, runner=runner)
        self.assertTrue(ok)
        self.assertNotIn('newer', message)
        self.assertFalse(checks_file.exists())  # catalog_version() already returned None: not "checked"

    def test_info_probe_is_never_given_input_or_open_stdin(self):
        runner = FakeRunner()
        deps.ensure('illustrate', self.root, self.deps_file, runner=runner)
        info_calls = [c for c in runner.calls if c['args'][1:3] == ['extension', 'info']]
        self.assertEqual(len(info_calls), 1)
        self.assertNotIn('input', info_calls[0]['kwargs'])
        self.assertEqual(info_calls[0]['kwargs'].get('stdin'), subprocess.DEVNULL)

    def test_auto_policy_never_auto_installs_a_prerelease_catalog_candidate(self):
        # Reproduced bug: under 'auto', a pre-release catalog version ('3.0.0-rc.1') was treated
        # as "newer" and auto-installed via 'specify extension update'. It must never be.
        write_yaml(self.root / '.specify/extension-dependencies.yml', 'update_policy: auto\n')
        runner = FakeRunner(script={('extension', 'info', 'illustrate'):
                                     deps._FakeCompleted(0, real_info_text(version='3.0.0-rc.1'), '')})
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=runner)
        self.assertTrue(ok)
        self.assertNotIn('newer', message)
        update_calls = [c for c in runner.calls if c['args'][1:3] == ['extension', 'update']]
        self.assertEqual(update_calls, [])


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
        def install_then_register(args, **kwargs):
            if args[1:3] == ['extension', 'add']:
                write_registry(self.root, {'illustrate': {'version': '2.1.2', 'enabled': True}})
                return deps._FakeCompleted(0, '', '')
            return deps._FakeCompleted(0, '', '')

        ok, message = deps.ensure('illustrate', self.root, self.deps_file, approve=True,
                                   runner=install_then_register, skip_catalog_check=True)
        self.assertTrue(ok)
        self.assertIn('ok (installed 2.1.2', message)

    def test_auto_policy_installs_without_approval(self):
        write_yaml(self.root / '.specify/extension-dependencies.yml', 'update_policy: auto\n')

        def install_then_register(args, **kwargs):
            if args[1:3] == ['extension', 'add']:
                write_registry(self.root, {'illustrate': {'version': '2.1.2', 'enabled': True}})
                return deps._FakeCompleted(0, '', '')
            return deps._FakeCompleted(0, '', '')

        ok, message = deps.ensure('illustrate', self.root, self.deps_file,
                                   runner=install_then_register, skip_catalog_check=True)
        self.assertTrue(ok)
        self.assertIn('ok (installed 2.1.2', message)

    def test_add_is_never_given_input_but_closes_stdin(self):
        runner = FakeRunner()
        deps.ensure('illustrate', self.root, self.deps_file, approve=True, runner=runner,
                     skip_catalog_check=True)
        add_calls = [c for c in runner.calls if c['args'][1:3] == ['extension', 'add']]
        self.assertEqual(len(add_calls), 1)
        self.assertNotIn('input', add_calls[0]['kwargs'])
        self.assertEqual(add_calls[0]['kwargs'].get('stdin'), subprocess.DEVNULL)


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

    def test_update_is_given_yes_input_not_an_open_inherited_stdin(self):
        write_registry(self.root, {'illustrate': {'version': '1.0.0', 'enabled': True}})
        runner = FakeRunner()
        deps.ensure('illustrate', self.root, self.deps_file, runner=runner, skip_catalog_check=True)
        update_calls = [c for c in runner.calls if c['args'][1:3] == ['extension', 'update']]
        self.assertEqual(len(update_calls), 1)
        self.assertEqual(update_calls[0]['kwargs'].get('input'), 'y\n')
        self.assertNotIn('stdin', update_calls[0]['kwargs'])  # input= and stdin= are mutually exclusive

    def test_timeout_expired_is_a_failure_not_an_exception(self):
        write_registry(self.root, {})
        runner = FakeRunner(raise_on={('extension', 'add', 'illustrate'):
                                       subprocess.TimeoutExpired(cmd=['specify'], timeout=5)})
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, runner=runner,
                                   skip_catalog_check=True, timeout=5)
        self.assertFalse(ok)
        self.assertIn('did not produce a compatible install', message)
        self.assertIn('exit 124', message)

    def test_every_call_gets_a_timeout(self):
        write_registry(self.root, {})
        runner = FakeRunner()
        deps.ensure('illustrate', self.root, self.deps_file, runner=runner, skip_catalog_check=True)
        self.assertTrue(runner.calls)
        for call in runner.calls:
            self.assertIn('timeout', call['kwargs'])
            self.assertIsNotNone(call['kwargs']['timeout'])


class PolicyValidationTests(unittest.TestCase):
    """N1: an inline comment must not silently corrupt `update_policy`, and an actually invalid
    value must raise rather than silently fall back to 'prompt' (which a mutating --approve could
    then act on)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.deps_file = self.root / 'dependencies.yml'
        write_yaml(self.deps_file, DEPENDENCIES_YML)
        # No .registry file: illustrate is absent, so 'ensure' must decide whether to mutate.

    def tearDown(self):
        self.tmp.cleanup()

    def test_comment_after_manual_policy_is_stripped_not_folded_into_the_value(self):
        # Reproduced bug: 'manual  # never mutate' parsed as the literal value
        # 'manual  # never mutate', which is not in {prompt, auto, manual}, so it silently fell
        # back to 'prompt' — and a subsequent --approve then mutated a project whose author wrote
        # 'manual' specifically to forbid that.
        write_yaml(self.root / '.specify/extension-dependencies.yml',
                    'update_policy: manual  # never mutate\ncheck_interval_hours: 24\n')
        runner = FakeRunner()
        ok, message = deps.ensure('illustrate', self.root, self.deps_file, approve=True, runner=runner)
        self.assertFalse(ok)
        self.assertIn('policy manual', message)
        self.assertEqual(runner.calls, [])  # still never mutates, even with --approve

    def test_hash_inside_a_quoted_value_is_preserved_not_treated_as_a_comment(self):
        path = self.root / 'quoted.yml'
        write_yaml(path, 'required_for: "diagram generation #1"  # trailing note\n')
        data = deps.read_yaml(path)
        self.assertEqual(data['required_for'], 'diagram generation #1')

    def test_full_line_comment_and_blank_lines_still_skipped(self):
        path = self.root / 'commented.yml'
        write_yaml(path, '# a full-line comment\n\nupdate_policy: auto\n')
        self.assertEqual(deps.read_yaml(path), {'update_policy': 'auto'})

    def test_unknown_update_policy_raises_instead_of_defaulting_to_prompt(self):
        write_yaml(self.root / '.specify/extension-dependencies.yml', 'update_policy: bogus\n')
        runner = FakeRunner()
        with self.assertRaises(deps.DepsError):
            deps.ensure('illustrate', self.root, self.deps_file, approve=True, runner=runner)
        self.assertEqual(runner.calls, [])  # raised before any mutation was even considered


class ReadYamlTests(unittest.TestCase):
    """The narrow dependencies.yml/extension-dependencies.yml reader, tested against the real
    files of all three consuming packages (no PyYAML: nothing installs requirements.txt)."""

    ROOT = Path(__file__).resolve().parents[3]

    def test_reads_pr_dependencies_yml(self):
        data = deps.read_yaml(self.ROOT / 'extensions/pr/dependencies.yml')
        ids = {entry['id']: entry for entry in data['dependencies']}
        self.assertEqual(ids['illustrate']['version'], '>=2.0.0,<3.0.0')
        self.assertEqual(ids['assure']['optional'], True)
        self.assertEqual(data['defaults']['update_policy'], 'prompt')
        self.assertEqual(data['defaults']['check_interval_hours'], 24)

    def test_reads_assure_dependencies_yml(self):
        data = deps.read_yaml(self.ROOT / 'extensions/assure/dependencies.yml')
        ids = {entry['id']: entry for entry in data['dependencies']}
        self.assertEqual(ids['illustrate']['version'], '>=2.0.0,<3.0.0')
        self.assertEqual(data['defaults']['check_interval_hours'], 24)

    def test_reads_user_manual_dependencies_yml(self):
        data = deps.read_yaml(self.ROOT / 'extensions/user-manual/dependencies.yml')
        ids = {entry['id']: entry for entry in data['dependencies']}
        self.assertEqual(ids['illustrate']['version'], '>=2.0.0,<3.0.0')
        self.assertEqual(data['defaults']['update_policy'], 'prompt')
        # Exactly one 'defaults' key: a duplicate block would silently keep only the last one,
        # which is indistinguishable here, so assert the file's raw text has no duplicate too.
        text = (self.ROOT / 'extensions/user-manual/dependencies.yml').read_text(encoding='utf-8')
        self.assertEqual(text.count('defaults:'), 1)

    def test_reads_flat_policy_override_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'extension-dependencies.yml'
            write_yaml(path, 'update_policy: manual\ncheck_interval_hours: 48\n')
            data = deps.read_yaml(path)
            self.assertEqual(data, {'update_policy': 'manual', 'check_interval_hours': 48})

    def test_missing_file_returns_default(self):
        self.assertEqual(deps.read_yaml(Path('/does/not/exist.yml'), default={}), {})

    def test_rejects_unsupported_construct(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'weird.yml'
            write_yaml(path, 'not_a_mapping_line\n')
            with self.assertRaises(deps.DepsError):
                deps.read_yaml(path)

    def test_tab_in_leading_whitespace_raises(self):
        # Reproduced bug: a tab wasn't counted as indentation, so the child line was read as
        # indent 0 and "lifted" to the top level instead of nesting under 'defaults:'.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'tabbed.yml'
            write_yaml(path, 'defaults:\n\tupdate_policy: auto\n')
            with self.assertRaises(deps.DepsError):
                deps.read_yaml(path)

    def test_duplicate_top_level_key_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'dup.yml'
            write_yaml(path, 'update_policy: prompt\nupdate_policy: auto\n')
            with self.assertRaises(deps.DepsError):
                deps.read_yaml(path)

    def test_duplicate_key_within_a_list_item_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'dup_item.yml'
            write_yaml(path, 'dependencies:\n  - id: illustrate\n    version: ">=1,<2"\n    version: ">=2,<3"\n')
            with self.assertRaises(deps.DepsError):
                deps.read_yaml(path)

    def test_quoted_key_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'quoted_key.yml'
            write_yaml(path, '"update_policy": auto\n')
            with self.assertRaises(deps.DepsError):
                deps.read_yaml(path)

    def test_flow_list_value_raises_instead_of_crashing(self):
        # Reproduced bug: 'dependencies: [{id: x}]' parsed as the literal string '[{id: x}]',
        # and iterating a dependency lookup over that string later crashed with
        # AttributeError ('str' object has no attribute 'get') instead of a clear error here.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'flow.yml'
            write_yaml(path, 'dependencies: [{id: x}]\n')
            with self.assertRaises(deps.DepsError):
                deps.read_yaml(path)

    def test_unbalanced_quote_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'unbalanced.yml'
            write_yaml(path, 'version: ">=2.0.0,<3.0.0\n')
            with self.assertRaises(deps.DepsError):
                deps.read_yaml(path)

    def test_dependencies_must_be_a_list_of_mappings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'not_a_list.yml'
            write_yaml(path, 'dependencies: illustrate\n')
            with self.assertRaises(deps.DepsError):
                deps.dependency_declaration(path, 'illustrate')

    def test_list_item_error_reports_its_own_line_number_not_the_parent_key_line(self):
        # Reproduced bug: the malformed item's own "- ..." line raised with the *parent*
        # 'dependencies:' key's line number (line 1) instead of its own (line 4).
        path_text = (
            'dependencies:\n'                     # line 1 (the parent key)
            '  - id: illustrate\n'                 # line 2
            '    version: ">=2.0.0,<3.0.0"\n'      # line 3
            '  - not_a_field_without_a_colon\n'    # line 4: malformed item body, no ':'
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'lineno.yml'
            write_yaml(path, path_text)
            with self.assertRaises(deps.DepsError) as ctx:
                deps.read_yaml(path)
            self.assertIn('line 4', str(ctx.exception))
            self.assertNotIn('line 1', str(ctx.exception))


class MainCliTests(unittest.TestCase):
    """The CLI entry point prints exactly one line and returns the documented exit codes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.deps_file = self.root / 'dependencies.yml'
        write_yaml(self.deps_file, DEPENDENCIES_YML)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exit_zero_when_present(self):
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
