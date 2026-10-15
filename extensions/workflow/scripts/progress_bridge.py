#!/usr/bin/env python3
"""Capability detection and CLI access for the optional Sanduq Progress extension.

Workflow reaches Progress only through its command line and versioned JSON. This module never
imports Progress code. It is the single place that decides the reporting mode:

  projection  Progress is installed and collects automatically (its status reports
              collection.automatic, or its host hooks are registered).
  refresh     Progress is installed but nothing collects automatically.
  legacy      Progress is absent; Workflow's own scripts/progress.py reporter runs unchanged.

`python progress_bridge.py mode` prints one line: `reporting: <mode>`.
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
HOOK_MARKERS = ('speckit.progress.hook', 'progress.py hook', 'progress.py" hook')
HOST_FILES = ('.claude/settings.json', '.claude/settings.local.json', '.codex/hooks.json', '.codex/config.toml',
              '.specify/extensions.yml')
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
    """Path of the Progress CLI, or None when Progress is not installed."""
    override = os.environ.get(SCRIPT_ENV)
    if override:
        return Path(override) if Path(override).is_file() else None
    path = Path(root) / RELATIVE
    return path if path.is_file() else None


def _json_hooks(data):
    """True when a parsed host config holds an enabled command entry that runs a Progress hook."""
    if isinstance(data, dict):
        command = data.get('command')
        if isinstance(command, str) and any(m in command for m in HOOK_MARKERS):
            if data.get('enabled') is not False and data.get('disabled') is not True:
                return True
        return any(_json_hooks(v) for v in data.values())
    if isinstance(data, list):
        return any(_json_hooks(v) for v in data)
    return False


def _yml_hooks(text):
    """Enabled Progress hook entries in .specify/extensions.yml (small line parser; no YAML dependency)."""
    blocks = []
    for line in text.splitlines():
        if re.match(r'\s*-\s+extension\s*:', line):
            blocks.append([line])
        elif blocks and line.strip() and not line.lstrip().startswith('#') and line[:1] in ' \t':
            blocks[-1].append(line)
        elif line.strip() and line[:1] not in ' \t-#':
            blocks.append([])  # a new top-level key ends the current entry
    for block in blocks:
        if not block:
            continue
        body = '\n'.join(block)
        if not re.search(r'extension\s*:\s*[\'"]?progress[\'"]?\s*$', block[0]):
            continue
        command = re.search(r'command\s*:\s*(\S+)', body)
        if not command or 'speckit.progress.hook' not in command.group(1):
            continue
        enabled = re.search(r'\benabled\s*:\s*(\S+)', body)
        if enabled and enabled.group(1).strip('\'"').lower() in ('false', 'no', 'off', '0'):
            continue
        return True
    return False


def extension_enabled(root):
    """False only when the installed-extension registry says Progress is disabled."""
    try:
        data = json.loads((Path(root) / '.specify' / 'extensions' / '.registry').read_text(encoding='utf-8-sig'))
        entry = (data.get('extensions') or {}).get('progress')
    except (OSError, ValueError, AttributeError):
        return True
    return not (isinstance(entry, dict) and entry.get('enabled') is False)


def hooks_registered(root):
    """True when an enabled Progress hook is wired in a host config and the extension itself is enabled."""
    if not extension_enabled(root):
        return False
    for name in HOST_FILES:
        try:
            text = (Path(root) / name).read_text(encoding='utf-8-sig')
        except OSError:
            continue
        if name.endswith('.yml'):
            if _yml_hooks(text):
                return True
            continue
        try:
            if name.endswith('.toml') and tomllib is None:
                continue
            data = tomllib.loads(text) if name.endswith('.toml') else json.loads(text)
        except Exception:  # unreadable config is not evidence of collection
            continue
        if _json_hooks(data):
            return True
    return False


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


def status(root, feature=None):
    """The Progress projection from `status --json`, or None when unavailable (absent, not initialised, broken)."""
    args = ['status', '--json'] + (['--feature', feature] if feature else [])
    result = run(root, args)
    if not result or result[0] != 0:
        return None
    try:
        data = json.loads(result[1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def mode(root, feature=None):
    """Decide the reporting mode. Returns {mode, script, automatic, source}."""
    path = script(root)
    if path is None:
        return {'mode': 'legacy', 'script': None, 'automatic': False, 'source': 'progress not installed'}
    report = status(root, feature)
    # status collection.automatic only reflects stored snapshots (history), so it is not proof of current collection.
    if hooks_registered(root):
        return {'mode': 'projection', 'script': str(path), 'automatic': True, 'source': 'hooks registered'}
    return {'mode': 'refresh', 'script': str(path), 'automatic': False, 'source': 'no automatic collection'}


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
    p.add_argument('--feature')
    p.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    root = args.root.resolve() if args.root else find_root()
    decision = mode(root, args.feature)
    print(json.dumps(decision) if args.json else 'reporting: ' + decision['mode'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
