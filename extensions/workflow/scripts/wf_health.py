"""Installation health: registry, hosts, commands, the dependency digest and `doctor` with its cache."""
from __future__ import annotations

import json
import shutil
import sanduq_ci
import skill_inventory
import lean_policy
import execution_tools
import yaml
from datetime import datetime, timezone
from pathlib import Path
from sanduq_hash import eol_drift
from sanduq_remote import same_github_repository
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from wf_core import (RANGES, COMMANDS, LINT_COMMAND, DOCTOR_CACHE, DOCTOR_CACHE_SECONDS, DOCTOR_CACHE_FILES,
                     WORKFLOW_SCRIPT, WorkflowError, require, read, digest, write, inside, canonical_path, sanduq_fs)
from wf_identity import github_repository, require_shared_history
from wf_fingerprints import fingerprint_files
from wf_policy import stages


def registry(root):
    return read(root / '.specify/extensions/.registry', {}).get('extensions', {})


def compatible(root, name):
    entry = registry(root).get(name, {})
    try:
        return entry.get('enabled') is True and Version(entry['version']) in SpecifierSet(RANGES[name])
    except (KeyError, ValueError):
        return False


def upgrade_command(root):
    """The dependency-aware fix: upgrade.py at the installed Workflow version installs the versions its lock names.
    Before the first `install.py --apply` (no install lock yet) the fix is that install (AHMED-35)."""
    version = registry(root).get('workflow', {}).get('version')
    if not (root / '.specify/workflow/install-lock.json').is_file():
        return 'python .specify/extensions/workflow/scripts/install.py --apply', version
    if not version:
        manifest = root / '.specify/extensions/workflow/extension.yml'
        doc = yaml.safe_load(manifest.read_text(encoding='utf-8-sig')) if manifest.is_file() else {}
        version = ((doc or {}).get('extension') or {}).get('version')
    return ('python .specify/extensions/workflow/scripts/upgrade.py --version ' + str(version or '<workflow version>') +
            ' --apply'), version


def dependency_errors(root, needed, project=False):
    """DEPENDENCY_UNAVAILABLE for a needed extension that is missing, disabled or outside RANGES and, with
    `project`, for a needed or installed optional one older than the installed Workflow's dependencies.json."""
    lock = read(root / '.specify/extensions/workflow/dependencies.json', {}) if project else {}
    lock = lock if isinstance(lock, dict) else {}
    pins = dict(lock.get('optional') or {})
    for group in (lock.get('selected') or {}).values():
        pins.update(group or {})
    pins.update(lock.get('required') or {})
    installed = registry(root)
    names = list(needed) + [n for n in (lock.get('optional') or {}) if n not in needed and n in installed]
    command, workflow_version = upgrade_command(root)
    errors = []
    for name in names:
        entry = installed.get(name, {})
        have = entry.get('version') if entry.get('enabled') is True else None
        pin = pins.get(name)
        try:
            older = bool(pin) and have is not None and Version(have) < Version(pin)
        except ValueError:
            older = True
        if (name in needed and not compatible(root, name)) or older:
            required = (pin + ' (' + RANGES[name] + ')') if pin and name in RANGES else (pin or RANGES[name])
            errors.append('DEPENDENCY_UNAVAILABLE: ' + name + ' ' + (have + ' is installed' if have else 'is not installed or not enabled') +
                          '; Workflow ' + str(workflow_version or '') + (' ' if workflow_version else '') + 'requires ' + name + ' ' + required +
                          '; run "' + command + '"')
    return errors


def active_host(root):
    integration = read(root / '.specify/integration.json', {})
    options = read(root / '.specify/init-options.json', {})
    return integration.get('default_integration') or integration.get('integration') or options.get('integration') or options.get('ai')


def command_exists(root, command):
    name = command.replace('.', '-')
    host = active_host(root)
    if host == 'codex': return (root / '.agents/skills' / name / 'SKILL.md').is_file()
    if host == 'claude': return (root / '.claude/skills' / name / 'SKILL.md').is_file()
    return False


