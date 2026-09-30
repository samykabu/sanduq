#!/usr/bin/env python3
"""Skill inventory, reported per host session load: what a Claude session and
a Codex session actually load, not one combined cross-host number.

`workflow.py doctor --project` surfaces this so C4 (skill pruning) has raw
counts and frontmatter-description byte totals to reason from; this module
never decides what to prune, and "never invoked" stays out of scope until a
telemetry source and window exist (see the plan, package B10).

Host sessions read different, overlapping sets of directories:

- ``claude`` loads home ``~/.claude/skills``, project ``.claude/skills``, and
  every installed, enabled plugin's skills (read from
  ``~/.claude/plugins/installed_plugins.json``, the one place Claude Code
  itself records exactly which installed copy is live; the wider plugin cache
  and marketplace trees hold stale versions and are not scanned). A
  ``project``/``local``-scoped entry only counts for the matching project; a
  plugin ``enabledPlugins`` turns off (user settings, overridden by the
  project's own, overridden by its local settings) is skipped; an
  ``installPath`` must resolve inside ``~/.claude/plugins`` itself (a UNC
  path is rejected by text alone, before touching the filesystem) or it is
  recorded under ``skipped_install_paths`` instead of scanned. When the
  manifest itself is missing or unreadable, plugin skills are reported as not
  counted rather than guessed at.
- ``codex`` loads ``$CODEX_HOME`` (or ``~/.codex``) skills — confirmed live
  against the installed Codex CLI, see ``codex_home_root`` — home
  ``~/.agents/skills``, and project ``.agents/skills``.

Sanduq itself installs the same command skill under both ``.claude/skills``
and ``.agents/skills`` at every level it manages (see
``workflow.HOST_SKILLS``), so a name shared between a claude root and a codex
root is an *expected mirror*, reported separately; only a name repeated
*within* one host's own roots is a duplicate.

A skill root is flat: ``<root>/<skill-name>/SKILL.md`` (matching
``workflow.command_exists``), so scanning is a single directory level per
root; no recursive descent means no symlink-loop risk from a skill's own
subfolders. A same-named entry that is a symlink or junction to elsewhere is
still resolved and de-duplicated so it is never counted twice.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

# Per-host-session-load defaults; see extensions/workflow/README.md ("Skill
# inventory") for the measured reasoning. A project may override either key
# under policy['skills']['inventory_thresholds']; the same limits are applied
# independently to each host's own combined total.
DEFAULT_THRESHOLDS = {
    'skill_count': 200,
    'description_bytes': 40960,  # 40 KiB of one host's combined frontmatter `description:` text
}

# Host name -> the roots (keys into the `roots` scan below) that host's
# session actually loads.
HOST_ROOTS = {
    'claude': ('claude_home', 'claude_project', 'claude_plugins'),
    'codex': ('codex_home', 'agents_home', 'agents_project'),
}
EMPTY_SCAN = {'skill_count': 0, 'description_bytes': 0, 'max_description_bytes': 0, 'skill_md_bytes': 0, 'names': []}


def home_root():
    """Portable resolution of the user's home directory.

    Windows and POSIX both fall back to ``Path.home()``; tests must never
    read the real machine's home directory, so set ``SANDUQ_SKILLS_HOME`` to
    override (the same shape as ``SANDUQ_CLAUDE_PROJECTS`` /
    ``SANDUQ_CODEX_SESSIONS`` in usage.py).
    """
    override = os.environ.get('SANDUQ_SKILLS_HOME')
    return Path(override) if override else Path.home()


def codex_home_root(home=None):
    """Portable resolution of $CODEX_HOME: the real Codex CLI convention, honoured as-is
    (never renamed) so a project's own Codex setup is read correctly; falls
    back to ``<home>/.codex``.

    ``<CODEX_HOME>/skills`` is confirmed live, not legacy: the installed Codex
    CLI (codex-cli 0.159.0, `@openai/codex-win32-x64` vendor `codex.exe`,
    checked 2026-09-29) embeds the literal default-expansion
    ``"${CODEX_HOME:-$HOME/.codex}/skills"`` alongside its `SkillsList`
    client request and `ReloadUserConfig`'s `force_reload`, and the directory
    on disk holds real per-skill folders (each its own `SKILL.md`) a session
    actually reads, plus a `.system` subfolder of bundled skills (imagegen,
    skill-creator, skill-installer, ...) this flat one-level scan does not
    descend into, matching every other root here.
    """
    override = os.environ.get('CODEX_HOME')
    if override:
        return Path(override)
    home_dir = Path(home) if home is not None else home_root()
    return home_dir / '.codex'


def resolve_roots(root, home=None, codex_home=None):
    """The five directory roots this module scans directly (plugin skills are separate)."""
    home_dir = Path(home) if home is not None else home_root()
    codex_dir = Path(codex_home) if codex_home is not None else codex_home_root(home_dir)
    return {
        'claude_home': home_dir / '.claude' / 'skills',
        'claude_project': Path(root) / '.claude' / 'skills',
        'agents_home': home_dir / '.agents' / 'skills',
        'agents_project': Path(root) / '.agents' / 'skills',
        'codex_home': codex_dir / 'skills',
    }


def _frontmatter_block(text):
    """The raw text between the opening and closing ``---`` frontmatter fence, or None."""
    if not text.startswith('---'):
        return None
    after = text[3:]
    if after.startswith('\r\n'):
        after = after[2:]
    elif after.startswith('\n'):
        after = after[1:]
    for fence in ('\n---', '\r\n---'):
        end = after.find(fence)
        if end != -1:
            return after[:end]
    return None


def _description_bytes(raw_text):
    """UTF-8 byte length of the frontmatter `description:` value, or 0 when absent/malformed."""
    block = _frontmatter_block(raw_text)
    if block is None:
        return 0
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return 0
    if not isinstance(data, dict):
        return 0
    description = data.get('description')
    if not isinstance(description, str):
        return 0
    return len(description.encode('utf-8'))


def _skill_dirs(root):
    """Yield (name, SKILL.md path) for each immediate child of ``root`` that has one.

    Robust to a missing root, an unreadable entry, and a symlink/junction
    (resolved and de-duplicated by real path so an alias is never counted
    twice; a broken link or a permission error is skipped, not raised).
    """
    try:
        if not root.is_dir():
            return
        entries = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError:
        return
    seen_real_paths = set()
    for entry in entries:
        try:
            if not entry.is_dir():
                continue
            real = entry.resolve()
        except OSError:
            continue
        if real in seen_real_paths:
            continue
        seen_real_paths.add(real)
        skill_md = entry / 'SKILL.md'
        try:
            if skill_md.is_file():
                yield entry.name, skill_md
        except OSError:
            continue


def _scan_root(root):
    """One directory's inventory: skill count, total/max description bytes, total SKILL.md bytes."""
    count = 0
    description_bytes_total = 0
    description_bytes_max = 0
    skill_md_bytes = 0
    names = []
    for name, skill_md in _skill_dirs(root):
        try:
            raw = skill_md.read_bytes()
        except OSError:
            continue
        count += 1
        skill_md_bytes += len(raw)
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('utf-8', errors='replace')
        size = _description_bytes(text)
        description_bytes_total += size
        description_bytes_max = max(description_bytes_max, size)
        names.append(name)
    return {
        'path': str(root),
        'exists': root.is_dir(),
        'skill_count': count,
        'description_bytes': description_bytes_total,
        'max_description_bytes': description_bytes_max,
        'skill_md_bytes': skill_md_bytes,
        'names': sorted(names),
    }


