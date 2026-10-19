#!/usr/bin/env python3
"""PreToolUse guard for Claude Code and Codex while a Sanduq Memory archive run is active.

Off unless `.specify/memory-policy.json` has `"guard_hooks": true` (exit 0 at once otherwise).
While `<git common dir>/sanduq-memory/active.json` exists it denies `git push|stash|reset|clean`
(`git stash list|show` stay allowed) and Write, Edit or a Codex patch under `specs/memory/`: a run
edits only its candidate.json, finalize writes memory, and recovery.md is the documented way to
finish, abandon or roll back. Exit 2 with a one-line reason on stderr denies the call; anything
unexpected allows, because a guard must never break the host. Standard library only.
"""
import json
import os
import re
import shlex
import subprocess
import sys

VERBS = {'push', 'stash', 'reset', 'clean'}
STASH_READ_ONLY = {'list', 'show'}
SEPARATORS = re.compile(r'&&|\|\||[;|&\n]')
PATCH_FILE = re.compile(r'^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$', re.M)
RECOVERY = '.specify/extensions/memory/references/recovery.md'


def enabled(root):
    try:
        with open(os.path.join(root, '.specify/memory-policy.json'), encoding='utf-8-sig') as stream:
            return json.load(stream).get('guard_hooks') is True
    except (OSError, ValueError, AttributeError):
        return False


def active(root):
    try:
        result = subprocess.run(['git', '-C', root, 'rev-parse', '--git-common-dir'],
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    common = result.stdout.strip()
    # os.path.join keeps an absolute common dir as it is.
    return result.returncode == 0 and bool(common) and os.path.isfile(
        os.path.join(root, common, 'sanduq-memory', 'active.json'))


def command_text(payload):
    tool_input = payload.get('tool_input')
    command = tool_input.get('command', tool_input.get('cmd')) if isinstance(tool_input, dict) else None
    if isinstance(command, list):
        command = '\n'.join(str(part) for part in command)
    return command if isinstance(command, str) else ''


def git_verbs(command):
    found = []
    for segment in SEPARATORS.split(command):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            tokens = segment.split()
        while tokens and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', tokens[0]):
            tokens = tokens[1:]
        if not tokens or os.path.basename(tokens[0]).lower() not in ('git', 'git.exe'):
            continue
        rest = tokens[1:]
        while rest and rest[0].startswith('-'):
            rest = rest[2:] if rest[0] in ('-C', '-c', '--git-dir', '--work-tree', '--namespace') else rest[1:]
        if rest and rest[0] in VERBS and not (rest[0] == 'stash' and len(rest) > 1 and rest[1] in STASH_READ_ONLY):
            found.append(rest[0])
    return found


def memory_writes(payload, root):
    tool_input = payload.get('tool_input') if isinstance(payload.get('tool_input'), dict) else {}
    paths = [tool_input.get(key) for key in ('file_path', 'path', 'notebook_path')]
    paths += PATCH_FILE.findall(command_text(payload) or str(tool_input.get('input', '')))
    base = os.path.normcase(os.path.abspath(os.path.join(root, 'specs', 'memory')))
    hits = []
    for path in paths:
        if isinstance(path, str) and path:
            full = os.path.normcase(os.path.abspath(os.path.join(root, path)))
            if full == base or full.startswith(base + os.sep):
                hits.append(path)
    return hits


def main(stdin=sys.stdin, environ=os.environ):
    try:
        payload = json.loads(stdin.read() or '{}')
    except (ValueError, OSError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    root = environ.get('CLAUDE_PROJECT_DIR') or (payload.get('cwd') if isinstance(payload.get('cwd'), str) else None) or '.'
    if not enabled(root):
        return 0
    verbs = git_verbs(command_text(payload))
    writes = memory_writes(payload, root)
    if not (verbs or writes) or not active(root):
        return 0
    if verbs:
        sys.stderr.write('Sanduq memory guard: git ' + verbs[0] + ' is refused while an archive run is active; the run '
                         'edits only its candidate.json, and ' + RECOVERY + ' is the way to finish, abandon or roll back.\n')
    else:
        sys.stderr.write('Sanduq memory guard: ' + writes[0] + ' is under specs/memory/, which only finalize writes while an '
                         'archive run is active; edit the run\'s candidate.json instead (recovery: ' + RECOVERY + ').\n')
    return 2


if __name__ == '__main__':
    try:
        code = main()
    except Exception:  # never crash the host on unexpected input
        code = 0
    sys.exit(code)
