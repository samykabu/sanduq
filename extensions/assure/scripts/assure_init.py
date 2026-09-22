#!/usr/bin/env python3
"""Configure QA lifecycle hooks using parsed YAML and verified postconditions."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import yaml

try:  # vendored beside this script in a built package
    import sanduq_ci
except ImportError:  # canonical source tree
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workflow" / "scripts"))
    import sanduq_ci


def find_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".specify" / "extensions.yml").is_file():
            return candidate
    raise SystemExit(".specify/extensions.yml not found; run inside an initialized Spec Kit project")


def update_hooks(text: str, integrated: bool) -> tuple[str, int]:
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict) or not isinstance(doc.get('hooks'), dict):
        raise SystemExit('invalid extensions.yml: expected a hooks mapping')
    changed = 0
    found_gate = False
    for event, hooks in doc['hooks'].items():
        if not isinstance(hooks, list) or any(not isinstance(h, dict) for h in hooks):
            raise SystemExit('invalid hook list: ' + event)
        for hook in hooks:
            if hook.get('extension') != 'assure':
                continue
            optional = not (integrated and event == 'before_implement')
            if event == 'before_implement':
                found_gate = True
            if hook.get('optional') is not optional:
                changed += 1
                hook['optional'] = optional
    if not found_gate:
        raise SystemExit("no assure hooks found; reinstall the assure extension and retry")
    output = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    parsed = yaml.safe_load(output)
    assert all(h['optional'] is (not integrated) for h in parsed['hooks']['before_implement'] if h.get('extension') == 'assure')
    return output, changed


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
  state_directory: .specify/extensions/assure/state
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
    managed = (root / '.specify/workflow.yml').is_file()
    # Managed sequencing is already reconciled. Init must not invalidate that
    # journal or introduce a second, unconditional documentation CI gate.
    updated, changed = (original, 0) if managed else update_hooks(original, args.mode == "integrated")
    config = root / ".specify" / "extensions" / "assure" / "assure-config.yml"

    if not args.dry_run:
        extensions_yml.write_text(updated, encoding="utf-8")
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(config_text(args.mode), encoding="utf-8")
        workflow_source = Path(__file__).resolve().parents[1] / "assets" / "github" / "documentation-gates.yml"
        workflow_target = root / ".github" / "workflows" / "documentation-gates.yml"
        workflow_target.parent.mkdir(parents=True, exist_ok=True)
        if not managed and not workflow_target.exists():
            # Render the project's own runner selection rather than copying the
            # shipped template, which targets no particular runner.
            workflow_target.write_bytes(
                sanduq_ci.render(workflow_source.read_bytes(), sanduq_ci.load_ci(root)))

    print(f"assure mode={args.mode} hooks_changed={changed} dry_run={str(args.dry_run).lower()}")
    print(config)


if __name__ == "__main__":
    main()
