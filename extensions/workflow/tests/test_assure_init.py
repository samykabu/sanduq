import importlib.util
import unittest
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
