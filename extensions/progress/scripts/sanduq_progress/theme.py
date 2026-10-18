"""Progress theme (progress.theme.v1): presets, strict validation, css/layout rendering. Stdlib only."""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import tempfile
from pathlib import Path

try:
    from .paths import PLAN_ROOT, project_dir, registry_dirs
except ImportError:  # run as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sanduq_progress.paths import PLAN_ROOT, project_dir, registry_dirs

BLOCKS = ("header", "decisions", "blockers", "orchestrator", "lanes", "boards", "events")  # attention first
TOKEN_KEYS = ("bg", "surface", "text", "muted", "line", "brand", "accent",
              "active", "waiting", "blocked", "done", "failed")
TOP_KEYS = {"v", "preset", "title", "logo", "density", "blocks", "hidden", "tokens", "font", "layout"}
LAYOUTS = ("timeline", "classic")  # timeline: the v3 Timeline view (default); classic: the v2 lanes view, fed the v2 document
DEFAULT_LAYOUT = "timeline"
DENSITIES = ("comfortable", "compact")
FONT_KEYS = ("sans", "mono")
DEFAULT_FONT = {"sans": "system-ui, -apple-system, 'Segoe UI', 'Noto Sans Arabic', sans-serif",
                "mono": "ui-monospace, 'Cascadia Mono', Consolas, monospace"}
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_FONT_BAD = re.compile(r"[;{}<>\\\n\r]")
_STATUS = {
    "light": {"waiting": "#6b7a74", "blocked": "#b3471f", "done": "#2f7a4d", "failed": "#a61b3a"},
    "dark": {"waiting": "#9aa8a1", "blocked": "#ef8a63", "done": "#5fbf84", "failed": "#f07088"},
}


class ThemeError(ValueError):
    pass


# Illustrate registry values (copied in; no YAML at runtime). tint = accent-tint rgba.
_ILL = {
    "cobalt": {
        "light": dict(paper="#f6f8fc", paper2="#ffffff", ink="#15233c", muted="#4f6078", rule="#c7d2e2",
                      accent="#2563eb", tint=(37, 99, 235, 0.09), link="#1d4ed8"),
        "dark": dict(paper="#101827", paper2="#17233a", ink="#f5f7fb", muted="#b6c2d4", rule="#40506a",
                     accent="#6ea0ff", tint=(110, 160, 255, 0.14), link="#8ab4ff"),
    },
    "emerald": {
        "light": dict(paper="#f4f8f5", paper2="#ffffff", ink="#15372f", muted="#496a60", rule="#c5d8d1",
                      accent="#0f8a64", tint=(15, 138, 100, 0.09), link="#0877a8"),
        "dark": dict(paper="#10231e", paper2="#173029", ink="#f3f8f6", muted="#b4c9c1", rule="#3c5e53",
                     accent="#49c99a", tint=(73, 201, 154, 0.14), link="#7fc8ff"),
    },
    "classic": {
        "light": dict(paper="#f5f5f5", paper2="#ececec", ink="#2d3142", muted="#4f5d75", rule="#bfc0c0",
                      accent="#eb6c36", tint=(235, 108, 54, 0.08), link="#2e5aa8"),
        "dark": dict(paper="#2d3142", paper2="#393e53", ink="#f5f5f5", muted="#bfc0c0", rule="#4f5363",
                     accent="#f08a59", tint=(240, 138, 89, 0.10), link="#6a95d8"),
    },
}


def _rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _blend(tint, base_hex):
    r, g, b, a = tint
    br, bg_, bb = _rgb(base_hex)
    return "#%02x%02x%02x" % tuple(round(c * a + base * (1 - a)) for c, base in ((r, br), (g, bg_), (b, bb)))


def _from_ill(name, mode, strong_active):
    v = _ILL[name][mode]
    active = v["link"] if strong_active else _blend(v["tint"], v["paper"])
    t = {"bg": v["paper"], "surface": v["paper2"], "text": v["ink"], "muted": v["muted"], "line": v["rule"],
         "brand": v["link"], "accent": v["accent"], "active": active}
    t.update(_STATUS[mode])
    return t


