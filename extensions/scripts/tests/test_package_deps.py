"""Install/package test: the pr, assure, and user-manual archives must each carry
`scripts/deps.py` byte-identical to the canonical shared implementation (B9)."""
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
            import json
            inventory = json.loads(archive.read('assure/package-inventory.json'))
            self.assertIn('assure/scripts/deps.py', inventory)


if __name__ == '__main__':
    unittest.main()
