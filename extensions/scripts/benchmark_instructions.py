#!/usr/bin/env python3
"""Measure the instruction load of Sanduq extensions (optimization round 2, stream B0).

For each extension it reads `extension.yml` and measures every command file, every skill file and
every file those tell the agent to read (one level deep): bytes, words, prohibitions, script calls,
prose steps, catalog description checks, and paragraphs duplicated across files.

    python benchmark_instructions.py --repo <checkout> --out <json> [--md <file>]
                                     [--extensions a,b] [--compare <before.json>]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

DEFAULT = ['assure', 'user-manual', 'pr', 'project', 'illustrate', 'memory', 'progress']
SKILL_GLOBS = ['skills/*/SKILL.ext.md', 'skill/SKILL.md', 'assets/skill/SKILL.md']
INTERPRETERS = {'python', 'python3', 'node', 'bash', 'sh', 'pwsh', 'gh', 'git'}
# Heuristic: a description whose first word is one of these opens with an imperative, not third person.
IMPERATIVE = {'generate', 'create', 'run', 'write', 'archive', 'configure', 'consult', 'inspect', 'process',
              'review', 'queue', 'print', 'pick', 'force', 'draw', 'import', 'export', 'set', 'show', 'resolve',
              'update', 'analyze', 'analyse', 'produce', 'make', 'turn', 'sync', 'initialize', 'initialise',
              'audit', 'choose', 'interview', 'finalize', 'finalise', 'add', 'advance', 'select', 'redraw'}
LINK_EXTS = ('.md', '.yml', '.yaml', '.json', '.py')
LINK_DIRS = ('references/', 'skills/', 'docs/', '.specify/extensions/')
PROHIBITION = re.compile(r"\b(never|do not|don't|must not|not allowed|forbidden|refuse[sd]?|prohibited|"
                         r"under no circumstances)\b", re.I)
STEP = re.compile(r'^\s*\d+[.)]\s')
SPAN = re.compile(r'`([^`\n]+)`')
MDLINK = re.compile(r'\]\(([^)\s]+)\)')
TOKEN = re.compile(r'[A-Za-z0-9_.~/-]+')
INVOKED = re.compile(r'\b(?:python3?|node|bash|sh|pwsh)\s+\S+')  # a script a call runs, not a file to read
WHEN = re.compile(r'\b(use when|when|after|before)\b', re.I)
TRIGGER = re.compile(r'"[^"]{3,}"|\basked to\b', re.I)
PARAGRAPHS = defaultdict(set)  # normalised paragraph -> files it appears in (filled by stats)


def first(text):
    parts = text.strip().split()
    return parts[0] if parts else ''


def stats(path, key):
    text = path.read_text(encoding='utf-8', errors='replace')
    script_calls = prose_steps = 0
    fence = False
    for line in text.splitlines():
        if line.strip().startswith('```'):
            fence = not fence
        elif fence:
            script_calls += first(line) in INTERPRETERS
        else:
            prose_steps += bool(STEP.match(line))
            script_calls += any(first(span) in INTERPRETERS for span in SPAN.findall(line))
    for paragraph in re.split(r'\n\s*\n', text):
        norm = ' '.join(paragraph.replace('`', '').lower().split())
        if len(norm.split()) >= 25:
            PARAGRAPHS[norm].add(key)
    words = len(text.split())
    prohibitions = len(PROHIBITION.findall(text))
    return {'bytes': path.stat().st_size, 'words': words, 'prohibitions': prohibitions,
            'prohibitions_per_100_words': round(prohibitions * 100 / words, 2) if words else 0,
            'script_calls': script_calls, 'prose_steps': prose_steps}


def links(text):
    found = MDLINK.findall(text)
    for span in SPAN.findall(text):
        found += TOKEN.findall(INVOKED.sub('', span))
    out = set()
    for tok in found:
        tok = tok.split('#')[0].rstrip('.')
        name = tok.rsplit('/', 1)[-1]
        if tok.startswith(('/', 'http')) or tok.endswith(('/', '-')) or name in LINK_EXTS or name.startswith('-'):
            continue  # absolute or external, or a fragment left by a placeholder such as `<type>.md`
        if tok.endswith(LINK_EXTS) or any(d in tok for d in LINK_DIRS):
            out.add(tok)
    return sorted(out)


def resolve(link, owner, ext_root, repo):
    if link.startswith('.specify/extensions/'):
        bases = [repo / 'extensions' / link[len('.specify/extensions/'):]]
    else:
        bases = [owner.parent / link, ext_root / link, repo / link]
    for base in bases:
        # The installed skill is SKILL.md; the source tree keeps it as SKILL.ext.md.
        for c in (base, base.with_name('SKILL.ext.md') if base.name == 'SKILL.md' else base):
            if c.is_file() and repo in c.resolve().parents:
                return c.resolve()
    return None


def describe(desc):
    words = desc.split()
    lead = re.sub(r'\W', '', words[0]).lower() if words else ''
    return {'chars': len(desc), 'under_1024': len(desc) < 1024, 'third_person': lead not in IMPERATIVE,
            'has_what': len(words) >= 5, 'has_when': bool(WHEN.search(desc)), 'has_triggers': bool(TRIGGER.search(desc))}


def failing(d):
    return [k for k in ('under_1024', 'third_person', 'has_what', 'has_when', 'has_triggers') if not d[k]]


def measure_extension(repo, ext):
    root = repo / 'extensions' / ext
    manifest = yaml.safe_load((root / 'extension.yml').read_text(encoding='utf-8'))
    hooks, events = manifest.get('hooks') or {}, manifest.get('events') or {}
    hooked = {h.get('command') for h in [*hooks.values(), *events.values()] if isinstance(h, dict)}
    files = {}

    def rel(path):
        return path.resolve().relative_to(repo).as_posix()

    def measured(path):
        key = rel(path)
        if key not in files:
            files[key] = stats(path, key)
        return files[key]

    def entry(path):
        s = measured(path)
        linked, scripts, missing = {}, {}, []
        for link in links(path.read_text(encoding='utf-8', errors='replace')):
            target = resolve(link, path, root, repo)
            if target is None:
                missing.append(link)
            elif target.suffix == '.py':
                scripts[rel(target)] = target.stat().st_size  # run, not read: shown, not counted
            elif target != path.resolve():
                linked[rel(target)] = measured(target)['bytes']
        return {**s, 'linked': linked, 'scripts': scripts, 'missing': missing,
                'instruction_bytes': s['bytes'] + sum(linked.values())}

    commands = {}
    for c in manifest['provides']['commands']:
        e = entry(root / c['file'])
        d = describe(c.get('description') or '')
        e['description'] = {'text': c.get('description') or '', **d, 'failing': failing(d)}
        e['hook_only'] = c['name'] in hooked and not (d['has_when'] or d['has_triggers'])
        commands[c['name']] = e
    skills = {}
    for pattern in SKILL_GLOBS:
        for path in sorted(root.glob(pattern)):
            e = entry(path)
            refs = sorted((path.parent / 'references').glob('*.md'))
            e['references'] = len(refs)
            e['references_bytes'] = sum(r.stat().st_size for r in refs)
            skills[rel(path)] = e
    total_bytes = sum(f['bytes'] for f in files.values())
    words = sum(f['words'] for f in files.values())
    prohibitions = sum(f['prohibitions'] for f in files.values())
    totals = {'instruction_bytes': total_bytes, 'instruction_tokens': total_bytes // 4, 'words': words,
              'prohibitions': prohibitions, 'prohibitions_per_100_words': round(prohibitions * 100 / words, 2) if words else 0,
              'script_calls': sum(f['script_calls'] for f in files.values()),
              'prose_steps': sum(f['prose_steps'] for f in files.values()),
              'descriptions_failing': sum(bool(c['description']['failing']) for c in commands.values()),
              'files': len(files)}
    return {'version': str(manifest['extension']['version']), 'catalog_entries': len(commands),
            'catalog_chars': sum(c['description']['chars'] for c in commands.values()),
            'hooks': sorted(hooks), 'events': sorted(events), 'commands': commands, 'skills': skills, 'totals': totals}


def measure(repo, extensions):
    repo = Path(repo).resolve()
    PARAGRAPHS.clear()
    result = {ext: measure_extension(repo, ext) for ext in extensions}
    duplicates = [{'text': norm[:80], 'words': len(norm.split()), 'files': sorted(paths)}
                  for norm, paths in PARAGRAPHS.items() if len(paths) > 1]
    duplicates.sort(key=lambda d: (-len(d['files']) * d['words'], d['text']))
    keys = ['instruction_bytes', 'instruction_tokens', 'words', 'prohibitions', 'script_calls', 'prose_steps',
            'descriptions_failing', 'files']
    totals = {k: sum(e['totals'][k] for e in result.values()) for k in keys}
    totals['prohibitions_per_100_words'] = round(totals['prohibitions'] * 100 / totals['words'], 2) if totals['words'] else 0
    totals['catalog_entries'] = sum(e['catalog_entries'] for e in result.values())
    totals['catalog_chars'] = sum(e['catalog_chars'] for e in result.values())
    totals['duplicate_paragraphs'] = len(duplicates)
    head = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip()
    return {'meta': {'repo': str(repo), 'commit': head, 'measured_at': datetime.now(timezone.utc).isoformat(),
                     'extensions': list(extensions)},
            'extensions': result, 'duplicates': duplicates, 'totals': totals}


def markdown(result):
    lines = [f'# Instruction benchmark: {result["meta"]["repo"]} @ {result["meta"]["commit"]}', '']
    for ext, e in result['extensions'].items():
        lines += [f'## {ext} {e["version"]}', '',
                  '| file | bytes | linked bytes | instruction bytes | proh/100w | script calls | prose steps | description |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
        for name, c in e['commands'].items():
            flags = ', '.join(c['description']['failing']) or 'ok'
            if c['hook_only']:
                flags += '; hook_only'
            lines.append(f'| {name} | {c["bytes"]} | {sum(c["linked"].values())} | {c["instruction_bytes"]} | '
                         f'{c["prohibitions_per_100_words"]} | {c["script_calls"]} | {c["prose_steps"]} | {flags} |')
        for name, s in e['skills'].items():
            lines.append(f'| {name} | {s["bytes"]} | {sum(s["linked"].values())} | {s["instruction_bytes"]} | '
                         f'{s["prohibitions_per_100_words"]} | {s["script_calls"]} | {s["prose_steps"]} | '
                         f'skill; references {s["references"]} files, {s["references_bytes"]} bytes |')
        lines.append('')
    lines += ['## Summary', '',
              '| extension | version | instruction bytes | tokens | words | proh/100w | script calls | prose steps | '
              'descriptions failing | catalog entries | catalog chars |',
              '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for ext, e in result['extensions'].items():
        t = e['totals']
        lines.append(f'| {ext} | {e["version"]} | {t["instruction_bytes"]} | {t["instruction_tokens"]} | {t["words"]} | '
                     f'{t["prohibitions_per_100_words"]} | {t["script_calls"]} | {t["prose_steps"]} | '
                     f'{t["descriptions_failing"]}/{e["catalog_entries"]} | {e["catalog_entries"]} | {e["catalog_chars"]} |')
    t = result['totals']
    lines.append(f'| all | | {t["instruction_bytes"]} | {t["instruction_tokens"]} | {t["words"]} | '
                 f'{t["prohibitions_per_100_words"]} | {t["script_calls"]} | {t["prose_steps"]} | '
                 f'{t["descriptions_failing"]}/{t["catalog_entries"]} | {t["catalog_entries"]} | {t["catalog_chars"]} |')
    lines += ['', f'## Duplicates (top 25 of {len(result["duplicates"])})', '',
              '| paragraph | words | files |', '| --- | ---: | --- |']
    for d in result['duplicates'][:25]:
        lines.append(f'| {d["text"].replace("|", "/")} | {d["words"]} | {", ".join(d["files"])} |')
    return '\n'.join(lines) + '\n'


def metrics(result):
    """Flatten one result into ordered {metric: number} for --compare."""
    values = {'totals.' + k: v for k, v in result['totals'].items()}
    for ext, e in result['extensions'].items():
        values[f'{ext}.catalog_entries'] = e['catalog_entries']
        values[f'{ext}.catalog_chars'] = e['catalog_chars']
        values.update({f'{ext}.{k}': v for k, v in e['totals'].items()})
        values.update({f'{ext}.{name}.instruction_bytes': c['instruction_bytes'] for name, c in e['commands'].items()})
    return values


def delta(before, after):
    if before is None or after is None:
        return 'n/a'
    if before == 0:
        return '0%' if after == 0 else 'new'
    return f'{(after - before) / before * 100:+.1f}%'


def compare(before, after):
    a, b = metrics(before), metrics(after)
    lines = [f'Before: {before["meta"]["repo"]} @ {before["meta"]["commit"]}',
             f'After: {after["meta"]["repo"]} @ {after["meta"]["commit"]}', '',
             '| metric | before | after | delta |', '| --- | ---: | ---: | ---: |']
    for key in dict.fromkeys([*a, *b]):
        lines.append(f'| {key} | {a.get(key, "-")} | {b.get(key, "-")} | {delta(a.get(key), b.get(key))} |')
    return '\n'.join(lines) + '\n'


# Self-check of the regexes and heuristics this file documents.
assert len(PROHIBITION.findall("Never push. Do not stash; don't refuse. A refusal is fine.")) == 4
assert [STEP.match(l) is not None for l in ('1. a', ' 2) b', '10.x', '- c')] == [True, True, False, False]
assert links('Read `.specify/extensions/x/skills/y/SKILL.md`, run `python scripts/a.py`, see [z](references/z.md#top); '
             'write `<type>.md` to `docs/`.') == ['.specify/extensions/x/skills/y/SKILL.md', 'references/z.md']
assert failing(describe('Generate the PR body.')) == ['third_person', 'has_what', 'has_when', 'has_triggers']
assert failing(describe('Writes the PR body after implementation; use when asked to "open a PR".')) == []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--repo', type=Path, required=True, help='Sanduq checkout to measure')
    parser.add_argument('--out', type=Path, required=True, help='JSON output path')
    parser.add_argument('--md', type=Path, help='Also write the Markdown tables to this file')
    parser.add_argument('--extensions', default=','.join(DEFAULT), help='Comma-separated extension ids')
    parser.add_argument('--compare', type=Path, help='Earlier JSON result; prints a delta table against it')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # duplicated paragraphs may carry non-cp1252 glyphs
    result = measure(args.repo, [e for e in args.extensions.split(',') if e])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    text = markdown(result)
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(text, encoding='utf-8')
    print(text)
    if args.compare:
        print(compare(json.loads(args.compare.read_text(encoding='utf-8')), result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
