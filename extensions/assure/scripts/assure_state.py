#!/usr/bin/env python3
"""Record and verify feature-scoped QA documentation freshness."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED_PARTS = {".git", "node_modules", "bin", "obj", "dist", "build", "coverage"}


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
    candidates = [remote_head, "origin/main", "origin/master", "HEAD^"]
    for candidate in candidates:
        if candidate and git(root, "rev-parse", "--verify", candidate):
            merge_base = git(root, "merge-base", "HEAD", candidate)
            return merge_base or candidate
    return ""


def fingerprint(root: Path, feature: Path) -> str:
    digest = hashlib.sha256()
    candidates: set[Path] = set()
    if feature.is_dir():
        candidates.update(path for path in feature.rglob("*") if path.is_file())
    candidates.update(working_paths(root))
    base = comparison_base(root)
    if base:
        for relative in git_raw(root, "diff", "--name-only", "-z", f"{base}..HEAD").split("\0"):
            path = root / relative
            if relative and path.is_file():
                candidates.add(path)
    for path in sorted(candidates, key=lambda item: item.as_posix().lower()):
        try:
            relative = path.resolve().relative_to(root.resolve())
        except ValueError:
            continue
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        posix = relative.as_posix()
        if posix.startswith((".specify/extensions/assure/state/", "User-Manual/")):
            continue
        if posix.startswith(f"docs/{feature.name}/"):
            continue
        digest.update(posix.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


def state_path(root: Path, feature: Path, kind: str) -> Path:
    return root / ".specify" / "extensions" / "assure" / "state" / f"{feature.name}-{kind}.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "record"))
    parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--kind", choices=("analyze", "document"), required=True)
    parser.add_argument("--output", action="append", default=[])
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    root = args.repo_root.resolve()
    feature = args.feature if args.feature.is_absolute() else root / args.feature
    current = fingerprint(root, feature)
    path = state_path(root, feature, args.kind)

    if args.action == "record":
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "kind": args.kind,
            "feature": feature.resolve().relative_to(root).as_posix(),
            "fingerprint": current,
            "gitHead": git(root, "rev-parse", "HEAD"),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "outputs": args.output,
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"current": True, "state": str(path), "recorded": True}))
        return

    if not path.is_file():
        print(json.dumps({"current": False, "reason": "missing", "state": str(path)}))
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(json.dumps({"current": False, "reason": "invalid", "state": str(path)}))
        return
    missing = [item for item in payload.get("outputs", []) if not (root / item).exists()]
    is_current = payload.get("fingerprint") == current and not missing
    print(json.dumps({
        "current": is_current,
        "reason": "current" if is_current else ("missing-output" if missing else "stale"),
        "state": str(path),
        "missingOutputs": missing,
    }))


if __name__ == "__main__":
    main()
