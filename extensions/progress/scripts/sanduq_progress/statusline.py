"""Claude statusline wrapper plus install/uninstall.

`progress.py statusline` reads the statusline JSON on stdin, records the host snapshot for a bound session, then
runs the previously configured statusLine command (kept in <project dir>/config.json) with the same stdin and
passes its stdout through byte for byte. With no previous command it prints one minimal line."""
import json
import os
import sys
from pathlib import Path

from . import refresh as refreshlib, snapshot
from .hosts import claude
from .lock import Lock, LockBusy
from .paths import Ctx, project_dir
from .util import atomic_write, diag, diag_once, read_json, utcnow, write_json


def record(raw, root, now=None):
    """Write the snapshot for a bound session. Best effort; returns the parsed payload or None."""
    now = now or utcnow()
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None
        obs = claude.parse_statusline(payload, now)
        binding = snapshot.lookup(root, 'claude', obs['session_id']) if obs['session_id'] else None
        if binding and snapshot.cwd_valid(binding, obs.get('cwd')):
            ctx = Ctx(root, binding['feature'])
            if ctx.dir.is_dir():
                with Lock(ctx.lock, retries=1, delay=0.05):
                    snapshot.merge(ctx, 'claude', obs['session_id'], now, fields=obs['fields'])
                    refreshlib.after_update(ctx, now)
        return payload
    except LockBusy:
        return None
    except Exception as exc:
        diag(project_dir(root) / 'diagnostics.log', f'statusline: {type(exc).__name__}: {exc}', now)
        return None


def minimal_line(payload):
    payload = payload or {}
    model = payload.get('model') if isinstance(payload.get('model'), dict) else {}
    window = payload.get('context_window') if isinstance(payload.get('context_window'), dict) else {}
    parts = [str(model.get('display_name') or model.get('id') or 'Claude')]
    if isinstance(window.get('used_percentage'), (int, float)):
        parts.append(f"ctx {int(window['used_percentage'])}%")
    return ' | '.join(parts)


def tracked(root, path):
    """True when git tracks `path`; a missing git or a non-repository counts as untracked."""
    import subprocess
    try:
        return subprocess.run(['git', 'ls-files', '--error-unmatch', '--', str(path)], cwd=str(root),
                              capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def chained_command(root):
    """The previous statusLine command, only while config.json is local state this install wrote: untracked by git
    and still naming the command recorded under `statusline.previous`. A committed config.json would otherwise run a
    shell command from the repository on every refresh."""
    cfg_path = project_dir(root) / 'config.json'
    config = read_json(cfg_path, {})
    saved = config.get('statusline') if isinstance(config, dict) and isinstance(config.get('statusline'), dict) else {}
    chained = saved.get('chained')
    if not chained:
        return None
    previous = saved.get('previous') if isinstance(saved.get('previous'), dict) else {}
    if chained != previous.get('command'):
        diag_once(cfg_path.parent / 'diagnostics.log', 'statusline: chained command ignored: it is not the command recorded in statusline.previous')
        return None
    if tracked(root, cfg_path):
        diag_once(cfg_path.parent / 'diagnostics.log', 'statusline: chained command ignored: config.json is tracked by git')
        return None
    return chained


def run(raw, root, now=None):
    """Return the bytes to print. Chained output is returned unchanged."""
    payload = record(raw, root, now)
    chained = chained_command(root)
    if chained:
        import subprocess
        try:
            out = subprocess.run(chained, shell=True, input=raw, capture_output=True, timeout=5, cwd=str(root))
            if out.stdout or out.returncode == 0:
                return out.stdout
        except (OSError, subprocess.SubprocessError):
            pass
    return (minimal_line(payload) + '\n').encode('utf-8')


def command_for(root):
    script = Path(__file__).resolve().parent.parent / 'progress.py'
    try:
        shown = script.relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        shown = script.as_posix()
    return f'{"python" if os.name == "nt" else "python3"} "{shown}" statusline'


def _settings(root):
    path = Path(root) / '.claude' / 'settings.json'
    data = read_json(path, {}) if path.exists() else {}
    return path, data if isinstance(data, dict) else {}


def install(root):
    """Point Claude's statusLine at the wrapper; the previous one is kept for exact restoration."""
    root = Path(root)
    cfg_path = project_dir(root) / 'config.json'
    config = read_json(cfg_path, {})
    config = config if isinstance(config, dict) else {}
    path, settings = _settings(root)
    ours = command_for(root)
    current = settings.get('statusLine')
    if not (isinstance(current, dict) and current.get('command') == ours):
        previous = current
        status = {'type': 'command', 'command': ours}
        if isinstance(previous, dict) and 'padding' in previous:
            status['padding'] = previous['padding']
        settings['statusLine'] = status
        config['statusline'] = {'enabled': True, 'previous': previous, 'command': ours,
                                'chained': previous.get('command') if isinstance(previous, dict) and previous.get('type') == 'command' else None}
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, json.dumps(settings, indent=2, ensure_ascii=False) + '\n')
        write_json(cfg_path, config)
    return True


def uninstall(root):
    root = Path(root)
    cfg_path = project_dir(root) / 'config.json'
    config = read_json(cfg_path, {})
    config = config if isinstance(config, dict) else {}
    saved = config.get('statusline') if isinstance(config.get('statusline'), dict) else {}
    path, settings = _settings(root)
    current = settings.get('statusLine')
    if isinstance(current, dict) and current.get('command') == saved.get('command') and saved.get('command'):
        if saved.get('previous') is None:
            settings.pop('statusLine', None)
        else:
            settings['statusLine'] = saved['previous']
        atomic_write(path, json.dumps(settings, indent=2, ensure_ascii=False) + '\n')
    config['statusline'] = {'enabled': False, 'chained': None}
    write_json(cfg_path, config)
    return True


def main_stdin(root):
    raw = sys.stdin.buffer.read()
    sys.stdout.buffer.write(run(raw, root))
    sys.stdout.buffer.flush()
