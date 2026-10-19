#!/usr/bin/env python3
"""Audit generated QA manuals (HTML): every `<img>` has non-empty `alt` and sits in a `<figure>`
with a `<figcaption>`, every relative `src`/`href` resolves, the "Development-only draft" marker is
present, and no secret-shaped value survived redaction. Prints one `path:line: message` per finding
and exits 1 when there is any. `--feature` audits the `.html` outputs recorded in the feature's
document state instead of explicit paths (exits 0 with `skipped no-state` when none is recorded).
Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

# Copied from the user-manual audit script (audit_manual.py) so the two packages stay independent,
# with its placeholder allowlist plus the HTML-escaped `<`; a value also ends at the next tag.
SECRET = re.compile(r"(?i)(api[_-]?key|client[_-]?secret|password|access[_-]?token|refresh[_-]?token)\s*[:=]\s*[\"']?([^\s\"'<]{8,})")
PLACEHOLDERS = ('redacted', 'example', 'placeholder', '<', '&lt;', '${')
DRAFT = 'development-only draft'
LINK_ATTRS = {'img': 'src', 'a': 'href', 'link': 'href', 'script': 'src', 'source': 'src', 'video': 'src', 'audio': 'src'}


class Manual(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.images, self.text = [], [], []
        self.figure = None  # (line, had_caption, images) while inside a <figure>

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        line = self.getpos()[0]
        if tag in LINK_ATTRS and attrs.get(LINK_ATTRS[tag]):
            self.links.append((line, attrs[LINK_ATTRS[tag]]))
        if tag == 'figure':
            self.figure = [line, False, []]
        if tag == 'figcaption' and self.figure:
            self.figure[1] = True
        if tag == 'img':
            self.images.append((line, (attrs.get('alt') or '').strip(), self.figure is not None))
            if self.figure:
                self.figure[2].append(line)

    def handle_endtag(self, tag):
        if tag == 'figure' and self.figure:
            if self.figure[2] and not self.figure[1]:
                for line in self.figure[2]:
                    self.images = [(l, a, False) if l == line else (l, a, f) for l, a, f in self.images]
            self.figure = None

    def handle_data(self, data):
        self.text.append(data)


def resolve(path, link, root):
    """A root-relative link is served from the nearest `public`/`static` ancestor, else the repository root."""
    if link.startswith('/'):
        base = next((p for p in path.parents if p.name in ('public', 'static')), root)
        return base / link.lstrip('/')
    return path.parent / link


def audit_file(path, root=None):
    path = Path(path)
    root = Path(root or Path.cwd())
    errors = []
    try:
        raw = path.read_text(encoding='utf-8-sig')
    except OSError as exc:
        return [f'{path}:0: unreadable ({exc})']
    parser = Manual()
    parser.feed(raw)
    for line, alt, captioned in parser.images:
        if not alt:
            errors.append(f'{path}:{line}: <img> without alt text')
        if not captioned:
            errors.append(f'{path}:{line}: <img> without a <figure> and <figcaption>')
    for line, target in parser.links:
        parts = urlsplit(target)
        if parts.scheme or target.startswith(('//', '#')) or not parts.path:
            continue
        if not resolve(path, unquote(parts.path), root).exists():
            errors.append(f'{path}:{line}: unresolved link {target}')
    if DRAFT not in raw.lower():
        errors.append(f'{path}:0: missing "Development-only draft" marker')
    for match in SECRET.finditer(raw):
        if any(marker in match.group(2).lower() for marker in PLACEHOLDERS):
            continue
        line = raw.count('\n', 0, match.start()) + 1
        errors.append(f'{path}:{line}: secret-like value for {match.group(1)}')
    return errors


def outputs_from_state(root, feature):
    state = root / '.specify/extensions/assure/state' / f'{Path(feature).name}-document.json'
    if not state.is_file():
        return None
    saved = json.loads(state.read_text(encoding='utf-8-sig'))
    return [root / p for p in (saved.get('outputs') or {}) if p.endswith(('.html', '.htm'))]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('paths', nargs='*', type=Path, help='Generated manual HTML files')
    parser.add_argument('--feature', type=Path, help='Audit the HTML outputs recorded for this feature')
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--json', action='store_true', help='Print {"files": N, "errors": [...]} instead of lines')
    args = parser.parse_args(argv)
    paths = list(args.paths)
    if args.feature:
        recorded = outputs_from_state(args.repo_root.resolve(), args.feature)
        if recorded is None:
            print('skipped no-state')
            return 0
        paths += recorded
    if not paths:
        parser.error('give at least one manual path or --feature')
    errors = [e for p in paths for e in audit_file(p, args.repo_root.resolve())]
    if args.json:
        print(json.dumps({'files': len(paths), 'errors': errors}))
    else:
        print('\n'.join(errors) if errors else f'ok files={len(paths)}')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
