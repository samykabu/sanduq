"""Front-half runtime: policy keys, tiers, claim output, side effects, doctor cache, source inventories,
the resume contract, revalidate-upstream, the bind-only Specify hook and phase-lazy task issues."""
import copy
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_gate as c  # noqa: E402
import lean_policy  # noqa: E402
import lifecycle  # noqa: E402
import workflow as w  # noqa: E402
from test_receipt_contract import Harness, checkpoint_validator  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/workflow.py'


def clean_env():
    """The process environment without any inherited Sanduq claim or delegation variables."""
    return {key: value for key, value in os.environ.items() if not key.startswith('SANDUQ_')}


class Base(Harness):
    def profiles(self, enabled=True):
        self.policy['profiles'] = {'enabled': enabled, 'lite': {'max_score': 3}, 'standard': {'max_score': 8}}
        self.configure()

    def scope_receipt(self, score):
        receipt = self.receipt('scope')
        receipt['effort_score'] = score
        return receipt

    def advance(self, run, last, receipts=None):
        """Claim and complete every stage up to and including `last`."""
        receipts = receipts or {}
        while True:
            claim = run.claim(self.usage(), finalize=True)
            stage = claim['stage']
            receipt = receipts.get(stage) or self.receipt(stage)
            run.complete(claim['token'], receipt)
            if stage == last:
                return

    def merged_plan_receipt(self):
        receipt = self.receipt('plan')
        tasks = self.root / self.feature / 'tasks.md'
        tasks.write_text('## Phase 1\n- [x] T001 Done behavior\n', encoding='utf-8')
        receipt['inputs'] = receipt['inputs'] + [self.feature + '/tasks.md']
        return receipt

    def lint_receipt(self):
        receipt = self.receipt('analyze')
        return {key: receipt[key] for key in ('stage', 'summary', 'outcome', 'inputs', 'evidence')} | {
            'lint': {'ok': True, 'findings': 0}}

    def events(self, run):
        return lifecycle.read_events(run.feature / 'workflow/lifecycle.jsonl')[0]

    def cli(self, *args):
        done = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), *args],
                              capture_output=True, text=True, encoding='utf-8')
        return done.returncode, json.loads(done.stdout)


class PolicyKeyTests(Base):
    def full_policy(self):
        policy = copy.deepcopy(self.policy)
        policy['profiles'] = {'enabled': True, 'lite': {'max_score': 3}, 'standard': {'max_score': 8}}
        policy['clarification'].update(max_questions_per_round=6, in_session_first_round=True)
        policy['artifacts'] = {'budgets': {'spec_kb': 25, 'plan_kb': 20, 'research_kb': 15, 'tasks_detail_lines': 2},
                               'enforce': 'lite-standard'}
        policy['issue_sync']['taskstoissues'] = 'phase-lazy'
        policy['project_sync'] = {'points': ['specify', 'execute', 'pr']}
        policy['scope'] = {'board_cache_seconds': 300}
        return policy

    def test_new_keys_validate_and_absent_keys_keep_defaults(self):
        policy = w.validate_policy(self.full_policy())
        self.assertEqual(policy['issue_sync']['taskstoissues'], 'phase-lazy')
        default = w.validate_policy(copy.deepcopy(self.policy))
        for key in ('profiles', 'artifacts', 'project_sync'):
            self.assertNotIn(key, default)
        self.assertEqual(w.stages(default), w.BASE_STAGES)
        self.assertTrue(all(w.project_sync(default, stage) for stage in w.PROJECT_SYNC_POINTS))
        self.assertFalse(w.project_sync(default, 'clarify'))

    def test_schema_accepts_the_new_keys(self):
        from jsonschema import Draft202012Validator
        schema = json.loads((SCRIPT.parents[1] / 'schemas/policy-v1.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(self.full_policy())
        bad = self.full_policy()
        bad['issue_sync']['taskstoissues'] = 'never'
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(bad)))

    def test_invalid_values_and_unknown_subkeys_are_refused(self):
        cases = [
            (lambda p: p.update(profiles={'enabled': 'yes'}), 'PROFILES_POLICY_INVALID'),
            (lambda p: p.update(profiles={'enabled': True, 'tiny': {}}), 'PROFILES_POLICY_INVALID'),
            (lambda p: p.update(profiles={'enabled': True, 'lite': {'max_score': 9}}), 'PROFILES_POLICY_INVALID'),
            (lambda p: p['clarification'].update(max_questions_per_round=0), 'CLARIFICATION_POLICY_INVALID'),
            (lambda p: p['clarification'].update(in_session_first_round='true'), 'CLARIFICATION_POLICY_INVALID'),
            (lambda p: p.update(artifacts={'budgets': {'spec_mb': 1}}), 'ARTIFACTS_POLICY_INVALID'),
            (lambda p: p.update(artifacts={'enforce': 'never'}), 'ARTIFACTS_POLICY_INVALID'),
            (lambda p: p.update(project_sync={'points': ['clarify']}), 'PROJECT_SYNC_POLICY_INVALID'),
            (lambda p: p.update(project_sync={'points': ['pr'], 'extra': 1}), 'PROJECT_SYNC_POLICY_INVALID'),
            (lambda p: p.update(scope={'board_cache_seconds': -1}), 'SCOPE_BOARD_CACHE_INVALID'),
            (lambda p: p['issue_sync'].update(taskstoissues='optional'), 'TASK_ISSUES_REQUIRED'),
        ]
        for mutate, code in cases:
            with self.subTest(code=code):
                policy = copy.deepcopy(self.policy)
                mutate(policy)
                with self.assertRaisesRegex(w.WorkflowError, code):
                    w.validate_policy(policy)

    def test_policy_cutoff_maps_the_new_sections(self):
        base = w.validate_policy(copy.deepcopy(self.policy))
        def cutoff(mutate):
            changed = copy.deepcopy(base)
            mutate(changed)
            return w.policy_cutoff(base, changed)
        self.assertEqual(cutoff(lambda p: p.update(profiles={'enabled': True})), w.BASE_STAGES.index('plan'))
        self.assertEqual(cutoff(lambda p: p.update(artifacts={'enforce': 'all'})), w.BASE_STAGES.index('analyze'))
        self.assertEqual(cutoff(lambda p: p['issue_sync'].update(taskstoissues='phase-lazy')),
                         w.BASE_STAGES.index('taskstoissues'))
        for operational in (lambda p: p.update(project_sync={'points': ['pr']}),
                            lambda p: p.update(scope={'board_cache_seconds': 0}),
                            lambda p: p['clarification'].update(max_questions_per_round=3, in_session_first_round=True)):
            self.assertEqual(cutoff(operational), len(w.BASE_STAGES))