def package_digest(root):
    """Ignore install timestamps but detect versions, enablement and source drift."""
    entries = {key: {k: value.get(k) for k in ('version', 'enabled')} for key, value in registry(root).items()}
    paths = []
    for folder in (root / '.specify/extensions', root / '.specify/presets'):
        if folder.is_dir():
            paths += [p.relative_to(root).as_posix() for p in folder.rglob('*') if p.is_file()
                      and p.suffix in ('.py', '.md', '.yml')
                      and not any(part in ('state', '__pycache__', 'tests') for part in p.relative_to(folder).parts)]
    paths += [p.relative_to(root).as_posix() for p in (root / '.agents/skills').glob('speckit-*/SKILL.md')]
    paths += [p.relative_to(root).as_posix() for p in (root / '.claude/skills').glob('speckit-*/SKILL.md')]
    paths += ['.specify/integration.json', '.specify/init-options.json']
    return digest({'registrations': entries, 'sources': fingerprint_files(root, paths)})


def resolve_commands(root, policy, tier=None):
    commands = dict(COMMANDS)
    if tier in ('lite', 'standard'):
        commands['analyze'] = LINT_COMMAND  # a model analyze runs only when lint asks for one
    for stage, suffix, choice in [('clarify', 'brainstorm', policy['providers']['clarification']),
                                  ('tasks', 'tasks', policy['providers']['tasks']),
                                  ('execute', 'execute', policy['execution']['engine'])]:
        candidate = 'speckit.superspec.' + suffix
        available = compatible(root, 'superspec') and command_exists(root, candidate)
        if choice == 'superspec':
            require(available, 'REQUIRED_PROVIDER_UNAVAILABLE: ' + candidate)
        if available and choice not in ('core', 'speckit'):
            commands[stage] = candidate
    if compatible(root, 'superspec') and command_exists(root, 'speckit.superspec.review'):
        commands['review'] = 'speckit.superspec.review'
    return commands


def project_errors(root, policy):
    config = read(root / '.specify/extensions/project/config.json', {})
    if not isinstance(config, dict): return ['PROJECT_CONFIG_INVALID: expected a JSON object']
    errors = []
    for key in ('owner', 'projectId', 'statusFieldId', 'stateFile'):
        if not isinstance(config.get(key), str) or not config[key]: errors.append('PROJECT_CONFIG_REQUIRED: ' + key)
    if type(config.get('projectNumber')) is not int or config['projectNumber'] < 1: errors.append('PROJECT_CONFIG_REQUIRED: projectNumber')
    if config.get('hookMode') != 'required': errors.append('PROJECT_SYNC_MUST_BE_REQUIRED: managed workflow updates the board automatically')
    options, phases = config.get('statusOptions', {}), config.get('phaseToStatus', {})
    if not isinstance(options, dict) or not options or not all(isinstance(v, str) and v for v in options.values()):
        errors.append('PROJECT_STATUS_OPTIONS_REQUIRED'); options = {}
    if not isinstance(phases, dict): phases = {}
    mapping = policy.get('scope', {}).get('statuses', {})
    for status in SCOPE_STATUSES:
        if mapping.get(status, status) not in options: errors.append('PROJECT_SCOPE_STATUS_MISSING: ' + mapping.get(status, status))
    for phase in ('open', 'analysis', 'engineer-review', 'ready', 'in-progress', 'in-review', 'done'):
        if phases.get(phase) not in options: errors.append('PROJECT_PHASE_UNMAPPED: ' + phase)
    if config.get('stateFile'):
        try: inside(root, config['stateFile'])
        except (WorkflowError, TypeError): errors.append('PROJECT_STATE_PATH_INVALID')
    return errors


SCOPE_STATUSES = ('Backlog', 'Feature Specification', 'Need Clarifications', 'Ready', 'In progress', 'In review', 'Done')


def project_defaults(root, policy):
    mapping = policy.get('scope', {}).get('statuses', {})
    phases = {'open': 'Feature Specification', 'analysis': 'Ready', 'engineer-review': 'Ready',
              'ready': 'Ready', 'in-progress': 'In progress', 'in-review': 'In review', 'done': 'Done'}
    phases = {phase: mapping.get(status, status) for phase, status in phases.items()}
    existing = read(root / '.specify/extensions/project/config.json', {})
    require(isinstance(existing, dict), 'PROJECT_CONFIG_INVALID: expected a JSON object')
    if existing.get('projectId') and isinstance(existing.get('phaseToStatus'), dict):
        phases.update({phase: status for phase, status in existing['phaseToStatus'].items() if phase in phases and isinstance(status, str) and status})
    # `statuses`: the exact column names doctor requires, so project init can create the missing ones.
    return {'phaseToStatus': phases, 'statuses': [mapping.get(status, status) for status in SCOPE_STATUSES],
            'source': 'managed policy with preserved configured phase choices'}


