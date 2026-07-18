#!/usr/bin/env python3
"""Validate User-Manual structure, metadata, links, assets, audiences, languages, and secrets."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML is required; install User-Manual/requirements.lock")

AUDIENCES = {"end-user", "administrator", "technical"}
CONTENT_TYPES = {"tutorial", "how-to", "reference", "explanation", "release-notes", "migration-guide"}
REQUIRED_META = {"title", "module", "audiences", "language", "content_type", "source_evidence", "last_verified", "status"}
SECRET = re.compile(r"(?i)(api[_-]?key|client[_-]?secret|password|access[_-]?token|refresh[_-]?token)\s*[:=]\s*[\"']?([^\s\"']{8,})")
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def front_matter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}, text
    return yaml.safe_load(parts[1]) or {}, parts[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("User-Manual"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    config_path = root / "manual.yml"
    if not config_path.is_file():
        raise SystemExit(f"missing {config_path}")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    provider = config.get("publishing", {}).get("ephemeral_provider")
    if provider:
        provider_id = str(provider)
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", provider_id):
            errors.append(f"invalid ephemeral provider id: {provider_id!r}")
        descriptor_path = root / "providers" / provider_id / "preview.yml"
        if not descriptor_path.is_file():
            errors.append(f"approved provider descriptor missing: {descriptor_path.relative_to(root)}")
        else:
            descriptor_text = descriptor_path.read_text(encoding="utf-8")
            descriptor = yaml.safe_load(descriptor_text) or {}
            if descriptor.get("id") != provider_id:
                errors.append(f"{descriptor_path.relative_to(root)}: provider id does not match manual.yml")
            approval = descriptor.get("approval")
            if not isinstance(approval, dict) or approval.get("status") != "approved":
                errors.append(f"{descriptor_path.relative_to(root)}: provider is not approved")
            workflow_config = descriptor.get("workflow")
            workflow = workflow_config.get("file") if isinstance(workflow_config, dict) else None
            if not workflow or not (root.parent / str(workflow)).is_file():
                errors.append(f"{descriptor_path.relative_to(root)}: checked-in workflow file is missing")
            for match in SECRET.finditer(descriptor_text):
                value = match.group(2).lower()
                if not any(marker in value for marker in ("redacted", "example", "placeholder", "<", "${")):
                    errors.append(f"{descriptor_path.relative_to(root)}: possible provider secret value")
    approved = {item.get("id") for item in config.get("modules", []) if item.get("status") == "approved"}
    required_languages = set(config.get("languages", {}).get("required", ["en"]))
    optional_languages = set(config.get("languages", {}).get("optional", []))
    seen: dict[str, set[str]] = {language: set() for language in required_languages | optional_languages}

    pages = sorted((root / "docs").rglob("*.md")) if (root / "docs").is_dir() else []
    if not pages:
        errors.append("no Markdown pages under User-Manual/docs")
    for path in pages:
        meta, body = front_matter(path)
        relative = path.relative_to(root).as_posix()
        missing = REQUIRED_META - set(meta)
        if missing:
            errors.append(f"{relative}: missing front matter {sorted(missing)}")
        audiences = set(meta.get("audiences", []))
        if not audiences or not audiences <= AUDIENCES:
            errors.append(f"{relative}: invalid audiences {sorted(audiences)}")
        language = str(meta.get("language", ""))
        if language and language not in required_languages | optional_languages:
            errors.append(f"{relative}: language {language!r} is not configured")
        content_type = meta.get("content_type")
        if content_type and content_type not in CONTENT_TYPES:
            errors.append(f"{relative}: unsupported content_type {content_type!r}")
        module = str(meta.get("module", ""))
        if language in seen and module:
            seen[language].add(module)
        for match in SECRET.finditer(body):
            value = match.group(2).lower()
            if not any(marker in value for marker in ("redacted", "example", "placeholder", "<", "${")):
                errors.append(f"{relative}: possible secret assigned to {match.group(1)}")
        for target in LINK.findall(body):
            clean = target.split("#", 1)[0].split("?", 1)[0]
            if not clean or re.match(r"^[a-z]+://", clean) or clean.startswith(("mailto:", "#")):
                continue
            if not (path.parent / clean).resolve().exists():
                errors.append(f"{relative}: missing linked file {target}")

    for language in required_languages:
        missing_modules = approved - seen.get(language, set())
        if missing_modules:
            errors.append(f"{language}: approved modules without pages: {sorted(missing_modules)}")
    for language in optional_languages:
        missing_modules = approved - seen.get(language, set())
        if missing_modules:
            warnings.append(f"{language}: translation missing for modules: {sorted(missing_modules)}")

    result = {"ok": not errors, "pages": len(pages), "errors": errors, "warnings": warnings}
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else "\n".join(errors + warnings) or f"manual audit ok ({len(pages)} pages)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
