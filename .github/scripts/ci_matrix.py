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
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITES = ["workflow", "scope", "user-manual", "memory", "illustrate", "progress", "assure", "pr", "project"]
OSES = ["ubuntu-latest", "windows-latest"]
# Suites whose Windows runs are slow (workflow 35-42 min, memory 14-16 min), so pushes to main skip
# them; pull requests and the nightly schedule still cover them.
WINDOWS_SLOW_SUITES = {"workflow", "memory"}
WINDOWS_WORKFLOW_EVENTS = {"pull_request", "schedule", "workflow_dispatch"}
ALWAYS_ALL = {"schedule", "workflow_dispatch"}
# The Windows workflow suite runs as this many parallel jobs; Linux workflow stays one job.
WINDOWS_WORKFLOW_SHARDS = 4
# Suites whose tests live outside extensions/<suite>/tests: (folder, modules). Project has no tests
# folder of its own; ci.yml also discovers extensions/project/tests once it exists.
SUITE_TESTS = {"project": ("extensions/workflow/tests", "test_project_sync_summary")}

# extensions/<key>/** also runs these suites. The mapping lists real dependencies only:
#   progress -> workflow: workflow tests exercise the Progress integration.
#   workflow -> scope: scope loads extensions/workflow/scripts/{workflow,decisions}.py
#                      (extensions/scope/scripts/workflow_policy.py).
#   scope -> workflow: workflow's ScopeCommandTests import Scope's real parser and main()
#                      (extensions/workflow/tests/test_execution_tools.py).
#   assure -> workflow: workflow tests render documentation-gates.yml and run assure_state.py.
#   pr -> workflow: workflow tests lint PR bodies and the guard hook covers gh pr.
DEPENDENTS = {"progress": ["workflow"], "workflow": ["scope"], "scope": ["workflow"],
              "assure": ["workflow"], "pr": ["workflow"]}

# docs/ paths that a regression suite reads as real inputs (not fixtures). Other docs/ changes only need lint.
#   docs/examples/: illustrate validates booking-illustration-theme.yml (test_illustration_theme.py);
#                   the booking manual is the user-manual example.
DOC_SUITES = {"docs/examples/": ["illustrate", "user-manual"]}

# Release metadata and top-level prose: lint validates them (pending/manifest/catalog checks, check_docs
# links), no suite reads them. Per-extension READMEs stay with their suite (progress tests read its README).
LINT_ONLY = {"CHANGELOG.md", "README.md", "CONTRIBUTING.md", "extensions/README.md",
             "extensions/pending-releases.json"}
# What installation, upgrade, project-init and dryrun exercise (plus every extensions/<id>/extension.yml).
INSTALL_PREFIXES = ("extensions/workflow/", "extensions/project/", "extensions/scripts/package.",
                    "extensions/scripts/smoke_", "extensions/scripts/shared/", "presets/", "prototypes/",
                    "vendor.lock.json", ".github/workflows/ci.yml", ".github/scripts/")
# shortcut: any vendor.lock.json change counts as an Illustrate vendor bump, even one to another input;
# parse the lock diff if those runs ever cost real time.
ILLUSTRATE_VENDORED = ("vendor.lock.json", "extensions/illustrate/skill/")


def normalized(files):
    return [p for p in (raw.strip().replace("\\", "/") for raw in files) if p]


def suites_for(files):
    """Return the set of suites to run (empty when nothing needs regression)."""
    suites = set()
    for path in normalized(files):
        parts = path.split("/")
        if path in LINT_ONLY:
            continue
        if parts[0] == "docs":
            for prefix, dependents in DOC_SUITES.items():
                if path.startswith(prefix):
                    suites.update(dependents)
            continue  # lint runs check_docs.py for the rest of docs/
        if parts[0] == "extensions" and len(parts) > 2 and parts[1] in SUITES:
            suite = parts[1]
            suites.add(suite)
            suites.update(DEPENDENTS.get(suite, []))
        else:
            # extensions/scripts, presets, catalogs, .github, other root files, other extensions
            return set(SUITES)
    return suites


def install_smoke(files):
    return any(p.startswith(INSTALL_PREFIXES) or (p.startswith("extensions/") and p.count("/") == 2
                                                  and p.endswith("/extension.yml")) for p in normalized(files))


def workflow_shards(count=WINDOWS_WORKFLOW_SHARDS):
    """Split the workflow test modules (discover's test*.py) into `count` lists, largest module first
    onto the lightest shard. shortcut: weighs modules by file size, not measured time; switch to
    per-module seconds if a CI run shows one shard far slower than the others."""
    shards, load = [[] for _ in range(count)], [0] * count
    files = sorted((ROOT / "extensions/workflow/tests").glob("test*.py"), key=lambda p: (-p.stat().st_size, p.name))
    for path in files:
        i = load.index(min(load))
        shards[i].append(path.stem)
        load[i] += path.stat().st_size
    return [sorted(s) for s in shards]


def build(files, event):
    everything = files is None or event in ALWAYS_ALL
    suites = set(SUITES) if everything else suites_for(files)
    if "workflow" in suites:
        suites.discard("project")  # the workflow suite already runs the project module
    include = []
    for suite in SUITES:
        if suite not in suites:
            continue
        tests, modules = SUITE_TESTS.get(suite, (f"extensions/{suite}/tests", ""))
        for os_name in OSES:
            windows = os_name == "windows-latest"
            if windows and suite in WINDOWS_SLOW_SUITES and event not in WINDOWS_WORKFLOW_EVENTS:
                continue
            if windows and suite == "workflow":
                for n, shard in enumerate(workflow_shards(), 1):
                    include.append({"os": os_name, "suite": suite, "tests": tests,
                                    "shard": f"{n}/{WINDOWS_WORKFLOW_SHARDS}", "modules": " ".join(shard)})
                continue
            include.append({"os": os_name, "suite": suite, "tests": tests, "modules": modules})
    return {
        "matrix": {"include": include},
        "has_regression": bool(include),
        # smoke_memory_install.py only exercises extensions/memory (and shared tooling, which selects all).
        "memory_install": "memory" in suites,
        "install_smoke": everything or install_smoke(files),
        "illustrate_vendored": everything or any(p.startswith(ILLUSTRATE_VENDORED) for p in normalized(files)),
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
