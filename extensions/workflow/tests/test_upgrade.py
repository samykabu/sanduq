"""Check CI preservation across the outer workflow upgrade transaction."""
import hashlib
import json
import re
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import upgrade
import install as upgrade_install
import delegate_dispatch as dispatch
import delegation
import workflow as w
import test_workflow as fixture
import test_install as fixture_install


class UpgradeCITests(unittest.TestCase):
    configure = fixture.WorkflowTests.configure

    def setUp(self):
        fixture.WorkflowTests.setUp(self)
        registered = w.registry(self.root)
        registered['workflow'] = {'version': '1.1.0', 'enabled': True}
        w.write(self.root / '.specify/extensions/.registry', {'extensions': registered})
        manifest = self.root / '.specify/extensions/workflow/extension.yml'
        manifest.parent.mkdir(parents=True)
        manifest.write_text(yaml.safe_dump({'extension': {
            'id': 'workflow', 'version': '1.1.1', 'repository': upgrade.REPOSITORY}}), encoding='utf-8')
        self.ci = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        self.ci.parent.mkdir(parents=True)
        self.original = b'name: Consumer CI\r\nruns-on: homek8\r\n'
        self.ci.write_bytes(self.original)

    def test_preserve_choice_reaches_new_installer_and_returns_verified_hash(self):
        commands = []
        result = upgrade.upgrade(self.root, '1.1.1', apply=True, preserve_ci=True,
                                 runner=lambda root, args, log: commands.append(args))
        self.assertIn('--preserve-ci', commands[-1])
        self.assertEqual(result['preserved_ci']['sha256'], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(self.ci.read_bytes(), self.original)

    def test_preserved_ci_is_recorded_before_the_target_installer_runs(self):
        # Issue #22: a checkout without the git-excluded receipt. The target
        # installer may be one that reads only the receipt during its health
        # check, so the choice must already be on disk when it starts.
        receipt = self.root / '.specify/workflow/install-receipt.json'
        self.assertFalse(receipt.exists())
        seen = []

        def runner(root, args, log):
            if args[0] == sys.executable:
                seen.append(w.read(receipt, {}).get('preserved_ci'))
        upgrade.upgrade(self.root, '1.1.1', apply=True, preserve_ci=True, runner=runner)
        self.assertEqual(seen, [{'path': '.github/workflows/sanduq-workflow-gates.yml',
                                 'sha256': hashlib.sha256(self.original).hexdigest()}])

    def test_recorded_preservation_is_rolled_back_with_a_failed_upgrade(self):
        receipt = self.root / '.specify/workflow/install-receipt.json'

        def runner(root, args, log):
            if args[0] == sys.executable:
                raise w.WorkflowError('INSTALL_ROLLED_BACK: simulated')
        with self.assertRaisesRegex(w.WorkflowError, 'WORKFLOW_UPGRADE_ROLLED_BACK'):
            upgrade.upgrade(self.root, '1.1.1', apply=True, preserve_ci=True, runner=runner)
        self.assertFalse(receipt.exists())

    def test_a_failed_installer_run_names_its_cause_at_the_top(self):
        real = upgrade_install.subprocess.run
        cause = 'Compatibility Error: Extension requires spec-kit >=1.1.1.dev0,<2.0.0, but 1.0.11 is installed.'

        def run(args, *rest, **kwargs):
            if args[0] == 'specify':
                return upgrade_install.subprocess.CompletedProcess(args, 0, '', '')
            if args[0] == sys.executable:
                error = 'INSTALL_ROLLED_BACK: INSTALL_COMMAND_FAILED: specify extension add progress: ' + cause
                return upgrade_install.subprocess.CompletedProcess(args, 1, json.dumps({'ok': False, 'error': error}), '')
            return real(args, *rest, **kwargs)
        with patch.object(upgrade_install.subprocess, 'run', side_effect=run):
            with self.assertRaisesRegex(w.WorkflowError, 'WORKFLOW_UPGRADE_ROLLED_BACK: INSTALL_COMMAND_FAILED: .*'
                                        'install.py .*--with progress: INSTALL_ROLLED_BACK: .*' + re.escape(cause)):
                upgrade.upgrade(self.root, '1.1.1', apply=True, with_optional=['progress'])

    def test_default_does_not_request_preservation(self):
        commands = []
        result = upgrade.upgrade(self.root, '1.1.1', apply=True,
                                 runner=lambda root, args, log: commands.append(args))
        self.assertNotIn('--preserve-ci', commands[-1])
        self.assertIsNone(result['preserved_ci'])

    def test_outer_transaction_rolls_back_if_new_installer_changes_preserved_ci(self):
        def runner(root, args, log):
            if args[0] == sys.executable:
                self.ci.write_bytes(b'Unexpected replacement\n')
        with self.assertRaisesRegex(w.WorkflowError, 'PROJECT_CI_PRESERVATION_FAILED'):
            upgrade.upgrade(self.root, '1.1.1', apply=True, preserve_ci=True, runner=runner)
        self.assertEqual(self.ci.read_bytes(), self.original)

    def test_delegation_choices_and_history_survive_upgrade(self):
        policy_path = self.root / '.specify/workflow.yml'
        policy = w.load_policy(self.root)
        policy['delegation']['enabled'] = True
        policy['delegation']['models']['codex']['standard'] = 'team-model'
        policy_path.write_text(yaml.safe_dump(policy), encoding='utf-8')
        ledger = self.root / self.feature / 'workflow/delegations.json'
        w.write(ledger, {'schema_version': 1, 'feature': self.feature,
                         'attempts': [{'run_id': 'codex-1', 'status': 'successful'}],
                         'route_decisions': []})
        original = ledger.read_bytes()
        upgrade.upgrade(self.root, '1.1.1', apply=True, runner=lambda *args: None)
        self.assertEqual(w.load_policy(self.root)['delegation']['models']['codex']['standard'],
                         'team-model')
        self.assertEqual(ledger.read_bytes(), original)

    def test_delegation_history_change_rolls_back_upgrade(self):
        ledger = self.root / self.feature / 'workflow/delegations.json'
        w.write(ledger, {'schema_version': 1, 'feature': self.feature,
                         'attempts': [], 'route_decisions': []})
        original = ledger.read_bytes()
        def runner(root, args, log):
            if args[0] == sys.executable:
                ledger.write_text('{"lost": true}', encoding='utf-8')
        with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_HISTORY_PRESERVATION_FAILED'):
            upgrade.upgrade(self.root, '1.1.1', apply=True, runner=runner)
        self.assertEqual(ledger.read_bytes(), original)

    def active_ledger(self, status):
        ledger = self.root / self.feature / 'workflow/delegations.json'
        w.write(ledger, {'schema_version': 1, 'feature': self.feature,
                         'attempts': [{'intent_id': 'i-1', 'identity': self.feature + '/T001',
                                       'status': status, 'run_id': 'codex-1'}],
                         'route_decisions': []})
        return ledger

    def test_upgrade_refuses_while_a_delegation_attempt_is_starting_or_running(self):
        for status in ('starting', 'running'):
            with self.subTest(status=status):
                ledger = self.active_ledger(status)
                original = ledger.read_bytes()
                commands = []
                with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_ATTEMPTS_ACTIVE'):
                    upgrade.upgrade(self.root, '1.1.1', apply=True,
                                    runner=lambda root, args, log: commands.append(args))
                self.assertEqual(commands, [])
                self.assertEqual(ledger.read_bytes(), original)
                self.assertFalse((self.root / '.specify/workflow/runtime/upgrade.lock').exists())

    def test_dispatchers_are_refused_during_upgrade_and_history_survives_rollback(self):
        policy_path = self.root / '.specify/workflow.yml'
        policy = w.load_policy(self.root)
        policy['delegation']['enabled'] = True
        policy_path.write_text(yaml.safe_dump(policy), encoding='utf-8')
        ledger = self.active_ledger('successful')
        original = ledger.read_bytes()
        refused = {}

        def runner(root, args, log):
            if args[0] != sys.executable:
                return
            for label, operation in {
                    'start': lambda: dispatch.start(self.root, self.feature, 'T001'),
                    'collect': lambda: dispatch.collect(self.root, self.feature, 'codex-1'),
                    'reassign': lambda: dispatch.reassign(self.root, self.feature, 'codex-1', 'harder'),
                    'recover': lambda: dispatch.recover_intent(self.root, self.feature, 'i-1'),
                    'abandon': lambda: dispatch.abandon_intent(self.root, self.feature, 'i-1', 'gone')}.items():
                try:
                    operation()
                except delegation.DelegationError as error:
                    refused[label] = str(error)
            raise w.WorkflowError('INSTALL_ROLLED_BACK: simulated')
        with self.assertRaisesRegex(w.WorkflowError, 'WORKFLOW_UPGRADE_ROLLED_BACK'):
            upgrade.upgrade(self.root, '1.1.1', apply=True, runner=runner)
        self.assertEqual(sorted(refused), ['abandon', 'collect', 'reassign', 'recover', 'start'])
        self.assertTrue(all(error.startswith('WORKFLOW_UPGRADE_IN_PROGRESS') for error in refused.values()))
        self.assertEqual(ledger.read_bytes(), original)

    def test_successful_upgrade_keeps_the_newest_three_zips(self):
        old = fixture_install.fake_backups(self.root, 4)
        result = upgrade.upgrade(self.root, '1.1.1', apply=True, runner=lambda *args: None)
        self.assertEqual(result['backups']['zips'], 3)
        self.assertTrue((Path(result['backup']) / 'before.zip').is_file())
        self.assertEqual([path.is_file() for path in old], [False, False, True, True])
        self.assertTrue(all((path.parent / 'result.json').is_file() for path in old))

    def test_failed_upgrade_prunes_no_backup(self):
        old = fixture_install.fake_backups(self.root, 4)

        def runner(root, args, log):
            if args[0] == sys.executable:
                raise w.WorkflowError('INSTALL_ROLLED_BACK: simulated')
        with self.assertRaisesRegex(w.WorkflowError, 'WORKFLOW_UPGRADE_ROLLED_BACK'):
            upgrade.upgrade(self.root, '1.1.1', apply=True, runner=runner)
        self.assertTrue(all(path.is_file() for path in old))

    def test_upgrade_refuses_while_a_memory_archive_run_is_active(self):
        fixture_install.memory_archive_run(self.root)
        commands = []
        with self.assertRaisesRegex(w.WorkflowError, 'MEMORY_ARCHIVE_ACTIVE: archive run a{32} is not finished'):
            upgrade.upgrade(self.root, '1.1.1', apply=True, runner=lambda root, args, log: commands.append(args))
        self.assertEqual(commands, [])
        self.assertFalse((self.root / '.specify/workflow/backups/upgrades').exists())
        self.assertFalse((self.root / '.specify/workflow/runtime/upgrade.lock').exists())
