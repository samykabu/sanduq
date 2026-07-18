#!/usr/bin/env python3
"""Configure QA lifecycle hooks without requiring a YAML dependency."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


def find_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".specify" / "extensions.yml").is_file():
            return candidate
    raise SystemExit(".specify/extensions.yml not found; run inside an initialized Spec Kit project")


def update_hooks(text: str, integrated: bool) -> tuple[str, int]:
    lines = text.splitlines()
    event = ""
    in_qa = False
    changed = 0
    for index, line in enumerate(lines):
        event_match = re.match(r"^  ([a-z0-9_-]+):\s*$", line)
        if event_match:
            event = event_match.group(1)
            in_qa = False
            continue
        item_match = re.match(r"^    - extension:\s*([^\s#]+)", line)
        if item_match:
            in_qa = item_match.group(1).strip("\"'") == "qa"
            continue
        if in_qa and re.match(r"^      optional:\s*(true|false)\s*$", line):
            mandatory = integrated and event == "before_implement"
            value = "false" if mandatory else "true"
            replacement = re.sub(r"(optional:\s*)(true|false)", rf"\g<1>{value}", line)
            if replacement != line:
                lines[index] = replacement
                changed += 1
            in_qa = False
    if not any("extension: qa" in line for line in lines):
        raise SystemExit("no QA hooks found; reinstall the qa extension and retry")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), changed


def config_text(mode: str) -> str:
    integrated = mode == "integrated"
    enabled = str(integrated).lower()
    return f'''schema_version: "1.0"
lifecycle:
  mode: {mode}
  require_analyze_before_implement: {enabled}
  require_document_before_pr: {enabled}
freshness:
  policy: feature-inputs-and-working-tree
  state_directory: .specify/extensions/qa/state
output:
  directory_name: qa
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("integrated", "manual"), required=True)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = args.repo_root.resolve() if args.repo_root else find_root(Path.cwd().resolve())
    extensions_yml = root / ".specify" / "extensions.yml"
    original = extensions_yml.read_text(encoding="utf-8")
    updated, changed = update_hooks(original, args.mode == "integrated")
    config = root / ".specify" / "extensions" / "qa" / "qa-config.yml"

    if not args.dry_run:
        extensions_yml.write_text(updated, encoding="utf-8")
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(config_text(args.mode), encoding="utf-8")
        workflow_source = Path(__file__).resolve().parents[1] / "assets" / "github" / "documentation-gates.yml"
        workflow_target = root / ".github" / "workflows" / "documentation-gates.yml"
        workflow_target.parent.mkdir(parents=True, exist_ok=True)
        if not workflow_target.exists():
            shutil.copy2(workflow_source, workflow_target)

    print(f"qa mode={args.mode} hooks_changed={changed} dry_run={str(args.dry_run).lower()}")
    print(config)


if __name__ == "__main__":
    main()
