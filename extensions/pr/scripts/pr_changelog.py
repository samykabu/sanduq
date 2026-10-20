#!/usr/bin/env python3
"""Seed docs/<slug>/CHANGELOG.md from facts the repository already holds.

    python .specify/extensions/pr/scripts/pr_changelog.py --feature specs/<slug> [--base <ref>] [--output <path>]

Facts: spec path and branch, the bound issue and repository (`scope-source.json`), the PR (`gh pr
view`), commit subjects from `git log <base>..HEAD` (base: --base, else origin's default branch from
origin/HEAD or GitHub; when no base resolves the commit line is left out), the checked and unchecked
tasks of `tasks.md` by phase, `progress.yml` top-level entries, the stage receipts in
`workflow/checkpoint.json` and the files under `evidence/`. The facts live between `<!-- speckit-changelog:facts:start -->` and
`<!-- speckit-changelog:facts:end -->`; a rerun regenerates only that block and keeps everything
else, so edit wording and add sections outside the markers. Missing inputs leave their line out.
Prints the output path. Exit 2 when the feature directory is missing. Standard library only.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pr_publish

START, END = '<!-- speckit-changelog:facts:start -->', '<!-- speckit-changelog:facts:end -->'
TASK = re.compile(r'^\s*[-*] \[(?P<done>[ xX])\] (?P<text>.+)$')
PHASE = re.compile(r'^## (?P<title>.+)$')
SKELETON = """\
### Architecture & boundaries

### Migration

### Scope (not in this phase)
"""


def run(args, cwd):
    try:
        return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, encoding='utf-8', timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None


def output(args, cwd):
    result = run(args, cwd)
    return result.stdout.strip() if result and result.returncode == 0 else ''


def commit_subjects(root, base):
    """(base ref, subjects) through PR publishing's default-branch rule; (None, '') when no log resolves."""
    if not base:
        try:
            name = pr_publish.default_branch(root)
        except pr_publish.Failure:
            name = ''
        refs = ['origin/' + name, name] if name else []
    else:
        refs = [base]
    for ref in refs:
        result = run(['git', 'log', '--format=%s', ref + '..HEAD'], root)
        if result and result.returncode == 0:
            return ref, result.stdout.strip()
    return None, ''


def tasks_by_phase(text):
    phases, current = {}, 'Tasks'
    for line in text.splitlines():
        heading = PHASE.match(line)
        if heading:
            current = heading.group('title').strip()
            continue
        task = TASK.match(line)
        if task:
            phases.setdefault(current, []).append((task.group('done') != ' ', task.group('text').strip()))
    return phases


def facts(root, feature, base):
    lines = []
    source = {}
    if (feature / 'scope-source.json').is_file():
        source = json.loads((feature / 'scope-source.json').read_text(encoding='utf-8'))
    pr = output(['gh', 'pr', 'view', '--json', 'url', '-q', '.url'], root)
    lines += ['- Spec: `' + feature.relative_to(root).as_posix() + '/spec.md`']
    branch = output(['git', 'branch', '--show-current'], root)
    lines += ['- Branch: `' + branch + '`'] if branch else []
    lines += ['- Issue: ' + source['repo'] + '#' + str(source['issue'])] if source.get('issue') else []
    lines += ['- PR: ' + pr] if pr else []
    base, commits = commit_subjects(root, base)
    lines += ['', '## [' + date.today().isoformat() + ']', '', '### Added']
    if base:  # no resolvable base: the line is left out, never reported as "no commits"
        lines += [''] + (['- ' + s for s in commits.splitlines()] or ['- (no commits on `' + base + '..HEAD`)'])
    lines += ['', '### Changed', '']
    phases = tasks_by_phase((feature / 'tasks.md').read_text(encoding='utf-8-sig')) if (feature / 'tasks.md').is_file() else {}
    for phase, items in phases.items():
        done = [text for ok, text in items if ok]
        lines += ['- ' + phase + ': ' + '; '.join(done)] if done else []
    lines += ['', '### Tests & quality', '']
    progress = feature / 'progress.yml'
    if progress.is_file():
        lines += ['- progress.yml: ' + line.strip() for line in progress.read_text(encoding='utf-8-sig').splitlines()
                  if re.match(r'^[A-Za-z_][\w-]*:\s*\S', line)]
    checkpoint = feature / 'workflow' / 'checkpoint.json'
    if checkpoint.is_file():
        receipts = json.loads(checkpoint.read_text(encoding='utf-8')).get('receipts') or {}
        lines += ['- Stage ' + stage + ': ' + str(receipt.get('summary', '')) for stage, receipt in receipts.items()]
    evidence = sorted(p.relative_to(root).as_posix() for p in (feature / 'evidence').glob('*') if p.is_file())
    lines += ['- Evidence: ' + ', '.join('`' + p + '`' for p in evidence)] if evidence else []
    lines += ['', '### Open items', '']
    lines += ['- ' + text for items in phases.values() for ok, text in items if not ok] or ['- none']
    return '\n'.join(lines)


def render(existing, block, feature_name):
    block = START + '\n' + block + '\n' + END
    if existing and START in existing and END in existing and existing.find(END) > existing.find(START):
        return existing[:existing.find(START)] + block + existing[existing.find(END) + len(END):]
    return '# Changelog: ' + feature_name + '\n\n' + block + '\n\n' + SKELETON


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--feature', required=True, help='specs/<slug>')
    parser.add_argument('--base', help="git base ref (default: origin's default branch, from origin/HEAD or GitHub)")
    parser.add_argument('--output', help='default: docs/<slug>/CHANGELOG.md')
    parser.add_argument('--root', default='.', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    feature = (root / args.feature).resolve()
    if not feature.is_dir():
        print('missing feature directory: ' + args.feature)
        return 2
    target = root / (args.output or 'docs/' + feature.name + '/CHANGELOG.md')
    existing = target.read_text(encoding='utf-8-sig') if target.is_file() else ''
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(existing, facts(root, feature, args.base), feature.name), encoding='utf-8', newline='\n')
    print(target.relative_to(root).as_posix())
    return 0


if __name__ == '__main__':
    sys.exit(main())
