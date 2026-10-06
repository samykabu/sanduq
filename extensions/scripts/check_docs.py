#!/usr/bin/env python3
"""Check active documentation links, source coverage, and extension version tables."""
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[2]
GUIDES = [ROOT / 'README.md', ROOT / 'CONTRIBUTING.md', ROOT / 'skills/README.md',
          ROOT / 'extensions/README.md', ROOT / 'docs/assets/README.md']
GUIDES += [ROOT / 'docs' / name for name in (
    'README.md', 'getting-started.md', 'skills.md', 'extensions.md', 'skill-guide.md',
    'workflow-guide.md', 'workflow-operations.md', 'sanduq-delivery-usage.md', 'documentation-review.md')]
GUIDES += sorted(ROOT.glob('extensions/*/README.md'))


def anchors(text):
    result, counts = set(), {}
    # Fenced shell comments are not headings.
    text = re.sub(r'^```.*?^```\s*$', '', text, flags=re.M | re.S)
    for heading in re.findall(r'^#{1,6}\s+(.+)', text, re.M):
        slug = re.sub(r'[^\w\- ]', '', re.sub(r'<[^>]*>', '', heading).lower()).replace(' ', '-')
        n = counts.get(slug, 0)
        counts[slug] = n + 1
        result.add(slug + (f'-{n}' if n else ''))
    result.update(re.findall(r'\bid=["\']([^"\']+)', text))
    return result


def check():
    errors = []
    texts = {p: p.read_text(encoding='utf-8') for p in GUIDES}
    for source, text in texts.items():
        text = re.sub(r'^```.*?^```\s*$', '', text, flags=re.M | re.S)
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
            elif link.fragment and target.suffix == '.md':
                content = texts.get(target) or target.read_text(encoding='utf-8')
                if unquote(link.fragment) not in anchors(content):
                    errors.append(f'{source.relative_to(ROOT)}: missing anchor {raw}')

    reference = texts[ROOT / 'docs/extensions.md']
    lifecycle = texts[ROOT / 'docs/skill-guide.md']
    all_text = '\n'.join(texts.values())
    index = texts[ROOT / 'extensions/README.md']
    commands = 0
    for path in sorted(ROOT.glob('extensions/*/extension.yml')):
        manifest = yaml.safe_load(path.read_text(encoding='utf-8'))
        meta = manifest['extension']
        entries = manifest['provides']['commands']
        commands += len(entries)
        for entry in entries:
            name = '$' + entry['name'].replace('.', '-')
            if not re.search(re.escape(name) + r'(?![\w-])', reference):
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
    skill_paths = sorted(ROOT.glob('skills/**/SKILL.md'))
    skill_paths += [p for p in ROOT.glob('extensions/**/SKILL.md') if 'tests' not in p.parts]
    for path in skill_paths:
        if path.relative_to(ROOT).as_posix() not in all_text:
            errors.append(f'skill source not documented: {path.relative_to(ROOT)}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Documentation OK: {len(GUIDES)} guides, {commands} commands, {len(skill_paths)} skill sources, overlays, links, and versions.')


if __name__ == '__main__':
    check()