def _aggregate_scans(scans):
    """Sum several `_scan_root`-shaped dicts (path/exists dropped by the caller)."""
    if not scans:
        return dict(EMPTY_SCAN)
    return {
        'skill_count': sum(s['skill_count'] for s in scans),
        'description_bytes': sum(s['description_bytes'] for s in scans),
        'max_description_bytes': max((s['max_description_bytes'] for s in scans), default=0),
        'skill_md_bytes': sum(s['skill_md_bytes'] for s in scans),
        'names': sorted(name for s in scans for name in s['names']),
    }


def _is_unc_path(value):
    """A UNC-style network path (``\\\\host\\share`` or ``//host/share``), checked
    on the raw string alone: resolving or stat-ing an unreachable network host
    can hang or error slowly, so this is decided before any filesystem call."""
    return value.startswith('\\\\') or value.startswith('//')


def _confine_to_plugins_root(install_path, plugins_root):
    """Resolve ``install_path`` (following symlinks) and require it to land inside
    ``plugins_root`` (already resolved). Returns ``(resolved_path, None)`` when
    accepted, or ``(None, reason)`` when it must be skipped instead."""
    if _is_unc_path(install_path):
        return None, 'UNC path'
    try:
        resolved = Path(install_path).resolve()
    except OSError:
        return None, 'could not resolve'
    if not resolved.is_relative_to(plugins_root):
        return None, 'outside ~/.claude/plugins'
    return resolved, None


