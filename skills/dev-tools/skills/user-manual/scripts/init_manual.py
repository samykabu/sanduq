#!/usr/bin/env python3
"""Scaffold an approved modular User-Manual without overwriting authored pages."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import date
from pathlib import Path


def q(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def valid_module(item: object, require_arabic: bool) -> dict[str, object]:
    if not isinstance(item, dict):
        raise SystemExit("each module must be a JSON object")
    module_id = str(item.get("id", ""))
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", module_id):
        raise SystemExit(f"invalid module id: {module_id!r}")
    name = str(item.get("name", "")).strip()
    description = str(item.get("description", "")).strip()
    evidence = item.get("evidence", [])
    if not name or not description or not isinstance(evidence, list) or not evidence:
        raise SystemExit(f"module {module_id!r} requires name, description, and evidence")
    name_ar = str(item.get("name_ar", "")).strip()
    description_ar = str(item.get("description_ar", "")).strip()
    if require_arabic and (not name_ar or not description_ar):
        raise SystemExit(f"module {module_id!r} requires name_ar and description_ar when Arabic is enabled")
    return {
        "id": module_id,
        "name": name,
        "description": description,
        "name_ar": name_ar,
        "description_ar": description_ar,
        "evidence": evidence,
    }


def manual_yaml(product: str, modules: list[dict[str, object]], arabic: bool, provider: str | None) -> str:
    optional = "[ar]" if arabic else "[]"
    lines = [
        'schema_version: "1.0"',
        f"product_name: {q(product)}",
        "languages:",
        "  required: [en]",
        f"  optional: {optional}",
        "  rtl: [ar]",
        "audiences:",
        "  end-user:",
        "    visibility: approved-public",
        "  administrator:",
        "    visibility: authenticated-internal",
        "  technical:",
        "    visibility: private",
        "publishing:",
        "  preview: private-ci-artifact",
        "  preview_security:",
        "    private_repository: repository-read-permission",
        "    public_repository: age-encrypted",
        "    age_recipient_variable: USER_MANUAL_PREVIEW_AGE_RECIPIENT",
        f"  ephemeral_provider: {q(provider) if provider else 'null'}",
        "  commit_build_outputs: false",
        "renderer:",
        "  primary: mkdocs-material",
        '  material_version: "9.7.6"',
        '  mkdocs_constraint: ">=1.6,<2"',
        "  compatibility: zensical",
        "modules:",
    ]
    for module in modules:
        lines.extend([
            f"  - id: {q(str(module['id']))}",
            f"    name: {q(str(module['name']))}",
            f"    description: {q(str(module['description']))}",
            "    status: approved",
            *(
                [
                    "    translations:",
                    "      ar:",
                    f"        name: {q(str(module['name_ar']))}",
                    f"        description: {q(str(module['description_ar']))}",
                ]
                if module.get("name_ar")
                else []
            ),
            "    evidence:",
            *[f"      - {q(str(path))}" for path in module["evidence"]],
        ])
    return "\n".join(lines) + "\n"


def page(title: str, module_id: str, language: str, body: str) -> str:
    return f'''---
title: {q(title)}
module: {module_id}
audiences: [end-user, administrator, technical]
language: {language}
content_type: explanation
source_evidence: [User-Manual/manual.yml]
last_verified: {date.today().isoformat()}
status: draft
---

# {title}

{body}
'''


def copy_if_missing(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(source, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--modules-file", type=Path, required=True)
    parser.add_argument("--product-name")
    parser.add_argument("--enable-arabic", action="store_true")
    parser.add_argument("--provider")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = args.repo_root.resolve()
    data = json.loads(args.modules_file.read_text(encoding="utf-8"))
    raw_modules = data.get("modules", data) if isinstance(data, dict) else data
    if not isinstance(raw_modules, list) or not raw_modules:
        raise SystemExit("modules file must contain a non-empty array")
    modules = [valid_module(item, args.enable_arabic) for item in raw_modules]
    product = args.product_name or root.name
    manual_root = root / "User-Manual"
    skill_root = Path(__file__).resolve().parents[1]

    if args.dry_run:
        print(json.dumps({"root": str(manual_root), "product": product, "modules": modules}, indent=2))
        return

    manual_root.mkdir(parents=True, exist_ok=True)
    config = manual_root / "manual.yml"
    if config.exists():
        raise SystemExit("User-Manual/manual.yml already exists; approve and merge module changes manually")
    config.write_text(manual_yaml(product, modules, args.enable_arabic, args.provider), encoding="utf-8")

    for language in (["en", "ar"] if args.enable_arabic else ["en"]):
        lang_root = manual_root / "docs" / language
        lang_root.mkdir(parents=True, exist_ok=True)
        title = product if language == "en" else product
        body = (
            "Use this manual to understand the application and complete common tasks."
            if language == "en"
            else "استخدم هذا الدليل لفهم التطبيق وتنفيذ المهام الشائعة."
        )
        (lang_root / "index.md").write_text(page(title, "system", language, body), encoding="utf-8")
        for module in modules:
            module_dir = lang_root / "modules" / str(module["id"])
            module_dir.mkdir(parents=True, exist_ok=True)
            module_page = module_dir / "index.md"
            if not module_page.exists():
                module_name = str(module["name_ar"] if language == "ar" else module["name"])
                description = str(module["description_ar"] if language == "ar" else module["description"])
                module_page.write_text(page(module_name, str(module["id"]), language, description), encoding="utf-8")

    for name in ("mkdocs.yml", "requirements.lock"):
        copy_if_missing(skill_root / "assets" / "scaffold" / name, manual_root / name)
    for name in ("extra.css", "rtl.css", "print.css"):
        copy_if_missing(skill_root / "assets" / "scaffold" / "theme" / name, manual_root / "theme" / name)
        for language in (["en", "ar"] if args.enable_arabic else ["en"]):
            copy_if_missing(
                skill_root / "assets" / "scaffold" / "theme" / name,
                manual_root / "docs" / language / "assets" / "stylesheets" / name,
            )
    for name in ("audit_manual.py", "build_manual.py", "manual_state.py"):
        copy_if_missing(skill_root / "scripts" / name, manual_root / "tools" / name)
    copy_if_missing(skill_root / "assets" / "github" / "user-manual-preview.yml", root / ".github" / "workflows" / "user-manual-preview.yml")
    copy_if_missing(skill_root / "assets" / "github" / "user-manual-release.yml", root / ".github" / "workflows" / "user-manual-release.yml")
    (manual_root / ".state").mkdir(exist_ok=True)
    print(f"initialized {manual_root} with {len(modules)} approved module(s)")


if __name__ == "__main__":
    main()
