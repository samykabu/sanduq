#!/usr/bin/env python3
"""Keep every installed Spec Kit integration (host) complete, and switch the default one.

Spec Kit registers extension commands and skills only for the default
integration. A reinstall (``specify extension add --force``) therefore removes
the other installed host's skills, and ``specify integration use <host>``
regenerates the new default's skills from upstream sources, including the
upstream Bridge skill that Sanduq replaces with a managed alias. This module
re-registers every installed host through the public ``integration use``
command, restoring the recorded default afterwards, and verifies the result.
"""
from __future__ import annotations

import json
import os
import re
import tomllib
import uuid
from pathlib import Path

import yaml

from workflow import (WORKFLOW_SCRIPT, WorkflowError, active_host, doctor, ensure_local_excludes, load_policy,
                      locked, package_digest, read, registry, require, write)

# The skill folder each supported host reads.
HOST_SKILLS = {'codex': '.agents/skills', 'claude': '.claude/skills'}
# Extensions and presets whose commands Sanduq installs and so must keep on every host.
MANAGED_EXTENSIONS = ('workflow', 'illustrate', 'project', 'scope', 'pr', 'assure', 'user-manual')
MANAGED_PRESETS = ('workflow', 'scope-gate', 'scope-brainstorm')
SANDUQ = 'https://github.com/samykabu/sanduq'
PACKAGE = Path(__file__).resolve().parents[1]
OVERLAY_MARKER = '<!-- sanduq-workflow-managed:v1 -->'
# Model families, only to catch a model name configured for the wrong host.
MODEL_FAMILIES = {'claude': re.compile(r'^(?:claude|opus|sonnet|haiku)', re.I),
                  'codex': re.compile(r'^(?:gpt|codex|o\d)', re.I)}
INTEGRATION_FILES = ('.specify/integration.json', '.specify/init-options.json')
# Sanduq-owned skills that replace an upstream command of the same name, and the
# hashes of earlier content each may replace without it being a local edit.
ALIASES = {'speckit-scope': 'legacy-alias-hashes.json',
           'speckit-superpowers-bridge': 'legacy-bridge-alias-hashes.json'}
INSTALL_LOCK = '.specify/workflow/install-lock.json'
# Scope commands only its hooks call. Scope no longer lists them as skills (OMAR-09); an older Scope's
# rendered copies are still hidden from the Claude slash menu here.
HOOK_ONLY_SKILLS = tuple('speckit-scope-' + name for name in ('guard', 'bind', 'after-specify', 'plan-guard', 'reconcile'))
# Where each host reads project hooks, and the text that marks Sanduq's guard entry in them.
HOOK_FILES = {'claude': '.claude/settings.json', 'codex': '.codex/hooks.json'}
GUARD_MARK = 'workflow/hooks/guard.py'
CODEX_HOOK_APPROVAL = ('Codex runs project hooks only in a trusted project and after you approve them: open Codex here, '
                       'run /hooks and approve the Sanduq guard (.codex/hooks.json).')
ROLES = ('worker', 'reviewer')
ROLE_FILES = {'claude': '.claude/agents/sanduq-{}.md', 'codex': '.codex/agents/sanduq-{}.toml'}
ROLE_MARKER = 'sanduq-role:v1'


def aliases_enabled(root):
    """Whether the short aliases are installed: the recorded choice, else what an older install left."""
    lock = read(root / INSTALL_LOCK, {})
    lock = lock if isinstance(lock, dict) else {}
    return lock['with_aliases'] if isinstance(lock.get('with_aliases'), bool) else bool(lock.get('aliases'))


def alias_wanted(name, destination, enabled, registered):
    """An upstream Bridge, once registered, is always replaced: it is an executor that bypasses the workflow."""
    if name == 'speckit-superpowers-bridge':
        return name in registered or (enabled and destination.exists())
    return enabled


def skill_name(command):
    return command.replace('.', '-')


