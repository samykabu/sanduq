"""AHMED-01 and SAMY-12: an active claim records its owner, `recover` refuses a live owner with CLAIM_OWNER_ALIVE,
`status` shows owner liveness, and the other-feature refusal names the exact recover command."""
import json
import os
import signal
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow as w  # noqa: E402
from test_receipt_contract import Harness  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
SCRIPT = SCRIPTS / 'workflow.py'
# Claims in-process with its own pid as the owner, prints the token, then sleeps until killed.
CLAIMER = '''
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import workflow as w
claim = w.Run(Path(sys.argv[2]), sys.argv[3]).claim(json.loads(sys.argv[4]), owner_pid=os.getpid())
print(claim['token'], os.getpid(), flush=True)
time.sleep(600)
'''


def clean_env():
    return {key: value for key, value in os.environ.items() if not key.startswith('SANDUQ_')}


class ClaimLivenessTests(Harness):
    def status(self, run):
        return w.native_run_status(self.root, run.relative, run.load(allow_branch_change=True), [])['active']

    def cli(self, *args):
        done = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), *args],
                              capture_output=True, text=True, encoding='utf-8', env=clean_env())
        return done.returncode, json.loads(done.stdout)

    def test_recover_is_refused_while_the_claiming_process_lives_and_allowed_once_it_is_killed(self):
        run = self.run_object()
        claimer = subprocess.Popen([sys.executable, '-c', CLAIMER, str(SCRIPTS), str(self.root), self.feature,
                                    json.dumps(self.usage())], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=clean_env())
        self.addCleanup(lambda: claimer.poll() is None and claimer.kill())
        line = claimer.stdout.readline().split()
        self.assertTrue(line, claimer.stderr.read() if claimer.poll() is not None else 'no token')
        # A Windows venv python.exe is a launcher, so the interpreter reports its own pid.
        token, pid = line[0], int(line[1])
        self.assertEqual(run.load()['active']['pid'], pid)
        self.assertEqual(self.status(run)['owner'], 'alive')
        self.assertEqual(self.status(run)['last_activity'], '0 min ago')
        code, result = self.cli('recover', '--feature', self.feature, '--token', token, '--reason', 'second session')
        self.assertEqual(code, 1)
        self.assertIn('CLAIM_OWNER_ALIVE', result['error'])
        self.assertIn('pid ' + str(pid), result['error'])
        self.assertIn('workflow.py status --feature ' + self.feature, result['error'])
        self.assertIn('--force-live-owner', result['error'])
        self.assertEqual(run.load()['active']['token'], token)
        os.kill(pid, signal.SIGTERM)  # TerminateProcess on Windows
        claimer.wait(timeout=30)
        claimer.stdout.close()
        claimer.stderr.close()
        self.assertEqual(self.status(run)['owner'], 'dead')
        code, result = self.cli('recover', '--feature', self.feature, '--token', token, '--reason', 'owner killed')
        self.assertEqual(code, 0, result)
        self.assertTrue(result['released'])
        self.assertNotIn('forced_live_owner', run.load()['recoveries'][-1])

    def test_a_cli_claim_is_protected_by_its_heartbeat(self):
        run = self.run_object()
        claim = run.claim(self.usage())  # no owner pid: the CLI exits at once
        self.assertIsNone(claim['pid'])
        self.assertEqual(claim['heartbeat_at'], claim['claimed_at'])
        self.assertEqual(self.status(run)['owner'], 'unknown')
        with self.assertRaisesRegex(w.WorkflowError, 'CLAIM_OWNER_ALIVE: .*last activity 0 min ago'):
            run.release_ownership(claim['token'], 'second session')
        with self.assertRaisesRegex(w.WorkflowError, 'CLAIM_OWNER_ALIVE'):
            run.release_ownership(claim['token'], 'second session', force_live_owner='  ')
        result = run.release_ownership(claim['token'], 'lost session', force_live_owner='the user closed that window')
        self.assertTrue(result['released'])
        forced = run.load()['recoveries'][-1]['forced_live_owner']
        self.assertEqual((forced['reason'], forced['owner']), ('the user closed that window', 'unknown'))

    def test_a_stale_heartbeat_allows_recover_and_pause_refreshes_it(self):
        run = self.run_object()
        claim = run.claim(self.usage())
        state = w.read(run.path)
        old = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        state['active']['heartbeat_at'] = old
        w.write(run.path, state)
        self.assertEqual(self.status(run)['last_activity'], '20 min ago')
        with w.locked(run.lock):
            run.checkpoint(run.load(), 'pause for the test')
        self.assertNotEqual(run.load()['active']['heartbeat_at'], old)
        with self.assertRaisesRegex(w.WorkflowError, 'CLAIM_OWNER_ALIVE'):
            run.release_ownership(claim['token'], 'second session')
        state = w.read(run.path)
        state['active']['heartbeat_at'] = old
        w.write(run.path, state)
        self.assertTrue(run.release_ownership(claim['token'], 'owner gone for 20 minutes')['released'])

    def test_heartbeat_refreshes_activity(self):
        # A rejected completion leaves the claim byte-identical (test_lifecycle), so it is no heartbeat.
        run = self.run_object()
        claim = run.claim(self.usage())
        old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        state = w.read(run.path)
        state['active']['heartbeat_at'] = old
        w.write(run.path, state)
        self.assertTrue(run.heartbeat(claim['token']))
        self.assertNotEqual(run.load()['active']['heartbeat_at'], old)
        self.assertFalse(run.heartbeat('another-token'))

    def test_legacy_claim_without_owner_fields_keeps_the_old_recover(self):
        run = self.run_object()
        claim = run.claim(self.usage())
        state = w.read(run.path)
        for key in ('pid', 'host', 'heartbeat_at'):
            state['active'].pop(key)
        w.write(run.path, state)
        self.assertEqual(self.status(run)['owner'], 'unknown')
        self.assertTrue(run.release_ownership(claim['token'], 'legacy claim')['released'])

    def test_other_feature_refusal_names_stage_session_and_recover_command(self):
        run = self.run_object()
        other = self.root / 'specs/002-other/workflow/checkpoint.json'
        w.write(other, {'active': {'stage': 'plan', 'token': 'tok-1', 'claimed_at': '2026-10-27T10:00:00+00:00',
                                   'session_id': 'other-session'}})
        with self.assertRaises(w.WorkflowError) as caught:
            run.claim(self.usage())
        message = str(caught.exception)
        self.assertIn('OTHER_FEATURE_OWNERSHIP_RECOVERY_REQUIRED: specs/002-other has an active plan claim', message)
        self.assertIn('claimed_at 2026-10-27T10:00:00+00:00, session other-session', message)
        self.assertIn('workflow.py recover --feature specs/002-other --token tok-1 --reason', message)


if __name__ == '__main__':
    unittest.main()
