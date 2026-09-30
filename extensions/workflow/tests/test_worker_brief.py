"""B13: speckit-workflow-worker-brief reads the execution protocol's own reference files
live (T0 turn budget, S6 forbidden commands, T7 result template), never a hand-copied duplicate."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import worker_brief as wb
from workflow import WorkflowError


class WorkerBriefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.feature = 'specs/001-example'
        self.directory = self.root / self.feature
        self.directory.mkdir(parents=True)
        (self.directory / 'tasks.md').write_text(
            '- [ ] T001 Implement the `src/pool.py` capacity check for EXEC-06\n'
            '- [ ] T002 Write API sample tests for T001\n', encoding='utf-8')
        (self.directory / 'spec.md').write_text(
            '# Spec\n\nEXEC-06: The capacity warning must use the correct flag.\n', encoding='utf-8')

    def test_turn_budget_row_matches_execution_assign_table(self):
        row = wb.turn_budget_row('qa_author')
        self.assertIsNotNone(row)
        self.assertTrue(row.startswith('| qa_author | ~300K'))

    def test_unknown_work_type_has_no_row(self):
        self.assertIsNone(wb.turn_budget_row('not-a-real-class'))

    def test_forbidden_commands_paragraph_contains_git_stash_rule(self):
        paragraph = wb.forbidden_commands_paragraph()
        self.assertIn('`git stash`', paragraph)
        self.assertIn('delegate_dispatch.py trust-reset', paragraph)

    def test_t7_template_has_all_ten_fields(self):
        template = wb.t7_template()
        for field in ('Task:', 'Status:', 'Files touched:', 'Tests:', 'Evidence:', 'Diff:',
                     'Consumers checked:', 'Tokens:', 'Blockers:', 'Next:'):
            self.assertIn(field, template)

    def test_requirement_id_extraction_from_description(self):
        self.assertEqual(wb.REQUIREMENT_ID.findall('Implement EXEC-06 and SC-004'), ['EXEC-06', 'SC-004'])

    def test_requirement_lines_pulls_verbatim_spec_line(self):
        lines = wb.requirement_lines(self.root, self.feature, 'Implement the capacity check for EXEC-06')
        self.assertEqual(lines, [('spec.md', 'EXEC-06: The capacity warning must use the correct flag.')])

    def test_owned_paths_extracts_backticked_file(self):
        self.assertEqual(wb.owned_paths('Implement the `src/pool.py` capacity check'), ['src/pool.py'])

    def test_build_classifies_work_type_from_task_description(self):
        brief, context = wb.build(self.root, self.feature, 'T002')
        self.assertEqual(context['work_type'], 'qa_author')
        self.assertIn('qa_author', brief)

    def test_build_respects_explicit_class_override(self):
        _, context = wb.build(self.root, self.feature, 'T001', work_type='review')
        self.assertEqual(context['work_type'], 'review')

    def test_missing_task_raises_clear_error(self):
        with self.assertRaises(WorkflowError) as ctx:
            wb.build(self.root, self.feature, 'T999')
        self.assertIn('TASK_NOT_FOUND', str(ctx.exception))

    def test_brief_contains_task_line_owned_paths_and_requirement(self):
        brief, _ = wb.build(self.root, self.feature, 'T001')
        self.assertIn('T001 Implement', brief)
        self.assertIn('`src/pool.py`', brief)
        self.assertIn('EXEC-06: The capacity warning must use the correct flag.', brief)
        self.assertIn('## Forbidden commands (S6)', brief)
        self.assertIn('## Result template (T7)', brief)

    def test_cli_writes_output_file_of_a_few_kb(self):
        import io, contextlib
        from unittest.mock import patch
        output_path = self.root / 'brief.md'
        with patch.object(sys, 'argv', ['worker_brief.py', '--root', str(self.root), '--feature', self.feature,
                                        '--task', 'T001', '--output', str(output_path)]), \
             contextlib.redirect_stdout(io.StringIO()):
            code = wb.main()
        self.assertEqual(code, 0)
        self.assertTrue(output_path.is_file())
        size = len(output_path.read_bytes())
        self.assertGreater(size, 500)
        self.assertLess(size, 6000)


if __name__ == '__main__':
    unittest.main()
