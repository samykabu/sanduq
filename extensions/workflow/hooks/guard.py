#!/usr/bin/env python3
"""PreToolUse guard for Claude Code and Codex: refuse commands that hide or take over others' work.

- `git add -A`, `git add .` and `git stash` are refused in every session unless env
  SANDUQ_ROLE=coordinator (the coordinator stages owned paths by name anyway).
- `delegate_dispatch.py trust-reset|accept|reassign|adopt` are refused only in a worker context:
  env SANDUQ_DELEGATED_RUN set, env SANDUQ_ROLE=worker, or a payload carrying `agent_id` or
  `agent_type` (both hosts add these in subagent sessions). The top-level session runs them.

Reads the hook payload (JSON) on stdin. Both hosts send ``tool_name`` and
``tool_input.command``; Codex may send the command as an argument list. Exit 2
with a one-line reason on stderr denies the call; exit 0 allows it. Anything
unexpected (no stdin, bad JSON, another tool) allows: a guard must never break
the host. Standard library only.
"""
import json
import os
import re
import shlex
import sys

DISPATCHER_ONLY = {'trust-reset', 'accept', 'reassign', 'adopt'}
# Read-only stash subcommands hide nothing.
STASH_READ_ONLY = {'list', 'show'}
SEPARATORS = re.compile(r'&&|\|\||[;|&\n]')


def command_text(payload):
    tool_input = payload.get('tool_input')
    command = tool_input.get('command', tool_input.get('cmd')) if isinstance(tool_input, dict) else None
    if isinstance(command, list):
        command = '\n'.join(str(part) for part in command)  # each argv item, e.g. bash -lc '<script>'
    return command if isinstance(command, str) else ''


def words(segment):
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def git_args(tokens):
    """The arguments after `git` and its global options, or None when this is not git."""
    while tokens and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', tokens[0]):
        tokens = tokens[1:]  # VAR=value prefixes
    if not tokens or os.path.basename(tokens[0]).lower() not in ('git', 'git.exe'):
        return None
    rest = tokens[1:]
    while rest and rest[0].startswith('-'):
        rest = rest[2:] if rest[0] in ('-C', '-c', '--git-dir', '--work-tree', '--namespace') else rest[1:]
    return rest


def findings(command):
    """(kind, reason) for each guarded command in ``command``; kind is 'git' or 'ledger'."""
    found = []
    for segment in SEPARATORS.split(command):
        tokens = words(segment.strip())
        args = git_args(tokens)
        if args:
            if args[0] == 'add' and any(a in ('-A', '--all', '.', './') for a in args[1:]):
                found.append(('git', "git add -A / git add . stages other agents' changes; stage your owned paths by name"))
            if args[0] == 'stash' and (len(args) == 1 or args[1] not in STASH_READ_ONLY):
                found.append(('git', "git stash hides other agents' changes; commit or report instead"))
        for index, token in enumerate(tokens):
            if token.replace(chr(92), '/').endswith('delegate_dispatch.py'):
                verbs = DISPATCHER_ONLY.intersection(tokens[index + 1:])
                if verbs:
                    found.append(('ledger', 'delegate_dispatch.py ' + sorted(verbs)[0] +
                                  " is the coordinator's command; a delegated worker or subagent may not run it"))
    return found


def worker_context(payload, environ):
    return bool(environ.get('SANDUQ_DELEGATED_RUN') or environ.get('SANDUQ_ROLE') == 'worker' or
                payload.get('agent_id') or payload.get('agent_type'))


def main(stdin=sys.stdin, environ=os.environ):
    try:
        payload = json.loads(stdin.read() or '{}')
    except (ValueError, OSError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    for kind, text in findings(command_text(payload)):
        if kind == 'git' and environ.get('SANDUQ_ROLE') != 'coordinator':
            sys.stderr.write('Sanduq guard: ' + text + ' (SANDUQ_ROLE=coordinator allows it).\n')
            return 2
        if kind == 'ledger' and worker_context(payload, environ):
            sys.stderr.write('Sanduq guard: ' + text + '.\n')
            return 2
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception:  # never crash the host on unexpected input
        code = 0
    sys.exit(code)
