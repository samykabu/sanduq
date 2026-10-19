"""IL6: the opt-in PostToolUse hook is a no-op until `illustrate.hooks.self_check: true`, then reports the first failure."""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from _helpers import EXT_DIR
from test_self_check import STATIC

spec = importlib.util.spec_from_file_location("self_check_hook", EXT_DIR / "hooks" / "self_check_hook.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

BAD = STATIC.replace("<body>", '<body onload="fetch(1)">', 1)


def run(root: Path, payload: dict) -> tuple[int, str]:
    stderr = io.StringIO()
    old, sys.stderr = sys.stderr, stderr
    try:
        code = hook.main(io.StringIO(json.dumps(payload)), {"CLAUDE_PROJECT_DIR": str(root)})
    finally:
        sys.stderr = old
    return code, stderr.getvalue()


class SelfCheckHook(unittest.TestCase):
    def project(self, policy: str | None) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        if policy is not None:
            (root / ".specify").mkdir()
            (root / ".specify" / "workflow.yml").write_text(policy, encoding="utf-8")
        (root / "bad.html").write_text(BAD, encoding="utf-8")
        (root / "good.html").write_text(STATIC, encoding="utf-8")
        return root

    @staticmethod
    def write(name: str) -> dict:
        return {"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": name, "content": "x"}}

    def test_no_op_when_the_key_is_off_or_the_policy_is_missing(self):
        for policy in (None, "", "illustrate:\n  hooks:\n    self_check: false\n", "illustrate: {}\n"):
            with self.subTest(policy=policy):
                self.assertEqual(run(self.project(policy), self.write("bad.html")), (0, ""))

    def test_key_on_reports_the_first_failure_and_passes_a_clean_diagram(self):
        root = self.project("illustrate:\n  hooks:\n    self_check: true\n")
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


if __name__ == "__main__":
    unittest.main()
