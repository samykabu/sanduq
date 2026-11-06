"""release.py bump writes every source copy of a version; promote drops the root CHANGELOG pending marker."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release  # noqa: E402

MANIFEST = '''schema_version: '1.0'
extension:
  id: pr
  name: Sanduq Pull Requests  # display name
  version: "4.3.0"
  repository: https://github.com/samykabu/sanduq
requires:
  speckit_version: ">=1.0.0"
  version: "4.3.0"
'''
INDEX = '''# Index

| Extension | Source version | Commands |
| --- | --- | ---: |
| [pr](pr/README.md) | 4.3.0 | 2 |
| [project](project/README.md) | 2.3.0 | 2 |
'''
CHANGELOG = '''# Changelog

## 2026-10-20 — Workflow 1.15.0, PR 4.4.0 (pending release)

- Next.

## 2026-10-19 — Project 2.4.0 (pending release)

- Other.
'''


class ReleaseBumpTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        ext = self.root / 'extensions'
        (ext / 'pr').mkdir(parents=True)
        (ext / 'workflow').mkdir()
        (ext / 'pr' / 'extension.yml').write_bytes(MANIFEST.encode())
        (ext / 'README.md').write_bytes(INDEX.encode())
        release.write(ext / 'workflow/dependencies.json',
                      {'schema_version': 1, 'required': {'pr': '4.3.0', 'project': '2.3.0'},
                       'selected': {'qa': {'assure': '2.4.0'}}, 'optional': {'progress': '1.3.0'}})
        release.write(ext / 'pending-releases.json', {'schema_version': 1, 'versions': {}, 'status': 'released'})
        self.before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def read(self, rel):
        return (self.root / rel).read_bytes().decode()

    def test_bump_writes_every_copy_and_nothing_else(self):
        result = release.bump('pr', '4.4.0', self.root)
        self.assertEqual(sorted(result['written']), ['extensions/README.md', 'extensions/pending-releases.json',
                                                     'extensions/pr/extension.yml', 'extensions/workflow/dependencies.json'])
        manifest = self.read('extensions/pr/extension.yml')
        self.assertEqual(manifest, MANIFEST.replace('version: "4.3.0"\n  repository', 'version: "4.4.0"\n  repository'))
        self.assertIn('  version: "4.3.0"\n', manifest)  # the requires block is untouched
        self.assertIn('| [pr](pr/README.md) | 4.4.0 | 2 |', self.read('extensions/README.md'))
        self.assertIn('| [project](project/README.md) | 2.3.0 | 2 |', self.read('extensions/README.md'))
        deps = json.loads(self.read('extensions/workflow/dependencies.json'))
        self.assertEqual(deps['required'], {'pr': '4.4.0', 'project': '2.3.0'})
        pending = json.loads(self.read('extensions/pending-releases.json'))
        self.assertEqual((pending['versions'], pending['status']), ({'pr': '4.4.0'}, 'implementation-in-progress'))
        self.assertNotIn(b'\r\n', (self.root / 'extensions/workflow/dependencies.json').read_bytes())

    def test_bump_keeps_crlf_and_each_quote_style(self):
        """A Windows checkout (core.autocrlf) has CRLF manifests; only the version value may change."""
        for quote in ('"', "'", ''):
            for newline in ('\r\n', '\n'):
                with self.subTest(quote=quote, newline=newline):
                    old, new = (f'{quote}{v}{quote}\n  repository' for v in ('4.3.0', '4.4.1'))
                    text = MANIFEST.replace('"4.3.0"\n  repository', old)
                    (self.root / 'extensions/pr/extension.yml').write_bytes(text.replace('\n', newline).encode())
                    (self.root / 'extensions/README.md').write_bytes(INDEX.encode())
                    release.bump('pr', '4.4.1', self.root)
                    self.assertEqual(self.read('extensions/pr/extension.yml'), text.replace(old, new).replace('\n', newline))

    def test_second_bump_is_a_no_op_and_a_lower_version_is_refused(self):
        release.bump('pr', '4.4.0', self.root)
        after = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(release.bump('pr', '4.4.0', self.root)['written'], [])
        with self.assertRaisesRegex(ValueError, 'lower than the source version'):
            release.bump('pr', '4.3.9', self.root)
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, after)

    def test_unknown_extension_changes_nothing(self):
        with self.assertRaisesRegex(ValueError, 'Unknown extension'):
            release.bump('nope', '1.0.0', self.root)
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, self.before)

    def test_promote_clears_only_headings_naming_a_promoted_version(self):
        (self.root / 'CHANGELOG.md').write_bytes(CHANGELOG.encode())
        cleared = release.clear_pending_headings({'pr': '4.4.0'}, self.root)
        self.assertEqual(cleared, ['## 2026-10-20 — Workflow 1.15.0, PR 4.4.0'])
        self.assertEqual(self.read('CHANGELOG.md'), CHANGELOG.replace('PR 4.4.0 (pending release)', 'PR 4.4.0'))
        self.assertEqual(release.clear_pending_headings({'pr': '4.4.0'}, self.root), [])


if __name__ == '__main__':
    unittest.main()
