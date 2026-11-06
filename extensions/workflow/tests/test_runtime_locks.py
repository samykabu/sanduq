"""SAMY-01: Workflow's runtime locks recover from a killed owner and name a live one."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import wf_core  # noqa: E402

# The base interpreter: under a Windows venv launcher the locks would be held by a grandchild.
PYTHON = getattr(sys, '_base_executable', None) or sys.executable

HOLDER = textwrap.dedent('''
    import sys, time
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    import wf_core
    with wf_core.locked(Path(sys.argv[2])), wf_core.locked(Path(sys.argv[3])):
        print('ready', flush=True)
        time.sleep(120)
''')


class RuntimeLockTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        runtime = Path(tmp.name) / '.specify/workflow/runtime'
        self.dispatch = runtime / 'dispatch.lock'
        self.feature = Path(tmp.name) / 'specs/001-demo/workflow/run.lock'

    def holder(self):
        """A child process holding dispatch.lock and the feature lock, as a claim does."""
        child = subprocess.Popen([PYTHON, '-c', HOLDER, str(SCRIPTS), str(self.dispatch), str(self.feature)],
                                 stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (child.poll() is None and child.kill(), child.wait(), child.stdout.close()))
        self.assertEqual(child.stdout.readline().strip(), 'ready')
        return child

    def test_locks_of_a_killed_owner_are_reclaimed_without_cleanup(self):
        child = self.holder()
        child.kill()  # TerminateProcess on Windows, SIGKILL elsewhere: no finally runs
        child.wait(30)
        self.assertTrue(self.dispatch.exists() and self.feature.exists())
        with wf_core.locked(self.dispatch), wf_core.locked(self.feature):
            self.assertEqual(json.loads(self.dispatch.read_text(encoding='utf-8'))['pid'], os.getpid())
        self.assertFalse(self.dispatch.exists() or self.feature.exists())
        self.assertEqual(sorted(p.name for p in self.dispatch.parent.iterdir()), [])  # no captured leftovers

    def test_a_live_owner_still_yields_workflow_busy_naming_it(self):
        child = self.holder()
        for path in (self.dispatch, self.feature):
            with self.subTest(lock=path.name):
                with self.assertRaises(wf_core.WorkflowError) as caught:
                    with wf_core.locked(path):
                        self.fail('a live owner was displaced')
                message = str(caught.exception)
                self.assertTrue(message.startswith('WORKFLOW_BUSY: retry the command'), message)
                self.assertIn('pid %d on host %s' % (child.pid, socket.gethostname()), message)
                self.assertIn('alive: yes', message)
                self.assertRegex(message, r'for \d+s')
                self.assertIn('ps -p %d' % child.pid, message)
        self.assertEqual(json.loads(self.dispatch.read_text(encoding='utf-8'))['pid'], child.pid)

    def test_foreign_host_and_old_version_locks_are_never_taken(self):
        dead = subprocess.run([PYTHON, '-c', 'import os; print(os.getpid())'],
                              capture_output=True, text=True, timeout=60)
        pid = int(dead.stdout)
        owners = {'another host': {'pid': pid, 'host': 'elsewhere', 'token': 't', 'created': 0},
                  'older Workflow record without host': {'pid': pid, 'created': '2026-10-01T00:00:00+00:00'}}
        self.dispatch.parent.mkdir(parents=True)
        for name, owner in owners.items():
            with self.subTest(owner=name):
                self.dispatch.write_text(json.dumps(owner), encoding='utf-8')
                with self.assertRaisesRegex(wf_core.WorkflowError, r'WORKFLOW_BUSY: .*pid %d .*alive: unknown' % pid):
                    with wf_core.locked(self.dispatch):
                        pass
                self.assertEqual(json.loads(self.dispatch.read_text(encoding='utf-8')), owner)


if __name__ == '__main__':
    unittest.main()
