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

No third-party dependency: `dependencies.yml` and `.specify/extension-dependencies.yml` are parsed
by a small, strict, narrow-subset reader (see `read_yaml` below) instead of PyYAML, because nothing
in the install/upgrade path (`install.py`, `upgrade.py`, `specify`) installs a package's
`requirements.txt` before its commands run.

Usage:
    python deps.py ensure illustrate [--root PATH] [--dependencies-file PATH]
                                      [--checks-file PATH] [--policy-file PATH]
                                      [--approve] [--skip-catalog-check] [--timeout SECONDS]

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

DEFAULT_POLICY = {'update_policy': 'prompt', 'check_interval_hours': 24}
DEFAULT_TIMEOUT_SECONDS = 60

_COMPARATORS = {
    '==': lambda a, b: compare_versions(a, b) == 0,
    '!=': lambda a, b: compare_versions(a, b) != 0,
    '>=': lambda a, b: compare_versions(a, b) >= 0,
    '<=': lambda a, b: compare_versions(a, b) <= 0,
    '>': lambda a, b: compare_versions(a, b) > 0,
    '<': lambda a, b: compare_versions(a, b) < 0,
}
# Longer operators must precede their prefixes ('>=' before '>', etc.) so the alternation
# matches the intended one. Bound accepts an optional 'v'/'V' prefix, a dotted numeric core,
# an optional '-<prerelease>' suffix and an optional '+<build>' suffix (SemVer-shaped).
_BOUND = r'[vV]?[0-9]+(?:\.[0-9]+)*(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?'
_CLAUSE_RE = re.compile(r'^(==|!=|>=|<=|~=|\^|>|<)\s*(' + _BOUND + r')$')
_VERSION_RE = re.compile(
    r'^[vV]?(?P<core>[0-9]+(?:\.[0-9]+)*)'
    r'(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
    r'(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$'
)
# What `specify extension info <id>` actually prints (plain Rich-rendered text, no --json
# option exists as of specify_cli 1.0.11/pinned commit 8147943512404afb9d99c6252cb9bf84369fd0b0):
# a header line "\n<Name> (v<version>)..." — see command_info.py's `_print_extension_info`
# (catalog hit) and its "installed locally, not in catalog" fallback. Both put the version in
# the first "(v...)" parenthetical.
_CATALOG_HEADER_RE = re.compile(r'\(v([^)]+)\)')


class DepsError(ValueError):
    """A malformed version, range, or dependency file."""


def parse_version(text):
    """Parse a version string into (core_tuple, prerelease_identifiers_or_None). Build
    metadata (a trailing '+...') is accepted but discarded: SemVer precedence ignores it."""
    text = str(text).strip()
    match = _VERSION_RE.match(text)
    if not match:
        raise DepsError('Not a supported version: ' + repr(text))
    core = tuple(int(part) for part in match.group('core').split('.'))
    prerelease = match.group('prerelease')
    identifiers = tuple(prerelease.split('.')) if prerelease else None
    return core, identifiers


def _identifier_key(identifier):
    # SemVer precedence: numeric identifiers compare numerically and always sort below any
    # alphanumeric identifier; alphanumeric identifiers compare as ASCII strings.
    if identifier.isdigit():
        return (0, int(identifier), '')
    return (1, 0, identifier)


def compare_versions(a, b):
    """SemVer precedence comparison; returns <0, 0, or >0. Accepts version strings or
    pre-parsed (core, prerelease) tuples, as returned by `parse_version`."""
    a_core, a_pre = parse_version(a) if isinstance(a, str) else a
    b_core, b_pre = parse_version(b) if isinstance(b, str) else b
    width = max(len(a_core), len(b_core))
    a_core = a_core + (0,) * (width - len(a_core))
    b_core = b_core + (0,) * (width - len(b_core))
    if a_core != b_core:
        return -1 if a_core < b_core else 1
    if a_pre is None and b_pre is None:
        return 0
    if a_pre is None:  # a release has higher precedence than any of its pre-releases
        return 1
    if b_pre is None:
        return -1
    a_keys = [_identifier_key(part) for part in a_pre]
    b_keys = [_identifier_key(part) for part in b_pre]
    for a_key, b_key in zip(a_keys, b_keys):
        if a_key != b_key:
            return -1 if a_key < b_key else 1
    if len(a_keys) != len(b_keys):
        return -1 if len(a_keys) < len(b_keys) else 1
    return 0