def _sanduq(mode):
    base = {"light": ("#f6f7f4", "#ffffff", "#1b2a24", "#4e5d56", "#d5dcd7", "#233c32", "#c65b36", "#2a62a0"),
            "dark": ("#121916", "#1a2420", "#eef2ef", "#a9b6af", "#2f3d37", "#dfe9e3", "#e07a55", "#7db4e8")}[mode]
    t = dict(zip(("bg", "surface", "text", "muted", "line", "brand", "accent", "active"), base))
    t.update(_STATUS[mode])
    return t


PRESETS = {"sanduq": {"light": _sanduq("light"), "dark": _sanduq("dark")}}
for _n in _ILL:
    PRESETS[_n] = {"light": _from_ill(_n, "light", True), "dark": _from_ill(_n, "dark", True)}

DEFAULT_PRESET = "sanduq"


def _fail(reason):
    raise ThemeError(reason)


def _check_color(where, val):
    if not isinstance(val, str) or not _HEX.match(val):
        _fail(f"{where} must be #rgb or #rrggbb")


def validate(doc):
    """Strictly validate a theme document; returns it unchanged or raises ThemeError."""
    if not isinstance(doc, dict):
        _fail("theme must be a JSON object")
    extra = set(doc) - TOP_KEYS
    if extra:
        _fail("unknown key " + sorted(extra)[0])
    if doc.get("v", 1) != 1:
        _fail("unsupported version")
    preset = doc.get("preset", DEFAULT_PRESET)
    if preset not in PRESETS:
        _fail("unknown preset " + str(preset)[:40])
    for k in ("title", "logo"):
        val = doc.get(k)
        if val is not None and (not isinstance(val, str) or len(val) > 200 or re.search(r"[\x00-\x1f]", val)):
            _fail(f"{k} must be a short string or null")
    if doc.get("density", "comfortable") not in DENSITIES:
        _fail("density must be comfortable or compact")
    if doc.get("layout", DEFAULT_LAYOUT) not in LAYOUTS:
        _fail("layout must be timeline or classic")
    for k in ("blocks", "hidden"):
        val = doc.get(k, [])
        if not isinstance(val, list) or any(b not in BLOCKS for b in val) or len(set(val)) != len(val):
            _fail(f"{k} must be a list of unique known blocks")
    tokens = doc.get("tokens", {})
    if not isinstance(tokens, dict) or set(tokens) - {"light", "dark"}:
        _fail("tokens must contain only light and dark")
    for mode, vals in tokens.items():
        if not isinstance(vals, dict):
            _fail(f"tokens.{mode} must be an object")
        for key, val in vals.items():
            if key not in TOKEN_KEYS:
                _fail(f"unknown token {mode}.{key}")
            _check_color(f"tokens.{mode}.{key}", val)
    font = doc.get("font", {})
    if not isinstance(font, dict) or set(font) - set(FONT_KEYS):
        _fail("font allows only sans and mono")
    for key, val in font.items():
        if not isinstance(val, str) or not val.strip() or len(val) > 200 or _FONT_BAD.search(val):
            _fail(f"font.{key} is not a safe font stack")
    return doc


def resolve_doc(doc=None):
    """Resolve an (optional) theme document into the full effective theme."""
    doc = validate(doc if doc is not None else {})
    preset = doc.get("preset", DEFAULT_PRESET)
    tokens = copy.deepcopy(PRESETS[preset])
    for mode, vals in doc.get("tokens", {}).items():
        tokens[mode].update(vals)
    hidden = list(doc.get("hidden", []))
    order = [b for b in doc.get("blocks", []) if b in BLOCKS]
    order += [b for b in BLOCKS if b not in order]
    font = dict(DEFAULT_FONT)
    font.update(doc.get("font", {}))
    return {"v": 1, "preset": preset, "title": doc.get("title"), "logo": doc.get("logo"),
            "density": doc.get("density", "comfortable"), "blocks": order, "hidden": hidden,
            "tokens": tokens, "font": font, "layout": doc.get("layout", DEFAULT_LAYOUT)}


