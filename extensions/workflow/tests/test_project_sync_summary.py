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
the *shape* of the skip line (`ok skipped=1 ...`) rather than its exact
reason text.
"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SH = ROOT / 'project/scripts/bash/project-sync.sh'
PS1 = ROOT / 'project/scripts/powershell/project-sync.ps1'


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


def run_bash_script(script, args, cwd):
    result = None
    for candidate in bash_path_candidates(script):
        result = subprocess.run(['bash', candidate, *args], cwd=cwd, text=True, capture_output=True)
        if not (result.returncode == 127 and 'No such file or directory' in result.stderr):
            return result
    return result


class ProjectSyncSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, capture_output=True)

    def test_bash_summary_and_json_together_is_rejected(self):
        if not shutil.which('bash'):
            self.skipTest('bash not available')
        result = run_bash_script(SH, ['--phase', 'open', '--summary', '--json'], self.root)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout.strip(), 'error --summary and --json cannot be combined')

    def test_bash_summary_reports_ok_on_graceful_skip(self):
        if not shutil.which('bash'):
            self.skipTest('bash not available')
        result = run_bash_script(SH, ['--phase', 'open', '--summary'], self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout.strip().splitlines()[-1], r'^ok skipped=1( reason=.*)?$')

    def test_pwsh_summary_and_json_together_is_rejected(self):
        if not shutil.which('pwsh'):
            self.skipTest('pwsh not available')
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(PS1), '-Phase', 'open', '-Summary', '-Json'],
                                 cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout.strip(), 'error --summary and --json cannot be combined')

    def test_pwsh_summary_reports_ok_on_graceful_skip(self):
        if not shutil.which('pwsh'):
            self.skipTest('pwsh not available')
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(PS1), '-Phase', 'open', '-Summary'],
                                 cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout.strip().splitlines()[-1], r'^ok skipped=1( reason=.*)?$')


if __name__ == '__main__':
    unittest.main()
