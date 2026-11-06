#!/usr/bin/env python3
"""PostToolUse check for Claude Code and Codex: a written HTML diagram must pass the skill's own checks.

Hook mode (no arguments, the host's hook JSON on stdin). Opt-in: `.specify/workflow.yml` must set
`illustrate: {hooks: {self_check: true}}` (flow or block form); otherwise, and whenever that file is missing, this
exits 0. The key is read with PyYAML when the hook's Python has it, else with a small reader for plain mappings. When a
diagram was written and the key cannot be read (invalid YAML, or anchors, aliases or tags without PyYAML), the hook
exits 2 and says how to fix it: a gate that may be on never passes silently.
For a Claude Write, Edit or MultiEdit, or a Codex `apply_patch` (every added, updated or moved file in the patch),
each written `.html` path whose content contains `<svg` gets `self_check.py`, `verify-geometry.py` and
`illustration_theme.py validate` from the installed skill (`skill/scripts/` beside this hook, that is
`.specify/extensions/illustrate/skill/scripts/`); the first failure goes to stderr with exit 2.
Anything unexpected (no stdin, bad JSON, another tool, no skill) allows: a hook must never break the host.

Management mode, run by the Workflow installer or by hand:

    python .specify/extensions/illustrate/hooks/self_check_hook.py install|uninstall|status --host claude|codex --root <project> [--json]

`install` writes one native PostToolUse entry that runs this script directly (`.claude/settings.json` or
`.codex/hooks.json`), `uninstall` removes it, and both remove the old Spec Kit dispatcher entries that ran
`speckit.illustrate.hook` (`.claude/settings.json`, `.codex/config.toml`). Unrelated hooks are kept, a rerun
changes nothing, and each prints {host, file, added, removed, needs_approval}. Codex runs a new hook only after
it is approved in `/hooks`. The entry runs this script through a one-line launcher that exits 0 when the script
is gone, so `specify extension remove illustrate` without `uninstall` leaves an inert entry, never a failing one.
"""
import json
import os
import re
import sys
from pathlib import Path

HOOK = Path(__file__).resolve()
SCRIPTS = HOOK.parent.parent / 'skill' / 'scripts'
WRITE_TOOLS = ('Write', 'Edit', 'MultiEdit', 'write_file', 'edit_file', 'apply_patch')
PATCH_PATH = re.compile(r'^\*\*\* (?:Add File|Update File|Move to): (.+?)\s*$', re.M)

ACTIONS = ('install', 'uninstall', 'status')
TAG = '--managed-by=sanduq-illustrate'
DISPATCHER = 'speckit.illustrate.hook'
HOST_FILES = {'claude': '.claude/settings.json', 'codex': '.codex/hooks.json'}
DISPATCHER_FILES = {'claude': '.claude/settings.json', 'codex': '.codex/config.toml'}
MATCHERS = {'claude': 'Write|Edit|MultiEdit', 'codex': 'apply_patch|Write|Edit|MultiEdit|write_file|edit_file'}
TIMEOUT = 60
# The installed command: exit 0 when the script is gone (extension removed without `uninstall`), else run it and keep
# its exit code (runpy lets SystemExit through). Root: CLAUDE_PROJECT_DIR, else the process cwd (Codex runs hooks
# from the session directory). No `$` or double quotes, so bash, PowerShell and cmd pass it through unchanged.
LAUNCHER = ("import os,runpy,sys;p=os.path.join(os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd(),'{path}');"
            "sys.exit(0) if not os.path.isfile(p) else runpy.run_path(p,run_name='__main__')")
# One Spec Kit `[[hooks.<Event>]]` block per handler, ending at its `speckit_marker = true` (Spec Kit's own pattern).
TOML_BLOCK = re.compile(r'\[\[hooks\.\w+\]\]\n(?:(?!\[\[hooks\.\w+\]\]).)*?speckit_marker = true\n*', re.DOTALL)


KEY_PATH = ('illustrate', 'hooks', 'self_check')
YAML_TRUE = {'true', 'True', 'TRUE', 'yes', 'Yes', 'YES', 'on', 'On', 'ON'}  # what PyYAML (YAML 1.1) loads as True
BLOCK_KEY = re.compile(r'''^(?:"([^"\\]*)"|'([^']*)'|([^\s"'#{}\[\],&*!|>%@`?-][^:]*?|-[^\s:][^:]*?))\s*:(?:\s+(.*))?$''')
FLOW_TOKEN = re.compile(r'''\s*(?:([{}\[\],:])|"([^"\\]*)"|'([^']*)'|([^\s{}\[\],:][^{}\[\],:]*))''')
FLOW_START = re.compile(r'^(?:-\s+)*(?:[^\s:][^:]*:\s+)?[\[{]')  # a value that opens a flow collection
BLOCK_SCALAR = re.compile(r'(?:^|:\s+|^-\s+)[|>][-+0-9]*$')
NEEDS_PYYAML ='anchors, aliases, tags, merge keys and block scalars need PyYAML'