def theme_path(project_root):
    return project_dir(project_root) / "theme.json"


def resolve(project_root):
    path = theme_path(project_root)
    if not path.is_file():
        return resolve_doc({})
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _fail("cannot read theme.json: " + str(exc)[:80])
    return resolve_doc(doc)


def _vars(tokens):
    return "".join(f"--{k}:{tokens[k]};" for k in TOKEN_KEYS)


def render_css(resolved):
    """Only :root custom properties (light, dark by media query, forced dark) plus density and fonts."""
    light, dark = resolved["tokens"]["light"], resolved["tokens"]["dark"]
    compact = resolved["density"] == "compact"
    dens = "--pad:{};--gap:{};".format("6px" if compact else "10px", "8px" if compact else "14px")
    fonts = "--sans:{};--mono:{};".format(resolved["font"]["sans"], resolved["font"]["mono"])
    return (
        "/* generated by progress theme; tokens only */\n"
        f":root{{color-scheme:light dark;{_vars(light)}{dens}{fonts}}}\n"
        f"@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{{_vars(dark)}}}}}\n"
        f":root[data-theme=dark]{{{_vars(dark)}}}\n"
    )


def render_layout(resolved):
    hidden = list(resolved["hidden"])
    blocks = [b for b in resolved["blocks"] if b not in hidden]
    payload = {"blocks": blocks, "hidden": hidden, "density": resolved["density"],
               "title": resolved.get("title"), "logo": resolved.get("logo"), "preset": resolved["preset"],
               "layout": resolved.get("layout", DEFAULT_LAYOUT)}
    text = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")
    return "window.__SANDUQ_PROGRESS_LAYOUT__=" + text + ";\n"


def _atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_assets(view_dir, resolved):
    """Write theme.css and layout.js atomically into the .view directory."""
    view_dir = Path(view_dir)
    _atomic_write(view_dir / "theme.css", render_css(resolved))
    _atomic_write(view_dir / "layout.js", render_layout(resolved))


def _scalar(v):
    v = v.split(" #")[0].strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def read_illustrate(project_root):
    """Minimal key:value read of .github/illustration-theme.yml -> {'theme', 'mode'} (no PyYAML)."""
    path = Path(project_root) / ".github" / "illustration-theme.yml"
    if not path.is_file():
        _fail("no .github/illustration-theme.yml")
    out, section = {}, None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        key, _, val = raw.strip().partition(":")
        if indent == 0:
            section = key if not val.strip() else None
        elif section == "active" and key in ("theme", "mode"):
            out[key] = _scalar(val)
    if "theme" not in out:
        _fail("illustration-theme.yml has no active.theme")
    return out


def from_illustrate(project_root):
    """Theme document mapping Illustrate roles: paper->bg, paper-2->surface, ink->text, muted->muted,
    rule->line, accent->accent, link->brand, accent-tint->active (blended onto paper)."""
    name = read_illustrate(project_root)["theme"]
    if name not in _ILL:
        _fail("unsupported illustrate theme " + name[:40])
    keep = ("bg", "surface", "text", "muted", "line", "brand", "accent", "active")
    tokens = {m: {k: v for k, v in _from_ill(name, m, False).items() if k in keep} for m in ("light", "dark")}
    return {"v": 1, "preset": name, "tokens": tokens}


def _stored(project_root):
    """The theme.json document as stored ({} when there is none); an unreadable one is an error, never silently replaced."""
    path = theme_path(project_root)
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _fail("cannot read theme.json: " + str(exc)[:80])
    validate(doc)
    return doc


