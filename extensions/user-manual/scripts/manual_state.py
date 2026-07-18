#!/usr/bin/env python3
"""Record or verify User Manual freshness for an active feature."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def git_raw(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else ""


def working_paths(root: Path) -> set[Path]:
    paths: set[Path] = set()
    fields = git_raw(root, "status", "--porcelain=v1", "-z").split("\0")
    index = 0
    while index < len(fields):
        field = fields[index]
        if not field:
            index += 1
            continue
        status = field[:2]
        relative = field[3:] if len(field) > 3 else ""
        path = root / relative
        if path.is_file():
            paths.add(path)
        index += 2 if "R" in status or "C" in status else 1
    return paths


def comparison_base(root: Path) -> str:
    remote_head = git(root, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    for candidate in (remote_head, "origin/main", "origin/master", "HEAD^"):
        if candidate and git(root, "rev-parse", "--verify", candidate):
            return git(root, "merge-base", "HEAD", candidate) or candidate
    return ""


def digest_inputs(root: Path, feature: Path) -> str:
    digest = hashlib.sha256()
    files = {path for path in feature.rglob("*") if path.is_file()} if feature.is_dir() else set()
    files.update(working_paths(root))
    base = comparison_base(root)
    if base:
        for relative in git_raw(root, "diff", "--name-only", "-z", f"{base}..HEAD").split("\0"):
            path = root / relative
            if relative and path.is_file():
                files.add(path)
    for path in sorted(files, key=lambda value: value.as_posix().lower()):
        try:
            relative = path.resolve().relative_to(root)
        except ValueError:
            continue
        posix = relative.as_posix()
        if posix.startswith(("User-Manual/site/", "User-Manual/pdf/", "User-Manual/.state/")):
            continue
        if posix.startswith(f"docs/{feature.name}/"):
            continue
        if any(part in {".git", "node_modules", "bin", "obj", "dist", "build", "coverage"} for part in relative.parts):
            continue
        digest.update(posix.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("record", "status"))
    parser.add_argument("--feature", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    feature = args.feature if args.feature.is_absolute() else root / args.feature
    state = root / "User-Manual" / ".state" / "features" / f"{feature.name}.json"
    current = digest_inputs(root, feature)
    if args.action == "record":
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({
            "schemaVersion": 1,
            "feature": feature.resolve().relative_to(root).as_posix(),
            "fingerprint": current,
            "gitHead": git(root, "rev-parse", "HEAD"),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"current": True, "recorded": True, "state": str(state)}))
        return
    if not state.is_file():
        print(json.dumps({"current": False, "reason": "missing", "state": str(state)}))
        return
    try:
        saved = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(json.dumps({"current": False, "reason": "invalid", "state": str(state)}))
        return
    matches = saved.get("fingerprint") == current
    print(json.dumps({"current": matches, "reason": "current" if matches else "stale", "state": str(state)}))


if __name__ == "__main__":
    main()