def skill_path(root, host, command):
    return root / HOST_SKILLS[host] / skill_name(command) / 'SKILL.md'


def installed_hosts(root):
    """Supported installed integrations, the default first."""
    integration = read(root / '.specify/integration.json', {})
    listed = integration.get('installed_integrations') if isinstance(integration, dict) else None
    listed = listed if isinstance(listed, list) else []
    default = active_host(root)
    hosts = [host for host in listed if host in HOST_SKILLS]
    if default in HOST_SKILLS and default not in hosts:
        hosts.insert(0, default)
    if default in hosts:
        hosts.remove(default); hosts.insert(0, default)
    return hosts


def unsupported_hosts(root):
    integration = read(root / '.specify/integration.json', {})
    listed = integration.get('installed_integrations') if isinstance(integration, dict) else None
    return [host for host in (listed if isinstance(listed, list) else []) if host not in HOST_SKILLS]


def manifest(path, section):
    try:
        document = yaml.safe_load(path.read_text(encoding='utf-8-sig')) or {}
    except (OSError, yaml.YAMLError):
        return None
    return document if isinstance(document, dict) and isinstance(document.get(section), dict) else None


def managed_commands(root):
    """Commands every installed, enabled Sanduq extension provides."""
    registered = registry(root)
    commands = {}
    for name in MANAGED_EXTENSIONS:
        entry = registered.get(name) or {}
        if entry.get('enabled') is not True:
            continue
        document = manifest(root / '.specify/extensions' / name / 'extension.yml', 'extension')
        if not document or str(document['extension'].get('repository', '')).rstrip('/') != SANDUQ:
            continue
        names = []
        for item in (document.get('provides') or {}).get('commands') or []:
            if isinstance(item, dict) and isinstance(item.get('name'), str):
                names.append(item['name'])
                names += [alias for alias in item.get('aliases') or [] if isinstance(alias, str)]
        commands[name] = names
    return commands


def preset_commands(root):
    commands = []
    for name in MANAGED_PRESETS:
        document = manifest(root / '.specify/presets' / name / 'preset.yml', 'preset')
        for item in ((document or {}).get('provides') or {}).get('templates') or []:
            if isinstance(item, dict) and item.get('type') == 'command' and isinstance(item.get('name'), str):
                commands.append(item['name'])
    return sorted(set(commands))


def skill_report(root, hosts=None):
    """Which managed skills each host lacks.

    Every command of an installed Sanduq extension must exist on every host. A
    Sanduq preset overlay replaces a command only where its base command is
    installed, so its skills must match across hosts: present on one host means
    present, and overlaid, on all of them.
    """
    hosts = installed_hosts(root) if hosts is None else hosts
    missing = {host: set() for host in hosts}
    for commands in managed_commands(root).values():
        for command in commands:
            for host in hosts:
                if not skill_path(root, host, command).is_file():
                    missing[host].add(skill_name(command))
    stale = {host: set() for host in hosts}
    for command in preset_commands(root):
        paths = {host: skill_path(root, host, command) for host in hosts}
        present = {host for host, path in paths.items() if path.is_file()}
        if not present:
            continue
        overlaid = {host for host in present
                    if OVERLAY_MARKER in paths[host].read_text(encoding='utf-8-sig', errors='replace')}
        for host in hosts:
            if host not in present:
                missing[host].add(skill_name(command))
            elif overlaid and host not in overlaid:
                stale[host].add(skill_name(command))
    return {'hosts': hosts,
            'missing': {host: sorted(names) for host, names in missing.items() if names},
            'overlay_missing': {host: sorted(names) for host, names in stale.items() if names}}


def skill_errors(report):
    errors = ['HOST_SKILLS_MISSING: ' + host + ' (' + HOST_SKILLS[host] + '): ' + ', '.join(names)
              for host, names in report['missing'].items()]
    errors += ['HOST_OVERLAY_MISSING: ' + host + ' (' + HOST_SKILLS[host] + '): ' + ', '.join(names)
               for host, names in report['overlay_missing'].items()]
    return errors


