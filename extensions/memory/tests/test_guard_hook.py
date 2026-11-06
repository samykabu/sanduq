"""The opt-in PreToolUse guard that protects an active archive run on Claude Code and Codex."""
import io
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr

GUARD = Path(__file__).resolve().parents[1] / "hooks/guard.py"
guard = runpy.run_path(str(GUARD))


class GuardHookTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sanduq-memory-guard-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.policy(True)
        self.state = self.root / ".git/sanduq-memory"
        self.state.mkdir(parents=True)
        (self.state / "active.json").write_text('{"run_id": "' + "a" * 32 + '"}')

    def policy(self, value):
        path = self.root / ".specify/memory-policy.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema_version": 1, "guard_hooks": value}))

    def run_guard(self, tool, **tool_input):
        payload = json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": str(self.root)})
        error = io.StringIO()
        with redirect_stderr(error):
            code = guard["main"](io.StringIO(payload), {})
        return code, error.getvalue()

    def test_active_run_denies_history_rewriting_git_verbs_and_names_the_way_out(self):
        for command in ("git push origin main", "git -C . reset --hard HEAD", "git stash", "cd x && git clean -fd"):
            code, message = self.run_guard("Bash", command=command)
            self.assertEqual(2, code, command)
            self.assertIn("candidate.json", message)
            self.assertIn("references/recovery.md", message)
        for command in ("git status", "git stash list", "git commit -m x", "echo git push"):
            self.assertEqual(0, self.run_guard("Bash", command=command)[0], command)

    def test_active_run_denies_writes_under_specs_memory_only(self):
        code, message = self.run_guard("Write", file_path=str(self.root / "specs/memory/entries/PM-x.md"))
        self.assertEqual(2, code)
        self.assertIn("candidate.json", message)
        self.assertEqual(2, self.run_guard("Edit", file_path="specs/memory/INDEX.md")[0])
        patch = "*** Begin Patch\n*** Update File: specs/memory/taxonomy.json\n@@\n-a\n+b\n*** End Patch\n"
        self.assertEqual(2, self.run_guard("apply_patch", command=patch)[0])
        self.assertEqual(0, self.run_guard("Write", file_path="specs/memory-notes.md")[0])
        self.assertEqual(0, self.run_guard("Write", file_path="specs/001-x/spec.md")[0])

    def test_guard_allows_everything_when_off_idle_or_given_unexpected_input(self):
        (self.state / "active.json").unlink()
        self.assertEqual(0, self.run_guard("Bash", command="git push")[0])
        (self.state / "active.json").write_text("{}")
        for value in (False, "true"):
            self.policy(value)
            self.assertEqual(0, self.run_guard("Bash", command="git push")[0])
        self.assertEqual(0, guard["main"](io.StringIO("not json"), {}))
        self.assertEqual(0, guard["main"](io.StringIO("[]"), {}))


if __name__ == "__main__":
    unittest.main()
