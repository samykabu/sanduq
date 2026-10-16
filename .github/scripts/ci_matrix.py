#!/usr/bin/env python3
"""Map changed files to the CI regression matrix (stdlib only).

Usage (from the `changes` job):
    ci_matrix.py --event pull_request --base <sha> --head <sha>
    ci_matrix.py --event push --base <before> --head <sha>
    ci_matrix.py --event schedule            # runs everything
    ci_matrix.py --event pull_request --files a b c   # offline / tests

Prints `matrix=<json>`, `has_regression=<bool>` and `memory_install=<bool>` lines, written to
$GITHUB_OUTPUT when set. When the changed files cannot be determined, everything runs.
"""
import argparse
import json
import os
import subprocess
import sys

SUITES = ["workflow", "scope", "user-manual", "memory", "illustrate", "progress"]
OSES = ["ubuntu-latest", "windows-latest"]
# Events that run the Windows workflow suite. It is slow, so pushes to main skip it;
# pull requests and the nightly schedule still cover it.
WINDOWS_WORKFLOW_EVENTS = {"pull_request", "schedule", "workflow_dispatch"}
ALWAYS_ALL = {"schedule", "workflow_dispatch"}

# extensions/<key>/** also runs these suites. The mapping lists real dependencies only:
#   progress -> workflow: workflow tests exercise the Progress integration.
#   workflow -> scope: scope loads extensions/workflow/scripts/{workflow,decisions}.py
#                      (extensions/scope/scripts/workflow_policy.py).
#   scope -> workflow: workflow's ScopeCommandTests import Scope's real parser and main()
#                      (extensions/workflow/tests/test_execution_tools.py).
DEPENDENTS = {"progress": ["workflow"], "workflow": ["scope"], "scope": ["workflow"]}

# docs/ paths that a regression suite reads as real inputs (not fixtures). Other docs/ changes only need lint.
#   docs/examples/: illustrate validates booking-illustration-theme.yml (test_illustration_theme.py);
#                   the booking manual is the user-manual example.
DOC_SUITES = {"docs/examples/": ["illustrate", "user-manual"]}


def suites_for(files):
    """Return the set of suites to run, or None when nothing needs regression."""
    suites = set()
    for raw in files:
        path = raw.strip().replace("\\", "/")
        if not path:
            continue
        parts = path.split("/")
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
            # extensions/scripts, presets, catalogs, pending-releases.json, .github, root files, other extensions
            return set(SUITES)
    return suites


def build(files, event):
    suites = set(SUITES) if (files is None or event in ALWAYS_ALL) else suites_for(files)
    include = []
    for suite in SUITES:
        if suite not in suites:
            continue
        for os_name in OSES:
            if suite == "workflow" and os_name == "windows-latest" and event not in WINDOWS_WORKFLOW_EVENTS:
                continue
            include.append({"os": os_name, "suite": suite})
    return {
        "matrix": {"include": include},
        "has_regression": bool(include),
        # smoke_memory_install.py only exercises extensions/memory (and shared tooling, which selects all).
        "memory_install": "memory" in suites,
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
    lines = [f"matrix={json.dumps(result['matrix'], separators=(',', ':'))}",
             f"has_regression={str(result['has_regression']).lower()}",
             f"memory_install={str(result['memory_install']).lower()}"]
    print("\n".join(lines))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
