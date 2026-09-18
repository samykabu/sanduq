import importlib.util
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

spec = importlib.util.spec_from_file_location('assure_init', Path(__file__).resolve().parents[2] / 'assure/scripts/assure_init.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class AssureInitTests(unittest.TestCase):
    def test_both_yaml_indents_and_unrelated_hooks(self):
        doc = {'settings': {'auto_execute_hooks': True}, 'hooks': {'before_implement': [
            {'extension': 'assure', 'optional': True}, {'extension': 'project', 'optional': True}],
            'after_tasks': [{'extension': 'assure', 'optional': True}]}}
        for indentation in (2, 4):
            text = yaml.safe_dump(doc, indent=indentation)
            output, count = m.update_hooks(text, True)
            self.assertEqual(count, 1)
            result = yaml.safe_load(output)
            self.assertFalse(result['hooks']['before_implement'][0]['optional'])
            self.assertTrue(result['hooks']['before_implement'][1]['optional'])
            self.assertEqual(result['settings'], doc['settings'])
            self.assertEqual(m.update_hooks(output, True)[1], 0)
            self.assertEqual(m.update_hooks(output, False)[1], 1)

    def test_missing_gate_is_not_success(self):
        with self.assertRaises(SystemExit):
            m.update_hooks('hooks:\n  after_tasks:\n  - extension: assure\n', True)

    def test_managed_init_preserves_reconciled_hooks_and_does_not_create_legacy_ci(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / '.specify').mkdir()
            (root / '.specify/workflow.yml').write_text('schema_version: 1\nprocesses: {qa: true, user_manual: false}\n', encoding='utf-8')
            hooks = 'hooks:\n  before_implement:\n  - extension: assure\n    optional: true\n    enabled: false\n'
            (root / '.specify/extensions.yml').write_text(hooks, encoding='utf-8')
            result = subprocess.run([sys.executable, str(Path(m.__file__)), '--repo-root', str(root), '--mode', 'integrated'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / '.specify/extensions.yml').read_text(encoding='utf-8'), hooks)
            self.assertFalse((root / '.github/workflows/documentation-gates.yml').exists())
            self.assertTrue((root / '.specify/extensions/assure/assure-config.yml').exists())