def alias_sources(package_root):
    # A package ships SKILL.md; a source checkout stores it as SKILL.ext.md (see package.py).
    def source(name):
        path = package_root / 'skills' / name / 'SKILL.md'
        return path if path.is_file() else path.with_name('SKILL.ext.md')
    return {name: source(name).read_bytes() for name in ALIASES}


def alias_errors(root, package_root, hosts=None, enabled=None):
    """Managed aliases that are not the packaged Sanduq content on every host folder."""
    hosts = installed_hosts(root) if hosts is None else hosts
    enabled = aliases_enabled(root) if enabled is None else enabled
    registered = registry(root)
    errors = []
    for name, source in alias_sources(package_root).items():
        for host in hosts:
            skills = root / HOST_SKILLS[host]
            if not skills.is_dir():
                continue
            destination = skills / name / 'SKILL.md'
            if not alias_wanted(name, destination, enabled, registered):
                continue
            if (not destination.is_file() or destination.is_symlink() or
                    destination.read_bytes().replace(b'\r\n', b'\n') != source.replace(b'\r\n', b'\n')):
                errors.append('ALIAS_NOT_RESTORED: ' + destination.relative_to(root).as_posix())
    return errors


def register_hosts(root, runner, log, default, hosts, only=None):
    """Register the managed extensions and presets for every installed host.

    ``specify integration use`` is the public command that registers enabled
    extensions and presets for a host, and it does so only by making that host
    the default. Each other host is selected in turn, then the recorded default
    is selected again and its integration files are put back byte for byte.
    ``only`` limits the other hosts visited (the ones found incomplete).
    """
    others = [host for host in hosts if host != default and (only is None or host in only)]
    if not others:
        return []
    saved = {name: (root / name).read_bytes() for name in INTEGRATION_FILES if (root / name).is_file()}
    for host in others:
        runner(root, ['specify', 'integration', 'use', host], log)
    runner(root, ['specify', 'integration', 'use', default], log)
    require(active_host(root) == default, 'HOST_DEFAULT_RESTORE_FAILED: expected ' + default +
            ', found ' + str(active_host(root)))
    for name, content in saved.items():
        (root / name).write_bytes(content)
    return others


def with_flag(text, key='user-invocable', value='false'):
    """``text`` with ``key: value`` in its YAML frontmatter; unchanged when already so or without frontmatter."""
    newline = '\r\n' if text.split('\n', 1)[0].endswith('\r') else '\n'
    lines = text.split(newline)
    fences = [index for index, line in enumerate(lines) if line.strip() == '---']
    if len(fences) < 2 or fences[0] != 0:
        return text
    end = fences[1]
    wanted = key + ': ' + value
    for index in range(1, end):
        if re.match(re.escape(key) + r'\s*:', lines[index]):
            if lines[index].strip() == wanted:
                return text
            lines[index] = wanted
            return newline.join(lines)
    return newline.join(lines[:end] + [wanted] + lines[end:])


def hide_hook_skills(root):
    """Mark Scope's hook-only commands ``user-invocable: false`` on Claude, after every Spec Kit render."""
    changed = []
    for name in HOOK_ONLY_SKILLS:
        path = root / HOST_SKILLS['claude'] / name / 'SKILL.md'
        if not path.is_file() or path.is_symlink():
            continue
        text = path.read_bytes().decode('utf-8')
        updated = with_flag(text)
        if updated != text:
            path.write_bytes(updated.encode('utf-8'))
            changed.append(path.relative_to(root).as_posix())
    return changed


def python_name(os_name=None):
    """Windows' python3 is often the Store stub; elsewhere python may not exist."""
    return 'python' if (os_name or os.name) == 'nt' else 'python3'


def guard_hooks(package_root, os_name=None):
    """The packaged guard hook entries, with {python} rendered for this platform."""
    document = json.loads((package_root / 'hooks/hooks.json').read_text(encoding='utf-8'))
    for groups in document['hooks'].values():
        for group in groups:
            for hook in group['hooks']:
                hook['command'] = hook['command'].replace('{python}', python_name(os_name))
    return document['hooks']