# Workflow files Sanduq renders into a consumer project, and the installed asset
# each one is rendered from.
MANAGED_CI = {
    '.github/workflows/sanduq-workflow-gates.yml': '.specify/extensions/workflow/assets/github/workflow-gates.yml',
    '.github/workflows/documentation-gates.yml': '.specify/extensions/assure/assets/github/documentation-gates.yml',
    '.github/workflows/user-manual-preview.yml': '.specify/extensions/user-manual/assets/github/user-manual-preview.yml',
    '.github/workflows/user-manual-release.yml': '.specify/extensions/user-manual/assets/github/user-manual-release.yml',
}


def preserved_ci_path(root):
    """The CI file a --preserve-ci install handed to the project, if any.

    The tracked install lock is authoritative so every clone, worktree and
    machine agrees, including when it records that nothing is preserved; the
    git-excluded receipt only covers installs made before the lock had the key.
    """
    lock = read(root / '.specify/workflow/install-lock.json', {})
    source = lock if 'preserved_ci' in lock else read(root / '.specify/workflow/install-receipt.json', {})
    preserved = (source.get('preserved_ci') or {}).get('path')
    return Path(preserved).as_posix() if preserved else None


def ci_errors(root, policy, preserved=None):
    """Check the project's CI selection against the workflow files on disk.

    Two failures matter: a runner the project's own policy forbids without a
    recorded reason, and a workflow file that no longer matches what the current
    selection renders, which means the selection was changed but never applied.
    An installer that is preserving a file passes it as ``preserved`` because
    nothing on disk records that choice until the install succeeds.
    """
    ci = policy.get('ci') or sanduq_ci.default_ci()
    evidence_file = root / '.github/workflows/sanduq-workflow-gates.yml'
    if ci.get('provider') == 'none':
        return (['CI_PROVIDER_NONE_FILE_PRESENT: remove a managed gate through the installer']
                if evidence_file.is_file() else [])
    gate = sanduq_ci.gate_config(ci)
    if gate['mode'] == 'disabled' and evidence_file.is_file():
        return ['CI_GATE_DISABLED_FILE_PRESENT: remove a managed gate through the installer or review custom CI']
    present = {name: root / name for name in MANAGED_CI if (root / name).is_file()}
    errors = list(sanduq_ci.exception_errors(ci, [Path(name).name for name in present]))
    preserved = Path(preserved).as_posix() if preserved else preserved_ci_path(root)
    for name, target in sorted(present.items()):
        if preserved == name:
            continue  # explicitly kept by --preserve-ci; the project owns it
        asset = root / MANAGED_CI[name]
        if not asset.is_file():
            continue  # that extension is not installed; nothing to render from
        try:
            expected = sanduq_ci.render(asset.read_bytes(), ci)
        except sanduq_ci.CIPolicyError as exc:
            errors.append('CI_TEMPLATE_UNRENDERABLE: ' + name + ': ' + str(exc))
            continue
        if target.read_bytes().replace(b'\r\n', b'\n') != expected.replace(b'\r\n', b'\n'):
            errors.append('CI_WORKFLOW_STALE: ' + name + ' does not match the current ci selection; '
                          'run the workflow installer to re-render it')
    return errors


def delegation_errors(root, policy):
    """Read-only delegation health with the command that repairs a missing skill."""
    from delegation import doctor as delegation_doctor
    health = delegation_doctor(root, active_host(root))
    if not health['ok']:
        error = health['error']
        if error == 'DELEGATE_SKILL_DOCTOR_FAILED' and health.get('owned') is False:
            # Installing cannot help: the first usable copy is not Sanduq's to replace.
            error += ': ' + health['path'] + ': ' + health['action']
        elif error in ('DELEGATE_SKILL_MISSING', 'DELEGATE_SKILL_BROKEN', 'DELEGATE_SKILL_INCOMPATIBLE',
                       'DELEGATE_SKILL_DOCTOR_FAILED'):
            scope = policy['delegation']['install_scope']
            details = [item['path'] + ' (' + item['reason'] + ')' for item in health.get('incompatible') or []]
            if details:
                error += ': ' + '; '.join(details)
            error += (': delegation is enabled but the delegate-task skill is not usable; run '
                      '"python .specify/extensions/workflow/scripts/delegation.py install" to install it at '
                      'the configured ' + scope + ' scope (delegation.install_scope), or set '
                      'delegation.enabled to false')
        return [error]
    if not any(health['harnesses'].values()):
        return ['DELEGATE_AGENT_CLI_UNAVAILABLE: no supported Codex or Claude CLI']
    return []


