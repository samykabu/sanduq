#!/usr/bin/env python3
"""Record or verify content and output freshness; noncurrent status exits 1."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

EXCLUDED = {".git", "node_modules", "bin", "obj", "dist", "build", "coverage", "__pycache__"}
OUTPUT_SKIP = {".state", "site", "pdf", "__pycache__"}


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise ValueError("Git freshness input unavailable: " + result.stderr.strip())
    return result.stdout


def relative(root: Path, value) -> str:
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Path outside project: " + str(value))
    return path.relative_to(root).as_posix()


def fingerprints(root: Path, paths) -> dict:
    """SHA-256 per file, None when missing. CRLF is normalized so a Windows
    checkout and a Linux CI checkout of the same commit agree."""
    result = {}
    for key in sorted({relative(root, value) for value in paths}):
        path = root / key
        result[key] = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() if path.is_file() else None
    return result


def base_ref(root: Path, explicit: str | None) -> str:
    """The merge-base with the target branch. No `HEAD^` fallback: it would hide
    earlier commits on a longer branch."""
    if explicit:
        return git(root, "merge-base", "HEAD", explicit).strip()
    for candidate in ("refs/remotes/origin/HEAD", "origin/main", "origin/master"):
        try:
            return git(root, "merge-base", "HEAD", candidate).strip()
        except ValueError:
            continue
    raise ValueError("Default remote branch unknown; supply --base-ref explicitly.")


def inputs(root: Path, feature: str, base: str | None) -> dict:
    paths = {relative(root, p) for p in (root / feature).rglob("*") if p.is_file()}
    comparison = base_ref(root, base)
    # name-only includes deleted files; diffing against the working tree includes
    # staged and unstaged edits; ls-files adds untracked files.
    paths.update(filter(None, git(root, "diff", "--name-only", "-z", comparison).split("\0")))
    paths.update(filter(None, git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")))

    def included(value: str) -> bool:
        # The manual is the output, so it is never its own input.
        return not (any(part in EXCLUDED for part in Path(value).parts)
                    or value.startswith(("User-Manual/", "docs/" + Path(feature).name + "/")))

    return {"base_commit": comparison, "files": fingerprints(root, [p for p in paths if included(p)])}


def record_or_status(root: Path, feature: Path, state_path: Path, action: str, outputs: list, base: str | None) -> dict:
    feature = relative(root, feature)
    saved = json.loads(state_path.read_text(encoding="utf-8-sig")) if state_path.is_file() else None
    # Pin the recorded merge-base so local and CI comparisons repeat, unless the
    # caller names a new target branch.
    comparison = base or (saved or {}).get("inputs", {}).get("base_commit")
    current = inputs(root, feature, comparison)
    if action == "record":
        if not outputs:
            raise ValueError("At least one actual output file is required.")
        output_hashes = fingerprints(root, outputs)
        if any(value is None for value in output_hashes.values()):
            raise ValueError("A declared output is missing.")
        payload = {"schemaVersion": 2, "feature": feature, "kind": "manual", "inputs": current,
                   "outputs": output_hashes, "gitHead": git(root, "rev-parse", "HEAD").strip()}
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return {"current": True, "recorded": True, "state": relative(root, state_path)}
    if not saved:
        return {"current": False, "reason": "missing"}
    if saved.get("schemaVersion") != 2:
        return {"current": False, "reason": "legacy-state-regenerate"}
    matches = (saved.get("feature") == feature and saved.get("inputs") == current
               and bool(saved.get("outputs")) and fingerprints(root, saved["outputs"]) == saved["outputs"])
    return {"current": matches, "reason": "current" if matches else "stale-input-or-output"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("record", "status"))
    parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref", help="Target branch to compare against (default: origin HEAD)")
    parser.add_argument("--output", action="append", default=[], help="Manual output file; repeatable")
    parser.add_argument("--summary", action="store_true", help="Print one line (ok/error, counts) instead of JSON")
    parser.add_argument("--json", action="store_true", help="Print the full JSON result (the default output)")
    args = parser.parse_args()
    if args.summary and args.json:
        parser.error("--summary and --json cannot be combined")
    root = args.repo_root.resolve()
    feature = args.feature if args.feature.is_absolute() else root / args.feature
    state = root / "User-Manual/.state/features" / f"{feature.name}.json"
    manual = root / "User-Manual"
    outputs = args.output or [p.relative_to(root).as_posix() for p in manual.rglob("*")
                              if p.is_file() and not any(part in OUTPUT_SKIP for part in p.relative_to(manual).parts)]
    try:
        result = record_or_status(root, feature, state, args.action, outputs, args.base_ref)
    except (ValueError, OSError) as exc:
        result = {"current": False, "reason": str(exc)}
    if args.summary:
        word = "ok" if result["current"] else "error"
        # An exception message can carry newlines; a summary is always one line.
        reason = " ".join(str(result.get("reason", "n/a")).split())
        detail = " recorded=1" if result.get("recorded") else f" reason={reason}"
        print(f"{word} action={args.action} kind=manual outputs={len(outputs)}{detail}")
    else:
        print(json.dumps(result))
    return 0 if result["current"] else 1


if __name__ == "__main__":
    sys.exit(main())