class TierTests(Base):
    def test_tier_bands_and_stage_lists(self):
        self.profiles()
        self.assertEqual([w.tier(self.policy, s) for s in (1, 3, 5, 8, 13)],
                         ['lite', 'lite', 'standard', 'standard', 'full'])
        self.assertEqual(w.tier(w.default_policy(True, True), 1), 'full')  # profiles absent
        full = w.stages(self.policy)
        self.assertEqual(w.stages(self.policy, 'full'), full)
        self.assertEqual(w.stages(self.policy, 'standard'), [s for s in full if s != 'tasks'])
        self.assertEqual(w.stages(self.policy, 'lite'),
                         [s for s in full if s not in ('tasks',) + w.LITE_SKIPPED])

    def test_lean_execution_defaults_on_for_lite_and_standard_unless_disabled(self):
        policy = w.default_policy(False, False)
        self.assertFalse(lean_policy.enabled(policy))
        self.assertTrue(lean_policy.enabled(policy, 'lite'))
        self.assertTrue(lean_policy.enabled(policy, 'standard'))
        self.assertFalse(lean_policy.enabled(policy, 'full'))
        policy['lean_execution'] = {'enabled': False}
        self.assertFalse(lean_policy.enabled(policy, 'lite'))

    def test_scope_receipt_requires_an_effort_score_when_profiles_are_enabled(self):
        self.profiles()
        run = self.run_object()
        claim = run.claim(self.usage())
        with self.assertRaisesRegex(w.WorkflowError, 'EFFORT_SCORE_REQUIRED'):
            run.complete(claim['token'], self.receipt('scope'))
        with self.assertRaisesRegex(w.WorkflowError, 'EFFORT_SCORE_REQUIRED'):
            run.complete(claim['token'], self.scope_receipt(4))
        run.complete(claim['token'], self.scope_receipt(2))
        self.assertEqual(run.load()['receipts']['scope']['effort_score'], 2)

    def test_lite_freezes_profile_merges_tasks_skips_stages_and_runs_lint(self):
        self.profiles()
        run = self.run_object()
        self.advance(run, 'clarify', {'scope': self.scope_receipt(2)})
        (run.feature / 'research.md').write_text('# Research', encoding='utf-8')
        claim = run.claim(self.usage())
        self.assertEqual((claim['stage'], claim['merged']), ('plan', ['tasks']))
        state = run.load()
        self.assertEqual((state['profile']['tier'], state['profile']['score']), ('lite', 2))
        self.assertEqual(set(state['skipped']), {'tasks', 'qa_analyze', 'manual_analyze', 'qa_document', 'manual_update'})
        self.assertEqual(state['commands']['analyze'], w.LINT_COMMAND)
        self.assertIn('environment', claim)  # lean execution defaults on for lite
        skipped = [e['stage'] for e in self.events(run) if e['event'] == 'skipped']
        self.assertEqual(set(skipped), set(state['skipped']))
        with self.assertRaisesRegex(w.WorkflowError, 'MERGED_TASKS_REQUIRED'):
            run.complete(claim['token'], self.receipt('plan'))
        result = run.complete(claim['token'], self.merged_plan_receipt())
        self.assertEqual((result['stage'], result['command']), ('analyze', w.LINT_COMMAND))
        self.assertEqual(result['skipped'], state['skipped'])
        # Lite: research.md is optional, so it is not a required input of later stages.
        self.assertNotIn(self.feature + '/research.md', w.required_inputs(self.root, self.feature, 'analyze'))
        self.assertIn(self.feature + '/research.md', w.required_inputs(self.root, self.feature, 'analyze', 'full'))
        claim = run.claim(self.usage())
        with self.assertRaisesRegex(w.WorkflowError, 'LINT_RECEIPT_REQUIRED'):
            run.complete(claim['token'], self.receipt('analyze'))
        run.complete(claim['token'], self.lint_receipt())
        state = run.load()
        self.assertEqual(state['receipts']['analyze']['command'], w.LINT_COMMAND)
        self.assertEqual(state['stage_plan']['stages'], w.stages(self.policy, 'lite'))
        self.assertEqual(run.next(state)['stage'], 'taskstoissues')
        checkpoint_validator().validate(state)

    def test_lint_resolved_analyze_also_accepts_a_model_analyze(self):
        self.profiles()
        run = self.run_object()
        self.advance(run, 'clarify', {'scope': self.scope_receipt(5)})
        claim = run.claim(self.usage())
        run.complete(claim['token'], self.merged_plan_receipt())
        state = run.load()
        self.assertEqual(state['profile']['tier'], 'standard')
        self.assertEqual(set(state['skipped']), {'tasks'})
        self.assertEqual(run.next(state)['stage'], 'qa_analyze')  # standard keeps QA and manual analysis
        self.advance(run, 'manual_analyze')
        claim = run.claim(self.usage())
        receipt = self.receipt('analyze')
        receipt['command'] = w.COMMANDS['analyze']
        run.complete(claim['token'], receipt)
        self.assertEqual(run.load()['receipts']['analyze']['command'], w.COMMANDS['analyze'])

    def test_profiles_disabled_keeps_the_full_list(self):
        run = self.run_object()
        self.advance(run, 'clarify')
        claim = run.claim(self.usage())
        self.assertNotIn('merged', claim)
        self.assertNotIn('profile', run.load())

    def test_score_above_standard_runs_full(self):
        self.profiles()
        run = self.run_object()
        self.advance(run, 'clarify', {'scope': self.scope_receipt(13)})
        claim = run.claim(self.usage())
        self.assertNotIn('merged', claim)
        state = run.load()
        self.assertEqual(state['profile']['tier'], 'full')
        self.assertEqual(state['skipped'], {})