class Unreadable(Exception):
    pass


def enabled(root):
    """`illustrate.hooks.self_check` is true. Raises Unreadable when the file cannot be read the way PyYAML would."""
    try:
        text = (root / '.specify' / 'workflow.yml').read_text(encoding='utf-8-sig')
    except OSError:
        return False
    if 'self_check' not in text:  # skip the parse when the key cannot be set
        return False
    try:
        import yaml
    except ImportError:
        return read_key(text)
    try:
        data = yaml.safe_load(text)
    except Exception as exc:
        raise Unreadable('invalid YAML: ' + ' '.join(str(exc).split())[:160]) from None
    return follow(data, KEY_PATH)


def follow(data, path):
    for key in path:
        data = data.get(key) if isinstance(data, dict) else None
    return data is True


def read_key(text):
    """The key without PyYAML: block and flow mappings of plain or quoted scalars, and comments. Lines it cannot
    read raise Unreadable rather than guess."""
    lines, depth, scalar = [], 0, None
    for number, raw in enumerate(text.splitlines(), 1):
        line = re.sub(r'(^|\s)#.*$', '', raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(' '))
        body = line[indent:]
        if scalar is not None and indent > scalar:
            continue  # block scalar content, never a key
        scalar = None
        if depth > 0:  # inside a multi-line flow collection: join it to the line that opened it
            lines[-1] = (*lines[-1][:2], lines[-1][2] + ' ' + body)
        elif body in ('---', '...') or body.startswith('%'):
            if lines:
                raise Unreadable(f'line {number}: more than one YAML document')
            continue
        else:
            lines.append((number, indent, body))
        if depth > 0 or FLOW_START.match(body):
            bare = re.sub(r'"[^"]*"|\'[^\']*\'', '', body)
            depth += bare.count('{') + bare.count('[') - bare.count('}') - bare.count(']')
        elif BLOCK_SCALAR.search(body):
            scalar = indent
    return block_lookup(lines, KEY_PATH)


def block_lookup(lines, path):
    """Follow path through one block mapping, given as its (line number, indent, text) lines."""
    if not lines:
        return False
    base, found = lines[0][1], None
    for index, (number, indent, body) in enumerate(lines):
        if indent > base:
            continue
        if indent < base or body.startswith('\t'):
            raise Unreadable(f'line {number}: unexpected indentation')
        if body == '-' or body.startswith('- '):
            if index == 0:
                return False  # a list, not a mapping
            continue  # an unindented list item of the key above
        match = BLOCK_KEY.match(body)
        if not match:
            raise Unreadable(f'line {number}: not a plain `key: value` line')
        if next(group for group in match.groups()[:3] if group is not None) != path[0]:
            if body.startswith('<<'):
                raise Unreadable(f'line {number}: {NEEDS_PYYAML}')
            continue
        end = next((i for i in range(index + 1, len(lines)) if lines[i][1] <= base), len(lines))
        found = (number, (match.group(4) or '').strip(), lines[index + 1:end])  # a duplicate key: the last one wins
    if found is None:
        return False
    number, rest, children = found
    if rest[:1] in ('{', '['):
        return flow_lookup(rest, path[1:], number)
    if rest[:1] in ('&', '*', '!', '|', '>') or (len(path) == 1 and children):
        raise Unreadable(f'line {number}: {NEEDS_PYYAML}')
    if len(path) == 1:
        return rest in YAML_TRUE  # a quoted "true" is a string, as in PyYAML
    return False if rest else block_lookup(children, path[1:])


