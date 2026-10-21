"""The one packaging exclusion list leaves human-only and unrunnable files out and keeps every runtime asset."""
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import package  # noqa: E402

REQUIRED = {
    'progress': ('README.md', 'scripts/progress.py', 'scripts/hook.py', 'skills/progress/SKILL.md',
                 'skills/progress/references/verbs.md', 'assets/ui/index.html'),
    'workflow': ('assets/delegate-task/SKILL.md', 'assets/delegate-task/delegate.mjs',
                 'assets/delegate-task/check-runner.mjs', 'assets/delegate-task/contracts/result-schema-v2.md'),
    'illustrate': ('skill/SKILL.md', 'skill/scripts/self_check.py', 'skill/scripts/export_diagram.py',
                   'skill/scripts/build-exploded-examples.py', 'skill/scripts/generate-hand-variants.cjs',
                   'skill/package.json'),
}
# Text an agent reads or runs: a name here must never be excluded.
AGENT_GLOBS = ('extension.yml', 'commands/**/*.md', 'skills/**/*.md', 'skill/SKILL.md', 'skill/references/*.md',
               'hooks/*.py', 'assets/delegate-task/SKILL.md', 'assets/delegate-task/references/*.md',
               'assets/delegate-task/contracts/*.md')


class PackageExclusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.names, cls.readmes = {}, {}
        for extension in REQUIRED:
            archive = Path(cls.tmp.name) / (extension + '.zip')
            package.package(extension, output=archive)
            with zipfile.ZipFile(archive) as z:
                cls.names[extension] = set(z.namelist())
                cls.readmes[extension] = z.read(extension + '/README.md').decode('utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_excluded_paths_are_absent_and_required_assets_ship(self):
        for extension, names in self.names.items():
            self.assertFalse([n for n in names if package.excluded(n)], extension)
            for rel in REQUIRED[extension]:
                self.assertIn(f'{extension}/{rel}', names)

    def test_every_exclusion_matches_a_source_file(self):
        for path in package.EXCLUDE_PATHS:
            self.assertTrue((package.ROOT / 'extensions' / path).exists(), path)

    def test_no_agent_route_names_an_excluded_file(self):
        for path in package.EXCLUDE_PATHS:
            extension, rel = path.split('/', 1)
            if Path(rel).name.startswith('README') or rel == 'docs':
                continue  # READMEs are for people; Progress's verbs.md names docs/ only to say it is not needed
            needle = '/'.join(rel.split('/')[-2:])
            root = package.ROOT / 'extensions' / extension
            for pattern in AGENT_GLOBS:
                for source in root.glob(pattern):
                    self.assertNotIn(needle, source.read_text(encoding='utf-8'), f'{source} names excluded {path}')

    def test_extension_changelogs_stay_in_the_repository_and_readme_links_point_at_github(self):
        for extension, names in self.names.items():
            self.assertTrue((package.ROOT / 'extensions' / extension / 'CHANGELOG.md').is_file(), extension)
            self.assertNotIn(f'{extension}/CHANGELOG.md', names)
        self.assertIn('](' + package.BLOB + 'workflow/CHANGELOG.md)', self.readmes['workflow'])
        self.assertIn('](' + package.BLOB + 'progress/CHANGELOG.md)', self.readmes['progress'])
        self.assertFalse(package.excluded('pr/templates/CHANGELOG.md'))  # only the top-level release history

    def test_license_and_text_files_are_lf_in_every_checkout(self):
        for path in ('LICENSE', 'extensions/workflow/LICENSE', 'extensions/scope/requirements.txt'):
            result = subprocess.run(['git', 'check-attr', 'text', 'eol', '--', path], cwd=package.ROOT,
                                    capture_output=True, text=True, check=True)
            self.assertIn(path + ': text: set', result.stdout)
            self.assertIn(path + ': eol: lf', result.stdout)

    def test_packaged_readme_links_resolve_inside_the_archive_or_point_at_github(self):
        for extension, text in self.readmes.items():
            for link in re.findall(r'\]\(([^)\s]+)\)', text):
                target = link.split('#')[0]
                if not target or re.match(r'[a-z]+:', target):
                    continue
                self.assertIn(f'{extension}/{target}', self.names[extension], f'{extension} README: {link}')


if __name__ == '__main__':
    unittest.main()
