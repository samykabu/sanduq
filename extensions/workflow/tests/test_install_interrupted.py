"""AHMED-09: Ctrl-C during an install, upgrade or host switch restores the snapshot; a hard kill leaves a marker
doctor reports as INSTALL_INTERRUPTED with the `install.py --restore <backup>` command."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import hosts
import install as installer
import upgrade
import test_install
import test_upgrade
import test_hosts
import test_workflow as fixture
from test_workflow import w


def dead_pid():
    child = subprocess.Popen([sys.executable, '-c', 'pass'])
    child.wait()
    return child.pid


class InterruptedInstallTests(unittest.TestCase):
    configure = fixture.WorkflowTests.configure
    setUp = test_install.InstallTests.setUp
    apply = test_install.InstallTests.apply

    def test_keyboard_interrupt_restores_the_snapshot_and_is_re_raised(self):
        before = installer.managed_files(self.root)

        def runner(root, args, log):
            (root / '.specify/workflow.yml').write_text('half written', encoding='utf-8')
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.apply(runner)
        self.assertEqual(installer.managed_files(self.root), before)
        self.assertFalse((self.root / installer.IN_PROGRESS).exists())
        backup = next((self.root / '.specify/workflow/backups/installs').glob('*/result.json'))
        self.assertEqual(w.read(backup)['error'], 'KeyboardInterrupt')

    def test_a_hard_kill_leaves_a_marker_doctor_reports_with_the_restore_command(self):
        backup = self.root / '.specify/workflow/backups/installs/abc'
        w.write(self.root / installer.IN_PROGRESS, {'kind': 'install', 'backup': str(backup), 'pid': os.getpid(),
                                                   'started_at': 'now'})
        self.assertEqual([e for e in w.doctor(self.root, self.policy)['errors'] if 'INTERRUPTED' in e], [])  # still running
        w.write(self.root / installer.IN_PROGRESS, {'kind': 'install', 'backup': str(backup), 'pid': dead_pid(),
                                                   'started_at': 'now'})
        errors = [e for e in w.doctor(self.root, self.policy)['errors'] if e.startswith('INSTALL_INTERRUPTED')]
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('run "python .specify/extensions/workflow/scripts/install.py --restore ' + str(backup) + '"', errors[0])

    def test_restore_puts_the_backed_up_managed_files_back(self):
        before = installer.managed_files(self.root)
        receipt = self.apply()
        self.assertNotEqual(installer.managed_files(self.root), before)
        w.write(self.root / installer.IN_PROGRESS, {'kind': 'install', 'backup': receipt['backup'], 'pid': dead_pid()})
        result = installer.restore_backup(self.root, receipt['backup'])
        self.assertEqual(result['files'], len(before))
        self.assertEqual(installer.managed_files(self.root), before)
        self.assertFalse((self.root / installer.IN_PROGRESS).exists())
        with self.assertRaisesRegex(w.WorkflowError, 'RESTORE_BACKUP_INVALID'):
            installer.restore_backup(self.root, self.root / 'nowhere')


class InterruptedUpgradeTests(unittest.TestCase):
    configure = fixture.WorkflowTests.configure
    setUp = test_upgrade.UpgradeCITests.setUp

    def test_keyboard_interrupt_restores_the_snapshot_and_is_re_raised(self):
        def runner(root, args, log):
            self.ci.write_bytes(b'half written')
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            upgrade.upgrade(self.root, '1.1.1', apply=True, runner=runner)
        self.assertEqual(self.ci.read_bytes(), self.original)
        self.assertFalse((self.root / installer.IN_PROGRESS).exists())


class InterruptedSwitchTests(unittest.TestCase):
    configure = fixture.WorkflowTests.configure
    setUp = test_hosts.SwitchTests.setUp  # the shared HostTests base is deleted from the module after use
    default = test_hosts.SwitchTests.default

    def test_keyboard_interrupt_restores_the_snapshot_and_is_re_raised(self):
        before = installer.managed_files(self.root)

        def runner(root, args, log):
            self.specify(root, args, log)
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            hosts.switch(self.root, 'claude', runner=runner, package_root=self.package)
        self.assertEqual(installer.managed_files(self.root), before)
        self.assertEqual(w.active_host(self.root), 'codex')
        self.assertFalse((self.root / installer.IN_PROGRESS).exists())


if __name__ == '__main__':
    unittest.main()
