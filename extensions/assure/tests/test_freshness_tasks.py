"""The analyze state survives the User Manual task block in tasks.md, as input and output (AU16)."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/shared'))
import sanduq_freshness as f  # noqa: E402

TASKS = '# Tasks\n\n## Phase 1\n\n- [ ] T001 Build the form\n'
BLOCK = ('\n<!-- user-manual-tasks:start -->\n### User Manual tasks\n\n- [ ] T002 Document the form in '
         'User-Manual/docs/en/modules/billing/index.md\n<!-- user-manual-tasks:end -->\n')


class AnalyzeTasksFreshnessTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        for args in (('init', '-q'), ('config', 'user.name', 'Test'), ('config', 'user.email', 'test@example.invalid')):
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        self.feature = 'specs/001-example'
        (self.root / self.feature).mkdir(parents=True)
        (self.root / self.feature / 'spec.md').write_text('# Example', encoding='utf-8')
        self.tasks = self.root / self.feature / 'tasks.md'
        self.tasks.write_text(TASKS, encoding='utf-8')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'baseline'], cwd=self.root, check=True)
        self.base = f.git(self.root, 'rev-parse', 'HEAD').strip()
        self.output = 'docs/001-example/QA.md'
        (self.root / self.output).parent.mkdir(parents=True)
        (self.root / self.output).write_text('Evidence', encoding='utf-8')

    def call(self, kind, action='status'):
        outputs = [self.feature + '/tasks.md'] if kind == 'analyze' else [self.output]
        state = f'.specify/extensions/assure/state/001-example-{kind}.json'
        return f.record_or_status(self.root, self.feature, kind, state, action, outputs, self.base)

    def test_manual_block_keeps_analyze_current(self):
        self.call('analyze', 'record')
        self.tasks.write_text(TASKS + BLOCK, encoding='utf-8')
        self.assertTrue(self.call('analyze')['current'])
        # A rerun of the manual Analyze replaces its block: still current.
        self.tasks.write_text(TASKS + BLOCK.replace('T002 Document', 'T002 Describe'), encoding='utf-8')
        self.assertTrue(self.call('analyze')['current'])
        # Recorded over the block, removing it is also no QA change.
        self.call('analyze', 'record')
        self.tasks.write_text(TASKS, encoding='utf-8')
        self.assertTrue(self.call('analyze')['current'])

    def test_a_qa_task_edit_still_stales_analyze(self):
        self.call('analyze', 'record')
        self.tasks.write_text(TASKS + '- [ ] T003 Add Playwright E2E test\n' + BLOCK, encoding='utf-8')
        result = self.call('analyze')
        self.assertFalse(result['current'])
        self.assertEqual(result['changed_inputs'], [self.feature + '/tasks.md'])
        self.assertEqual(result['changed_outputs'], [self.feature + '/tasks.md'])

    def test_document_kind_still_sees_the_manual_block(self):
        self.call('document', 'record')
        self.tasks.write_text(TASKS + BLOCK, encoding='utf-8')
        self.assertFalse(self.call('document')['current'])

    def test_an_earlier_state_without_the_block_stays_current(self):
        # Old-state handling: hashes of a tasks.md without the block are unchanged by the new rule.
        self.call('analyze', 'record')
        state = self.root / '.specify/extensions/assure/state/001-example-analyze.json'
        saved = json.loads(state.read_text(encoding='utf-8'))
        expected = hashlib.sha256(TASKS.encode()).hexdigest()
        self.assertEqual(saved['outputs'][self.feature + '/tasks.md'], expected)
        self.assertEqual(saved['inputs']['files'][self.feature + '/tasks.md'], expected)


if __name__ == '__main__':
    unittest.main()
