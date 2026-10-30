#!/usr/bin/env python3
"""Assemble User Manual editions from canonical Markdown, then render each one.

An edition is one audience and language (and optionally one module). Assembly selects its pages,
rewrites their links, copies only the assets they reach and writes `edition.json`. The renderer in
`manual.yml` (`renderer.kind`) then turns the edition into output:

- `markdown` (default): the assembled Markdown itself, readable on GitHub or a wiki.
- `command`: the project's own tool (Pandoc, Quarto, a script) run on the edition.
- `mkdocs`: an MkDocs HTML site, and with `--pdf` a PDF through mkdocs-to-pdf.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
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


RENDERERS = ("markdown", "command", "mkdocs")
DEFAULT_RENDERER = "markdown"
AUDIENCES = ("end-user", "administrator", "technical")
BUILD_LOG_TAIL = 40


def split_page(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("---\n", 2)
    return (yaml.safe_load(parts[1]) or {}, parts[2]) if len(parts) == 3 else ({}, text)


# Inline links and images (with an optional "title" and <angle-bracketed> targets), reference
# definitions ("[id]: target"), and src/href attributes in HTML.
LINK = re.compile(
    r'(?P<ib>!?\[[^\]]*\]\()(?P<iv><[^>\n]+>|[^\s)]+)(?P<ia>(?:\s+"[^"\n]*")?\))'
    r'|(?P<rb>^[ ]{0,3}\[(?!\^)[^\]\n]+\]:[ \t]*)(?P<rv><[^>\n]+>|\S+)(?P<ra>(?:[ \t]+"[^"\n]*")?[ \t]*$)'
    r'|(?P<hb>(?:src|href)=["\'])(?P<hv>[^"\']+)(?P<ha>["\'])',
    re.M,
)


def copy_pages(source: Path, target: Path, audience: str, module: str | None, page_suffix: str = ".md",
               titles: dict[str, str] | None = None) -> int:
    """Stage the pages this edition selects, and only the assets they reach.

    A manual keeps shared assets beside its language directories, so a page reaches them through a
    relative path that leaves its own language root. Every reachable asset is copied into the edition,
    shared paths rebased under `assets/`, and each link rewritten to where its target landed.
    Unreachable files stay out, so one audience never ships another's screenshots, and a missing asset
    or a link into a page this audience does not receive fails the build where it can still be fixed.
    `page_suffix` is what an HTML or SVG asset's link to a page points at: `.html` for a site renderer.
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
            kind = "i" if match.group("ib") is not None else "r" if match.group("rb") is not None else "h"
            before, value, after = match.group(kind + "b"), match.group(kind + "v"), match.group(kind + "a")
            bracketed = value.startswith("<") and value.endswith(">")
            parts = urlsplit(value[1:-1] if bracketed else value)
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
                relative = relative[:-3] + page_suffix
            relative += ("?" + parts.query if parts.query else "") + ("#" + parts.fragment if parts.fragment else "")
            if kind != "h" and (bracketed or " " in relative):
                relative = "<" + relative + ">"
            return before + relative + after

        text = path.read_text(encoding="utf-8")
        if path.suffix == ".md" and text.startswith("---\n") and text.count("---\n") >= 2:
            # Front matter is source metadata: GitHub would show it as a table and Pandoc would let each page's
            # title replace the edition's. The manifest keeps each page's title for the renderers.
            title = (split_page(path)[0] or {}).get("title")
            if titles is not None and title:
                titles[output.relative_to(target).as_posix()] = str(title)
            text = text.split("---\n", 2)[2].lstrip("\n")
        output.write_text(LINK.sub(link, text), encoding="utf-8")

    for page in sorted(selected):
        copy(page)
    return len(selected)


PAGE_ORDER = ("index.md", "user-guide.md", "admin-guide.md", "technical.md")
MODULES_TITLE = {"en": "Modules", "ar": "الوحدات"}
TOC_TITLE = {"en": "Contents", "ar": "المحتويات"}
AUDIENCE_TITLE = {
    "en": {"end-user": "User Guide", "administrator": "Administrator Guide", "technical": "Technical Reference"},
    "ar": {"end-user": "دليل المستخدم", "administrator": "دليل الإدارة", "technical": "المرجع التقني"},
}


