import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
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
