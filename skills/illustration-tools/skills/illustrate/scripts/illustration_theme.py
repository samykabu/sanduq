#!/usr/bin/env python3
"""Initialize, select, validate, and resolve project-level Illustrate themes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

CONFIG_RELATIVE = Path(".github") / "illustration-theme.yml"
REGISTRY = Path(__file__).resolve().parents[1] / "assets" / "illustration-themes.yml"
COLOR_KEYS = (
    "paper",
    "paper-2",
    "ink",
    "muted",
    "soft",
    "rule",
    "rule-solid",
    "accent",
    "accent-tint",
    "link",
)
FONT_KEYS = ("sans", "serif", "mono", "remote_css_url")


class ThemeError(ValueError):
    pass


def _scalar(value: str) -> Any:
    value = value.strip()
    if value in ("{}", "{ }"):
        return {}
    if value in ("null", "~"):
        return None
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    if value.startswith(('"', "'")):
        try:
            return json.loads(value) if value.startswith('"') else value[1:-1].replace("''", "'")
        except json.JSONDecodeError as exc:
            raise ThemeError(f"invalid quoted value: {value}") from exc
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    """Load the mapping-only YAML subset emitted by this tool without dependencies."""
    if not path.is_file():
        raise ThemeError(f"missing file: {path}")
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ThemeError(f"{path}:{number}: tabs are not supported")
        indent = len(raw) - len(raw.lstrip(" "))
        if indent % 2:
            raise ThemeError(f"{path}:{number}: indentation must use multiples of two spaces")
        body = raw.strip()
        if ":" not in body:
            raise ThemeError(f"{path}:{number}: expected key: value")
        key, value = body.split(":", 1)
        key = key.strip().strip('"').strip("'")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ThemeError(f"{path}:{number}: invalid indentation")
        parent = stack[-1][1]
        if not value.strip():
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _scalar(value)
    return root


def _quote(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def dump_yaml(data: dict[str, Any], indent: int = 0) -> str:
    lines: list[str] = []
    prefix = " " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            if value:
                lines.append(f"{prefix}{key}:")
                lines.append(dump_yaml(value, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {{}}")
        else:
            lines.append(f"{prefix}{key}: {_quote(value)}")
    return "\n".join(lines)


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(data) + "\n", encoding="utf-8")


def project_config(root: str | Path) -> Path:
    return Path(root).resolve() / CONFIG_RELATIVE


def registry() -> dict[str, Any]:
    doc = load_yaml(REGISTRY)
    if not isinstance(doc.get("themes"), dict):
        raise ThemeError(f"{REGISTRY}: themes mapping is required")
    return doc


def default_config(theme: str = "cobalt", mode: str = "light", font_loading: str = "remote") -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "active": {"theme": theme, "mode": mode, "font_loading": font_loading},
        "custom_themes": {},
    }


def _hex_rgb(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ThemeError(f"expected #rrggbb color, got {value!r}")
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def _luminance(value: str) -> float:
    channels = []
    for channel in _hex_rgb(value):
        normalized = channel / 255
        channels.append(normalized / 12.92 if normalized <= 0.04045 else ((normalized + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def validate_palette(name: str, mode: str, palette: dict[str, Any]) -> None:
    missing = [key for key in COLOR_KEYS if not palette.get(key)]
    if missing:
        raise ThemeError(f"theme {name}/{mode} is missing: {', '.join(missing)}")
    for key in ("paper", "paper-2", "ink", "muted", "soft", "rule-solid", "accent", "link"):
        value = str(palette[key])
        if not (re.fullmatch(r"#[0-9a-fA-F]{6}", value) or (key == "rule-solid" and value.startswith("rgba("))):
            raise ThemeError(f"theme {name}/{mode} has invalid {key}: {value}")
    for key in ("rule", "accent-tint"):
        if not re.fullmatch(r"rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*(?:0(?:\.\d+)?|1(?:\.0+)?)\s*\)", str(palette[key])):
            raise ThemeError(f"theme {name}/{mode} has invalid {key}: {palette[key]}")
    ink_ratio = contrast(str(palette["ink"]), str(palette["paper"]))
    muted_ratio = contrast(str(palette["muted"]), str(palette["paper"]))
    if ink_ratio < 4.5:
        raise ThemeError(f"theme {name}/{mode} ink contrast is {ink_ratio:.2f}, below 4.5")
    if muted_ratio < 4.5:
        raise ThemeError(f"theme {name}/{mode} muted contrast is {muted_ratio:.2f}, below 4.5")


def validate_theme(name: str, theme: dict[str, Any]) -> None:
    typography = theme.get("typography")
    if not isinstance(typography, dict):
        raise ThemeError(f"theme {name} is missing typography")
    missing_fonts = [key for key in FONT_KEYS[:3] if not typography.get(key)]
    if missing_fonts:
        raise ThemeError(f"theme {name} typography is missing: {', '.join(missing_fonts)}")
    for mode in ("light", "dark"):
        palette = theme.get(mode)
        if not isinstance(palette, dict):
            raise ThemeError(f"theme {name} is missing {mode} palette")
        validate_palette(name, mode, palette)


def all_themes(config: dict[str, Any]) -> dict[str, Any]:
    merged = dict(registry()["themes"])
    custom = config.get("custom_themes") or {}
    if not isinstance(custom, dict):
        raise ThemeError("custom_themes must be a mapping")
    merged.update(custom)
    return merged


def validate_config(config: dict[str, Any]) -> None:
    if str(config.get("schema_version")) != "1.0":
        raise ThemeError("schema_version must be 1.0")
    active = config.get("active")
    if not isinstance(active, dict):
        raise ThemeError("active mapping is required")
    mode = active.get("mode")
    if mode not in ("light", "dark"):
        raise ThemeError("active.mode must be light or dark")
    if active.get("font_loading") not in ("remote", "local", "system"):
        raise ThemeError("active.font_loading must be remote, local, or system")
    themes = all_themes(config)
    selected = str(active.get("theme", ""))
    if selected not in themes:
        raise ThemeError(f"unknown active theme {selected!r}; available: {', '.join(sorted(themes))}")
    for name, theme in themes.items():
        if not isinstance(theme, dict):
            raise ThemeError(f"theme {name} must be a mapping")
        validate_theme(name, theme)


def choose(prompt: str, choices: list[str], default: int = 0) -> str:
    print(prompt)
    for index, choice in enumerate(choices, 1):
        suffix = " (recommended)" if index - 1 == default else ""
        print(f"  {index}. {choice}{suffix}")
    answer = input(f"Select [{default + 1}]: ").strip()
    if not answer:
        return choices[default]
    try:
        return choices[int(answer) - 1]
    except (ValueError, IndexError) as exc:
        raise ThemeError(f"invalid selection: {answer}") from exc


def command_init(args: argparse.Namespace) -> None:
    path = project_config(args.project_root)
    if path.exists() and not args.force:
        print(f"Theme already initialized: {path}")
        print(dump_yaml(load_yaml(path)))
        return
    reg = registry()
    names = list(reg["themes"])
    theme = args.theme
    mode = args.mode
    font_loading = args.font_loading
    create_custom = False
    interactive = sys.stdin.isatty() and not args.non_interactive
    if interactive and not theme:
        labels = [f"{name} - {reg['themes'][name]['label']}" for name in names] + ["custom - create a project theme"]
        selected = choose("Choose an illustration theme:", labels)
        theme = selected.split(" - ", 1)[0]
        if theme == "custom":
            create_custom = True
            theme = str(reg.get("default_theme", "cobalt"))
    theme = theme or str(reg.get("default_theme", "cobalt"))
    if theme not in names:
        raise ThemeError(f"unknown preset {theme!r}; available: {', '.join(names)}")
    if interactive and not mode:
        mode = choose("Choose the initial color mode:", ["light", "dark"])
    if interactive and not font_loading:
        font_loading = choose("How should diagram fonts load?", ["remote", "local", "system"])
    config = default_config(theme, mode or "light", font_loading or "remote")
    validate_config(config)
    write_yaml(path, config)
    print(f"Initialized {path} with {theme}/{config['active']['mode']}")
    if create_custom:
        command_create(
            argparse.Namespace(
                project_root=args.project_root,
                from_file=None,
                name=None,
                mode=config["active"]["mode"],
            )
        )


def load_or_init(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    path = project_config(args.project_root)
    if not path.exists():
        init_args = argparse.Namespace(
            project_root=args.project_root,
            force=False,
            non_interactive=not sys.stdin.isatty(),
            theme=None,
            mode=None,
            font_loading=None,
        )
        command_init(init_args)
    config = load_yaml(path)
    validate_config(config)
    return path, config


def resolved(config: dict[str, Any]) -> dict[str, Any]:
    active = config["active"]
    name = str(active["theme"])
    mode = str(active["mode"])
    theme = all_themes(config)[name]
    typography = dict(theme["typography"])
    if active["font_loading"] != "remote":
        typography["remote_css_url"] = ""
    return {
        "schema_version": "1.0",
        "theme": name,
        "label": theme.get("label", name),
        "mode": mode,
        "font_loading": active["font_loading"],
        "colors": dict(theme[mode]),
        "typography": typography,
    }


def as_css(theme: dict[str, Any]) -> str:
    lines = []
    url = theme["typography"].get("remote_css_url")
    if url:
        lines.append(f'@import url("{url}");')
    lines.append(":root {")
    for key, value in theme["colors"].items():
        lines.append(f"  --color-{key}: {value};")
    for key in ("sans", "serif", "mono"):
        lines.append(f"  --font-{key}: {theme['typography'][key]};")
    lines.append("}")
    return "\n".join(lines)


def command_resolve(args: argparse.Namespace) -> None:
    _, config = load_or_init(args)
    result = resolved(config)
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.format == "css":
        print(as_css(result))
    else:
        print(dump_yaml(result))


def command_list(args: argparse.Namespace) -> None:
    path = project_config(args.project_root)
    config = load_yaml(path) if path.exists() else default_config()
    active = config.get("active", {})
    for name, theme in all_themes(config).items():
        marker = "*" if name == active.get("theme") else " "
        print(f"{marker} {name:16} {theme.get('label', name)}")


def command_set(args: argparse.Namespace) -> None:
    path, config = load_or_init(args)
    themes = all_themes(config)
    if args.theme not in themes:
        raise ThemeError(f"unknown theme {args.theme!r}; available: {', '.join(sorted(themes))}")
    config["active"]["theme"] = args.theme
    if args.mode:
        config["active"]["mode"] = args.mode
    if args.font_loading:
        config["active"]["font_loading"] = args.font_loading
    validate_config(config)
    write_yaml(path, config)
    print(f"Selected {config['active']['theme']}/{config['active']['mode']} in {path}")


def _prompt_value(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def command_create(args: argparse.Namespace) -> None:
    path, config = load_or_init(args)
    if args.from_file:
        source = load_yaml(Path(args.from_file).resolve())
        source_name = str(source.pop("name", ""))
        name = args.name or source_name
        theme = source
    else:
        if not sys.stdin.isatty():
            raise ThemeError("create requires an interactive terminal or --from-file")
        name = args.name or input("Custom theme id (lowercase letters, numbers, hyphens): ").strip()
        base_name = choose("Start from which preset?", list(registry()["themes"]))
        base = registry()["themes"][base_name]
        theme = {
            "label": _prompt_value("Display label", name.replace("-", " ").title()),
            "description": _prompt_value("Description", f"Project theme based on {base_name}."),
            "typography": {},
            "light": {},
            "dark": {},
        }
        for key in FONT_KEYS:
            theme["typography"][key] = _prompt_value(f"Font {key}", str(base["typography"].get(key, "")))
        for mode in ("light", "dark"):
            print(f"{mode.title()} palette")
            for key in COLOR_KEYS:
                theme[mode][key] = _prompt_value(key, str(base[mode][key]))
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", name):
        raise ThemeError("custom theme id must use lowercase letters, numbers, and hyphens")
    validate_theme(name, theme)
    config.setdefault("custom_themes", {})[name] = theme
    config["active"]["theme"] = name
    if args.mode:
        config["active"]["mode"] = args.mode
    validate_config(config)
    write_yaml(path, config)
    print(f"Created and selected custom theme {name} in {path}")


def command_validate(args: argparse.Namespace) -> None:
    path = project_config(args.project_root)
    config = load_yaml(path) if path.exists() else default_config()
    validate_config(config)
    print(f"Theme configuration is valid: {path if path.exists() else 'built-in cobalt default'}")
    for name in all_themes(config):
        print(f"  {name}: light and dark palettes, typography, and contrast valid")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-root", default=".", help="target project root (default: current directory)")
    sub = ap.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create .github/illustration-theme.yml")
    init.add_argument("--theme", choices=("cobalt", "emerald", "classic"))
    init.add_argument("--mode", choices=("light", "dark"))
    init.add_argument("--font-loading", choices=("remote", "local", "system"))
    init.add_argument("--non-interactive", action="store_true", help="default to cobalt/light without prompting")
    init.add_argument("--force", action="store_true", help="replace an existing project configuration")
    init.set_defaults(handler=command_init)

    listing = sub.add_parser("list", help="list built-in and project custom themes")
    listing.set_defaults(handler=command_list)

    resolve = sub.add_parser("resolve", help="resolve active colors and fonts")
    resolve.add_argument("--format", choices=("yaml", "json", "css"), default="yaml")
    resolve.set_defaults(handler=command_resolve)

    selection = sub.add_parser("set", help="select an existing theme or mode")
    selection.add_argument("--theme", required=True)
    selection.add_argument("--mode", choices=("light", "dark"))
    selection.add_argument("--font-loading", choices=("remote", "local", "system"))
    selection.set_defaults(handler=command_set)

    create = sub.add_parser("create", help="create a custom light/dark theme and font set")
    create.add_argument("--name")
    create.add_argument("--from-file", help="mapping with label, typography, light, and dark sections")
    create.add_argument("--mode", choices=("light", "dark"), default="light")
    create.set_defaults(handler=command_create)

    validate = sub.add_parser("validate", help="validate presets and the project configuration")
    validate.set_defaults(handler=command_validate)
    return ap


def main() -> int:
    try:
        args = parser().parse_args()
        args.handler(args)
        return 0
    except ThemeError as exc:
        print(f"illustration-theme: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