def is_guard(handler):
    return isinstance(handler, dict) and GUARD_MARK in str(handler.get('command', ''))


def register_guard(root, host, package_root):
    """Merge the guard into the host's project hook file, replacing only an earlier guard entry."""
    path = root / HOOK_FILES[host]
    raw = path.read_text(encoding='utf-8-sig') if path.is_file() else ''
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        data = None
    require(isinstance(data, dict) and isinstance(data.get('hooks', {}), dict),
            'HOOK_SETTINGS_INVALID: ' + HOOK_FILES[host] + ' is not a JSON object with a "hooks" object; fix it first')
    before = json.dumps(data, sort_keys=True)
    hooks = data.setdefault('hooks', {})
    for event, groups in guard_hooks(package_root).items():
        kept = []
        for group in hooks.get(event) if isinstance(hooks.get(event), list) else []:
            inner = group.get('hooks') if isinstance(group, dict) else None
            if isinstance(inner, list) and any(is_guard(h) for h in inner):
                inner = [h for h in inner if not is_guard(h)]
                if not inner:
                    continue
                group = {**group, 'hooks': inner}
            kept.append(group)
        hooks[event] = kept + groups
    if json.dumps(data, sort_keys=True) == before:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    return True


def render_role(role, host, model=None):
    """One role definition as the host's custom-agent file."""
    source = '.specify/extensions/workflow/assets/roles/' + role['name'].removeprefix('sanduq-') + '.yml'
    note = ROLE_MARKER + ' generated from ' + source + ' by the workflow installer; local edits are replaced'
    from delegate_dispatch import NO_DISPATCHER_COMMANDS  # the one source of the forbidden dispatcher commands
    instructions = role['instructions'].strip().replace('{no_dispatcher_commands}', NO_DISPATCHER_COMMANDS.strip()) + '\n'
    if host == 'claude':
        head = ['---', 'name: ' + role['name'], 'description: ' + json.dumps(role['description'], ensure_ascii=False),
                'tools: ' + ', '.join(role['tools'])] + (['model: ' + model] if model else []) + ['---']
        return '\n'.join(head) + '\n\n<!-- ' + note + ' -->\n\n' + instructions
    # A TOML literal string keeps the text readable; JSON string escapes are valid TOML otherwise.
    body = "'''\n" + instructions + "'''" if "'''" not in instructions else json.dumps(instructions, ensure_ascii=False)
    lines = ['# ' + note, 'name = ' + json.dumps(role['name']),
             'description = ' + json.dumps(role['description'], ensure_ascii=False)]
    lines += ['model = ' + json.dumps(model)] if model else []
    return '\n'.join(lines + ['developer_instructions = ' + body]) + '\n'


def load_role(package_root, name):
    return yaml.safe_load((package_root / 'assets/roles' / (name + '.yml')).read_text(encoding='utf-8'))


def role_models(policy, host, package_root):
    """tier -> model for each role, pinned only when delegation is enabled (its routes then name the tiers, SAMY-03);
    otherwise a role inherits the session's model."""
    delegation = (policy or {}).get('delegation') or {}
    if not delegation.get('enabled'):
        return {}
    models = (delegation.get('models') or {}).get(host) or {}
    tiers = (load_role(package_root, name)['model_tier'] for name in ROLES)
    return {tier: models[tier] for tier in tiers if tier in models}


def role_model(text, host):
    """The model line of a rendered role file, or None."""
    if host == 'codex':
        try:
            return tomllib.loads(text).get('model')
        except tomllib.TOMLDecodeError:
            return '<invalid TOML>'  # doctor reports the file as stale instead of crashing
    match = re.search(r'^model: (.+)$', text.split('\n---', 1)[0], re.M)
    return match.group(1).strip() if match else None


