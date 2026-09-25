import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import install as installer
import workflow as w
import test_workflow as fixture


class InstallTests(unittest.TestCase):
    configure = fixture.WorkflowTests.configure

    def setUp(self):
        fixture.WorkflowTests.setUp(self)
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.package = Path(temporary.name).resolve()
        source = Path(__file__).resolve().parents[1]
        shutil.copyfile(source / 'dependencies.json', self.package / 'dependencies.json')
        shutil.copytree(source / 'skills', self.package / 'skills')
        shutil.copytree(source / 'assets', self.package / 'assets')
        for name in ('scope-gate', 'scope-brainstorm', 'workflow'):
            p = self.package / 'presets' / name / 'preset.yml'
            p.parent.mkdir(parents=True); p.write_text('schema_version: "1.0"', encoding='utf-8')

    def version(self, name, value, enabled=True):
        registry = w.registry(self.root); registry[name].update(version=value, enabled=enabled)
        w.write(self.root / '.specify/extensions/.registry', {'extensions': registry})

    def test_disabled_gate_installs_no_job_and_removes_only_managed_job(self):
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        with patch.object(installer, 'install_aliases', return_value={}), \
             patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}), \
             patch.object(installer, 'required_gate_checks', return_value=[]):
            installer.install(self.root, apply=True, package_root=self.package, runner=lambda *args: None)
            self.assertTrue(target.is_file())
            self.policy['ci']['gate']['mode'] = 'disabled'
            self.configure()
            result = installer.install(self.root, apply=True, package_root=self.package, runner=lambda *args: None)
            self.assertEqual(result['gate']['mode'], 'disabled')
            self.assertFalse(target.exists())

    def test_disabled_gate_refuses_stale_required_branch_check(self):
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((self.package / 'assets/github/workflow-gates.yml').read_bytes())
        self.policy['ci']['gate']['mode'] = 'disabled'
        self.configure()
        with patch.object(installer, 'required_gate_checks', return_value=['workflow-evidence']):
            with self.assertRaisesRegex(w.WorkflowError, 'CI_GATE_REQUIRED_BY_BRANCH_RULE'):
                installer.install(self.root, apply=True, package_root=self.package,
                                  runner=lambda *args: None)
        self.assertTrue(target.is_file())

    def test_provider_none_installs_no_managed_gate_job(self):
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        self.policy['ci']['provider'] = 'none'
        self.configure()
        with patch.object(installer, 'install_aliases', return_value={}), \
             patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}):
            result = installer.install(self.root, apply=True, package_root=self.package,
                                       runner=lambda *args: None)
        self.assertTrue(result['applied'])
        self.assertFalse(target.exists())

    def test_branch_rule_inspection_covers_ruleset_and_legacy_protection(self):
        def api(args, **kwargs):
            endpoint = args[2]
            if endpoint == 'repos/acme/app':
                value = {'default_branch': 'main'}
            elif '/rules/branches/' in endpoint:
                value = [{'type': 'required_status_checks', 'parameters': {
                    'required_status_checks': [{'context': 'workflow-evidence'}]}}]
            else:
                value = {'contexts': ['Sanduq workflow gates / workflow-evidence']}
            return subprocess.CompletedProcess(args, 0, json.dumps(value), '')
        with patch.object(installer.subprocess, 'run', side_effect=api), \
             patch.object(installer, 'github_repository', return_value='acme/app'):
            self.assertEqual(installer.required_gate_checks(self.root),
                             ['Sanduq workflow gates / workflow-evidence', 'workflow-evidence'])

    def test_disabled_gate_refuses_to_claim_custom_preserved_workflow_is_off(self):
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('name: Custom gate\n', encoding='utf-8')
        self.policy['ci']['gate']['mode'] = 'disabled'
        self.configure()
        with patch.object(installer, 'install_aliases', return_value={}), \
             patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}):
            with self.assertRaisesRegex(w.WorkflowError, 'CI_GATE_DISABLED_PRESERVED_FILE_CONFLICT'):
                installer.install(self.root, apply=True, package_root=self.package,
                                  runner=lambda *args: None, preserve_ci=True)
        self.assertEqual(target.read_text(encoding='utf-8'), 'name: Custom gate\n')

    def test_ci_checkout_conversion_survives_installer_rerun_and_asset_upgrade(self):
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        asset = self.package / 'assets/github/workflow-gates.yml'
        for original, converted in ((b'name: CI\non: pull_request\n', b'name: CI\r\non: pull_request\r\n'),
                                    (b'name: CI\r\non: pull_request\r\n', b'name: CI\non: pull_request\n')):
            with self.subTest(original=original):
                asset.write_bytes(original)
                # Exercise the real transaction; external CLI and fixture-only
                # command registrations are outside this regression's scope.
                with patch.object(installer, 'install_aliases', return_value={}), \
                     patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}):
                    installer.install(self.root, apply=True, package_root=self.package, runner=lambda *args: None)
                    receipt_path = self.root / '.specify/workflow/install-receipt.json'
                    receipt = w.read(receipt_path)
                    receipt['ci_sha256'] = hashlib.sha256(original).hexdigest()
                    w.write(receipt_path, receipt)
                    target.write_bytes(converted)
                    installer.install(self.root, apply=True, package_root=self.package, runner=lambda *args: None)
                    self.assertEqual(target.read_bytes(), original)
                    # A new release changes the asset; the historical raw hash
                    # must still recognize an unedited, converted predecessor.
                    w.write(receipt_path, receipt)
                    target.write_bytes(converted)
                    asset.write_bytes(b'name: Updated CI\non: pull_request\n')
                    installer.install(self.root, apply=True, package_root=self.package, runner=lambda *args: None)
                    self.assertEqual(target.read_bytes(), asset.read_bytes())
                target.unlink()

    def test_ci_semantic_edits_still_roll_back_without_overwrite(self):
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        target.parent.mkdir(parents=True, exist_ok=True)
        original = b'name: CI\non: pull_request\n'
        edited = b'name: CI\r\non: push\r\n'
        target.write_bytes(edited)
        w.write(self.root / '.specify/workflow/install-receipt.json',
                {'ci_sha256': hashlib.sha256(original).hexdigest()})
        with patch.object(installer, 'install_aliases', return_value={}), \
             patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}):
            with self.assertRaisesRegex(w.WorkflowError, 'CI_WORKFLOW_HAS_LOCAL_EDITS'):
                installer.install(self.root, apply=True, package_root=self.package, runner=lambda *args: None)
        self.assertEqual(target.read_bytes(), edited)

    def test_ci_guard_preserves_whitespace_and_lone_carriage_return_edits(self):
        original = b'name: CI\non: pull_request\n'
        receipt = {'ci_sha256': hashlib.sha256(original).hexdigest()}
        for edited in (b'name: CI \non: pull_request\n', b'name: CI\ron: pull_request\n',
                       b'name: CI\non: pull_request', b'name: CI\n on: pull_request\n'):
            with self.subTest(edited=edited):
                self.assertFalse(installer.ci_matches_managed(edited, original, receipt))

    def test_explicit_preserve_ci_keeps_custom_policy_without_blessing_it_as_managed(self):
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        target.parent.mkdir(parents=True, exist_ok=True)
        custom = b'name: Local policy\r\njobs:\r\n  check:\r\n    runs-on: homek8\r\n'
        target.write_bytes(custom)
        with patch.object(installer, 'install_aliases', return_value={}), \
             patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}):
            result = installer.install(self.root, apply=True, package_root=self.package,
                                       runner=lambda *args: None, preserve_ci=True)
            self.assertEqual(target.read_bytes(), custom)
            self.assertEqual(result['preserved_ci'], {
                'path': '.github/workflows/sanduq-workflow-gates.yml',
                'sha256': hashlib.sha256(custom).hexdigest()})
            self.assertEqual(w.read(self.root / '.specify/workflow/install-receipt.json')['preserved_ci'], result['preserved_ci'])
            # A later invocation without the explicit choice must still protect
            # this consumer policy from replacement by the bundled template.
            with self.assertRaisesRegex(w.WorkflowError, 'CI_WORKFLOW_HAS_LOCAL_EDITS'):
                installer.install(self.root, apply=True, package_root=self.package, runner=lambda *args: None)
            self.assertEqual(target.read_bytes(), custom)

    def test_preserve_ci_passes_health_check_on_a_checkout_without_a_receipt(self):
        # Issue #22: the receipt is git-excluded, so a fresh clone or worktree
        # has none. The health check runs before it is written and must still
        # know the preserved file belongs to the project.
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'name: Local policy\njobs: {}\n')
        asset = self.root / '.specify/extensions/workflow/assets/github/workflow-gates.yml'
        asset.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.package / 'assets/github/workflow-gates.yml', asset)
        self.assertFalse((self.root / '.specify/workflow/install-receipt.json').exists())

        def health(root, policy, project=False, preserved_ci=None):
            errors = w.ci_errors(root, policy, preserved_ci)
            return {'ok': not errors, 'errors': errors}
        with patch.object(installer, 'install_aliases', return_value={}),              patch.object(installer, 'doctor', side_effect=health):
            result = installer.install(self.root, apply=True, package_root=self.package,
                                       runner=lambda *args: None, preserve_ci=True)
        self.assertEqual(result['preserved_ci']['path'], '.github/workflows/sanduq-workflow-gates.yml')
        # The tracked lock carries the choice to every other checkout.
        lock = w.read(self.root / '.specify/workflow/install-lock.json')
        self.assertEqual(lock['preserved_ci'], {'path': '.github/workflows/sanduq-workflow-gates.yml'})
        (self.root / '.specify/workflow/install-receipt.json').unlink()
        self.assertEqual(w.ci_errors(self.root, w.load_policy(self.root)), [])

    def test_preserve_ci_still_installs_template_when_project_has_no_ci_file(self):
        with patch.object(installer, 'install_aliases', return_value={}), \
             patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}):
            result = installer.install(self.root, apply=True, package_root=self.package,
                                       runner=lambda *args: None, preserve_ci=True)
        self.assertIsNone(result['preserved_ci'])
        # What lands in the project is the template rendered for its CI selection.
        self.assertEqual((self.root / '.github/workflows/sanduq-workflow-gates.yml').read_bytes(),
                         installer.rendered(self.package / 'assets/github/workflow-gates.yml',
                                            w.load_policy(self.root)))

    def test_newer_compatible_package_is_retained_without_downgrade(self):
        self.version('pr', '4.2.0')
        result = installer.install(self.root, package_root=self.package)
        self.assertEqual(result['retained_newer'][0]['extension'], 'pr')
        self.assertNotIn('pr', [op['extension'] for op in result['extensions']])

    def test_newer_incompatible_or_disabled_package_requires_resolution(self):
        self.version('pr', '5.0.0')
        with self.assertRaisesRegex(w.WorkflowError, 'NEWER_DEPENDENCY_INCOMPATIBLE'):
            installer.install(self.root, package_root=self.package)
        self.version('pr', '4.2.0', enabled=False)
        with self.assertRaisesRegex(w.WorkflowError, 'NEWER_DEPENDENCY_DISABLED'):
            installer.install(self.root, package_root=self.package)

    def test_unrelated_scope_package_cannot_be_overwritten(self):
        p = self.root / '.specify/extensions/scope/extension.yml'
        manifest = yaml.safe_load(p.read_text(encoding='utf-8'))
        manifest['extension']['repository'] = 'https://github.com/unrelated/scope'
        p.write_text(yaml.safe_dump(manifest), encoding='utf-8')
        with self.assertRaisesRegex(w.WorkflowError, 'SOURCE_CONFLICT'):
            installer.install(self.root, package_root=self.package)

    def test_backups_and_runtime_are_ignored_without_ignoring_receipts(self):
        w.ensure_local_excludes(self.root)
        for value in ('.specify/workflow/backups/a.zip', '.specify/workflow/runtime/usage.json', '.specify/workflow/install-receipt.json'):
            result = subprocess.run(['git', 'check-ignore', value], cwd=self.root, capture_output=True)
            self.assertEqual(result.returncode, 0, value)
        result = subprocess.run(['git', 'check-ignore', self.feature + '/workflow/checkpoint.json'], cwd=self.root, capture_output=True)
        self.assertEqual(result.returncode, 1)

    def test_internal_command_symlink_roundtrips_without_writing_through_link(self):
        target = self.root / '.specify/extensions/pr/original.md'
        target.write_text('Original command', encoding='utf-8')
        alias = self.root / '.claude/skills/speckit-pr-generate/SKILL.md'
        alias.parent.mkdir(parents=True)
        try:
            alias.symlink_to(target)
        except OSError as error:
            self.skipTest('Host does not support test symlinks: ' + str(error))
        before = installer.snapshot(self.root, self.package / 'backup')
        alias.unlink(); alias.write_text('Replaced registration', encoding='utf-8')
        target.write_text('Changed command', encoding='utf-8')
        installer.restore(self.root, before, installer.managed_files(self.root))
        self.assertTrue(alias.is_symlink())
        self.assertEqual(target.read_text(encoding='utf-8'), 'Original command')
        self.assertEqual(installer.managed_files(self.root), before)

    def test_owned_alias_upgrade_uses_previous_hash_and_preserves_local_edits(self):
        inventory = installer.install_aliases(self.root, self.package)
        w.write(self.root / '.specify/workflow/install-lock.json', {'aliases': inventory})
        source = self.package / 'skills/speckit-scope/SKILL.md'
        source.write_text(source.read_text(encoding='utf-8') + '\nUpdated owned routing.\n', encoding='utf-8')
        updated = installer.install_aliases(self.root, self.package)
        self.assertNotEqual(inventory, updated)
        w.write(self.root / '.specify/workflow/install-lock.json', {'aliases': updated})
        destination = self.root / '.agents/skills/speckit-scope/SKILL.md'
        destination.write_text(destination.read_text(encoding='utf-8') + '\nUser customization\n', encoding='utf-8')
        with self.assertRaisesRegex(w.WorkflowError, 'ALIAS_HAS_LOCAL_EDITS'):
            installer.install_aliases(self.root, self.package)
        self.assertIn('User customization', destination.read_text(encoding='utf-8'))

    def test_recognized_legacy_short_alias_routes_through_owned_dispatcher(self):
        destination = self.root / '.agents/skills/speckit-superpowers-bridge/SKILL.md'
        destination.parent.mkdir(parents=True)
        old = b'Legacy executor fixture'
        destination.write_bytes(old)
        w.write(self.package / 'assets/legacy-bridge-alias-hashes.json', [hashlib.sha256(old).hexdigest()])
        self.assertIn('LEGACY_ALIAS_RECONCILIATION_REQUIRED', str(w.doctor(self.root, self.policy)))
        installer.install_aliases(self.root, self.package)
        self.assertIn('<!-- sanduq-workflow-alias:v1 -->', destination.read_text(encoding='utf-8'))
        self.assertNotIn('LEGACY_ALIAS_RECONCILIATION_REQUIRED', str(w.doctor(self.root, self.policy)))