class ClaimOutputTests(Base):
    def test_claim_prints_reference_text_side_effects_and_project_sync(self):
        self.policy['project_sync'] = {'points': ['specify', 'execute', 'pr']}
        self.configure()
        run = self.run_object()
        self.advance(run, 'specify')
        claim = run.claim(self.usage())
        self.assertEqual(claim['stage'], 'clarify')
        reference = SCRIPT.parents[1] / 'skills/workflow/references/stage-clarify.md'
        self.assertEqual(claim['reference_text'], reference.read_text(encoding='utf-8-sig'))
        self.assertEqual(claim['side_effects'], [self.feature + '/spec.md', '.specify/project-sync-state.json',
                                                 self.feature + '/checklists/*.md'])
        self.assertFalse(claim['project_sync'])

    def test_cli_claim_omits_baseline_and_complete_is_compact_unless_verbose(self):
        run = self.run_object()
        usage = self.root / 'usage.json'
        w.write(usage, self.usage())
        code, claim = self.cli('claim', '--feature', self.feature, '--usage', str(usage))
        self.assertEqual(code, 0)
        self.assertNotIn('baseline', claim)
        self.assertIn('baseline', run.load()['active'])
        self.assertTrue(claim['project_sync'] is False and claim['reference_text'])
        receipt = self.root / 'receipt.json'
        w.write(receipt, self.receipt('scope'))
        code, done = self.cli('complete', '--feature', self.feature, '--token', claim['token'], '--receipt', str(receipt))
        self.assertEqual(code, 0)
        self.assertEqual(done, {'ok': True, 'stage': 'scope',
                                'next': {'stage': 'specify', 'command': 'speckit.specify', 'reason': 'pending'}})
        code, claim = self.cli('claim', '--feature', self.feature, '--usage', str(usage), '--verbose')
        self.assertIn('baseline', claim)
        w.write(receipt, self.receipt('specify'))
        code, done = self.cli('complete', '--feature', self.feature, '--token', claim['token'], '--receipt',
                              str(receipt), '--verbose')
        self.assertEqual(done['completed'], 'specify')
        self.assertEqual(done['stage'], 'clarify')


