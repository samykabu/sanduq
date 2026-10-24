"""Bounded Scope recovery author checks. Public CLI/package scenarios are collected separately."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow as w
import decisions
import wf_scope_revalidation as recovery
import wf_core
import lifecycle
from test_receipt_contract import Harness, checkpoint_validator

scope_tests = Path(__file__).resolve().parents[2] / 'scope/tests/test_scope.py'
spec = importlib.util.spec_from_file_location('recovery_scope_fixture', scope_tests)
scope_fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope_fixture)
sm = scope_fixture.m


class ScopeRecoveryTests(Harness):
    def setUp(self):
        super().setUp()
        self.policy = w.default_policy(False, False)
        self.configure()
        self.git('config', 'core.autocrlf', 'false')
        self.gh = scope_fixture.FakeGitHub()
        issue = self.gh.add(10, body='Refunds require owner approval.\n')
        issue['user'] = {'login': 'owner'}
        approved = {'version': 2, 'score': 3, 'prompt': 'Implement refund approval.',
                    'dependencies': [], 'fingerprint': sm.fingerprint(issue), 'operation': 'approved-op',
                    'approval': {'approved_by': 'owner', 'approved_at': '2026-10-23T00:00:00+00:00',
                                 'analysis_sha256': 'a' * 64}}
        issue['body'] = sm.replace_block(issue['body'], '<!-- speckit-scope:metadata ' + json.dumps(approved) + ' -->')
        issue['labels'] = [{'name': 'effort:3'}]
        self.source = {'repo': 'acme/app', 'issue': 10, 'parent': None,
                       **{key: approved[key] for key in ('score', 'prompt', 'fingerprint', 'dependencies', 'approval')}}
        self.write(self.feature + '/spec.md', '# Refund approval\n')
        w.write(self.root / self.feature / 'scope-source.json', self.source)
        source_path = self.root / self.feature / 'scope-source.json'
        source_path.write_bytes((json.dumps(self.source, indent=2) + '\n').encode())
        self.decision = self.feature + '/workflow/decisions.json'
        self.write(self.decision, '{\n  "version": 1,\n  "feature": "' + self.feature + '",\n  "issue": "acme/app#10",\n  "decisions": []\n}\n')
        ledger = self.root / self.decision
        ledger.write_bytes(ledger.read_bytes().replace(b'\n', b'\r\n'))
        self.proof_paths = [self.feature + '/evidence/scope/' + name for name in ('gate.json', 'assessment.json')]
        for name in self.proof_paths:
            self.write(name, '{\n  "retained": true\n}\n')
            path = self.root / name
            path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
        self.context = '.github/memory/project-memory.md'
        self.write(self.context, '# Project context\nOriginal context.\n')
        self.write('UIUX-Deviations.md', '# Deviations\nNone.\n')
        self.addCleanup(self.start_patch(patch.object(decisions, 'GitHub', return_value=self.gh)).stop)
        self.addCleanup(self.start_patch(patch.object(recovery, 'provider', side_effect=self.provider)).stop)
        self.run = self.run_object()
        claim = self.run.claim(self.usage())
        receipt = self.receipt('scope')
        receipt.update(inputs=[self.feature + '/scope-source.json', self.context, 'UIUX-Deviations.md'],
                       evidence=self.proof_paths, effort_score=3)
        self.run.complete(claim['token'], receipt)
        claim = self.run.claim(self.usage())
        self.run.complete(claim['token'], self.receipt('specify'))
        # A legacy writer's checkpoint, without changing its accepted receipt map.
        legacy = self.run.load()
        legacy.update(schema_version=1, repo_path=str(self.root))
        w.write(self.run.path, legacy)
        self.before = copy.deepcopy(self.run.load())
        self.commit_all('Accepted legacy Scope proof')
        self.anchor = self.git('rev-parse', 'HEAD')
        self.write('.gitattributes', 'specs/** -text\n')
        self.commit_all('Preserve feature bytes')

    @staticmethod
    def start_patch(patcher):
        patcher.start()
        return patcher

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, capture_output=True, text=True, check=True).stdout.strip()

    def provider(self, run, receipt, original):
        return sm.Scope(run.root, self.gh).revalidate_accepted(run.relative, receipt, original)

    def persistent(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*')
                if p.is_file() and '__pycache__' not in p.parts}

    def assessment(self, plan, filename='recovery.json'):
        findings = [{'path': p['path'], 'classification': p['classification'], 'conclusion': 'scope-unchanged',
                     'rationale': 'Compared exact historical and current proof; refund approval is unchanged.'}
                    for p in plan['paths']]
        evidence = self.feature + '/evidence/scope/' + filename
        w.write(self.root / evidence, {'schema': recovery.ASSESSMENT, 'plan_id': plan['plan_id'],
                                     'scope_unchanged': True, 'findings': findings})
        return {'schema': recovery.ASSESSMENT, 'plan_id': plan['plan_id'], 'actor': 'owner',
                'reason': 'Assess unchanged Scope after byte guard.', 'schema_transition': plan['schema_transition'],
                'stages': {'scope': {'summary': 'Refund approval remains unchanged.', 'evidence': [evidence],
                                     'assessments': findings}}}

    def test_legacy_crlf_plan_is_stable_and_completely_readonly(self):
        before = self.persistent()
        first = self.run.revalidate_upstream('scope', plan=True)
        second = self.run.revalidate_upstream('scope', plan=True)
        self.assertEqual(first, second)
        self.assertEqual(before, self.persistent())
        self.assertEqual({p['path'] for p in first['paths']}, set(self.proof_paths + [self.decision]))
        self.assertEqual({p['classification'] for p in first['paths']}, {'unchanged-bytes-context-transition'})
        self.assertEqual(first['history_anchor'], self.anchor)
        self.assertEqual(self.gh.writes, [])

    def test_apply_preserves_actual_receipt_map_and_all_original_proofs(self):
        plan = recovery.plan(self.run)
        assessment = self.assessment(plan)
        original = {name: (self.root / name).read_bytes() for name in plan['inventory'] if (self.root / name).is_file()}
        with patch.object(w.Run, 'claim', side_effect=AssertionError('no claim during recovery')):
            result = self.run.revalidate_upstream('scope', assessment, apply=True)
        self.assertEqual(result['revalidated'], ['scope'])
        after = self.run.load()
        self.assertEqual(set(after['receipts']), set(self.before['receipts']))
        self.assertEqual(after['receipts']['specify'], self.before['receipts']['specify'])
        self.assertEqual(after['receipts']['scope']['scope_revalidations'][-1]['previous_receipt'], self.before['receipts']['scope'])
        for name, data in original.items():
            if name.endswith('/lifecycle.jsonl'):
                continue
            self.assertEqual((self.root / name).read_bytes(), data, name)
        checkpoint_validator().validate(after)
        self.assertEqual(self.gh.writes, [])

    def test_real_context_edits_require_assessment_and_leave_later_receipts_stale(self):
        for name in (self.context, 'UIUX-Deviations.md'):
            (self.root / name).write_text('Updated context; refund approval remains the same.\n', encoding='utf-8')
        plan = recovery.plan(self.run)
        self.assertEqual({p['path'] for p in plan['paths'] if p['classification'] == 'context-edit'},
                         {self.context, 'UIUX-Deviations.md'})
        old = copy.deepcopy(self.before['receipts']['specify'])
        recovery.apply(self.run, self.assessment(plan))
        self.assertEqual(self.run.load()['receipts']['specify'], old)

    def test_wrong_and_extra_assessments_and_runtime_fields_are_rejected(self):
        plan = recovery.plan(self.run)
        valid = self.assessment(plan)
        variants = []
        extra = copy.deepcopy(valid); extra['hashes'] = {}; variants.append(extra)
        missing = copy.deepcopy(valid); missing['stages']['scope']['assessments'].pop(); variants.append(missing)
        forged = copy.deepcopy(valid); forged['stages']['scope']['assessments'][0]['after_fingerprint'] = 'b' * 64; variants.append(forged)
        path = copy.deepcopy(valid); path['stages']['scope']['assessments'][0]['path'] = 'unapproved'; variants.append(path)
        before = self.persistent()
        for value in variants:
            with self.subTest(value=value), self.assertRaises(w.WorkflowError):
                recovery.apply(self.run, value)
            self.assertEqual(before, self.persistent())

    def test_changed_prompt_approval_requirements_effort_and_children_are_rejected(self):
        original = copy.deepcopy(self.gh.issues[10])
        for change in ('prompt', 'approval', 'requirements', 'effort', 'children'):
            self.gh.issues[10] = copy.deepcopy(original)
            issue = self.gh.issues[10]
            metadata = sm.metadata(issue['body'])
            if change == 'requirements': issue['body'] += '\nNew requirement'
            elif change == 'effort': issue['labels'] = [{'name': 'effort:5'}]
            elif change == 'children': self.gh.children[10] = {11}; self.gh.add(11)
            else:
                if change == 'prompt': metadata['prompt'] += ' Different approved behavior.'
                else: metadata['approval']['approved_by'] = 'another-owner'
                issue['body'] = sm.replace_block(issue['body'], '<!-- speckit-scope:metadata ' + json.dumps(metadata) + ' -->')
            with self.subTest(change=change), self.assertRaises(Exception):
                recovery.plan(self.run)
        self.gh.children[10] = set()

    def test_old_hash_match_without_historical_raw_bytes_is_not_proof(self):
        # The current normalized bytes still match, but the authoritative old blob was CRLF.
        path = self.root / self.decision
        path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
        plan = recovery.plan(self.run)
        self.assertFalse(plan['can_apply'])
        self.assertIn('SCOPE_RECOVERY_SUBSTANTIVE_CHANGE: ' + self.decision, plan['blockers'])

    def test_stale_checkpoint_head_index_attributes_policy_and_evidence_refuse(self):
        plan = recovery.plan(self.run)
        assessment = self.assessment(plan)
        before = self.run.path.read_bytes()
        changed = self.run.load(); changed['generation'] += 1; w.write(self.run.path, changed)
        after_external_write = self.persistent()
        with self.assertRaisesRegex(w.WorkflowError, 'PLAN_STALE'):
            recovery.apply(self.run, assessment)
        self.assertEqual(after_external_write, self.persistent())
        self.run.path.write_bytes(before)
        self.git('config', 'recovery.test', 'changed')
        with self.assertRaisesRegex(w.WorkflowError, 'PLAN_STALE'):
            recovery.apply(self.run, assessment)

    def test_atomic_replace_failure_keeps_previous_checkpoint(self):
        plan = recovery.plan(self.run); assessment = self.assessment(plan)
        before = self.run.path.read_bytes()
        with patch.object(wf_core, 'replace_file', side_effect=OSError('replace failed')):
            with self.assertRaisesRegex(OSError, 'replace failed'):
                recovery.apply(self.run, assessment)
        self.assertEqual(self.run.path.read_bytes(), before)
        self.assertEqual(list(self.run.path.parent.glob('*.tmp')), [])

    def test_recovered_plan_and_noop_apply_make_no_writes(self):
        found = recovery.plan(self.run)
        recovery.apply(self.run, self.assessment(found))
        noop = recovery.plan(self.run)
        self.assertTrue(noop['noop'])
        assessment = self.assessment(noop, 'noop.json')
        before = self.persistent()
        self.assertEqual(recovery.apply(self.run, assessment)['revalidated'], [])
        self.assertEqual(self.persistent(), before)

    def test_missing_or_corrupt_inventory_sidecar_is_a_direct_blocker(self):
        state = self.run.load()
        state['receipts']['specify']['source_inventory'] = {'path': 'workflow/inventory/old.json', 'sha256': 'a' * 64}
        w.write(self.run.path, state)
        with self.assertRaisesRegex(w.WorkflowError, 'SOURCE_INVENTORY_INVALID'):
            recovery.plan(self.run)

    def test_missing_historical_checkpoint_never_falls_back_to_normalized_hash(self):
        state = self.run.load()
        state['receipts']['scope']['claim_id'] = 'no-such-acceptance'
        w.write(self.run.path, state)
        with self.assertRaisesRegex(w.WorkflowError, 'HISTORY_MISSING'):
            recovery.plan(self.run)

    def test_exact_retained_storage_hash_has_a_distinct_verified_interpretation(self):
        # A legacy storage-domain fixture: the raw Git bytes, not parsed JSON, explain its acceptance.
        (self.root / '.gitattributes').write_bytes(b'')
        state = self.run.load()
        state['receipts']['scope']['fingerprints'][self.decision] = recovery.sha((self.root / self.decision).read_bytes())
        w.write(self.run.path, state)
        self.commit_all('Retained exact-storage legacy receipt')
        plan = recovery.plan(self.run)
        item = next(p for p in plan['paths'] if p['path'] == self.decision)
        self.assertEqual(item['before_interpretation'], 'exact-retained-storage')
        self.assertEqual(item['before_raw_sha256'], item['after_raw_sha256'])
        self.assertEqual(item['classification'], 'unchanged-bytes-context-transition')

    def test_lifecycle_failure_reports_committed_and_retains_durable_outbox(self):
        plan = recovery.plan(self.run); assessment = self.assessment(plan)
        with patch.object(lifecycle, 'flush', side_effect=OSError('append failed')):
            result = recovery.apply(self.run, assessment)
        self.assertTrue(result['committed']); self.assertTrue(result['lifecycle_pending'])
        self.assertTrue(self.run.load().get(lifecycle.OUTBOX))

    def test_final_provider_race_refuses_without_checkpoint_mutation(self):
        plan = recovery.plan(self.run); assessment = self.assessment(plan)
        before = self.run.path.read_bytes()
        real = recovery.provider
        calls = 0
        def changed(*args):
            nonlocal calls
            calls += 1
            result = real(*args)
            if calls == 3:
                result['status'] = 'In progress'
            return result
        with patch.object(recovery, 'provider', side_effect=changed):
            with self.assertRaisesRegex(w.WorkflowError, 'PLAN_STALE'):
                recovery.apply(self.run, assessment)
        self.assertEqual(self.run.path.read_bytes(), before)

    def test_active_delegated_maintenance_legacy_and_ledger_writers_refuse(self):
        import delegation
        for name in ('upgrade.lock', 'install.lock'):
            path = self.root / '.specify/workflow/runtime' / name
            path.write_text('{}')
            with self.assertRaises(delegation.DelegationError): recovery.plan(self.run)
            path.unlink()
        w.write(self.root / '.specify/superpowers-handoff.json', {'status': 'executing'})
        with self.assertRaisesRegex(w.WorkflowError, 'LEGACY_EXECUTOR'): recovery.plan(self.run)
        (self.root / '.specify/superpowers-handoff.json').unlink()
        with patch.dict(os.environ, {'SANDUQ_DELEGATED_RUN': 'worker'}):
            with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_WORKER_CONTEXT'): recovery.plan(self.run)
        saved = self.run.path.read_bytes()
        state = self.run.load(); state['active'] = {'stage': 'scope', 'token': 'someone-else'}
        w.write(self.run.path, state)
        with self.assertRaisesRegex(w.WorkflowError, 'ACTIVE_CLAIM'): recovery.plan(self.run)
        self.run.path.write_bytes(saved)
        w.write(self.run.feature / 'workflow/delegations.json', {'attempts': [{'status': 'running', 'run_id': 'live'}]})
        with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_ATTEMPTS_ACTIVE'): recovery.plan(self.run)

    def test_attributes_policy_and_head_changes_make_the_reviewed_plan_obsolete(self):
        plan = recovery.plan(self.run); assessment = self.assessment(plan)
        for label in ('.gitattributes', '.specify/workflow.yml'):
            path = self.root / label; original = path.read_bytes()
            path.write_bytes(original + b'\n# changed after preview\n')
            before = self.run.path.read_bytes()
            with self.subTest(label=label), self.assertRaisesRegex(w.WorkflowError, 'PLAN_STALE'):
                recovery.apply(self.run, assessment)
            self.assertEqual(self.run.path.read_bytes(), before)
            path.write_bytes(original)
        self.git('commit', '--allow-empty', '-qm', 'Changed HEAD after preview')
        before = self.run.path.read_bytes()
        with self.assertRaisesRegex(w.WorkflowError, 'PLAN_STALE'):
            recovery.apply(self.run, assessment)
        self.assertEqual(self.run.path.read_bytes(), before)

    def test_extra_live_questions_and_unbound_assessment_evidence_are_rejected(self):
        plan = recovery.plan(self.run); assessment = self.assessment(plan)
        proof = self.root / assessment['stages']['scope']['evidence'][0]
        data = json.loads(proof.read_text(encoding='utf-8'))
        data['plan_id'] = '0' * 64
        proof.write_text(json.dumps(data), encoding='utf-8')
        before = self.run.path.read_bytes()
        with self.assertRaisesRegex(w.WorkflowError, 'EVIDENCE_UNBOUND'):
            recovery.apply(self.run, assessment)
        self.assertEqual(self.run.path.read_bytes(), before)
        body = decisions.render_body('SD1', 'Change refund policy?', ['Keep', 'Change'])
        marker = {'version': 1, 'id': 'SD1', 'options': ['Keep', 'Change'], 'body_digest': decisions.digest(body),
                  'request_digest': 'owner-question', 'choice_format': 1, 'mode': 'single', 'recommended': None}
        comment = {'id': 81, 'user': {'login': 'owner', 'type': 'User'},
                   'body': '<!-- sanduq-decision:question ' + json.dumps(marker) + ' -->\n' + body}
        old_api = self.gh.api
        self.gh.api = lambda endpoint, **kw: [comment] if '/comments?' in endpoint else old_api(endpoint, **kw)
        with self.assertRaisesRegex(w.WorkflowError, 'DECISION_UNRESOLVED'):
            recovery.plan(self.run)

    def test_evidence_symlink_is_refused_even_when_it_stays_inside_the_repository(self):
        path = self.root / self.proof_paths[0]
        target = self.root / 'same-proof.json'; target.write_bytes(path.read_bytes()); path.unlink()
        try:
            path.symlink_to(target)
        except OSError as exc:
            self.skipTest('Symlink creation unavailable: ' + str(exc))
        with self.assertRaisesRegex(w.WorkflowError, 'UNSAFE_PATH'):
            recovery.plan(self.run)


class ProviderFailureTests(unittest.TestCase):
    def test_scope_recovery_recipe_does_not_advise_a_destructive_claim(self):
        recipe = w.recovery_recipe('specs/412-refund-approval', 'scope',
                                  {'reason': 'explicit-drift', 'paths': ['specs/412-refund-approval/workflow/decisions.json']},
                                  {}, {'evidence': [], 'fingerprints': {}}, Path.cwd())
        self.assertIn('--through scope --plan', recipe[0])
        self.assertFalse(any(' claim ' in step for step in recipe))

    def test_provider_failure_is_a_structured_workflow_error(self):
        from types import SimpleNamespace
        class ProviderError(Exception):
            pass
        class Scope:
            def __init__(self, root): pass
            def revalidate_accepted(self, *args): raise ProviderError('SCOPE_STALE: changed requirements')
        module = SimpleNamespace(Scope=Scope, ScopeError=ProviderError)
        spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda value: None))
        with patch.object(recovery.importlib.util, 'spec_from_file_location', return_value=spec), \
                patch.object(recovery.importlib.util, 'module_from_spec', return_value=module):
            with self.assertRaisesRegex(w.WorkflowError, 'SCOPE_STALE'):
                recovery.provider(SimpleNamespace(root=Path.cwd(), relative='specs/001'), {}, {})


if __name__ == '__main__':
    unittest.main()