def _expand_clause(op, bound):
    """Translate the npm-style '^' and PEP 440 '~=' operators into an equivalent
    (>=, <) pair; every other operator is returned unchanged."""
    if op == '^':
        core, _ = parse_version(bound)
        core = core + (0,) * max(0, 3 - len(core))
        major, minor, patch = core[0], core[1], core[2]
        if major > 0:
            upper = (major + 1, 0, 0)
        elif minor > 0:
            upper = (0, minor + 1, 0)
        else:
            upper = (0, 0, patch + 1)
        return [('>=', bound), ('<', '.'.join(str(part) for part in upper))]
    if op == '~=':
        core, _ = parse_version(bound)
        if len(core) < 2:
            raise DepsError("'~=' requires at least major.minor: " + repr(bound))
        upper = core[:-2] + (core[-2] + 1, 0)
        return [('>=', bound), ('<', '.'.join(str(part) for part in upper))]
    return [(op, bound)]


def _expand_range(range_expr):
    """Expand a whole range expression into a flat list of (op, bound) comparator pairs,
    splitting on commas and/or whitespace and translating '^'/'~=' first."""
    comparators = []
    for raw_clause in re.split(r'[,\s]+', str(range_expr).strip()):
        if not raw_clause:
            continue
        match = _CLAUSE_RE.match(raw_clause)
        if not match:
            raise DepsError('Unsupported version range clause: ' + repr(raw_clause))
        op, bound = match.groups()
        comparators.extend(_expand_clause(op, bound))
    return comparators


def version_satisfies(installed, range_expr):
    """An AND of simple comparator clauses. Clauses may be separated by commas and/or
    whitespace, e.g. '>=2.0.0,<3.0.0' or '>=2.0.0 <3.0.0'. Supports ==, !=, >=, <=, >, <,
    the PEP 440 '~=' compatible-release operator, and the npm-style '^' caret operator;
    pre-release/build-metadata suffixes and a leading 'v' are accepted per SemVer.

    Follows npm-semver's pre-release rule: an installed pre-release version (e.g.
    '3.0.0-rc.1') satisfies a range only if some comparator's bound shares its exact
    major.minor.patch AND that bound itself carries a pre-release tag. A plain '>=2.0.0,<3.0.0'
    range therefore never matches any pre-release, even one numerically inside the range —
    without this, '2.5.0-rc.1' and even '3.0.0-rc.1' would incorrectly satisfy it.
    """
    comparators = _expand_range(range_expr)
    installed_core, installed_pre = parse_version(installed)
    if installed_pre is not None:
        def _same_core(bound_core):
            width = max(len(installed_core), len(bound_core))
            a = installed_core + (0,) * (width - len(installed_core))
            b = bound_core + (0,) * (width - len(bound_core))
            return a == b

        eligible = any(
            _same_core(parse_version(bound)[0]) and parse_version(bound)[1] is not None
            for _, bound in comparators
        )
        if not eligible:
            return False
    for op, bound in comparators:
        if not _COMPARATORS[op](installed, bound):
            return False
    return True


def _parse_scalar(text):
    text = text.strip()
    if not text:
        return None
    if text[0] in ('"', "'"):
        if len(text) < 2 or text[-1] != text[0]:
            raise DepsError('Unbalanced quote in value: ' + repr(text))
        return text[1:-1]
    if text[0] in ('[', '{'):
        if text in ('[]', '{}'):
            return [] if text == '[]' else {}
        raise DepsError('Flow-style YAML value is not supported: ' + repr(text))
    if text == 'true':
        return True
    if text == 'false':
        return False
    if text in ('null', '~'):
        return None
    if re.fullmatch(r'-?[0-9]+', text):
        return int(text)
    return text


def _parse_key(text):
    key = text.strip()
    if key and key[0] in ('"', "'"):
        raise DepsError('Quoted keys are not supported: ' + repr(text))
    return key


def _set_unique(mapping, key, value, lineno):
    if key in mapping:
        raise DepsError('Duplicate key %r at line %d' % (key, lineno))
    mapping[key] = value