def host_warnings(root):
    """Another installed host that lost managed skills or aliases still works as the default.

    It becomes a failure only once that host is selected, so it is a warning
    with the command that repairs it.
    """
    import hosts
    installed = hosts.installed_hosts(root)
    others = [host for host in installed if host != active_host(root)]
    if not others:
        return []
    problems = hosts.skill_errors(hosts.skill_report(root, others))
    try:
        problems += hosts.alias_errors(root, Path(__file__).resolve().parents[1], others)
    except OSError:
        pass  # a source tree without the packaged aliases
    repair = WORKFLOW_SCRIPT + ' host --use ' + str(active_host(root))
    return [problem + '; run "' + repair + '" to re-register every installed host' for problem in problems]


def progress_wiring_warnings(root):
    """IP20: native Progress wiring next to a Spec Kit dispatcher entry runs every hook event twice. Any later
    `specify extension` command re-renders the dispatcher entries."""
    if (read(root / '.specify/workflow/install-lock.json', {}).get('progress') or {}).get('hook_wiring') != 'native':
        return []
    import progress_bridge
    doubled = [name for files in progress_bridge.HOST_FILES.values() for name in files
               if (root / name).is_file()
               and 'speckit.progress.hook' in (root / name).read_text(encoding='utf-8-sig', errors='replace')]
    return ['PROGRESS_HOOKS_DOUBLE_WIRED: ' + ', '.join(doubled) + " also hold Spec Kit's speckit.progress.hook "
            'entries next to the native Progress wiring, so each hook event runs twice; run "python '
            '.specify/extensions/workflow/scripts/install.py --apply"'] if doubled else []


def interrupted_install_errors(root):
    """INSTALL_INTERRUPTED when an install, upgrade or host switch left its in-progress marker and its process is gone
    (AHMED-09); the marker names the backup `install.py --restore` puts back."""
    from install import IN_PROGRESS  # lazy: install imports this module
    marker = read(root / IN_PROGRESS, None) if (root / IN_PROGRESS).is_file() else None
    if not isinstance(marker, dict) or sanduq_fs.process_alive(marker.get('pid')):
        return []
    return ['INSTALL_INTERRUPTED: the ' + str(marker.get('kind')) + ' started ' + str(marker.get('started_at')) +
            ' (pid ' + str(marker.get('pid')) + ') did not finish; managed files may be half-written; run "python '
            '.specify/extensions/workflow/scripts/install.py --restore ' + str(marker.get('backup')) + '"']


def history_errors(root):
    """HISTORY_UNRELATED as a doctor --project error (AHMED-24)."""
    try:
        require_shared_history(root)
    except WorkflowError as exc:
        return [str(exc)]
    return []


HOOK_PYTHON_PROBE = 'import sys;print(sys.version_info[0],sys.version_info[1])'


