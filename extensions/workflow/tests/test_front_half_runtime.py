"""Front-half runtime: policy keys, tiers, claim output, side effects, doctor cache, source inventories,
the resume contract, revalidate-upstream, the bind-only Specify hook and phase-lazy task issues."""
import copy
import json
import os
import re
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
from runtime_patch import patch_runtime  # noqa: E402
from test_receipt_contract import Harness, checkpoint_validator  # noqa: E402
import lifecycle_snapshot  # noqa: E402

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

    def run_object(self):
        # W22/X25: the started run, and below each lifecycle prefix, is built once per class and starting tree.
        return lifecycle_snapshot.reuse(self, lambda: Harness.run_object(self), lambda: w.Run(self.root, self.feature))

    def advance(self, run, last, receipts=None):
        """Claim and complete every stage up to and including `last` (a copy when this class already did it)."""
        key = (last, json.dumps(receipts or {}, sort_keys=True))
        lifecycle_snapshot.reuse(self, lambda: self.advance_fresh(run, last, receipts), lambda: None, key)

    def advance_fresh(self, run, last, receipts=None):
        """`advance` that always runs the stages, for a test that observes them (patches, counters)."""
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
        policy['progress'] = {'hook_wiring': 'native', 'post_tool_matcher': 'Edit|Write'}
        policy['illustrate'] = {'hooks': {'self_check': True}}
        return policy

    def test_new_keys_validate_and_absent_keys_keep_defaults(self):
        policy = w.validate_policy(self.full_policy())
        self.assertEqual(policy['issue_sync']['taskstoissues'], 'phase-lazy')
        default = w.validate_policy(copy.deepcopy(self.policy))
        for key in ('profiles', 'artifacts', 'project_sync', 'progress', 'illustrate'):
            self.assertNotIn(key, default)
        for partial in ({'progress': {}}, {'progress': {'hook_wiring': 'speckit'}}, {'illustrate': {}},
                        {'illustrate': {'hooks': {}}}):
            w.validate_policy({**copy.deepcopy(self.policy), **partial})
        self.assertEqual(w.stages(default), w.BASE_STAGES)
        self.assertTrue(all(w.project_sync(default, stage) for stage in w.PROJECT_SYNC_POINTS))
        self.assertFalse(w.project_sync(default, 'clarify'))
        self.assertEqual(w.project_sync(default, 'execute', 'specs/001-a'), {
            'phase': 'in-progress',
            'command': 'python .specify/extensions/workflow/scripts/workflow.py project-sync --feature specs/001-a '
                       '--phase in-progress'})
        self.assertEqual({stage: w.project_sync(default, stage)['phase'] for stage in w.PROJECT_SYNC_POINTS},
                         w.PROJECT_SYNC_PHASES)

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
            (lambda p: p.update(profiles={'enabled': True, 'tiny': {}}), 'POLICY_KEY_UNKNOWN: profiles.tiny'),
            (lambda p: p.update(profiles={'enabled': True, 'lite': {'max_score': 9}}), 'PROFILES_POLICY_INVALID'),
            (lambda p: p['clarification'].update(max_questions_per_round=0), 'CLARIFICATION_POLICY_INVALID'),
            (lambda p: p['clarification'].update(in_session_first_round='true'), 'CLARIFICATION_POLICY_INVALID'),
            (lambda p: p.update(artifacts={'budgets': {'spec_mb': 1}}), 'POLICY_KEY_UNKNOWN: artifacts.budgets.spec_mb; did you mean artifacts.budgets.spec_kb'),
            (lambda p: p.update(artifacts={'enforce': 'never'}), 'ARTIFACTS_POLICY_INVALID'),
            (lambda p: p.update(project_sync={'points': ['clarify']}), 'PROJECT_SYNC_POLICY_INVALID'),
            (lambda p: p.update(project_sync={'points': ['pr'], 'extra': 1}), 'POLICY_KEY_UNKNOWN: project_sync.extra'),
            (lambda p: p.update(scope={'board_cache_seconds': -1}), 'SCOPE_BOARD_CACHE_INVALID'),
            (lambda p: p.update(progress={'hook_wiring': 'hooks'}), 'PROGRESS_POLICY_INVALID'),
            (lambda p: p.update(progress={'post_tool_matcher': 1}), 'PROGRESS_POLICY_INVALID'),
            (lambda p: p.update(progress={'matcher': ''}), 'POLICY_KEY_UNKNOWN: progress.matcher'),
            (lambda p: p.update(progress='native'), 'PROGRESS_POLICY_INVALID'),
            (lambda p: p.update(illustrate={'hooks': {'self_check': 'yes'}}), 'ILLUSTRATE_POLICY_INVALID'),
            (lambda p: p.update(illustrate={'hooks': {'verify': True}}), 'POLICY_KEY_UNKNOWN: illustrate.hooks.verify'),
            (lambda p: p.update(illustrate={'theme': {}}), 'POLICY_KEY_UNKNOWN: illustrate.theme'),
            (lambda p: p.update(illustrate={'hooks': True}), 'ILLUSTRATE_POLICY_INVALID'),
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
                            lambda p: p.update(progress={'hook_wiring': 'native'}),
                            lambda p: p.update(illustrate={'hooks': {'self_check': True}}),
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

    def plan_claim_with_scope_source(self, source, labels=None):
        """Claim Plan after a Scope receipt scored 2, with this scope-source.json and these issue labels."""
        self.profiles()
        run = self.run_object()
        self.advance_fresh(run, 'scope', {'scope': self.scope_receipt(2)})
        w.write(run.feature / 'scope-source.json', source)
        self.advance_fresh(run, 'clarify')
        calls = []

        class GitHub:
            def api(self, endpoint):
                calls.append(endpoint)
                return {'number': 10, 'labels': [{'name': name} for name in labels or []]}
        with patch('decisions.GitHub', GitHub):
            try:
                return run.claim(self.usage()), calls
            except w.WorkflowError as exc:
                return exc, calls

    def test_effort_label_that_differs_from_the_receipt_score_is_refused(self):
        # OMAR-05: label effort:8, receipt score 2; no cached score, so one GitHub read decides.
        error, calls = self.plan_claim_with_scope_source({'repo': 'acme/app', 'issue': 10}, ['bug', 'effort:8'])
        self.assertEqual(calls, ['repos/acme/app/issues/10'])
        self.assertRegex(str(error), r'^EFFORT_SCORE_MISMATCH: the Scope receipt records effort_score 2 but '
                                     r'effort:8 label on acme/app#10 says 8;.* refresh --feature ')

    def test_scope_verified_score_is_used_without_a_github_read(self):
        error, calls = self.plan_claim_with_scope_source({'repo': 'acme/app', 'issue': 10, 'score': 8})
        self.assertIn('EFFORT_SCORE_MISMATCH', str(error))
        self.assertIn('scope-source.json (verified by Scope at bind) says 8', str(error))
        self.assertEqual(calls, [])

    def test_matching_verified_score_fixes_the_tier(self):
        claim, calls = self.plan_claim_with_scope_source({'repo': 'acme/app', 'issue': 10, 'score': 2})
        self.assertEqual((claim['stage'], claim['profile']['tier'], calls), ('plan', 'lite', []))

    def test_missing_effort_label_is_unverified(self):
        error, _ = self.plan_claim_with_scope_source({'repo': 'acme/app', 'issue': 10}, ['bug'])
        self.assertIn('EFFORT_SCORE_UNVERIFIED: acme/app#10 carries 0 effort:<n> labels', str(error))

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
        self.advance(run, 'scope')
        claim = run.claim(self.usage(), finalize=True)
        self.assertEqual((claim['stage'], claim['project_sync']), ('specify', {
            'phase': 'open', 'command': 'python .specify/extensions/workflow/scripts/workflow.py project-sync '
                                        '--feature ' + self.feature + ' --phase open'}))
        run.complete(claim['token'], self.receipt('specify'))
        claim = run.claim(self.usage())
        self.assertEqual(claim['stage'], 'clarify')
        reference = SCRIPT.parents[1] / 'skills/workflow/references/stage-clarify.md'
        self.assertEqual(claim['reference_text'], reference.read_text(encoding='utf-8-sig'))
        self.assertEqual(claim['side_effects'], [self.feature + '/spec.md', '.specify/project-sync-state.json',
                                                 self.feature + '/checklists/*.md'])
        self.assertFalse(claim['project_sync'])

    FRAGMENTS = ('execute/lean.md', 'execute/orchestrator.md', 'execute/delegated-workers.md',
                 'execute/reporting-legacy.md', 'reporting.md')
    WORKER_RULE = '`git stash` and `git add -A`/`git add .` are forbidden for a task worker'

    def test_execute_protocol_carries_only_the_parts_of_its_mode(self):
        references = SCRIPT.parents[1] / 'skills/workflow/references'
        heading = {name: (references / name).read_text(encoding='utf-8').splitlines()[0] for name in self.FRAGMENTS}
        used = set()
        for lean in (True, False):
            for delegation in (True, False):
                for reporting in ('projection', 'refresh', 'legacy'):
                    policy = copy.deepcopy(self.policy)
                    policy['lean_execution'] = {'enabled': lean}
                    policy['delegation']['enabled'] = delegation
                    parts = w.execute_protocol(policy, 'full', reporting)
                    expected = {'execute/lean.md' if lean else 'execute/orchestrator.md',
                                'execute/reporting-legacy.md' if reporting == 'legacy' else 'reporting.md'}
                    if delegation:
                        expected.add('execute/delegated-workers.md')
                    self.assertEqual(parts[:2], ['execution-assign.md', 'execution-report.md'])
                    self.assertEqual(set(parts[2:]), expected)
                    text = w.reference_text(self.root, 'execute', parts)
                    self.assertTrue(text.startswith('# Stage reference: execute'))
                    for name in self.FRAGMENTS:
                        self.assertEqual(heading[name] in text, name in expected, (lean, delegation, reporting, name))
                    # worker prohibitions stay in the text whatever the guard hook does
                    self.assertIn(self.WORKER_RULE, re.sub(r'\s+', ' ', text))
                    used.update(parts)
        self.assertTrue(set(self.FRAGMENTS) <= used)

    def test_execute_claim_prints_its_reporting_mode_and_composed_protocol(self):
        run = self.run_object()
        self.advance(run, 'taskstoissues')
        legacy = ['execution-assign.md', 'execution-report.md', 'execute/orchestrator.md', 'execute/reporting-legacy.md']

        def reclaim(**kwargs):
            state = run.load()
            state['active'] = None
            run.save(state)
            return run.claim(self.usage(), **kwargs)

        claim = run.claim(self.usage())  # first claim: the full protocol
        self.assertEqual(claim['stage'], 'execute')
        self.assertEqual(claim['reporting']['mode'], 'legacy')  # Progress is not installed in the fixture
        protocol = claim['execute_protocol']
        self.assertEqual((protocol['files'], protocol['printed']), (legacy, True))
        self.assertIn('a dedicated orchestration agent schedules and integrates', protocol['summary'])
        self.assertIn('delegate_dispatch.py', protocol['summary'])
        self.assertEqual(claim['reference_text'], w.reference_text(self.root, 'execute', legacy))
        self.assertIn('## Legacy reporter calls (mode legacy only)', claim['reference_text'])
        self.assertEqual(run.load()['execute_protocol']['digest'], protocol['digest'])
        checkpoint_validator().validate(run.load())

        claim = reclaim()  # unchanged: named, not printed
        self.assertEqual(claim['execute_protocol']['digest'], protocol['digest'])
        self.assertIs(claim['execute_protocol']['printed'], False)
        self.assertIn('follow the summary', claim['execute_protocol']['note'])
        self.assertEqual(claim['execute_protocol']['summary'], protocol['summary'])  # OMAR-18: printed on every claim
        self.assertEqual(claim['reference_text'], w.reference_text(self.root, 'execute'))

        self.assertIs(reclaim(verbose=True)['execute_protocol']['printed'], True)  # --verbose always prints

        with patch('progress_bridge.mode', return_value={'mode': 'projection', 'source': 'hooks registered'}):
            claim = reclaim()  # mode change
        self.assertEqual(claim['reporting'], {'mode': 'projection', 'reason': 'hooks registered'})
        self.assertEqual((claim['execute_protocol']['files'][-1], claim['execute_protocol']['printed']),
                         ('reporting.md', True))
        self.assertNotIn('## Legacy reporter calls', claim['reference_text'])
        self.assertIs(reclaim()['execute_protocol']['printed'], True)  # back to legacy: changed again

        real = w.reference_text
        edited = lambda root, stage, parts=(): real(root, stage, parts) + ('One more rule.' + chr(10) if parts else '')
        with patch.object(w, 'reference_text', edited):
            claim = reclaim()  # content change
        self.assertIs(claim['execute_protocol']['printed'], True)
        self.assertIn('One more rule.', claim['reference_text'])

    def test_cli_verbose_claim_prints_the_protocol_again(self):
        run = self.run_object()
        self.advance(run, 'taskstoissues')
        run.claim(self.usage())
        state = run.load()
        state['active'] = None
        run.save(state)
        usage = self.root / 'usage.json'
        w.write(usage, self.usage())
        code, claim = self.cli('claim', '--feature', self.feature, '--usage', str(usage), '--verbose')
        self.assertEqual(code, 0)
        self.assertIs(claim['execute_protocol']['printed'], True)
        self.assertIn('## Legacy reporter calls', claim['reference_text'])

    def test_receipt_template_completes_every_stage_and_each_stage_field_is_required(self):
        self.profiles()
        self.policy['issue_sync'] = {'taskstoissues': 'phase-lazy', 'parent_link': 'native-subissue'}
        self.configure()
        # OMAR-01: every gating field is a placeholder the agent sets.
        fills = {'effort_score': 13, 'lint': {'ok': True, 'findings': 0},
                 'pr_url': 'https://github.com/acme/app/pull/11', 'outcome': 'passed', 'unresolved': 0,
                 'answers_applied': True, 'native_links_verified': True, 'blocking_findings': 0,
                 'images_verified': True}
        base = {'stage', 'outcome', 'summary', 'inputs', 'evidence'}
        run = self.run_object()
        seen = set()
        while True:
            claim = run.claim(self.usage(), finalize=True)
            stage = claim['stage']
            template = claim['receipt_template']
            fixture = self.receipt(stage)
            receipt = {**template, 'summary': fixture['summary'], 'evidence': fixture['evidence'],
                       'inputs': template['inputs'] + fixture['inputs']}
            receipt.update({key: fills[key] for key in template if key in fills})
            self.assertFalse([key for key, value in receipt.items() if '<' in json.dumps(value)], stage)
            for field in sorted(set(template) - base):
                with self.subTest(stage=stage, field=field), self.assertRaises(w.WorkflowError):
                    run.complete(claim['token'], {key: value for key, value in receipt.items() if key != field})
                seen.add(field)
            run.complete(claim['token'], receipt)  # the filled template is enough
            if stage == 'pr':
                break
        self.assertTrue({'effort_score', 'unresolved', 'answers_applied', 'parent_issue', 'native_links_verified',
                         'lazy', 'blocking_findings', 'pr_url', 'images_verified'} <= seen)

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
        with patch_runtime('doctor', counting):
            self.advance_fresh(run, 'specify')
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
        with patch_runtime('doctor', return_value={'ok': False, 'errors': ['BROKEN'], 'project_checked': True}):
            with self.assertRaisesRegex(w.WorkflowError, 'BROKEN'):
                run.claim(self.usage())
        self.assertEqual(w.read(self.root / w.DOCTOR_CACHE)['key']['policy_digest'], before)

    def test_inventory_and_eol_scan_run_only_in_the_explicit_doctor(self):
        with patch.object(w.skill_inventory, 'inventory', return_value={'hosts': {}}) as inventory, \
                patch_runtime('eol_drift', return_value=[]) as eol:
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


