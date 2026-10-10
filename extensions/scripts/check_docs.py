#!/usr/bin/env python3
"""Check active documentation: links, command and skill coverage, version tables, banned terms,
and the generated lifecycle hooks reference. `--write` regenerates docs/reference/hooks.md."""
import ast
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs'
# Top-level docs/*.md covers the index, style guide, examples and forwarding stubs.
GUIDES = [ROOT / 'README.md', ROOT / 'CONTRIBUTING.md', ROOT / 'extensions/README.md', DOCS / 'assets/README.md']
GUIDES += sorted(DOCS.glob('*.md'))
for folder in ('start', 'scenarios', 'extensions', 'workflow', 'reference'):
    GUIDES += sorted((DOCS / folder).glob('*.md'))
GUIDES += sorted(ROOT.glob('extensions/*/README.md'))
# The sample manual is example product content: links are checked, wording is not.
SAMPLES = [DOCS / 'examples/booking-manual/README.md'] + sorted(DOCS.glob('examples/booking-manual/docs/**/*.md'))
GUIDES += SAMPLES
COMMANDS_PAGE = DOCS / 'reference/commands.md'
LIFECYCLE_PAGE = DOCS / 'workflow/lifecycle.md'
HOOKS_PAGE = DOCS / 'reference/hooks.md'
INTERNAL = DOCS / 'internal'
# Words that hide a hard step or add nothing; matched as whole words outside code.
BANNED = ('simply', 'just', 'obviously', 'seamless', 'seamlessly', 'leverage', 'effortless')
START, END = '<!-- generated:hooks:start -->', '<!-- generated:hooks:end -->'
PHASES = ('specify', 'clarify', 'plan', 'tasks', 'analyze', 'taskstoissues', 'implement')
FENCE = re.compile(r'^```.*?^```\s*$', re.M | re.S)


def anchors(text):
    result, counts = set(), {}
    # Fenced shell comments are not headings.
    text = FENCE.sub('', text)
    for heading in re.findall(r'^#{1,6}\s+(.+)', text, re.M):
        slug = re.sub(r'[^\w\- ]', '', re.sub(r'<[^>]*>', '', heading).lower()).replace(' ', '-')
        n = counts.get(slug, 0)
        counts[slug] = n + 1
        result.add(slug + (f'-{n}' if n else ''))
    result.update(re.findall(r'\bid=["\']([^"\']+)', text))
    return result


def manifest_hooks():
    """Yield (extension, event, hook) for every hook declared in an extension manifest."""
    for path in sorted(ROOT.glob('extensions/*/extension.yml')):
        manifest = yaml.safe_load(path.read_text(encoding='utf-8'))
        for event, entries in (manifest.get('hooks') or {}).items():
            for hook in entries if isinstance(entries, list) else [entries]:
                yield manifest['extension']['id'], event, hook


def event_key(event):
    when, _, phase = event.partition('_')
    return (PHASES.index(phase) if phase in PHASES else len(PHASES), phase, when != 'before')


def workflow_rules():
    """Read stage selection from workflow.py and hook ownership from reconcile.py without importing them."""
    scripts = ROOT / 'extensions/workflow/scripts'
    tree = ast.parse((scripts / 'workflow.py').read_text(encoding='utf-8'))
    names = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and \
                node.targets[0].id in ('BASE_STAGES', 'COMMANDS'):
            names[node.targets[0].id] = ast.literal_eval(node.value)
        if isinstance(node, ast.FunctionDef) and node.name == 'stages':
            exec(compile(ast.Module([node], []), 'workflow.py', 'exec'), names)
    tree = ast.parse((scripts / 'reconcile.py').read_text(encoding='utf-8'))
    owned = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                 and getattr(n.targets[0], 'id', '') == 'OWNED')
    rule = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                and getattr(n.targets[0], 'id', '') == 'managed')
    managed = compile(ast.Expression(rule), 'reconcile.py', 'eval')
    return names, lambda ext, event, command: bool(
        eval(managed, {'OWNED': owned}, {'hook': {'extension': ext, 'command': command}, 'event': event}))


