"""audit_qa.py: a clean manual passes; missing alt, caption, asset, index link, marker and a secret each fail."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_qa  # noqa: E402

CLEAN = """<html><body><h1>Password reset</h1><p>Development-only draft</p>
<a href="../index.html">Index</a> <a href="#steps">Steps</a> <a href="https://example.com">Ext</a>
<figure><img src="../../assets/reset/form.png" alt="Reset form"><figcaption>Form opens</figcaption></figure>
<pre>Authorization: Bearer [REDACTED]</pre></body></html>
"""


class AuditQaTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'qa/assets/reset').mkdir(parents=True)
        (root / 'qa/assets/reset/form.png').write_bytes(b'png')
        (root / 'qa/features/reset').mkdir(parents=True)
        (root / 'qa/features/index.html').write_text('<p>Development-only draft</p>', encoding='utf-8')
        self.manual = root / 'qa/features/reset/index.html'

    def audit(self, html):
        self.manual.write_text(html, encoding='utf-8')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = audit_qa.main([str(self.manual)])
        return code, out.getvalue()

    def test_clean_manual_passes(self):
        self.assertEqual(self.audit(CLEAN), (0, 'ok files=1\n'))

    def test_each_defect_is_reported(self):
        cases = {
            'without alt text': CLEAN.replace(' alt="Reset form"', ''),
            'without a <figure> and <figcaption>': CLEAN.replace('<figcaption>Form opens</figcaption>', ''),
            'unresolved link ../../assets/reset/missing.png': CLEAN.replace('form.png', 'missing.png'),
            'unresolved link ../nowhere.html': CLEAN.replace('../index.html', '../nowhere.html'),
            'missing "Development-only draft" marker': CLEAN.replace('Development-only draft', 'Draft'),
            'secret-like value for password': CLEAN.replace('</pre>', '\npassword: hunter2hunter2</pre>'),
        }
        for expected, html in cases.items():
            with self.subTest(expected):
                code, out = self.audit(html)
                self.assertEqual(code, 1)
                self.assertIn(expected, out)


if __name__ == '__main__':
    unittest.main()
