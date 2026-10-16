"""Tests for .github/scripts/ci_matrix.py: changed paths to regression suites."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".github" / "scripts"))
import ci_matrix  # noqa: E402


def pairs(files, event="pull_request"):
    return {(i["suite"], i["os"]) for i in ci_matrix.build(files, event)["matrix"]["include"]}


def suites(files, event="pull_request"):
    return {s for s, _ in pairs(files, event)}


class CiMatrixTests(unittest.TestCase):
    def test_progress_runs_progress_and_workflow(self):
        self.assertEqual({"progress", "workflow"}, suites(["extensions/progress/scripts/progress.py"]))

    def test_workflow_runs_workflow_and_scope(self):
        self.assertEqual({"workflow", "scope"}, suites(["extensions/workflow/scripts/workflow.py"]))

    def test_single_suite(self):
        self.assertEqual({"illustrate"}, suites(["extensions/illustrate/skill/SKILL.md"]))

    def test_docs_only_runs_nothing(self):
        result = ci_matrix.build(["docs/start/install.md"], "pull_request")
        self.assertFalse(result["has_regression"])
        self.assertFalse(result["memory_install"])

    def test_shared_paths_run_everything(self):
        for path in ("extensions/scripts/vendor.py", ".github/workflows/ci.yml", "catalog.json",
                     "presets/x/preset.yml", "extensions/pending-releases.json", "README.md"):
            self.assertEqual(set(ci_matrix.SUITES), suites([path]), path)

    def test_windows_workflow_excluded_on_push_only(self):
        self.assertNotIn(("workflow", "windows-latest"), pairs(["extensions/workflow/a.py"], "push"))
        self.assertIn(("workflow", "ubuntu-latest"), pairs(["extensions/workflow/a.py"], "push"))
        self.assertIn(("workflow", "windows-latest"), pairs(["extensions/workflow/a.py"], "pull_request"))
        self.assertIn(("workflow", "windows-latest"), pairs(None, "schedule"))

    def test_unknown_files_and_schedule_run_everything(self):
        self.assertEqual(set(ci_matrix.SUITES), suites(None, "push"))
        self.assertEqual(set(ci_matrix.SUITES), suites(["docs/a.md"], "schedule"))

    def test_memory_install_follows_memory_suite(self):
        self.assertTrue(ci_matrix.build(["extensions/memory/x.py"], "push")["memory_install"])
        self.assertFalse(ci_matrix.build(["extensions/scope/x.py"], "push")["memory_install"])


if __name__ == "__main__":
    unittest.main()