def hook_python_warnings(root):
    """HOOK_PYTHON_MISSING / HOOK_PYTHON_TOO_OLD for the interpreter the active host's guard hook names (AHMED-21):
    the guard allows everything when it cannot run, and Progress and Memory hooks need Python 3.11."""
    import hosts
    path = root / hosts.HOOK_FILES.get(active_host(root), '')
    try:
        document = json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
    except ValueError:
        return []  # HOOK_SETTINGS_INVALID is the installer's call
    hooks = document.get('hooks') if isinstance(document, dict) else None
    commands = [handler.get('command') for groups in (hooks or {}).values() if isinstance(groups, list)
                for group in groups if isinstance(group, dict)
                for handler in (group.get('hooks') or []) if hosts.is_guard(handler)]
    if not commands:
        return []
    name = str(commands[0]).split(None, 1)[0]
    where = path.relative_to(root).as_posix()
    needed = (3, 11) if {'progress', 'memory'} & set(registry(root)) else (3, 10)
    executable = shutil.which(name)
    if not executable:
        return ['HOOK_PYTHON_MISSING: ' + where + ' runs hooks with "' + name + '", which is not on PATH, so the guard '
                'hook allows everything; install it or re-render the hooks for this machine with "python '
                '.specify/extensions/workflow/scripts/install.py --apply"']
    try:
        probe = sanduq_fs.run_bounded([executable, '-c', HOOK_PYTHON_PROBE], timeout=15, error_code='HOOK_PYTHON_MISSING',
                                      next_step='check "' + name + ' --version"', error=WorkflowError,
                                      capture_output=True, text=True)
        version = tuple(int(part) for part in probe.stdout.split())
    except (WorkflowError, OSError, ValueError) as exc:
        return ['HOOK_PYTHON_MISSING: ' + where + ' runs hooks with "' + name + '", which cannot report its version ('
                + str(exc) + '), so the guard hook allows everything']
    if version < needed:
        return ['HOOK_PYTHON_TOO_OLD: ' + where + ' runs hooks with "' + name + '" (Python ' + '.'.join(map(str, version))
                + '); the installed hooks need ' + '.'.join(map(str, needed)) + ' or later; install it first on PATH, '
                'then run "python .specify/extensions/workflow/scripts/install.py --apply"']
    return []


def guard_approval_warnings(root):
    """On Codex the guard hook runs only in a trusted project after `/hooks` approval; warn where it would not run.
    A warning, not an error: the worker prohibitions stay in the Execute text either way."""
    import hosts
    import progress_bridge
    if 'codex' not in hosts.installed_hosts(root):
        return []
    registered, active = progress_bridge.codex_hook_state(root, (hosts.GUARD_MARK,))
    return ['GUARD_HOOK_UNAPPROVED: ' + hosts.CODEX_HOOK_APPROVAL] if registered and not active else []


def doctor_cache_key(root, policy, dependency_digest=None):
    """What a cached green doctor result is valid for: packages, policy and the registration files' mtimes."""
    mtimes = {}
    for name in DOCTOR_CACHE_FILES:
        try:
            mtimes[name] = (root / name).stat().st_mtime_ns
        except OSError:
            mtimes[name] = None
    return {'dependency_digest': dependency_digest or package_digest(root), 'policy_digest': digest(policy),
            'mtimes': mtimes}


def store_doctor_cache(root, policy, result, dependency_digest=None):
    if result.get('ok') and result.get('project_checked'):
        write(root / DOCTOR_CACHE, {'at': datetime.now(timezone.utc).timestamp(),
                                    'key': doctor_cache_key(root, policy, dependency_digest), 'result': result})


def cached_doctor(root, policy, dependency_digest=None):
    """The last green `doctor(project=True)` result while nothing it checked changed and it is under 600 s old;
    otherwise a fresh run, cached when green. `dependency_digest` passes a package digest already computed."""
    cache = read(root / DOCTOR_CACHE, {}) if (root / DOCTOR_CACHE).is_file() else {}
    try:
        age = datetime.now(timezone.utc).timestamp() - float(cache.get('at'))
    except (TypeError, ValueError):
        age = None
    if (age is not None and 0 <= age < DOCTOR_CACHE_SECONDS and isinstance(cache.get('result'), dict)
            and cache['result'].get('ok') is True
            and cache.get('key') == doctor_cache_key(root, policy, dependency_digest)):
        return {**cache['result'], 'cached': True}
    result = doctor(root, policy, project=True, check_delegation=False, check_preflight=False)
    store_doctor_cache(root, policy, result, dependency_digest)
    return result


