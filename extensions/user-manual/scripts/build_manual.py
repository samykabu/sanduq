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


# Themes whose look the extension ships configuration and RTL styling for. Any
# other installed MkDocs theme is accepted with `renderer.theme_options` passed
# through untouched, and gets the generic RTL stylesheet.
BUILT_IN_THEMES = {"mkdocs", "readthedocs"}
DEFAULT_THEME = "material"


def installed_themes() -> set[str]:
    from importlib.metadata import entry_points
    return {entry.name for entry in entry_points(group="mkdocs.themes")}


def theme_locales(name: str) -> set[str] | None:
    """Locales a built-in MkDocs theme ships, or None when it does not say."""
    if name not in BUILT_IN_THEMES:
        return None
    import mkdocs.themes
    folder = Path(mkdocs.themes.__file__).parent / name / "locales"
    return {"en"} | ({entry.name for entry in folder.iterdir() if entry.is_dir()} if folder.is_dir() else set())


def theme_config(name: str, language: str, options: dict | None = None) -> dict:
    """The MkDocs `theme` block for one edition.

    Material keeps the extension's established features and light/dark palette.
    The built-in MkDocs themes take a `locale`, which is only set when the theme
    ships that language; otherwise the theme falls back to English chrome and the
    build adds RTL styling itself. `options` from manual.yml override defaults.
    """
    if name == "material":
        config = {
            "name": "material",
            "language": language,
            "features": ["navigation.tabs", "navigation.sections", "navigation.indexes", "content.code.copy"],
            "palette": [
                {"media": "(prefers-color-scheme: light)", "scheme": "default", "toggle": {"icon": "material/brightness-7", "name": "Dark mode"}},
                {"media": "(prefers-color-scheme: dark)", "scheme": "slate", "toggle": {"icon": "material/brightness-4", "name": "Light mode"}},
            ],
        }
    else:
        config = {"name": name}
        locales = theme_locales(name)
        if locales is not None and language in locales:
            config["locale"] = language
        if name == "readthedocs":
            config.update({"navigation_depth": 4, "collapse_navigation": False, "sticky_navigation": True})
    config.update(options or {})
    config["name"] = name
    return config


SCAFFOLD_THEME = Path(__file__).resolve().parents[1] / "assets" / "scaffold" / "theme"


def stylesheet_source(theme_dir: Path, name: str) -> Path | None:
    """A project override of a manual stylesheet, else the copy this extension ships."""
    for folder in (theme_dir, SCAFFOLD_THEME):
        if (folder / name).is_file():
            return folder / name
    return None


def rtl_stylesheet(theme_dir: Path, name: str) -> str | None:
    """The extra RTL stylesheet for a right-to-left edition.

    Material mirrors its own layout from the page language, so it needs none.
    Other themes get `rtl-<theme>.css` when one exists, else `rtl-generic.css`.
    """
    if name == "material":
        return None
    specific = f"rtl-{name}.css"
    return specific if stylesheet_source(theme_dir, specific) else "rtl-generic.css"


PAGE_ORDER = ("index.md", "user-guide.md", "admin-guide.md", "technical.md")
MODULES_TITLE = {"en": "Modules", "ar": "الوحدات"}
AUDIENCE_TITLE = {
    "ar": {"end-user": "دليل المستخدم", "administrator": "دليل الإدارة", "technical": "المرجع التقني"},
}


def build_nav(docs: Path, manual: dict, language: str) -> list:
    """Navigation in manual.yml module order, with each module named in the edition's language.

    Without an explicit nav MkDocs titles sections from folder names, so an Arabic
    edition shows English slugs. Pages keep their own front-matter titles; only the
    module sections are named here. Modules missing from manual.yml keep their slug.
    """
    def ordered(folder: Path) -> list[str]:
        pages = sorted(p for p in folder.glob("*.md"))
        rank = {name: i for i, name in enumerate(PAGE_ORDER)}
        return [p.relative_to(docs).as_posix() for p in sorted(pages, key=lambda p: (rank.get(p.name, len(rank)), p.name))]

    nav: list = ordered(docs)
    modules_root = docs / "modules"
    if modules_root.is_dir():
        names = {}
        for module in manual.get("modules") or []:
            translated = ((module.get("translations") or {}).get(language) or {}).get("name")
            names[str(module.get("id"))] = str(translated or module.get("name") or module.get("id"))
        known = [str(m.get("id")) for m in manual.get("modules") or []]
        folders = sorted((f for f in modules_root.iterdir() if f.is_dir()),
                         key=lambda f: (known.index(f.name) if f.name in known else len(known), f.name))
        sections = [{names.get(f.name, f.name.replace("-", " ").capitalize()): ordered(f)} for f in folders if ordered(f)]
        if sections:
            nav.append({MODULES_TITLE.get(language, MODULES_TITLE["en"]): sections})
    return nav


def resolve_theme(manual: dict, renderer: str) -> tuple[str, dict]:
    settings = manual.get("renderer") or {}
    name = str(settings.get("theme") or DEFAULT_THEME)
    options = settings.get("theme_options") or {}
    if not isinstance(options, dict):
        raise SystemExit("renderer.theme_options must be a mapping")
    if renderer == "zensical" and name != "material":
        raise SystemExit(f"Zensical is a Material compatibility check; theme {name!r} builds with --renderer material")
    available = installed_themes()
    if name not in available:
        raise SystemExit(f"MkDocs theme {name!r} is not installed (available: {', '.join(sorted(available))})")
    return name, options


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

    theme_name, theme_options = resolve_theme(manual, args.renderer)
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
        stylesheets = ["extra.css", "rtl.css", "print.css"]
        rtl_languages = {str(code) for code in (manual.get("languages") or {}).get("rtl", [])}
        if stylesheet_source(root / "theme", f"theme-{theme_name}.css"):
            stylesheets.append(f"theme-{theme_name}.css")
        extra_rtl = rtl_stylesheet(root / "theme", theme_name) if args.language in rtl_languages else None
        if extra_rtl:
            stylesheets.append(extra_rtl)
        for css in stylesheets:
            found = stylesheet_source(root / "theme", css)
            if found is None:
                raise SystemExit(f"missing manual stylesheet: {root / 'theme' / css}")
            shutil.copy2(found, styles / css)

        plugins: list[object] = ["search"]
        if args.pdf:
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            plugins.append({"to-pdf": {"output_path": staged_pdf.name, "cover": True, "toc_title": "Contents"}})
        config = {
            "site_name": f"{product} - {AUDIENCE_TITLE.get(args.language, {}).get(args.audience, args.audience)}",
            "nav": build_nav(staged_docs, manual, args.language),
            "docs_dir": "docs",
            "site_dir": "site",
            "use_directory_urls": False,
            "theme": theme_config(theme_name, args.language, theme_options),
            "plugins": plugins,
            "markdown_extensions": ["admonition", "attr_list", "tables", "toc", "pymdownx.details", "pymdownx.superfences", "pymdownx.tabbed"],
            "extra_css": [f"assets/stylesheets/{css}" for css in stylesheets],
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
