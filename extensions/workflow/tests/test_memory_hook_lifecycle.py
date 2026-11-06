"""D3 gate: Workflow owns Memory's session and prepare hooks across the install lifecycle.

Scripted, no model and no network: Memory installed before and after Workflow, Memory re-init, a
`specify extension update memory` re-registration, `reconcile --restore`, automatic mode off and an
interrupted archive. Registration uses the real Spec Kit `HookExecutor.register_hooks` when
`specify_cli` is importable (CI pin 0282d03), else `register_hooks` below, which keeps the two
behaviours that matter here: this extension's entries are re-created `enabled: true`, and its
entries on events the manifest no longer declares are purged.
"""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import test_workflow as fixture
from reconcile import WorkflowError, reconcile  # the `workflow` module reconcile and install load

w = fixture.w
SOURCE = Path(__file__).resolve().parents[2] / 'memory'
OWNED = {'before_specify:speckit.memory.session', 'after_implement:speckit.memory.prepare'}

try:
    from specify_cli.extensions import ExtensionManifest, HookExecutor
except ImportError:  # the workflow suite does not install Spec Kit
    HookExecutor = None


def register_hooks(root, manifest_path):
    """Spec Kit's `register_hooks`, or the stand-in that keeps its re-enable and purge behaviour."""
    if HookExecutor is not None:
        HookExecutor(root).register_hooks(ExtensionManifest(manifest_path))
        return
    manifest = yaml.safe_load(manifest_path.read_text(encoding='utf-8'))
    ext = manifest['extension']['id']
    path = root / '.specify/extensions.yml'
    config = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    hooks = config.setdefault('hooks', {}) or {}
    config['hooks'] = hooks
    for event in list(hooks):
        if event not in manifest['hooks']:
            hooks[event] = [h for h in hooks[event] if h.get('extension') != ext]
    for event, entry in manifest['hooks'].items():
        items = [h for h in hooks.get(event) or [] if h.get('extension') != ext]  # also drops init-only bindings
        items.append({'extension': ext, 'command': entry['command'], 'enabled': True,
                      'optional': entry.get('optional', True), 'priority': 10,
                      'prompt': f"Execute {entry['command']}?", 'description': entry.get('description', ''),
                      'condition': None})
        hooks[event] = items
    installed = config.setdefault('installed', []) or []
    config['installed'] = installed if ext in installed else installed + [ext]
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')