def render_hooks():
    rows = sorted(manifest_hooks(), key=lambda r: (event_key(r[1]), r[2].get('priority', 10), r[0]))
    out = ['## Manifest defaults', '',
           'Generated from each `extensions/*/extension.yml`. This is what Spec Kit registers when you',
           'install an extension, before any init command changes it. Lower priority runs first.', '',
           '| Phase | When | Extension | Command | Mode | Priority |', '| --- | --- | --- | --- | --- | ---: |']
    for ext, event, hook in rows:
        when, _, phase = event.partition('_')
        mode = 'optional' if hook.get('optional', True) else 'mandatory'
        out.append(f"| {phase} | {when} | {ext} | `{hook['command']}` | {mode} | {hook.get('priority', '')} |")
    out += ['', '## Preset overlays', '',
            'Generated from `presets/*/preset.yml`. An overlay runs Sanduq policy before the upstream command.', '',
            '| Preset | Command | Strategy |', '| --- | --- | --- |']
    for path in sorted(ROOT.glob('presets/*/preset.yml')):
        manifest = yaml.safe_load(path.read_text(encoding='utf-8'))
        for item in manifest['provides'].get('templates', []):
            out.append(f"| {manifest['preset']['id']} | `{item['replaces']}` | {item.get('strategy', 'replace')} |")
    names, managed = workflow_rules()
    stage_of = {command: stage for stage, command in names['COMMANDS'].items()}
    selection = {}
    for qa in (False, True):
        for manual in (False, True):
            for stage in names['stages']({'processes': {'qa': qa, 'user_manual': manual}}):
                selection.setdefault(stage, set()).add((qa, manual))
    labels = {4: 'always', 2: None}
    out += ['', '## Managed Workflow', '',
            'Generated from `BASE_STAGES`, `COMMANDS` and `stages()` in `extensions/workflow/scripts/workflow.py`,',
            'and from the hook-ownership rule in `extensions/workflow/scripts/reconcile.py`. The dispatcher runs',
            'these stages in order. A stage named `workflow:…` is performed by Workflow itself.', '',
            '| # | Stage | Command | Runs when |', '| ---: | --- | --- | --- |']
    for n, stage in enumerate(names['BASE_STAGES'], 1):
        combos = selection.get(stage, set())
        when = labels.get(len(combos)) or ('QA selected' if all(q for q, _ in combos) else 'User Manual selected')
        out.append(f"| {n} | `{stage}` | `{names['COMMANDS'][stage]}` | {when} |")
    out += ['', 'When `speckit.workflow.reconcile` runs, it sets `enabled: false` on each extension hook it owns.',
            'The dispatcher then runs that command as a stage, so it never runs twice. Other hooks keep',
            'their manifest mode.', '',
            '| Phase | When | Extension | Command | Under Workflow |', '| --- | --- | --- | --- | --- |']
    for ext, event, hook in rows:
        when, _, phase = event.partition('_')
        command = hook['command']
        if managed(ext, event, command):
            stage = stage_of.get(command)
            state = f'disabled; runs as stage `{stage}`' if stage else 'disabled; the dispatcher owns this step'
        else:
            state = 'kept'
        out.append(f'| {phase} | {when} | {ext} | `{command}` | {state} |')
    return '\n'.join(out) + '\n'


def hooks_text(current):
    if START not in current or END not in current:
        raise SystemExit(f'{HOOKS_PAGE.relative_to(ROOT)}: generated markers missing')
    head, rest = current.split(START, 1)
    return head + START + '\n' + render_hooks() + END + rest.split(END, 1)[1]


