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

import re
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
    return {name: (package_root / 'skills' / name / 'SKILL.md').read_bytes() for name in ALIASES}


def alias_errors(root, package_root, hosts=None):
    """Managed aliases that are not the packaged Sanduq content on every host folder."""
    hosts = installed_hosts(root) if hosts is None else hosts
    registered = registry(root)
    errors = []
    for name, source in alias_sources(package_root).items():
        for host in hosts:
            skills = root / HOST_SKILLS[host]
            if not skills.is_dir():
                continue
            destination = skills / name / 'SKILL.md'
            if name == 'speckit-superpowers-bridge' and name not in registered and not destination.exists():
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


def switch(root, target, preview=False, runner=None, package_root=None):
    """Make ``target`` the default host without losing any host's managed skills."""
    from install import command, delegation_preflight, install_aliases, alias_edit_errors, restore, snapshot
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
    blockers += alias_edit_errors(root, package_root)
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
        log = []
        try:
            runner(root, ['specify', 'integration', 'use', target], log)
            require(active_host(root) == target, 'HOST_SWITCH_FAILED: the default is ' + str(active_host(root)))
            after_use = skill_report(root, hosts)
            others = [host for host in hosts if host != target and
                      (host in after_use['missing'] or host in after_use['overlay_missing'])]
            registered = register_hosts(root, runner, log, target, hosts, only=others)
            aliases = install_aliases(root, package_root, baseline=before)
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
                      'doctor': health,
                      'dependency_digest': {'before': digest_before, 'after': digest_after,
                                            'changed': digest_after != digest_before},
                      'checkpoints_to_migrate': migrations(root, digest_after, False, reason, digest_before)}
            write(backup / 'result.json', {'ok': True, 'commands': log})
            return result
        except Exception as exc:
            from install import managed_files
            write(backup / 'result.json', {'ok': False, 'error': str(exc), 'commands': log})
            restore(root, before, managed_files(root))
            raise WorkflowError('HOST_SWITCH_ROLLED_BACK: ' + str(exc) + '; backup: ' + str(backup)) from exc