class SideEffectTests(Base):
    def test_side_effect_globs_stay_within_one_folder(self):
        patterns = w.side_effects(self.policy, self.feature, 'clarify')
        self.assertTrue(w.matches_side_effect(self.feature + '/checklists/requirements.md', patterns))
        self.assertTrue(w.matches_side_effect(self.feature.replace('/', '\\') + '\\checklists\\a.md', patterns))
        self.assertFalse(w.matches_side_effect(self.feature + '/checklists/deep/a.md', patterns))
        self.assertFalse(w.matches_side_effect(self.feature + '/plan.md', patterns))
        self.policy['issue_sync']['taskstoissues'] = 'phase-lazy'
        self.assertIn(self.feature + '/workflow/task-issues.json', w.side_effects(self.policy, self.feature, 'execute'))

    def test_clarify_may_change_a_checklist_an_earlier_receipt_depends_on(self):
        run = self.run_object()
        checklist = self.write(self.feature + '/checklists/requirements.md', '- [ ] item')
        other = self.write(self.feature + '/notes.md', 'note')
        self.advance(run, 'scope')
        claim = run.claim(self.usage())
        receipt = self.receipt('specify')
        receipt['inputs'] = receipt['inputs'] + [checklist, other]
        run.complete(claim['token'], receipt)
        claim = run.claim(self.usage())
        self.write(checklist, '- [x] item')
        run.complete(claim['token'], self.receipt('clarify'))
        state = run.load()
        self.assertIn(checklist, state['lineage'][-1]['changes'])
        self.assertEqual(state['receipts']['specify']['fingerprints'][checklist],
                         w.fingerprint_files(self.root, [checklist])[checklist])
        claim = run.claim(self.usage())
        self.write(other, 'changed note')
        with self.assertRaisesRegex(w.WorkflowError, 'UPSTREAM_INPUT_CHANGED_DURING_STAGE: ' + other):
            run.complete(claim['token'], self.receipt('plan'))


