"""Portable init_manual: theme defaults, theme stylesheets and tool copies, no Spec Kit layout."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

INIT = Path(__file__).resolve().parents[1] / 'scripts/init_manual.py'


class InitManualTests(unittest.TestCase):
    def test_scaffold_records_the_theme_and_ships_every_stylesheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            modules = root / 'modules.json'
            modules.write_text(json.dumps([{'id': 'refunds', 'name': 'Refunds', 'description': 'Refund requests',
                                            'evidence': ['src/refunds']}]), encoding='utf-8')
            result = subprocess.run([sys.executable, str(INIT), '--repo-root', str(root), '--modules-file', str(modules)],
                                    capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(0, result.returncode, result.stderr)
            manual = root / 'User-Manual'
            self.assertIn('  theme: material\n', (manual / 'manual.yml').read_text(encoding='utf-8'))
            for name in ('extra.css', 'rtl.css', 'print.css', 'rtl-generic.css', 'rtl-readthedocs.css',
                         'theme-readthedocs.css'):
                self.assertTrue((manual / 'theme' / name).is_file(), name)
            for name in ('audit_manual.py', 'build_manual.py', 'manual_state.py'):
                self.assertTrue((manual / 'tools' / name).is_file(), name)
            self.assertTrue((root / '.github/workflows/user-manual-preview.yml').is_file())
            self.assertFalse((root / '.specify').exists())


if __name__ == '__main__':
    unittest.main()
