"""SAMY-02: subprocesses run under the dispatch and feature locks are bounded; a hung one is reported by name
and the locks are released."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import workflow as w  # noqa: E402
import delegation  # noqa: E402
import memory_handoff as mh  # noqa: E402

SLEEP = 'import time; time.sleep(60)'

# Calls without `timeout=` that are bounded another way or cannot hang under a lock. Key: (file, function).
ALLOWED = {
    ('delegate_dispatch.py', 'run_capped'): 'Popen takes no timeout; proc.wait(timeout=...) bounds it and a timeout '
                                            'kills the whole tree',
    ('verify_affected.py', 'run_lanes'): 'Popen; its poll loop enforces the deadline and kills the tree',
    ('wf_core.py', 'run_git'): 'local git plumbing reads; a caller that needs a bound passes timeout= via **options',
    ('sanduq_hash.py', '_git'): 'local git hash-object/cat-file plumbing fed through stdin, no network or prompt',
    ('sanduq_hash.py', 'text_attributes'): 'local git check-attr over stdin, no network or prompt',
    ('source_key.py', '_git'): 'local git plumbing reads, no network or prompt',
}
# Not owned by the PH-02 runtime stream; each has a proposed change in the PH-02 report. Delete an entry when its
# change lands (the staleness check below fails until then).
PENDING = {
    ('delegate_dispatch.py', 'kill_process_tree'): 'taskkill: timeout 30 s',
    ('delegation.py', 'check_copy'): 'node --check of a staged driver copy: DOCTOR_TIMEOUT',
    ('install.py', 'command'): 'specify CLI during install (dispatch and install locks held)',
    ('install.py', 'progress_accepts'): 'progress hooks --help',
    ('install.py', 'wire_progress'): 'progress hook wiring',
    ('install.py', 'wire_illustrate'): 'illustrate wiring',
    ('wf_receipts.py', 'ready_checks'): 'Ready check commands',
    ('workflow.py', 'sync_project'): 'Project Sync (outside the lock, the CLI still hangs)',
}


def unbounded_calls():
    found = set()
    for path in sorted(SCRIPTS.glob('*.py')):
        def visit(node, function):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function = node.name
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ('run', 'Popen') and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == 'subprocess'
                    and not any(k.arg == 'timeout' for k in node.keywords)):
                found.add((path.name, function))
            for child in ast.iter_child_nodes(node):
                visit(child, function)
        visit(ast.parse(path.read_text(encoding='utf-8')), '<module>')
    return found


class BoundedSubprocessTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.dispatch = self.root / '.specify/workflow/runtime/dispatch.lock'
        self.feature = self.root / 'specs/001-demo/workflow/run.lock'

    def assert_bounded(self, started, limit=30):
        self.assertLess(time.monotonic() - started, limit)
        self.assertFalse(self.dispatch.exists() or self.feature.exists(), 'a lock outlived the timed-out call')

    def test_no_unbounded_subprocess_outside_the_allowlist(self):
        found = unbounded_calls()
        self.assertEqual(sorted(found - set(ALLOWED) - set(PENDING)), [], 'add timeout= or justify it in ALLOWED')
        self.assertEqual(sorted((set(ALLOWED) | set(PENDING)) - found), [], 'stale allowlist entry: remove it')

    def test_memory_helper_timeout_blocks_the_handoff_and_releases_dispatch_lock(self):
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, timeout=60)
        w.write(self.root / '.specify/extensions/.registry', {'extensions': {'memory': {'enabled': True}}})
        archive = self.root / '.specify/extensions/memory/scripts/archive.py'
        archive.parent.mkdir(parents=True)
        archive.write_text(SLEEP + '\n', encoding='utf-8')
        started = time.monotonic()
        with patch.object(mh, 'MEMORY_HELPER_TIMEOUT', 1):
            result = mh.handoff(self.root, 'session', run_class=w.Run)
        self.assertEqual((result['ok'], result['status']), (False, 'blocked'))
        self.assertTrue(result['reason'].startswith('MEMORY_HELPER_TIMEOUT: '), result['reason'])
        self.assertIn('archive.py --root . pending', result['reason'])
        self.assert_bounded(started)

    def test_doctor_probe_timeout_is_named_and_releases_both_locks(self):
        driver = self.root / 'delegate.mjs'
        driver.write_text(SLEEP + '\n', encoding='utf-8')
        real = subprocess.run

        def node(args, **kwargs):  # `node --version` answers; the driver's doctor hangs
            if args[1:] == ['--version']:
                return subprocess.CompletedProcess(args, 0, 'v20.0.0\n', '')
            return real(args, **kwargs)

        started = time.monotonic()
        with patch.object(delegation.shutil, 'which', return_value=sys.executable), \
             patch.object(delegation, 'inspect_skill', return_value={'ok': True, 'driver': str(driver)}), \
             patch.object(delegation, 'DOCTOR_TIMEOUT', 1), patch.object(subprocess, 'run', node):
            with w.locked(self.dispatch), w.locked(self.feature):
                result = delegation.doctor(self.root, 'codex')
        self.assertEqual((result['ok'], result['error']), (False, 'DELEGATE_DOCTOR_TIMEOUT'))
        self.assertIn('delegation.py doctor', result['action'])
        self.assertEqual(delegation.health_error(result).split(':')[0], 'DELEGATE_DOCTOR_TIMEOUT')
        self.assert_bounded(started)

    def test_diff_review_timeout_is_named_and_releases_the_feature_lock(self):
        started = time.monotonic()
        hung = [sys.executable, '-c', SLEEP]
        with patch.object(sys.modules['wf_receipts'], 'diff_review_command', return_value=hung):
            with self.assertRaisesRegex(w.WorkflowError, r'^DIFF_REVIEW_TIMEOUT: .* within 1 s .*rerun'):
                with w.locked(self.dispatch), w.locked(self.feature):
                    w.diff_review_sha256(self.root, 'a' * 40, 'b' * 40, timeout=1)
        self.assert_bounded(started)


if __name__ == '__main__':
    unittest.main()
