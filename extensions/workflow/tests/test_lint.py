"""workflow:lint (C2, C3): deterministic Analyze checks, budgets and the --record receipt."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lint  # noqa: E402
import test_workflow as fixture  # noqa: E402

SPEC = '# Spec\n\n- **FR-001**: Create things\n- **FR-002a**: Edit things\n- **SC-001**: Fast\n'
PLAN = '# Plan\n\nThe API is described in contracts/api.yaml.\n'
TASKS = ('# Tasks\n\n## Phase 1: Setup\n\n- [ ] T001 Create things (FR-001)\n'
         '- [ ] T002 Edit things for FR-002a and SC-001\n  - Dependencies: T001\n')


def write_feature(directory, spec=SPEC, plan=PLAN, tasks=TASKS, contracts=('api.yaml',)):
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in (('spec.md', spec), ('plan.md', plan), ('tasks.md', tasks)):
        if text is not None:
            (directory / name).write_text(text, encoding='utf-8', newline='\n')
    for name in contracts:
        (directory / 'contracts').mkdir(exist_ok=True)
        (directory / 'contracts' / name).write_text('openapi: 3.1.0\n', encoding='utf-8')


class LintChecks(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.feature = 'specs/001-a'
        self.directory = self.root / self.feature

    def lint(self, policy=None, tier='full', **files):
        write_feature(self.directory, **files)
        return lint.run(self.root, self.feature, policy or {}, tier)

    def codes(self, result):
        return {(f['code'], f['severity']) for f in result['findings']}

    def test_clean_feature_passes_without_findings(self):
        result = self.lint()
        self.assertEqual(result, {'ok': True, 'findings': [], 'needs_model_analyze': False, 'budgets': {}})

    def test_uncovered_requirement_needs_model_analyze(self):
        result = self.lint(spec=SPEC + '- **FR-003**: Delete things\n- **FR-001a**: Variant\n')
        self.assertEqual(self.codes(result), {('REQUIREMENT_UNCOVERED', 'warning')})
        self.assertEqual(len(result['findings']), 2)  # FR-001 in tasks does not cover FR-001a
        self.assertTrue(result['ok'])
        self.assertTrue(result['needs_model_analyze'])

    def test_uncovered_success_criterion_is_a_plain_warning(self):
        result = self.lint(spec=SPEC + '- **SC-002**: Cheap\n')
        self.assertEqual(self.codes(result), {('REQUIREMENT_UNCOVERED', 'warning')})
        self.assertIn('SC-002', result['findings'][0]['message'])
        self.assertTrue(result['ok'])
        self.assertFalse(result['needs_model_analyze'])

    def test_task_without_requirement_warns_outside_setup_and_polish_phases(self):
        tasks = (TASKS + '- [ ] T003 Install tooling\n\n## Phase 2: User Story 1\n\n- [ ] T004 Tidy up\n'
                 '- [ ] T005 [US1] Story work\n\n## Phase 3: Foundational\n\n- [ ] T006 Base schema\n\n'
                 '## Phase 4: Polish & Cross-Cutting Concerns\n\n- [ ] T007 Docs\n\n## Notes about polish\n\n'
                 '- [ ] T008 Not a phase heading\n')
        result = self.lint(tasks=tasks)
        self.assertEqual(self.codes(result), {('TASK_WITHOUT_REQUIREMENT', 'warning')})
        self.assertEqual([f['message'][:4] for f in result['findings']], ['T004', 'T008'])
        self.assertTrue(result['ok'])
        self.assertFalse(result['needs_model_analyze'])

    def test_duplicate_and_contradictory_task_ids(self):
        result = self.lint(tasks=TASKS + '- [x] T001 Create things (FR-001)\n')
        self.assertEqual(self.codes(result), {('TASK_ID_DUPLICATE', 'error'), ('TASK_STATUS_CONTRADICTORY', 'warning')})
        self.assertFalse(result['ok'])
        self.assertTrue(result['needs_model_analyze'])
        same = self.lint(tasks=TASKS + '- [ ] T002 Again FR-001\n')
        self.assertEqual(self.codes(same), {('TASK_ID_DUPLICATE', 'error')})
        self.assertFalse(same['needs_model_analyze'])

    def test_gaps_and_order_are_warnings(self):
        result = self.lint(tasks='- [ ] T004 FR-001 FR-002a SC-001\n- [ ] T001 FR-001\n')
        self.assertTrue(result['ok'])
        self.assertEqual(self.codes(result), {('TASK_ID_GAP', 'warning'), ('TASK_ID_ORDER', 'warning')})
        self.assertEqual([f['message'][:4] for f in result['findings'] if f['code'] == 'TASK_ID_GAP'], ['T002', 'T003'])

    def test_inline_dependency_cycle_and_unknown_prerequisite(self):
        cyclic = TASKS.replace('T001 Create things', 'T001 Create things after T002')
        result = self.lint(tasks=cyclic)
        self.assertEqual(self.codes(result), {('TASK_DEPENDENCY_CYCLE', 'error')})
        self.assertFalse(result['ok'])
        unknown = self.lint(tasks=TASKS + '- [ ] T003 FR-001 depends on T001 and T009\n')
        self.assertEqual(self.codes(unknown), {('TASK_DEPENDENCY_UNKNOWN', 'error')})
        self.assertIn('T009', unknown['findings'][0]['message'])

    def test_dependency_mapping_file_joins_the_graph(self):
        mapping = self.directory / 'workflow/task-dependencies.json'
        mapping.parent.mkdir(parents=True)
        mapping.write_text(json.dumps({'T001': ['T002']}))
        self.assertEqual(self.codes(self.lint()), {('TASK_DEPENDENCY_CYCLE', 'error')})
        mapping.write_text('["not", "a", "mapping"]')
        result = self.lint()
        self.assertEqual(self.codes(result), {('TASK_DEPENDENCIES_INVALID', 'error')})
        self.assertEqual(result['findings'][0]['path'], self.feature + '/workflow/task-dependencies.json')

    def test_headline_limit_is_two_hundred_characters(self):
        exact = 'T001 FR-001 ' + 'x' * (200 - len('T001 FR-001 '))
        self.assertTrue(self.lint(tasks=TASKS.replace('T001 Create things (FR-001)', exact))['ok'])
        result = self.lint(tasks=TASKS.replace('T001 Create things (FR-001)', exact + 'y'))
        self.assertEqual(self.codes(result), {('TASK_HEADLINE_TOO_LONG', 'error')})
        self.assertIn('201 characters', result['findings'][0]['message'])

    def test_open_clarification_marker_blocks(self):
        result = self.lint(spec=SPEC + '- [NEEDS CLARIFICATION: which store?]\n')
        self.assertEqual(self.codes(result), {('SPEC_NEEDS_CLARIFICATION', 'error')})
        self.assertEqual(result['findings'][0]['path'], self.feature + '/spec.md')

    def test_unreferenced_contract_warns(self):
        result = self.lint(contracts=('api.yaml', 'events.json'))
        self.assertEqual(self.codes(result), {('CONTRACT_UNREFERENCED', 'warning')})
        self.assertEqual(result['findings'][0]['path'], self.feature + '/contracts/events.json')

    def test_missing_artifacts_and_empty_tasks(self):
        result = self.lint(plan=None, contracts=())
        self.assertEqual(self.codes(result), {('ARTIFACT_MISSING', 'error')})
        result = self.lint(tasks='# Tasks\n')
        self.assertIn(('NO_TASKS', 'error'), self.codes(result))

    def test_budgets_block_on_lite_and_standard_and_warn_on_full(self):
        policy = {'artifacts': {'budgets': {'spec_kb': 0.05, 'plan_kb': 20, 'tasks_detail_lines': 0},
                                'enforce': 'lite-standard'}}
        for tier, severity in (('lite', 'error'), ('standard', 'error'), ('full', 'warning')):
            with self.subTest(tier=tier):
                result = self.lint(policy, tier)
                self.assertEqual(self.codes(result), {('BUDGET_EXCEEDED', severity), ('BUDGET_TASK_DETAIL', severity)})
                self.assertEqual(result['ok'], severity == 'warning')
                self.assertEqual(result['budgets']['spec.md'], {'bytes': len(SPEC.encode()), 'limit_bytes': 51, 'over': True})
                self.assertEqual(result['budgets']['plan.md']['over'], False)
                self.assertNotIn('research.md', result['budgets'])  # absent artifacts are not measured

    def test_enforce_all_and_warn(self):
        budgets = {'spec_kb': 0.05}
        self.assertEqual(self.codes(self.lint({'artifacts': {'budgets': budgets, 'enforce': 'all'}}, 'full')),
                         {('BUDGET_EXCEEDED', 'error')})
        self.assertEqual(self.codes(self.lint({'artifacts': {'budgets': budgets, 'enforce': 'warn'}}, 'lite')),
                         {('BUDGET_EXCEEDED', 'warning')})
        with self.assertRaisesRegex(lint.workflow.WorkflowError, 'LINT_ENFORCE_INVALID'):
            self.lint({'artifacts': {'budgets': budgets, 'enforce': 'sometimes'}})
        with self.assertRaisesRegex(lint.workflow.WorkflowError, 'LINT_TIER_INVALID'):
            self.lint(tier='huge')


class LintRuntime(unittest.TestCase):
    setUp = fixture.WorkflowTests.setUp
    configure = fixture.WorkflowTests.configure
    usage = fixture.WorkflowTests.usage
    receipt = fixture.WorkflowTests.receipt

    def main(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lint.main(['--root', str(self.root), '--feature', self.feature, *args])
        return code, buf.getvalue()

    def claim_analyze(self, spec=SPEC):
        self.policy = fixture.w.default_policy(False, False)
        self.configure()
        write_feature(self.root / self.feature, spec=spec)
        run = fixture.w.Run(self.root, self.feature)
        run.start('acme/app#10')
        for stage in ('scope', 'specify', 'clarify', 'plan', 'tasks'):
            claim = run.claim(self.usage())
            run.complete(claim['token'], self.receipt(stage, [self.feature + '/spec.md']))
        claim = run.claim(self.usage())
        self.assertEqual(claim['stage'], 'analyze')
        return claim['token']

    def test_cli_json_and_summary(self):
        write_feature(self.root / self.feature, spec=SPEC + '- **FR-003**: Delete things\n')
        code, out = self.main('--json')
        result = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual([f['code'] for f in result['findings']], ['REQUIREMENT_UNCOVERED'])
        self.assertTrue(result['needs_model_analyze'])
        code, out = self.main()
        self.assertEqual(out.splitlines()[0], 'ok errors=0 warnings=1 needs_model_analyze=1')
        (self.root / self.feature / 'spec.md').write_text(SPEC + '[NEEDS CLARIFICATION: x]', encoding='utf-8')
        code, out = self.main('--tier', 'lite')
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith('error errors=1'))

    def test_record_completes_the_claimed_analyze_stage(self):
        token = self.claim_analyze()
        code, out = self.main('--record', '--token', token)
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)['stage'], 'taskstoissues')
        stored = fixture.w.Run(self.root, self.feature).load()['receipts']['analyze']
        self.assertEqual(stored['lint'], {'ok': True, 'findings': 0})
        self.assertEqual(stored['inputs'], [self.feature + '/' + n for n in ('spec.md', 'plan.md', 'tasks.md')])
        evidence = stored['evidence'][0]
        self.assertRegex(evidence, r'^specs/001-example/evidence/lint-\d{8}T\d{6}\d+Z\.json$')
        self.assertTrue(json.loads((self.root / evidence).read_text(encoding='utf-8'))['ok'])

    def test_record_refuses_when_model_analyze_is_needed(self):
        token = self.claim_analyze(SPEC + '- **FR-003**: Delete things\n')
        code, out = self.main('--record', '--token', token)
        self.assertEqual(code, 1)
        self.assertEqual((json.loads(out)['recorded'], json.loads(out)['reason']), (False, 'needs_model_analyze'))
        state = fixture.w.Run(self.root, self.feature).load()
        self.assertEqual(state['active']['stage'], 'analyze')
        self.assertFalse(list((self.root / self.feature / 'evidence').glob('lint-*.json')))

    def test_record_requires_a_token(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.main('--record')


if __name__ == '__main__':
    unittest.main()
