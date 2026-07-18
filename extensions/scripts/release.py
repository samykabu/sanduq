#!/usr/bin/env python3
"""Bump extension versions, refresh catalog.json, and emit a release manifest.

Driven by .github/workflows/release-extensions.yml. For each extension id passed
on the command line this script:

  * reads ``extensions/<id>/extension.yml``
  * decides the next version (see version resolution below)
  * rewrites the ``version:`` line in extension.yml (surrounding formatting and
    comments are preserved — only that one line changes)
  * updates the public ``catalog.json`` and mirrors it to
    ``extensions/catalog.json``:
      - existing entry  -> release URLs/version and manifest-derived requirements
        are refreshed (maintainer-curated catalog fields stay untouched)
      - new extension   -> a full entry is generated from extension.yml using
        the existing ``pr`` entry as the template
  * appends to a release manifest (JSON) the workflow reads back to cut releases

Version resolution (first match wins):
  1. ``--set-version X.Y.Z``                      explicit override
  2. extension.yml version already ahead of the   maintainer bumped it by hand
     catalog version                              -> release that version as-is
  3. missing from catalog                          new entry -> release current
  4. otherwise                                     auto ``--bump`` (default patch)

Usage:
  python extensions/scripts/release.py pr [foo ...] \
      --bump patch --repo-url https://github.com/samykabu/sanduq --branch main
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - guarded in CI by `pip install pyyaml`
    sys.exit("PyYAML is required: pip install pyyaml")

ROOT = Path(__file__).resolve().parents[2]
EXT_DIR = ROOT / "extensions"
CATALOG = ROOT / "catalog.json"
COMPAT_CATALOG = EXT_DIR / "catalog.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bump_version(version: str, level: str) -> str:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version.strip())
    if not m:
        sys.exit(f"cannot parse semantic version {version!r}")
    major, minor, patch = (int(x) for x in m.groups())
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def replace_yaml_version(text: str, new_version: str) -> str:
    """Replace the indented ``version: "..."`` line under the extension block.

    Anchored on leading whitespace so it never matches ``schema_version`` (column
    0) or ``speckit_version`` (a different key).
    """
    new_text, n = re.subn(
        r'(?m)^(\s+version:\s*)"[^"]*"',
        lambda m: f'{m.group(1)}"{new_version}"',
        text,
        count=1,
    )
    if n == 0:
        sys.exit("could not find an indented `version:` line in extension.yml")
    return new_text


def raw_catalog_url(repo_url: str, branch: str) -> str:
    prefix = "https://github.com/"
    if repo_url.startswith(prefix):
        return f"https://raw.githubusercontent.com/{repo_url[len(prefix):]}/{branch}/catalog.json"
    return ""


def new_catalog_entry(meta, ext_id, version, download_url, repo_url, branch):
    """Build a full catalog entry for a brand-new extension (pr entry = template)."""
    commands = (meta.get("provides", {}) or {}).get("commands", []) or []
    hooks = meta.get("hooks", {}) or {}
    return {
        "name": meta.get("name", ext_id),
        "id": ext_id,
        "version": version,
        "description": meta.get("description", ""),
        "author": meta.get("author", ""),
        "repository": meta.get("repository", repo_url),
        "homepage": f"{repo_url}/tree/{branch}/extensions/{ext_id}",
        "documentation": f"{repo_url}/blob/{branch}/extensions/{ext_id}/README.md",
        "changelog": f"{repo_url}/blob/{branch}/extensions/{ext_id}/CHANGELOG.md",
        "download_url": download_url,
        "license": meta.get("license", "PolyForm-Noncommercial-1.0.0"),
        "category": meta.get("category", "uncategorized"),
        "effect": meta.get("effect", "read-write"),
        "requires": meta.get("requires", {}) or {},
        "provides": {"commands": len(commands), "hooks": len(hooks)},
        "tags": meta.get("tags", []) or [],
        "verified": False,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def load_meta(yml_text: str) -> dict:
    """Flatten the parts of extension.yml the catalog cares about."""
    doc = yaml.safe_load(yml_text) or {}
    meta = dict(doc.get("extension", {}) or {})
    meta["requires"] = doc.get("requires", {}) or {}
    meta["provides"] = doc.get("provides", {}) or {}
    meta["hooks"] = doc.get("hooks", {}) or {}
    if "tags" in doc:
        meta["tags"] = doc.get("tags") or []
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ids", nargs="+", help="extension ids to release (dir names under extensions/)")
    ap.add_argument("--bump", default="patch", choices=["patch", "minor", "major"])
    ap.add_argument("--set-version", default=None, help="force this exact version")
    ap.add_argument("--repo-url", default="https://github.com/samykabu/sanduq")
    ap.add_argument("--branch", default="main", help="default branch used for catalog docs links")
    ap.add_argument("--manifest", default=str(ROOT / "dist" / "released.json"))
    args = ap.parse_args()

    repo_url = args.repo_url.rstrip("/")
    branch = args.branch.strip() or "main"
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    catalog["catalog_url"] = raw_catalog_url(repo_url, branch) or catalog.get("catalog_url", "")
    catalog.setdefault("extensions", {})

    released = []
    for ext_id in args.ids:
        yml_path = EXT_DIR / ext_id / "extension.yml"
        if not yml_path.is_file():
            print(f"skip {ext_id}: no extension.yml", file=sys.stderr)
            continue

        text = yml_path.read_text(encoding="utf-8")
        meta = load_meta(text)
        current = str(meta.get("version", "0.0.0"))
        existing = catalog["extensions"].get(ext_id)
        catalog_version = existing.get("version") if existing else None

        if args.set_version:
            new_version = args.set_version
        elif catalog_version and current != catalog_version:
            # Maintainer bumped extension.yml by hand -> honour it verbatim.
            new_version = current
        elif existing is None:
            # New catalog entry -> publish the version declared by the extension.
            new_version = current
        else:
            new_version = bump_version(current, args.bump)

        yml_path.write_text(replace_yaml_version(text, new_version), encoding="utf-8")

        tag = f"{ext_id}-v{new_version}"
        asset = f"{ext_id}.zip"
        download_url = f"{repo_url}/releases/download/{tag}/{asset}"

        if existing:
            entry = dict(existing)
            entry["version"] = new_version
            entry["repository"] = repo_url
            entry["homepage"] = f"{repo_url}/tree/{branch}/extensions/{ext_id}"
            entry["documentation"] = f"{repo_url}/blob/{branch}/extensions/{ext_id}/README.md"
            entry["changelog"] = f"{repo_url}/blob/{branch}/extensions/{ext_id}/CHANGELOG.md"
            entry["download_url"] = download_url
            entry["license"] = meta.get("license", "PolyForm-Noncommercial-1.0.0")
            entry["requires"] = meta.get("requires", {}) or {}
            entry["updated_at"] = now_iso()
            catalog["extensions"][ext_id] = entry
        else:
            catalog["extensions"][ext_id] = new_catalog_entry(
                meta, ext_id, new_version, download_url, repo_url, branch
            )

        released.append(
            {
                "id": ext_id,
                "version": new_version,
                "previous": current,
                "tag": tag,
                "asset": asset,
                "zip": f"dist/{asset}",
                "new_entry": existing is None,
            }
        )
        print(f"{ext_id}: {current} -> {new_version}  ({tag})")

    if not released:
        print("no extensions to release", file=sys.stderr)

    catalog["updated_at"] = now_iso()
    serialized_catalog = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
    CATALOG.write_text(serialized_catalog, encoding="utf-8")
    COMPAT_CATALOG.write_text(serialized_catalog, encoding="utf-8")

    manifest = Path(args.manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(released, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {manifest} ({len(released)} release(s))")


if __name__ == "__main__":
    main()