def _read_enabled_plugins(path):
    """The `enabledPlugins` map of one settings.json-shaped file, or {} when the
    file is missing, unreadable, malformed, or has none."""
    try:
        raw = path.read_text(encoding='utf-8-sig')
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    enabled = data.get('enabledPlugins') if isinstance(data, dict) else None
    if not isinstance(enabled, dict):
        return {}
    return {key: value for key, value in enabled.items() if isinstance(key, str)}


def _effective_enabled_plugins(home, root):
    """User settings, then the project's settings.json, then its settings.local.json:
    each layer's explicit true/false for a plugin overrides the layer before
    it; a plugin no layer mentions is left out (defaults to enabled, the
    unchanged prior behaviour when no settings file disables it)."""
    effective = {}
    effective.update(_read_enabled_plugins(Path(home) / '.claude' / 'settings.json'))
    effective.update(_read_enabled_plugins(Path(root) / '.claude' / 'settings.json'))
    effective.update(_read_enabled_plugins(Path(root) / '.claude' / 'settings.local.json'))
    return effective


def _plugin_skills_claude(home, root):
    """Claude Code plugin skills, read only through the installed-plugins manifest.

    ``~/.claude/plugins/installed_plugins.json`` records each installed
    plugin's live ``installPath``; that is the one place this can be read
    reliably; the wider ``plugins/cache`` and ``plugins/marketplaces`` trees
    hold every version ever fetched (including a ``.trash`` of superseded
    ones) and are never scanned directly. A missing or unparseable manifest,
    or one whose "plugins" key isn't a map, is reported as not counted rather
    than guessed at; entries within it that are malformed are skipped
    individually so one bad entry does not lose the rest.

    A ``project``- or ``local``-scoped entry only applies to *this* project
    (its ``projectPath`` must resolve to ``root``); a ``user``-scoped or
    unmarked entry always applies. A plugin explicitly disabled in
    ``enabledPlugins`` (user ``settings.json``, overridden by the project's
    own ``settings.json``, overridden by its ``settings.local.json``) is
    skipped entirely. Every ``installPath`` must resolve, following symlinks,
    to somewhere inside ``~/.claude/plugins`` itself; a UNC path
    (``\\\\host\\share`` or ``//host/share``) is rejected by its literal text
    before any filesystem access (resolving or even stat-ing an unreachable
    network path can hang or error slowly), and anything rejected is listed
    under ``skipped_install_paths`` rather than silently dropped.
    """
    manifest_path = Path(home) / '.claude' / 'plugins' / 'installed_plugins.json'
    base = {'path': str(manifest_path)}
    try:
        raw = manifest_path.read_text(encoding='utf-8-sig')
    except OSError:
        return {**base, 'exists': False, 'counted': False,
                'reason': 'installed_plugins.json not found', 'skipped_install_paths': [], **dict(EMPTY_SCAN)}
    try:
        data = json.loads(raw)
    except ValueError:
        return {**base, 'exists': True, 'counted': False,
                'reason': 'installed_plugins.json is not valid JSON', 'skipped_install_paths': [],
                **dict(EMPTY_SCAN)}
    plugins = data.get('plugins') if isinstance(data, dict) else None
    if not isinstance(plugins, dict):
        return {**base, 'exists': True, 'counted': False,
                'reason': 'installed_plugins.json has no "plugins" object', 'skipped_install_paths': [],
                **dict(EMPTY_SCAN)}
    plugins_root = (Path(home) / '.claude' / 'plugins').resolve()
    project_root = Path(root).resolve()
    enabled = _effective_enabled_plugins(home, root)
    seen_install_paths = set()
    skipped_install_paths = []
    scans = []
    for plugin_key, entries in plugins.items():
        if enabled.get(plugin_key) is False:
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get('scope') in ('project', 'local'):
                project_path = entry.get('projectPath')
                if not isinstance(project_path, str) or not project_path:
                    continue
                try:
                    if Path(project_path).resolve() != project_root:
                        continue
                except OSError:
                    continue
            install_path = entry.get('installPath')
            if not isinstance(install_path, str) or not install_path:
                continue
            resolved, reason = _confine_to_plugins_root(install_path, plugins_root)
            if resolved is None:
                skipped_install_paths.append({'installPath': install_path, 'reason': reason})
                continue
            if resolved in seen_install_paths:
                continue
            seen_install_paths.add(resolved)
            scans.append(_scan_root(resolved / 'skills'))
    return {**base, 'exists': True, 'counted': True, 'reason': None,
            'skipped_install_paths': skipped_install_paths, **_aggregate_scans(scans)}