class DoctorCacheTests(Base):
    def test_claims_reuse_a_green_doctor_until_something_it_checked_changes(self):
        run = self.run_object()
        calls = []
        real = w.doctor
        def counting(*args, **kwargs):
            calls.append(kwargs)
            return real(*args, **kwargs)
        with patch.object(w, 'doctor', counting):
            self.advance(run, 'specify')
            self.assertEqual(len(calls), 1)
            cache = w.read(self.root / w.DOCTOR_CACHE)
            self.assertTrue(cache['result']['ok'])
            registry = self.root / '.specify/extensions.yml'
            stamp = registry.stat().st_mtime_ns + 5_000_000_000
            os.utime(registry, ns=(stamp, stamp))
            claim = run.claim(self.usage())
            self.assertEqual(len(calls), 2)
            run.complete(claim['token'], self.receipt('clarify'))
            cache = w.read(self.root / w.DOCTOR_CACHE)
            cache['at'] -= w.DOCTOR_CACHE_SECONDS + 1
            w.write(self.root / w.DOCTOR_CACHE, cache)
            run.claim(self.usage())
            self.assertEqual(len(calls), 3)

    def test_policy_change_invalidates_the_cache_and_a_red_result_is_never_cached(self):
        run = self.run_object()
        claim = run.claim(self.usage())
        run.complete(claim['token'], self.receipt('scope'))
        before = w.read(self.root / w.DOCTOR_CACHE)['key']['policy_digest']
        self.policy['project_sync'] = {'points': ['pr']}
        self.configure()
        run = w.Run(self.root, self.feature)
        with patch.object(w, 'doctor', return_value={'ok': False, 'errors': ['BROKEN'], 'project_checked': True}):
            with self.assertRaisesRegex(w.WorkflowError, 'BROKEN'):
                run.claim(self.usage())
        self.assertEqual(w.read(self.root / w.DOCTOR_CACHE)['key']['policy_digest'], before)

    def test_inventory_and_eol_scan_run_only_in_the_explicit_doctor(self):
        with patch.object(w.skill_inventory, 'inventory', return_value={'hosts': {}}) as inventory, \
                patch.object(w, 'eol_drift', return_value=[]) as eol:
            run = self.run_object()
            run.claim(self.usage())
            w.doctor(self.root, self.policy, project=True)
            self.assertEqual((inventory.call_count, eol.call_count), (0, 0))
            result = w.doctor(self.root, self.policy, project=True, explicit=True)
            self.assertEqual((inventory.call_count, eol.call_count), (1, 1))
            self.assertIn('skill_inventory', result)

    def test_explicit_doctor_command_refreshes_the_cache(self):
        (self.root / w.DOCTOR_CACHE).parent.mkdir(parents=True, exist_ok=True)
        code, result = self.cli('doctor', '--project')
        self.assertEqual(code, 0, result)
        cache = w.read(self.root / w.DOCTOR_CACHE)
        self.assertTrue(cache['result']['ok'])
        self.assertLess(time.time() - cache['at'], 60)


class WriteRetryTests(unittest.TestCase):
    def test_write_retries_a_briefly_held_target(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'state.json'
            real, attempts = os.replace, []
            def flaky(source, destination):
                attempts.append(destination)
                if len(attempts) <= 2:
                    raise PermissionError(5, 'Access is denied')
                return real(source, destination)
            with patch.object(w.os, 'replace', flaky), patch.object(w.time, 'sleep'):
                w.write(target, {'ok': True})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(w.read(target), {'ok': True})
            def always(source, destination):
                raise PermissionError(5, 'Access is denied')
            with patch.object(w.os, 'replace', always), patch.object(w.time, 'sleep') as sleep:
                with self.assertRaises(PermissionError):
                    w.write(target, {'ok': False})
            self.assertEqual(sleep.call_count, 9)


class InventoryAndHandoffTests(Base):
    def test_source_stages_store_an_inventory_side_file_read_by_status_and_ci_index(self):
        self.write('src/app.py', 'print(1)')
        run = self.run_object()
        self.complete_through(run, 'verify')
        receipt = run.load()['receipts']['verify']
        self.assertNotIn('source_fingerprints', receipt)
        reference = receipt['source_inventory']
        self.assertEqual(reference['path'], 'workflow/inventory/verify-' + receipt['claim_id'] + '.json')
        inventory = w.source_fingerprints_of(self.root, receipt, self.feature)
        self.assertEqual(inventory, w.source_fingerprints(self.root))
        self.assertTrue(w.receipt_current(self.root, self.feature, 'verify', receipt, self.policy))
        legacy = {key: value for key, value in receipt.items() if key != 'source_inventory'}
        legacy['source_fingerprints'] = inventory
        self.assertEqual(w.source_fingerprints_of(self.root, legacy), inventory)
        self.assertTrue(w.receipt_current(self.root, self.feature, 'verify', legacy, self.policy))
        self.commit_all()
        result = c.check_index(self.root, self.feature)
        self.assertGreater(result['indexed_paths'], 0)
        side = self.root / self.feature / reference['path']
        side.write_text(side.read_text(encoding='utf-8').replace('"', "'", 2), encoding='utf-8')
        status = w.receipt_status(self.root, self.feature, 'verify', receipt, self.policy)
        self.assertEqual(status['reason'], 'source-inventory-invalid')
        checkpoint_validator().validate(run.load())

    def test_pause_writes_the_status_resume_prompt_and_keeps_handoff_text_outside_the_block(self):
        run = self.run_object()
        handoff = run.path.parent / 'handoff.md'
        handoff.parent.mkdir(parents=True, exist_ok=True)
        handoff.write_text('# My notes\n\nKeep this.\n', encoding='utf-8')
        result = run.claim(self.usage(.51, method='measured'))
        self.assertEqual(result['prompt'], 'Run python .specify/extensions/workflow/scripts/workflow.py status '
                         '--feature ' + self.feature + ' and continue with speckit.workflow.continue; do not read '
                         'checkpoint.json directly.\n')
        text = handoff.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('# My notes\n\nKeep this.\n'))
        self.assertEqual(text.count(w.HANDOFF_BEGIN), 1)
        handoff.write_text(text + '\nAfter the block.\n', encoding='utf-8')
        run.claim(self.usage(.51, method='measured'))
        text = handoff.read_text(encoding='utf-8')
        self.assertEqual((text.count(w.HANDOFF_BEGIN), text.count(w.HANDOFF_END)), (1, 1))
        self.assertTrue(text.startswith('# My notes') and text.endswith('After the block.\n'))
        self.assertEqual(w.handoff_text('# Workflow handoff\n\n- old', 'BLOCK'), 'BLOCK\n')

    def test_status_runs_without_run_roots_and_shows_profile_and_next(self):
        run = self.run_object()
        self.advance(run, 'scope')
        code, result = self.cli('status', '--feature', self.feature)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['completed'], ['scope'])
        self.assertEqual(result['next_action']['stage'], 'specify')