def doctor(root, policy, project=False, preserved_ci=None, check_delegation=True, check_preflight=True,
           explicit=False):
    """Installation health. `explicit` (the `doctor` command) also runs the skill inventory (with `project`)
    and the byte-sensitive line-ending scan, which no claim or other command pays for."""
    needed = ['scope', 'project', 'pr'] + (['assure'] if policy['processes']['qa'] else []) + (['user-manual'] if policy['processes']['user_manual'] else [])
    errors = dependency_errors(root, needed, project)
    if active_host(root) not in ('codex','claude'):
        errors.append('HOST_UNSUPPORTED: this release supports Codex and Claude skills mode')
    if (check_delegation and policy.get('delegation', {}).get('enabled') and
            active_host(root) in ('codex', 'claude')):
        errors += delegation_errors(root, policy)
    bridge = read(root / '.specify/superpowers-handoff.json', {})
    if bridge.get('status') in ('executing', 'blocked'):
        errors.append('LEGACY_EXECUTOR_OWNS_FEATURE: reconcile the recorded bridge handoff before managed execution')
    agent = '.agents' if active_host(root) == 'codex' else '.claude'
    alias = root / agent / 'skills/speckit-superpowers-bridge/SKILL.md'
    if alias.is_file() and '<!-- sanduq-workflow-alias:v1 -->' not in alias.read_text(encoding='utf-8-sig'):
        errors.append('LEGACY_ALIAS_RECONCILIATION_REQUIRED: run the workflow installer; do not patch the upstream command')
    for name in needed:
        manifest = root / '.specify/extensions' / name / 'extension.yml'
        doc = yaml.safe_load(manifest.read_text(encoding='utf-8-sig')) if manifest.exists() else {}
        if (doc or {}).get('extension', {}).get('repository', '').rstrip('/') != 'https://github.com/samykabu/sanduq':
            errors.append('DEPENDENCY_SOURCE_MISMATCH: ' + name + ' must come from samykabu/sanduq')
    try:
        commands = resolve_commands(root, policy)
        errors += ['COMMAND_UNAVAILABLE: ' + commands[s] for s in stages(policy)
                   if not commands[s].startswith('workflow:') and not command_exists(root, commands[s])]
    except WorkflowError as exc:
        errors.append(str(exc))
    hooks_path = root / '.specify/extensions.yml'
    if not hooks_path.exists():
        errors.append('HOOK_RECONCILIATION_REQUIRED')
    else:
        hooks = yaml.safe_load(hooks_path.read_text(encoding='utf-8-sig')) or {}
        require(isinstance(hooks, dict) and isinstance(hooks.get('hooks'), dict), 'HOOK_CONFIG_INVALID')
        from reconcile import managed_hook  # lazy: reconcile imports this module
        for event, items in hooks.get('hooks', {}).items():
            require(isinstance(items, list) and all(isinstance(item, dict) for item in items), 'HOOK_LIST_INVALID: ' + event)
            for hook in items:
                if managed_hook(event, hook) and hook.get('enabled', True):
                    errors.append('DUPLICATE_STAGE_OWNER: ' + event + ':' + hook.get('command', '') +
                                  '; run "python .specify/extensions/workflow/scripts/reconcile.py --apply"')
    preset_registry = read(root / '.specify/presets/.registry', {}).get('presets', {})
    for preset in ('workflow', 'scope-gate', 'scope-brainstorm'):
        if not (root / '.specify/presets' / preset / 'preset.yml').is_file():
            errors.append('PRESET_REQUIRED: ' + preset)
        if preset_registry.get(preset, {}).get('enabled') is not True:
            errors.append('PRESET_NOT_ENABLED: ' + preset)
    errors += ci_errors(root, policy, preserved_ci) + interrupted_install_errors(root)
    if project: errors += project_errors(root, policy) + history_errors(root)
    warnings = host_warnings(root) + guard_approval_warnings(root) + progress_wiring_warnings(root)
    if explicit: warnings += hook_python_warnings(root)  # one subprocess; no claim pays for it
    # E9: AGENTS.md is the standing file; CLAUDE.md should import it, not repeat it.
    claude_md = root / 'CLAUDE.md'
    if (root / 'AGENTS.md').is_file() and claude_md.is_file() and \
            '@AGENTS.md' not in claude_md.read_text(encoding='utf-8-sig', errors='replace'):
        warnings.append('INSTRUCTION_FILES_DUPLICATED: CLAUDE.md and AGENTS.md both exist; '
                        'put "@AGENTS.md" in CLAUDE.md so both hosts read one standing file')
    # Only a --project doctor run pays for this (migrate/upgrade doctor calls do
    # not), and a scan failure (an unreadable plugin manifest, an odd path) is
    # reported, never allowed to fail doctor itself.
    skill_inventory_result = None
    if project and explicit:
        try:
            skill_inventory_result = skill_inventory.inventory(root, policy)
            warnings += skill_inventory.warnings(skill_inventory_result)
        except Exception as exc:
            skill_inventory_result = None
            warnings.append('SKILL_INVENTORY_UNAVAILABLE: ' + str(exc))
    if isinstance(policy.get('delegation'), dict):
        from delegation import light_tier_route_warnings, unsafe_review_routes, REVIEW_ROUTE_UNSAFE
        warnings += light_tier_route_warnings(policy['delegation'])
        refused = unsafe_review_routes(policy['delegation']) if policy['delegation'].get('enabled') else []
        if refused:  # a warning: only these routes are refused, every other route still delegates
            warnings.append(REVIEW_ROUTE_UNSAFE + ' (refused: ' + ', '.join(refused) + ')')
    drift = eol_drift(root) if explicit else None
    if drift:
        warnings.append(
            f'BYTE_SENSITIVE_EOL_DRIFT: {len(drift)} tracked byte-sensitive file(s) (.sql or -text, e.g. {drift[0]}) '
            'have working-tree line endings that differ from the index (i/lf w/crlf or i/crlf w/lf). Evidence '
            'fingerprints use the committed blob while such a file is otherwise unchanged, but tools reading the '
            'working tree see different bytes than CI. Remedy: commit or stash edits, add "*.sql -text" to '
            '.gitattributes (or set core.autocrlf=false), then re-checkout the files listed by "git ls-files --eol" '
            'with "git -c core.autocrlf=false checkout -- <path>".')
    preflight = lean_preflight(root, policy) if check_preflight else None
    if preflight and not preflight['ok']:
        errors += ['LEAN_PREFLIGHT_FAILED: ' + json.dumps(preflight)]
    result = {'ok': not errors, 'errors': errors, 'warnings': warnings, 'project_checked': project,
              'context': 'Only fresh reliable measurements can trigger context pauses; unavailable or estimated usage is nonblocking outside explicit strict mode'}
    if project and explicit:
        result['skill_inventory'] = skill_inventory_result
    if explicit:
        from install import backup_usage  # lazy: only an explicit doctor reports the kept backups (X19)
        result['backups'] = {**backup_usage(root), 'kept': 'the three newest before.zip'}
    if preflight:
        result['preflight'] = preflight
    return result


