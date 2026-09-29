#!/usr/bin/env python3
"""Skill inventory across every root a host reads: the user's home skills
folder and each project-local root.

`workflow.py doctor` surfaces this so C4 (skill pruning) has raw counts and
frontmatter-description byte totals to reason from; this module never decides
what to prune, and "never invoked" stays out of scope until a telemetry
source and window exist (see the plan, package B10).

A skill root is flat: ``<root>/<skill-name>/SKILL.md`` (matching
``workflow.command_exists``), so scanning is a single directory level per
root; no recursive descent means no symlink-loop risk from a skill's own
subfolders. A same-named entry that is a symlink or junction to elsewhere is
still resolved and de-duplicated so it is never counted twice.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

# Combined-across-roots defaults; see extensions/workflow/README.md ("Skill
# inventory") for the reasoning. A project may override either key under
# policy['skills']['inventory_thresholds'].
DEFAULT_THRESHOLDS = {
    'skill_count': 150,
    'description_bytes': 20480,  # 20 KiB of combined frontmatter `description:` text
}

# Root name -> the relative path it inventories.
HOME_SKILLS_RELATIVE = Path('.claude/skills')
PROJECT_ROOTS = {
    'project_claude': Path('.claude/skills'),
    'project_agents': Path('.agents/skills'),
}


def home_root():
    """Portable resolution of the user's home directory.

    Windows and POSIX both fall back to ``Path.home()``; tests must never read
    the real machine's home directory, so set ``SANDUQ_HOME`` to override (the
    same shape as ``SANDUQ_CLAUDE_PROJECTS`` / ``SANDUQ_CODEX_SESSIONS`` in
    usage.py).
    """
    override = os.environ.get('SANDUQ_HOME')
    return Path(override) if override else Path.home()


def resolve_roots(root, home=None):
    """The three inventoried roots, keyed the same way in every result."""
    home_dir = Path(home) if home is not None else home_root()
    return {
        'home': home_dir / HOME_SKILLS_RELATIVE,
        **{name: root / relative for name, relative in PROJECT_ROOTS.items()},
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
    """One root's inventory: skill count, total/max description bytes, total SKILL.md bytes."""
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


def thresholds(policy=None):
    """Effective thresholds: documented defaults, overridden per key by policy."""
    configured = ((policy or {}).get('skills') or {}).get('inventory_thresholds') or {}
    merged = dict(DEFAULT_THRESHOLDS)
    for key in DEFAULT_THRESHOLDS:
        if key in configured:
            merged[key] = configured[key]
    return merged


def inventory(root, policy=None, home=None):
    """Full inventory: per-root counts/bytes, combined totals, and cross-root duplicates.

    Always returns the full numbers, even below threshold, so C4's pruning
    pass can use them regardless of whether doctor warned.
    """
    roots = resolve_roots(root, home)
    per_root = {name: _scan_root(path) for name, path in roots.items()}
    owners = {}
    for root_name, data in per_root.items():
        for skill_name in data['names']:
            owners.setdefault(skill_name, []).append(root_name)
    duplicates = {name: sorted(where) for name, where in owners.items() if len(where) > 1}
    combined = {
        'skill_count': sum(d['skill_count'] for d in per_root.values()),
        'description_bytes': sum(d['description_bytes'] for d in per_root.values()),
        'max_description_bytes': max((d['max_description_bytes'] for d in per_root.values()), default=0),
        'skill_md_bytes': sum(d['skill_md_bytes'] for d in per_root.values()),
    }
    for data in per_root.values():
        data.pop('names', None)
    return {
        'roots': per_root,
        'combined': combined,
        'duplicates': duplicates,
        'thresholds': thresholds(policy),
    }


def warning(inv):
    """SKILL_INVENTORY_LARGE when the combined count or description bytes exceed threshold, else None."""
    limits = inv['thresholds']
    combined = inv['combined']
    over_count = combined['skill_count'] > limits['skill_count']
    over_bytes = combined['description_bytes'] > limits['description_bytes']
    if not (over_count or over_bytes):
        return None
    return ('SKILL_INVENTORY_LARGE: {count} skills ({count_limit} threshold), {bytes} bytes of frontmatter '
            'descriptions ({bytes_limit} threshold) combined across home ~/.claude/skills, project .claude/skills '
            'and .agents/skills; review with the C4 pruning pass (owner judgement, no telemetry-based "never '
            'invoked" signal yet)').format(
        count=combined['skill_count'], count_limit=limits['skill_count'],
        bytes=combined['description_bytes'], bytes_limit=limits['description_bytes'])