def _store(project_root, doc):
    validate(doc)
    _atomic_write(theme_path(project_root), json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def _views(root):
    return [*root.glob("specs/*/progress/.view"), *root.glob(PLAN_ROOT + "/*/.view"),
            *(root / d / ".view" for d in registry_dirs(root))]


def _refresh_views(project_root, resolved):
    for view in _views(Path(project_root)):
        if view.is_dir():
            write_assets(view, resolved)


def _republish(project_root):
    """Rebuild report.json and data.js for every initialised report, each under its own report lock. The layout decides
    which document data.js carries (v3 for timeline, v2 for classic), so changing it must publish the matching one now;
    the next hook or refresh would otherwise leave the browser showing the wrong schema. Returns the reports it could not
    republish as (feature, reason) pairs; the theme itself is already saved."""
    import importlib
    from datetime import datetime, timezone
    package = __package__ or "sanduq_progress"  # run as a script, there is no package: the top of this file puts it on sys.path
    Lock, LockBusy = (getattr(importlib.import_module(package + ".lock"), n) for n in ("Lock", "LockBusy"))
    Ctx = importlib.import_module(package + ".paths").Ctx
    refresh = importlib.import_module(package + ".refresh").refresh
    util = importlib.import_module(package + ".util")
    ProgressError, utcnow = util.ProgressError, util.utcnow
    root = Path(project_root)
    stamp = os.environ.get("SANDUQ_PROGRESS_NOW")  # the same test clock the progress command honours
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc) if stamp else utcnow()
    failed = []
    for view in _views(root):
        directory = view.parent
        is_feature = directory.name == "progress" and directory.parent.parent.name == "specs"
        feature = (directory.parent if is_feature else directory).relative_to(root).as_posix()
        try:
            ctx = Ctx(root, feature)
            if not ctx.report.is_file():
                continue  # never initialised: nothing to republish
            lock = Lock(ctx.lock, retries=3, delay=0.2)
            try:
                lock.acquire()
            except LockBusy:
                failed.append((feature, "another progress command is running"))
                continue
            try:
                refresh(ctx, moment)
            finally:
                lock.release()
        except (OSError, ValueError, ProgressError) as exc:
            failed.append((feature, type(exc).__name__))
    return failed


USAGE = "theme --preset NAME | --from-illustrate | --file PATH | --layout timeline|classic | --show | --help"


def cli(argv, project_root=None):
    root = Path(project_root) if project_root else Path.cwd()
    args = list(argv)
    try:
        if args in (["--help"], ["-h"]):
            print(USAGE)
            return 0
        if args == ["--show"]:
            print(json.dumps(resolve(root), indent=2))
            return 0
        if len(args) == 2 and args[0] == "--layout":
            if args[1] not in LAYOUTS:
                _fail("layout must be timeline or classic")
            doc = _stored(root)  # only the layout changes; every other customization is kept
            doc["layout"] = args[1]
            doc.setdefault("v", 1)
            label = "layout " + args[1]
        elif len(args) == 2 and args[0] == "--preset":
            if args[1] not in PRESETS:
                _fail("unknown preset " + args[1][:40])
            doc, label = {"v": 1, "preset": args[1]}, args[1]
        elif args == ["--from-illustrate"]:
            doc = from_illustrate(root)
            label = doc["preset"]
        elif len(args) == 2 and args[0] == "--file":
            try:
                doc = json.loads(Path(args[1]).read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                _fail("cannot read file: " + str(exc)[:80])
            validate(doc)
            doc.setdefault("v", 1)
            label = doc.get("preset", DEFAULT_PRESET)
        else:
            print("progress: error PROGRESS_USAGE " + USAGE)
            return 2
        if "layout" not in doc:
            keep = _stored(root).get("layout")  # a new look keeps the layout the user picked
            if keep:
                doc["layout"] = keep
        before = resolve(root).get("layout")
        _store(root, doc)
        _refresh_views(root, resolve_doc(doc))
        print(f"progress: theme {label}")
        if resolve_doc(doc).get("layout") != before:
            for feature, why in _republish(root):
                print(f"progress: warning data.js for {feature} not republished ({why}); run progress refresh")
        return 0
    except ThemeError as exc:
        print(f"progress: error PROGRESS_THEME_INVALID {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