class RevalidateUpstreamTests(Base):
    def setUp(self):
        super().setUp()
        self.policy = w.default_policy(False, False)
        self.configure()
        self.run = self.run_object()
        self.advance(self.run, 'analyze')
        self.spec = self.root / self.feature / 'spec.md'

    def entry(self, stage):
        receipt = self.receipt(stage)
        return {key: receipt[key] for key in ('summary', 'evidence', 'inputs')}

    def test_whitespace_only_markdown_change_is_restamped_without_a_receipt(self):
        self.spec.write_bytes(self.spec.read_bytes().replace(b'\n', b'\r\n') + b'   \r\n')
        self.assertEqual(self.run.next(self.run.load())['stage'], 'specify')
        plan = self.run.revalidate_upstream('analyze', plan=True)
        self.assertEqual(plan['needs_receipt'], [])
        self.assertEqual(plan['restamp'], ['specify', 'clarify', 'plan', 'tasks', 'analyze'])
        self.assertTrue(all(paths == [] for paths in plan['changed'].values()))
        result = self.run.revalidate_upstream('analyze', {'stages': {}})
        self.assertEqual(result['restamped'], plan['restamp'])
        state = self.run.load()
        self.assertEqual(state['receipts']['specify']['fingerprints'][self.feature + '/spec.md'],
                         w.fingerprint_files(self.root, [self.feature + '/spec.md'])[self.feature + '/spec.md'])
        self.assertEqual(self.run.next(state)['stage'], 'taskstoissues')
        kinds = {(e['event'], e['episode_id']) for e in self.events(self.run) if e['event'] == 'revalidate-upstream'}
        self.assertEqual(len(kinds), 1)
        self.assertTrue(next(iter(kinds))[1].startswith('revalidate-upstream:'))
        checkpoint_validator().validate(state)

    def test_real_change_needs_an_entry_per_stage_and_reuses_complete_validation(self):
        self.spec.write_text('# Changed requirement', encoding='utf-8')
        plan = self.run.revalidate_upstream('plan', plan=True)
        self.assertEqual(plan['changed'], {stage: [self.feature + '/spec.md'] for stage in ('specify', 'clarify', 'plan')})
        with self.assertRaisesRegex(w.WorkflowError, 'REVALIDATE_UPSTREAM_RECEIPT_MISSING: clarify, plan'):
            self.run.revalidate_upstream('plan', {'stages': {'specify': self.entry('specify')}})
        with self.assertRaisesRegex(w.WorkflowError, 'REVALIDATE_UPSTREAM_STAGE_NOT_STALE: scope'):
            self.run.revalidate_upstream('plan', {'stages': {'scope': self.entry('scope')}})
        bad = {stage: self.entry(stage) for stage in ('specify', 'clarify', 'plan')}
        bad['plan']['evidence'] = [self.feature + '/evidence/missing.txt']
        with self.assertRaisesRegex(w.WorkflowError, 'EVIDENCE_MISSING'):
            self.run.revalidate_upstream('plan', {'stages': bad})
        self.assertEqual(self.run.load()['receipts']['specify']['fingerprints'],
                         self.run.load()['receipts']['specify']['fingerprints'])
        result = self.run.revalidate_upstream('plan', {'stages': {
            stage: self.entry(stage) for stage in ('specify', 'clarify', 'plan')}})
        self.assertEqual(result['revalidated'], ['specify', 'clarify', 'plan'])
        state = self.run.load()
        self.assertEqual(state['receipts']['clarify']['answers_applied'], True)  # carried from the old receipt
        self.assertEqual(state['receipts']['plan']['revalidated_upstream']['via'], 'receipt')
        self.assertEqual(self.run.next(state)['stage'], 'tasks')  # tasks stays stale: past --through

    def test_refused_with_an_active_claim_and_when_nothing_is_stale(self):
        with self.assertRaisesRegex(w.WorkflowError, 'REVALIDATE_UPSTREAM_NOT_NEEDED'):
            self.run.revalidate_upstream('plan', {'stages': {}})
        self.run.claim(self.usage())
        with self.assertRaisesRegex(w.WorkflowError, 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_REVALIDATE_UPSTREAM'):
            self.run.revalidate_upstream('plan', plan=True)

    def test_cli_plan(self):
        self.spec.write_text('# Changed requirement', encoding='utf-8')
        code, result = self.cli('revalidate-upstream', '--feature', self.feature, '--through', 'specify', '--plan')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['changed'], {'specify': [self.feature + '/spec.md']})
        code, result = self.cli('revalidate-upstream', '--feature', self.feature, '--through', 'specify')
        self.assertIn('REVALIDATE_UPSTREAM_RECEIPT_REQUIRED', result['error'])


