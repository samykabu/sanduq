#!/usr/bin/env python3
"""Scan the repository for projects and refresh `.github/memory/project-memory.md`.

Walks the tree (pruning `scan.exclude` from `.specify/extensions/assure/assure-config.yml`), tests
the marker files and `package.json` dependency names the Assure commands used to spell out, classifies
each project as web, mobile, backend, infrastructure or tooling, prints one line per project and
rewrites the block between `<!-- assure-scan:start -->` and `<!-- assure-scan:end -->` in the memory
file. Text outside the markers (for example `planned/spec-only` rows) is kept. `--check` prints the
inventory and the block without writing. Stdlib only, like `deps.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

START, END = '<!-- assure-scan:start -->', '<!-- assure-scan:end -->'
MEMORY = Path('.github/memory/project-memory.md')
CONFIG = Path('.specify/extensions/assure/assure-config.yml')
# The packaged config template holds the one literal default list (scan.exclude); init copies it.
TEMPLATE = Path(__file__).resolve().parents[1] / 'assure-config.template.yml'
WORKSPACE_MARKERS = ('pnpm-workspace.yaml', 'nx.json', 'turbo.json', 'lerna.json', 'rush.json')
WEB_DEPS = {'react': 'React', 'next': 'Next.js', 'vite': 'Vite', 'react-scripts': 'CRA',
            '@angular/core': 'Angular', 'vue': 'Vue', 'nuxt': 'Nuxt', 'svelte': 'Svelte',
            '@sveltejs/kit': 'SvelteKit', '@remix-run/react': 'Remix', 'astro': 'Astro',
            '@tanstack/react-router': 'TanStack Router', 'react-router': 'React Router',
            'react-router-dom': 'React Router', 'storybook': 'Storybook'}
WEB_FILES = ('vite.config.*', 'next.config.*', 'angular.json', 'astro.config.*', 'svelte.config.*')
MOBILE_DEPS = {'react-native': 'React Native', 'expo': 'Expo', 'expo-router': 'expo-router'}
MOBILE_FILES = ('app.json', 'app.config.*', 'metro.config.*', 'android', 'ios')
BACKEND_FILES = ('*.csproj', '*.sln', 'pyproject.toml', 'go.mod', 'Cargo.toml', 'openapi.yml', 'openapi.yaml', 'openapi.json')
BACKEND_DEPS = {'express': 'Express', 'fastify': 'Fastify', '@nestjs/core': 'NestJS', 'koa': 'Koa'}
INFRA_FILES = ('Dockerfile', 'docker-compose*.y*ml', 'compose.y*ml', 'Chart.yaml', '*.tf', 'Pulumi.yaml')
TOOLING_FILES = ('extension.yml', 'plugin.json', 'preset.yml', 'action.yml')
RUNNER_DEPS = {'@playwright/test': 'playwright', 'playwright': 'playwright', 'cypress': 'cypress',
               'detox': 'detox', 'appium': 'appium', 'webdriverio': 'appium'}
SCRIPT_NAMES = ('dev', 'start', 'build', 'test', 'e2e', 'lint', 'storybook')
ROLE_ORDER = ('mobile', 'web', 'backend', 'infrastructure', 'tooling')


def read_config(path):
    """Narrow reader for assure-config.yml: top-level sections whose children are `key: value`
    scalars or `key:` followed by `- item` lines. Anything else is ignored, never mis-parsed."""
    result, section, key = {}, None, None
    if not Path(path).is_file():
        return result
    for raw in Path(path).read_text(encoding='utf-8-sig').splitlines():
        line = raw.split(' #')[0].rstrip()
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        indent = len(line) - len(line.lstrip())
        text = line.strip()
        if indent == 0 and text.endswith(':'):
            section, key = result.setdefault(text[:-1], {}), None
        elif indent == 0 and ':' in text:
            section = None
        elif section is not None and text.startswith('- ') and key is not None:
            section.setdefault(key, []).append(_scalar(text[2:]))
        elif section is not None and ':' in text and not text.startswith('- '):
            key, _, value = text.partition(':')
            key = key.strip()
            section[key] = _scalar(value) if value.strip() else []
    return result


def _scalar(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in '"\'':
        return text[1:-1]
    return {'true': True, 'false': False}.get(text, text)


DEFAULT_EXCLUDE = (read_config(TEMPLATE).get('scan') or {}).get('exclude') or []


def _package(directory):
    try:
        data = json.loads((directory / 'package.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _deps(package):
    names = set()
    for key in ('dependencies', 'devDependencies'):
        names.update((package.get(key) or {}).keys())
    return names


def _present(directory, patterns):
    return sorted({p.name for pattern in patterns for p in directory.glob(pattern)})


def classify(directory, root):
    """One inventory row for `directory`, or None when it holds no project marker."""
    package = _package(directory)
    deps = _deps(package) if package else set()
    markers = {}
    markers['mobile'] = [MOBILE_DEPS[d] for d in sorted(deps & MOBILE_DEPS.keys())] + _present(directory, MOBILE_FILES)
    markers['web'] = [WEB_DEPS[d] for d in sorted(deps & WEB_DEPS.keys())] + _present(directory, WEB_FILES)
    markers['backend'] = _present(directory, BACKEND_FILES) + [BACKEND_DEPS[d] for d in sorted(deps & BACKEND_DEPS.keys())]
    markers['infrastructure'] = _present(directory, INFRA_FILES)
    markers['tooling'] = _present(directory, TOOLING_FILES)
    # A mobile app is also a React app; a web app may also carry a Dockerfile. Mobile wins over web,
    # a product marker wins over an infrastructure or tooling one.
    role = next((r for r in ROLE_ORDER if markers[r]), 'tooling' if package else None)
    if role is None:
        return None
    stack = [m for r in ROLE_ORDER for m in markers[r]]
    if package:
        stack.insert(0, 'package.json')
    if (directory / '.github/workflows').is_dir():
        stack.append('GitHub Actions')
    scripts = package.get('scripts') or {} if package else {}
    commands = [name for name in SCRIPT_NAMES if name in scripts]
    runner = next((RUNNER_DEPS[d] for d in RUNNER_DEPS if d in deps), '')
    if not runner and (directory / '.maestro').is_dir():
        runner = 'maestro'
    if not runner and _present(directory, ('playwright.config.*',)):
        runner = 'playwright'
    public = next((d for d in ('public', 'static') if (directory / d).is_dir()), '')
    rel = directory.relative_to(root).as_posix() if directory != root else '.'
    qa_root = (Path(rel) / public / 'qa' if role == 'web' and public else Path(rel) / 'qa').as_posix()
    shell = _present(directory, ('src/routes', 'src/pages', 'src/main.*', 'src/App.*', 'pages', 'app'))
    return {'name': directory.name if directory != root else root.name, 'path': rel, 'role': role,
            'markers': stack, 'commands': commands, 'runner': runner, 'public': public, 'shell': shell,
            'qa_root': qa_root, 'docs': 'docs' if (directory / 'docs').is_dir() else ''}


def scan(root, exclude):
    projects, found = [], set()
    for current, dirs, files in os.walk(root):
        # `.specify` holds Spec Kit's installed extensions, never a project of the repository.
        dirs[:] = sorted(d for d in dirs if d not in exclude and d != '.specify')
        directory = Path(current)
        row = classify(directory, root)
        if row:
            projects.append(row)
        found.update(f for f in files if f in WORKSPACE_MARKERS)
    package = _package(root)
    if package and 'workspaces' in package:
        found.add('package.json workspaces')
    return projects, sorted(found)


def summary_lines(projects):
    return [f"{p['role']}\t{p['path']}\t{', '.join(p['markers']) or '-'}\trunner={p['runner'] or '-'}"
            f"\tcommands={','.join(p['commands']) or '-'}" for p in projects]


def render_block(projects, found, today):
    fronts = [p for p in projects if p['role'] in ('web', 'mobile')]
    others = [p for p in projects if p['role'] not in ('web', 'mobile')]
    web = [p['path'] for p in fronts if p['role'] == 'web']
    mobile = [p['path'] for p in fronts if p['role'] == 'mobile']
    out = [START, '# Project memory', '', f'Last scanned: {today}', '', '## Frontend Coverage Summary', '',
           f"- Web frontends detected: {', '.join(web) if web else 'none'}",
           f"- Mobile frontends detected: {', '.join(mobile) if mobile else 'none'}",
           '- Planned/spec-only frontends: see the rows below the end marker, if any.',
           f"- Reusable frontend paths: {', '.join(p['qa_root'] for p in fronts) if fronts else 'none'}",
           '', '## Frontend Project Inventory', '']
    if fronts:
        out += ['| Project | Path | Status | Platform | Framework | Router/app shell | Public dir | QA root | Screenshot runner | Commands | Evidence |',
                '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
        out += [f"| {p['name']} | {p['path']} | implemented | {p['role']} | {', '.join(m for m in p['markers'] if m != 'package.json') or '-'} | "
                f"{', '.join(p['shell']) or '-'} | {p['public'] or '-'} | {p['qa_root']} | {p['runner'] or '-'} | "
                f"{', '.join(p['commands']) or '-'} | {p['path']}/package.json |" for p in fronts]
    else:
        out.append('No implemented web or mobile frontend was detected.')
    out += ['', '## Detected Projects', '']
    if others:
        out += ['| Project | Path | Role | Stack markers | Commands | Docs root | QA root |', '| --- | --- | --- | --- | --- | --- | --- |']
        out += [f"| {p['name']} | {p['path']} | {p['role']} | {', '.join(p['markers']) or '-'} | {', '.join(p['commands']) or '-'} | "
                f"{p['docs'] or '-'} | {p['qa_root']} |" for p in others]
    else:
        out.append('No other project was detected.')
    out += ['', '## Scan Markers', '',
            f"- Workspace markers found: {', '.join(found) if found else 'none'}",
            f"- Frontend markers found: {', '.join(sorted({m for p in fronts for m in p['markers'] if m != 'package.json'})) or 'none'}",
            f"- Frontend markers not found: {'none' if fronts else 'no web or mobile dependency, config file or app folder in any package.json project'}",
            '', '## Maintenance Rules', '',
            '- Generated by `assure_scan.py`; rerun it instead of editing between the markers.',
            '- Add `planned/spec-only` rows below the end marker with their spec, plan or quickstart source; they survive reruns.',
            '- Verify the inventory against current marker files when frontend markers appear or disappear.',
            END]
    return '\n'.join(out) + '\n'


def merge(existing, block):
    if existing and START in existing and END in existing:
        head, rest = existing.split(START, 1)
        return head + block.rstrip('\n') + rest.split(END, 1)[1]
    return (existing.rstrip('\n') + '\n\n' if existing else '') + block


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--check', action='store_true', help='Print the inventory and block; write nothing')
    parser.add_argument('--config', type=Path, default=None, help='assure-config.yml (default: the installed one under --root)')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    config = read_config(args.config or root / CONFIG)
    exclude = set((config.get('scan') or {}).get('exclude') or DEFAULT_EXCLUDE)
    if not exclude:  # no config list and no packaged template: scanning node_modules and .git would be wrong
        raise SystemExit('assure_scan: no scan.exclude list in ' + str(CONFIG) + ' and no packaged ' + TEMPLATE.name
                         + '; reinstall the assure extension or add scan.exclude to the config')
    projects, found = scan(root, exclude)
    target = root / MEMORY
    existing = target.read_text(encoding='utf-8-sig') if target.is_file() else ''
    # Keep the previous date when nothing else changed: the memory file is a freshness input.
    previous = re.search(r'^Last scanned: (\S+)$', existing.split(START, 1)[-1].split(END, 1)[0], re.M) \
        if START in existing and END in existing else None
    block = render_block(projects, found, previous.group(1)) if previous else None
    if block is None or merge(existing, block) != existing:
        block = render_block(projects, found, date.today().isoformat())
    merged = merge(existing, block)
    print('\n'.join(summary_lines(projects)) or 'no project markers found')
    if args.check:
        print(f"memory: {'unchanged' if merged == existing else 'would write'} {MEMORY.as_posix()}")
        print(block, end='')
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        if merged != existing:
            target.write_text(merged, encoding='utf-8')
        print(f"memory: {'unchanged' if merged == existing else 'written'} {MEMORY.as_posix()}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
