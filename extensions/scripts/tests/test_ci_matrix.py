"""Tests for .github/scripts/ci_matrix.py: changed paths to regression suites."""
import datetime
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import textwrap
import unittest
import unittest.mock
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".github" / "scripts"))
import ci_matrix  # noqa: E402
import shard_times  # noqa: E402

ALL = set(ci_matrix.SUITES)
WORKFLOW_TESTS = ci_matrix.ROOT / "extensions/workflow/tests"


def units(include):
    """One record per suite a matrix entry runs (the Linux batch runs several), from its runs lines."""
    out = []
    for entry in include:
        for line in entry["runs"].splitlines():
            suite, tests, *modules = line.split()
            out.append({"os": entry["os"], "suite": suite, "tests": tests, "modules": " ".join(modules),
                        **({"shard": entry["shard"]} if "shard" in entry else {})})
    return out


def pairs(files, event="pull_request"):
    return {(i["suite"], i["os"]) for i in units(ci_matrix.build(files, event)["matrix"]["include"])}


def suites(files, event="pull_request"):
    return {s for s, _ in pairs(files, event)}


class CiMatrixTests(unittest.TestCase):
    def test_progress_runs_progress_and_workflow(self):
        self.assertEqual({"progress", "workflow"}, suites(["extensions/progress/scripts/progress.py"]))

    def test_workflow_runs_workflow_scope_and_pr(self):
        self.assertEqual({"workflow", "scope", "pr"}, suites(["extensions/workflow/scripts/workflow.py"]))

    def test_single_suite(self):
        self.assertEqual({"illustrate"}, suites(["extensions/illustrate/commands/x.md"]))

    def test_illustrate_skill_also_runs_the_scope_and_pr_modules_that_read_it(self):
        selection = ci_matrix.selection_for(["extensions/illustrate/skill/SKILL.md"])
        self.assertEqual({"illustrate": None, "scope": {"test_plan"}, "pr": {"test_pr_diagram_recipe"}}, selection)

    def test_memory_change_selects_workflow(self):
        """SAMY-06: workflow's Memory handoff tests run Memory's archive.py."""
        self.assertEqual({"memory", "workflow"}, suites(["extensions/memory/scripts/archive.py"]))

    def test_docs_only_runs_nothing(self):
        result = ci_matrix.build(["docs/start/install.md"], "pull_request")
        self.assertFalse(result["has_regression"])
        self.assertFalse(result["memory_install"])

    def test_shared_paths_run_everything(self):
        for path in ("extensions/scripts/package.py", ".github/workflows/ci.yml", "catalog.json",
                     "presets/x/preset.yml", "vendor.lock.json"):
            self.assertEqual(ALL, suites([path]), path)

    def test_windows_workflow_excluded_on_push_only(self):
        self.assertNotIn(("workflow", "windows-latest"), pairs(["extensions/workflow/a.py"], "push"))
        self.assertIn(("workflow", "ubuntu-latest"), pairs(["extensions/workflow/a.py"], "push"))
        self.assertIn(("workflow", "windows-latest"), pairs(["extensions/workflow/a.py"], "pull_request"))
        self.assertIn(("workflow", "windows-latest"), pairs(None, "schedule"))

    def test_windows_memory_follows_the_windows_workflow_event_rule(self):
        self.assertEqual({("memory", "ubuntu-latest"), ("workflow", "ubuntu-latest")},
                         pairs(["extensions/memory/x.py"], "push"))
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
        self.assertEqual({"memory", "workflow"}, suites(["README.md", "extensions/memory/scripts/x.py"]))
        self.assertEqual(ALL, suites(["CHANGELOG.md", "extensions/scripts/package.py"]))

    def test_project_change_runs_the_project_suite_and_the_smoke_jobs(self):
        path = "extensions/project/scripts/project_sync.py"
        result = self.result([path])
        self.assertLessEqual({("project", "ubuntu-latest"), ("project", "windows-latest")}, pairs([path]))
        self.assertTrue(result["install_smoke"])
        entry = [i for i in units(result["matrix"]["include"]) if i["suite"] == "project"][0]
        target = ci_matrix.ROOT / entry["tests"] / ((entry["modules"] or "") + ".py")
        self.assertTrue(target.is_file() if entry["modules"] else any((ci_matrix.ROOT / entry["tests"]).glob("test*.py")))

    def test_install_smoke_follows_install_relevant_paths(self):
        for path in ("extensions/workflow/scripts/install.py", "extensions/scope/extension.yml",
                     "extensions/scripts/package.py", "extensions/scripts/smoke_install.py",
                     "extensions/scripts/shared/deps.py", "presets/workflow/preset.yml", "vendor.lock.json",
                     ".github/workflows/ci.yml", ".github/scripts/ci_matrix.py",
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

    def test_illustrate_vendored_checks_only_on_vendor_bumps_on_demand_and_weekly(self):
        command = "extensions/illustrate/commands/speckit.illustrate.export.md"
        self.assertEqual({"illustrate"}, suites([command]))
        self.assertFalse(self.result([command])["illustrate_vendored"])
        self.assertFalse(self.result(["extensions/illustrate/hooks/self_check_hook.py"])["illustrate_vendored"])
        for files, event in ((["vendor.lock.json"], "pull_request"),
                             (["extensions/illustrate/skill/scripts/verify-geometry.py"], "push"),
                             (["docs/a.md"], "workflow_dispatch"), (None, "push")):
            result = self.result(files, event)
            self.assertTrue(result["illustrate_vendored"], (files, event))
            self.assertIn("illustrate", {i["suite"] for i in units(result["matrix"]["include"])}, (files, event))

    def test_windows_workflow_runs_as_four_shards_covering_every_module_once(self):
        include = units(self.result(["extensions/workflow/scripts/workflow.py"])["matrix"]["include"])
        windows = [i for i in include if i["suite"] == "workflow" and i["os"] == "windows-latest"]
        linux = [i for i in include if i["suite"] == "workflow" and i["os"] == "ubuntu-latest"]
        on_disk = sorted(p.stem for p in WORKFLOW_TESTS.glob("test*.py"))
        # Linux shards the workflow suite the same way.
        for legs in (windows, linux):
            self.assertEqual(["1/4", "2/4", "3/4", "4/4"], [i["shard"] for i in legs])
            listed = [m for i in legs for m in i["modules"].split()]
            self.assertEqual(len(listed), len(set(listed)), "a module is in two shards")
            self.assertEqual(on_disk, sorted(listed))
            self.assertTrue(all(i["modules"] and i["tests"] == "extensions/workflow/tests" for i in legs))

    def test_shards_balance_module_bytes_without_a_table(self):
        sizes = {p.stem: p.stat().st_size for p in WORKFLOW_TESTS.glob("test*.py")}
        loads = [sum(sizes[m] for m in shard) for shard in ci_matrix.shards("workflow", 4, weights={})]
        # Greedy largest-first: shards differ by at most the largest module.
        self.assertLessEqual(max(loads) - min(loads), max(sizes.values()))

    def test_push_omits_both_windows_slow_suites(self):
        windows = {s for s, o in pairs(None, "push") if o == "windows-latest"}
        self.assertFalse({"workflow", "memory"} & windows)
        self.assertIn("scope", windows)

    def test_linux_runs_every_suite_but_whole_workflow_in_one_batch_job(self):
        """FAST: one Linux job for the small suites, sharded workflow, Windows unchanged."""
        include = ci_matrix.build(None, "schedule")["matrix"]["include"]
        linux = [i for i in include if i["os"] == "ubuntu-latest"]
        batch = [i for i in linux if "shard" not in i]
        self.assertEqual(1, len(batch))
        self.assertEqual(sorted(ALL - {"workflow"}), sorted(batch[0]["suites"]))
        self.assertEqual(batch[0]["suites"], [line.split()[0] for line in batch[0]["runs"].splitlines()])
        self.assertEqual(" + ".join(batch[0]["suites"]), batch[0]["suite"])
        self.assertEqual(4, len([i for i in linux if i["suite"] == "workflow"]))
        windows = [i for i in include if i["os"] == "windows-latest"]
        self.assertTrue(all(i["suites"] == [i["suite"]] and len(i["runs"].splitlines()) == 1 for i in windows))
        # Path selection holds: a pr change batches only pr; workflow follows as its dependent.
        include = ci_matrix.build(["extensions/pr/scripts/x.py"], "pull_request")["matrix"]["include"]
        self.assertEqual([["pr"]], [i["suites"] for i in include if i["os"] == "ubuntu-latest" and "shard" not in i])

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
        for name in ("installation", "project-init", "dryrun"):
            job = self.job(name)
            self.assertIn("needs: changes", job, name)
            self.assertIn("needs.changes.outputs.install_smoke == 'true'", job, name)

    def test_vendored_illustrate_checks_follow_their_flag(self):
        regression = self.job("regression")
        for step in ("Illustrate builders and verifiers", "Illustrate rendered-layout lint",
                     "Cache the Playwright browser", "Install Playwright for Illustrate render checks"):
            head = regression[regression.index(step):].split("run:")[0].split("with:")[0]
            self.assertIn("needs.changes.outputs.illustrate_vendored == 'true'", head, step)
            self.assertIn("runner.os == 'Linux'", head, step)

    def test_fresh_runners_still_install_chromium_os_dependencies(self):
        regression = self.job("regression")
        self.assertIn("playwright install --with-deps chromium", regression)
        self.assertIn("ms-playwright", regression)

    def test_every_setup_python_caches_pip(self):
        for workflow in ("ci.yml", "release-extensions.yml"):
            text = (ci_matrix.ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
            steps = re.findall(r"uses: actions/setup-python@\S+.*\n((?:\s{8,}\S.*\n)+)", text)
            self.assertTrue(steps, workflow)
            for body in steps:
                self.assertIn("cache: pip", body, workflow)

    def test_linux_regression_runs_on_the_declared_python_floor(self):
        """SAMY-11: every extension.yml declares python >=3.11 and the Linux regression legs run on it."""
        self.assertIn("python-version: ${{ matrix.os == 'windows-latest' && '3.13' || '3.11' }}", self.job("regression"))
        for manifest in sorted((ci_matrix.ROOT / "extensions").glob("*/extension.yml")):
            self.assertRegex(manifest.read_text(encoding="utf-8"), r"- name: python\n(?:.*\n)?\s+version: ['\"]>=3\.11['\"]",
                             manifest.parent.name)

    def test_every_smoke_runs_with_its_arguments_on_linux_and_windows(self):
        """FAST: the Linux smokes moved into one job per host; each still runs, with the same arguments."""
        install = self.job("installation")
        self.assertIn("host: ${{ fromJSON(needs.changes.outputs.install_smoke == 'true' && '[\"claude\", \"codex\"]' "
                      "|| '[\"claude\"]') }}", install)
        self.assertIn("needs.changes.outputs.memory_install == 'true'", install.split("steps:")[0])
        for line in ('run: python extensions/scripts/smoke_install.py --host "$HOST"\n',
                     'run: python extensions/scripts/smoke_install.py --host "$HOST" --superspec-source '
                     '"$GITHUB_WORKSPACE/dist/upstream-superspec"\n',
                     "run: python extensions/scripts/smoke_upgrade.py\n",
                     "run: python extensions/scripts/smoke_project_init.py\n",
                     "run: python extensions/scripts/smoke_memory_install.py\n"):
            self.assertIn(line, install)
        self.assertNotRegex(self.text, r"(?m)^  upgrade:")
        for name in ("memory-installation", "project-init"):
            self.assertIn("os: [windows-latest]", self.job(name), name)

    def test_the_suite_step_runs_every_suite_before_failing(self):
        regression = self.job("regression")
        self.assertIn("RUNS: ${{ matrix.runs }}", regression)
        self.assertIn('echo "=== $suite rc=$rc"', regression)
        self.assertIn('if (( ${#failed[@]} )); then echo "Failed suites: ${failed[*]}"; exit 1; fi', regression)
        self.assertNotIn("matrix.suite ==", regression)

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


class Round4Selection(unittest.TestCase):
    """IP13-IP15, X15, X16, PM19, AU23."""

    def include(self, files, event="pull_request", today=None):
        return units(ci_matrix.build(files, event, today)["matrix"]["include"])

    def test_illustrate_hook_runs_workflow_hook_tests_and_the_install_smoke(self):
        path = "extensions/illustrate/hooks/self_check_hook.py"
        for event in ("pull_request", "push"):
            result = ci_matrix.build([path], event)
            workflow = [i for i in units(result["matrix"]["include"]) if i["suite"] == "workflow"]
            self.assertEqual({"ubuntu-latest", "windows-latest"}, {i["os"] for i in workflow}, event)
            self.assertTrue(all(i["modules"] == "test_install_hooks" and "shard" not in i for i in workflow), event)
            self.assertEqual({"illustrate", "workflow"}, {i["suite"] for i in units(result["matrix"]["include"])})
            self.assertTrue(result["install_smoke"], event)
        self.assertTrue((WORKFLOW_TESTS / "test_install_hooks.py").is_file())

    def test_a_whole_suite_wins_over_its_module_list(self):
        files = ["extensions/illustrate/hooks/self_check_hook.py", "extensions/workflow/scripts/workflow.py"]
        workflow = [i for i in self.include(files) if i["suite"] == "workflow"]
        self.assertEqual(4, len([i for i in workflow if i["os"] == "windows-latest"]))
        self.assertEqual(4, len([i for i in workflow if i["os"] == "ubuntu-latest"]))
        self.assertNotIn("test_install_hooks", [i["modules"] for i in workflow])

    def test_vendored_checks_run_on_one_scheduled_day_a_week(self):
        monday = datetime.date(2026, 10, 19)
        days = [monday + datetime.timedelta(n) for n in range(7)]
        weekly = [d for d in days if ci_matrix.build(None, "schedule", d)["illustrate_vendored"]]
        self.assertEqual([ci_matrix.VENDORED_WEEKDAY], [d.weekday() for d in weekly])
        # The suite itself still runs every night.
        self.assertIn("illustrate", {i["suite"] for i in self.include(None, "schedule", monday)})
        self.assertTrue(ci_matrix.build(["docs/a.md"], "workflow_dispatch", monday)["illustrate_vendored"])

    def test_tooling_paths_are_lint_only(self):
        for path in (".github/workflows/release-extensions.yml", ".github/workflows/vendor-update.yml",
                     ".github/workflows/prune-artifacts.yml", ".github/actionlint.yaml",
                     "extensions/scripts/tests/test_vendor.py", "extensions/scripts/test_check_docs.py",
                     "extensions/scripts/validate_skills.py", "extensions/scripts/vendor.py"):
            result = ci_matrix.build([path], "pull_request")
            self.assertFalse(result["has_regression"], path)
            self.assertFalse(result["install_smoke"], path)
        self.assertEqual(ALL, suites([".github/workflows/ci.yml"]))

    def test_tooling_scripts_run_the_one_module_that_reads_them(self):
        for path, suite, module in (("extensions/scripts/release.py", "workflow", "test_release"),
                                    ("extensions/scripts/check_docs.py", "assure", "test_descriptions"),
                                    ("extensions/scripts/benchmark_instructions.py", "scope", "test_instructions")):
            include = self.include([path])
            self.assertEqual({suite}, {i["suite"] for i in include}, path)
            self.assertEqual({module}, {i["modules"] for i in include}, path)
            self.assertEqual(2, len(include), path)
            self.assertTrue((ci_matrix.ROOT / include[0]["tests"] / (module + ".py")).is_file(), path)

    def test_injected_files_run_every_suite_that_ships_them(self):
        self.assertEqual({"workflow", "project", "scope", "pr"}, suites(["extensions/scripts/shared/sanduq_remote.py"]))
        self.assertLessEqual({"workflow", "scope", "assure", "user-manual"},
                             suites(["extensions/workflow/scripts/sanduq_ci.py"]))
        self.assertLessEqual({"assure", "user-manual"}, suites(["extensions/workflow/scripts/sanduq_hash.py"]))
        self.assertTrue(ci_matrix.build(["extensions/scripts/shared/deps.py"], "push")["install_smoke"])
        # A shared file the table does not know runs everything.
        self.assertEqual(ALL, suites(["extensions/scripts/shared/new_helper.py"]))

    def test_injected_table_covers_every_built_archive(self):
        spec = importlib.util.spec_from_file_location("package_for_ci", ci_matrix.ROOT / "extensions/scripts/package.py")
        package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(package)
        sources = {p.name: p for p in (ci_matrix.ROOT / "extensions/scripts/shared").glob("*.py")}
        sources.update({Path(p).name: ci_matrix.ROOT / p for p in ci_matrix.INJECTED})
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        for extension in sorted(p.parent.name for p in (ci_matrix.ROOT / "extensions").glob("*/extension.yml")):
            archive = out / (extension + ".zip")
            package.package(extension, archive)
            with zipfile.ZipFile(archive) as zf:
                for name in zf.namelist():
                    folder, _, base = name.rpartition("/")
                    source = sources.get(base)
                    if folder != extension + "/scripts" or source is None or zf.read(name) != source.read_bytes():
                        continue
                    if source.parent == ci_matrix.ROOT / "extensions" / extension / "scripts":
                        continue  # the extension's own file
                    path = source.relative_to(ci_matrix.ROOT).as_posix()
                    self.assertIn(extension, ci_matrix.INJECTED.get(path, []), f"{extension} ships {path}")

    def test_project_runs_with_workflow_and_from_either_test_folder(self):
        self.assertEqual({"project", "workflow"}, suites(["extensions/project/scripts/x.py"]))
        self.assertIn("project", suites(None, "schedule"))
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.addCleanup(setattr, ci_matrix, "ROOT", ci_matrix.ROOT)
        ci_matrix.ROOT = root
        (root / "extensions/workflow/tests").mkdir(parents=True)
        (root / "extensions/workflow/tests/test_project_sync_summary.py").write_text("")
        self.assertEqual(ci_matrix.PROJECT_LEGACY, ci_matrix.suite_tests("project"))
        (root / "extensions/project/tests").mkdir(parents=True)
        (root / "extensions/project/tests/test_project_sync.py").write_text("")
        self.assertEqual(("extensions/project/tests", ""), ci_matrix.suite_tests("project"))
        (root / "extensions/workflow/tests/test_project_sync_summary.py").unlink()
        self.assertEqual(("extensions/project/tests", ""), ci_matrix.suite_tests("project"))

    def test_every_unit_is_in_exactly_one_windows_shard(self):
        for suite, count in ci_matrix.WINDOWS_SHARDS.items():
            include = [i for i in self.include([f"extensions/{suite}/scripts/x.py"]) if i["suite"] == suite]
            windows = [i for i in include if i["os"] == "windows-latest"]
            self.assertEqual([f"{n}/{count}" for n in range(1, count + 1)], [i["shard"] for i in windows], suite)
            listed = [u for i in windows for u in i["modules"].split()]
            self.assertEqual(len(listed), len(set(listed)), suite)
            self.assertEqual(sorted(ci_matrix.shard_units(suite)), sorted(listed), suite)
            linux = [i for i in include if i["os"] == "ubuntu-latest"]
            if suite in ci_matrix.LINUX_SHARDS:
                self.assertEqual(sorted(listed), sorted(u for i in linux for u in i["modules"].split()), suite)
            else:
                self.assertEqual([""], [i["modules"] for i in linux], suite)

    def test_memory_shards_by_class_and_covers_every_module(self):
        units = ci_matrix.shard_units("memory")
        self.assertTrue(all(u.count(".") == 1 for u in units))
        modules = {p.stem for p in (ci_matrix.ROOT / "extensions/memory/tests").glob("test*.py")}
        self.assertEqual(modules, {u.split(".")[0] for u in units})

    def test_test_classes_skips_mixins_and_follows_local_bases(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        path = folder / "test_x.py"
        path.write_text("import unittest\nfrom unittest import TestCase\n"
                        "class Mixin:\n    def test_a(self): pass\n"
                        "class A(Mixin, unittest.TestCase): pass\n"
                        "class B(TestCase): pass\n"
                        "class C(B): pass\n"
                        "class Helper(object): pass\n", encoding="utf-8")
        self.assertEqual(["A", "B", "C"], ci_matrix.test_classes(path))

    def test_a_unit_missing_from_the_table_still_gets_a_shard(self):
        units = ci_matrix.shard_units("workflow")
        weights = {u: 10.0 for u in sorted(units)[1:]}
        listed = [u for shard in ci_matrix.shards("workflow", 4, weights) for u in shard]
        self.assertEqual(sorted(units), sorted(listed))
        # An empty table falls back to file size.
        listed = [u for shard in ci_matrix.shards("memory", 2, {}) for u in shard]
        self.assertEqual(sorted(ci_matrix.shard_units("memory")), sorted(listed))

    def test_shards_balance_measured_seconds(self):
        table = json.loads(ci_matrix.WEIGHTS.read_text(encoding="utf-8"))
        self.assertTrue(table.get("source"))
        for suite in ci_matrix.WINDOWS_SHARDS:
            weights, units = table[suite], ci_matrix.shard_units(suite)
            self.assertTrue(all(isinstance(v, (int, float)) and v >= 0 for v in weights.values()), suite)
            known = [u for u in units if u in weights]
            self.assertGreater(len(known), len(units) // 2, f"{suite}: most units should be measured")
            rate = sum(weights[u] for u in known) / sum(units[u] for u in known)
            cost = {u: weights.get(u, units[u] * rate) for u in units}
            loads = [sum(cost[u] for u in s) for s in ci_matrix.shards(suite)]
            # Greedy heaviest-first: shards differ by at most the heaviest unit.
            self.assertLessEqual(max(loads) - min(loads), max(cost.values()) + 1e-6, suite)


class Round4WorkflowFiles(unittest.TestCase):
    """X16 actionlint in lint; X24 every action pinned by commit with its version."""

    def test_every_action_is_pinned_by_commit_with_its_version(self):
        for path in sorted((ci_matrix.ROOT / ".github/workflows").glob("*.yml")):
            for ref, rest in re.findall(r"uses: (\S+)(.*)", path.read_text(encoding="utf-8")):
                self.assertRegex(ref, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$", f"{path.name}: {ref}")
                self.assertRegex(rest, r"^ # v\d+\.\d+\.\d+$", f"{path.name}: {ref}")

    def test_lint_runs_actionlint_with_a_checked_download(self):
        text = (ci_matrix.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        lint = re.search(r"^  lint:\n(?:(?:    .*)?\n)+", text, re.M).group(0)
        self.assertIn("sha256sum -c", lint)
        self.assertLess(lint.index("ShellCheck bash scripts"), lint.index("actionlint"))
        self.assertTrue((ci_matrix.ROOT / ".github/actionlint.yaml").is_file())

    def test_suite_step_leaves_the_project_folder_to_the_matrix(self):
        text = (ci_matrix.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("discover -s extensions/project/tests", text)


class Round5ShardTimes(unittest.TestCase):
    """SHARD: per-unit seconds from the sharded step, and the table rebuilt from them; X22 sanduq_gh entry."""

    SCRIPT = ci_matrix.ROOT / ".github/scripts/shard_times.py"
    FIXTURE = {
        "test_m1.py": "import unittest\n"
                      "class A(unittest.TestCase):\n"
                      "    @classmethod\n    def setUpClass(cls): print('A-up')\n"
                      "    @classmethod\n    def tearDownClass(cls): print('A-down')\n"
                      "    def test_a(self): pass\n"
                      "class B(unittest.TestCase):\n"
                      "    @classmethod\n    def tearDownClass(cls): print('B-down')\n"
                      "    def test_b(self): pass\n",
        "test_m2.py": "import unittest\n"
                      "class C(unittest.TestCase):\n    def test_fails(self): self.fail('x')\n",
    }

    def run_both(self, names):
        import os
        import subprocess
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        for name, text in self.FIXTURE.items():
            (folder / name).write_text(text, encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(folder))
        plain, timed = (subprocess.run(command + names, cwd=folder, env=env, capture_output=True, text=True)
                        for command in ([sys.executable, "-m", "unittest", "-q"],
                                        [sys.executable, str(self.SCRIPT), "run"]))
        return plain, timed

    def test_run_keeps_tests_exit_code_and_fixtures_and_times_each_name(self):
        for names, code in ((["test_m1.A", "test_m1.B", "test_m2"], 1), (["test_m1"], 0), (["test_nope"], 1)):
            plain, timed = self.run_both(names)
            self.assertEqual((code, code), (plain.returncode, timed.returncode), names)
            ran = re.compile(r"^Ran \d+ tests?", re.M)
            self.assertEqual(ran.findall(plain.stderr), ran.findall(timed.stderr), names)
            for line in ("A-up", "A-down", "B-down"):
                self.assertEqual(plain.stdout.count(line), timed.stdout.count(line), (names, line))
            self.assertEqual(names, [m[1] for m in map(shard_times.LINE.search, timed.stdout.splitlines()) if m])

    def write_logs(self, *texts):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        paths = []
        for n, text in enumerate(texts):
            paths.append(folder / f"log{n}.txt")
            paths[-1].write_text(text, encoding="utf-8")
        return paths

    def test_read_times_parses_job_log_lines_and_averages_repeats(self):
        logs = self.write_logs(
            "2026-10-22T10:00:00.1Z shard-unit-seconds test_lint 12.50\n"
            "2026-10-22T10:00:00.2Z Ran 40 tests in 30.1s\n"
            "2026-10-22T10:00:00.3Z shard-unit-seconds test_x notanumber\n",
            "regression (windows-latest, memory, 1/2)\tRun the suite\t2026-10-22T10:00:01.0Z "
            "shard-unit-seconds test_archive.ArchiveTests 30.04\n"
            "regression (windows-latest, workflow, 1/4)\tRun the suite\t2026-10-22T10:00:02.0Z "
            "shard-unit-seconds test_lint 13.50\r\n")
        self.assertEqual({"test_lint": 13.0, "test_archive.ArchiveTests": 30.04}, shard_times.read_times(logs))

    def test_rebuild_replaces_measured_suites_and_drops_unknown_units(self):
        workflow, memory = sorted(ci_matrix.shard_units("workflow"))[0], sorted(ci_matrix.shard_units("memory"))[0]
        old = {"source": "old", "workflow": {"test_gone": 1.0}, "memory": {"kept.Tests": 2.0}}
        table = shard_times.rebuild({workflow: 1.26, "test_deleted": 5.0}, old, "runs 1 and 2")
        self.assertEqual({"source": "runs 1 and 2", "workflow": {workflow: 1.3}, "memory": {"kept.Tests": 2.0}}, table)
        self.assertEqual({"test_gone": 1.0}, old["workflow"])
        self.assertEqual({memory: 2.0}, shard_times.rebuild({memory: 2.0}, old, "s")["memory"])

    def test_rebuild_cli_writes_the_table_and_refuses_logs_without_times(self):
        import contextlib
        import io
        unit = sorted(ci_matrix.shard_units("workflow"))[0]
        out = Path(tempfile.mkdtemp()) / "weights.json"
        self.addCleanup(shutil.rmtree, out.parent, ignore_errors=True)
        empty, = self.write_logs("Ran 3 tests in 1.0s\n")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, shard_times.main(["rebuild", "--source", "s", "--out", str(out), str(empty)]))
        self.assertFalse(out.exists())
        log, = self.write_logs(f"shard-unit-seconds {unit} 4.0\n")
        self.assertEqual(0, shard_times.main(["rebuild", "--source", "run 7", "--out", str(out), str(log)]))
        self.assertEqual({"source": "run 7", "workflow": {unit: 4.0}}, json.loads(out.read_text(encoding="utf-8")))

    def test_sharded_step_prints_unit_times_and_discover_is_unchanged(self):
        text = (ci_matrix.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn('PYTHONPATH="$tests" python .github/scripts/shard_times.py run "${names[@]}" || rc=$?', text)
        self.assertIn('python -m unittest discover -s "$tests" -q || rc=$?', text)

    def test_sanduq_gh_runs_every_suite_that_ships_it(self):
        self.assertEqual({"scope", "workflow", "project", "pr"}, suites(["extensions/scripts/shared/sanduq_gh.py"]))
        self.assertTrue(ci_matrix.build(["extensions/scripts/shared/sanduq_gh.py"], "push")["install_smoke"])


class Round5Lint(unittest.TestCase):
    """X23: lint runs the bump guard after the documentation checks; release.py and package.py select as before."""

    def test_lint_runs_check_bumps_after_the_documentation_checks(self):
        text = (ci_matrix.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        lint = re.search(r"^  lint:\n(?:(?:    .*)?\n)+", text, re.M).group(0)
        step = "run: python3 extensions/scripts/release.py check-bumps"
        self.assertIn(step, lint)
        self.assertLess(lint.index("Check documentation links and command coverage"), lint.index(step))

    def test_release_and_package_keep_their_selection(self):
        self.assertEqual([("workflow", "test_release")] * 2,
                         [(i["suite"], i["modules"]) for i in units(ci_matrix.build(["extensions/scripts/release.py"],
                                                                                     "pull_request")["matrix"]["include"])])
        self.assertEqual(ALL, suites(["extensions/scripts/package.py"]))


class Round5ProjectInit(unittest.TestCase):
    """PM5: project-init drives project_init.py through the smoke on both OSes, not once per shell."""

    def job_text(self, name):
        text = (ci_matrix.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        return re.search(rf"^  {name}:\n(?:(?:    .*)?\n)+", text, re.M).group(0)

    def test_project_init_runs_the_python_smoke_on_both_oses(self):
        text = (ci_matrix.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = re.search(r"^  project-init:\n(?:(?:    .*)?\n)+", text, re.M).group(0)
        # The Linux leg runs in the claude installation job.
        self.assertIn("os: [windows-latest]", job)
        self.assertIn("run: python extensions/scripts/smoke_project_init.py\n", self.job_text("installation"))
        # PH-01 (SEC-02): a runner label never comes from matrix data; only the literal windows-latest leg
        # may resolve to a GitHub-hosted runner, everything else falls through to the fork/home logic.
        self.assertIn("runs-on: ${{ matrix.os == 'windows-latest' && 'windows-latest' || ", job)
        self.assertIn("'homek8-general'", job)
        self.assertNotIn("&& matrix.os ||", text)
        self.assertIn("uses: actions/setup-python@", job)
        self.assertIn("- run: python extensions/scripts/smoke_project_init.py\n", job)
        self.assertNotIn("--shell", job)
        self.assertIn("name: project-init-${{ matrix.os }}", job)


def cross_suite_references(root=ci_matrix.ROOT):
    """{(source suite, test suite): test module stems} for every test file under extensions/<suite>/tests that
    names another suite's source: `parents[2] / '<suite>'`, `<pkg>.parent / '<suite>'` or `extensions/<suite>/`.
    Paths under a fixture's `.specify/extensions/` are installed copies the test builds, not sources."""
    names = "|".join(re.escape(s) for s in ci_matrix.SUITES)
    patterns = [re.compile(r"""(?:parents\[2\]|\.parent)\s*/\s*['"](%s)(?=['"/])""" % names),
                re.compile(r"""(?<!\.specify/)extensions/(%s)(?=['"/])""" % names)]
    edges = {}
    for suite in ci_matrix.SUITES:
        for path in sorted((root / f"extensions/{suite}/tests").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for match in (m for pattern in patterns for m in pattern.finditer(text)):
                if match.group(1) != suite:
                    edges.setdefault((match.group(1), suite), set()).add(path.stem)
    return edges


def covered(source, dependent, modules):
    """True when a change to `source` selects the `dependent` modules: a DEPENDENTS edge or a MODULE_RULES entry."""
    if dependent in ci_matrix.DEPENDENTS.get(source, []):
        return True
    named = set()
    for prefix, rule in ci_matrix.MODULE_RULES.items():
        if prefix.startswith(f"extensions/{source}/"):
            named.update(rule.get(dependent, []))
    return modules <= named


class CrossSuiteScan(unittest.TestCase):
    """SAMY-06: a suite whose tests read another suite's source runs when that source changes."""

    def test_every_cross_suite_reference_has_a_selection_edge(self):
        edges = cross_suite_references()
        self.assertIn(("memory", "workflow"), edges)  # the scan sees the references it must
        self.assertIn(("workflow", "pr"), edges)
        missing = {edge: sorted(mods) for edge, mods in edges.items() if not covered(*edge, mods)}
        self.assertEqual({}, missing, "add these to DEPENDENTS (or MODULE_RULES) in .github/scripts/ci_matrix.py")

    def test_the_scan_fails_when_an_edge_is_removed(self):
        edges = cross_suite_references()
        for source, dependent in (("memory", "workflow"), ("workflow", "pr")):
            trimmed = {k: [d for d in v if not (k == source and d == dependent)] for k, v in ci_matrix.DEPENDENTS.items()}
            with unittest.mock.patch.object(ci_matrix, "DEPENDENTS", trimmed):
                self.assertFalse(covered(source, dependent, edges[(source, dependent)]), (source, dependent))

    def test_installed_fixture_paths_are_not_references(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for suite in ci_matrix.SUITES:
                (root / f"extensions/{suite}/tests").mkdir(parents=True)
            (root / "extensions/project/tests/test_x.py").write_text(
                "a = root / '.specify/extensions/workflow/scripts/w.py'\n"
                "b = Path(__file__).resolve().parents[2] / 'memory'\n", encoding="utf-8")
            self.assertEqual({("memory", "project"): {"test_x"}}, cross_suite_references(root))


class ReleaseWindowsGate(unittest.TestCase):
    """SAMY-07: a ready release also needs a scheduled or dispatched ci run with the Windows legs."""

    def test_release_requires_the_windows_legs_and_dispatches_ci_otherwise(self):
        text = (ci_matrix.ROOT / ".github/workflows/release-extensions.yml").read_text(encoding="utf-8")
        self.assertIn("actions: write", text)
        self.assertIn("r['event'] in ('schedule', 'workflow_dispatch')", text)
        self.assertIn("'regression (windows-latest, workflow', 'regression (windows-latest, memory'", text)
        self.assertIn("actions/workflows/ci.yml/dispatches', '-f', 'ref=main'", text)
        self.assertEqual(ci_matrix.WINDOWS_SLOW_SUITES, {"workflow", "memory"})  # the legs the gate names
        self.assertTrue({"schedule", "workflow_dispatch"} <= ci_matrix.WINDOWS_WORKFLOW_EVENTS)
        # Every publishing step waits for the CI gate, not only the pending status.
        steps = text.split("- name: Require successful CI for the current main commit", 1)[1]
        self.assertNotIn("steps.gate.outputs.ready", steps.split("          PY\n", 1)[1])

    def test_a_ci_run_the_release_dispatched_starts_the_release_when_it_passes(self):
        """GITHUB_TOKEN runs start no workflow_run, so the bot-dispatched ci run dispatches the release itself."""
        text = (ci_matrix.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = re.search(r"^  release-trigger:\n(?:(?:    .*)?\n)+", text, re.M).group(0)
        jobs = set(re.findall(r"(?m)^  ([a-z-]+):$", text.split("\njobs:\n", 1)[1])) - {"release-trigger"}
        self.assertEqual(set(re.search(r"needs: \[(.*)\]", job).group(1).split(", ")), jobs)
        for condition in ("!contains(needs.*.result, 'failure')", "!contains(needs.*.result, 'cancelled')",
                          "github.event_name == 'workflow_dispatch' && github.actor == 'github-actions[bot]'",
                          "github.ref == 'refs/heads/main'"):
            self.assertIn(condition, job)
        self.assertIn("runs-on: homek8-general\n    permissions:\n      actions: write\n", job)
        self.assertIn('actions/workflows/release-extensions.yml/dispatches" -f ref=main -f "inputs[ci_run_id]=$GITHUB_RUN_ID"', job)
        # Every other ci run reaches the release through workflow_run, so one run never triggers it twice.
        release = (ci_matrix.ROOT / ".github/workflows/release-extensions.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_run:\n    workflows: [ci]\n    types: [completed]", release)

    def gate(self, run_status, ci_run_id, other_job="success"):
        """Run the release gate's script against a still-running or finished dispatched ci run."""
        text = (ci_matrix.ROOT / ".github/workflows/release-extensions.yml").read_text(encoding="utf-8")
        script = textwrap.dedent(text.split("python - <<'PY'\n", 1)[1].split("          PY\n", 1)[0])
        sha = "a" * 40
        runs = [{"id": 1, "event": "push", "head_branch": "main", "status": "completed", "conclusion": "success"},
                {"id": 2, "event": "workflow_dispatch", "head_branch": "main", "status": run_status,
                 "conclusion": "success" if run_status == "completed" else None}]
        jobs = [{"name": "regression (windows-latest, workflow)", "status": "completed", "conclusion": "success"},
                {"name": "regression (windows-latest, memory)", "status": "completed", "conclusion": "success"},
                {"name": "lint", "status": "completed" if other_job else "in_progress", "conclusion": other_job},
                {"name": "release-trigger", "status": "in_progress", "conclusion": None}]

        def gh(argv, **_):
            self.assertNotIn("-X", argv)  # the gate must not dispatch ci.yml again here
            return json.dumps({"workflow_runs": runs} if "/runs?" in argv[2] else {"jobs": jobs})

        env = {"GH_REPO": "o/r", "HEAD_SHA": sha, "CI_RUN_ID": ci_run_id}
        with unittest.mock.patch.dict("os.environ", env, clear=True), \
                unittest.mock.patch("subprocess.check_output", gh), unittest.mock.patch("builtins.print") as said:
            with self.assertRaises(SystemExit):
                exec(compile(script, "gate", "exec"), {"__name__": "__main__"})
        return said.call_args[0][0]

    def test_the_gate_counts_the_ci_run_that_dispatched_it_while_it_finishes(self):
        """A release dispatched by release-trigger reaches the gate before that ci run completes."""
        self.assertIn("ci run 2 (workflow_dispatch) passed the Windows legs", self.gate("in_progress", "2"))
        # Without the run id, or while another job of that run is unfinished or failed, it is still running.
        self.assertIn("still running", self.gate("in_progress", ""))
        self.assertIn("still running", self.gate("in_progress", "2", other_job=None))
        self.assertIn("still running", self.gate("in_progress", "2", other_job="failure"))
        self.assertIn("still running", self.gate("in_progress", "3"))
        self.assertIn("passed the Windows legs", self.gate("completed", ""))


if __name__ == "__main__":
    unittest.main()
