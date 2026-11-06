"""Packages ship executable, byte-identical canonical helpers and inventory bindings."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from package import package, ROOT


class CheckHelperPackageTests(unittest.TestCase):
    def test_memory_and_workflow_helpers_execute_from_extracted_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for extension, cli in (('memory', 'archive.py'), ('workflow', 'execution_tools.py')):
                output = root / (extension + '.zip')
                package(extension, output=output)
                with zipfile.ZipFile(output) as archive:
                    helpers = ['check_inputs.py', 'bounded_json.py']
                    if extension == 'workflow':
                        helpers.append('evidence_snapshot.py')
                    inventory = json.loads(archive.read(extension + '/package-inventory.json'))
                    for helper in helpers:
                        member = extension + '/scripts/' + helper
                        expected = (ROOT / 'extensions/scripts/shared' / helper).read_bytes()
                        self.assertEqual(archive.read(member), expected)
                        self.assertEqual(inventory[member], hashlib.sha256(expected).hexdigest())
                    archive.extractall(root / 'packages')
                result = subprocess.run([sys.executable, str(root / 'packages' / extension / 'scripts' / cli), '--help'],
                                        cwd=root, capture_output=True, encoding='utf-8', timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)


class PackagedHashTests(unittest.TestCase):
    def test_documentation_packages_ship_the_canonical_hash_helper(self):
        canonical = (ROOT / 'extensions/workflow/scripts/sanduq_hash.py').read_bytes()
        freshness = (ROOT / 'extensions/scripts/shared/sanduq_freshness.py').read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            for extension in ('assure', 'user-manual'):
                with self.subTest(extension):
                    archive = package(extension, output=Path(folder) / (extension + '.zip'))['archive']
                    with zipfile.ZipFile(archive) as bundle:
                        self.assertEqual(bundle.read(extension + '/scripts/sanduq_hash.py'), canonical)
                        self.assertEqual(bundle.read(extension + '/scripts/sanduq_freshness.py'), freshness)
                        inventory = json.loads(bundle.read(extension + '/package-inventory.json'))
                        self.assertEqual(inventory[extension + '/scripts/sanduq_hash.py'], hashlib.sha256(canonical).hexdigest())
        # No extension carries its own hand-maintained copy that could drift.
        copies = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'extensions').rglob('sanduq_hash.py'))
        self.assertEqual(copies, ['extensions/workflow/scripts/sanduq_hash.py'])
