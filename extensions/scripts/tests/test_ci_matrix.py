"""Tests for .github/scripts/ci_matrix.py: changed paths to regression suites."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".github" / "scripts"))
import ci_matrix  # noqa: E402

# Everything except `project`, whose module the workflow suite already runs.
ALL = set(ci_matrix.SUITES) - {"project"}
WORKFLOW_TESTS = ci_matrix.ROOT / "extensions/workflow/tests"


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
                     "presets/x/preset.yml", "vendor.lock.json"):
            self.assertEqual(ALL, suites([path]), path)

    def test_windows_workflow_excluded_on_push_only(self):
        self.assertNotIn(("workflow", "windows-latest"), pairs(["extensions/workflow/a.py"], "push"))
        self.assertIn(("workflow", "ubuntu-latest"), pairs(["extensions/workflow/a.py"], "push"))
        self.assertIn(("workflow", "windows-latest"), pairs(["extensions/workflow/a.py"], "pull_request"))
        self.assertIn(("workflow", "windows-latest"), pairs(None, "schedule"))

    def test_windows_memory_follows_the_windows_workflow_event_rule(self):
        self.assertEqual({("memory", "ubuntu-latest")}, pairs(["extensions/memory/x.py"], "push"))
        for event in ("pull_request", "schedule", "workflow_dispatch"):
            self.assertIn(("memory", "windows-latest"), pairs(["extensions/memory/x.py"], event), event)

    def test_unknown_files_and_schedule_run_everything(self):
        self.assertEqual(ALL, suites(None, "push"))
        self.assertEqual(ALL, suites(["docs/a.md"], "schedule"))

    def test_memory_install_follows_memory_suite(self):
        self.assertTrue(ci_matrix.build(["extensions/memory/x.py"], "push")["memory_install"])
        self.assertFalse(ci_matrix.build(["extensions/scope/x.py"], "push")["memory_install"])


class Round3Selection(unittest.TestCase):
    """X3, X4, X6: release metadata lint-only, project coverage, gated smoke jobs, shards, vendored checks."""

    def result(self, files, event="pull_request"):
        return ci_matrix.build(files, event)

    def test_release_metadata_and_top_level_prose_are_lint_only(self):
        for path in ("CHANGELOG.md", "README.md", "CONTRIBUTING.md", "extensions/README.md",
                     "extensions/pending-releases.json", "docs/start/install.md", "docs/reference/glossary.md"):
            result = self.result([path])
            self.assertFalse(result["has_regression"], path)
            self.assertFalse(result["install_smoke"], path)
            self.assertFalse(result["memory_install"], path)
            self.assertFalse(result["illustrate_vendored"], path)

    def test_docs_examples_keep_their_suites_without_install_smoke(self):
        path = "docs/examples/booking-illustration-theme.yml"
        self.assertEqual({"illustrate", "user-manual"}, suites([path]))
        self.assertFalse(self.result([path])["install_smoke"])

    def test_extension_readme_stays_with_its_suite(self):
        self.assertEqual({"progress", "workflow"}, suites(["extensions/progress/README.md"]))

    def test_mixed_lint_only_and_code_keeps_the_code_selection(self):
        self.assertEqual({"memory"}, suites(["README.md", "extensions/memory/scripts/x.py"]))
        self.assertEqual(ALL, suites(["CHANGELOG.md", "extensions/scripts/vendor.py"]))

    def test_project_change_runs_the_project_suite_and_the_smoke_jobs(self):
        path = "extensions/project/scripts/project_sync.py"
        result = self.result([path])
        self.assertEqual({("project", "ubuntu-latest"), ("project", "windows-latest")}, pairs([path]))
        self.assertTrue(result["install_smoke"])
        entry = result["matrix"]["include"][0]
        self.assertEqual(("extensions/workflow/tests", "test_project_sync_summary"), (entry["tests"], entry["modules"]))
        self.assertTrue((ci_matrix.ROOT / entry["tests"] / (entry["modules"] + ".py")).is_file())

    def test_project_suite_is_dropped_when_workflow_runs(self):
        self.assertEqual({"workflow", "scope"},
                         suites(["extensions/project/scripts/x.py", "extensions/workflow/scripts/workflow.py"]))
        self.assertNotIn("project", suites(None, "schedule"))

    def test_install_smoke_follows_install_relevant_paths(self):
        for path in ("extensions/workflow/scripts/install.py", "extensions/scope/extension.yml",
                     "extensions/scripts/package.py", "extensions/scripts/smoke_install.py",
                     "extensions/scripts/shared/deps.py", "presets/workflow/preset.yml", "vendor.lock.json",
                     "prototypes/sanduq-delivery/x.py", ".github/workflows/ci.yml", ".github/scripts/ci_matrix.py",
                     "extensions/project/scripts/project_sync.py"):
            self.assertTrue(self.result([path])["install_smoke"], path)
        for path in ("extensions/scope/scripts/scope.py", "extensions/memory/scripts/x.py",
                     "extensions/illustrate/commands/x.md", "extensions/scripts/check_docs.py",
                     "extensions/scope/tests/extension.yml", "docs/start/install.md"):
            self.assertFalse(self.result([path])["install_smoke"], path)

    def test_install_smoke_runs_on_schedule_dispatch_and_unknown_changes(self):
        self.assertTrue(self.result(["docs/a.md"], "schedule")["install_smoke"])
        self.assertTrue(self.result(["docs/a.md"], "workflow_dispatch")["install_smoke"])
        self.assertTrue(self.result(None, "push")["install_smoke"])

    def test_illustrate_vendored_checks_only_on_vendor_bumps_and_nightly(self):
        command = "extensions/illustrate/commands/speckit.illustrate.export.md"
        self.assertEqual({"illustrate"}, suites([command]))
        self.assertFalse(self.result([command])["illustrate_vendored"])
        self.assertFalse(self.result(["extensions/illustrate/hooks/self_check_hook.py"])["illustrate_vendored"])
        for files, event in ((["vendor.lock.json"], "pull_request"),
                             (["extensions/illustrate/skill/scripts/verify-geometry.py"], "push"),
                             (["docs/a.md"], "schedule"), (["docs/a.md"], "workflow_dispatch"), (None, "push")):
            result = self.result(files, event)
            self.assertTrue(result["illustrate_vendored"], (files, event))
            self.assertIn("illustrate", {i["suite"] for i in result["matrix"]["include"]}, (files, event))

    def test_windows_workflow_runs_as_four_shards_covering_every_module_once(self):
        include = self.result(["extensions/workflow/scripts/workflow.py"])["matrix"]["include"]
        windows = [i for i in include if i["suite"] == "workflow" and i["os"] == "windows-latest"]
        linux = [i for i in include if i["suite"] == "workflow" and i["os"] == "ubuntu-latest"]
        self.assertEqual(["1/4", "2/4", "3/4", "4/4"], [i["shard"] for i in windows])
        listed = [m for i in windows for m in i["modules"].split()]
        on_disk = sorted(p.stem for p in WORKFLOW_TESTS.glob("test*.py"))
        self.assertEqual(len(listed), len(set(listed)), "a module is in two shards")
        self.assertEqual(on_disk, sorted(listed))
        self.assertTrue(all(i["modules"] and i["tests"] == "extensions/workflow/tests" for i in windows))
        # Linux workflow stays one discover job.
        self.assertEqual([{"os": "ubuntu-latest", "suite": "workflow", "tests": "extensions/workflow/tests",
                           "modules": ""}], linux)

    def test_shards_balance_module_bytes(self):
        sizes = {p.stem: p.stat().st_size for p in WORKFLOW_TESTS.glob("test*.py")}
        loads = [sum(sizes[m] for m in shard) for shard in ci_matrix.workflow_shards()]
        # Greedy largest-first: shards differ by at most the largest module.
        self.assertLessEqual(max(loads) - min(loads), max(sizes.values()))

    def test_push_omits_both_windows_slow_suites(self):
        windows = {s for s, o in pairs(None, "push") if o == "windows-latest"}
        self.assertFalse({"workflow", "memory"} & windows)
        self.assertIn("scope", windows)

    def test_cli_prints_every_output(self):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ci_matrix.main(["--event", "pull_request", "--files", "README.md"])
        keys = [line.split("=", 1)[0] for line in out.getvalue().splitlines()]
        self.assertEqual(["matrix", "has_regression", "memory_install", "install_smoke", "illustrate_vendored"], keys)


class CiWorkflowFile(unittest.TestCase):
    """ci.yml wires the outputs: smoke jobs gated on `changes`, vendored checks on their flag, caches."""

    @classmethod
    def setUpClass(cls):
        cls.text = (ci_matrix.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    def job(self, name):
        match = re.search(rf"^  {re.escape(name)}:\n(?:(?:    .*)?\n)+", self.text, re.M)
        self.assertIsNotNone(match, name)
        return match.group(0)

    def test_changes_exposes_every_output(self):
        changes = self.job("changes")
        for key in ("matrix", "has_regression", "memory_install", "install_smoke", "illustrate_vendored"):
            self.assertIn(f"{key}: ${{{{ steps.matrix.outputs.{key} }}}}", changes, key)

    def test_smoke_jobs_need_changes_and_install_smoke(self):
        for name in ("installation", "upgrade", "project-init", "dryrun"):
            job = self.job(name)
            self.assertIn("needs: changes", job, name)
            self.assertIn("needs.changes.outputs.install_smoke == 'true'", job, name)

    def test_vendored_illustrate_checks_follow_their_flag(self):
        regression = self.job("regression")
        for step in ("Illustrate builders and verifiers", "Illustrate rendered-layout lint"):
            head = regression[regression.index(step):].split("run:")[0]
            self.assertIn("needs.changes.outputs.illustrate_vendored == 'true'", head, step)

    def test_fresh_runners_still_install_chromium_os_dependencies(self):
        regression = self.job("regression")
        self.assertIn("playwright install --with-deps chromium", regression)
        self.assertIn("ms-playwright", regression)

    def test_every_setup_python_caches_pip(self):
        for workflow in ("ci.yml", "release-extensions.yml"):
            text = (ci_matrix.ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
            steps = re.findall(r"uses: actions/setup-python@\S+\n((?:\s{8,}\S.*\n)+)", text)
            self.assertTrue(steps, workflow)
            for body in steps:
                self.assertIn("cache: pip", body, workflow)

    def test_spec_kit_installs_by_name_so_pip_reuses_the_cached_wheel(self):
        # pip only looks up its wheel cache for a VCS URL when the requirement is named.
        self.assertNotIn("install 'git+https://github.com/github/spec-kit", self.text)
        self.assertIn("specify-cli @ git+https://github.com/github/spec-kit.git@", self.text)


class ReviewFindings(unittest.TestCase):
    def test_scope_change_also_runs_workflow(self):
        self.assertEqual(ci_matrix.suites_for(["extensions/scope/scripts/scope.py"]), {"scope", "workflow"})

    def test_docs_examples_run_the_suites_that_read_them(self):
        self.assertEqual(ci_matrix.suites_for(["docs/examples/booking-illustration-theme.yml"]),
                         {"illustrate", "user-manual"})
        self.assertEqual(ci_matrix.suites_for(["docs/start/install.md"]), set())

    def test_rename_out_of_a_suite_keeps_the_old_path(self):
        import os
        import shutil
        import subprocess
        import tempfile
        repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repo, ignore_errors=True)

        def git(*args):
            return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
        git("init", "-q")
        git("config", "user.email", "t@example.invalid")
        git("config", "user.name", "t")
        os.makedirs(os.path.join(repo, "extensions", "memory"))
        with open(os.path.join(repo, "extensions", "memory", "a.py"), "w") as fh:
            fh.write("x = 1" + chr(10) * 1 + "y = 2" + chr(10))
        git("add", "-A")
        git("commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        os.makedirs(os.path.join(repo, "docs"))
        git("mv", "extensions/memory/a.py", "docs/a.py")
        git("commit", "-qm", "move")
        head = git("rev-parse", "HEAD")
        here = os.getcwd()
        os.chdir(repo)
        try:
            files = ci_matrix.changed_files("push", base, head)
        finally:
            os.chdir(here)
        self.assertIn("extensions/memory/a.py", files)
        self.assertIn("memory", ci_matrix.suites_for(files))

if __name__ == "__main__":
    unittest.main()
