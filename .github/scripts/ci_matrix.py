#!/usr/bin/env python3
"""Map changed files to the CI regression matrix (stdlib only).

Usage (from the `changes` job):
    ci_matrix.py --event pull_request --base <sha> --head <sha>
    ci_matrix.py --event push --base <before> --head <sha>
    ci_matrix.py --event schedule            # runs everything
    ci_matrix.py --event pull_request --files a b c   # offline / tests

Prints `matrix=<json>`, `has_regression=<bool>`, `memory_install=<bool>`, `install_smoke=<bool>` and
`illustrate_vendored=<bool>` lines, written to $GITHUB_OUTPUT when set. When the changed files cannot be
determined, everything runs.
"""
import argparse
import ast
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITES = ["workflow", "scope", "user-manual", "memory", "illustrate", "progress", "assure", "pr", "project"]
OSES = ["ubuntu-latest", "windows-latest"]
# Suites whose Windows runs are slow (workflow 21-23 min of runner time, memory 8-12 min), so pushes to
# main skip them; pull requests and the nightly schedule still cover them.
WINDOWS_SLOW_SUITES = {"workflow", "memory"}
WINDOWS_WORKFLOW_EVENTS = {"pull_request", "schedule", "workflow_dispatch"}
ALWAYS_ALL = {"schedule", "workflow_dispatch"}
# Windows runs of these suites are split into parallel jobs. Workflow shards by module, memory by test
# class (test_archive is one class and about two thirds of the suite).
WINDOWS_SHARDS = {"workflow": 4, "memory": 2}
# Linux shards the whole workflow suite (about 5 to 15 minutes there) with the same weights. Every other
# Linux run (memory takes about 1.5 minutes there, the rest under one) shares one batch job, because the
# self-hosted scale set runs few jobs at once and each job's setup costs about a minute.
LINUX_SHARDS = {"workflow": 4}
# Measured seconds per module (workflow) or module.Class (memory); see its "source" key.
WEIGHTS = ROOT / ".github/scripts/shard_weights.json"
# The vendored Illustrate checks also run on scheduled runs on this weekday (Monday = 0).
VENDORED_WEEKDAY = 6

# extensions/<key>/** also runs these suites. The mapping lists real dependencies only:
#   progress -> workflow: workflow tests exercise the Progress integration.
#   workflow -> scope: scope loads extensions/workflow/scripts/{workflow,decisions}.py
#                      (extensions/scope/scripts/workflow_policy.py).
#   scope -> workflow: workflow's ScopeCommandTests import Scope's real parser and main()
#                      (extensions/workflow/tests/test_execution_tools.py).
#   assure -> workflow: workflow tests render documentation-gates.yml and run assure_state.py.
#   pr -> workflow: workflow tests lint PR bodies and the guard hook covers gh pr.
#   project -> workflow: workflow's sync_project runs project_sync.py (test_sync_binding, test_workflow).
#   memory -> workflow: workflow's Memory handoff tests run Memory's real archive.py (test_memory_handoff,
#                       test_memory_hook_lifecycle).
#   workflow -> pr: pr_publish tests import extensions/workflow/scripts (test_pr_publish).
# test_ci_matrix.py scans every extensions/<suite>/tests/*.py for references to another suite's source and
# fails when neither this table nor MODULE_RULES covers one.
DEPENDENTS = {"progress": ["workflow"], "workflow": ["scope", "pr"], "scope": ["workflow"],
              "assure": ["workflow"], "pr": ["workflow"], "project": ["workflow"], "memory": ["workflow"]}

