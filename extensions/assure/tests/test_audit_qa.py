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

    def test_redacted_placeholders_pass_like_the_user_manual_audit(self):
        # D2: the redaction rule's own placeholders are not secrets.
        for sample in ('password: &lt;redacted&gt;', 'password: <redacted-value>', 'api_key=${API_KEY_VALUE}',
                       'access_token: example-token-value', 'client_secret: placeholder-secret'):
            with self.subTest(sample):
                self.assertEqual(self.audit(CLEAN.replace('</pre>', '\n' + sample + '</pre>')), (0, 'ok files=1\n'))

    def test_encoded_and_root_relative_links_resolve(self):
        # D3: a percent-encoded file name and a site-root link into a public/ dir are real files.
        (self.manual.parents[2] / 'assets/reset/a b.png').write_bytes(b'png')
        self.assertEqual(self.audit(CLEAN.replace('form.png', 'a%20b.png')), (0, 'ok files=1\n'))
        root = self.manual.parents[3]
        page = root / 'web/public/qa/features/reset/index.html'
        (page.parents[2] / 'assets/reset').mkdir(parents=True)
        (page.parents[2] / 'assets/reset/form.png').write_bytes(b'png')
        for link, code in (('/qa/assets/reset/form.png', 0), ('/qa/missing.png', 1)):
            with self.subTest(link):
                page.parent.mkdir(parents=True, exist_ok=True)
                page.write_text(CLEAN.replace('../index.html', link), encoding='utf-8')
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(audit_qa.main([str(page), '--repo-root', str(root)]), code, out.getvalue())
                self.assertEqual('unresolved link ' + link in out.getvalue(), bool(code))


if __name__ == '__main__':
    unittest.main()