class BindOnlyAndLazyIssueTests(Base):
    def test_rendered_spec_makes_specify_bind_only(self):
        run = self.run_object()
        self.advance(run, 'scope')
        self.write(self.feature + '/spec.md', '<!-- sanduq-scope:rendered ' + 'a' * 64 + ' -->\n# Spec\n')
        claim = run.claim(self.usage())
        self.assertEqual((claim['stage'], claim['mode']), ('specify', 'bind-only'))
        run.complete(claim['token'], self.receipt('specify'))

    def test_plain_spec_keeps_the_existing_modes(self):
        run = self.run_object()
        self.advance(run, 'scope')
        self.write(self.feature + '/spec.md', '# Spec\n<!-- sanduq-scope:rendered ' + 'a' * 64 + ' -->\n')
        self.assertNotEqual(run.claim(self.usage())['mode'], 'bind-only')

    def test_phase_lazy_needs_lazy_receipt_first_phase_mapping_and_every_task_by_ready(self):
        self.policy = w.default_policy(False, False)
        self.policy['issue_sync']['taskstoissues'] = 'phase-lazy'
        self.configure()
        run = self.run_object()
        self.write(self.feature + '/tasks.md',
                   '# Tasks\n## Phase 1\n- [x] T001 Done behavior\n## Phase 2\n- [x] T002 Later behavior\n')
        self.advance(run, 'analyze')
        claim = run.claim(self.usage())
        self.assertEqual(claim['stage'], 'taskstoissues')
        w.write(run.feature / 'workflow/task-issues.json', {'repo': 'acme/app', 'parent': 10, 'feature': self.feature,
                                                            'tasks': {'T002': {'number': 12, 'linked': True}}})
        receipt = self.receipt('taskstoissues')
        with self.assertRaisesRegex(w.WorkflowError, 'TASK_ISSUES_LAZY_REQUIRED'):
            run.complete(claim['token'], receipt)
        receipt['lazy'] = True
        with self.assertRaisesRegex(w.WorkflowError, 'TASK_MAPPING_FIRST_PHASE_INCOMPLETE: T001'):
            run.complete(claim['token'], receipt)
        w.write(run.feature / 'workflow/task-issues.json', {'repo': 'acme/app', 'parent': 10, 'feature': self.feature,
                                                            'tasks': {'T001': {'number': 11, 'linked': True}}})
        run.complete(claim['token'], receipt)
        state = run.load()
        with self.assertRaisesRegex(w.WorkflowError, 'TASK_MAPPING_INCOMPLETE: T002; phase-lazy'):
            w.ready_checks(self.root, self.feature, self.policy, state,
                           rules={'tasks': False, 'task_links': True, 'documentation': False})
        # Execute may extend the mapping phase by phase.
        claim = run.claim(self.usage())
        w.write(run.feature / 'workflow/task-issues.json', {'repo': 'acme/app', 'parent': 10, 'feature': self.feature,
                                                            'tasks': {'T001': {'number': 11, 'linked': True},
                                                                      'T002': {'number': 12, 'linked': True}}})
        run.complete(claim['token'], self.receipt('execute'))
        self.assertEqual(w.ready_checks(self.root, self.feature, self.policy, run.load(),
                                        rules={'tasks': False, 'task_links': True, 'documentation': False}),
                         ['task_links'])

    def test_first_phase_tasks(self):
        self.assertEqual(w.first_phase_tasks('# T\n## Setup\n- [ ] T001 a\n- [x] T002 b\n## Core\n- [ ] T003 c\n'),
                         ['T001', 'T002'])
        self.assertEqual(w.first_phase_tasks('- [ ] T001 a\n## Next\n- [ ] T002 b\n'), ['T001'])