class GuardApprovalTests(Base):
    """Doctor and status say when Codex would skip the workflow guard hook (not trusted or not approved)."""
    GUARD = 'python .specify/extensions/workflow/hooks/guard.py'

    def setUp(self):
        super().setUp()
        self.codex_home = self.root / 'codex-home'
        self.codex_home.mkdir()
        environment = patch.dict(os.environ, {'CODEX_HOME': str(self.codex_home)})
        environment.start()
        self.addCleanup(environment.stop)
        self.hooks = self.root / '.codex/hooks.json'
        self.hooks.parent.mkdir(parents=True, exist_ok=True)
        self.hooks.write_text(json.dumps({'hooks': {'PreToolUse': [
            {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': self.GUARD}]}]}}), encoding='utf-8')

    def warnings(self):
        return [item for item in w.doctor(self.root, self.policy)['warnings'] if item.startswith('GUARD_HOOK_UNAPPROVED')]

    def approve(self, trusted=True):
        key = (str(self.hooks) + ':pre_tool_use:0:0').replace('\\', '\\\\')
        project = str(self.root).lower().replace('\\', '\\\\')
        text = f'[hooks.state."{key}"]\ntrusted_hash = "sha256:abc"\n'
        if trusted:
            text = f'[projects."{project}"]\ntrust_level = "trusted"\n\n' + text
        (self.codex_home / 'config.toml').write_text(text, encoding='utf-8')

    def test_unapproved_guard_warns_in_doctor_and_status_with_the_hooks_step(self):
        warnings = self.warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn('/hooks', warnings[0])
        run = self.run_object()
        status = w.native_run_status(self.root, run.relative, run.load(), [])
        self.assertEqual(status['warnings'], warnings)
        self.approve(trusted=False)  # approved hook in an untrusted project still does not run
        self.assertEqual(len(self.warnings()), 1)

    def test_approved_guard_in_a_trusted_project_does_not_warn(self):
        self.approve()
        self.assertEqual(self.warnings(), [])

    def test_claude_only_project_never_warns(self):
        w.write(self.root / '.specify/init-options.json', {'integration': 'claude', 'ai_skills': True})
        self.assertEqual(self.warnings(), [])


class OperationCacheTests(Base):
    """One git and fingerprint pass per command: memoised inside `operation()`, dropped by the runtime's writes."""

    def git_calls(self):
        calls, real = [], subprocess.run

        def run(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == 'git':
                calls.append(list(cmd[1:]))
            return real(cmd, *args, **kwargs)
        return calls, patch.object(subprocess, 'run', run)

    @staticmethod
    def count(calls, *prefix):
        return sum(call[:len(prefix)] == list(prefix) for call in calls)

    def test_source_inventory_is_memoised_until_the_runtime_writes_a_source_path(self):
        self.write('src/app.py', 'print(1)\n')
        calls, counting = self.git_calls()
        with counting:
            with w.operation():
                first = w.source_fingerprints(self.root)
                self.assertEqual(w.source_fingerprints(self.root), first)
                w.write(self.root / self.feature / 'workflow/note.json', {})  # operational: kept
                w.source_fingerprints(self.root)
                self.assertEqual(self.count(calls, 'ls-files', '--cached'), 1)
                w.write(self.root / 'src/settings.json', {'a': 1})  # a source path: dropped
                self.assertIn('src/settings.json', w.source_fingerprints(self.root))
                self.assertEqual(self.count(calls, 'ls-files', '--cached'), 2)
            w.source_fingerprints(self.root)
            w.source_fingerprints(self.root)
        self.assertEqual(self.count(calls, 'ls-files', '--cached'), 4)  # nothing is memoised outside an operation

    def test_attributes_are_asked_once_per_path_and_dropped_by_a_gitattributes_write(self):
        self.write('src/a.py', 'a\n')
        self.write('src/b.py', 'b\n')
        calls, counting = self.git_calls()
        with counting, w.operation():
            w.fingerprint_files(self.root, ['src/a.py'])
            w.fingerprint_files(self.root, ['src/a.py', 'src/b.py'])
            w.fingerprint_files(self.root, ['src/b.py'])
            self.assertEqual(self.count(calls, 'check-attr'), 2)  # a, then only b
            target = self.root / '.gitattributes'
            temp = self.root / 'attributes.tmp'
            temp.write_text('*.py -text\n', encoding='utf-8')
            w.replace_file(temp, target)
            w.fingerprint_files(self.root, ['src/a.py'])
            self.assertEqual(self.count(calls, 'check-attr'), 3)

    def test_identity_is_memoised_and_a_mutating_git_call_drops_it(self):
        calls, counting = self.git_calls()
        with counting, w.operation():
            self.assertEqual(w.normalized_remote(self.root), 'github.com/acme/app')
            self.assertEqual(w.github_repository(self.root), 'acme/app')
            self.assertEqual(self.count(calls, 'config', '--get', 'remote.origin.url'), 1)
            w.git(self.root, 'remote', 'set-url', 'origin', 'https://github.com/acme/other.git')
            self.assertEqual(w.normalized_remote(self.root), 'github.com/acme/other')
        subprocess.run(['git', 'remote', 'set-url', 'origin', 'https://github.com/acme/third.git'], cwd=self.root,
                       check=True)
        self.assertEqual(w.normalized_remote(self.root), 'github.com/acme/third')

    def test_the_one_git_runner_keeps_the_memo_for_reads_and_drops_it_after_a_write(self):
        """W26: unchecked git calls go through `run_git`, which applies the same memo rule as `git`."""
        calls, counting = self.git_calls()
        with counting, w.operation():
            w.normalized_remote(self.root)
            self.assertTrue(w.git_ok(self.root, 'rev-parse', '--git-dir'))
            self.assertFalse(w.git_ok(self.root, 'check-ref-format', '--branch', 'a..b'))
            w.normalized_remote(self.root)
            self.assertEqual(self.count(calls, 'config', '--get', 'remote.origin.url'), 1)
            self.assertEqual(w.run_git(self.root, 'remote', 'set-url', 'origin',
                                       'https://github.com/acme/other.git').returncode, 0)
            self.assertEqual(w.normalized_remote(self.root), 'github.com/acme/other')

    def test_load_with_a_recorded_root_commit_skips_the_history_walk(self):
        run = self.run_object()
        calls, counting = self.git_calls()
        with counting:
            run.load()
        self.assertEqual(self.count(calls, 'rev-list'), 0)
        self.assertEqual(self.count(calls, 'merge-base', '--is-ancestor'), 1)
        state = run.load()
        state['repo_identity']['root_commit'] = 'b' * 40  # unreachable: the full walk decides, and refuses
        run.path.write_text(json.dumps(state), encoding='utf-8')
        with counting, self.assertRaisesRegex(w.WorkflowError, 'CHECKPOINT_IDENTITY_MISMATCH'):
            run.load()
        self.assertEqual(self.count(calls, 'rev-list'), 1)

    def test_claim_after_ready_hashes_the_source_tree_once_and_asks_attributes_once(self):
        self.write('src/app.py', 'print(1)\n')
        run = self.run_object()
        self.advance(run, 'ready')
        calls, counting = self.git_calls()
        with counting:
            claim = run.claim(self.usage(), finalize=True)
        self.assertEqual(claim['stage'], 'pr')
        self.assertEqual(self.count(calls, 'ls-files', '--cached'), 1)
        # the package digest, one prefetch over every receipt's paths, and the source inventory
        self.assertEqual(self.count(calls, 'check-attr'), 3)


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
        self.assertRegex(result['lean_execution'], r'^(on|off) \((tier default|policy|default)\)$')


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

    def test_bind_only_claim_binds_through_scope_with_the_printed_flags(self):
        """B1: the lean Specify claim on a rendered spec prints Scope's bind with the claim flags; that exact
        command binds a root issue kept whole (no native parent, B2)."""
        self.bind_rendered_issue()
        self.assertEqual(w.read(self.root / self.feature / 'scope-source.json', {})['issue'], 10)

    def test_scope_bind_gives_the_pr_lint_its_prerequisites(self):
        """B5: bind records the checked prerequisites in scope-source.json, and the PR stage's lint reads them."""
        run = self.bind_rendered_issue(prerequisite=9)
        self.assertEqual(w.read(self.root / self.feature / 'scope-source.json', {})['dependencies'], [9])
        import execution_tools
        body = 'Closes #10\n\nBuilds on #9.\n'
        (self.root / self.feature / 'pr-body.md').write_bytes(body.encode())  # the exact sent bytes
        w.write(self.root / self.feature / 'pr-lint.json', execution_tools.pr_lint(body, 'acme/app', 10, [9]))
        receipt = {'pr_body_file': self.feature + '/pr-body.md', 'pr_lint_file': self.feature + '/pr-lint.json',
                   'evidence': [self.feature + '/pr-body.md', self.feature + '/pr-lint.json'],
                   'pr_body_sha256': execution_tools.pr_lint(body, 'acme/app', 10, [9])['body_sha256']}
        binding = w.pr_lint_binding(self.root, self.feature, run.load(), receipt)
        self.assertEqual(binding['prerequisites'], [9])
        (self.root / self.feature / 'pr-body.md').write_bytes(b'Closes #10\nFixes #9\n')  # closing a prerequisite is refused
        with self.assertRaisesRegex(w.WorkflowError, 'PREREQUISITE_CLOSE'):
            w.pr_lint_binding(self.root, self.feature, run.load(), receipt)

    def bind_rendered_issue(self, prerequisite=None):
        """Publish #10 with Scope's fake GitHub, complete Scope, render the spec, claim Specify and run the
        claim's printed Scope bind; returns the run."""
        import shlex
        sys.path.insert(0, str(SCRIPT.parents[2] / 'scope/tests'))
        import test_scope as scope_fixture
        sm = scope_fixture.m
        analysis_file = self.feature + '/scope-analysis.json'
        self.policy['lean_execution'] = {'enabled': True, 'scope_analysis': analysis_file}
        self.configure()
        gh = scope_fixture.FakeGitHub()
        gh.add(10)
        if prerequisite:
            gh.add(prerequisite, status='Done')['state'] = 'closed'
            gh.deps[10] = {prerequisite}
        with patch('sanduq_remote.origin_url', return_value='https://github.com/acme/app.git'):
            app = sm.Scope(self.root, gh)
        snapshot = app.inspect('10')
        analysis = {'issue': 10, 'fingerprint': snapshot['fingerprint'], 'requirements': ['AC-1'],
                    'alignment': 'Reuses tested existing behavior', 'evidence': ['src/feature.py:10'], 'images': [],
                    'tree': scope_fixture.node()}
        app.approve(snapshot, analysis, 0, 'test owner', 'I approve this exact proposal.')
        app.publish(snapshot, analysis, True)
        w.write(self.root / analysis_file, analysis)
        run = self.run_object()
        self.advance_fresh(run, 'scope')
        app.render_spec('10', self.root / analysis_file, self.feature, apply=True)
        claim = run.claim(self.usage())
        self.assertEqual((claim['stage'], claim['mode']), ('specify', 'bind-only'))
        argv = shlex.split(claim['scope_command']['command'])[2:]
        self.assertEqual(argv[:2], ['bind', '10'])
        decisions = sm.workflow_policy._decisions_module()  # cached per process: patched, never overwritten
        no_decisions = {'version': 1, 'feature': self.feature, 'issue': 'acme/app#10', 'decisions': []}
        previous = os.getcwd()
        os.chdir(self.root)
        try:
            with patch.object(sm, 'Scope', return_value=app), patch('sys.stdout', new=__import__('io').StringIO()), \
                    patch.object(decisions, 'reconcile', return_value=no_decisions), \
                    patch.object(sm.workflow_policy, '_decisions_module', return_value=decisions):
                code = sm.main(argv)
        finally:
            os.chdir(previous)
        self.assertEqual(code, 0)
        return run

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