# Paths that run only some modules of a suite: {path prefix: {suite: [modules]}}.
#   Illustrate's hook is wired into managed installs by install.wire_illustrate (test_install_hooks).
#   The repository tooling below is read by one module each.
#   Scope's plan tests and PR's diagram recipe tests read Illustrate's skill files.
MODULE_RULES = {"extensions/illustrate/hooks/": {"workflow": ["test_install_hooks"]},
                "extensions/illustrate/skill/": {"scope": ["test_plan"], "pr": ["test_pr_diagram_recipe"]},
                "extensions/scripts/release.py": {"workflow": ["test_release"]},
                "extensions/scripts/check_docs.py": {"assure": ["test_descriptions"]},
                "extensions/scripts/benchmark_instructions.py": {"scope": ["test_instructions"]}}

# Files that extensions/scripts/package.py injects into other packages, with every suite that ships or
# tests them. test_ci_matrix.py checks this against the built archives. Other shared files run everything.
INJECTED = {"extensions/scripts/shared/sanduq_freshness.py": ["assure", "user-manual", "workflow"],
            "extensions/scripts/shared/deps.py": ["pr", "assure", "user-manual"],
            "extensions/scripts/shared/check_inputs.py": ["memory", "workflow"],
            "extensions/scripts/shared/bounded_json.py": ["memory", "workflow"],
            "extensions/scripts/shared/evidence_snapshot.py": ["workflow"],
            "extensions/scripts/shared/sanduq_remote.py": ["workflow", "project", "scope"],
            "extensions/scripts/shared/sanduq_gh.py": ["scope", "workflow", "project", "pr"],
            "extensions/scripts/shared/sanduq_pr_lint.py": ["pr", "workflow"],
            "extensions/scripts/shared/sanduq_fs.py": ["workflow", "memory", "scope"],
            "extensions/scope/scripts/sanduq_scope_github.py": ["scope", "workflow"],
            "extensions/workflow/scripts/sanduq_hash.py": ["workflow", "assure", "user-manual"],
            "extensions/workflow/scripts/sanduq_ci.py": ["workflow", "assure", "user-manual"]}

# docs/ paths that a regression suite reads as real inputs (not fixtures). Other docs/ changes only need lint.
#   docs/examples/: illustrate validates booking-illustration-theme.yml (test_illustration_theme.py);
#                   the booking manual is the user-manual example.
DOC_SUITES = {"docs/examples/": ["illustrate", "user-manual"]}

# Release metadata, top-level prose and repository tooling: lint validates or tests them, no suite reads
# them. Per-extension READMEs stay with their suite (progress tests read its README).
LINT_ONLY = {"CHANGELOG.md", "README.md", "CONTRIBUTING.md", "extensions/README.md",
             "extensions/pending-releases.json", ".github/actionlint.yaml",
             ".github/workflows/release-extensions.yml", ".github/workflows/vendor-update.yml",
             ".github/workflows/prune-artifacts.yml", "extensions/scripts/test_check_docs.py",
             "extensions/scripts/validate_skills.py", "extensions/scripts/vendor.py"}
LINT_ONLY_PREFIXES = ("extensions/scripts/tests/",)
# What installation, upgrade, project-init and dryrun exercise (plus every extensions/<id>/extension.yml).
# Illustrate's hook is wired into the installed hooks.
INSTALL_PREFIXES = ("extensions/workflow/", "extensions/project/", "extensions/scripts/package.",
                    "extensions/scripts/smoke_", "extensions/scripts/shared/", "presets/",
                    "vendor.lock.json", ".github/workflows/ci.yml", ".github/scripts/",
                    "extensions/illustrate/hooks/")
# shortcut: any vendor.lock.json change counts as an Illustrate vendor bump, even one to another input;
# parse the lock diff if those runs ever cost real time.
ILLUSTRATE_VENDORED = ("vendor.lock.json", "extensions/illustrate/skill/")
# Project's tests moved from the workflow suite to extensions/project/tests (PM19); either location works.
PROJECT_LEGACY = ("extensions/workflow/tests", "test_project_sync_summary")


def normalized(files):
    return [p for p in (raw.strip().replace("\\", "/") for raw in files) if p]