def _strip_comment(raw_line):
    """Drop a trailing ' #...'/'\\t#...' comment, respecting quotes: a '#' inside a quoted
    scalar (e.g. a version range that happened to contain one) is never treated as a comment.
    An unterminated quote is left as-is here; `_parse_scalar` raises on it once the value is
    extracted, so the error names the actual malformed value instead of a mangled one.
    """
    quote = None
    for i, ch in enumerate(raw_line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch == '#' and (i == 0 or raw_line[i - 1] in (' ', '\t')):
            return raw_line[:i]
    return raw_line


def read_yaml(path, default=None):
    """Read the narrow YAML subset actually used by `dependencies.yml` and
    `.specify/extension-dependencies.yml`: top-level `key: value` scalars, plus at most one
    level of either a flat mapping (`defaults:` followed by indented `key: value` lines) or a
    list of flat mappings (`dependencies:` followed by indented `- key: value` items, each
    optionally continued by further indented `key: value` lines). Nothing deeper is supported;
    an unrecognised construct raises `DepsError` rather than silently mis-parsing. This is
    deliberately not a general YAML parser — see the module docstring for why.
    """
    if default is None:
        default = {}
    if path is None or not Path(path).is_file():
        return default

    lines = []  # (lineno, indent, stripped_content), comments/blank lines removed
    for lineno, raw in enumerate(Path(path).read_text(encoding='utf-8-sig').splitlines(), 1):
        content = _strip_comment(raw).rstrip()
        stripped = content.strip()
        if not stripped or stripped.startswith('#') or stripped == '---' or stripped.startswith('%'):
            continue
        leading = content[:len(content) - len(content.lstrip())]
        if '\t' in leading:
            raise DepsError('Tab in leading whitespace at line %d: %r' % (lineno, raw))
        indent = len(leading)
        lines.append((lineno, indent, stripped))

    result = {}
    i, total = 0, len(lines)
    while i < total:
        lineno, indent, stripped = lines[i]
        if indent != 0:
            raise DepsError('Unsupported YAML indentation at line %d: %r' % (lineno, stripped))
        if ':' not in stripped:
            raise DepsError('Unsupported YAML line %d: %r' % (lineno, stripped))
        key, _, value = stripped.partition(':')
        key, value = _parse_key(key), value.strip()
        i += 1
        if value:
            _set_unique(result, key, _parse_scalar(value), lineno)
            continue
        if i >= total or lines[i][1] <= indent:
            _set_unique(result, key, None, lineno)
            continue
        child_indent = lines[i][1]
        if lines[i][2].startswith('- '):
            items = []
            while i < total and lines[i][1] == child_indent and lines[i][2].startswith('- '):
                item_lineno, _, item_line = lines[i]
                item = {}
                body = item_line[2:].strip()
                i += 1
                if body:
                    if ':' not in body:
                        raise DepsError('Unsupported YAML list item at line %d: %r' % (item_lineno, body))
                    k, _, v = body.partition(':')
                    _set_unique(item, _parse_key(k), _parse_scalar(v.strip()), item_lineno)
                field_indent = None
                while i < total and lines[i][1] > child_indent:
                    f_lineno, f_indent, f_line = lines[i]
                    if field_indent is None:
                        field_indent = f_indent
                    elif f_indent != field_indent:
                        raise DepsError('Unsupported YAML indentation at line %d: %r' % (f_lineno, f_line))
                    if ':' not in f_line:
                        raise DepsError('Unsupported YAML line %d: %r' % (f_lineno, f_line))
                    k, _, v = f_line.partition(':')
                    _set_unique(item, _parse_key(k), _parse_scalar(v.strip()), f_lineno)
                    i += 1
                items.append(item)
            _set_unique(result, key, items, lineno)
        else:
            mapping = {}
            while i < total and lines[i][1] == child_indent:
                f_lineno, _, f_line = lines[i]
                if ':' not in f_line:
                    raise DepsError('Unsupported YAML line %d: %r' % (f_lineno, f_line))
                k, _, v = f_line.partition(':')
                _set_unique(mapping, _parse_key(k), _parse_scalar(v.strip()), f_lineno)
                i += 1
            _set_unique(result, key, mapping, lineno)
    return result


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
    dependencies = data.get('dependencies')
    if dependencies is None:
        dependencies = []
    if not isinstance(dependencies, list) or not all(isinstance(item, dict) for item in dependencies):
        raise DepsError("'dependencies' must be a list of mappings in " + str(dependencies_file))
    for entry in dependencies:
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


def run_specify(args, runner, input=None, timeout=None):
    """Run `specify <args>`. Both `specify extension add --from <url>` (without `--dev`) and
    `specify extension update` can prompt interactively (`typer.confirm`, no `--yes`/`--force`
    equivalent exists in specify_cli 1.0.11): pass `input='y\\n'` to auto-confirm an authorised
    mutation, and otherwise close stdin (`DEVNULL`) so an unexpected prompt fails fast (Click
    raises `Abort` on EOF) instead of hanging on an inherited interactive stdin. Every call has a
    timeout; `subprocess.TimeoutExpired` is treated as a plain command failure, not raised.
    """
    kwargs = {'capture_output': True, 'text': True, 'encoding': 'utf-8',
              'timeout': DEFAULT_TIMEOUT_SECONDS if timeout is None else timeout}
    if input is not None:
        kwargs['input'] = input
    else:
        kwargs['stdin'] = subprocess.DEVNULL
    try:
        return runner(['specify'] + list(args), **kwargs)
    except FileNotFoundError as exc:
        return _FakeCompleted(127, '', str(exc))
    except subprocess.TimeoutExpired as exc:
        return _FakeCompleted(124, '', 'timed out after ' + str(exc.timeout) + 's: ' + str(exc))
    except OSError as exc:
        return _FakeCompleted(1, '', str(exc))


def catalog_version(name, runner, timeout=None):
    """The catalog's current version for `name`, from `specify extension info`'s plain-text
    header, or None if the command failed or the header could not be found/parsed. Never
    raises: an unparseable or absent catalog version is something to ignore, not a fatal error.
    """
    result = run_specify(['extension', 'info', name], runner, timeout=timeout)
    if result.returncode != 0 or not result.stdout:
        return None
    match = _CATALOG_HEADER_RE.search(result.stdout)
    if not match:
        return None
    candidate = match.group(1).strip()
    try:
        parse_version(candidate)
    except DepsError:
        return None
    return candidate


def _recipe(name, existing):
    return 'specify extension ' + ('update' if existing else 'add') + ' ' + name


def ensure(name, root, dependencies_file, checks_file=None, policy_file=None, approve=False,
           skip_catalog_check=False, runner=subprocess.run, now=None, timeout=None):
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
        raise DepsError('Unsupported update_policy: ' + repr(update_policy))

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
        # 'update' always prompts "Update these extensions?" with no --yes equivalent; feed it
        # a confirmation since this branch only runs once the policy has authorised the change.
        # 'add' (no --from) never prompts, so it keeps stdin closed via run_specify's default.
        result = run_specify(['extension', action, name], runner,
                              input='y\n' if action == 'update' else None, timeout=timeout)
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
    if due and not skip_catalog_check:
        latest = catalog_version(name, runner, timeout=timeout)
        if latest is not None:
            # Record the check only now: a skipped probe (--skip-catalog-check) or one that
            # failed/returned nothing must not stamp checked_at, or a working install would
            # look "recently checked" for check_interval_hours despite having learned nothing.
            checked[name] = {'checked_at': now.isoformat(), 'installed_version': entry.get('version')}
            write_json(checks_file, checked)
            try:
                _, latest_pre = parse_version(latest)
                # A pre-release catalog release (e.g. '3.0.0-rc.1') is never "newer": it must
                # never be surfaced to the user or auto-installed as a stable upgrade. Nor is a
                # catalog version that is merely *different* from the installed one: it must be
                # strictly greater by SemVer precedence, or an older-but-still-range-compatible
                # catalog result (e.g. installed 1.2.0, catalog 1.1.0, both satisfying '^1.0.0')
                # would be reported and even auto-installed as an "update".
                is_newer = (latest_pre is None
                            and compare_versions(latest, entry.get('version')) > 0
                            and version_satisfies(latest, range_expr))
            except DepsError:
                # An unparseable catalog version (a format this script doesn't recognise) is
                # ignored, not fatal: the dependency itself is already known-compatible here.
                is_newer = False
            if is_newer:
                if update_policy == 'auto':
                    run_specify(['extension', 'update', name], runner, input='y\n', timeout=timeout)
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
    ensure_parser.add_argument('--timeout', type=float, default=None,
                                help='Per-subprocess-call timeout in seconds (default: %d)' % DEFAULT_TIMEOUT_SECONDS)

    args = parser.parse_args(argv)

    script_path = Path(__file__).resolve()
    dependencies_file = args.dependencies_file or (script_path.parent.parent / 'dependencies.yml')
    root = args.root or _default_root(script_path)

    try:
        ok, message = ensure(args.name, root, dependencies_file, checks_file=args.checks_file,
                              policy_file=args.policy_file, approve=args.approve,
                              skip_catalog_check=args.skip_catalog_check, timeout=args.timeout)
    except DepsError as exc:
        print(args.name + ': ' + str(exc))
        return 1

    print(message)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