def thresholds(policy=None):
    """Effective thresholds: documented defaults, overridden per key by policy.

    Applied independently to each host's own combined total (a project with
    two very different host session loads gets two independent comparisons,
    not one summed check).
    """
    configured = ((policy or {}).get('skills') or {}).get('inventory_thresholds') or {}
    merged = dict(DEFAULT_THRESHOLDS)
    for key in DEFAULT_THRESHOLDS:
        if key in configured:
            merged[key] = configured[key]
    return merged


def inventory(root, policy=None, home=None, codex_home=None):
    """Full inventory: per-root and per-host-session-load counts/bytes, cross-host mirrors,
    and same-host duplicate skill names.

    Always returns the full numbers, even below threshold, so C4's pruning
    pass can use them regardless of whether doctor warned.
    """
    home_dir = Path(home) if home is not None else home_root()
    directory_roots = resolve_roots(root, home_dir, codex_home)
    per_root = {name: _scan_root(path) for name, path in directory_roots.items()}
    per_root['claude_plugins'] = _plugin_skills_claude(home_dir, root)

    hosts = {}
    for host, root_names in HOST_ROOTS.items():
        owners = {}
        for root_name in root_names:
            for name in per_root[root_name]['names']:
                owners.setdefault(name, []).append(root_name)
        duplicates = {name: sorted(where) for name, where in owners.items() if len(where) > 1}
        combined = {
            'skill_count': sum(per_root[r]['skill_count'] for r in root_names),
            'description_bytes': sum(per_root[r]['description_bytes'] for r in root_names),
            'max_description_bytes': max((per_root[r]['max_description_bytes'] for r in root_names), default=0),
            'skill_md_bytes': sum(per_root[r]['skill_md_bytes'] for r in root_names),
        }
        hosts[host] = {'roots': list(root_names), 'combined': combined, 'duplicates': duplicates}

    claude_names = {name for r in HOST_ROOTS['claude'] for name in per_root[r]['names']}
    codex_names = {name for r in HOST_ROOTS['codex'] for name in per_root[r]['names']}
    mirrors = {}
    for name in sorted(claude_names & codex_names):
        mirrors[name] = {
            'claude': sorted(r for r in HOST_ROOTS['claude'] if name in per_root[r]['names']),
            'codex': sorted(r for r in HOST_ROOTS['codex'] if name in per_root[r]['names']),
        }

    roots_public = {name: {k: v for k, v in data.items() if k != 'names'} for name, data in per_root.items()}
    return {
        'roots': roots_public,
        'hosts': hosts,
        'mirrors': mirrors,
        'thresholds': thresholds(policy),
    }


def warnings(inv):
    """SKILL_INVENTORY_LARGE for each host whose own combined count or description
    bytes exceed threshold; empty when neither host is over."""
    limits = inv['thresholds']
    messages = []
    for host in sorted(inv['hosts']):
        combined = inv['hosts'][host]['combined']
        over_count = combined['skill_count'] > limits['skill_count']
        over_bytes = combined['description_bytes'] > limits['description_bytes']
        if not (over_count or over_bytes):
            continue
        messages.append(
            'SKILL_INVENTORY_LARGE: {host} host session load is {count} skills ({count_limit} threshold), '
            '{bytes} bytes of frontmatter descriptions ({bytes_limit} threshold) across {roots}; review with '
            'the C4 pruning pass (owner judgement, no telemetry-based "never invoked" signal yet)'.format(
                host=host, count=combined['skill_count'], count_limit=limits['skill_count'],
                bytes=combined['description_bytes'], bytes_limit=limits['description_bytes'],
                roots=', '.join(inv['hosts'][host]['roots'])))
    return messages
