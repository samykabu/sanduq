"""PR2: pr_changelog.py seeds docs/<slug>/CHANGELOG.md from tasks, log, progress and receipts inside
a marked block; a rerun regenerates the block and keeps edits outside it; missing inputs still give
a valid skeleton. git and gh are replaced by a fake runner."""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pr_changelog  # noqa: E402

TASKS = ('# Tasks\n\n## Phase 1: Setup\n\n- [x] T001 Create parser (FR-001)\n- [ ] T002 Wire CLI\n\n'
         '## Phase 2: Polish\n\n- [X] T003 Add docs\n')


def fake_run(args, cwd):
    key = ' '.join(args[:3])
    out = {'gh pr view': 'https://github.com/acme/app/pull/12', 'git branch --show-current': 'feat/x',
           'git symbolic-ref --short': 'origin/main', 'git log --format=%s': 'feat: parser\nfix: cli'}.get(key)
    return subprocess.CompletedProcess(args, 0 if out is not None else 1, out or '', '')


class ChangelogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.feature = self.root / 'specs/001-x'
        (self.feature / 'evidence').mkdir(parents=True)
        (self.feature / 'workflow').mkdir()
        (self.feature / 'tasks.md').write_text(TASKS, encoding='utf-8')
        (self.feature / 'scope-source.json').write_text(json.dumps({'repo': 'acme/app', 'issue': 10}), encoding='utf-8')
        (self.feature / 'progress.yml').write_text('tests: 12 passed\ncoverage: 91%\n  nested: skip\n', encoding='utf-8')
        (self.feature / 'workflow/checkpoint.json').write_text(
            json.dumps({'receipts': {'verify': {'summary': 'All 12 tests pass'}}}), encoding='utf-8')
        (self.feature / 'evidence/unit.json').write_text('{}', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *extra):
        out = io.StringIO()
        with patch.object(pr_changelog, 'run', fake_run), redirect_stdout(out):
            code = pr_changelog.main(['--root', str(self.root), '--feature', 'specs/001-x', *extra])
        return code, out.getvalue().strip()

    def test_skeleton_holds_every_fact_inside_the_block(self):
        code, printed = self.run_script()
        self.assertEqual((code, printed), (0, 'docs/001-x/CHANGELOG.md'))
        text = (self.root / printed).read_text(encoding='utf-8')
        block = text[text.index(pr_changelog.START):text.index(pr_changelog.END)]
        for fact in ('- Spec: `specs/001-x/spec.md`', '- Branch: `feat/x`', '- Issue: acme/app#10',
                     '- PR: https://github.com/acme/app/pull/12', '- feat: parser', '- fix: cli',
                     '- Phase 1: Setup: T001 Create parser (FR-001)', '- Phase 2: Polish: T003 Add docs',
                     '- progress.yml: tests: 12 passed', '- progress.yml: coverage: 91%',
                     '- Stage verify: All 12 tests pass', '- Evidence: `specs/001-x/evidence/unit.json`',
                     '### Open items\n\n- T002 Wire CLI'):
            self.assertIn(fact, block, fact)
        self.assertNotIn('nested: skip', block)
        self.assertIn('### Scope (not in this phase)', text[text.index(pr_changelog.END):])

    def test_rerun_regenerates_the_block_and_keeps_edits_outside_it(self):
        path = self.root / self.run_script()[1]
        edited = path.read_text(encoding='utf-8').replace('### Migration\n', '### Migration\n\nRun the backfill once.\n')
        edited = 'Preface kept.\n\n' + edited
        path.write_text(edited, encoding='utf-8')
        (self.feature / 'tasks.md').write_text(TASKS.replace('- [ ] T002', '- [x] T002'), encoding='utf-8')
        self.run_script()
        text = path.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('Preface kept.\n\n'))
        self.assertIn('Run the backfill once.', text)
        self.assertIn('- Phase 1: Setup: T001 Create parser (FR-001); T002 Wire CLI', text)
        self.assertIn('### Open items\n\n- none', text)
        self.assertEqual(text.count(pr_changelog.START), 1)

    def test_missing_inputs_still_write_a_valid_skeleton(self):
        for name in ('tasks.md', 'scope-source.json', 'progress.yml', 'workflow/checkpoint.json', 'evidence/unit.json'):
            (self.feature / name).unlink()
        code, printed = self.run_script('--base', 'develop', '--output', 'docs/other/CHANGELOG.md')
        self.assertEqual((code, printed), (0, 'docs/other/CHANGELOG.md'))
        text = (self.root / printed).read_text(encoding='utf-8')
        self.assertIn('### Open items\n\n- none', text)
        self.assertNotIn('Issue:', text)
        self.assertIn(pr_changelog.END, text)

    def test_missing_feature_exits_2(self):
        self.assertEqual(self.run_script('--feature', 'specs/none')[0], 2)


if __name__ == '__main__':
    unittest.main()
