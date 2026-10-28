#!/usr/bin/env python3
"""PreToolUse guard for Claude Code and Codex: refuse commands that hide or take over others' work.

- `git add -A|-u|.`, `git commit -a` and `git stash` are refused in every session unless env
  SANDUQ_ROLE=coordinator is set where the host was launched (it then applies to every subagent;
  the refusal does not name it). The guard is advisory: it sees only the host's shell tools
  (matcher `Bash|PowerShell|shell`), so a script, an alias or another tool bypasses it.
- `delegate_dispatch.py trust-reset|accept|reassign|adopt` are refused only in a worker context:
  env SANDUQ_DELEGATED_RUN set, env SANDUQ_ROLE=worker, or a payload carrying `agent_id` or
  `agent_type` (both hosts add these in subagent sessions). The top-level session runs them.
- `delegate_dispatch.py ... --confirm-fallback` is the user's confirmation of a substitute model and
  `delegate_dispatch.py attest-native` is the top-level session's own attestation of a native subagent
  stage; both are refused in that worker context and in a delegated orchestrator (env
  SANDUQ_DELEGATED_ROLE set).
- `gh pr create|edit --body-file <f>` is refused in a managed project (`.specify/workflow.yml`
  present) when the sibling lint `<f minus suffix>.lint.json` (what `pr_publish.py` writes) is
  missing or its `body_sha256` is not the file's hash (a path holding an unexpanded shell variable such as
  `$R/body.md` is allowed: the hook cannot resolve it); an inline `--body`/`-b` is refused there too
  (no lint receipt can cover it); `gh pr create` is refused when its head
  (`--head`, else the current branch) is the repository default branch (`origin/HEAD`), in every
  project. An unresolvable branch allows.
- A `gh`/`curl`/`wget` command that posts content (a comment, review, PR/issue body, `gh api` fields or input,
  a curl/wget request body or a POST/PATCH/PUT) and carries a `sanduq-gate-waiver` marker in its own arguments or
  in a file it names (`--body-file`, `-F`, `--input`, `@file`) is refused in every session: a waiver is the
  owner's word, never the agent's (delivery-policy.md). Reading or grepping for the marker stays allowed.

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
# The top-level session's own word, refused wherever --confirm-fallback is (SAMY-03).
TOP_LEVEL_ONLY = {'attest-native'}
# Read-only stash subcommands hide nothing.
STASH_READ_ONLY = {'list', 'show'}
WAIVER_MARKER = 'sanduq-gate-waiver'
SEND_METHODS = {'POST', 'PATCH', 'PUT'}
WAIVER_REASON = ('a CI gate waiver is the owner decision; an agent may not post one. Ask the owner to post '
                 'it (docs/workflow/delivery-policy.md, One-off rule waiver)')
BY_NAME = 'stage your owned paths by name (git add -- <path>...)'
SEPARATORS = re.compile(r'&&|\|\||[;|&\n]')
UNEXPANDED = re.compile(r'\$|%[A-Za-z_]\w*%|`')  # a shell variable or substitution the hook cannot expand


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
    managed = os.path.isfile(os.path.join(root, '.specify/workflow.yml'))
    if managed and any(t in ('--body', '-b') or t.startswith('--body=') for t in tokens[3:]):
        found.append(('pr', 'an inline --body cannot carry a lint receipt in a managed project; publish through '
                            '.specify/extensions/pr/scripts/pr_publish.py (or pass --body-file with its lint)'))
    body = option(tokens[3:], '--body-file', '-F')
    if managed and tokens[2] == 'create' and not body:  # --fill, a template or an editor body: none carries a lint
        found.append(('pr', 'gh pr create needs a linted --body-file in a managed project; publish through '
                            '.specify/extensions/pr/scripts/pr_publish.py'))
    # R7: the hook sees the command before the shell expands it, so `$R/body.md` or `%R%\body.md` names no file
    # it can read; such a path is allowed (the guard is advisory and `complete` recomputes the lint anyway).
    if body and managed and not UNEXPANDED.search(body):
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


def short_flag(args, letters, *longs):
    """True when one of ``longs`` is present or a short option cluster (``-am``) carries one of ``letters``."""
    return any(a in longs or re.fullmatch('-[A-Za-z]*[' + letters + '][A-Za-z]*', a) for a in args)


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


def shell_segments(command):
    """Token lists of each pipeline/sequence segment, splitting only on separators outside quotes."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|()\n')
        lexer.whitespace, lexer.whitespace_split = ' \t\r', True
        tokens = list(lexer)
    except ValueError:
        return [words(segment.strip()) for segment in SEPARATORS.split(command)]
    segments, current = [], []
    for token in tokens:
        if token and set(token) <= set(';&|()\n'):
            segments.append(current)
            current = []
        else:
            current.append(token)
    return segments + [current]


