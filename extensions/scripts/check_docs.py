#!/usr/bin/env python3
"""Check active documentation: links, command and skill coverage, version tables, banned terms,
release facts (Workflow's dependency pins, extension counts, the add-all install block, root
CHANGELOG headings), the generated lifecycle hooks reference and the generated error registry page. `--write`
regenerates docs/reference/hooks.md and docs/reference/errors.md."""
import ast
import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs'
# Top-level docs/*.md covers the index, style guide and examples.
GUIDES = [ROOT / 'README.md', ROOT / 'CONTRIBUTING.md', ROOT / 'SECURITY.md', ROOT / 'extensions/README.md', DOCS / 'assets/README.md']
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
ERRORS_PAGE = DOCS / 'reference/errors.md'
ERRORS_START, ERRORS_END = '<!-- generated:errors:start -->', '<!-- generated:errors:end -->'
INTERNAL = DOCS / 'internal'
# Words that hide a hard step or add nothing; matched as whole words outside code.
BANNED = ('simply', 'just', 'obviously', 'seamless', 'seamlessly', 'leverage', 'effortless')
START, END = '<!-- generated:hooks:start -->', '<!-- generated:hooks:end -->'
PHASES = ('specify', 'clarify', 'plan', 'tasks', 'analyze', 'taskstoissues', 'implement')
# Extensions whose command frontmatter and extension.yml must carry one identical description.
SAME_DESCRIPTION = ('assure', 'user-manual', 'pr', 'project', 'illustrate', 'memory', 'progress')
FENCE = re.compile(r'^```.*?^```\s*$', re.M | re.S)
CHANGELOG = ROOT / 'CHANGELOG.md'
DEPENDENCIES = ROOT / 'extensions/workflow/dependencies.json'
INSTALL_PAGE = DOCS / 'start/install-by-host.md'
NUMBERS = ('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen '
           'sixteen seventeen eighteen nineteen twenty').split()
# "nine extensions", "all nine Spec Kit extensions", the shields.io "Spec_Kit-9_extensions" badge.
COUNT = re.compile(r'\b(' + '|'.join(NUMBERS) + r'|\d+)[\s_-]+(?:(?:spec[\s_-]kit|sanduq)[\s_-]+)?extensions\b', re.I)
NAMED_VERSION = re.compile(r'([A-Za-z][A-Za-z-]*(?: [A-Z][A-Za-z-]*)*) (\d+\.\d+\.\d+)\b')


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
    """Read stage selection from the runtime and hook ownership from reconcile.py without importing them."""
    scripts = ROOT / 'extensions/workflow/scripts'
    names = {}
    for module in ('wf_core.py', 'wf_policy.py'):  # workflow.py re-exports them from these modules (W9)
        for node in ast.parse((scripts / module).read_text(encoding='utf-8')).body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and \
                    node.targets[0].id in ('BASE_STAGES', 'COMMANDS'):
                names[node.targets[0].id] = ast.literal_eval(node.value)
            if isinstance(node, ast.FunctionDef) and node.name == 'stages':
                exec(compile(ast.Module([node], []), module, 'exec'), names)
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