def flow_lookup(text, path, number):
    """Follow path through one flow collection (`{hooks: {self_check: true}}`) of plain or quoted scalars."""
    unreadable = Unreadable(f'line {number}: a flow mapping this reader cannot parse; {NEEDS_PYYAML}')
    tokens, position = [], 0
    while text[position:].strip():
        match = FLOW_TOKEN.match(text, position)
        if not match:
            raise unreadable
        punct, double, single, plain = match.groups()
        if punct:
            tokens.append(('p', punct))
        elif plain is not None:
            if plain.strip()[:1] in ('&', '*', '!', '|', '>'):
                raise unreadable
            tokens.append(('s', plain.strip()))
        else:
            tokens.append(('q', double if double is not None else single))
        position = match.end()
    tokens.append(('end', None))
    at = [0]

    def take():
        at[0] += 1
        return tokens[at[0] - 1]

    def node():
        kind, item = take()
        if kind == 's':
            return True if item in YAML_TRUE else item
        if kind == 'q':
            return item
        if (kind, item) not in (('p', '{'), ('p', '[')):
            raise unreadable
        close = '}' if item == '{' else ']'
        result = {} if item == '{' else []
        while tokens[at[0]] != ('p', close):
            if close == '}':
                key = take()
                if key[0] not in ('s', 'q') or take() != ('p', ':'):
                    raise unreadable
                result[key[1]] = None if tokens[at[0]] in (('p', ','), ('p', close)) else node()
            else:
                result.append(node())
            if tokens[at[0]] == ('p', ','):
                take()
            elif tokens[at[0]] != ('p', close):
                raise unreadable
        take()
        return result

    data = node()
    if tokens[at[0]] != ('end', None):
        raise unreadable
    return follow(data, path)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def written_paths(payload):
    """Every path the tool wrote: Claude's `file_path`, or each Add, Update and Move target of a Codex patch."""
    tool_input = payload.get('tool_input')
    if payload.get('tool_name') not in WRITE_TOOLS:
        return []
    raw = (tool_input.get('file_path') or tool_input.get('path')) if isinstance(tool_input, dict) else None
    if isinstance(raw, str):
        return [raw]
    return list(dict.fromkeys(path for text in strings(tool_input) for path in PATCH_PATH.findall(text)))


def written_diagrams(payload, root):
    """The written .html paths that contain <svg (a moved file's old path no longer exists and drops out)."""
    found = []
    for raw in written_paths(payload):
        if not raw.lower().endswith('.html'):
            continue
        path = Path(raw)
        path = path if path.is_absolute() else root / path
        try:
            if '<svg' in path.read_text(encoding='utf-8', errors='replace'):
                found.append(path)
        except OSError:
            continue
    return found


def checks(root, path):
    python = sys.executable or 'python'
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        text = ''
    # Technical-color diagrams carry the pinned export toolbar; Illustrate 3.6 checks them with their own profile.
    profile = ['--profile', 'technical-color'] if 'html2canvas' in text and 'downloadPNG(this)' in text else []
    return (
        ('self_check.py', [python, str(SCRIPTS / 'self_check.py'), *profile, str(path)]),
        ('verify-geometry.py', [python, str(SCRIPTS / 'verify-geometry.py'), str(path)]),
        ('illustration_theme.py validate',
         [python, str(SCRIPTS / 'illustration_theme.py'), '--project-root', str(root), 'validate']),
    )


def first_failure(root, path):
    """`<script>: <first finding>` for the first failing check, or None."""
    import subprocess  # only a written diagram pays for it
    for name, argv in checks(root, path):
        run = subprocess.run(argv, capture_output=True, text=True, cwd=str(root))
        if run.returncode == 0:
            continue
        lines = [line.strip() for line in (run.stdout + run.stderr).splitlines() if line.strip()]
        lines = [line for line in lines if not line.startswith(('FAIL ', 'OK ', 'Summary:'))] or lines
        return name + ': ' + (lines[0].lstrip('- ') if lines else 'exit ' + str(run.returncode))
    return None


def main(stdin=sys.stdin, environ=os.environ):
    try:
        payload = json.loads(stdin.read() or '{}')
    except (ValueError, OSError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    root = Path(environ.get('CLAUDE_PROJECT_DIR') or payload.get('cwd') or '.').resolve()
    diagrams = written_diagrams(payload, root)  # the payload first: most writes are not diagrams
    if not diagrams or not SCRIPTS.is_dir():
        return 0
    try:
        if not enabled(root):
            return 0
    except Exception as exc:  # Unreadable, or a reader bug: either way the gate may be on
        sys.stderr.write(unreadable_message(exc) + '\n')
        return 2
    for path in diagrams:
        failure = first_failure(root, path)
        if failure:
            sys.stderr.write('Illustrate self-check: ' + failure + ' (' + str(path) + ')\n')
            return 2
    return 0


def unreadable_message(exc):
    try:
        import yaml  # noqa: F401
        fix = 'fix the YAML'
    except ImportError:
        fix = (f'install PyYAML for {sys.executable or "the Python that runs this hook"}, or write the key as plain '
               'block lines (illustrate: / hooks: / self_check: true)')
    return (f'Illustrate self-check: cannot read illustrate.hooks.self_check in .specify/workflow.yml ({exc}); {fix}. '
            'To turn the check off, set it to false and rerun the Workflow installer, or run this hook with uninstall.')


# ---- management CLI ----------------------------------------------------------------------------------------

class Refused(Exception):
    pass


def command_for(root, host):
    try:
        relative = HOOK.relative_to(root).as_posix()
    except ValueError:
        raise Refused(f'{HOOK} is outside {root}; run the copy under .specify/extensions/illustrate/hooks/') from None
    python = 'python' if sys.platform == 'win32' else 'python3'
    return f'{python} -c "{LAUNCHER.format(path=relative)}" {TAG}'


def load_json(path):
    try:
        raw = path.read_text(encoding='utf-8-sig')
    except FileNotFoundError:
        return {}
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict) or not isinstance(data.get('hooks', {}), dict):
        raise Refused(f'{path.name} has an unexpected shape; not touching it')
    return data


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.illustrate-tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


