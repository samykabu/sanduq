#!/usr/bin/env python3
"""Configure QA lifecycle hooks using parsed YAML and verified postconditions."""

from __future__ import annotations

import argparse
import re
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


TEMPLATE = Path(__file__).resolve().parents[1] / "assure-config.template.yml"
GATE = Path(__file__).resolve().parents[1] / "assets" / "github" / "documentation-gates.yml"
PREVIOUS_GATE = GATE.parent / "previous" / "documentation-gates.yml"
# AU8 added these lines; a file equal to the render without them is an unedited earlier gate.
HEAD_CHECKOUT = (b"          # The recorded states describe the PR head, not GitHub's merge commit.\n"
                 b"          ref: ${{ github.event.pull_request.head.sha }}\n")
LIFECYCLE = re.compile(r"(?m)^lifecycle:[ \t]*(?:#.*)?\n((?:[ \t]+\S.*(?:\n|\Z)|[ \t]*\n)*)")


def config_text(mode: str, text: str | None = None, source: Path = TEMPLATE) -> str:
    """`text` (default: the packaged template, which holds the default scan.exclude list) with only
    the three lifecycle values set for `mode`; every other line is kept as written."""
    enabled = str(mode == "integrated").lower()
    text = TEMPLATE.read_text(encoding="utf-8") if text is None else text
    block = LIFECYCLE.search(text)
    if block:
        body = block.group(1)
        for key, value in (("mode", mode), ("require_analyze_before_implement", enabled),
                           ("require_document_before_pr", enabled)):
            body = re.sub(rf"(?m)^([ \t]+{key}:[ \t]*)[^\s#]+", lambda m: m.group(1) + value, body, count=1)
        text = text[:block.start(1)] + body + text[block.end(1):]
    try:
        lifecycle = (yaml.safe_load(text) or {}).get("lifecycle")
    except (yaml.YAMLError, AttributeError):
        lifecycle = None
    expected = {"mode": mode, "require_analyze_before_implement": enabled == "true",
                "require_document_before_pr": enabled == "true"}
    if not isinstance(lifecycle, dict) or {key: lifecycle.get(key) for key in expected} != expected:
        hint = ("reinstall the assure extension" if source == TEMPLATE else
                "set lifecycle.mode, require_analyze_before_implement and require_document_before_pr by hand")
        raise SystemExit(f"{source} has no lifecycle block with the three keys init sets; {hint}")
    return text


def update_gate(root: Path, managed: bool, dry_run: bool) -> str:
    """Write the documentation gate when absent and replace an unedited earlier render; keep local edits."""
    if managed:
        return "managed"
    target = root / ".github" / "workflows" / "documentation-gates.yml"
    # Render the project's own runner selection rather than copying the
    # shipped template, which targets no particular runner.
    ci = sanduq_ci.load_ci(root)
    template = GATE.read_bytes().replace(b"\r\n", b"\n")
    rendered = sanduq_ci.render(template, ci)
    status = "written"
    if target.exists():
        current = target.read_bytes().replace(b"\r\n", b"\n")
        if current == rendered:
            return "current"
        # An unedited render of the template before the base-branch gate (SEC-03) is replaced too.
        previous = PREVIOUS_GATE.read_bytes().replace(b"\r\n", b"\n")
        if current not in [sanduq_ci.render(t, ci) for t in (previous, previous.replace(HEAD_CHECKOUT, b""))]:
            if b"github.event.pull_request.head.sha" not in current:
                print(f"{target.relative_to(root).as_posix()} has local edits: add "
                      "`ref: ${{ github.event.pull_request.head.sha }}` under its checkout `with:`")
            return "kept"
        status = "updated"
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(rendered)
    return status


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
    # An existing config keeps the consumer's settings; init changes only the lifecycle values.
    existing = config.read_text(encoding="utf-8-sig") if config.is_file() else None
    text = config_text(args.mode) if existing is None else config_text(args.mode, existing, config)

    if not args.dry_run:
        if changed:
            extensions_yml.write_text(updated, encoding="utf-8")
        if text != existing:
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(text, encoding="utf-8")
    gate = update_gate(root, managed, args.dry_run)

    print(f"assure mode={args.mode} hooks_changed={changed} ci_gate={gate} dry_run={str(args.dry_run).lower()}")
    print(config)


if __name__ == "__main__":
    main()
