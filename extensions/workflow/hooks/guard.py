#!/usr/bin/env python3
"""PreToolUse guard for Claude Code and Codex: refuse commands that hide or take over others' work.

- `git add -A`, `git add .` and `git stash` are refused in every session unless env
  SANDUQ_ROLE=coordinator (the coordinator stages owned paths by name anyway).
- `delegate_dispatch.py trust-reset|accept|reassign|adopt` are refused only in a worker context:
  env SANDUQ_DELEGATED_RUN set, env SANDUQ_ROLE=worker, or a payload carrying `agent_id` or
  `agent_type` (both hosts add these in subagent sessions). The top-level session runs them.
- `gh pr create|edit --body-file <f>` is refused in a managed project (`.specify/workflow.yml`
  present) when the sibling lint `<f minus suffix>.lint.json` (what `pr_publish.py` writes) is
  missing or its `body_sha256` is not the file's hash; `gh pr create` is refused when its head
  (`--head`, else the current branch) is the repository default branch (`origin/HEAD`), in every
  project. An unresolvable branch allows.

Reads the hook payload (JSON) on stdin. Both hosts send ``tool_name`` and
``tool_input.command``; Codex may send the command as an argument list. Exit 2
with a one-line reason on stderr denies the call; exit 0 allows it. Anything
unexpected (no stdin, bad JSON, another tool) allows: a guard must never break
the host. Standard library only.
"""
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys

DISPATCHER_ONLY = {'trust-reset', 'accept', 'reassign', 'adopt'}
# Read-only stash subcommands hide nothing.
STASH_READ_ONLY = {'list', 'show'}
SEPARATORS = re.compile(r'&&|\|\||[;|&\n]')


def option(args, *names):
    """The value of the first of ``names`` (``--x v``, ``--x=v`` or ``-x v``) in an argument list, else None."""
    for index, token in enumerate(args):
        if token in names and index + 1 < len(args):
            return args[index + 1]
        for name in names:
            if name.startswith('--') and token.startswith(name + '='):
                return token[len(name) + 1:]
    return None


def git_output(root, *args):
    try:
        result = subprocess.run(['git', '-C', root, *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ''
    return result.stdout.strip() if result.returncode == 0 else ''


def on_default_branch(root, head=None):
    """True only when the PR head (``--head``, else the current branch) and origin/HEAD resolve and are equal."""
    head = head or git_output(root, 'symbolic-ref', '--short', 'HEAD')
    default = git_output(root, 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD').split('/', 1)[-1]
    return bool(head) and bool(default) and head == default


def pr_findings(tokens, root):
    if [os.path.basename(t).lower() for t in tokens[:2]] != ['gh', 'pr'] or len(tokens) < 3 or tokens[2] not in ('create', 'edit'):
        return []
    found = []
    if tokens[2] == 'create' and on_default_branch(root, option(tokens[3:], '--head', '-H')):
        found.append(('pr', 'gh pr create on the repository default branch; create the PR from a feature branch'))
    body = option(tokens[3:], '--body-file', '-F')
    if body and os.path.isfile(os.path.join(root, '.specify/workflow.yml')):
        path = os.path.join(root, body)
        lint = os.path.splitext(path)[0] + '.lint.json'
        try:
            with open(lint, encoding='utf-8') as stream:
                recorded = json.load(stream).get('body_sha256')
            with open(path, 'rb') as stream:
                actual = hashlib.sha256(stream.read()).hexdigest()
        except (OSError, ValueError, AttributeError):
            recorded, actual = None, ''
        if recorded != actual:
            found.append(('pr', 'the PR body ' + body + ' has no matching ' + os.path.basename(lint) +
                          '; publish through pr_publish.py so the lint receipt matches the sent body'))
    return found


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


def findings(command, root='.'):
    """(kind, reason) for each guarded command in ``command``; kind is 'git', 'ledger' or 'pr'."""
    found = []
    for segment in SEPARATORS.split(command):
        tokens = words(segment.strip())
        found += pr_findings(tokens, root)
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
    root = environ.get('CLAUDE_PROJECT_DIR') or (payload.get('cwd') if isinstance(payload.get('cwd'), str) else None) or '.'
    for kind, text in findings(command_text(payload), root):
        if kind == 'git' and environ.get('SANDUQ_ROLE') != 'coordinator':
            sys.stderr.write('Sanduq guard: ' + text + ' (SANDUQ_ROLE=coordinator allows it).\n')
            return 2
        if kind == 'ledger' and worker_context(payload, environ):
            sys.stderr.write('Sanduq guard: ' + text + '.\n')
            return 2
        if kind == 'pr':
            sys.stderr.write('Sanduq guard: ' + text + '.\n')
            return 2
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception:  # never crash the host on unexpected input
        code = 0
    sys.exit(code)