def lean_preflight(root, policy):
    config = lean_policy.settings(policy)
    if not config['enabled'] or not config.get('preflight_manifest'):
        return None
    try:
        return execution_tools.preflight(inside(root, config['preflight_manifest']))
    except (execution_tools.InputError, OSError, ValueError) as exc:
        return {'schema': execution_tools.PREFLIGHT_SCHEMA, 'ok': False,
                'checks': [], 'failed': ['manifest'], 'error': str(exc)}


def pr_lint_binding(root, feature, state, receipt):
    """Recompute exact-body lint from native Scope binding, never a submitted success flag."""
    source_label = feature + '/scope-source.json'
    source = read(inside(root, source_label), {})
    repo, issue = state['issue'].split('#')
    require(same_github_repository(github_repository(root), repo), 'PR_LINT_REPOSITORY_MISMATCH')
    require((source.get('repo'), source.get('issue')) == (repo, int(issue)), 'PR_LINT_SCOPE_BINDING_MISMATCH')
    require('dependencies' in source and isinstance(source['dependencies'], list) and
            all(type(n) is int and n > 0 for n in source['dependencies']), 'PR_LINT_SCOPE_PREREQUISITES_REQUIRED')
    body_label = canonical_path(root, receipt.get('pr_body_file', ''))
    lint_label = canonical_path(root, receipt.get('pr_lint_file', ''))
    require(body_label != lint_label and body_label in receipt['evidence'] and lint_label in receipt['evidence'],
            'PR_LINT_EVIDENCE_REQUIRED')
    try:
        body = inside(root, body_label).read_bytes().decode('utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        raise WorkflowError('PR_LINT_BODY_UNREADABLE: ' + str(body_label) + ': ' + str(exc)) from exc
    computed = execution_tools.pr_lint(body, repo, int(issue), source['dependencies'])
    require(computed['ok'], 'PR_CLOSING_REFERENCE_REJECTED: ' + json.dumps(computed['violations']))
    recorded = read(inside(root, lint_label), {})
    require(recorded == computed, 'PR_LINT_RECEIPT_MISMATCH: regenerate lint for the exact sent body')
    require(receipt.get('pr_body_sha256') == computed['body_sha256'], 'PR_SENT_BODY_SHA_MISMATCH')
    return {'body': body_label, 'lint': lint_label, 'scope': source_label,
            'body_sha256': computed['body_sha256'], 'bound': computed['bound'],
            'prerequisites': sorted(set(source['dependencies']))}