def install_roles(root, host, package_root, policy=None):
    """Write each role file Sanduq owns; a same-named file without the marker is the user's and is left alone.
    A model is pinned as role_models decides."""
    models = role_models(policy, host, package_root)
    written, skipped = [], []
    for name in ROLES:
        role = load_role(package_root, name)
        path = root / ROLE_FILES[host].format(name)
        relative = path.relative_to(root).as_posix()
        current = path.read_text(encoding='utf-8-sig') if path.is_file() else None
        if current is not None and ROLE_MARKER not in current:
            skipped.append(relative)
            continue
        content = render_role(role, host, models.get(role['model_tier']))
        if current != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
            written.append(relative)
    return written, skipped


def role_file_warnings(root, policy, package_root=None):
    """ROLE_FILES_STALE (AHMED-19) when the default host's role files, or the models install-lock.json records they
    were rendered with, differ from the models .specify/workflow.yml now pins."""
    host = active_host(root)
    if host not in ROLE_FILES:
        return []
    package_root = package_root or PACKAGE
    expected = role_models(policy, host, package_root)
    lock = read(root / INSTALL_LOCK, {})
    stale = [INSTALL_LOCK] if (isinstance(lock, dict) and isinstance(lock.get('role_models'), dict)
                               and lock['role_models'].get(host, {}) != expected) else []
    for name in ROLES:
        path = root / ROLE_FILES[host].format(name)
        text = path.read_text(encoding='utf-8-sig') if path.is_file() else ''
        if ROLE_MARKER in text and role_model(text, host) != expected.get(load_role(package_root, name)['model_tier']):
            stale.append(path.relative_to(root).as_posix())
    return (['ROLE_FILES_STALE: ' + ', '.join(stale) + ' do not match the ' + host + ' delegation models in '
             '.specify/workflow.yml; run "python .specify/extensions/workflow/scripts/reconcile.py --apply"']
            if stale else [])


def apply_host_files(root, policy=None, package_root=None, hosts=None):
    """Re-apply what Sanduq adds to each installed host beside its skills: hidden hook-only
    skills, the guard hook and the role agents. Idempotent; install, host switch and reconcile run it."""
    package_root = package_root or PACKAGE
    hosts = installed_hosts(root) if hosts is None else hosts
    result = {'hidden_skills': hide_hook_skills(root) if 'claude' in hosts else [],
              'hooks_registered': [], 'roles_written': [], 'roles_skipped': [], 'role_models': {}}
    for host in hosts:
        if register_guard(root, host, package_root):
            result['hooks_registered'].append(HOOK_FILES[host])
        written, skipped = install_roles(root, host, package_root, policy)
        result['role_models'][host] = role_models(policy, host, package_root)
        result['roles_written'] += written
        result['roles_skipped'] += skipped
    lock = read(root / INSTALL_LOCK, None)
    if isinstance(lock, dict) and lock.get('role_models') != result['role_models']:
        write(root / INSTALL_LOCK, {**lock, 'role_models': result['role_models']})  # what doctor's ROLE_FILES_STALE compares
    if 'codex' in hosts:
        result['codex_hook_approval'] = CODEX_HOOK_APPROVAL
    return result


def model_family(model):
    for host, pattern in MODEL_FAMILIES.items():
        if isinstance(model, str) and pattern.match(model.strip()):
            return host
    return None