def method_sends(args):
    """True when ``-X``/``--method``/``--request`` (``-XPOST`` too) names POST, PATCH or PUT."""
    method = option(args, '-X', '--method', '--request')
    method = method or next((a[2:] for a in args if a.startswith('-X') and len(a) > 2), None)
    return (method or '').upper() in SEND_METHODS


def posts_waiver(tokens, root):
    """True when this segment is a gh/curl/wget call that sends content carrying the waiver marker."""
    while tokens and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', tokens[0]):
        tokens = tokens[1:]  # VAR=value prefixes
    name = re.sub(r'\.exe$', '', os.path.basename(tokens[0]).lower()) if tokens else ''
    args = tokens[1:]
    if name == 'gh':
        sends = (args[:2] in (['pr', 'comment'], ['issue', 'comment'], ['pr', 'review'], ['pr', 'create'],
                              ['pr', 'edit'], ['issue', 'create'], ['issue', 'edit']) or
                 args[:1] == ['api'] and (method_sends(args) or any(
                     a in ('-f', '-F', '--field', '--raw-field', '--input') or
                     a.startswith(('--field=', '--raw-field=', '--input=')) for a in args)))
    elif name in ('curl', 'wget'):
        sends = method_sends(args) or any(
            a in ('-d', '-F', '-T', '--form', '--upload-file') or re.match(r'-[dF].|--(data|form|post-|body-)', a)
            for a in args)
    else:
        return False
    if not sends:
        return False
    if any(WAIVER_MARKER in a for a in args):
        return True
    files = [option(args, '--body-file', '-F', '--input', '--upload-file', '-T', '--post-file')]
    files += [m.group(1) for m in (re.match(r'(?:-d|[^@]*=)?@(.+)', a) for a in args) if m]  # @f, -d@f, k=@f
    for path in filter(None, files):
        try:
            with open(os.path.join(root, path), encoding='utf-8', errors='replace') as stream:
                if WAIVER_MARKER in stream.read():
                    return True
        except OSError:
            pass
    return False


def findings(command, root='.'):
    """(kind, reason) for each guarded command in ``command``; kind is 'git', 'ledger', 'fallback', 'pr' or 'waiver'."""
    found = []
    if any(posts_waiver(tokens, root) for tokens in shell_segments(command)):
        found.append(('waiver', WAIVER_REASON))
    for segment in SEPARATORS.split(command):
        tokens = words(segment.strip())
        found += pr_findings(tokens, root)
        args = git_args(tokens)
        if args:
            if args[0] == 'add' and (short_flag(args[1:], 'Au', '--all', '--update') or any(a in ('.', './') for a in args[1:])):
                found.append(('git', "git add -A / -u / . stages other agents' changes; " + BY_NAME))
            if args[0] == 'commit' and short_flag(args[1:], 'a', '--all'):
                found.append(('git', "git commit -a commits other agents' changes; " + BY_NAME + ' and commit without -a'))
            if args[0] == 'stash' and (len(args) == 1 or args[1] not in STASH_READ_ONLY):
                found.append(('git', "git stash hides other agents' changes; commit or report instead"))
        for index, token in enumerate(tokens):
            if token.replace(chr(92), '/').endswith('delegate_dispatch.py'):
                verbs = DISPATCHER_ONLY.intersection(tokens[index + 1:])
                if verbs:
                    found.append(('ledger', 'delegate_dispatch.py ' + sorted(verbs)[0] +
                                  " is the coordinator's command; a delegated worker or subagent may not run it"))
                if any(t == '--confirm-fallback' or t.startswith('--confirm-fallback=') for t in tokens[index + 1:]):
                    found.append(('fallback', "delegate_dispatch.py --confirm-fallback is the user's confirmation; a "
                                              'delegated worker, orchestrator or subagent may not give it. Show the '
                                              'user the FALLBACK_CONFIRMATION_REQUIRED message instead'))
                if TOP_LEVEL_ONLY.intersection(tokens[index + 1:]):
                    found.append(('fallback', "delegate_dispatch.py attest-native is the top-level session's own "
                                              'attestation; a delegated worker, orchestrator or subagent may not '
                                              'give it. Report the stage result to the top-level session instead'))
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
            sys.stderr.write('Sanduq guard: ' + text + '.\n')
            return 2
        if kind == 'fallback' and (worker_context(payload, environ) or environ.get('SANDUQ_DELEGATED_ROLE')):
            sys.stderr.write('Sanduq guard: ' + text + '.\n')
            return 2
        if kind == 'ledger' and worker_context(payload, environ):
            sys.stderr.write('Sanduq guard: ' + text + '.\n')
            return 2
        if kind in ('pr', 'waiver'):
            sys.stderr.write('Sanduq guard: ' + text + '.\n')
            return 2
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception:  # never crash the host on unexpected input
        code = 0
    sys.exit(code)
