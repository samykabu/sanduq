#!/usr/bin/env python3
"""Join the changed inputs of `manual_state.py status` with the manual's evidence.

Prints the affected modules, pages, audiences and the changed paths no module
evidence or page `source_evidence` claims, and records the same list under
`impact` in `User-Manual/.state/coverage.json`. Gated by `lifecycle.impact_scope`
in `manual.yml`: `all` (default) lists every module and page, as the commands
read today; `evidence` starts from the changed paths.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML is required; install User-Manual/requirements.lock")

AUDIENCES = ("end-user", "administrator", "technical")


def front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    parts = text.split("---\n", 2)
    if not text.startswith("---\n") or len(parts) < 3:
        return {}
    data = yaml.safe_load(parts[1])
    return data if isinstance(data, dict) else {}


def listed(value: object) -> list[str]:
    """Evidence written as one string counts as a one-item list."""
    return [value] if isinstance(value, str) else [str(v) for v in value or []]


def covers(evidence: object, changed: str) -> bool:
    """A changed path matches an evidence entry by equality, directory prefix or glob."""
    pattern = str(evidence).replace("\\", "/").strip("/")
    return changed == pattern or changed.startswith(pattern + "/") or fnmatch.fnmatch(changed, pattern)


def impact(root: Path, status: dict) -> dict:
    manual = root / "User-Manual"
    config = yaml.safe_load((manual / "manual.yml").read_text(encoding="utf-8")) or {}
    scope = str((config.get("lifecycle") or {}).get("impact_scope", "all"))
    if scope not in ("all", "evidence"):
        raise SystemExit(f"lifecycle.impact_scope must be all or evidence, not {scope!r}")
    modules = {str(m.get("id")): listed(m.get("evidence")) for m in config.get("modules") or []}
    pages = {p.relative_to(root).as_posix(): front_matter(p) for p in sorted((manual / "docs").rglob("*.md"))}
    changed = status.get("changed_inputs") or []
    if scope == "all" or not changed:
        hit_modules, hit_pages, unmatched = set(modules), set(pages), []
    else:
        hit_modules = {m for m, evidence in modules.items() if any(covers(e, c) for e in evidence for c in changed)}
        hit_pages = {page for page, meta in pages.items()
                     if any(covers(e, c) for e in listed(meta.get("source_evidence")) for c in changed)}
        hit_modules |= {str(pages[page].get("module")) for page in hit_pages if pages[page].get("module")}
        hit_pages |= {page for page, meta in pages.items() if str(meta.get("module")) in hit_modules}
        claimed = [e for evidence in modules.values() for e in evidence] + \
                  [e for meta in pages.values() for e in listed(meta.get("source_evidence"))]
        unmatched = [c for c in changed if not any(covers(e, c) for e in claimed)]
    audiences = {str(a) for page in hit_pages for a in pages[page].get("audiences") or []}
    return {"impact_scope": scope, "reason": status.get("reason"), "changed_inputs": changed,
            "modules": sorted(hit_modules), "pages": sorted(hit_pages),
            "audiences": [a for a in AUDIENCES if a in audiences] + sorted(audiences - set(AUDIENCES)),
            "unmatched": unmatched}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    command = [sys.executable, str(Path(__file__).with_name("manual_state.py")), "status", "--feature",
               str(args.feature), "--repo-root", str(root), "--json"]
    if args.base_ref:
        command += ["--base-ref", args.base_ref]
    # stderr passes through; a stale status exits 1 and still prints the JSON.
    status = json.loads(subprocess.run(command, stdout=subprocess.PIPE, text=True, encoding="utf-8").stdout)
    result = impact(root, status)
    coverage = root / "User-Manual/.state/coverage.json"
    coverage.parent.mkdir(parents=True, exist_ok=True)
    recorded = json.loads(coverage.read_text(encoding="utf-8")) if coverage.is_file() else {}
    recorded = recorded if isinstance(recorded, dict) else {}
    recorded["impact"] = result
    coverage.write_text(json.dumps(recorded, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
