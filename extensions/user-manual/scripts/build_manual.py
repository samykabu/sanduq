#!/usr/bin/env python3
"""Build one audience/language User Manual HTML site and optional PDF/archive."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML is required; install User-Manual/requirements.lock")


def split_page(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("---\n", 2)
    return (yaml.safe_load(parts[1]) or {}, parts[2]) if len(parts) == 3 else ({}, text)


LINK = re.compile(r'(!?\[[^\]]*\]\()([^\s)]+)(\))|((?:src|href)=["\'])([^"\']+)(["\'])')


def copy_pages(source: Path, target: Path, audience: str, module: str | None) -> int:
    """Stage the pages this edition selects, and only the assets they reach.

    A manual keeps shared assets beside its language directories, so a page
    reaches them through a relative path that leaves its own language root.
    Copying the language directory alone leaves those links pointing outside
    the staged documentation, which the strict site build then rejects. Every
    reachable asset is therefore copied into the edition, shared paths rebased
    under `assets/`, and each link rewritten to where its target actually
    landed. Unreachable files stay out, so one audience never ships another's
    screenshots, and a missing asset or a link into a page this audience does
    not receive fails the build where it can still be fixed.
    """
    source = source.resolve()
    common = source.parent / "assets"
    selected = {
        page.resolve() for page in source.rglob("*.md")
        if audience in split_page(page)[0].get("audiences", [])
        and (not module or str(split_page(page)[0].get("module", "")) in {"system", module})
    }
    copied: set[Path] = set()

    def destination(path: Path) -> Path:
        if path.is_relative_to(source):
            return target / path.relative_to(source)
        if path.is_relative_to(common):
            return target / "assets" / path.relative_to(common)
        raise ValueError(f"Manual asset escapes documentation roots: {path}")

    def copy(path: Path) -> None:
        if path in copied:
            return
        copied.add(path)
        output = destination(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() not in {".md", ".html", ".svg"}:
            shutil.copy2(path, output)
            return

        def link(match: re.Match) -> str:
            before, value, after = (match.group(1), match.group(2), match.group(3)) if match.group(1) else (match.group(4), match.group(5), match.group(6))
            parts = urlsplit(value)
            if parts.scheme or parts.netloc or not parts.path:
                return match.group(0)
            linked = (path.parent / unquote(parts.path)).resolve()
            if not linked.is_file():
                raise ValueError(f"Missing manual asset: {path}: {value}")
            if linked.suffix == ".md" and linked not in selected:
                raise ValueError(f"Cross-audience page link: {path}: {value}")
            copy(linked)
            relative = Path(os.path.relpath(destination(linked), output.parent)).as_posix()
            if path.suffix != ".md" and linked.suffix == ".md":
                relative = str(Path(relative).with_suffix(".html")).replace("\\", "/")
            suffix = ("?" + parts.query if parts.query else "") + ("#" + parts.fragment if parts.fragment else "")
            return before + relative + suffix + after

        output.write_text(LINK.sub(link, path.read_text(encoding="utf-8")), encoding="utf-8")

    for page in sorted(selected):
        copy(page)
    return len(selected)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("User-Manual"))
    parser.add_argument("--audience", choices=("end-user", "administrator", "technical"), required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--version", default="preview")
    parser.add_argument("--module", help="Build only one module plus shared system pages")
    parser.add_argument("--renderer", choices=("material", "zensical"), default="material")
    parser.add_argument("--pdf", action="store_true")
    parser.add_argument("--archive", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    manual = yaml.safe_load((root / "manual.yml").read_text(encoding="utf-8")) or {}
    source = root / "docs" / args.language
    if not source.is_dir():
        raise SystemExit(f"language source not found: {source}")
    edition = f"{args.audience}-{args.language}" + (f"-{args.module}" if args.module else "")
    site_dir = root / "site" / args.version / args.language / args.audience
    if args.module:
        site_dir = site_dir / "modules" / args.module
    pdf_path = root / "pdf" / args.version / f"{edition}.pdf"
    product = manual.get("product_name", root.parent.name)

    if args.pdf and args.renderer == "zensical":
        raise SystemExit("PDF builds use the Material renderer; Zensical is an HTML compatibility check")
    if args.pdf:
        preflight = subprocess.run(
            [sys.executable, "-m", "weasyprint", "--info"],
            text=True,
            capture_output=True,
            check=False,
        )
        if preflight.returncode:
            detail = preflight.stderr.strip() or preflight.stdout.strip()
            raise SystemExit(
                "PDF renderer unavailable. Install the WeasyPrint native dependencies for this "
                f"operating system before retrying.\n{detail}"
            )

    with tempfile.TemporaryDirectory(prefix=".build-", dir=root) as raw_temp:
        temp = Path(raw_temp)
        staged_docs = temp / "docs"
        staged_site = temp / "site"
        staged_pdf = staged_site / f"{edition}.pdf"
        count = copy_pages(source, staged_docs, args.audience, args.module)
        if count == 0:
            raise SystemExit(f"no {args.audience}/{args.language} pages selected")
        styles = staged_docs / "assets" / "stylesheets"
        styles.mkdir(parents=True, exist_ok=True)
        for css in ("extra.css", "rtl.css", "print.css"):
            shutil.copy2(root / "theme" / css, styles / css)

        plugins: list[object] = ["search"]
        if args.pdf:
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            plugins.append({"to-pdf": {"output_path": staged_pdf.name, "cover": True, "toc_title": "Contents"}})
        config = {
            "site_name": f"{product} - {args.audience}",
            "docs_dir": "docs",
            "site_dir": "site",
            "use_directory_urls": False,
            "theme": {
                "name": "material",
                "language": args.language,
                "features": ["navigation.tabs", "navigation.sections", "navigation.indexes", "content.code.copy"],
                "palette": [
                    {"media": "(prefers-color-scheme: light)", "scheme": "default", "toggle": {"icon": "material/brightness-7", "name": "Dark mode"}},
                    {"media": "(prefers-color-scheme: dark)", "scheme": "slate", "toggle": {"icon": "material/brightness-4", "name": "Light mode"}},
                ],
            },
            "plugins": plugins,
            "markdown_extensions": ["admonition", "attr_list", "tables", "toc", "pymdownx.details", "pymdownx.superfences", "pymdownx.tabbed"],
            "extra_css": ["assets/stylesheets/extra.css", "assets/stylesheets/rtl.css", "assets/stylesheets/print.css"],
            "extra": {"audience": args.audience, "language": args.language, "version": args.version},
        }
        config_path = temp / "mkdocs.yml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
        site_dir.parent.mkdir(parents=True, exist_ok=True)
        command = (
            ["zensical", "build", "--strict", "--config-file", str(config_path)]
            if args.renderer == "zensical"
            else [sys.executable, "-m", "mkdocs", "build", "--strict", "--config-file", str(config_path)]
        )
        result = subprocess.run(command, cwd=temp, check=False)
        if result.returncode:
            raise SystemExit(result.returncode)
        site_dir.parent.mkdir(parents=True, exist_ok=True)
        if site_dir.exists():
            shutil.rmtree(site_dir)
        shutil.copytree(staged_site, site_dir)
        if args.pdf:
            if not staged_pdf.is_file():
                raise SystemExit(f"PDF renderer did not create {staged_pdf}")
            shutil.copy2(staged_pdf, pdf_path)

    if args.archive:
        archive = root / "site" / args.version / f"{edition}.zip"
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(site_dir.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(site_dir))
        print(archive)
    print(site_dir)
    if args.pdf:
        print(pdf_path)


if __name__ == "__main__":
    main()
