"""`progress hooks install|uninstall|status`: native host hooks that call scripts/hook.py.

Claude Code reads `.claude/settings.json` (project) or `~/.claude/settings.json` (user); Codex reads `.codex/hooks.json`
(project) or `~/.codex/hooks.json` (user). Both use the same shape:

    {"hooks": {"<Event>": [{"matcher": "<regex, optional>", "hooks": [{"type": "command", "command": "...", "timeout": 10}]}]}}

Every command ends in `; exit 0` (valid in bash and PowerShell): if the script path disappears (a plugin cache that was
updated or pruned) the hook ends quietly instead of blocking the host with Python's exit code 2. `hooks status` flags such
entries. Uninstall before updating or removing the plugin.

Every entry written here carries the argument `--managed-by=progress-report` in its command. That tag is how uninstall
finds exactly its own entries and nothing else; the rest of the file is preserved (key order, other hooks, other
settings). Spec Kit registers Progress through its own event dispatcher (`speckit.progress.hook-*`); when such hooks are
present this installer refuses, so one event is never recorded twice.
"""
import json
import os
import re
import sys
from pathlib import Path

from .lock import Lock, LockBusy
from .paths import inside
from .util import ProgressError, atomic_write

TAG = '--managed-by=progress-report'
SPECKIT_MARK = 'speckit.progress.hook'
TIMEOUT = 10
SUBAGENT_MATCHER = 'Task|Agent|spawn_agent'
HOOK_SCRIPT = Path(__file__).resolve().parent.parent / 'hook.py'

# (host event name, hook.py event, matcher). Codex documents no session end event: its Stop already forces a final refresh.
CLAUDE_EVENTS = (('SessionStart', 'session_start', None), ('PreToolUse', 'pre_tool_use', SUBAGENT_MATCHER),
                 ('PostToolUse', 'post_tool_use', None), ('Stop', 'stop', None), ('SessionEnd', 'session_end', None))
CODEX_EVENTS = tuple(e for e in CLAUDE_EVENTS if e[0] != 'SessionEnd')
EVENTS = {'claude': CLAUDE_EVENTS, 'codex': CODEX_EVENTS}


LOCK_WAIT = 3.0  # seconds to wait for another installer
UNSAFE_PYTHON = re.compile(r'[\s"\'`$&|;<>()*?]')


def refused(code, message):
    return ProgressError(code, message, 3)


def home():
    return Path(os.environ.get('SANDUQ_PROGRESS_HOME') or Path.home())


def settings_path(root, host, scope):
    if scope == 'project':
        return Path(root) / ('.claude/settings.json' if host == 'claude' else '.codex/hooks.json')
    if host == 'claude':
        base = Path(os.environ['CLAUDE_CONFIG_DIR']) if os.environ.get('CLAUDE_CONFIG_DIR') else home() / '.claude'
        return base / 'settings.json'
    base = Path(os.environ['CODEX_HOME']) if os.environ.get('CODEX_HOME') else home() / '.codex'
    return base / 'hooks.json'


def shown(root, path):
    path = Path(path)
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        pass
    try:
        return '~/' + path.relative_to(home()).as_posix()
    except ValueError:
        return path.name


def read_raw(path):
    """The file's bytes, or None when it does not exist."""
    try:
        return Path(path).read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise refused('PROGRESS_HOOKS_SETTINGS', f'cannot read {Path(path).name}: {type(exc).__name__}') from None


def parse(path, raw):
    """The settings document from its bytes ({} when missing or empty). A file that is not a JSON object is never overwritten."""
    if raw is None or not raw.strip():
        return {}
    try:
        data = json.loads(raw.decode('utf-8-sig'))
    except ValueError:
        raise refused('PROGRESS_HOOKS_SETTINGS', f'{Path(path).name} is not valid JSON; fix it first') from None
    if not isinstance(data, dict) or not isinstance(data.get('hooks', {}), dict):
        raise refused('PROGRESS_HOOKS_SETTINGS', f'{Path(path).name} has an unexpected "hooks" shape; not touching it')
    return data


def load(path):
    return parse(path, read_raw(path))


def load_quiet(path):
    """(document, True), or ({}, False) when the file cannot be read: only the file an install writes may stop it."""
    try:
        return load(path), True
    except ProgressError:
        return {}, False


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def has_speckit(data):
    return any(SPECKIT_MARK in text for text in strings(data.get('hooks', {})))


