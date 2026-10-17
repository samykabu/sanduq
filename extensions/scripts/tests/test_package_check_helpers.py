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
