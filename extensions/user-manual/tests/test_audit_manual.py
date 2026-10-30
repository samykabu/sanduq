"""Portable audit_manual: GitHub-safe syntax warnings and every link form."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AUDIT = Path(__file__).resolve().parents[1] / 'scripts/audit_manual.py'
FRONT = ('---\ntitle: Home\nmodule: system\naudiences: [end-user]\nlanguage: en\ncontent_type: how-to\n'
         'source_evidence: [src]\nlast_verified: 2026-10-30\nstatus: draft\n---\n')


class AuditTests(unittest.TestCase):
    def audit(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'docs/en').mkdir(parents=True)
            (root / 'docs/en/shot one.png').write_bytes(b'x')
            (root / 'manual.yml').write_text('languages:\n  required: [en]\nmodules: []\n', encoding='utf-8')
            (root / 'docs/en/index.md').write_text(FRONT + body, encoding='utf-8')
            done = subprocess.run([sys.executable, str(AUDIT), '--root', str(root), '--json'],
                                  capture_output=True, text=True, encoding='utf-8')
            return done.returncode, json.loads(done.stdout)

    def test_mkdocs_only_syntax_is_flagged_with_its_github_form(self):
        code, result = self.audit('!!! note "Before"\n    Sign in.\n\n=== "Web"\n    Open it.\n')
        self.assertEqual(0, code)
        self.assertEqual(2, len(result['warnings']), result['warnings'])
        self.assertIn('> [!NOTE]', result['warnings'][0])
        self.assertIn('<details>', result['warnings'][1])

    def test_github_alerts_pass_quietly(self):
        code, result = self.audit('> [!NOTE]\n> Sign in.\n\n<details>\n<summary>Web</summary>\n\nOpen it.\n</details>\n')
        self.assertEqual((0, []), (code, result['warnings']))

    def test_titled_bracketed_and_reference_links_resolve(self):
        code, result = self.audit('![A](<shot one.png> "Shot")\n[x][s]\n\n[s]: <shot one.png>\n')
        self.assertEqual((0, []), (code, result['errors']))
        code, result = self.audit('A claim.[^1]\n\n[^1]: Explanation of the information.\n')
        self.assertEqual((0, []), (code, result['errors']), 'a footnote is not a link')
        code, result = self.audit('```js\nconst routes = {\n  [region]: endpoint,\n};\n```\n\n```markdown\n!!! note\n```\n')
        self.assertEqual((0, [], []), (code, result['errors'], result['warnings']), 'code examples are not checked')
        code, result = self.audit('```\ncode\n````\n\n[gone](after-the-fence.md)\n')
        self.assertEqual(1, code, 'prose after a longer closing fence is still checked')
        code, result = self.audit('- ```text\n  [x]: y\n  ```\n\n```example``` span.\n\n[gone](after-the-span.md)\n')
        self.assertEqual(1, code)
        self.assertEqual(['index.md'.join(('docs/en/', ': missing linked file after-the-span.md'))], result['errors'])
        code, result = self.audit('[gone](missing.md "Title")\n')
        self.assertEqual(1, code)
        self.assertIn('missing linked file missing.md', result['errors'][0])


if __name__ == '__main__':
    unittest.main()