def is_ours(handler):
    command = handler.get('command') if isinstance(handler, dict) else None
    return isinstance(command, str) and TAG in command and 'hook.py' in command


def own_count(data):
    count = 0
    for groups in data.get('hooks', {}).values():
        for group in groups if isinstance(groups, list) else []:
            count += sum(1 for h in group.get('hooks', []) if is_ours(h)) if isinstance(group, dict) and isinstance(group.get('hooks'), list) else 0
    return count


def python_command(override):
    if override and UNSAFE_PYTHON.search(override):
        raise ProgressError('PROGRESS_USAGE', '--python takes one command word without spaces or shell characters '
                            '(put the interpreter on PATH, or use a short path)', 2)
    return override or ('python' if sys.platform == 'win32' else 'python3')


def script_of(command):
    m = re.search(r'"([^"]*hook\.py)"', command) or re.search(r'(\S*hook\.py)', command)
    return m.group(1) if m else None


def missing_scripts(root, data):
    """How many of our entries point at a hook script that no longer exists."""
    count = 0
    for groups in data.get('hooks', {}).values():
        for group in groups if isinstance(groups, list) else []:
            for h in group.get('hooks', []) if isinstance(group, dict) and isinstance(group.get('hooks'), list) else []:
                if not is_ours(h):
                    continue
                script = script_of(h['command'])
                if script:
                    script = re.sub(r'^\$\{?CLAUDE_PROJECT_DIR\}?', str(Path(root).as_posix()), script)
                    count += 0 if (Path(root) / script).exists() else 1
    return count


def command_for(root, host, scope, event, python):
    script = HOOK_SCRIPT.resolve()
    if scope == 'project':
        if not inside(script, root):
            raise ProgressError('PROGRESS_HOOKS_PATH', 'the skill is outside this repository; use --scope user or copy the skill into the repo', 3)
        relative = script.relative_to(Path(root).resolve()).as_posix()
        path = f'${{CLAUDE_PROJECT_DIR}}/{relative}' if host == 'claude' else relative
    else:
        path = script.as_posix()
    return f'{python} "{path}" {event} {TAG}; exit 0'


def strip_own(data):
    """Remove this installer's entries, and the groups and keys that only held them. Returns how many entries went."""
    removed = 0
    hooks = data.get('hooks', {})
    for name in list(hooks):
        groups = hooks[name]
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            inner = group.get('hooks') if isinstance(group, dict) else None
            if not isinstance(inner, list):
                kept.append(group)
                continue
            left = [h for h in inner if not is_ours(h)]
            removed += len(inner) - len(left)
            if left:
                kept.append({**group, 'hooks': left} if len(left) != len(inner) else group)
        if kept:
            hooks[name] = kept
        else:
            del hooks[name]
    if 'hooks' in data and not hooks:
        del data['hooks']
    return removed


def install_lock_path(root, host):
    """One lock file per host for every install and uninstall: it sits next to the user-scope settings, so a project-scope
    and a user-scope installer (which look at each other's registrations) serialise on the same file."""
    path = settings_path(root, host, 'user')
    return Path(str(path) + '.progress-lock')


class InstallLock:
    """The package's OS-backed `Lock`: released by the operating system when its owner dies, never taken over by age and
    never removed by anyone else, so a live installer that is merely slow keeps it."""

    def __init__(self, path):
        self.lock = Lock(path, retries=max(0, int(LOCK_WAIT / 0.05)), delay=0.05)

    def __enter__(self):
        try:
            return self.lock.acquire()
        except LockBusy:
            raise refused('PROGRESS_HOOKS_CONFLICT', f'another installer holds {self.lock.path.name}; retry') from None
        except OSError as exc:
            raise refused('PROGRESS_HOOKS_CONFLICT', f'cannot take {self.lock.path.name}: {type(exc).__name__}') from None

    def __exit__(self, *exc):
        self.lock.release()
        return False


def before_replace(path):
    """Seam between computing the new document and replacing the file (tests change the file here)."""


def edit(path, mutate, lock_path=None):
    """Read, `mutate(document)`, write, under a lock and only if the file is unchanged since it was read. A change in
    between (the host or the user editing the settings) is re-read and the edit re-applied once; a second change refuses.
    `mutate` runs again on every attempt, so checks inside it see what is on disk now."""
    path = Path(path)
    with InstallLock(lock_path or Path(str(path) + '.progress-lock')):
        for attempt in (1, 2):
            raw = read_raw(path)
            data = parse(path, raw)
            result = mutate(data)
            if result is False:  # nothing to write
                return result
            before_replace(path)
            if read_raw(path) == raw:
                atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + '\n')
                return result
        raise refused('PROGRESS_HOOKS_CONFLICT', f'{path.name} changed while it was being edited; nothing written, retry')