class LintRecordEndToEndTests(Base):
    def test_lint_record_completes_analyze_on_a_lite_feature(self):
        self.profiles()
        self.write(self.feature + '/spec.md', '# Spec\n\n## Requirements\n\n- **FR-001**: The parser accepts input.\n')
        run = self.run_object()
        self.advance(run, 'clarify', {'scope': self.scope_receipt(2)})
        claim = run.claim(self.usage())
        self.assertEqual((claim['stage'], claim['merged']), ('plan', ['tasks']))
        self.write(self.feature + '/tasks.md', '# Tasks\n\n## Phase 1: Setup\n\n- [x] T001 Implement FR-001 parser input\n')
        receipt = self.receipt('plan')
        receipt['inputs'] = receipt['inputs'] + [self.feature + '/tasks.md']
        run.complete(claim['token'], receipt)
        claim = run.claim(self.usage())
        self.assertEqual((claim['stage'], claim['command']), ('analyze', w.LINT_COMMAND))
        done = subprocess.run([sys.executable, str(SCRIPT.parent / 'lint.py'), '--root', str(self.root), '--feature',
                               self.feature, '--record', '--token', claim['token']],
                              capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        state = run.load()
        stored = state['receipts']['analyze']
        self.assertEqual(stored['command'], w.LINT_COMMAND)
        self.assertIs(stored['lint']['ok'], True)
        self.assertIsNone(state['active'])
        self.assertEqual(run.next(state)['stage'], 'taskstoissues')


class LeanTierDispatchTests(Base):
    """delegate_dispatch reads the feature's frozen tier: lite and standard are lean by default."""

    def checkpoint(self, tier):
        branch = w.git(self.root, 'branch', '--show-current')
        w.write(self.root / self.feature / 'workflow/checkpoint.json',
                {'feature': self.feature, 'branch': branch, 'commands': dict(w.COMMANDS),
                 'active': {'stage': 'execute', 'token': 'claim-token', 'session_id': 'session'},
                 'profile': {'tier': tier, 'score': 2, 'fixed_at': w.now()}})

    def dispatch_view(self):
        import delegate_dispatch as dispatch
        with patch.dict(os.environ, clean_env(), clear=True):
            env = dispatch.driver_env(self.root, 'intent', feature=self.feature)
        return dispatch, dispatch.lean_enabled(self.root, self.feature), env.get('SANDUQ_WORKFLOW_CLAIM_TOKEN')

    def test_lite_feature_is_lean_in_the_dispatcher(self):
        import delegation
        self.policy['delegation']['enabled'] = True
        self.configure()
        self.checkpoint('lite')
        dispatch, lean, token = self.dispatch_view()
        self.assertEqual((lean, token), (True, 'claim-token'))
        self.assertFalse(dispatch.lean_enabled(self.root))  # no feature: the policy alone decides
        with patch.dict(os.environ, clean_env(), clear=True), patch.object(dispatch, 'candidate_start') as launch:
            with self.assertRaisesRegex(delegation.DelegationError, 'LEAN_COORDINATOR_OWNS_STAGE'):
                dispatch.start(self.root, self.feature, 'stage:execute', token='claim-token')
        launch.assert_not_called()
        attempt = {'pinned': False, 'retry_count': 0, 'route_candidates': [], 'candidate_index': 0}
        self.assertIsNone(dispatch.retry_plan(self.policy, attempt, {'status': 'failed'}, False, 'codex', 'lite'))

    def test_full_feature_is_lean_only_when_the_policy_enables_it(self):
        self.checkpoint('full')
        dispatch, lean, token = self.dispatch_view()
        self.assertEqual((lean, token), (False, None))
        self.policy['lean_execution'] = {'enabled': True}
        self.configure()
        self.assertEqual(self.dispatch_view()[1:], (True, 'claim-token'))

    def test_explicit_false_turns_lean_off_for_lite(self):
        self.policy['lean_execution'] = {'enabled': False}
        self.configure()
        self.checkpoint('lite')
        self.assertEqual(self.dispatch_view()[1:], (False, None))


if __name__ == '__main__':
    unittest.main()
