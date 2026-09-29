#!/usr/bin/env python3
"""Ensure a declared Spec Kit extension dependency (e.g. `illustrate`) is installed, enabled, and
within its declared SemVer range.

This replaces the "Ensure the Illustrate dependency" instruction block that used to be duplicated,
verbatim, across the pr, assure, and user-manual commands (B9). The checks, the policy handling,
and the failure message/recipe are unchanged from that block; only the mechanism moved from
per-command prose to one script every command calls.

Ships identically into `pr/scripts/deps.py`, `assure/scripts/deps.py`, and
`user-manual/scripts/deps.py` by `extensions/scripts/package.py`; canonical source and tests live
here, under `extensions/scripts/shared/` and `extensions/scripts/tests/`.

Usage:
    python deps.py ensure illustrate [--root PATH] [--dependencies-file PATH]
                                      [--checks-file PATH] [--policy-file PATH]
                                      [--approve] [--skip-catalog-check]

Prints exactly one line and exits 0 when the dependency is ready, non-zero otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError as _exc:  # pragma: no cover - environment guard
    yaml = None
    _YAML_IMPORT_ERROR = _exc
else:
    _YAML_IMPORT_ERROR = None

DEFAULT_POLICY = {'update_policy': 'prompt', 'check_interval_hours': 24}

_COMPARATORS = {
    '==': lambda a, b: a == b,
    '!=': lambda a, b: a != b,
    '>=': lambda a, b: a >= b,
    '<=': lambda a, b: a <= b,
    '>': lambda a, b: a > b,
    '<': lambda a, b: a < b,
}
_CLAUSE_RE = re.compile(r'^(==|!=|>=|<=|>|<)\s*([0-9]+(?:\.[0-9]+)*)$')


class DepsError(ValueError):
    """A malformed version, range, or dependency file."""


def _require_yaml():
    if yaml is None:
        raise DepsError('PyYAML is required to read dependencies.yml (pip install PyYAML): ' + str(_YAML_IMPORT_ERROR))
    return yaml


def parse_version(text):
    text = str(text).strip()
    parts = [p for p in text.split('.') if p != '']
    if not parts or not all(p.isdigit() for p in parts):
        raise DepsError('Not a supported version: ' + repr(text))
    return tuple(int(p) for p in parts)


def version_satisfies(installed, range_expr):
    """A comma-separated AND of simple comparator clauses, e.g. '>=2.0.0,<3.0.0'."""
    installed_tuple = parse_version(installed)
    for clause in str(range_expr).split(','):
        clause = clause.strip()
        if not clause:
            continue
        match = _CLAUSE_RE.match(clause)
        if not match:
            raise DepsError('Unsupported version range clause: ' + repr(clause))
        op, bound = match.groups()
        bound_tuple = parse_version(bound)
        width = max(len(installed_tuple), len(bound_tuple))
        a = installed_tuple + (0,) * (width - len(installed_tuple))
        b = bound_tuple + (0,) * (width - len(bound_tuple))
        if not _COMPARATORS[op](a, b):
            return False
    return True


def read_yaml(path, default=None):
    if default is None:
        default = {}
    if path is None or not Path(path).is_file():
        return default
    _require_yaml()
    with open(path, 'r', encoding='utf-8-sig') as handle:
        return yaml.safe_load(handle) or {}


def read_json(path, default=None):
    if default is None:
        default = {}
    if path is None or not Path(path).is_file():
        return default
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (ValueError, OSError):
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def registry_entry(root, name):
    data = read_json(Path(root) / '.specify/extensions/.registry')
    return (data.get('extensions') or {}).get(name)


def dependency_declaration(dependencies_file, name):
    data = read_yaml(dependencies_file)
    for entry in (data.get('dependencies') or []):
        if entry.get('id') == name:
            return entry
    return None


def project_policy(root, package_defaults, policy_file=None):
    policy = dict(DEFAULT_POLICY)
    for key in DEFAULT_POLICY:
        if package_defaults and key in package_defaults:
            policy[key] = package_defaults[key]
    project = read_yaml(Path(root) / '.specify/extension-dependencies.yml')
    for key in DEFAULT_POLICY:
        if key in project:
            policy[key] = project[key]
    if policy_file is not None:
        override = read_yaml(policy_file)
        for key in DEFAULT_POLICY:
            if key in override:
                policy[key] = override[key]
    return policy


class _FakeCompleted:
    def __init__(self, returncode, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_specify(args, runner):
    try:
        return runner(['specify'] + list(args), capture_output=True, text=True, encoding='utf-8')
    except FileNotFoundError as exc:
        return _FakeCompleted(127, '', str(exc))
    except OSError as exc:
        return _FakeCompleted(1, '', str(exc))


def catalog_version(name, runner):
    result = run_specify(['extension', 'info', name], runner)
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        data = json.loads(result.stdout)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    for key in ('version', 'catalog_version', 'latest_version'):
        value = data.get(key)
        if isinstance(value, str):
            return value
    return None


def _recipe(name, existing):
    return 'specify extension ' + ('update' if existing else 'add') + ' ' + name


def ensure(name, root, dependencies_file, checks_file=None, policy_file=None, approve=False,
           skip_catalog_check=False, runner=subprocess.run, now=None):
    """Return (ok, message). `ok` is False exactly when the dependency is missing/incompatible
    and cannot be brought into range under the effective policy; `message` is always one line.
    """
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    checks_file = Path(checks_file) if checks_file is not None else (root / '.specify/extensions/.dependency-checks.json')

    declaration = dependency_declaration(dependencies_file, name)
    if declaration is None:
        return False, name + ': no dependency declaration for "' + name + '" in ' + str(dependencies_file)
    range_expr = declaration.get('version')
    if not range_expr:
        return False, name + ': dependency declaration in ' + str(dependencies_file) + ' has no version range'

    package_data = read_yaml(dependencies_file)
    policy = project_policy(root, package_data.get('defaults'), policy_file)
    update_policy = policy.get('update_policy', 'prompt')
    if update_policy not in ('prompt', 'auto', 'manual'):
        update_policy = 'prompt'

    def compatible_entry():
        entry = registry_entry(root, name)
        ok = bool(entry) and entry.get('enabled') is True and version_satisfies(entry.get('version', '0'), range_expr)
        return entry, ok

    entry, compatible = compatible_entry()

    if not compatible:
        can_mutate = update_policy == 'auto' or (update_policy == 'prompt' and approve)
        if not can_mutate:
            if not entry:
                reason = 'absent'
            elif entry.get('enabled') is not True:
                reason = 'disabled'
            else:
                reason = 'installed ' + str(entry.get('version')) + ' is outside ' + range_expr
            return False, (name + ': ' + reason + ' (policy ' + update_policy + '); run: ' + _recipe(name, bool(entry)))
        action = 'update' if entry else 'add'
        result = run_specify(['extension', action, name], runner)
        entry, compatible = compatible_entry()
        if not compatible:
            detail_lines = [line for line in (result.stderr or result.stdout or '').strip().splitlines() if line.strip()]
            detail = (': ' + detail_lines[-1]) if detail_lines else ''
            return False, (name + ': `' + _recipe(name, action == 'update') + '` did not produce a compatible install'
                            ' (exit ' + str(result.returncode) + ')' + detail + '; run: ' + _recipe(name, bool(entry)))

    checked = read_json(checks_file)
    last = (checked.get(name) or {}).get('checked_at')
    due = True
    if last:
        try:
            elapsed_hours = (now - datetime.fromisoformat(last)).total_seconds() / 3600.0
            due = elapsed_hours >= float(policy.get('check_interval_hours', 24))
        except (ValueError, TypeError):
            due = True

    newer_note = ''
    if due:
        latest = None if skip_catalog_check else catalog_version(name, runner)
        checked[name] = {'checked_at': now.isoformat(), 'installed_version': entry.get('version')}
        write_json(checks_file, checked)
        if latest and latest != entry.get('version') and version_satisfies(latest, range_expr):
            if update_policy == 'auto':
                run_specify(['extension', 'update', name], runner)
                refreshed, refreshed_ok = compatible_entry()
                if refreshed_ok:
                    entry = refreshed
            else:
                newer_note = '; newer compatible release ' + latest + ' available: run ' + _recipe(name, True)

    return True, (name + ': ok (installed ' + str(entry.get('version')) + ', satisfies ' + range_expr + ')' + newer_note)


def _default_root(script_path):
    parents = script_path.parents
    # Installed layout: <root>/.specify/extensions/<pkg>/scripts/deps.py
    if len(parents) > 4 and (parents[3].name == '.specify'):
        return parents[4]
    return Path.cwd()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    ensure_parser = sub.add_parser('ensure', help='Ensure a declared dependency is installed, enabled, and in range')
    ensure_parser.add_argument('name', help='Dependency id, e.g. illustrate')
    ensure_parser.add_argument('--root', type=Path, default=None,
                                help='Project root containing .specify/ (default: inferred from the installed path, else cwd)')
    ensure_parser.add_argument('--dependencies-file', type=Path, default=None,
                                help="This package's dependencies.yml (default: sibling of this script's parent)")
    ensure_parser.add_argument('--checks-file', type=Path, default=None,
                                help='Override .specify/extensions/.dependency-checks.json')
    ensure_parser.add_argument('--policy-file', type=Path, default=None,
                                help='Override .specify/extension-dependencies.yml')
    ensure_parser.add_argument('--approve', action='store_true',
                                help='Explicit user approval to install/update under the prompt policy')
    ensure_parser.add_argument('--skip-catalog-check', action='store_true',
                                help='Skip the read-only catalog freshness probe (no network)')

    args = parser.parse_args(argv)

    script_path = Path(__file__).resolve()
    dependencies_file = args.dependencies_file or (script_path.parent.parent / 'dependencies.yml')
    root = args.root or _default_root(script_path)

    try:
        ok, message = ensure(args.name, root, dependencies_file, checks_file=args.checks_file,
                              policy_file=args.policy_file, approve=args.approve,
                              skip_catalog_check=args.skip_catalog_check)
    except DepsError as exc:
        print(args.name + ': ' + str(exc))
        return 1

    print(message)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
