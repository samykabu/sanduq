"""Catalog descriptions: one string per Assure command, in catalog form, and check_docs.py rejects drift."""
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

EXTENSION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXTENSION.parent / 'scripts'))
import check_docs  # noqa: E402

MANIFEST = EXTENSION / 'extension.yml'


class DescriptionTest(unittest.TestCase):
    def test_each_command_has_one_catalog_description(self):
        for entry in yaml.safe_load(MANIFEST.read_text(encoding='utf-8'))['provides']['commands']:
            with self.subTest(entry['name']):
                front = yaml.safe_load((EXTENSION / entry['file']).read_text(encoding='utf-8').split('---', 2)[1])
                text = entry['description']
                self.assertEqual(front['description'], text)
                self.assertLess(len(text), 300)
                self.assertRegex(text, r'^[A-Z][a-z]+s ')  # third person, what first
                self.assertIn('Use when', text)
                self.assertRegex(text, r'"[^"]+"')

    def test_check_docs_rejects_a_drifted_description(self):
        original = Path.read_text
        drifted = re.sub(r'(speckit\.assure\.init\.md\r?\n      description: )', r'\1Drifted. ',
                         original(MANIFEST, encoding='utf-8'))
        with patch.object(Path, 'read_text', lambda p, *a, **kw: drifted if p == MANIFEST else original(p, *a, **kw)):
            with self.assertRaises(SystemExit) as failure:
                check_docs.check()
        self.assertIn('speckit.assure.init: extension.yml description differs', str(failure.exception))


if __name__ == '__main__':
    unittest.main()