class MemoryHookLifecycleTests(unittest.TestCase):
    setUp_base = fixture.WorkflowTests.setUp
    configure = fixture.WorkflowTests.configure
    usage = fixture.WorkflowTests.usage
    run_object = fixture.WorkflowTests.run_object

    def setUp(self):
        self.setUp_base()
        w.git(self.root, 'config', 'core.autocrlf', 'false')
        w.ensure_local_excludes(self.root)
        # Memory's installer needs its own "installed:" list and a bare "hooks:" heading. `settings` comes first:
        # Memory's add_hook drops a top-level key that follows the hooks it rewrites (S-PM request in the notes).
        (self.root / '.specify/extensions.yml').write_text(
            'installed:\n- project\nsettings:\n  auto_execute_hooks: true\nhooks:\n  after_tasks:\n  - extension: project\n'
            '    command: speckit.project.sync\n    enabled: true\n    optional: false\n', encoding='utf-8')
        self.manifest = self.root / '.specify/extensions/memory/extension.yml'

    def copy_memory(self):
        installed = self.root / '.specify/extensions/memory'
        shutil.copytree(SOURCE, installed, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', 'tests', 'CHANGELOG.md'))
        for helper in ('check_inputs.py', 'bounded_json.py', 'sanduq_fs.py'):
            shutil.copyfile(SOURCE.parent / 'scripts/shared' / helper, installed / 'scripts' / helper)
        # Spec Kit's feature scripts, which Memory's init patches with its number guard.
        shutil.copytree(SOURCE / 'tests/fixtures/entry-points/.specify/scripts', self.root / '.specify/scripts',
                        dirs_exist_ok=True)

    def memory_init(self):
        """`speckit.memory.init`: Memory's real installer."""
        result = subprocess.run([sys.executable, '-B', str(self.root / '.specify/extensions/memory/scripts/install.py'),
                                 '--root', str(self.root), '--target-branch', 'main'],
                                capture_output=True, text=True, encoding='utf-8', cwd=self.root)
        body = json.loads(result.stdout)
        self.assertNotIn('error', body, result.stdout + result.stderr)

    def add_memory(self):
        """`specify extension add memory` then init."""
        self.copy_memory()
        register_hooks(self.root, self.manifest)
        self.memory_init()

    def hooks(self):
        doc = yaml.safe_load((self.root / '.specify/extensions.yml').read_text(encoding='utf-8'))
        return {event + ':' + h['command']: h for event, items in doc['hooks'].items() for h in items
                if h.get('extension') == 'memory'}

    def owners(self):
        return {e.split(': ', 1)[1].split(';')[0] for e in w.doctor(self.root, w.load_policy(self.root))['errors']
                if e.startswith('DUPLICATE_STAGE_OWNER') and 'memory' in e}

    def assert_managed(self):
        hooks = self.hooks()
        for key in OWNED:
            self.assertIs(hooks[key]['enabled'], False, key)
        self.assertTrue(all(h.get('enabled', True) for k, h in hooks.items() if k not in OWNED))
        self.assertIn('before_analyze:speckit.memory.impact', hooks)
        self.assertEqual(set(), self.owners())

    def test_memory_before_workflow_reinit_update_and_restore(self):
        self.add_memory()
        registered = self.hooks()
        reconcile(self.root, apply=True)  # what Workflow's installer runs
        self.assert_managed()
        # Memory re-init writes its entries again (enabled unless Memory keeps the flag); reconcile accepts it.
        self.memory_init()
        reconcile(self.root, apply=True)
        self.assert_managed()
        # `specify extension update memory`: Spec Kit re-creates the entries enabled.
        register_hooks(self.root, self.manifest)
        self.assertEqual(OWNED, self.owners())
        # The update drops impact's init-only before_specify binding until Memory's init runs again.
        self.assertNotIn('before_specify:speckit.memory.impact', self.hooks())
        updated = set(self.hooks())
        reconcile(self.root, apply=True)
        self.assert_managed()
        # A disabled entry edited by hand is still refused.
        doc = yaml.safe_load((self.root / '.specify/extensions.yml').read_text(encoding='utf-8'))
        before = (self.root / '.specify/extensions.yml').read_text(encoding='utf-8')
        next(h for h in doc['hooks']['after_implement'] if h['command'] == 'speckit.memory.prepare')['priority'] = 99
        (self.root / '.specify/extensions.yml').write_text(yaml.safe_dump(doc, sort_keys=False), encoding='utf-8')
        with self.assertRaisesRegex(WorkflowError, 'HOOK_CHANGED_SINCE_RECONCILE: after_implement:speckit.memory.prepare'):
            reconcile(self.root, apply=True)
        (self.root / '.specify/extensions.yml').write_text(before, encoding='utf-8')
        # Workflow uninstall: restore brings the registered entries back enabled.
        reconcile(self.root, apply=True, restore=True)
        restored = self.hooks()
        for key in OWNED:
            self.assertIs(restored[key]['enabled'], True, key)
        self.assertEqual(updated, set(restored))
        self.assertIn('before_specify:speckit.memory.impact', registered)

    def test_memory_after_workflow_needs_reconcile_which_doctor_names(self):
        reconcile(self.root, apply=True)
        self.add_memory()
        errors = [e for e in w.doctor(self.root, w.load_policy(self.root))['errors'] if 'memory' in e]
        self.assertEqual(OWNED, self.owners())
        self.assertTrue(all('reconcile.py --apply' in e for e in errors if e.startswith('DUPLICATE_STAGE_OWNER')))
        reconcile(self.root, apply=True)
        self.assert_managed()

    def test_automatic_mode_off_claims_and_an_interrupted_archive_blocks(self):
        self.add_memory()
        reconcile(self.root, apply=True)
        run = self.run_object()
        # Automatic mode is off after init: the claim's real session handoff reports pending and work goes on.
        claim = run.claim(self.usage())
        self.assertEqual('scope', claim['stage'])
        self.assertEqual('pending', run.load()['memory_session']['status'])
        state = run.load()
        state['active'] = None
        w.write(run.path, state)
        # An interrupted archive: Memory records the run; the claim and Workflow's installer both refuse.
        active = self.root / '.git/sanduq-memory/active.json'
        active.parent.mkdir(parents=True, exist_ok=True)
        w.write(active, {'run_id': 'a' * 32})
        claim = run.claim({**self.usage(), 'session_id': 'later-session'})
        self.assertEqual('memory_blocked', claim['status'])
        self.assertIs(claim['ok'], False)
        self.assertIsNone(run.load()['active'])
        import install
        with self.assertRaisesRegex(WorkflowError, 'MEMORY_ARCHIVE_ACTIVE'):
            install.memory_archive_preflight(self.root)


if __name__ == '__main__':
    unittest.main()
