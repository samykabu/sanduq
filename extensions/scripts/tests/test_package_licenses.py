"""SEC-13: every package ships its MIT licence, and every vendoring package the upstream notices for what it vendors."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import package  # noqa: E402

UPSTREAM = {'illustrate': ('Cathryn Lavery', 'Tabler Icons', 'Simple Icons', 'log-z/logos', 'Devicon', 'sanduq-skills'),
            'progress': ('progress-report', 'sanduq-skills'),
            'workflow': ('delegate-task', 'sanduq-skills'),
            'user-manual': ('user-manual', 'dev-tools', 'sanduq-skills'),
            'memory': ('GitHub Spec Kit',)}


class PackageLicenseTests(unittest.TestCase):
    def test_every_package_ships_mit_license_and_its_notices(self):
        extensions = sorted(path.parent.name for path in (package.ROOT / 'extensions').glob('*/extension.yml'))
        self.assertTrue(set(UPSTREAM) <= set(extensions))
        for extension in extensions:
            with self.subTest(extension=extension):
                files = package.package_files(extension)
                self.assertTrue(files[extension + '/LICENSE'].startswith(b'MIT License'))
                notices = files.get(extension + '/THIRD_PARTY_NOTICES.md', b'').decode('utf-8')
                for name in UPSTREAM.get(extension, ()):
                    self.assertIn(name, notices)
                if extension in package.NOTICES:
                    self.assertNotIn('](vendor.lock.json)', notices)  # relative links would break outside the repo

    def test_vendoring_packages_ship_notices_and_injected_helpers_carry_spdx(self):
        # PH-02-T13: a helper injected from outside the extension's own folder starts with its SPDX line.
        for extension in sorted(path.parent.name for path in (package.ROOT / 'extensions').glob('*/extension.yml')):
            with self.subTest(extension=extension):
                files = package.package_files(extension)
                self.assertIn(extension + '/LICENSE', files)
                if extension in package.NOTICES:
                    self.assertIn(extension + '/THIRD_PARTY_NOTICES.md', files)
                injected = [name for name in files if name.startswith(extension + '/scripts/') and name.endswith('.py')
                            and not (package.ROOT / 'extensions' / name).is_file()]
                for name in injected:
                    lines = files[name].decode('utf-8').splitlines()
                    self.assertEqual(lines[1 if lines[0].startswith('#!') else 0], '# SPDX-License-Identifier: MIT', name)
        self.assertGreaterEqual(len(list((package.ROOT / 'extensions/scripts/shared').glob('*.py'))), 9)

    def test_extension_without_license_falls_back_to_root_license(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'extensions/demo').mkdir(parents=True)
            (root / 'extensions/demo/extension.yml').write_text('id: demo\n')
            (root / 'LICENSE').write_bytes(b'MIT License\nroot\n')
            self.assertEqual(package.package_files('demo', root)['demo/LICENSE'], b'MIT License\nroot\n')


if __name__ == '__main__':
    unittest.main()
