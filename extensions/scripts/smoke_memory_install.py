#!/usr/bin/env python3
"""Install the packaged Memory extension through real Spec Kit on all supported hosts."""
import argparse
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import zipfile
from package import ROOT, package


def smoke(specify="specify"):
    folder = ROOT / "dist/memory-install-tests"
    folder.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(dir=folder)).resolve()
    built = package("memory", output=workspace / "memory.zip")
    with zipfile.ZipFile(built["archive"]) as archive:
        assert not any("/tests/" in name or "__pycache__" in name for name in archive.namelist())
        archive.extractall(workspace / "packages")
    outcomes = []
    for host in ("codex", "claude", "copilot"):
        for shell in ("sh", "ps"):
            project = workspace / (host + "-" + shell)
            project.mkdir()
            count = 0

            def run(args, expected=0):
                nonlocal count
                count += 1
                result = subprocess.run(args, cwd=project, input="y\n", text=True, encoding="utf-8", capture_output=True)
                (project / f"{count:02}.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
                if (result.returncode == 0) != (expected == 0):
                    raise RuntimeError(f"{args} failed: inspect {project}/{count:02}.log")
                return result.stdout

            run([specify, "init", "--here", "--force", "--ignore-agent-tools", "--integration", host, "--script", shell])
            run(["git", "init", "-b", "main"])
            run([specify, "extension", "add", "--dev", str(workspace / "packages/memory")])
            installer = str(project / ".specify/extensions/memory/scripts/install.py")
            initialized = json.loads(run([sys.executable, installer, "--target-branch", "main"]))
            assert not initialized["automatic_enabled"], initialized
            policy = project / ".specify/memory-policy.json"
            original_policy = policy.read_bytes()
            run([sys.executable, installer])
            assert original_policy == policy.read_bytes()
            state = json.loads(run([sys.executable, str(project / ".specify/extensions/memory/scripts/archive.py"), "pending", "--gate"]))
            assert state["success"] and not state["data"]["enabled"], state
            config = (project / ".specify/extensions.yml").read_text()
            assert config.index("command: speckit.memory.session") < config.index("command: speckit.memory.impact")
            assert config.count("command: speckit.memory.session") == 1
            assert len(initialized["commands"]) == 7
            # Exercise optional Git-extension guards against the same pinned build.
            run([specify, "extension", "add", "git"])
            with_git = json.loads(run([sys.executable, installer]))
            assert len(with_git["guards"]) > len(initialized["guards"])
            registry = project / "specs/.archive-index.json"
            registry.parent.mkdir(exist_ok=True)
            registry.write_text(json.dumps({"schema_version": 1, "high_water": 9, "archived": {"specs/009-old": {}}}))
            run([sys.executable, str(project / ".specify/extensions/memory/scripts/archive.py"), "pending", "--gate"])
            if shell == "ps":
                executable = shutil.which("pwsh")
                arguments = ["-NoProfile", "-File", str(project / ".specify/scripts/powershell/create-new-feature.ps1"), "-Json", "-DryRun", "-Number", "9", "new feature"]
            else:
                git = Path(shutil.which("git"))
                candidate = git.parents[1] / "bin/bash.exe"
                executable = str(candidate) if candidate.exists() else shutil.which("bash")
                arguments = [str(project / ".specify/scripts/bash/create-new-feature.sh"), "--json", "--dry-run", "--number", "9", "new feature"]
            if executable:
                run([executable, *arguments], expected=1)
            run([specify, "extension", "list"])
            outcomes.append({"host": host, "shell": shell, "automatic_enabled": False, "commands": 7})
    report = {"success": True, "package_sha256": built["sha256"], "cases": outcomes}
    (workspace / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({**report, "evidence": str(workspace)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specify", default="specify")
    smoke(parser.parse_args().specify)
