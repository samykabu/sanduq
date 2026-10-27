"""assure_init.py keeps consumer files (AU9) and moves an unedited earlier CI gate to the PR head (AU8)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import assure_init  # noqa: E402

HOOKS = ('# hooks registered by Spec Kit\nhooks:\n  before_implement:\n  - extension: assure\n    optional: {gate}\n'
         '  after_tasks:\n  - extension: assure\n    optional: true\n')
GATE = '.github/workflows/documentation-gates.yml'


class AssureInitTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / '.specify').mkdir()
        self.hooks = self.root / '.specify/extensions.yml'
        self.config = self.root / '.specify/extensions/assure/assure-config.yml'

    def init(self, mode):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'assure_init.py'), '--repo-root', str(self.root),
                                 '--mode', mode], capture_output=True, text=True)
        return result

    def test_rerun_keeps_consumer_config(self):
        self.hooks.write_text(HOOKS.format(gate='true'), encoding='utf-8')
        self.assertEqual(self.init('manual').returncode, 0)
        custom = self.config.read_text(encoding='utf-8').replace('    - .cache\n', '    - .cache\n    - generated\n')
        custom = '# our QA settings\n' + custom
        self.config.write_text(custom, encoding='utf-8')
        for mode, value in (('integrated', 'true'), ('integrated', 'true'), ('manual', 'false')):
            with self.subTest(mode=mode):
                result = self.init(mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                text = self.config.read_text(encoding='utf-8')
                self.assertTrue(text.startswith('# our QA settings\n'))
                self.assertIn('    - generated\n', text)
                self.assertIn(f'  mode: {mode}\n', text)
                self.assertIn(f'  require_document_before_pr: {value}\n', text)
        self.assertEqual(self.config.read_text(encoding='utf-8'), custom)

    def test_same_mode_rerun_leaves_extensions_yml_bytes(self):
        text = HOOKS.format(gate='false')
        self.hooks.write_text(text, encoding='utf-8')
        result = self.init('integrated')
        self.assertIn('hooks_changed=0', result.stdout)
        self.assertEqual(self.hooks.read_text(encoding='utf-8'), text)
        self.assertIn('hooks_changed=1', self.init('manual').stdout)

    def test_config_without_the_lifecycle_keys_is_refused_not_replaced(self):
        self.hooks.write_text(HOOKS.format(gate='true'), encoding='utf-8')
        self.config.parent.mkdir(parents=True)
        self.config.write_text('scan:\n  exclude:\n    - generated\n', encoding='utf-8')
        result = self.init('integrated')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('lifecycle', result.stderr)
        self.assertEqual(self.config.read_text(encoding='utf-8'), 'scan:\n  exclude:\n    - generated\n')

    def test_gate_checks_out_the_pr_head(self):
        rendered = assure_init.sanduq_ci.render(assure_init.GATE.read_bytes(), assure_init.sanduq_ci.default_ci())
        checkout = rendered.decode().split('uses: actions/checkout@', 1)[1].split('- name:', 1)[0]
        self.assertIn('ref: ${{ github.event.pull_request.head.sha }}', checkout)
        self.assertIn(assure_init.HEAD_CHECKOUT, assure_init.GATE.read_bytes().replace(b'\r\n', b'\n'))

    def test_init_replaces_an_unedited_earlier_gate_and_keeps_an_edited_one(self):
        self.hooks.write_text(HOOKS.format(gate='true'), encoding='utf-8')
        ci = assure_init.sanduq_ci.default_ci()
        template = assure_init.GATE.read_bytes().replace(b'\r\n', b'\n')
        # The gate before AU8, and the head-run gate before SEC-03.
        previous = assure_init.PREVIOUS_GATE.read_bytes().replace(b'\r\n', b'\n')
        earlier = assure_init.sanduq_ci.render(previous.replace(assure_init.HEAD_CHECKOUT, b''), ci)
        target = self.root / GATE
        target.parent.mkdir(parents=True)
        for old in (earlier, assure_init.sanduq_ci.render(previous, ci)):
            target.write_bytes(old.replace(b'\n', b'\r\n'))
            result = self.init('manual')
            self.assertIn('ci_gate=updated', result.stdout)
            self.assertEqual(target.read_bytes(), assure_init.sanduq_ci.render(template, ci))
        self.assertIn('ci_gate=current', self.init('manual').stdout)
        edited = earlier.replace(b'fetch-depth: 0', b'fetch-depth: 0\n          lfs: true')
        target.write_bytes(edited)
        result = self.init('manual')
        self.assertIn('ci_gate=kept', result.stdout)
        self.assertIn('github.event.pull_request.head.sha', result.stdout)
        self.assertEqual(target.read_bytes(), edited)


if __name__ == '__main__':
    unittest.main()
