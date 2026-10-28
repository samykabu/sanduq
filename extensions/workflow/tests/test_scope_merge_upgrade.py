"""DEC-03: a project on the last released train with a separate Scope (Workflow 1.25.0, Scope 1.14.0) and a feature
in progress upgrades to the Workflow that provides Scope. The old package, its skills and hooks go; its state in
.specify/scope stays and the merged scripts read it; the feature keeps its Scope receipt through `migrate`."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import install as installer
import upgrade
import workflow as w
import test_hosts
import test_workflow as fixture

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts/scope'
OLD_HOOKS = {'before_specify': [{'extension': 'scope', 'command': 'speckit.scope.guard', 'enabled': True, 'optional': False}],
             'after_specify': [{'extension': 'scope', 'command': 'speckit.scope.bind', 'enabled': True, 'optional': False},
                               {'extension': 'scope', 'command': 'speckit.scope.after-specify', 'enabled': False,
                                'optional': False}],
             'before_plan': [{'extension': 'scope', 'command': 'speckit.scope.plan-guard', 'enabled': True, 'optional': False}],
             'after_implement': [{'extension': 'scope', 'command': 'speckit.scope.reconcile', 'enabled': True,
                                  'optional': False},
                                 {'extension': 'custom', 'command': 'custom.check', 'enabled': True, 'optional': True}]}
OPERATION = '10-0123456789abcdef'
# test_hosts deletes its base class so unittest does not run it alone.
HostTests = test_hosts.InstallKeepsHostsTests.__bases__[0]


class ScopeMergeUpgradeTests(HostTests):
    receipt = fixture.WorkflowTests.receipt
    usage = fixture.WorkflowTests.usage

    def setUp(self):
        super().setUp()
        # A feature in progress under the old train: Scope and Specify passed, recorded with the old command name.
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        for stage in ('scope', 'specify'):
            claim = run.claim(self.usage())
            self.assertEqual(claim['stage'], stage)
            run.complete(claim['token'], self.receipt(stage))
        state = w.read(run.path)
        state['commands']['scope'] = 'speckit.scope.run'
        state['receipts']['scope']['command'] = 'speckit.scope.run'
        w.write(run.path, state)
        # The released train installed beside it: Workflow 1.25.0, Scope 1.14.0 with its skills, hooks and state.
        registered = w.registry(self.root)
        registered.update(workflow={'version': '1.25.0', 'enabled': True}, scope={'version': '1.14.0', 'enabled': True})
        w.write(self.root / '.specify/extensions/.registry', {'extensions': registered})
        test_hosts.write_manifest(self.root, 'workflow', '1.25.0')
        test_hosts.write_manifest(self.root, 'scope', '1.14.0')
        for folder in test_hosts.hosts.HOST_SKILLS.values():
            for name in ('speckit-scope-run', 'speckit-scope-plan'):
                path = self.root / folder / name / 'SKILL.md'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('registered ' + name, encoding='utf-8')
        (self.root / '.specify/extensions.yml').write_text(yaml.safe_dump({'hooks': OLD_HOOKS}, sort_keys=False),
                                                         encoding='utf-8')
        self.state = {'.specify/scope/approvals/10-baseline.json': {'issue': 10, 'analysis_sha256': 'a' * 64},
                      '.specify/scope/runs/' + OPERATION + '/journal.json': {'operation': OPERATION.split('-')[1],
                                                                            'nodes': {'root': 10, 'a': 21},
                                                                            'published': False}}
        for name, value in self.state.items():
            w.write(self.root / name, value)

    def upgrade(self):
        with patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}):
            return upgrade.upgrade(self.root, '2.0.0', apply=True, runner=self.specify)

    def test_upgrade_removes_scope_first_and_keeps_its_state_and_the_feature(self):
        plan = upgrade.upgrade(self.root, '2.0.0')
        self.assertFalse(plan['applied'])
        result = self.upgrade()
        self.assertTrue(result['applied'])
        calls = [c[:4] for c in self.specify.calls]
        self.assertEqual(calls[0], ['specify', 'extension', 'add', 'workflow'])
        removed = calls.index(['specify', 'extension', 'remove', 'scope'])
        self.assertTrue(all(c[:3] != ['specify', 'extension', 'add'] for c in calls[2:removed]), calls)
        # No scope package, skills or hooks remain; everything else does.
        self.assertNotIn('scope', w.registry(self.root))
        self.assertFalse((self.root / '.specify/extensions/scope').exists())
        for folder in test_hosts.hosts.HOST_SKILLS.values():
            self.assertFalse(list((self.root / folder).glob('speckit-scope-*')), folder)
            self.assertTrue((self.root / folder / 'speckit-workflow-scope-run/SKILL.md').is_file(), folder)
        hooks = yaml.safe_load((self.root / '.specify/extensions.yml').read_text(encoding='utf-8'))['hooks']
        self.assertEqual([h['extension'] for items in hooks.values() for h in items], ['custom'])
        lock = w.read(self.root / '.specify/workflow/install-lock.json')
        self.assertNotIn('scope', lock['extensions'])
        receipt = w.read(self.root / '.specify/workflow/install-receipt.json')
        self.assertEqual(receipt['scope_removed']['version'], '1.14.0')
        for name, value in self.state.items():
            self.assertEqual(w.read(self.root / name), value, name)
        # The real doctor sees no Scope problem now.
        self.assertEqual([e for e in w.doctor(self.root, w.load_policy(self.root))['errors'] if 'scope' in e.lower()], [])

        # The feature in progress: the rename alone invalidates nothing; migrate records the new name.
        run = w.Run(self.root, self.feature)
        state = run.load()
        preview = run.migration_plan(state)
        self.assertEqual((preview['changed_commands'], preview['invalidated']), ([], []))
        run.migrate('Scope merged into Workflow (DEC-03)')
        state = w.read(run.path)
        self.assertEqual(state['commands']['scope'], 'speckit.workflow.scope-run')
        self.assertEqual(sorted(state['receipts']), ['scope', 'specify'])
        self.assertEqual(run.next(state)['stage'], 'clarify')

        # The renamed commands' scripts run from Workflow and read the state Scope 1.14.0 left.
        done = subprocess.run([sys.executable, str(SCRIPTS / 'scope.py'), '--root', str(self.root), 'cancel', OPERATION],
                              cwd=self.root, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        listed = json.loads(done.stdout)
        self.assertEqual((listed['journal'], listed['created']),
                         ('.specify/scope/runs/' + OPERATION + '/journal.json', {'a': 21}))
        for script in ('clarification.py', 'accept_plan.py'):
            done = subprocess.run([sys.executable, str(SCRIPTS / script), '--help'], cwd=self.root,
                                  capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(done.returncode, 0, script + ': ' + done.stderr)

    def test_a_failed_upgrade_puts_scope_back(self):
        before = test_hosts.tree(self.root)
        # A failure after Spec Kit removed Scope: both transactions roll back.
        with patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}),              patch.object(installer, 'wire_illustrate', side_effect=w.WorkflowError('SIMULATED')),              self.assertRaisesRegex(w.WorkflowError, 'WORKFLOW_UPGRADE_ROLLED_BACK'):
            upgrade.upgrade(self.root, '2.0.0', apply=True, runner=self.specify)
        self.assertIn(['specify', 'extension', 'remove', 'scope', '--force'], self.specify.calls)
        self.assertEqual(w.registry(self.root)['scope']['version'], '1.14.0')
        after = test_hosts.tree(self.root)
        for name in [n for n in before if n.startswith(('.specify/extensions', '.specify/scope', '.agents/', '.claude/'))]:
            self.assertEqual(after.get(name), before[name], name)


if __name__ == '__main__':
    unittest.main()