def handlers(data):
    for groups in data.get('hooks', {}).values():
        for group in groups if isinstance(groups, list) else []:
            inner = group.get('hooks') if isinstance(group, dict) else None
            yield from inner if isinstance(inner, list) else []


def strip_handlers(data, drop):
    """Remove handlers for which drop(handler) is true, and the groups and keys left empty. Returns the count."""
    removed = 0
    hooks = data.get('hooks', {})
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            inner = group.get('hooks') if isinstance(group, dict) else None
            if not isinstance(inner, list):
                kept.append(group)
                continue
            left = [h for h in inner if not drop(h)]
            removed += len(inner) - len(left)
            if left:
                kept.append(group if len(left) == len(inner) else {**group, 'hooks': left})
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if 'hooks' in data and not hooks:
        del data['hooks']
    return removed


def command_of(handler):
    command = handler.get('command') if isinstance(handler, dict) else None
    return command if isinstance(command, str) else ''


def is_ours(handler):
    return TAG in command_of(handler)


def is_dispatcher(handler):
    return DISPATCHER in command_of(handler)


def clean_toml(path):
    """Drop the Spec Kit blocks in Codex config.toml that run speckit.illustrate.hook. Returns the count."""
    try:
        text = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return 0
    removed = 0

    def drop(match):
        nonlocal removed
        if DISPATCHER not in match.group(0):
            return match.group(0)
        removed += 1
        return ''
    updated = TOML_BLOCK.sub(drop, text)
    if removed:
        write_text(path, updated)
    return removed


def manage(action, host, root):
    path = root / HOST_FILES[host]
    data = load_json(path)
    result = {'host': host, 'file': HOST_FILES[host], 'added': 0, 'removed': 0, 'needs_approval': False}
    ours = [h for h in handlers(data) if is_ours(h)]
    if action == 'status':
        dispatcher = root / DISPATCHER_FILES[host]
        text = dispatcher.read_text(encoding='utf-8', errors='replace') if dispatcher.is_file() else ''
        result.update(installed=bool(ours), dispatcher_entries=text.count(DISPATCHER))
        result['needs_approval'] = host == 'codex' and bool(ours)  # whether Codex approved it is not visible here
        return result
    group = {'matcher': MATCHERS[host], 'hooks': [{'type': 'command', 'command': command_for(root, host), 'timeout': TIMEOUT}]}
    before = json.dumps(data, sort_keys=True)
    current = [g for g in data.get('hooks', {}).get('PostToolUse') or [] if isinstance(g, dict) and g.get('hooks') == group['hooks']]
    if not (action == 'install' and len(ours) == 1 and current == [group]):  # an exact install stays as it is
        result['removed'] += strip_handlers(data, is_ours)
        if action == 'install':
            groups = data.setdefault('hooks', {}).setdefault('PostToolUse', [])
            if not isinstance(groups, list):
                raise Refused(f'{path.name} hooks.PostToolUse is not a list; not touching it')
            groups.append(group)
            result['added'] = 1
    if host == 'claude':
        result['removed'] += strip_handlers(data, is_dispatcher)
    if json.dumps(data, sort_keys=True) != before:
        write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    if host == 'codex':
        result['removed'] += clean_toml(root / DISPATCHER_FILES[host])
    result['needs_approval'] = host == 'codex' and result['added'] > 0
    return result


def cli(argv):
    import argparse
    parser = argparse.ArgumentParser(prog='self_check_hook.py', description='Manage the Illustrate post-write hook.')
    parser.add_argument('action', choices=ACTIONS)
    parser.add_argument('--host', required=True, choices=sorted(HOST_FILES))
    parser.add_argument('--root', required=True)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = manage(args.action, args.host, Path(args.root).resolve())
    except (Refused, ValueError, OSError) as exc:
        sys.stderr.write(f'illustrate hook {args.action}: {exc}\n')
        return 2
    if args.json:
        print(json.dumps(result))
    else:
        print(' '.join(f'{key}={json.dumps(value)}' for key, value in result.items()))
        if result['needs_approval']:
            print('Codex runs the new hook only after you approve it: open /hooks in Codex.')
    return 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ACTIONS:
        sys.exit(cli(sys.argv[1:]))
    try:
        code = main()
    except Exception:  # never crash the host on unexpected input
        code = 0
    sys.exit(code)
