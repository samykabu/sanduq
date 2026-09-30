"""B13: speckit-workflow-worker-brief reads the execution protocol's own reference files
live (T0 turn budget, T7 result template), never a hand-copied duplicate, and reuses
delegate_dispatch's own S6/QA_COLLECT_ADDENDUM constants (review round 1, finding 10)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import delegate_dispatch as dd
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

    def test_forbidden_commands_text_reuses_delegate_dispatch_constant(self):
        # Finding 10: the exact NO_DISPATCHER_COMMANDS constant, not a
        # second, hand-scraped copy of a prose paragraph.
        self.assertIn(dd.NO_DISPATCHER_COMMANDS, wb.forbidden_commands_text('implementation'))

    def test_forbidden_commands_text_appends_qa_collect_addendum(self):
        text = wb.forbidden_commands_text('qa_collect')
        self.assertTrue(text.endswith(dd.NO_DISPATCHER_COMMANDS + dd.QA_COLLECT_ADDENDUM))

    def test_brief_forbids_git_stash_and_wildcard_add(self):
        # Round 2, finding 11: the B11 S6 git half must not be dropped.
        brief, _, _ = wb.build(self.root, self.feature, 'T001')
        self.assertIn('git stash', brief)
        self.assertIn('git add -A', brief)
        self.assertIn('git add .', brief)

    def test_spawn_and_wait_rules_are_f1_and_f2(self):
        f1, f2 = wb.spawn_and_wait_rules()
        self.assertIn('blocking rather than backgrounded', f1)
        self.assertIn('is never a valid final message from any agent in this protocol', f2)

    def test_report_on_state_change_rule_is_f3(self):
        rule = wb.report_on_state_change_rule()
        self.assertIn('A wake-up that carries no new information', rule)

    def test_read_summary_first_rule_is_t8(self):
        rule = wb.read_summary_first_rule()
        self.assertIn('read its summary first', rule)
        self.assertIn('only for a lane that failed', rule)

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
        brief, context, oversized = wb.build(self.root, self.feature, 'T002')
        self.assertEqual(context['work_type'], 'qa_author')
        self.assertIn('qa_author', brief)
        self.assertFalse(oversized)

    def test_build_respects_explicit_class_override(self):
        _, context, _ = wb.build(self.root, self.feature, 'T001', work_type='review')
        self.assertEqual(context['work_type'], 'review')

    def test_missing_task_raises_clear_error(self):
        with self.assertRaises(WorkflowError) as ctx:
            wb.build(self.root, self.feature, 'T999')
        self.assertIn('TASK_NOT_FOUND', str(ctx.exception))

    def test_brief_contains_task_line_owned_paths_requirement_and_new_sections(self):
        brief, _, _ = wb.build(self.root, self.feature, 'T001')
        self.assertIn('T001 Implement', brief)
        self.assertIn('`src/pool.py`', brief)
        self.assertIn('EXEC-06: The capacity warning must use the correct flag.', brief)
        self.assertIn('## Forbidden commands (S6)', brief)
        self.assertIn('## Result template (T7)', brief)
        self.assertIn('## Spawn and wait rules (F1, F2)', brief)
        self.assertIn('## Report only on state change (F3)', brief)
        self.assertIn('## Read summaries before raw output (T8)', brief)

    def test_qa_collect_is_not_a_cli_class_choice(self):
        # Finding 10: qa_collect is light-tier eligible only behind an
        # explicit [Collect] task marker, never an ad hoc CLI override.
        self.assertNotIn('qa_collect', wb.CLI_WORK_TYPES)
        import contextlib
        import io
        from unittest.mock import patch
        with patch.object(sys, 'argv', ['worker_brief.py', '--root', str(self.root), '--feature', self.feature,
                                        '--task', 'T001', '--class', 'qa_collect']), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                wb.main()
        self.assertEqual(ctx.exception.code, 2)

    def test_collect_marker_still_yields_qa_collect_automatically(self):
        (self.directory / 'tasks.md').write_text(
            '- [ ] T003 [Collect] Run the existing smoke suite and report its result\n', encoding='utf-8')
        _, context, _ = wb.build(self.root, self.feature, 'T003')
        self.assertEqual(context['work_type'], 'qa_collect')

    def test_oversized_contract_excerpt_is_dropped_to_stay_in_budget(self):
        (self.directory / 'contracts').mkdir()
        (self.directory / 'contracts/pool.md').write_text('pool contract\n' + ('x' * 10_000), encoding='utf-8')
        brief, _, oversized = wb.build(self.root, self.feature, 'T001')
        self.assertFalse(oversized)
        self.assertLessEqual(len(brief.encode('utf-8')), wb.MAX_BYTES)
        self.assertNotIn('## Contract excerpt', brief)

    def test_still_oversized_without_contract_is_reported_not_hidden(self):
        huge_id = ' '.join(f'EXEC-{i:02d}' for i in range(1, 60))
        (self.directory / 'tasks.md').write_text(f'- [ ] T004 Implement {huge_id}\n', encoding='utf-8')
        (self.directory / 'spec.md').write_text(
            '\n'.join(f'EXEC-{i:02d}: {"padding " * 40}requirement line.' for i in range(1, 60)),
            encoding='utf-8')
        brief, _, oversized = wb.build(self.root, self.feature, 'T004')
        self.assertTrue(oversized)
        self.assertGreater(len(brief.encode('utf-8')), wb.MAX_BYTES)

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
        self.assertGreater(size, wb.MIN_BYTES // 2)
        self.assertLessEqual(size, wb.MAX_BYTES)

    def test_cli_output_is_valid_json_even_with_backslashes_in_path(self):
        # Finding 10: json.dumps, not hand-built JSON, so a Windows path in
        # --output (backslashes) doesn't break parsing.
        import contextlib
        import io
        import json
        from unittest.mock import patch
        output_path = self.root / 'brief.md'
        with patch.object(sys, 'argv', ['worker_brief.py', '--root', str(self.root), '--feature', self.feature,
                                        '--task', 'T001', '--output', str(output_path)]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            wb.main()
        parsed = json.loads(out.getvalue())
        self.assertTrue(parsed['ok'])
        self.assertEqual(Path(parsed['path']), output_path)


if __name__ == '__main__':
    unittest.main()
