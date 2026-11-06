#!/usr/bin/env python3
"""Capability detection and CLI access for the optional Sanduq Progress extension.

Workflow reaches Progress only through its command line and versioned JSON. This module never
imports Progress code. It is the single place that decides the reporting mode:

  projection  Progress is installed and enabled, and its hooks are registered and enabled for the active host.
  refresh     Progress is installed and enabled, but the active host does not collect automatically (or the host
              cannot be told). On Codex that includes registered hooks the user has not approved: Codex silently
              skips a hook whose project is untrusted or whose definition has no approval in its user config.
  legacy      Progress is absent or disabled in the spec-kit registry; Workflow's own scripts/progress.py reporter
              runs unchanged.

`python progress_bridge.py mode [--host claude|codex]` prints one line: `reporting: <mode>`. Without --host the host
is detected from the environment; an unknown or ambiguous host selects `refresh`. When Codex hooks are registered but
not approved the line carries the reason: `reporting: refresh (codex hooks not approved)`.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11: TOML host configs cannot be read
    tomllib = None

SCRIPT_ENV = 'SANDUQ_PROGRESS_SCRIPT'  # tests and source-tree use; normally the installed path is used
RELATIVE = Path('.specify/extensions/progress/scripts/progress.py')
# The last two match native wiring (`progress hooks install`: hook.py runs without Spec Kit's dispatcher, tagged).
HOOK_MARKERS = ('speckit.progress.hook', 'progress.py hook', 'progress.py" hook', 'progress/scripts/hook.py',
                '--managed-by=progress-report')
HOST_FILES = {'claude': ('.claude/settings.json', '.claude/settings.local.json'),
              'codex': ('.codex/hooks.json', '.codex/config.toml')}
HOSTS = tuple(HOST_FILES)
# Variables the host CLIs set in the processes they start. CODEX_HOME is only a config location users also set under
# other hosts, so it does not identify Codex.
HOST_ENV_CLAUDE = ('CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT')
HOST_ENV_CODEX = ('CODEX_THREAD_ID', 'CODEX_SANDBOX', 'CODEX_SANDBOX_NETWORK_DISABLED', 'CODEX_CI')
RUNS_SCHEMA = 'progress.runs.v1'
MODES = ('projection', 'refresh', 'legacy')


def find_root(start=None):
    """Nearest ancestor holding an installed Progress script or a .specify folder; else the start directory."""
    here = Path(start or Path.cwd()).resolve()
    if here.is_file():
        here = here.parent
    chain = (here, *here.parents)
    for candidate in chain:
        if (candidate / RELATIVE).is_file():
            return candidate
    for candidate in chain:
        if (candidate / '.specify').is_dir():
            return candidate
    return here


def script(root):
    """Path of the Progress CLI, or None when Progress is not installed or is disabled in the spec-kit registry
    (a disabled extension's commands and hooks are inert, so nothing may be forwarded to it)."""
    if not extension_enabled(root):
        return None
    override = os.environ.get(SCRIPT_ENV)
    if override:
        return Path(override) if Path(override).is_file() else None
    path = Path(root) / RELATIVE
    return path if path.is_file() else None


def _off(data):
    """True when a config object is itself switched off (`enabled: false` or `disabled: true`)."""
    return data.get('enabled') is False or data.get('disabled') is True


def _json_hooks(data, markers=HOOK_MARKERS):
    """True when a parsed host config holds an enabled command entry that runs a hook carrying one of `markers` (a
    Progress hook by default). A disabled object disables everything beneath it, so the walk does not descend."""
    if isinstance(data, dict):
        if _off(data):
            return False
        command = data.get('command')
        if isinstance(command, str) and any(m in command for m in markers):
            return True
        return any(_json_hooks(v, markers) for v in data.values())
    if isinstance(data, list):
        return any(_json_hooks(v, markers) for v in data)
    return False


def _globally_disabled(data):
    """Host-wide switches: Claude's `disableAllHooks: true`; Codex's `[features] codex_hooks/hooks = false`."""
    if not isinstance(data, dict):
        return None
    if isinstance(data.get('disableAllHooks'), bool):
        return data['disableAllHooks']
    features = data.get('features')
    if isinstance(features, dict):
        for key in ('codex_hooks', 'hooks'):
            if features.get(key) is False:
                return True
    return None


def extension_enabled(root):
    """False only when the installed-extension registry says Progress is disabled."""
    try:
        data = json.loads((Path(root) / '.specify' / 'extensions' / '.registry').read_text(encoding='utf-8-sig'))
        entry = (data.get('extensions') or {}).get('progress')
    except (OSError, ValueError, AttributeError):
        return True
    return not (isinstance(entry, dict) and entry.get('enabled') is False)


def _snake(name):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', str(name)).lower()


def _norm_path(value):
    """Comparable form of a path: forward slashes, no extended-length prefix, lowercased on Windows."""
    text = str(value)
    if text.startswith('\\\\?\\'):
        text = text[4:]
    text = text.replace('\\', '/').rstrip('/')
    return text.lower() if os.name == 'nt' else text


def _hook_slots(data, markers=HOOK_MARKERS):
    """Yield (event, group index, hook index) for each enabled Progress hook in a parsed Codex hooks config.
    Nested groups (`hooks.Event[i].hooks[j]`) and flat groups (the entry itself is the hook, index 0) are accepted."""
    hooks = data.get('hooks') if isinstance(data, dict) else None
    if not isinstance(hooks, dict) or _off(hooks):
        return
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        for gi, group in enumerate(groups):
            if not isinstance(group, dict) or _off(group):
                continue
            inner = group.get('hooks')
            entries = inner if isinstance(inner, list) else [group]
            for hi, entry in enumerate(entries):
                if _json_hooks(entry, markers):
                    yield _snake(event), gi, hi


def _codex_trusted(user, root):
    """True when the user's Codex config marks the project path as trusted."""
    projects = (user or {}).get('projects')
    if not isinstance(projects, dict):
        return False
    want = _norm_path(root)
    return any(isinstance(v, dict) and v.get('trust_level') == 'trusted' and _norm_path(k) == want
               for k, v in projects.items())


def _codex_approvals(user):
    """Normalised (path, event, group, hook) keys of hooks.state entries holding a non-empty trusted_hash. The hash
    algorithm is Codex's own and is not verified, so an edited hook whose approval went stale is not detected."""
    hooks = (user or {}).get('hooks')
    state = hooks.get('state') if isinstance(hooks, dict) else None
    keys = set()
    if isinstance(state, dict):
        for key, value in state.items():
            digest = value.get('trusted_hash') if isinstance(value, dict) else None
            parts = str(key).rsplit(':', 3)
            if isinstance(digest, str) and digest.strip() and len(parts) == 4:
                keys.add((_norm_path(parts[0]), parts[1].lower(), parts[2], parts[3]))
    return keys


def _codex_active(root, configs, user_toml, user_files, markers=HOOK_MARKERS):
    """(active, registered). A Progress hook is active only when Codex will run it: project-defined hooks need the
    project trusted and an approval entry for that exact file, event, group and hook index; user-level hooks need the
    approval entry."""
    approvals = _codex_approvals(user_toml)
    trusted = _codex_trusted(user_toml, root)
    registered = False
    sources = [(Path(root) / n, configs[n], True) for n in HOST_FILES['codex'] if n in configs]
    sources += [(p, d, False) for p, d in user_files]
    for path, data, project in sources:
        for event, gi, hi in _hook_slots(data, markers):
            registered = True
            if (not project or trusted) and (_norm_path(path), event, str(gi), str(hi)) in approvals:
                return True, True
    return False, registered


def _user_codex_files(user_toml):
    """User-level Codex hook definitions: hooks.json and config.toml under $CODEX_HOME or ~/.codex."""
    override = os.environ.get('CODEX_HOME')
    base = Path(override) if override else Path.home() / '.codex'
    found = [(base / 'config.toml', user_toml)] if user_toml else []
    try:
        found.append((base / 'hooks.json', json.loads((base / 'hooks.json').read_text(encoding='utf-8-sig'))))
    except Exception:
        pass
    return found


def _user_configs():
    """User-level host configs that can switch hooks off: $CLAUDE_CONFIG_DIR or ~/.claude, $CODEX_HOME or ~/.codex."""
    homes = {'claude': (os.environ.get('CLAUDE_CONFIG_DIR'), '.claude', 'settings.json'),
             'codex': (os.environ.get('CODEX_HOME'), '.codex', 'config.toml')}
    found = {}
    for host, (override, default, name) in homes.items():
        path = Path(override) / name if override else Path.home() / default / name
        try:
            text = path.read_text(encoding='utf-8-sig')
            if name.endswith('.toml'):
                if tomllib is None:
                    continue
                found[host] = tomllib.loads(text)
            else:
                found[host] = json.loads(text)
        except Exception:  # absent or unreadable user config states no switch
            continue
    return found


def detect_host(env=None):
    """'claude' or 'codex' from the host CLI's own environment variables; None when neither or both are present."""
    env = os.environ if env is None else env
    claude = any(env.get(name) for name in HOST_ENV_CLAUDE)
    codex = any(env.get(name) for name in HOST_ENV_CODEX)
    return 'claude' if claude and not codex else 'codex' if codex and not claude else None


def hooks_registered(root, host):
    """True when an enabled Progress hook is wired in the given host's config (only that host's files count), the
    extension itself is enabled and, for Codex, the hooks are approved (see `hooks_state`)."""
    return hooks_state(root, host)[0]


def _project_configs(root):
    """The project's parsed host configs; an absent or unreadable one is left out."""
    configs = {}
    for name in [n for files in HOST_FILES.values() for n in files]:
        try:
            text = (Path(root) / name).read_text(encoding='utf-8-sig')
            if name.endswith('.toml') and tomllib is None:
                continue
            configs[name] = tomllib.loads(text) if name.endswith('.toml') else json.loads(text)
        except Exception:  # absent or unreadable config is not evidence of collection
            continue
    return configs


def codex_hook_state(root, markers):
    """(registered, active) for Codex hooks whose command carries one of `markers`: active only when Codex will run
    one (hooks not switched off, the project trusted for a project hook, and an approval entry for that exact hook).
    Like `hooks_state`, the stored hash is not verified, so an approval gone stale after an edit is not detected."""
    configs, user = _project_configs(root), _user_configs()
    active, registered = _codex_active(root, configs, user.get('codex'), _user_codex_files(user.get('codex')), markers)
    if (any(_globally_disabled(configs.get(n)) for n in HOST_FILES['codex'])
            or bool(_globally_disabled(user.get('codex')))):
        active = False
    return registered, active


def hooks_state(root, host):
    """(active, unapproved). `unapproved` is True when Codex hooks are registered but Codex would skip them."""
    if host not in HOSTS or not extension_enabled(root):
        return False, False
    configs = _project_configs(root)
    user = _user_configs()
    if host == 'claude':
        # Local settings override project settings, which override user settings, when they state the switch.
        switches = [_globally_disabled(configs.get(n)) for n in ('.claude/settings.local.json', '.claude/settings.json')]
        switches.append(_globally_disabled(user.get('claude')))
        if next((v for v in switches if v is not None), False):
            return False, False
    else:
        # A switch in the project or user config.toml turns hooks off everywhere.
        if (any(_globally_disabled(configs.get(n)) for n in HOST_FILES['codex'])
                or bool(_globally_disabled(user.get('codex')))):
            return False, False
        active, registered = _codex_active(root, configs, user.get('codex'), _user_codex_files(user.get('codex')))
        return active, registered and not active
    return any(_json_hooks(configs[n]) for n in HOST_FILES[host] if n in configs), False


def run(root, args, timeout=60, stdin=None):
    """Run the Progress CLI from the repository root. Returns (exit_code, stdout, stderr) or None if absent."""
    path = script(root)
    if path is None:
        return None
    try:
        done = subprocess.run([sys.executable, str(path), '--root', str(root), *args], cwd=str(root), input=stdin,
                              capture_output=True, text=True, encoding='utf-8', timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return 70, '', f'progress CLI could not run: {type(exc).__name__}'
    return done.returncode, done.stdout, done.stderr


def status_line(root, feature):
    """Progress's own one-line text status for `feature`, or None when Progress is absent. A failure comes back
    as its first output line, never raised: the workflow record must print without it."""
    result = run(root, ['status', '--feature', feature], timeout=10)
    if result is None:
        return None
    lines = (result[1] or result[2] or '').strip().splitlines()
    return lines[0] if lines else f'progress status exited {result[0]} with no output'


def mode(root, feature=None, host=None):
    """Decide the reporting mode for the active host (detected from the environment when not given).
    Returns {mode, script, automatic, host, source}. `feature` is accepted for compatibility and unused: the decision
    needs no Progress process."""
    path = script(root)
    if path is None:
        return {'mode': 'legacy', 'script': None, 'automatic': False, 'host': None, 'source': 'progress not installed or disabled'}
    host = host or detect_host()
    if host is None:
        return {'mode': 'refresh', 'script': str(path), 'automatic': False, 'host': None, 'source': 'active host unknown'}
    active, unapproved = hooks_state(root, host)
    if active:
        return {'mode': 'projection', 'script': str(path), 'automatic': True, 'host': host, 'source': 'hooks registered'}
    if unapproved:
        return {'mode': 'refresh', 'script': str(path), 'automatic': False, 'host': host,
                'source': 'codex hooks registered but not approved', 'reason': 'codex hooks not approved'}
    return {'mode': 'refresh', 'script': str(path), 'automatic': False, 'host': host, 'source': 'no automatic collection'}


def runs(root, runs_dirs, now=None, stall_seconds=None):
    """Normalized runs from `progress runs --json`, or None when Progress is absent or answers another schema."""
    args = ['runs', '--json']
    for folder in runs_dirs:
        args += ['--runs-dir', str(folder)]
    if now:
        args += ['--now', now]
    if stall_seconds is not None:
        args += ['--stall-seconds', str(stall_seconds)]
    result = run(root, args)
    if not result or result[0] != 0:
        return None
    try:
        data = json.loads(result[1])
    except ValueError:
        return None
    return data if isinstance(data, dict) and data.get('schema') == RUNS_SCHEMA else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('mode', help='print the reporting mode')
    p.add_argument('--root', type=Path)
    p.add_argument('--feature', help='accepted for compatibility; ignored')
    p.add_argument('--host', choices=HOSTS, help='active host; detected from the environment when absent')
    p.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    root = args.root.resolve() if args.root else find_root()
    decision = mode(root, args.feature, args.host)
    reason = decision.get('reason')
    print(json.dumps(decision) if args.json else 'reporting: ' + decision['mode'] + (f' ({reason})' if reason else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
