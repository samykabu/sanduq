"""B7: project-sync (Bash and PowerShell) --summary/--json contract.

project-sync.sh/.ps1 have no dedicated tests/ directory (the `project`
extension is not in ci.yml's `python -m unittest discover` matrix), so their
CLI is exercised here, matching the established pattern for assure_state.py
and manual_state.py above.

Both scripts degrade gracefully (log + exit 0) before ever touching GitHub
when a precondition is missing (`gh`/`jq` not installed, not authenticated,
or no `config.json`). A fresh git repository with no `.specify` config
guarantees that graceful-skip path regardless of which precondition is the
first to be missing on the machine running the test, so these tests assert
the *shape* of the skip line rather than its exact reason text.

Under `--summary`/`-Summary`, stdout must be exactly one line: the run log
(bash `log`/`warn`, PowerShell `Write-Log`) moves off stdout, a graceful skip
prints `skipped reason=...` (never `ok` — a skip is not success), a genuine
mid-run failure (bash `set -e`, PowerShell `$ErrorActionPreference = 'Stop'`)
is caught and reported as one `error ...` line, and a real success prints
`ok issue=<n> status=<status> created=<n> closed=<n>`.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SH = ROOT / 'project/scripts/bash/project-sync.sh'
PS1 = ROOT / 'project/scripts/powershell/project-sync.ps1'

# A minimal but complete project config; the exact ids/columns do not matter,
# only that config.json is valid enough to pass the "not configured" skip
# gate and drive a real (fake-gh-backed) run through to the final summary.
CONFIG_JSON = """{
  "projectNumber": 1, "projectId": "PVT_1", "owner": "acme", "ownerType": "org",
  "statusFieldId": "F1", "stateFile": ".specify/project-sync-state.json",
  "statusOrder": ["Backlog", "Ready", "Done"],
  "statusOptions": {"Backlog": "OPT_0", "Ready": "OPT_1", "Done": "OPT_2"},
  "phaseToStatus": {"open": "Backlog", "ready": "Ready", "done": "Done"},
  "subIssues": {"enabled": false, "maxCount": 0, "warnAboveCount": 0, "labels": [],
                "titleTemplate": "{slug} {taskId}: {desc}"},
  "parentIssue": {"labels": ["spec-feature"], "titleTemplate": "[{slug}] {title}"}
}
"""

# A fake `gh` (bash script) covering exactly the subcommands a `--phase open`
# run makes on a brand new feature with no prior state: auth check, the
# GraphQL-budget probe, the parent-issue search/create, and the Project
# item-add/item-edit. Nothing here mutates real GitHub; there is no GitHub.
FAKE_GH_SH = """#!/usr/bin/env bash
a1="$1"; a2="$2"
if [ "$a1" = "auth" ] && [ "$a2" = "status" ]; then echo "Logged in to github.com as fixture"; echo "Token scopes: 'project', 'repo'"; exit 0; fi
if [ "$a1" = "issue" ] && [ "$a2" = "list" ]; then echo "[]"; exit 0; fi
if [ "$a1" = "label" ] && [ "$a2" = "create" ]; then exit 0; fi
if [ "$a1" = "issue" ] && [ "$a2" = "create" ]; then echo "https://github.com/acme/app/issues/42"; exit 0; fi
if [ "$a1" = "issue" ] && [ "$a2" = "view" ]; then echo '{"id":"NODE_42"}'; exit 0; fi
if [ "$a1" = "project" ] && [ "$a2" = "item-add" ]; then echo '{"id":"ITEM_1"}'; exit 0; fi
if [ "$a1" = "project" ] && [ "$a2" = "item-edit" ]; then exit 0; fi
exit 1
"""

# Same fixture as FAKE_GH_SH, but as a PowerShell function overriding `gh` in
# the current scope: portable across Windows/Linux pwsh (a `.cmd`/`.sh` fake
# executable is not), and it is the same technique this repo's own
# smoke_project_init.py already uses for project-init.ps1.
FAKE_GH_PS1_FUNCTION = """
function global:gh {
    $global:LASTEXITCODE = 0
    $a = $args
    if ($a[0] -eq 'auth' -and $a[1] -eq 'status') { 'Logged in to github.com as fixture'; "Token scopes: 'project', 'repo'"; return }
    if ($a[0] -eq 'api' -and $a[1] -eq 'graphql') { '5000'; return }
    if ($a[0] -eq 'issue' -and $a[1] -eq 'list') { '[]'; return }
    if ($a[0] -eq 'label' -and $a[1] -eq 'create') { return }
    if ($a[0] -eq 'issue' -and $a[1] -eq 'create') { 'https://github.com/acme/app/issues/42'; return }
    if ($a[0] -eq 'issue' -and $a[1] -eq 'view') { '{"id":"NODE_42"}'; return }
    if ($a[0] -eq 'project' -and $a[1] -eq 'item-add') { '{"id":"ITEM_1"}'; return }
    if ($a[0] -eq 'project' -and $a[1] -eq 'item-edit') { return }
    $global:LASTEXITCODE = 1
}
"""


def bash_path_candidates(path):
    """POSIX form first; on a Windows host whose `bash` on PATH is actually a
    WSL launcher (rather than Git-Bash/MSYS), that process needs the drive
    mounted under /mnt/<letter> instead of a bare drive-letter path."""
    posix = path.as_posix()
    candidates = [posix]
    match = re.match(r'^([A-Za-z]):(/.*)$', posix)
    if match:
        candidates.append(f'/mnt/{match.group(1).lower()}{match.group(2)}')
    return candidates


def run_bash_script(script, args, cwd, env=None):
    result = None
    for candidate in bash_path_candidates(script):
        result = subprocess.run(['bash', candidate, *args], cwd=cwd, text=True, capture_output=True, env=env)
        if not (result.returncode == 127 and 'No such file or directory' in result.stderr):
            return result
    return result


def write_script(path, text):
    """Write an executable fake tool with LF-only line endings, regardless of
    host OS: a native Windows Python's default text-mode write translates
    '\\n' to '\\r\\n', which corrupts the shebang line ('#!/usr/bin/env
    bash\\r') and makes the interpreter unresolvable ("bash\\r: No such file
    or directory")."""
    with open(path, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    path.chmod(0o755)


def prepend_path(fakebin):
    """The real environment with `fakebin` prepended to PATH, so a fake `gh`
    is found first while every other tool (jq, git, ...) still resolves
    normally — replacing the environment outright risks breaking whatever
    PATH-translation the host's `bash` on PATH relies on internally."""
    env = dict(os.environ)
    env['PATH'] = str(fakebin) + os.pathsep + env.get('PATH', '')
    return env


def bash_has(cwd, tool):
    """Whether the *bash actually used to run the script* (which, depending
    on the host, may resolve a different PATH than this Python process) sees
    `tool` on its own PATH."""
    result = subprocess.run(['bash', '-lc', f'command -v {tool}'], cwd=cwd, text=True, capture_output=True)
    return result.returncode == 0


class ProjectSyncSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, capture_output=True)

    # -- flag conflict -----------------------------------------------------

    def test_bash_summary_and_json_together_is_rejected(self):
        if not shutil.which('bash'):
            self.skipTest('bash not available')
        result = run_bash_script(SH, ['--phase', 'open', '--summary', '--json'], self.root)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout.strip(), 'error --summary and --json cannot be combined')

    def test_pwsh_summary_and_json_together_is_rejected(self):
        if not shutil.which('pwsh'):
            self.skipTest('pwsh not available')
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(PS1), '-Phase', 'open', '-Summary', '-Json'],
                                 cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        # The PowerShell message names its own -Summary/-Json parameters.
        self.assertEqual(result.stdout.strip(), 'error -Summary and -Json cannot be combined')

    # -- graceful skip: exactly one stdout line, never "ok" -----------------

    def test_bash_summary_skip_is_one_line_and_never_ok(self):
        if not shutil.which('bash'):
            self.skipTest('bash not available')
        result = run_bash_script(SH, ['--phase', 'open', '--summary'], self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        self.assertRegex(lines[0], r'^skipped reason=.+$')

    def test_pwsh_summary_skip_is_one_line_and_never_ok(self):
        if not shutil.which('pwsh'):
            self.skipTest('pwsh not available')
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(PS1), '-Phase', 'open', '-Summary'],
                                 cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        self.assertRegex(lines[0], r'^skipped reason=.+$')

    # -- mid-run failure: exactly one "error ..." line, never "ok" ----------

    def test_bash_summary_mid_run_failure_is_one_error_line(self):
        if not shutil.which('bash'):
            self.skipTest('bash not available')
        subprocess.run(['git', 'remote', 'add', 'origin', 'https://github.com/acme/app.git'],
                        cwd=self.root, check=True, capture_output=True)
        config = self.root / '.specify/extensions/project/config.json'
        config.parent.mkdir(parents=True)
        config.write_text('{}', encoding='utf-8')
        fakebin = Path(tempfile.mkdtemp())
        write_script(fakebin / 'gh', FAKE_GH_SH)
        # jq is present (passing `command -v jq`) but broken: past the skip
        # gates, the first real jq call (reading config.json) fails and, per
        # F2, must surface as one `error exit=<rc> line=<n>` line, not a raw
        # shell trace and not a stray "ok".
        write_script(fakebin / 'jq', '#!/usr/bin/env bash\nexit 1\n')
        result = run_bash_script(SH, ['--phase', 'open', '--summary'], self.root, env=prepend_path(fakebin))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        self.assertRegex(lines[0], r'^error exit=\d+ line=\d+$')
        self.assertNotIn('ok ', result.stdout)

    def test_pwsh_summary_mid_run_failure_is_one_error_line(self):
        if not shutil.which('pwsh'):
            self.skipTest('pwsh not available')
        # A malformed config.json passes the "not configured" existence
        # check (Test-Path) but fails ConvertFrom-Json, a genuine mid-run
        # terminating error under $ErrorActionPreference = 'Stop' — no fake
        # gh needed, since config parsing happens before any gh call.
        config = self.root / '.specify/extensions/project/config.json'
        config.parent.mkdir(parents=True)
        config.write_text('not valid json{', encoding='utf-8')
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(PS1), '-Phase', 'open', '-Summary'],
                                 cwd=self.root, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        self.assertTrue(lines[0].startswith('error '), result.stdout)
        self.assertNotIn('ok ', result.stdout)

    # -- real success: one "ok ..." line with counts (bash/ps1 parity) ------

    def configure_repo(self):
        subprocess.run(['git', 'config', 'user.name', 'test'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.invalid'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'remote', 'add', 'origin', 'https://github.com/acme/app.git'],
                        cwd=self.root, check=True, capture_output=True)
        config = self.root / '.specify/extensions/project/config.json'
        config.parent.mkdir(parents=True)
        config.write_text(CONFIG_JSON, encoding='utf-8')

    def test_bash_summary_success_reports_counts(self):
        if not shutil.which('bash'):
            self.skipTest('bash not available')
        if not bash_has(self.root, 'jq'):
            self.skipTest('a real jq is required to drive a full (fake-gh-backed) success run; '
                           'the flag-conflict, skip and mid-run-failure paths above do not need one')
        self.configure_repo()
        fakebin = Path(tempfile.mkdtemp())
        write_script(fakebin / 'gh', FAKE_GH_SH)
        result = run_bash_script(SH, ['--phase', 'open', '--summary'], self.root, env=prepend_path(fakebin))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        self.assertEqual(lines[0], 'ok issue=42 status=Backlog created=0 closed=0')

    def test_pwsh_summary_success_reports_counts(self):
        if not shutil.which('pwsh'):
            self.skipTest('pwsh not available')
        self.configure_repo()
        wrapper = self.root / '_wrapper.ps1'
        wrapper.write_text(FAKE_GH_PS1_FUNCTION + f"\n& '{PS1.as_posix()}' -Phase open -Summary\n", encoding='utf-8')
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(wrapper)],
                                 cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        self.assertEqual(lines[0], 'ok issue=42 status=Backlog created=0 closed=0')

    def test_pwsh_json_reports_the_same_real_run(self):
        if not shutil.which('pwsh'):
            self.skipTest('pwsh not available')
        self.configure_repo()
        wrapper = self.root / '_wrapper.ps1'
        wrapper.write_text(FAKE_GH_PS1_FUNCTION + f"\n& '{PS1.as_posix()}' -Phase open -Json\n", encoding='utf-8')
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(wrapper)],
                                 cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        import json
        payload = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(payload['issue'], 42)
        self.assertEqual(payload['status'], 'Backlog')

    def test_bash_json_summary_unaffected_by_this_session(self):
        # F8 parity: the sibling test above exercises -Json for pwsh on the
        # same fixture; this confirms the bash --json branch still reports
        # the same real run, unchanged by this session's --summary/error-trap
        # work (--json's own output format was never touched).
        if not shutil.which('bash'):
            self.skipTest('bash not available')
        if not bash_has(self.root, 'jq'):
            self.skipTest('a real jq is required to drive a full (fake-gh-backed) success run')
        self.configure_repo()
        fakebin = Path(tempfile.mkdtemp())
        write_script(fakebin / 'gh', FAKE_GH_SH)
        result = run_bash_script(SH, ['--phase', 'open', '--json'], self.root, env=prepend_path(fakebin))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        import json
        payload = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(payload['issue'], 42)
        self.assertEqual(payload['status'], 'Backlog')


if __name__ == '__main__':
    unittest.main()