def delegation_findings(root, target, current=None):
    """What the delegation policy must change before ``target`` can be the selected host.

    Reads the raw policy so a section that no longer validates is reported by
    key rather than as one opaque error. Nothing is rewritten.
    """
    from delegation import MODEL_PROFILES
    path = root / '.specify/workflow.yml'
    try:
        raw = yaml.safe_load(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
    except (OSError, yaml.YAMLError) as exc:
        return {'enabled': None, 'required_changes': ['.specify/workflow.yml does not parse: ' + str(exc)],
                'advisories': [], 'notes': []}
    config = (raw or {}).get('delegation') if isinstance(raw, dict) else None
    if not isinstance(config, dict):
        return {'enabled': False, 'required_changes': [], 'advisories': [],
                'notes': ['No delegation section: delegation is off and needs no change for ' + target + '.']}
    enabled = config.get('enabled') is True
    changes, notes = [], []
    other = 'claude' if target == 'codex' else 'codex'
    models = config.get('models') if isinstance(config.get('models'), dict) else {}
    tiers = models.get(target)
    if not isinstance(tiers, dict):
        changes.append('delegation.models.' + target + ' is missing: add ' + ', '.join(MODEL_PROFILES) +
                       ' model names for ' + target)
    else:
        for tier in MODEL_PROFILES:
            value = tiers.get(tier)
            key = 'delegation.models.' + target + '.' + tier
            if not isinstance(value, str) or not value.strip():
                changes.append(key + ' is missing: set the ' + target + ' model for the ' + tier + ' tier')
            elif model_family(value) == other:
                changes.append(key + ' is "' + value + '", a ' + other + ' model: set a ' + target + ' model')
    routes = config.get('routes') if isinstance(config.get('routes'), dict) else {}
    overrides = config.get('overrides') if isinstance(config.get('overrides'), dict) else {}
    for prefix, table in (('delegation.routes.', routes), ('delegation.overrides.', overrides)):
        for name, route in table.items():
            if not isinstance(route, dict):
                continue
            candidates = [('preferred', route.get('preferred'))]
            candidates += [('fallbacks[' + str(i) + ']', item) for i, item in enumerate(route.get('fallbacks') or [])]
            for label, item in candidates:
                if not isinstance(item, dict):
                    continue
                key = prefix + str(name) + '.' + label
                if 'tier' in item and item['tier'] not in MODEL_PROFILES:
                    changes.append(key + '.tier "' + str(item['tier']) + '" is not a configured tier')
                harness = item.get('harness')
                if harness == 'selected' and model_family(item.get('model')) == other:
                    changes.append(key + '.model "' + item['model'] + '" is a ' + other + ' model but the route '
                                   'follows the selected host: use a tier or a ' + target + ' model')
                if harness in HOST_SKILLS and harness != target:
                    notes.append(key + ' pins harness ' + harness + ': it keeps delegating to ' + harness +
                                 ' after the switch (change it to "selected" to follow ' + target + ')')
    if enabled:
        notes.append('delegation.enabled: the delegate-task skill is installed for ' + target +
                     ' at the configured install_scope during the switch')
    return {'enabled': enabled, 'required_changes': changes if enabled else [],
            'advisories': [] if enabled else changes, 'notes': notes}


def checkpoints(root):
    found = []
    for path in sorted((root / 'specs').glob('*/workflow/checkpoint.json')):
        state = read(path, {})
        if isinstance(state, dict):
            found.append((path.parent.parent.relative_to(root).as_posix(), state))
    return found


def migrations(root, digest, changed, reason, previous=None):
    """The checkpoints whose recorded dependency digest will not match ``digest``.

    ``already_stale`` marks a checkpoint that did not match ``previous`` (the
    digest before the switch) either, so it needed ``migrate`` regardless.
    """
    entries = []
    for feature, state in checkpoints(root):
        recorded = state.get('dependency_digest')
        if not changed and recorded == digest:
            continue
        entries.append({'feature': feature, 'branch': state.get('branch'),
                        'active_claim': bool(state.get('active')),
                        'already_stale': recorded != (digest if previous is None else previous),
                        'commands': ['git switch ' + str(state.get('branch')),
                                     WORKFLOW_SCRIPT + ' migrate --feature ' + feature + ' --preview',
                                     WORKFLOW_SCRIPT + ' migrate --feature ' + feature + ' --reason "' + reason + '"']})
    return entries


def status(root, package_root=None):
    root = root.resolve()
    package_root = package_root or PACKAGE
    hosts = installed_hosts(root)
    report = skill_report(root, hosts)
    aliases = alias_errors(root, package_root, hosts)
    return {'default': active_host(root), 'installed_hosts': hosts, 'unsupported_hosts': unsupported_hosts(root),
            'skills': report, 'aliases_not_restored': aliases, 'dependency_digest': package_digest(root),
            'ok': not skill_errors(report) and not aliases}


def switch(root, target, preview=False, runner=None, package_root=None, replace_unrecognized_aliases=False):
    """Make ``target`` the default host without losing any host's managed skills."""
    from install import (command, delegation_preflight, install_aliases, alias_edit_errors, prune_backups, restore,
                         review_aliases, snapshot, mark_in_progress, clear_in_progress)
    from reconcile import reconcile
    runner = runner or command
    package_root = package_root or PACKAGE
    root = root.resolve()
    require(target in HOST_SKILLS, 'HOST_UNSUPPORTED: ' + str(target))
    current = active_host(root)
    hosts = installed_hosts(root)
    blockers = []
    if target not in hosts:
        blockers.append('HOST_NOT_INSTALLED: ' + target + ' is not in .specify/integration.json '
                        'installed_integrations; run "specify integration install ' + target + '" first')
    try:
        policy = load_policy(root)
    except WorkflowError as exc:
        policy = None
        blockers.append(str(exc))
    delegation = delegation_findings(root, target, current)
    blockers += ['DELEGATION_POLICY_NOT_VALID_FOR_HOST: ' + item for item in delegation['required_changes']]
    for feature, state in checkpoints(root):
        if state.get('active'):
            blockers.append('ACTIVE_STAGE_MUST_BE_RESOLVED: ' + feature)
    if read(root / '.specify/superpowers-handoff.json', {}).get('status') in ('executing', 'blocked'):
        blockers.append('LEGACY_EXECUTOR_OWNS_FEATURE: reconcile its actual work before switching hosts')
    # Judged before any Spec Kit command runs; Spec Kit's own render counts only
    # when the whole file is exactly what it generates from the current sources.
    enabled = aliases_enabled(root)
    review = review_aliases(root, package_root, runner, enabled=enabled)
    if not replace_unrecognized_aliases:
        blockers += alias_edit_errors(root, package_root, review=review)
    upgrade = read(root / '.specify/workflow/runtime/upgrade.lock', {})
    if upgrade:
        blockers.append('WORKFLOW_UPGRADE_IN_PROGRESS')
    before_report = skill_report(root, hosts)
    incomplete = [host for host in hosts if host != target and
                  (host in before_report['missing'] or host in before_report['overlay_missing'])]
    commands = [['specify', 'integration', 'use', target]]
    if incomplete:
        commands += [['specify', 'integration', 'use', host] for host in incomplete]
        commands.append(['specify', 'integration', 'use', target])
    digest_before = package_digest(root)
    repairs = bool(skill_errors(before_report) or alias_errors(root, package_root, hosts))
    reason = ('Host switched from ' + str(current) + ' to ' + target if current != target
              else 'Host ' + target + ' re-registered')
    predicted = current != target or repairs
    plan = {'preview': preview, 'from': current, 'to': target, 'installed_hosts': hosts,
            'unsupported_hosts': unsupported_hosts(root), 'commands': commands,
            'skills_before': before_report,
            'aliases_to_restore': [path for path in alias_errors(root, package_root, hosts)],
            'aliases_generated_by_spec_kit': sorted(review['generated']),
            'aliases_unrecognized': sorted(review['unrecognized']),
            'replace_unrecognized_aliases_requested': replace_unrecognized_aliases,
            'delegation': delegation,
            'dependency_digest': {'before': digest_before, 'will_change': predicted,
                                  'why': ('.specify/integration.json and .specify/init-options.json are part of '
                                          'the package digest' if current != target else
                                          'skills are re-registered' if repairs else 'nothing changes')},
            'checkpoints_to_migrate': migrations(root, digest_before, predicted, reason),
            'blockers': blockers, 'can_apply': not blockers}
    if preview:
        return plan
    require(not blockers, 'HOST_SWITCH_BLOCKED: ' + '; '.join(blockers))
    doctor_before = doctor(root, policy)['errors']
    ensure_local_excludes(root)
    with locked(root / '.specify/workflow/runtime/dispatch.lock'), locked(root / '.specify/workflow/runtime/install.lock'):
        require(not read(root / '.specify/workflow/runtime/upgrade.lock', {}), 'WORKFLOW_UPGRADE_IN_PROGRESS')
        for feature, state in checkpoints(root):
            require(not state.get('active'), 'ACTIVE_STAGE_MUST_BE_RESOLVED: ' + feature)
        delegation_preflight(root)
        backup = root / '.specify/workflow/backups/hosts' / uuid.uuid4().hex
        before = snapshot(root, backup)
        mark_in_progress(root, 'host', backup)
        log = []
        try:
            runner(root, ['specify', 'integration', 'use', target], log)
            require(active_host(root) == target, 'HOST_SWITCH_FAILED: the default is ' + str(active_host(root)))
            after_use = skill_report(root, hosts)
            others = [host for host in hosts if host != target and
                      (host in after_use['missing'] or host in after_use['overlay_missing'])]
            registered = register_hosts(root, runner, log, target, hosts, only=others)
            replaced = []
            aliases = install_aliases(root, package_root, baseline=before, generated=review['generated'],
                                      replace_unrecognized=replace_unrecognized_aliases, backup=backup,
                                      replaced=replaced, enabled=enabled)
            reconcile(root, apply=True)
            if policy['delegation']['enabled']:
                from delegation import doctor as delegation_doctor, health_error
                health = delegation_doctor(root, target, install=True, scope=policy['delegation']['install_scope'])
                require(health['ok'], health_error(health))
            errors = skill_errors(skill_report(root, hosts)) + alias_errors(root, package_root, hosts)
            require(not errors, '; '.join(errors))
            health = doctor(root, policy)
            introduced = [error for error in health['errors'] if error not in doctor_before]
            require(not introduced, 'DOCTOR_FAILED_AFTER_SWITCH: ' + '; '.join(introduced))
            digest_after = package_digest(root)
            lock_path = root / '.specify/workflow/install-lock.json'
            lock = read(lock_path, None)
            if isinstance(lock, dict):
                lock.update(host=target, aliases=aliases, dependency_digest=digest_after)
                write(lock_path, lock)
            result = {**plan, 'preview': False, 'applied': True, 'backup': str(backup),
                      'executed': [entry['args'] for entry in log],
                      're_registered_hosts': registered, 'aliases_restored': sorted(aliases),
                      'replaced_unrecognized_aliases': replaced,
                      'doctor': health,
                      'dependency_digest': {'before': digest_before, 'after': digest_after,
                                            'changed': digest_after != digest_before},
                      'checkpoints_to_migrate': migrations(root, digest_after, False, reason, digest_before)}
            if result['checkpoints_to_migrate']:  # F11: name the step a user would otherwise skip
                result['next'] = ('Migrate each feature in checkpoints_to_migrate before continuing it, for example: '
                                  + '; '.join(result['checkpoints_to_migrate'][0]['commands']))
            write(backup / 'result.json', {'ok': True, 'commands': log})
            result['backups'] = prune_backups(root)
            clear_in_progress(root)
            return result
        except BaseException as exc:  # Ctrl-C and SystemExit restore too, then re-raise as they are (AHMED-09)
            from install import managed_files
            write(backup / 'result.json', {'ok': False, 'error': str(exc) or type(exc).__name__, 'commands': log})
            restore(root, before, managed_files(root))
            clear_in_progress(root)
            if not isinstance(exc, Exception): raise
            raise WorkflowError('HOST_SWITCH_ROLLED_BACK: ' + str(exc) + '; backup: ' + str(backup)) from exc
