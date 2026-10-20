"""release.py promote returns every path it wrote, and the release job stages each of them (X17, after #98)."""
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release  # noqa: E402

WORKFLOW = release.ROOT / '.github/workflows/release-extensions.yml'
MANIFEST = ('schema_version: "1.0"\nextension:\n  id: example\n  name: Example\n  version: "1.1.0"\n'
            '  repository: https://github.com/samykabu/sanduq\n')
CHANGELOG = ('# Changelog\n\nAll notable changes.\n\n## 2026-10-21 — Example 1.1.0 (pending release)\n\n- New.\n\n'
             '## 2026-10-01 — Example 1.0.0\n\n- Old.\n')


def staged_paths():
    """The paths of the release job's `git add` line (the job commits only what it stages)."""
    lines = [line.strip() for line in WORKFLOW.read_text(encoding='utf-8').splitlines() if line.strip().startswith('git add ')]
    assert len(lines) == 1, lines
    return shlex.split(lines[0])[2:]


def covered(path, staged):
    return any(token in ('.', '-A', '--all') or path == token or path.startswith(token.rstrip('/') + '/')
               for token in staged)


class PromoteWrittenTests(unittest.TestCase):
    def promote(self, changelog):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        (root / '.gitignore').write_text('dist/\n')
        (root / 'extensions/example').mkdir(parents=True)
        (root / 'extensions/example/extension.yml').write_text(MANIFEST)
        (root / 'extensions/example/README.md').write_text('Example')
        if changelog:
            (root / 'CHANGELOG.md').write_bytes(changelog.encode())
        catalog = {'extensions': {'example': {'version': '1.0.0'}}}
        release.write(root / 'catalog.json', catalog)
        release.write(root / 'extensions/catalog.json', catalog)
        release.write(root / 'extensions/pending-releases.json', {'versions': {'example': '1.1.0'}, 'status': 'ready'})
        for args in (('init', '-q'), ('config', 'user.name', 'Test'), ('config', 'user.email', 'test@example.invalid'),
                     ('config', 'core.autocrlf', 'false'), ('add', '.'), ('commit', '-qm', 'Source')):
            subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)
        plan = release.prepare(root)
        release.write(root / 'dist/release-verification.json', {
            'plan_sha256': release.sha(root / 'dist/release-plan.json'),
            'assets': [{'tag': x['tag'], 'sha256': x['sha256'], 'verified': True} for x in plan['releases']]})
        result = release.promote(root, verifier=lambda *args: None)
        changed = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=root, check=True,
                                 capture_output=True, text=True).stdout.splitlines()
        return result['written'], sorted(line[3:] for line in changed)

    def test_written_lists_exactly_what_promote_changed(self):
        for changelog in (CHANGELOG, None):
            with self.subTest(changelog=bool(changelog)):
                written, changed = self.promote(changelog)
                self.assertEqual(sorted(written), changed)
                self.assertEqual('CHANGELOG.md' in written, bool(changelog))

    def test_release_job_stages_every_path_promote_can_write(self):
        staged = staged_paths()
        written, _ = self.promote(CHANGELOG)
        self.assertEqual(len(written), 4)
        self.assertEqual([path for path in written if not covered(path, staged)], [])


if __name__ == '__main__':
    unittest.main()
