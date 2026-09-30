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
(bash `log`/`warn`, PowerShell `Write-Log`) moves off stdout — even with
`$VerbosePreference = 'Continue'`, since PowerShell's `Write-Verbose` is not
enough on its own — a graceful skip prints `skipped reason=...` (never `ok`
— a skip is not success), a genuine mid-run failure (bash `set -e`,
PowerShell `$ErrorActionPreference = 'Stop'`) is caught and reported as one
`error reason=<msg>` line (bash additionally carries `exit=<rc>` and, when
known, `line=<n>`), and a real success prints
`ok issue=<n> status=<status> created=<n> closed=<n>`.
"""
import functools
import os
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


def _git_bash_candidates():
    """Windows-only Git-Bash locations to try, ahead of a bare 'bash' lookup.

    A bare `['bash', ...]` subprocess call on Windows is resolved by
    CreateProcess's own search order (the calling process's directory,
    the current directory, the Windows system directory, the Windows
    directory, and only then PATH) rather than by walking PATH the way a
    shell would. `C:\\Windows\\System32\\bash.exe` -- the WSL launcher --
    sits in that system directory, so it wins over Git Bash even when Git
    Bash is earlier on PATH from a shell's own point of view. Passing an
    *absolute* path instead of a bare name sidesteps that search entirely.
    """
    candidates = [r'C:\Program Files\Git\bin\bash.exe']
    exec_path = subprocess.run(['git', '--exec-path'], capture_output=True, text=True)
    if exec_path.returncode == 0 and exec_path.stdout.strip():
        # git --exec-path is typically .../mingw64/libexec/git-core; the
        # matching bash.exe is two levels up, under bin/.
        sibling = Path(exec_path.stdout.strip()) / '..' / '..' / 'bin' / 'bash.exe'
        candidates.append(str(sibling))
    return candidates


def _is_system32_bash(path):
    """True when `path` resolves to the WSL launcher shim, which must never
    be picked even if it happens to run (e.g. a real distro is installed):
    it is a different OS userland, not the Windows POSIX environment
    (jq/PATH/filesystem) these tests set up and depend on."""
    system_root = os.environ.get('SystemRoot', r'C:\Windows')
    system32_bash = os.path.normcase(os.path.join(system_root, 'System32', 'bash.exe'))
    try:
        return os.path.normcase(os.path.abspath(path)) == system32_bash
    except (OSError, ValueError):
        return False


@functools.lru_cache(maxsize=1)
def find_bash():
    """A real, working POSIX bash -- never `C:\\Windows\\System32\\bash.exe`.

    Candidates are resolved to absolute paths and verified by actually
    running `<bash> -c 'echo ok'`, not merely by name: a WSL distro being
    installed would make the System32 launcher "work", but it would still
    be the wrong bash for these tests (see `_is_system32_bash`). Returns
    None, with no candidate found or working, so callers can skip with a
    clear reason instead of failing on the wrong shell.
    """
    candidates = list(_git_bash_candidates()) if os.name == 'nt' else []
    candidates.append('bash')  # last resort: POSIX hosts, or whatever PATH gives
    seen = set()
    for candidate in candidates:
        resolved = candidate if os.path.isabs(candidate) else shutil.which(candidate)
        if not resolved or os.path.normcase(resolved) in seen:
            continue
        seen.add(os.path.normcase(resolved))
        if not os.path.isfile(resolved) or _is_system32_bash(resolved):
            continue
        try:
            probe = subprocess.run([resolved, '-c', 'echo ok'], capture_output=True, text=True, timeout=10)
        except OSError:
            continue
        if probe.returncode == 0 and probe.stdout.strip() == 'ok':
            return resolved
    return None


def run_bash_script(script, args, cwd, env=None):
    bash = find_bash()
    if bash is None:
        return None
    return subprocess.run([bash, script.as_posix(), *args], cwd=cwd, text=True, capture_output=True, env=env)


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
    """Whether the *bash actually used to run the script* (the one `find_bash`
    resolves, which, depending on the host, may see a different PATH than
    this Python process) sees `tool` on its own PATH."""
    bash = find_bash()
    if bash is None:
        return False
    result = subprocess.run([bash, '-lc', f'command -v {tool}'], cwd=cwd, text=True, capture_output=True)
    return result.returncode == 0


class ProjectSyncSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, capture_output=True)

    # -- flag conflict -----------------------------------------------------

    def test_bash_summary_and_json_together_is_rejected(self):
        if not find_bash():
            self.skipTest('no working POSIX bash found (Git Bash absent; never the WSL System32 launcher)')
        result = run_bash_script(SH, ['--phase', 'open', '--summary', '--json'], self.root)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout.strip(), 'error exit=2 reason=--summary and --json cannot be combined')

    def test_pwsh_summary_and_json_together_is_rejected(self):
        if not shutil.which('pwsh'):
            self.skipTest('pwsh not available')
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(PS1), '-Phase', 'open', '-Summary', '-Json'],
                                 cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        # F11: the same `error reason=<msg>` shape as bash (which additionally
        # carries `exit=<rc>`); the message names ps1's own -Summary/-Json.
        self.assertEqual(result.stdout.strip(), 'error reason=-Summary and -Json cannot be combined')

    def test_bash_unknown_arg_warning_goes_to_stderr(self):
        # F11: an unrecognised flag is a diagnostic, not summary output, so it
        # must never land on stdout regardless of --summary/--json/neither.
        if not find_bash():
            self.skipTest('no working POSIX bash found (Git Bash absent; never the WSL System32 launcher)')
        result = run_bash_script(SH, ['--phase', 'open', '--bogus-flag', '--summary'], self.root)
        self.assertNotIn('unknown arg', result.stdout)
        self.assertIn('unknown arg: --bogus-flag', result.stderr)

    # -- graceful skip: exactly one stdout line, never "ok" -----------------

    def test_bash_summary_skip_is_one_line_and_never_ok(self):
        if not find_bash():
            self.skipTest('no working POSIX bash found (Git Bash absent; never the WSL System32 launcher)')
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

    def test_pwsh_summary_stdout_is_one_line_even_with_verbose_preference(self):
        # F10: Write-Verbose alone is not enough — it still reaches stdout
        # when the caller sets -Verbose or $VerbosePreference = 'Continue'.
        # Write-Log must route to [Console]::Error instead, which neither can
        # affect, so stdout stays exactly the one summary line regardless.
        if not shutil.which('pwsh'):
            self.skipTest('pwsh not available')
        wrapper = self.root / '_verbose_wrapper.ps1'
        wrapper.write_text(
            "$VerbosePreference = 'Continue'\n"
            f"& '{PS1.as_posix()}' -Phase open -Summary\n",
            encoding='utf-8')
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(wrapper)],
                                 cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        self.assertRegex(lines[0], r'^skipped reason=.+$')

    # -- mid-run failure: exactly one "error ..." line, never "ok" ----------

    def test_bash_summary_mid_run_failure_is_one_error_line(self):
        # A broken (but present) jq fails on the first real config read, a
        # raw command failure with no preceding warn(): reason falls back to
        # "unknown" and the ERR trap still knows the failing line.
        if not find_bash():
            self.skipTest('no working POSIX bash found (Git Bash absent; never the WSL System32 launcher)')
        subprocess.run(['git', 'remote', 'add', 'origin', 'https://github.com/acme/app.git'],
                        cwd=self.root, check=True, capture_output=True)
        config = self.root / '.specify/extensions/project/config.json'
        config.parent.mkdir(parents=True)
        config.write_text('{}', encoding='utf-8')
        fakebin = Path(tempfile.mkdtemp())
        write_script(fakebin / 'gh', FAKE_GH_SH)
        write_script(fakebin / 'jq', '#!/usr/bin/env bash\nexit 1\n')
        result = run_bash_script(SH, ['--phase', 'open', '--summary'], self.root, env=prepend_path(fakebin))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        self.assertRegex(lines[0], r'^error exit=\d+ reason=unknown line=\d+$')
        self.assertNotIn('ok ', result.stdout)

    def test_bash_summary_warn_then_exit_reports_last_warn_as_reason(self):
        # F9: `warn "..."; exit 1` (e.g. project-sync.sh's managed-mode
        # parent-binding checks) has no failing command for the ERR trap to
        # see, so line stays unknown — but LAST_WARN (set by warn() right
        # before the exit) still supplies a real reason, not "unknown".
        # Reaching this branch needs config.json parsed for real (managed
        # mode is checked only after PROJ_NUM/PROJ_ID/... are read), so this
        # needs a genuine jq like the success-path tests above.
        if not find_bash():
            self.skipTest('no working POSIX bash found (Git Bash absent; never the WSL System32 launcher)')
        if not bash_has(self.root, 'jq'):
            self.skipTest('a real jq is required to reach the managed-mode check')
        self.configure_repo()
        (self.root / '.specify').mkdir(exist_ok=True)
        (self.root / '.specify/workflow.yml').write_text('schema: 1\n', encoding='utf-8')  # -> MANAGED=1
        # No specs/<feature>/scope-source.json: the managed branch's first
        # check ("Managed workflow requires scope-source.json") fires.
        fakebin = Path(tempfile.mkdtemp())
        write_script(fakebin / 'gh', FAKE_GH_SH)
        result = run_bash_script(SH, ['--phase', 'open', '--summary', '--feature', 'example'],
                                  self.root, env=prepend_path(fakebin))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        self.assertEqual(lines[0], 'error exit=1 reason=Managed workflow requires scope-source.json')

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
        # F11: same `error reason=<msg>` shape as bash.
        self.assertTrue(lines[0].startswith('error reason='), result.stdout)
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
        if not find_bash():
            self.skipTest('no working POSIX bash found (Git Bash absent; never the WSL System32 launcher)')
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
        if not find_bash():
            self.skipTest('no working POSIX bash found (Git Bash absent; never the WSL System32 launcher)')
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