def error_registry():
    """`wf_core.ERRORS` loaded from the source tree (the module needs nothing but the shared helpers)."""
    scripts = ROOT / 'extensions/workflow/scripts'
    sys.path.insert(0, str(ROOT / 'extensions/scripts/shared'))
    spec = importlib.util.spec_from_file_location('wf_core', scripts / 'wf_core.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ERRORS


def render_errors():
    out = ['Generated from `ERRORS` in `extensions/workflow/scripts/wf_core.py`; regenerate with',
           '`python extensions/scripts/check_docs.py --write`. A CLI error whose code is listed here carries the same',
           '`explain` and `next` fields in its JSON output. `<feature>` is the feature directory, `specs/<slug>`.', '',
           '| Code | What happened and why | Next command |', '| --- | --- | --- |']
    for code, (what, why, command) in sorted(error_registry().items()):
        what, why, command = (text.replace('|', '\\|') for text in (what, why, command))  # a pipe splits the cell
        out.append(f'| `{code}` | {what} {why} | `{command}` |')
    return '\n'.join(out) + '\n'


def generated_text(current, page, start, end, render):
    if start not in current or end not in current:
        raise SystemExit(f'{page.relative_to(ROOT)}: generated markers missing')
    head, rest = current.split(start, 1)
    return head + start + '\n' + render() + end + rest.split(end, 1)[1]


def errors_text(current):
    return generated_text(current, ERRORS_PAGE, ERRORS_START, ERRORS_END, render_errors)


def hooks_text(current):
    if START not in current or END not in current:
        raise SystemExit(f'{HOOKS_PAGE.relative_to(ROOT)}: generated markers missing')
    head, rest = current.split(START, 1)
    return head + START + '\n' + render_hooks() + END + rest.split(END, 1)[1]


def version_key(version):
    return tuple(int(part) for part in version.split('.'))


def release_facts(manifests, texts):
    """Version copies, extension counts and changelog headings that drift between releases."""
    errors = []
    versions = {m['extension']['id']: str(m['extension']['version']) for m in manifests}

    def pins(node, where):
        for key, value in node.items():
            if isinstance(value, dict):
                yield from pins(value, f'{where}.{key}')
            else:
                yield f'{where}.{key}', key, value
    deps = json.loads(DEPENDENCIES.read_text(encoding='utf-8'))
    for section in ('required', 'selected', 'optional'):
        for where, name, pinned in pins(deps.get(section) or {}, section):
            if versions.get(name) != pinned:
                errors.append(f'{DEPENDENCIES.relative_to(ROOT)}: {where} pins {pinned}, extension.yml has '
                              f'{versions.get(name, "no such extension")} (run release.py bump)')
    for source, text in texts.items():
        if source in SAMPLES:
            continue
        for number, line in ((m.group(1), text.count('\n', 0, m.start()) + 1) for m in COUNT.finditer(text)):
            count = int(number) if number.isdigit() else NUMBERS.index(number.lower())
            if count != len(versions):
                errors.append(f'{source.relative_to(ROOT)}:{line}: says {number} extensions; there are {len(versions)}')
    block = re.search(r'^## All \w+ extensions\n(.*?)(?=^## )', texts[INSTALL_PAGE], re.M | re.S)
    added = set(re.findall(r'specify extension add ([a-z][a-z0-9-]*)', block.group(1))) if block else set()
    if added != set(versions):
        errors.append(f'{INSTALL_PAGE.relative_to(ROOT)}: the add-all block differs from the extensions: '
                      f'missing {sorted(set(versions) - added)}, extra {sorted(added - set(versions))}')
    catalog = {k: v['version'] for k, v in json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8'))['extensions'].items()}
    changelog = CHANGELOG.read_text(encoding='utf-8')
    headings = [(n, line) for n, line in enumerate(changelog.splitlines(), 1) if line.startswith('## ')]
    preamble = changelog.find('All notable changes')
    if headings and (preamble < 0 or changelog.count('\n', 0, preamble) + 1 > headings[0][0]):
        errors.append('CHANGELOG.md: the "All notable changes" preamble must come before the first entry')
    for n, line in headings:
        if not re.search(r'\b\d{4}-\d{2}-\d{2}\b', line):
            errors.append(f'CHANGELOG.md:{n}: heading has no YYYY-MM-DD date')
        if '(unreleased)' in line:
            errors.append(f'CHANGELOG.md:{n}: use "(pending release)" at the end of the heading, not "(unreleased)"')
        if '(pending release)' in line:
            if not line.endswith(' (pending release)'):
                errors.append(f'CHANGELOG.md:{n}: "(pending release)" must end the heading')
            published = [f'{name} {v}' for name, v in NAMED_VERSION.findall(line)
                         if name.lower().replace(' ', '-') in catalog
                         and version_key(v) <= version_key(catalog[name.lower().replace(' ', '-')])]
            if published:
                errors.append(f'CHANGELOG.md:{n}: "(pending release)" but catalog.json already lists '
                              f'{", ".join(published)} (release.py promote clears it)')
    return errors


def lower_bound(spec):
    match = re.search(r'>=\s*(\d+(?:\.\d+)*)', str(spec or ''))
    return match and match.group(1)


def same_version(a, b):
    a, b = version_key(a), version_key(b)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) == b + (0,) * (width - len(b))


def version_drift(manifests):
    """The Requires row, the README's "describes X.Y.Z" and old "(unreleased)" headings agree with each manifest."""
    errors = []
    for manifest in manifests:
        meta, requires = manifest['extension'], manifest.get('requires') or {}
        ext, version = meta['id'], str(meta['version'])
        # {spoken name: (manifest lower bound, required)}; "Illustrate 2.x" reads as 2.0.0.
        bounds = {d['id'].replace('-', ' '): (lower_bound(d.get('version')), d.get('required', True))
                  for d in requires.get('extensions') or []}
        bounds['spec kit'] = (lower_bound(requires.get('speckit_version')), False)
        bounds.update({t['name']: (lower_bound(t.get('version')), False) for t in requires.get('tools') or []})
        page = DOCS / 'extensions' / (ext + '.md')
        row = re.search(r'^\| Requires \|(.*)\|\s*$', page.read_text(encoding='utf-8'), re.M) if page.is_file() else None
        if row:
            where = f'{page.relative_to(ROOT)}: Requires row'
            for name, (bound, required) in bounds.items():
                named = re.search(r'\b' + re.escape(name) + r'\b(?: (\d+(?:\.\d+)*)(?:\.x)?\b)?', row.group(1), re.I)
                if required and not named:
                    errors.append(f'{where} does not name {name}, which extension.yml requires')
                elif named and named.group(1) and bound and not same_version(named.group(1), bound):
                    errors.append(f'{where} says {named.group(0)}; extension.yml requires {name} >={bound}')
        readme = ROOT / 'extensions' / ext / 'README.md'
        if readme.is_file():
            for n, line in enumerate(readme.read_text(encoding='utf-8').splitlines(), 1):
                for described in re.findall(r'\bdescribes [A-Z][\w -]*? (\d+\.\d+\.\d+)\b', line):
                    if described != version:
                        errors.append(f'{readme.relative_to(ROOT)}:{n}: describes {described}; extension.yml has '
                                      f'{version} (fix or delete the sentence)')
        changelog = ROOT / 'extensions' / ext / 'CHANGELOG.md'
        if changelog.is_file():
            released = False  # an "## Unreleased" heading may only sit above the manifest version's entry
            for n, line in enumerate(changelog.read_text(encoding='utf-8').splitlines(), 1):
                if not line.startswith('## '):
                    continue
                heading = re.search(r'\d+\.\d+\.\d+', line)
                if heading and version_key(heading.group()) <= version_key(version):
                    released = True
                if 'unreleased' in line.lower() and released:
                    errors.append(f'{changelog.relative_to(ROOT)}:{n}: "{line[3:]}" is marked unreleased below '
                                  f'{version}, the manifest version')
    return errors


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
    manifests = []
    for path in sorted(ROOT.glob('extensions/*/extension.yml')):
        manifest = yaml.safe_load(path.read_text(encoding='utf-8'))
        manifests.append(manifest)
        meta = manifest['extension']
        entries = manifest['provides']['commands']
        commands += len(entries)
        for entry in entries:
            if meta['id'] in SAME_DESCRIPTION:
                front = (path.parent / entry['file']).read_text(encoding='utf-8').split('---', 2)[1]
                if yaml.safe_load(front).get('description') != entry.get('description'):
                    errors.append(f'{entry["name"]}: extension.yml description differs from {entry["file"]} frontmatter')
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
    errors += release_facts(manifests, texts)
    errors += version_drift(manifests)
    hooks = HOOKS_PAGE.read_text(encoding='utf-8')
    if hooks_text(hooks) != hooks:
        errors.append(f'{HOOKS_PAGE.relative_to(ROOT)} is stale: run check_docs.py --write')
    registry_page = ERRORS_PAGE.read_text(encoding='utf-8')
    if errors_text(registry_page) != registry_page:
        errors.append(f'{ERRORS_PAGE.relative_to(ROOT)} is stale: run check_docs.py --write')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Documentation OK: {len(GUIDES)} guides, {documented} of {commands} commands, '
          f'{portable_ok} of {len(portable)} vendored portable skills, {len(skill_paths)} skill sources, '
          f'both lifecycle views current, no banned terms, overlays, links, versions, pins, counts and changelog headings.')


if __name__ == '__main__':
    if '--write' in sys.argv[1:]:
        HOOKS_PAGE.write_bytes(hooks_text(HOOKS_PAGE.read_text(encoding='utf-8')).encode('utf-8'))
        print(f'Wrote {HOOKS_PAGE.relative_to(ROOT)}')
        ERRORS_PAGE.write_bytes(errors_text(ERRORS_PAGE.read_text(encoding='utf-8')).encode('utf-8'))
        print(f'Wrote {ERRORS_PAGE.relative_to(ROOT)}')
    check()
