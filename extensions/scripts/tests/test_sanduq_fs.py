"""`sanduq_fs.py`: the shared lock, atomic JSON write and bounded runner (SAMY-01/02/09)."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shared'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sanduq_fs as fs  # noqa: E402
import package  # noqa: E402


def dead_pid():
    python = getattr(sys, '_base_executable', None) or sys.executable
    done = subprocess.run([python, '-c', 'import os; print(os.getpid())'], capture_output=True, text=True, timeout=60)
    return int(done.stdout)


class Busy(Exception):
    pass


class SanduqFsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.lock = self.root / 'runtime/probe.lock'

    def owner(self, **values):
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        record = {'host': socket.gethostname(), 'token': 'old', 'created': 0, **values}
        self.lock.write_text(json.dumps(record), encoding='utf-8')
        return record

    def test_dead_owner_is_recovered_and_the_lock_released(self):
        self.owner(pid=dead_pid())
        with fs.file_lock(self.lock, 0, 'BUSY', Busy) as token:
            self.assertTrue(fs.lock_held(self.lock, token))
        self.assertEqual(list(self.lock.parent.iterdir()), [])

    def test_live_owner_raises_the_callers_error_naming_it(self):
        self.owner(pid=os.getpid())
        started = time.monotonic()
        with self.assertRaisesRegex(Busy, r'^BUSY: retry .* pid %d on host .* \(alive: yes\)' % os.getpid()):
            with fs.file_lock(self.lock, 0.2, 'BUSY', Busy):
                pass
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(fs.lock_owner(self.lock)['token'], 'old')

    def test_unreadable_owner_is_stale_only_once_old(self):
        self.lock.parent.mkdir(parents=True)
        self.lock.write_text('', encoding='utf-8')
        self.assertFalse(fs.recover_stale_lock(self.lock))
        old = time.time() - fs.LOCK_UNREADABLE_STALE_SECONDS - 5
        os.utime(self.lock, (old, old))
        self.assertTrue(fs.recover_stale_lock(self.lock))
        self.assertFalse(self.lock.exists())

    def test_recovery_puts_back_a_lock_that_turned_live(self):
        live = self.owner(pid=os.getpid(), token='live')
        verdicts = iter((True,))
        real = fs.lock_is_stale
        # The inspection sees a dead owner; by the capture a live owner holds it.
        flip = lambda path, owner: next(verdicts, None) or real(path, owner)  # noqa: E731
        with patch.object(fs, 'lock_is_stale', side_effect=flip):
            self.assertFalse(fs.recover_stale_lock(self.lock))
        self.assertEqual(fs.lock_owner(self.lock), live)
        self.assertEqual([p.name for p in self.lock.parent.iterdir()], ['probe.lock'])

    def test_write_json_is_atomic_and_read_json_defaults(self):
        target = self.root / 'a/b.json'
        self.assertEqual(fs.read_json(target, {'x': 1}), {'x': 1})
        fs.write_json(target, {'k': 'v'})
        self.assertEqual(fs.read_json(target), {'k': 'v'})
        self.assertEqual([p.name for p in target.parent.iterdir()], ['b.json'])  # no temp left behind

    def test_replace_retries_a_transient_windows_sharing_violation(self):
        source, target = self.root / 's', self.root / 't'
        source.write_text('new', encoding='utf-8')
        real, calls = os.replace, []

        def flaky(a, b):
            calls.append(a)
            if len(calls) < 3:
                raise PermissionError('in use')
            return real(a, b)
        with patch.object(fs.os, 'replace', flaky), patch.object(fs.time, 'sleep'):
            fs.replace_file(source, target)
        self.assertEqual((len(calls), target.read_text(encoding='utf-8')), (3, 'new'))

    def test_run_bounded_names_the_error_and_next_step(self):
        started = time.monotonic()
        with self.assertRaisesRegex(Busy, r'^STUB_TIMEOUT: .* within 1 s and was stopped; rerun it'):
            fs.run_bounded([sys.executable, '-c', 'import time; time.sleep(60)'], timeout=1,
                           error_code='STUB_TIMEOUT', next_step='rerun it', error=Busy, capture_output=True)
        self.assertLess(time.monotonic() - started, 30)
        done = fs.run_bounded([sys.executable, '-c', 'print(7)'], timeout=30, error_code='X', next_step='y',
                              capture_output=True, text=True)
        self.assertEqual(done.stdout.strip(), '7')

    def test_workflow_package_ships_the_source_bytes(self):
        self.assertIn('workflow', package.SHARED['sanduq_fs.py'])
        output = self.root / 'workflow.zip'
        package.package('workflow', output=output)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read('workflow/scripts/sanduq_fs.py'),
                             (package.ROOT / 'extensions/scripts/shared/sanduq_fs.py').read_bytes())


if __name__ == '__main__':
    unittest.main()
