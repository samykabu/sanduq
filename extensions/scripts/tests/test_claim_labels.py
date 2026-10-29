"""PH-04-T07: a percentage or ratio claim in README.md or a recent root CHANGELOG entry names its source or says estimated."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLAIM = re.compile(r'\b\d+(\.\d+)? ?(%|percent\b)|\b\d+(\.\d+)?x\b')
SOURCE = re.compile(r'docs/evidence/|tests/|estimated', re.I)
SINCE = '2026-10-17'  # entries before the October 2026 review are history and stay as written


def unlabelled():
    lines = [('README.md', n, line) for n, line in enumerate((ROOT / 'README.md').read_text(encoding='utf-8').splitlines(), 1)]
    recent = False
    for n, line in enumerate((ROOT / 'CHANGELOG.md').read_text(encoding='utf-8').splitlines(), 1):
        if line.startswith('## '):
            date = re.search(r'\d{4}-\d{2}-\d{2}', line)
            recent = bool(date) and date.group() >= SINCE
        elif recent:
            lines.append(('CHANGELOG.md', n, line))
    return [f'{name}:{n}' for name, n, line in lines if CLAIM.search(line) and not SOURCE.search(line)]


class ClaimLabelTests(unittest.TestCase):
    def test_percentage_and_ratio_claims_name_their_source(self):
        self.assertEqual(unlabelled(), [])

    def test_the_check_sees_an_unlabelled_claim(self):
        self.assertTrue(CLAIM.search('reads 18% fewer bytes') and not SOURCE.search('reads 18% fewer bytes'))
        self.assertTrue(SOURCE.search('41 percent (docs/evidence/benchmarks/instructions-compare.md)'))


if __name__ == '__main__':
    unittest.main()