def check():
    errors = []
    texts = {p: p.read_text(encoding='utf-8') for p in GUIDES}
    for source, text in texts.items():
        text = FENCE.sub('', text)
        destinations = re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', text)
        destinations += re.findall(r'\b(?:href|src|srcset)=["\']([^"\']+)', text)
        for raw in destinations:
            raw = raw.strip().strip('<>')
            if '<' in raw or urlsplit(raw).scheme or raw.startswith('//'):
                continue
            link = urlsplit(raw)
            target = (source.parent / unquote(link.path)).resolve() if link.path else source
            if not target.exists():
                errors.append(f'{source.relative_to(ROOT)}: missing {raw}')
            elif INTERNAL in target.parents or target == INTERNAL:
                if source != ROOT / 'CONTRIBUTING.md':
                    errors.append(f'{source.relative_to(ROOT)}: user page links to docs/internal: {raw}')
            elif link.fragment and target.suffix == '.md':
                content = texts.get(target) or target.read_text(encoding='utf-8')
                if unquote(link.fragment) not in anchors(content):
                    errors.append(f'{source.relative_to(ROOT)}: missing anchor {raw}')
        if source not in SAMPLES:
            prose = re.sub(r'`[^`\n]*`|<!--.*?-->|\]\([^)]*\)', ' ', text, flags=re.S)
            for word in re.findall(r'\b(' + '|'.join(BANNED) + r')\b', prose, re.I):
                errors.append(f'{source.relative_to(ROOT)}: banned term "{word}"')

    reference = texts[COMMANDS_PAGE]
    lifecycle = texts[LIFECYCLE_PAGE]
    all_text = '\n'.join(texts.values())
    index = texts[ROOT / 'extensions/README.md']
    commands = documented = 0
    for path in sorted(ROOT.glob('extensions/*/extension.yml')):
        manifest = yaml.safe_load(path.read_text(encoding='utf-8'))
        meta = manifest['extension']
        entries = manifest['provides']['commands']
        commands += len(entries)
        for entry in entries:
            name = '$' + entry['name'].replace('.', '-')
            if re.search(re.escape(name) + r'(?![\w-])', reference):
                documented += 1
            else:
                errors.append(f'command has no usage example: {name}')
        name = meta['id']
        row = f"| [{name}]({name}/README.md) | {meta['version']} | {len(entries)} |"
        if row not in index:
            errors.append(f'extension table differs from source: {name}')
    for path in sorted(ROOT.glob('presets/*/preset.yml')):
        manifest = yaml.safe_load(path.read_text(encoding='utf-8'))
        for item in manifest.get('provides', {}).get('templates', []):
            name = '$' + item['name'].replace('.', '-')
            if item.get('type') == 'command' and not re.search(re.escape(name) + r'(?![\w-])', lifecycle):
                errors.append(f'overlay missing from lifecycle guide: {item["name"]}')
    skill_paths = sorted(p for pattern in ('SKILL.md', 'SKILL.ext.md') for p in ROOT.glob('extensions/**/' + pattern)
                         if 'tests' not in p.parts)
    for path in skill_paths:
        if path.relative_to(ROOT).as_posix() not in all_text:
            errors.append(f'skill source not documented: {path.relative_to(ROOT)}')
    vendored = {f for item in json.loads((ROOT / 'vendor.lock.json').read_text(encoding='utf-8'))['inputs'].values()
                for f in item['files']}
    portable = [p for p in skill_paths if any(f.startswith(p.parent.relative_to(ROOT).as_posix() + '/') for f in vendored)]
    portable_ok = sum(p.relative_to(ROOT).as_posix() in all_text for p in portable)
    hooks = HOOKS_PAGE.read_text(encoding='utf-8')
    if hooks_text(hooks) != hooks:
        errors.append(f'{HOOKS_PAGE.relative_to(ROOT)} is stale: run check_docs.py --write')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Documentation OK: {len(GUIDES)} guides, {documented} of {commands} commands, '
          f'{portable_ok} of {len(portable)} vendored portable skills, {len(skill_paths)} skill sources, '
          f'both lifecycle views current, no banned terms, overlays, links, and versions.')


if __name__ == '__main__':
    if '--write' in sys.argv[1:]:
        HOOKS_PAGE.write_bytes(hooks_text(HOOKS_PAGE.read_text(encoding='utf-8')).encode('utf-8'))
        print(f'Wrote {HOOKS_PAGE.relative_to(ROOT)}')
    check()
