"""Static package and managed driver changes require the existing reviewed migration."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow as w
from test_receipt_contract import Harness


class ToolchainFreezeTests(Harness):
    def put(self, name, content='original'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def test_inventory_covers_static_bytes_and_missing_binary_members(self):
        folder = '.specify/extensions/workflow'
        member = self.put(folder + '/assets/contract.dat')
        w.write(self.root / folder / 'package-inventory.json', {
            'workflow/assets/contract.dat': hashlib.sha256(member.read_bytes()).hexdigest()})
        original = w.package_digest(self.root)
        member.write_bytes(b'changed')
        self.assertNotEqual(w.package_digest(self.root), original)
        member.write_bytes(b'original')
        self.assertEqual(w.package_digest(self.root), original)
        member.unlink()
        self.assertNotEqual(w.package_digest(self.root), original)

    def test_new_static_contract_is_detected_even_with_package_inventory(self):
        w.write(self.root / '.specify/extensions/workflow/package-inventory.json', {})
        before = w.package_digest(self.root)
        self.put('.specify/extensions/workflow/schemas/new.json', '{}')
        self.assertNotEqual(w.package_digest(self.root), before)

    def test_static_json_and_managed_driver_block_claim_until_migration(self):
        paths = []
        for name in ('.specify/extensions/workflow/dependencies.json',
                     '.specify/extensions/workflow/assets/driver.mjs',
                     '.agents/skills/delegate-task/delegate.mjs',
                     '.claude/skills/delegate-task/contracts/static.json'):
            with self.subTest(name=name):
                path = self.put(name, '{}')
                paths.append(path)
                before = w.package_digest(self.root)
                path.write_text('{"changed": true}', encoding='utf-8')
                self.assertNotEqual(w.package_digest(self.root), before)
                path.write_text('{}', encoding='utf-8')
        run = self.run_object()
        claim = run.claim(self.usage())
        run.complete(claim['token'], self.receipt('scope'))
        before = run.load()['dependency_digest']
        paths[-1].write_text('{"changed": true}', encoding='utf-8')
        with self.assertRaisesRegex(w.WorkflowError, 'DEPENDENCY_CHANGED'):
            run.claim(self.usage())
        accepted = run.load()['receipts']['scope']
        preview = run.preview_migration()
        self.assertEqual(preview['dependency_from'], before)
        self.assertEqual(preview['invalidated'], [])
        run.migrate('Reviewed blocking toolchain fix')
        self.assertNotEqual(run.load()['dependency_digest'], before)
        self.assertEqual(run.load()['receipts']['scope'], accepted)
        self.assertEqual(run.claim(self.usage())['stage'], 'specify')

    def test_runtime_state_and_raw_runs_do_not_change_freeze(self):
        self.put('.agents/skills/delegate-task/delegate.mjs')
        registry = self.root / '.specify/extensions/.registry'
        registrations = w.read(registry)
        registrations['extensions']['optional'] = {'version': '1.0.0', 'enabled': False}
        w.write(registry, registrations)
        before = w.package_digest(self.root)
        for name in ('.specify/extensions/workflow/state/runtime.json',
                     '.specify/extensions/workflow/__pycache__/module.py',
                     '.agents/skills/delegate-task/runs/result.md',
                     '.agents/skills/delegate-task/runs/containment-windows.ps1',
                     '.agents/skills/delegate-task/__pycache__/job-windows.ps1',
                     '.agents/skills/delegate-task/test/fixture.json',
                     '.agents/skills/delegate-task/coverage/report.json',
                     '.agents/skills/delegate-task/node_modules/dependency/index.mjs',
                     '.specify/extensions/optional/state/output.json',
                     '.specify/extensions/project/config.json',
                     '.specify/project-sync-state.json',
                     '.specify/workflow/install-receipt.json'):
            self.put(name, 'mutable')
        registrations['extensions']['optional']['installed_at'] = 'later'
        w.write(registry, registrations)
        self.assertEqual(w.package_digest(self.root), before)

    def test_managed_powershell_helpers_are_frozen_without_inventory(self):
        for host in ('.agents', '.claude'):
            for name in ('containment-windows.ps1', 'job-windows.ps1'):
                with self.subTest(host=host, name=name):
                    path = self.put(host + '/skills/delegate-task/' + name)
                    before = w.package_digest(self.root)
                    path.write_text('changed executable helper', encoding='utf-8')
                    self.assertNotEqual(w.package_digest(self.root), before)
                    path.write_text('original', encoding='utf-8')
                    self.assertEqual(w.package_digest(self.root), before)

    def test_inventory_cannot_escape_package_boundary(self):
        path = self.root / '.specify/extensions/workflow/package-inventory.json'
        for member in ('workflow/../../outside.json', 'workflow/..\\outside.json', 'workflow/\0bad',
                       'outside.json', 'workflow/' + self.root.as_posix() + '/outside'):
            with self.subTest(member=member):
                w.write(path, {member: 'irrelevant'})
                with self.assertRaisesRegex(w.WorkflowError, 'PACKAGE_INVENTORY_INVALID'):
                    w.package_digest(self.root)
        path.write_text('{invalid', encoding='utf-8')
        with self.assertRaisesRegex(w.WorkflowError, 'PACKAGE_INVENTORY_INVALID'):
            w.package_digest(self.root)
