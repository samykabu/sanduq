"""Tests for extensions/scripts/vendor.py: multi-directory maps, single-file maps, test exclusion and bundles."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vendor  # noqa: E402


def run(cwd, *args):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


class PlannedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = Path(self.tmp.name)
        base = self.src / 'skills/b/skills/s'
        for rel, text in {'scripts/a.py': 'a', 'scripts/tests/t.py': 't', 'docs/d.md': 'd',
                          'assets/ui/x.css': 'x', 'assets/other/y.css': 'y',
                          'SKILL.md': '---\nname: s\n---\nbody\n'}.items():
            (base / rel).parent.mkdir(parents=True, exist_ok=True)
            (base / rel).write_text(text, encoding='utf-8')
        run(self.src, 'init', '-q')
        run(self.src, '-c', 'user.name=t', '-c', 'user.email=t@t', 'add', '-A')
        run(self.src, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'x')
        self.sha = run(self.src, 'rev-parse', 'HEAD')

    def test_maps_directories_and_single_file_and_skips_tests(self):
        b = 'skills/b/skills/s/'
        rule = {'internal': True, 'map': [[b + 'scripts', 'ext/scripts'], [b + 'assets/ui', 'ext/assets/ui'],
                                          [b + 'docs', 'ext/docs'], [b + 'SKILL.md', 'ext/skills/s/SKILL.md']]}
        files = vendor.planned(self.src, self.sha, rule)
        self.assertEqual(sorted(files), ['ext/assets/ui/x.css', 'ext/docs/d.md', 'ext/scripts/a.py',
                                         'ext/skills/s/SKILL.md'])
        self.assertIn(b'internal: true', files['ext/skills/s/SKILL.md'])

    def test_missing_source_is_an_error(self):
        with self.assertRaises(ValueError):
            vendor.planned(self.src, self.sha, {'map': [['nope', 'ext/nope']]})


class LockTests(unittest.TestCase):
    def test_every_bundle_input_is_locked_at_one_ref(self):
        lock = json.loads(vendor.LOCK.read_text(encoding='utf-8'))
        for bundle, names in vendor.BUNDLES.items():
            refs = {lock['inputs'][name]['ref'] for name in names}
            self.assertEqual(len(refs), 1, f'{bundle} inputs are pinned to different releases: {refs}')


if __name__ == '__main__':
    unittest.main()
