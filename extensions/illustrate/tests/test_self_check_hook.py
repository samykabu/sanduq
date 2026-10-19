"""The opt-in Illustrate PostToolUse hook: a no-op until `illustrate.hooks.self_check: true`, then reports the first
failure for Claude writes and Codex `apply_patch` payloads; and its install|uninstall|status management CLI."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

EXT_DIR = Path(__file__).resolve().parent.parent
HOOK = EXT_DIR / "hooks" / "self_check_hook.py"
spec = importlib.util.spec_from_file_location("self_check_hook", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

# A minimal static diagram that passes self_check.py, verify-geometry.py and the default theme.
GOOD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>T</title>
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400&display=swap" rel="stylesheet">
  <style>body { background: #f5f5f5; }</style>
</head>
<body>
<svg viewBox="0 0 100 50" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="t-title t-desc">
  <title id="t-title">Title</title><desc id="t-desc">Description.</desc>
  <rect x="1" y="1" width="60" height="40" fill="#f5f5f5"/>
</svg>
</body>
</html>
"""
BAD = GOOD.replace("<body>", '<body onload="fetch(1)">', 1)
ON = "illustrate:\n  hooks:\n    self_check: true\n"


def run(root: Path, payload: dict) -> tuple[int, str]:
    stderr = io.StringIO()
    old, sys.stderr = sys.stderr, stderr
    try:
        code = hook.main(io.StringIO(json.dumps(payload)), {"CLAUDE_PROJECT_DIR": str(root)})
    finally:
        sys.stderr = old
    return code, stderr.getvalue()


def patch(*sections: str) -> dict:
    text = "*** Begin Patch\n" + "".join(sections) + "*** End Patch\n"
    return {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "tool_input": {"command": text}}


def temp_root(case: unittest.TestCase) -> Path:
    root = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, root, ignore_errors=True)
    return root


class SelfCheckHook(unittest.TestCase):
    def project(self, policy: str | None) -> Path:
        root = temp_root(self)
        if policy is not None:
            (root / ".specify").mkdir()
            (root / ".specify" / "workflow.yml").write_text(policy, encoding="utf-8")
        (root / "bad.html").write_text(BAD, encoding="utf-8")
        (root / "good.html").write_text(GOOD, encoding="utf-8")
        return root

    @staticmethod
    def write(name: str) -> dict:
        return {"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": name, "content": "x"}}

    def test_no_op_when_the_key_is_off_or_the_policy_is_missing(self):
        for policy in (None, "", "illustrate:\n  hooks:\n    self_check: false\n", "illustrate: {}\n"):
            for payload in (self.write("bad.html"), patch("*** Add File: bad.html\n+x\n")):
                with self.subTest(policy=policy, tool=payload["tool_name"]):
                    self.assertEqual(run(self.project(policy), payload), (0, ""))

    def test_key_on_reports_the_first_failure_and_passes_a_clean_diagram(self):
        root = self.project(ON)
        code, message = run(root, self.write("bad.html"))
        self.assertEqual(code, 2)
        self.assertIn("self_check.py: ", message)
        self.assertIn("executable attribute", message)
        self.assertEqual(message.count("\n"), 1, message)
        self.assertEqual(run(root, self.write("good.html"))[0], 0)
        # Not a diagram, not an HTML file, another tool, no input: allowed without running anything.
        (root / "page.html").write_text("<p>no svg</p>", encoding="utf-8")
        self.assertEqual(run(root, self.write("page.html"))[0], 0)
        self.assertEqual(run(root, self.write("bad.htm"))[0], 0)
        self.assertEqual(run(root, {**self.write("bad.html"), "tool_name": "Bash"})[0], 0)
        self.assertEqual(run(root, {"tool_name": "Write"})[0], 0)

    def test_codex_apply_patch_checks_every_added_updated_and_moved_html(self):
        root = self.project(ON)
        (root / "moved.html").write_text(BAD, encoding="utf-8")
        several = patch("*** Add File: good.html\n+x\n", "*** Update File: notes.md\n@@\n-a\n+b\n",
                        "*** Update File: old.html\n*** Move to: moved.html\n@@\n-a\n+b\n")
        self.assertEqual(hook.written_paths(several), ["good.html", "notes.md", "old.html", "moved.html"])
        code, message = run(root, several)
        self.assertEqual(code, 2)
        self.assertIn("moved.html", message)
        # Every file of a clean patch passes; a moved file's old path is gone and drops out; a deletion is not a write.
        self.assertEqual(run(root, patch("*** Update File: gone.html\n*** Move to: good.html\n", "*** Add File: good.html\n+x\n")), (0, ""))
        self.assertEqual(run(root, patch("*** Delete File: bad.html\n")), (0, ""))
        # The patch may arrive as a bare string or an argv list.
        self.assertEqual(run(root, {"tool_name": "apply_patch", "tool_input": "*** Begin Patch\n*** Update File: bad.html\n"})[0], 2)
        self.assertEqual(run(root, {"tool_name": "apply_patch", "tool_input": {"cmd": ["apply_patch", "*** Add File: bad.html\n"]}})[0], 2)