def build_nav(docs: Path, manual: dict, language: str) -> list:
    """Navigation in manual.yml module order, with each module named in the edition's language.

    Pages keep their own front-matter titles; only the module sections are named here. Modules missing
    from manual.yml keep their slug.
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


def nav_pages(nav: list) -> list[str]:
    """The pages of a navigation tree in reading order."""
    pages: list[str] = []
    for item in nav:
        if isinstance(item, str):
            pages.append(item)
        else:
            for children in item.values():
                pages += nav_pages(children)
    return pages


def titled_nav(nav: list, titles: dict[str, str]) -> list:
    """The navigation with each page that has a front-matter title labelled by it (`{title: page}`)."""
    return [({titles[item]: item} if item in titles else item) if isinstance(item, str)
            else {name: titled_nav(children, titles) for name, children in item.items()} for item in nav]


def reading_order(docs: Path, nav: list) -> list[str]:
    """Every page of the edition in reading order: the navigation's pages, with each page nested deeper than
    the navigation reaches (such as modules/<id>/tasks/refund.md) placed after the last page of its closest
    listed folder, so a renderer command receives them all."""
    order = nav_pages(nav)
    listed = set(order)
    for page in sorted(p.relative_to(docs).as_posix() for p in docs.rglob("*.md")):
        if page in listed:
            continue
        parts, at = page.split("/"), len(order)
        for depth in range(len(parts) - 1, 0, -1):
            prefix = "/".join(parts[:depth]) + "/"
            hits = [i for i, listed_page in enumerate(order) if listed_page.startswith(prefix)]
            if hits:
                at = hits[-1] + 1
                break
        order.insert(at, page)
    return order


BRAND_TEXT = ("title", "subtitle", "author", "copyright")


def load_brand(root: Path, manual: dict) -> dict:
    """`theme/brand.yml`: the values every renderer shows (title, subtitle, author, copyright, logo,
    colors). Paths are relative to the manual root. The title defaults to manual.yml's product name."""
    path = root / "theme" / "brand.yml"
    brand = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if not isinstance(brand or {}, dict):
        raise SystemExit(f"{path}: brand settings must be a mapping")
    brand = {key: value for key, value in (brand or {}).items() if value not in (None, "", {})}
    for key in BRAND_TEXT:
        if key in brand:
            brand[key] = str(brand[key])
    brand.setdefault("title", str(manual.get("product_name") or root.parent.name))
    if "logo" in brand and not (root / str(brand["logo"])).is_file():
        raise SystemExit(f"brand logo not found: {root / str(brand['logo'])}")
    if not isinstance(brand.get("colors", {}), dict):
        raise SystemExit(f"{path}: colors must be a mapping such as {{primary: '#1f6f78'}}")
    return brand


def renderer_settings(manual: dict, override: str | None = None) -> dict:
    settings = dict(manual.get("renderer") or {})
    kind = str(override or settings.get("kind") or DEFAULT_RENDERER)
    if kind not in RENDERERS:
        raise SystemExit(f"renderer.kind must be one of {', '.join(RENDERERS)}, not {kind!r}")
    settings["kind"] = kind
    return settings


def edition_paths(root: Path, args: argparse.Namespace) -> tuple[str, Path, Path]:
    edition = f"{args.audience}-{args.language}" + (f"-{args.module}" if args.module else "")
    site_dir = root / "site" / args.version / args.language / args.audience
    if args.module:
        site_dir = site_dir / "modules" / args.module
    return edition, site_dir, root / "pdf" / args.version / f"{edition}.pdf"