def add(selection, suite, modules=None):
    """Select a whole suite (modules None) or some of its modules; a whole selection wins."""
    if modules is None or selection.get(suite, set()) is None:
        selection[suite] = None
    else:
        selection.setdefault(suite, set()).update(modules)


def selection_for(files):
    """Return {suite: None for the whole suite, or a set of modules}; empty when nothing needs regression."""
    selection = {}
    for path in normalized(files):
        parts = path.split("/")
        if path in LINT_ONLY or path.startswith(LINT_ONLY_PREFIXES):
            continue
        if parts[0] == "docs":
            for prefix, dependents in DOC_SUITES.items():
                if path.startswith(prefix):
                    for suite in dependents:
                        add(selection, suite)
            continue  # lint runs check_docs.py for the rest of docs/
        rules = [rule for prefix, rule in MODULE_RULES.items() if path.startswith(prefix)]
        for rule in rules:
            for suite, modules in rule.items():
                add(selection, suite, modules)
        if path in INJECTED:
            for suite in INJECTED[path]:
                for name in [suite] + DEPENDENTS.get(suite, []):
                    add(selection, name)
        elif parts[0] == "extensions" and len(parts) > 2 and parts[1] in SUITES:
            for name in [parts[1]] + DEPENDENTS.get(parts[1], []):
                add(selection, name)
        elif not rules:
            # extensions/scripts, presets, catalogs, .github, other root files, other extensions
            return {suite: None for suite in SUITES}
    return selection


def suites_for(files):
    """Return the set of suites to run (empty when nothing needs regression)."""
    return set(selection_for(files))


def install_smoke(files):
    return any(p.startswith(INSTALL_PREFIXES) or (p.startswith("extensions/") and p.count("/") == 2
                                                  and p.endswith("/extension.yml")) for p in normalized(files))


def suite_tests(suite):
    """(folder, modules) the suite runs from; modules "" means discover the folder."""
    if suite == "project" and not any((ROOT / "extensions/project/tests").glob("test*.py")) \
            and (ROOT / PROJECT_LEGACY[0] / (PROJECT_LEGACY[1] + ".py")).is_file():
        return PROJECT_LEGACY
    return f"extensions/{suite}/tests", ""


def test_classes(path):
    """Top-level unittest.TestCase classes of a test module, found without importing it."""
    cases = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.ClassDef):
            bases = [b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "") for b in node.bases]
            if any(b.endswith("TestCase") or b in cases for b in bases):
                cases.add(node.name)
    return sorted(cases)


def shard_units(suite):
    """{unit: size in bytes}: modules for workflow, module.Class for memory (unittest names both)."""
    units = {}
    for path in sorted((ROOT / f"extensions/{suite}/tests").glob("test*.py")):
        if suite != "memory":
            units[path.stem] = path.stat().st_size
            continue
        lines, cases = path.read_text(encoding="utf-8").splitlines(keepends=True), test_classes(path)
        for node in ast.parse("".join(lines)).body:
            if isinstance(node, ast.ClassDef) and node.name in cases:
                units[f"{path.stem}.{node.name}"] = len("".join(lines[node.lineno - 1:node.end_lineno]).encode())
    return units


def shards(suite, count=None, weights=None):
    """Split a suite's units into `count` lists, heaviest first onto the lightest shard. A unit's weight is
    its measured seconds; a unit missing from the table weighs its bytes at the table's seconds per byte."""
    count = count or WINDOWS_SHARDS[suite]
    if weights is None:
        weights = json.loads(WEIGHTS.read_text(encoding="utf-8")).get(suite, {}) if WEIGHTS.is_file() else {}
    units = shard_units(suite)
    known = [u for u in units if u in weights]
    rate = sum(weights[u] for u in known) / max(1, sum(units[u] for u in known)) if known else 1.0
    cost = {u: weights.get(u, units[u] * rate) for u in units}
    lists, load = [[] for _ in range(count)], [0.0] * count
    for unit in sorted(units, key=lambda u: (-cost[u], u)):
        i = load.index(min(load))
        lists[i].append(unit)
        load[i] += cost[unit]
    return [sorted(s) for s in lists]


