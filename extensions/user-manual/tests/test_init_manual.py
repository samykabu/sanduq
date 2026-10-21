"""init_manual.py writes the scaffold and never overwrites an authored page (AU10)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/init_manual.py'
MODULES = {'modules': [{'id': 'billing', 'name': 'Billing', 'description': 'Invoices and payments.',
                        'name_ar': 'الفوترة', 'description_ar': 'الفواتير والمدفوعات.', 'evidence': ['src/billing/']}]}


class InitManualTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.modules = self.root / 'modules.json'
        self.modules.write_text(json.dumps(MODULES), encoding='utf-8')
        self.manual = self.root / 'User-Manual'

    def init(self, *extra):
        result = subprocess.run([sys.executable, str(SCRIPT), '--repo-root', str(self.root), '--modules-file',
                                 str(self.modules), '--product-name', 'Shop', *extra], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_home_page_survives(self):
        home = self.manual / 'docs/en/index.md'
        home.parent.mkdir(parents=True)
        home.write_text('# My authored home page\n', encoding='utf-8')
        self.init()
        self.assertEqual(home.read_text(encoding='utf-8'), '# My authored home page\n')

    def test_fresh_run_writes_the_stub_modules_and_css(self):
        self.init('--enable-arabic')
        for language in ('en', 'ar'):
            with self.subTest(language=language):
                home = (self.manual / f'docs/{language}/index.md').read_text(encoding='utf-8')
                self.assertIn('title: "Shop"', home)
                self.assertIn(f'language: {language}', home)
                self.assertTrue((self.manual / f'docs/{language}/modules/billing/index.md').is_file())
                self.assertTrue((self.manual / f'docs/{language}/assets/stylesheets/extra.css').is_file())
        self.assertIn('id: "billing"', (self.manual / 'manual.yml').read_text(encoding='utf-8'))
        self.assertTrue((self.manual / 'theme/rtl.css').is_file())
        self.assertTrue((self.root / '.github/workflows/user-manual-preview.yml').is_file())


if __name__ == '__main__':
    unittest.main()