def assemble(root: Path, manual: dict, args: argparse.Namespace, target: Path, page_suffix: str = ".md") -> dict:
    """Write one edition's pages and assets to `target`; return its manifest (also `edition.json`)."""
    source = root / "docs" / args.language
    if not source.is_dir():
        raise SystemExit(f"language source not found: {source}")
    titles: dict[str, str] = {}
    if copy_pages(source, target, args.audience, args.module, page_suffix, titles) == 0:
        raise SystemExit(f"no {args.audience}/{args.language} pages selected")
    brand = load_brand(root, manual)
    rtl = {str(code) for code in (manual.get("languages") or {}).get("rtl", [])}
    nav = build_nav(target, manual, args.language)
    audience_title = AUDIENCE_TITLE.get(args.language, AUDIENCE_TITLE["en"]).get(args.audience, args.audience)
    manifest = {
        "schema_version": 1,
        "title": f"{brand['title']} - {audience_title}",
        "audience": args.audience,
        "language": args.language,
        "direction": "rtl" if args.language in rtl else "ltr",
        "module": args.module,
        "version": args.version,
        "toc_title": TOC_TITLE.get(args.language, TOC_TITLE["en"]),
        "pages": reading_order(target, nav),
        "titles": dict(sorted(titles.items())),
        "nav": nav,
        "brand": brand,
    }
    (target / "edition.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Pandoc-style metadata, so `--metadata-file {metadata}` sets title, author, language and direction.
    metadata = {"title": brand["title"], "subtitle": brand.get("subtitle") or audience_title,
                **{key: brand[key] for key in ("author", "copyright") if key in brand},
                "lang": args.language, "dir": manifest["direction"], "toc-title": manifest["toc_title"]}
    (target / "metadata.yml").write_text(yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return manifest


def run_renderer(command: list[str], cwd: Path, edition: str, kind: str) -> None:
    # The renderer's banners and INFO lines would flood the caller's transcript; show them only on failure.
    try:
        result = subprocess.run(command, cwd=cwd, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise SystemExit(f"{edition}: {kind} renderer command not found: {command[0]}")
    if result.returncode:
        tail = "\n".join((result.stdout or "").strip().splitlines()[-BUILD_LOG_TAIL:])
        print(f"{edition}: {kind} build failed\n{tail}", file=sys.stderr)
        raise SystemExit(result.returncode)


PLACEHOLDER = re.compile(r"\{(edition|manifest|metadata|output|language|direction|audience|version|module|title)\}")


def command_argv(command: object, values: dict[str, str], pages: list[str]) -> list[str]:
    """The renderer command with placeholders filled. A string is split like a POSIX shell (no globbing,
    pipes or variables); a list is used as given. `{pages}`, as a whole argument, becomes every page path
    in reading order."""
    if isinstance(command, str) and command.strip():
        # shortcut: POSIX splitting reads a backslash as an escape; Windows paths need the list form.
        tokens = shlex.split(command)
    elif isinstance(command, list) and command and all(isinstance(item, (str, int, float)) for item in command):
        tokens = [str(item) for item in command]
    else:
        raise SystemExit("renderer.command must be a non-empty string or list for renderer.kind: command")
    argv: list[str] = []
    for token in tokens:
        if token == "{pages}":
            argv += pages
        else:
            argv.append(PLACEHOLDER.sub(lambda match: values[match.group(1)], token))
    return argv


def render_command(root: Path, manual: dict, settings: dict, args: argparse.Namespace, edition: str, site_dir: Path) -> None:
    with tempfile.TemporaryDirectory(prefix=".build-", dir=root) as raw_temp:
        staged = Path(raw_temp) / "edition"
        manifest = assemble(root, manual, args, staged)
        if site_dir.exists():
            shutil.rmtree(site_dir)
        site_dir.mkdir(parents=True)
        values = {"edition": str(staged), "manifest": str(staged / "edition.json"),
                  "metadata": str(staged / "metadata.yml"), "output": str(site_dir),
                  "title": manifest["title"], "module": args.module or "",
                  **{key: str(manifest[key]) for key in ("language", "direction", "audience", "version")}}
        argv = command_argv(settings.get("command"), values, [str(staged / page) for page in manifest["pages"]])
        # The command runs from the manual root, so its own template paths are project-relative.
        run_renderer(argv, root, edition, "command")
        if not any(site_dir.iterdir()):
            raise SystemExit(f"{edition}: the renderer command wrote nothing to {site_dir}")


# ---- MkDocs renderer -------------------------------------------------------------------------------------

# Themes whose look this skill ships configuration and RTL styling for. Any other installed MkDocs theme
# is accepted with `renderer.theme_options` passed through untouched, and gets the generic RTL stylesheet.
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

    Material keeps its navigation features and light/dark palette. The built-in MkDocs themes take a
    `locale`, set only when the theme ships that language. `options` from manual.yml override defaults.
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


SCRIPT_DIR = Path(__file__).resolve().parent
# The skill ships its stylesheets in assets/scaffold/theme; the copy init_manual.py puts in User-Manual/tools/
# has them beside it in tools/theme/.
SCAFFOLD_THEME = next((folder for folder in (SCRIPT_DIR.parent / "assets" / "scaffold" / "theme", SCRIPT_DIR / "theme")
                       if folder.is_dir()), SCRIPT_DIR.parent / "assets" / "scaffold" / "theme")


def stylesheet_source(theme_dir: Path, name: str) -> Path | None:
    """A project override of a manual stylesheet, else the copy this skill ships."""
    for folder in (theme_dir, SCAFFOLD_THEME):
        if (folder / name).is_file():
            return folder / name
    return None


def rtl_stylesheet(theme_dir: Path, name: str) -> str | None:
    """The extra RTL stylesheet for a right-to-left edition: none for Material (it mirrors itself from the
    page language), `rtl-<theme>.css` when one exists, else `rtl-generic.css`."""
    if name == "material":
        return None
    specific = f"rtl-{name}.css"
    return specific if stylesheet_source(theme_dir, specific) else "rtl-generic.css"


def resolve_theme(settings: dict, root: Path) -> tuple[str, dict]:
    name = str(settings.get("theme") or DEFAULT_THEME)
    if not isinstance(settings.get("theme_options") or {}, dict):
        raise SystemExit("renderer.theme_options must be a mapping")
    options = dict(settings.get("theme_options") or {})
    custom = settings.get("custom_dir") or options.get("custom_dir")
    if custom:
        # The build runs in a temporary folder: a project-relative override folder is resolved here.
        folder = Path(str(custom)) if Path(str(custom)).is_absolute() else root / str(custom)
        if not folder.is_dir():
            raise SystemExit(f"renderer custom_dir not found: {folder}")
        options["custom_dir"] = str(folder)
    available = installed_themes()
    if name not in available:
        raise SystemExit(f"MkDocs theme {name!r} is not installed (available: {', '.join(sorted(available)) or 'none'}); "
                         "install User-Manual/requirements-mkdocs.lock")
    return name, options


# GitHub alerts ("> [!NOTE]") become admonitions, titled in the edition's language.
ALERT = re.compile(r"^> ?\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*\n((?:>.*(?:\n|$))*)", re.M)
ADMONITION = {"NOTE": "note", "TIP": "tip", "IMPORTANT": "info", "WARNING": "warning", "CAUTION": "danger"}
ALERT_TITLE = {
    "en": {"NOTE": "Note", "TIP": "Tip", "IMPORTANT": "Important", "WARNING": "Warning", "CAUTION": "Caution"},
    "ar": {"NOTE": "ملاحظة", "TIP": "تلميح", "IMPORTANT": "مهم", "WARNING": "تحذير", "CAUTION": "تنبيه"},
}


def mkdocs_markdown(text: str, language: str) -> str:
    """GitHub-flavoured constructs in the form MkDocs renders: alerts as admonitions, and `<details>`
    blocks marked so the Markdown inside them is rendered (md_in_html).
    shortcut: an alert or <details> written inside a fenced code block is converted too."""
    titles = ALERT_TITLE.get(language, ALERT_TITLE["en"])

    def alert(match: re.Match) -> str:
        body = [re.sub(r"^> ?", "", line) for line in match.group(2).splitlines()]
        lines = "".join(("    " + line if line.strip() else "") + "\n" for line in body)
        return f'!!! {ADMONITION[match.group(1)]} "{titles[match.group(1)]}"\n{lines}\n'

    return re.sub(r"<details(?![^>]*\bmarkdown=)", '<details markdown="1"', ALERT.sub(alert, text))


PDF_COVER = (
    '<article id="doc-cover">\n'
    '{% if cover_logo %}<div class="wrapper upper"><img class="brand-logo" src="{{ cover_logo }}" alt=""></div>'
    '{% else %}<div class="wrapper"></div>{% endif %}\n<div class="wrapper">\n'
    '<h1>{{ cover_title | e }}</h1>\n'
    '{% if cover_subtitle %}<h2>{{ cover_subtitle | e }}</h2>{% endif %}\n</div>\n'
    '<div class="properties"><address>\n'
    '{% if author %}<p id="author">{{ author | e }}</p>{% endif %}\n'
    '{% if copyright %}<p id="copyright">{{ copyright | e }}</p>{% endif %}\n'
    '</address></div>\n</article>\n'
)


def render_mkdocs(root: Path, manual: dict, settings: dict, args: argparse.Namespace, edition: str, site_dir: Path,
                  pdf_path: Path) -> None:
    theme_name, theme_options = resolve_theme(settings, root)
    if args.pdf:
        preflight = subprocess.run([sys.executable, "-m", "weasyprint", "--info"], text=True, capture_output=True, check=False)
        if preflight.returncode:
            detail = preflight.stderr.strip() or preflight.stdout.strip()
            raise SystemExit("PDF renderer unavailable. Install User-Manual/requirements-pdf.lock and the WeasyPrint "
                             f"system libraries for this operating system before retrying.\n{detail}")

    with tempfile.TemporaryDirectory(prefix=".build-", dir=root) as raw_temp:
        temp = Path(raw_temp)
        staged_docs, staged_site = temp / "docs", temp / "site"
        staged_pdf = staged_site / f"{edition}.pdf"
        manifest = assemble(root, manual, args, staged_docs, ".html")
        (staged_docs / "edition.json").replace(temp / "edition.json")
        (staged_docs / "metadata.yml").unlink()
        for page in staged_docs.rglob("*.md"):
            page.write_text(mkdocs_markdown(page.read_text(encoding="utf-8"), args.language), encoding="utf-8")
        brand = manifest["brand"]
        styles = staged_docs / "assets" / "stylesheets"
        styles.mkdir(parents=True, exist_ok=True)
        stylesheets = ["extra.css", "rtl.css", "print.css"]
        if stylesheet_source(root / "theme", f"theme-{theme_name}.css"):
            stylesheets.append(f"theme-{theme_name}.css")
        extra_rtl = rtl_stylesheet(root / "theme", theme_name) if manifest["direction"] == "rtl" else None
        if extra_rtl:
            stylesheets.append(extra_rtl)
        for css in stylesheets:
            found = stylesheet_source(root / "theme", css)
            if found is None:
                raise SystemExit(f"missing manual stylesheet: {root / 'theme' / css}")
            shutil.copy2(found, styles / css)
        primary = (brand.get("colors") or {}).get("primary")
        if primary:
            (styles / "brand.css").write_text(
                f":root {{ --brand-primary: {primary}; --md-primary-fg-color: {primary}; "
                f"--md-accent-fg-color: {primary}; }}\n", encoding="utf-8")
            stylesheets.append("brand.css")
        theme = theme_config(theme_name, args.language, theme_options)
        logo = None
        if "logo" in brand:
            logo = staged_docs / "assets" / "brand" / Path(str(brand["logo"])).name
            logo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / str(brand["logo"]), logo)
            theme.setdefault("logo", logo.relative_to(staged_docs).as_posix())

        plugins: list[object] = ["search"]
        if args.pdf:
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            templates = temp / "pdf_templates"
            templates.mkdir()
            (templates / "cover.html").write_text(PDF_COVER, encoding="utf-8")
            if (root / "theme" / "pdf").is_dir():
                # The project's own cover.html and styles.scss replace the defaults.
                shutil.copytree(root / "theme" / "pdf", templates, dirs_exist_ok=True)
            pdf_options = {"output_path": staged_pdf.name, "cover": True, "toc_title": manifest["toc_title"],
                           "custom_template_path": "pdf_templates", "cover_title": brand["title"],
                           "cover_subtitle": brand.get("subtitle") or manifest["title"].split(" - ", 1)[-1],
                           **{key: brand[key] for key in ("author", "copyright") if key in brand},
                           **({"cover_logo": logo.resolve().as_uri()} if logo else {})}
            if theme_name not in ("material", "mkdocs"):
                # mkdocs-to-pdf 0.10.1 has handlers only for these two, and its generic fallback logs an error and
                # takes the wrong arguments, so any other theme failed. This one adds nothing to the pages.
                (temp / "pdf_theme_handler.py").write_text(
                    "def get_stylesheet(debug_html):\n    return None\n\n\n"
                    "def get_script_sources():\n    return []\n\n\n"
                    "def inject_link(html, href, page, logger, options):\n    return html\n", encoding="utf-8")
                pdf_options["theme_handler_path"] = "pdf_theme_handler.py"
            plugins.append({"to-pdf": pdf_options})
            # mkdocs-to-pdf rebuilds <html> without the page's lang and dir; its event hook, loaded from the
            # build folder, restores them so the RTL rules and the Arabic font apply in the PDF too.
            (temp / "pdf_event_hook.py").write_text(
                "def pre_pdf_render(soup, logger):\n"
                f"    soup.html['lang'] = {args.language!r}\n"
                f"    soup.html['dir'] = {manifest['direction']!r}\n"
                "    return soup\n", encoding="utf-8")
        config = {
            "site_name": manifest["title"],
            # Front matter is stripped from staged pages, so the navigation carries each page's authored title.
            "nav": titled_nav(manifest["nav"], manifest["titles"]),
            "docs_dir": "docs",
            "site_dir": "site",
            "use_directory_urls": False,
            "theme": theme,
            "plugins": plugins,
            "markdown_extensions": ["admonition", "attr_list", "md_in_html", "tables", "toc", "pymdownx.details",
                                    "pymdownx.superfences", "pymdownx.tabbed"],
            "extra_css": [f"assets/stylesheets/{css}" for css in stylesheets],
            "extra": {"audience": args.audience, "language": args.language, "version": args.version, "brand": brand},
        }
        config_path = temp / "mkdocs.yml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
        run_renderer([sys.executable, "-m", "mkdocs", "build", "--strict", "--config-file", str(config_path)],
                     temp, edition, "mkdocs")
        if site_dir.exists():
            shutil.rmtree(site_dir)
        site_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staged_site, site_dir)
        if args.pdf:
            if not staged_pdf.is_file():
                raise SystemExit(f"PDF renderer did not create {staged_pdf}")
            shutil.copy2(staged_pdf, pdf_path)


def build_edition(args: argparse.Namespace, root: Path, manual: dict) -> tuple[Path, Path | None, Path | None]:
    """Build one audience/language edition; returns (output dir, archive or None, pdf or None)."""
    settings = renderer_settings(manual, getattr(args, "renderer", None))
    kind = settings["kind"]
    if args.pdf and kind != "mkdocs":
        raise SystemExit(f"--pdf builds with renderer.kind: mkdocs; with {kind!r}, "
                         + ("the renderer command makes its own PDF" if kind == "command" else "there is no PDF to build"))
    edition, site_dir, pdf_path = edition_paths(root, args)
    if kind == "markdown":
        if site_dir.exists():
            shutil.rmtree(site_dir)
        assemble(root, manual, args, site_dir)
    elif kind == "command":
        render_command(root, manual, settings, args, edition, site_dir)
    else:
        render_mkdocs(root, manual, settings, args, edition, site_dir, pdf_path)

    archive = None
    if args.archive:
        archive = root / "site" / args.version / f"{edition}.zip"
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(site_dir.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(site_dir))
    return site_dir, archive, pdf_path if args.pdf else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--root", type=Path, default=Path("User-Manual"))
    parser.add_argument("--audience", choices=AUDIENCES)
    parser.add_argument("--language")
    parser.add_argument("--all", action="store_true",
                        help="Build every audience for each manual.yml language that has a docs/<lang>/ directory")
    parser.add_argument("--version", default="preview")
    parser.add_argument("--module", help="Build only one module plus shared system pages")
    parser.add_argument("--renderer", choices=RENDERERS, help="Override renderer.kind from manual.yml")
    parser.add_argument("--pdf", action="store_true", help="Also build a PDF (renderer.kind: mkdocs)")
    parser.add_argument("--archive", action="store_true", help="Also zip each edition's output")
    parser.add_argument("--print-renderer", action="store_true",
                        help="Print the renderer kind manual.yml selects and exit (for CI install steps)")
    args = parser.parse_args()
    root = args.root.resolve()
    manual = yaml.safe_load((root / "manual.yml").read_text(encoding="utf-8")) or {}
    if args.print_renderer:
        print(renderer_settings(manual, args.renderer)["kind"])
        return
    if args.all and (args.audience or args.language or args.module):
        parser.error("--all takes no --audience, --language or --module")
    if not args.all and not (args.audience and args.language):
        parser.error("--audience and --language are required without --all")

    if not args.all:
        site_dir, archive, pdf_path = build_edition(args, root, manual)
        if archive:
            print(archive)
        print(site_dir)
        if pdf_path:
            print(pdf_path)
        return
    languages = manual.get("languages") or {}
    wanted = [str(code) for key in ("required", "optional") for code in languages.get(key) or []]
    present = [code for code in dict.fromkeys(wanted) if (root / "docs" / code).is_dir()]
    if not present:
        raise SystemExit(f"no language directory under {root / 'docs'} for manual.yml languages {wanted}")
    for language in present:
        for audience in AUDIENCES:
            edition_args = argparse.Namespace(**{**vars(args), "audience": audience, "language": language})
            site_dir, archive, pdf_path = build_edition(edition_args, root, manual)
            print(f"{audience} {language}: {site_dir}" + (f" {archive}" if archive else "") + (f" {pdf_path}" if pdf_path else ""))


if __name__ == "__main__":
    main()