def workflow_shards(count=None):
    return shards("workflow", count)


def vendored(files, event, today=None):
    """Upstream verifies the vendored skill at the locked sha and lint proves the bytes equal, so its
    builders and verifiers run on a vendor change, on demand, on unknown changes and once a week."""
    if event == "schedule":
        return (today or datetime.datetime.now(datetime.timezone.utc).date()).weekday() == VENDORED_WEEKDAY
    if event == "workflow_dispatch" or files is None:
        return True
    return any(p.startswith(ILLUSTRATE_VENDORED) for p in normalized(files))


def build(files, event, today=None):
    """Matrix entries: os, suite (the job name), suites (for step conditions) and runs, one
    "<suite> <tests folder> [modules...]" line per suite the job runs in order; shards add shard."""
    everything = files is None or event in ALWAYS_ALL
    selection = {suite: None for suite in SUITES} if everything else selection_for(files)
    include, batch = [], []
    for suite in SUITES:
        if suite not in selection:
            continue
        tests, modules = suite_tests(suite)
        partial = selection[suite] is not None
        if partial:
            modules = " ".join(sorted(selection[suite]))
        for os_name in OSES:
            windows = os_name == "windows-latest"
            if windows and not partial and suite in WINDOWS_SLOW_SUITES and event not in WINDOWS_WORKFLOW_EVENTS:
                continue
            counts = WINDOWS_SHARDS if windows else LINUX_SHARDS
            if not partial and suite in counts:
                for n, shard in enumerate(shards(suite, counts[suite]), 1):
                    include.append({"os": os_name, "suite": suite, "suites": [suite], "shard": f"{n}/{counts[suite]}",
                                    "runs": " ".join([suite, tests] + shard)})
                continue
            run = " ".join(filter(None, [suite, tests, modules]))
            if windows:
                include.append({"os": os_name, "suite": suite, "suites": [suite], "runs": run})
            else:
                batch.append((suite, run))
    if batch:
        # First, so the longest Linux job asks for a runner first.
        include.insert(0, {"os": "ubuntu-latest", "suite": " + ".join(s for s, _ in batch),
                           "suites": [s for s, _ in batch], "runs": "\n".join(r for _, r in batch)})
    return {
        "matrix": {"include": include},
        "has_regression": bool(include),
        # smoke_memory_install.py only exercises extensions/memory (and shared tooling, which selects all).
        "memory_install": "memory" in selection,
        "install_smoke": everything or install_smoke(files),
        "illustrate_vendored": vendored(files, event, today),
    }


def changed_files(event, base, head):
    if event in ALWAYS_ALL or not head or not base or set(base) == {"0"}:
        return None
    sep = "..." if event == "pull_request" else ".."
    try:
        out = subprocess.run(["git", "diff", "--name-only", "--no-renames", f"{base}{sep}{head}"],
                             check=True, capture_output=True, text=True).stdout
    except (subprocess.CalledProcessError, OSError):
        return None  # e.g. force push removed `before`; run everything
    return out.splitlines()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--event", required=True)
    p.add_argument("--base", default="")
    p.add_argument("--head", default="")
    p.add_argument("--files", nargs="*", help="explicit changed files (skips git)")
    a = p.parse_args(argv)
    files = a.files if a.files is not None else changed_files(a.event, a.base, a.head)
    result = build(files, a.event)
    lines = [f"matrix={json.dumps(result['matrix'], separators=(',', ':'))}"]
    lines += [f"{key}={str(result[key]).lower()}"
              for key in ("has_regression", "memory_install", "install_smoke", "illustrate_vendored")]
    print("\n".join(lines))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
