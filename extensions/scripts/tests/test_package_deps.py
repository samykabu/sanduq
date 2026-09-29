"""Install/package test: the pr, assure, and user-manual archives must each carry
`scripts/deps.py` byte-identical to the canonical shared implementation (B9)."""
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from package import package, ROOT  # noqa: E402

CONSUMERS = ('pr', 'assure', 'user-manual')


class PackagedDepsScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.canonical = (ROOT / 'extensions/scripts/shared/deps.py').read_bytes()

    def test_each_consumer_package_ships_deps_py(self):
        for extension in CONSUMERS:
            with self.subTest(extension=extension):
                output = Path(self.tmp.name) / (extension + '.zip')
                package(extension, output=output)
                with zipfile.ZipFile(output) as archive:
                    names = set(archive.namelist())
                    member = extension + '/scripts/deps.py'
                    self.assertIn(member, names)
                    self.assertEqual(archive.read(member), self.canonical)

    def test_package_inventory_hashes_the_shipped_script(self):
        output = Path(self.tmp.name) / 'assure.zip'
        package('assure', output=output)
        with zipfile.ZipFile(output) as archive:
            inventory = json.loads(archive.read('assure/package-inventory.json'))
            self.assertIn('assure/scripts/deps.py', inventory)

    def test_packaged_deps_script_runs_ensure_inside_an_installed_fixture(self):
        """Extend the install/package check with an actual run of the shipped script (not just a
        byte comparison): unzip each consumer package into a simulated installed project layout
        (<root>/.specify/extensions/<pkg>/scripts/deps.py, its dependencies.yml, and a compatible
        .registry) and invoke it exactly as the commands do, with --skip-catalog-check so it never
        touches the network or a real `specify` binary."""
        for extension in CONSUMERS:
            with self.subTest(extension=extension):
                project = Path(self.tmp.name) / (extension + '-fixture')
                ext_dir = project / '.specify/extensions' / extension
                (project / '.specify/extensions').mkdir(parents=True, exist_ok=True)
                archive_path = Path(self.tmp.name) / (extension + '-installed.zip')
                package(extension, output=archive_path)
                with zipfile.ZipFile(archive_path) as archive:
                    for member in archive.namelist():
                        if member.startswith(extension + '/scripts/') or member == extension + '/dependencies.yml':
                            target = project / '.specify/extensions' / member
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(archive.read(member))
                registry = project / '.specify/extensions/.registry'
                registry.write_text(json.dumps(
                    {'extensions': {'illustrate': {'version': '2.1.2', 'enabled': True}}}), encoding='utf-8')

                script = ext_dir / 'scripts/deps.py'
                self.assertTrue(script.is_file(), 'deps.py missing from the installed fixture')
                result = subprocess.run(
                    [sys.executable, str(script), 'ensure', 'illustrate', '--skip-catalog-check'],
                    cwd=project, capture_output=True, text=True, encoding='utf-8', timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(), 'illustrate: ok (installed 2.1.2, satisfies >=2.0.0,<3.0.0)')


if __name__ == '__main__':
    unittest.main()