CLAUDE_UNRELATED = {
    "permissions": {"allow": ["Bash(git status)"]},
    "hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "guard.sh"}]}],
        "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "fmt.sh", "timeout": 5}]}],
    },
}
SPECKIT_CLAUDE = {"type": "command", "timeout": 65, "__speckit_event__": True,
                  "command": 'python3 "${CLAUDE_PROJECT_DIR}/.specify/events.py" speckit.illustrate.hook post_tool_use 60'}
SPECKIT_TOML = """[[hooks.PostToolUse]]
matcher = "Write|Edit"

[[hooks.PostToolUse.hooks]]
type = "command"
command = "python3 .specify/events.py speckit.illustrate.hook post_tool_use 60"
timeout = 65
speckit_marker = true

"""
OTHER_TOML = """model = "o4"

[[hooks.Stop]]
matcher = "*"

[[hooks.Stop.hooks]]
type = "command"
command = "python3 .specify/events.py speckit.progress.hook-stop stop 10"
timeout = 15
speckit_marker = true

"""


class ManagementCli(unittest.TestCase):
    def project(self) -> Path:
        root = temp_root(self)
        installed = root / ".specify" / "extensions" / "illustrate" / "hooks"
        installed.mkdir(parents=True)
        shutil.copy2(HOOK, installed / HOOK.name)
        return root

    def cli(self, root: Path, *args: str, script: Path | None = None) -> subprocess.CompletedProcess:
        script = script or root / ".specify" / "extensions" / "illustrate" / "hooks" / HOOK.name
        return subprocess.run([sys.executable, str(script), *args, "--root", str(root), "--json"],
                              capture_output=True, text=True)

    def ok(self, root: Path, *args: str) -> dict:
        done = self.cli(root, *args)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    @staticmethod
    def write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def assert_script_exists(self, root: Path, command: str) -> None:
        script = command.split("'")[3]  # the path inside the launcher's os.path.join
        self.assertTrue((root / script).is_file(), command)

    @staticmethod
    def launch(root: Path, command: str, payload: dict, claude: bool) -> subprocess.CompletedProcess:
        """Run the installed command as the host would: `<python> -c "<launcher>" <tag>`, payload on stdin."""
        _, code, tag = command.split('"')
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        if claude:
            env["CLAUDE_PROJECT_DIR"] = str(root)
        return subprocess.run([sys.executable, "-c", code, tag.strip()], input=json.dumps(payload), capture_output=True,
                              text=True, cwd=str(root if not claude else root.parent), env=env)

    def test_installed_command_runs_the_script_and_is_inert_once_it_is_gone(self):
        root = self.project()
        shutil.copytree(EXT_DIR / "skill" / "scripts", root / ".specify" / "extensions" / "illustrate" / "skill" / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__", "vendor"))
        (root / ".specify" / "workflow.yml").write_text(ON, encoding="utf-8")
        (root / "bad.html").write_text(BAD, encoding="utf-8")
        write = {"tool_name": "Write", "tool_input": {"file_path": "bad.html"}}
        for host in ("claude", "codex"):
            self.ok(root, "install", "--host", host)
        claude = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        codex = json.loads((root / ".codex" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        for command, is_claude in ((claude, True), (codex, False)):
            with self.subTest(claude=is_claude):
                done = self.launch(root, command, write, is_claude)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn("executable attribute", done.stderr)
        # `specify extension remove illustrate` without uninstall: the entries stay but do nothing.
        shutil.rmtree(root / ".specify" / "extensions" / "illustrate")
        for command, is_claude in ((claude, True), (codex, False)):
            with self.subTest(claude=is_claude, removed=True):
                done = self.launch(root, command, write, is_claude)
                self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))

    def test_claude_install_uninstall_keeps_unrelated_hooks_and_drops_the_dispatcher(self):
        root = self.project()
        settings = root / ".claude" / "settings.json"
        fixture = json.loads(json.dumps(CLAUDE_UNRELATED))
        fixture["hooks"]["PostToolUse"].append({"matcher": "Write|Edit", "hooks": [SPECKIT_CLAUDE]})
        fixture["hooks"]["PostToolUse"][0]["hooks"].append(dict(SPECKIT_CLAUDE))  # shares a group with an unrelated hook
        self.write_json(settings, fixture)

        self.assertEqual(self.ok(root, "install", "--host", "claude"),
                         {"host": "claude", "file": ".claude/settings.json", "added": 1, "removed": 2, "needs_approval": False})
        data = json.loads(settings.read_text(encoding="utf-8"))
        self.assertNotIn("speckit.illustrate.hook", settings.read_text(encoding="utf-8"))
        self.assertEqual(data["permissions"], CLAUDE_UNRELATED["permissions"])
        self.assertEqual(data["hooks"]["PreToolUse"], CLAUDE_UNRELATED["hooks"]["PreToolUse"])
        self.assertEqual(data["hooks"]["PostToolUse"][0], CLAUDE_UNRELATED["hooks"]["PostToolUse"][0])
        ours = data["hooks"]["PostToolUse"][1]
        self.assertEqual(ours["matcher"], "Write|Edit|MultiEdit")
        self.assertIn("'.specify/extensions/illustrate/hooks/self_check_hook.py'", ours["hooks"][0]["command"])
        self.assertTrue(ours["hooks"][0]["command"].endswith(" --managed-by=sanduq-illustrate"))
        self.assert_script_exists(root, ours["hooks"][0]["command"])

        before = settings.read_bytes()
        self.assertEqual(self.ok(root, "install", "--host", "claude")["added"], 0)
        self.assertEqual(settings.read_bytes(), before, "a rerun changes nothing")
        self.assertTrue(self.ok(root, "status", "--host", "claude")["installed"])

        self.assertEqual(self.ok(root, "uninstall", "--host", "claude"),
                         {"host": "claude", "file": ".claude/settings.json", "added": 0, "removed": 1, "needs_approval": False})
        self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), CLAUDE_UNRELATED)
        before = settings.read_bytes()
        self.assertEqual(self.ok(root, "uninstall", "--host", "claude")["removed"], 0)
        self.assertEqual(settings.read_bytes(), before)
        self.assertFalse(self.ok(root, "status", "--host", "claude")["installed"])

    def test_codex_install_uninstall_cleans_config_toml_and_asks_for_approval(self):
        root = self.project()
        hooks_json, config = root / ".codex" / "hooks.json", root / ".codex" / "config.toml"
        unrelated = {"hooks": {"PostToolUse": [{"matcher": "shell", "hooks": [{"type": "command", "command": "log.sh"}]}]}}
        self.write_json(hooks_json, unrelated)
        config.write_text(OTHER_TOML + SPECKIT_TOML, encoding="utf-8")

        self.assertEqual(self.ok(root, "install", "--host", "codex"),
                         {"host": "codex", "file": ".codex/hooks.json", "added": 1, "removed": 1, "needs_approval": True})
        self.assertEqual(config.read_text(encoding="utf-8"), OTHER_TOML, "Progress's Spec Kit block and user keys stay")
        data = json.loads(hooks_json.read_text(encoding="utf-8"))
        self.assertEqual(data["hooks"]["PostToolUse"][0], unrelated["hooks"]["PostToolUse"][0])
        ours = data["hooks"]["PostToolUse"][1]
        self.assertIn("apply_patch", ours["matcher"].split("|"))
        self.assert_script_exists(root, ours["hooks"][0]["command"])

        rerun = self.ok(root, "install", "--host", "codex")
        self.assertEqual((rerun["added"], rerun["removed"], rerun["needs_approval"]), (0, 0, False))
        status = self.ok(root, "status", "--host", "codex")
        self.assertEqual((status["installed"], status["dispatcher_entries"]), (True, 0))

        self.assertEqual(self.ok(root, "uninstall", "--host", "codex")["removed"], 1)
        self.assertEqual(json.loads(hooks_json.read_text(encoding="utf-8")), unrelated)
        self.assertEqual(self.ok(root, "uninstall", "--host", "codex")["removed"], 0)

    def test_uninstall_alone_cleans_an_old_dispatcher_entry(self):
        root = self.project()
        (root / ".codex").mkdir()
        (root / ".codex" / "config.toml").write_text(SPECKIT_TOML, encoding="utf-8")
        self.write_json(root / ".claude" / "settings.json", {"hooks": {"PostToolUse": [{"matcher": "Write|Edit", "hooks": [SPECKIT_CLAUDE]}]}})
        self.assertEqual(self.ok(root, "status", "--host", "codex")["dispatcher_entries"], 1)
        self.assertEqual(self.ok(root, "uninstall", "--host", "codex")["removed"], 1)
        self.assertEqual(self.ok(root, "uninstall", "--host", "claude")["removed"], 1)
        self.assertEqual((root / ".codex" / "config.toml").read_text(encoding="utf-8"), "")
        self.assertEqual(json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8")), {})
        self.assertFalse((root / ".codex" / "hooks.json").exists(), "uninstall never creates a host file")

    def test_refusals_write_nothing(self):
        root = self.project()
        settings = root / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text("{not json", encoding="utf-8")
        done = self.cli(root, "install", "--host", "claude")
        self.assertEqual(done.returncode, 2)
        self.assertEqual(settings.read_text(encoding="utf-8"), "{not json")
        # A copy outside the project would leave a command pointing at a path the project does not own.
        done = self.cli(root, "install", "--host", "codex", script=HOOK)
        self.assertEqual(done.returncode, 2)
        self.assertIn("outside", done.stderr)
        self.assertFalse((root / ".codex").exists())

    def test_text_output_names_the_codex_approval_step(self):
        root = self.project()
        script = root / ".specify" / "extensions" / "illustrate" / "hooks" / HOOK.name
        done = subprocess.run([sys.executable, str(script), "install", "--host", "codex", "--root", str(root)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('host="codex" file=".codex/hooks.json" added=1 removed=0 needs_approval=true', done.stdout)
        self.assertIn("/hooks", done.stdout)


if __name__ == "__main__":
    unittest.main()