def check_registrations(root, host, scope, target_data, force_both=False):
    """Refuse when Spec Kit registers Progress hooks in either scope, or when the other scope already has ours (unless
    --force-both). `target_data` is the document being edited, so the file that is written is judged as it is now."""
    for other in ('project', 'user'):
        found = settings_path(root, host, other)
        data, ok = (target_data, True) if other == scope else load_quiet(found)
        if ok and has_speckit(data):
            raise refused('PROGRESS_HOOKS_SPECKIT', f'Spec Kit already registers Progress hooks in {shown(root, found)}; remove them or keep using the extension')
        if ok and other != scope and own_count(data) and not force_both:
            raise refused('PROGRESS_HOOKS_DUPLICATE', f'hooks are already installed in {shown(root, found)}; uninstall them there first, or pass --force-both')


def install(root, host, scope, python, force_both=False):
    path = settings_path(root, host, scope)
    commands = [command_for(root, host, scope, event, python) for _, event, _ in EVENTS[host]]

    def mutate(data):
        check_registrations(root, host, scope, data, force_both)  # on every attempt, inside the lock
        strip_own(data)
        hooks = data.setdefault('hooks', {})
        for (name, _, matcher), command in zip(EVENTS[host], commands):
            group = {'matcher': matcher} if matcher else {}
            group['hooks'] = [{'type': 'command', 'command': command, 'timeout': TIMEOUT}]
            hooks.setdefault(name, [])
            if not isinstance(hooks[name], list):
                raise refused('PROGRESS_HOOKS_SETTINGS', f'{path.name} hooks.{name} is not a list; not touching it')
            hooks[name].append(group)
        return True

    edit(path, mutate, install_lock_path(root, host))
    note = (' (Codex hooks are experimental: enable the codex_hooks feature; Codex runs them only after you trust the project '
            'and approve each hook)') if host == 'codex' else ''
    return f'progress: hooks installed {host} {scope} {len(EVENTS[host])} entries in {shown(root, path)}{note}'


def uninstall(root, host, scope):
    path = settings_path(root, host, scope)
    if not path.is_file():
        return f'progress: hooks removed {host} {scope} 0 entries'
    removed = edit(path, lambda data: strip_own(data) or False, install_lock_path(root, host))
    return f'progress: hooks removed {host} {scope} {removed or 0} entries from {shown(root, path)}'


# ---- Codex approval -----------------------------------------------------------------------------------------
# Codex runs a project hook only when the project is trusted in the user config ([projects."<path>"] trust_level) and the
# hook definition is approved ([hooks.state."<file>:<event>:<group>:<hook>"] trusted_hash). Read-only: never edited here.
# The hash algorithm is not ours to verify, so an edited hook may need approving again.

def codex_config(scope, root):
    if scope == 'project':
        return Path(root) / '.codex' / 'config.toml'
    base = Path(os.environ['CODEX_HOME']) if os.environ.get('CODEX_HOME') else home() / '.codex'
    return base / 'config.toml'


def load_toml(path):
    """The parsed TOML document, {} when absent, None when unreadable (or tomllib is missing: Python before 3.11)."""
    try:
        import tomllib
        return tomllib.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except Exception:
        return None


def norm_key(text):
    """Windows-proof comparison: separators and case do not matter, nor an extended-length prefix."""
    text = str(text).replace(chr(92), '/')
    return re.sub(r'^//[?.]/', '', text).lower()


def snake(name):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower() if not name.islower() else name


def codex_hook_keys(path, data, ours):
    """State keys of every hook in `data['hooks']` accepted by `ours(handler)`: file:event:group:hook."""
    keys = []
    hooks = data.get('hooks')
    for event, groups in (hooks.items() if isinstance(hooks, dict) else ()):
        if not isinstance(groups, list):
            continue
        for gi, group in enumerate(groups):
            inner = group.get('hooks') if isinstance(group, dict) else None
            for hi, handler in enumerate(inner if isinstance(inner, list) else ()):
                if ours(handler):
                    keys.append(f'{Path(path).resolve().as_posix()}:{snake(event)}:{gi}:{hi}')
    return keys


