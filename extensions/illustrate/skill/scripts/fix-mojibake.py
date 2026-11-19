#!/usr/bin/env python3
"""Replace mojibake sequences in UTF-8 files with their original characters.

The repo had a few files saved by a tool that interpreted UTF-8 as cp1252 and
re-saved as UTF-8, producing classic mojibake (em-dash --> 'â€"', section sign
--> 'Â§', right arrow --> 'â†'', etc.). This script rewrites those sequences
in-place without touching legitimately-encoded UTF-8 elsewhere in the file.

    python scripts/fix-mojibake.py FILE [FILE ...]

Exits 2 without arguments, 1 when a file is missing or is not UTF-8.
"""
import sys

PAIRS = [
    ('â€”', '—'),  # em-dash
    ('â€“', '–'),  # en-dash
    ('â€™', '’'),  # right single quote
    ('â€˜', '‘'),  # left single quote
    ('â€œ', '“'),  # left double quote
    ('â€', '”'),  # right double quote
    ('â€¦', '…'),  # horizontal ellipsis
    ('â€¢', '•'),  # bullet
    ('â†’', '→'),  # right arrow
    ('â†‘', '←'),  # left arrow
    ('â†‘', '↑'),  # up arrow (same prefix collision - rare)
    ('â†“', '↓'),  # down arrow
    ('â‰¤', '≤'),  # less-than-or-equal
    ('â‰¥', '≥'),  # greater-than-or-equal
    ('Ã—',       '×'),  # multiplication sign
    ('Ã·',       '÷'),  # division sign
    ('Â§',       '§'),  # section sign
    ('Â°',       '°'),  # degree
    ('Â½',       '½'),  # one-half
    ('Â«',       '«'),  # «
    ('Â»',       '»'),  # »
    ('Â©',       '©'),  # ©
    ('Â®',       '®'),  # ®
]


def fix(path: str) -> int:
    with open(path, 'rb') as f:
        raw = f.read()
    had_bom = raw.startswith(b'\xef\xbb\xbf')
    if had_bom:
        raw = raw[3:]
    text = raw.decode('utf-8')
    n = 0
    for bad, good in PAIRS:
        if bad in text:
            n += text.count(bad)
            text = text.replace(bad, good)
    if n == 0 and not had_bom:
        print(f'{path}: no mojibake found')
        return 0
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    note = f' (also stripped BOM)' if had_bom else ''
    print(f'{path}: replaced {n} sequence(s){note}')
    return n


def main(paths: list[str]) -> int:
    if not paths:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    status = 0
    for p in paths:
        try:
            fix(p)
        except FileNotFoundError:
            print(f'{p}: no such file', file=sys.stderr)
            status = 1
        except UnicodeDecodeError as exc:
            print(f'{p}: not UTF-8 ({exc.reason} at byte {exc.start}); left unchanged', file=sys.stderr)
            status = 1
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