def mentions_speckit(handler):
    return any(SPECKIT_MARK in t for t in strings(handler))


def codex_registered(root, scope):
    """State keys of the Progress hooks Codex would read for this scope: the installer's hooks.json entries plus the
    Spec Kit entries in config.toml."""
    found = []
    hooks_file = settings_path(root, 'codex', scope)
    data, ok = load_quiet(hooks_file)
    if ok:
        found += codex_hook_keys(hooks_file, data, is_ours)
    config = codex_config(scope, root)
    toml = load_toml(config)
    if toml:
        found += codex_hook_keys(config, toml, mentions_speckit)
    return found


def codex_approval(root):
    """{'trusted': bool|None, 'project': (registered, approved), 'user': (registered, approved), 'known': bool}.
    `known` is False when the user config cannot be read, in which case nothing is claimed about approval."""
    user = load_toml(codex_config('user', root))
    state = user.get('hooks', {}).get('state', {}) if isinstance(user, dict) and isinstance(user.get('hooks'), dict) else {}
    approved = {norm_key(k) for k, v in state.items() if isinstance(v, dict) and str(v.get('trusted_hash') or '').strip()}
    projects = user.get('projects', {}) if isinstance(user, dict) and isinstance(user.get('projects'), dict) else {}
    trusted_paths = {norm_key(k).rstrip('/') for k, v in projects.items() if isinstance(v, dict) and v.get('trust_level') == 'trusted'}
    here = Path(root).resolve()
    chain = [norm_key(p.as_posix()).rstrip('/') for p in (here, *here.parents)]
    out = {'known': user is not None, 'trusted': any(c in trusted_paths for c in chain)}
    for scope in ('project', 'user'):
        keys = codex_registered(root, scope)
        out[scope] = (len(keys), sum(1 for k in keys if norm_key(k) in approved))
    return out


def codex_unapproved(root):
    """True when Codex has Progress hooks registered that it will not run (not approved, or project untrusted)."""
    try:
        info = codex_approval(root)
    except Exception:
        return False
    if not info['known']:
        return False
    registered, approved = info['project']
    user_registered, user_approved = info['user']
    return (registered and (approved < registered or not info['trusted'])) or user_approved < user_registered


def status(root, hosts):
    parts, speckit = [], False
    approval = codex_approval(root) if 'codex' in hosts else None
    for host in hosts:
        cells, needs_action = [], False
        for scope in ('project', 'user'):
            data, ok = load_quiet(settings_path(root, host, scope))
            if not ok:
                cells.append(f'{scope} unreadable')
                continue
            speckit = speckit or has_speckit(data)
            gone = missing_scripts(root, data)
            expected = len(EVENTS[host])
            count = own_count(data)
            if host == 'codex':
                toml = load_toml(codex_config(scope, root))
                speckit = speckit or bool(toml) and SPECKIT_MARK in ' '.join(strings(toml.get('hooks', {})))
                registered, approved = approval[scope]
                if registered:
                    expected = max(expected, registered)
                    cell = f'{scope} {registered}/{expected} registered' + (f' ({gone} script missing)' if gone else '')
                    if approval['known']:
                        cell += f', {approved}/{registered} approved'
                        needs_action = needs_action or approved < registered
                        if scope == 'project' and not approval['trusted']:
                            cell += ', project untrusted'
                            needs_action = True
                    cells.append(cell)
                    continue
            cells.append(f'{scope} {count}/{expected}' + (f' ({gone} script missing)' if gone else ''))
        detailed = any('registered' in c for c in cells)
        parts.append(f'{host} ' + ('; ' if detailed else ' ').join(cells))
        if needs_action:
            parts[-1] += ' (approve the hooks in Codex)'
    return 'progress: hooks ' + '; '.join(parts) + f"; spec-kit {'yes' if speckit else 'no'}"


def execute(a, root):
    """The result line of a hooks verb. Never touches a host unless asked: install and uninstall need --host."""
    root = Path(root)
    if a.action == 'status':
        return status(root, (a.host,) if a.host else ('claude', 'codex'))
    if not a.host:
        raise ProgressError('PROGRESS_USAGE', f'hooks {a.action} needs --host claude|codex', 2)
    if a.action == 'install':
        return install(root, a.host, a.scope, python_command(a.python), a.force_both)
    return uninstall(root, a.host, a.scope)


def run(a, root):
    print(execute(a, root))
    return 0
