"""Legacy PR prerequisite compatibility: accepted native proof plus fresh provider, no consumer writes."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow as w
import wf_scope_revalidation as recovery
from wf_receipts import scope_proof_authority
from test_receipt_contract import Harness

spec = importlib.util.spec_from_file_location('pr_scope_fixture', Path(__file__).resolve().parents[2] / 'scope/tests/test_scope.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
sm = fixture.m


class LegacyPrerequisiteTests(Harness):
    def setUp(self):
        super().setUp()
        self.gh = fixture.FakeGitHub()
        self.gh.add(1093, body='Approve booking refunds.')
        for n in (1089, 1092):
            self.gh.add(n, status='Done')['state'] = 'closed'
        self.gh.deps[1093] = {1089, 1092}
        self.app = sm.Scope(self.root, self.gh)
        snapshot = self.app.inspect('1093')
        analysis = {'issue': 1093, 'fingerprint': snapshot['fingerprint'], 'requirements': ['AC-1'],
                    'alignment': 'Existing refund behavior', 'evidence': ['src/refund.py:1'], 'images': [], 'tree': fixture.node()}
        self.app.approve(snapshot, analysis, 0, 'owner', 'I approve this refund scope.')
        self.app.publish(snapshot, analysis, True)
        self.proof = self.app.gate('1093')
        self.proof_label = self.write(self.feature + '/evidence/scope/native-gate.json', json.dumps(self.proof))
        # This is the historical deficient binding shape, before any PR operation.
        self.source = dict(self.proof, repo='acme/app', approval=sm.metadata(self.gh.issues[1093]['body'])['approval'])
        self.source.pop('dependencies')
        self.source_label = self.feature + '/scope-source.json'
        self.write(self.source_label, json.dumps(self.source))
        self.state = {'feature': self.feature, 'issue': 'acme/app#1093', 'receipts': {
            'scope': {'stage': 'scope', 'outcome': 'passed', 'evidence': [self.proof_label],
                      'fingerprints': w.fingerprint_files(self.root, [self.proof_label])},
            'specify': {'stage': 'specify', 'outcome': 'passed', 'fingerprints': w.fingerprint_files(self.root, [self.source_label])}}}
        self.body_label = self.write(self.feature + '/pr-body.md', 'Closes #1093\n\nBuilds on #1089 and #1092.\n')
        lint = w.execution_tools.pr_lint((self.root / self.body_label).read_bytes().decode('utf-8'), 'acme/app', 1093, [1089, 1092])
        self.lint_label = self.write(self.feature + '/pr-lint.json', json.dumps(lint))
        self.receipt = {'pr_body_file': self.body_label, 'pr_lint_file': self.lint_label,
                        'pr_body_sha256': lint['body_sha256'], 'evidence': [self.body_label, self.lint_label]}
        patcher = patch.object(recovery, 'provider', side_effect=lambda run, receipt, original: self.app.validate_binding(original))
        patcher.start(); self.addCleanup(patcher.stop)

    def persistent(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_approved_legacy_proof_recovers_prerequisites_without_writes(self):
        before = self.persistent(); writes = list(self.gh.writes)
        binding = w.pr_lint_binding(self.root, self.feature, self.state, self.receipt)
        self.assertEqual(binding['prerequisites'], [1089, 1092])
        self.assertEqual(binding['prerequisite_evidence'], [self.proof_label])
        self.assertEqual(before, self.persistent()); self.assertEqual(writes, self.gh.writes)

    def test_missing_changed_and_untrusted_proof_fail_closed_with_path(self):
        path = self.root / self.proof_label; data = path.read_bytes()
        for mode in ('missing', 'changed', 'untrusted', 'missing-approval'):
            state = copy.deepcopy(self.state)
            if mode == 'missing': path.unlink()
            elif mode == 'changed': path.write_bytes(data + b' changed')
            elif mode == 'untrusted': state['receipts']['scope']['fingerprints'] = {}
            else:
                source = dict(self.source); source.pop('approval')
                self.write(self.source_label, json.dumps(source))
                state['receipts']['specify']['fingerprints'] = w.fingerprint_files(self.root, [self.source_label])
            before = self.persistent()
            with self.subTest(mode=mode), self.assertRaisesRegex(w.WorkflowError, self.proof_label):
                w.pr_lint_binding(self.root, self.feature, state, self.receipt)
            self.assertEqual(before, self.persistent())
            path.write_bytes(data); self.write(self.source_label, json.dumps(self.source))

    def test_changed_provider_and_closing_prerequisites_or_foreign_issue_are_rejected(self):
        self.gh.add(1094, status='Done')['state'] = 'closed'
        self.gh.deps[1093].add(1094)
        with self.assertRaises(Exception):
            w.pr_lint_binding(self.root, self.feature, self.state, self.receipt)
        self.gh.deps[1093].remove(1094)
        for body in ('Closes #1089', 'Closes #1092', 'Closes foreign/repo#1093'):
            self.write(self.body_label, body)
            with self.subTest(body=body), self.assertRaisesRegex(w.WorkflowError, 'CLOSING_REFERENCE_REJECTED'):
                w.pr_lint_binding(self.root, self.feature, self.state, self.receipt)

    def test_explicit_dependencies_remain_strict_and_never_fall_back(self):
        for value in (None, '1089', [True], [0]):
            self.write(self.source_label, json.dumps(dict(self.source, dependencies=value)))
            with self.subTest(value=value), self.assertRaisesRegex(w.WorkflowError, 'PR_LINT_SCOPE_PREREQUISITES_REQUIRED'):
                w.pr_lint_binding(self.root, self.feature, self.state, self.receipt)

    def test_foreign_binding_and_unbound_source_are_rejected_before_provider_reads(self):
        with patch.object(recovery, 'provider', side_effect=AssertionError('must not read provider')):
            self.write(self.source_label, json.dumps(dict(self.source, repo='foreign/repo')))
            with self.assertRaisesRegex(w.WorkflowError, 'PR_LINT_SCOPE_BINDING_MISMATCH'):
                w.pr_lint_binding(self.root, self.feature, self.state, self.receipt)
            self.write(self.source_label, json.dumps(dict(self.source, prompt='Unapproved refund scope')))
            with self.assertRaisesRegex(w.WorkflowError, 'PR_LINT_SCOPE_BINDING_UNTRUSTED'):
                w.pr_lint_binding(self.root, self.feature, self.state, self.receipt)

    def test_proof_changed_during_provider_validation_is_rejected(self):
        def race(run, receipt, original):
            result = self.app.validate_binding(original)
            path = self.root / self.proof_label
            path.write_bytes(path.read_bytes() + b'\n')
            return result
        with patch.object(recovery, 'provider', side_effect=race):
            with self.assertRaisesRegex(w.WorkflowError, 'PR_LINT_SCOPE_PROOF_CHANGED'):
                w.pr_lint_binding(self.root, self.feature, self.state, self.receipt)


class FrozenAuthorityTests(unittest.TestCase):
    def test_missing_parent_membership_is_enriched_even_with_existing_approval(self):
        approval = {'approved_by': 'owner', 'approved_at': '2026-10-24', 'analysis_sha256': 'a' * 64}
        original = {'repo': 'acme/app', 'issue': 1, 'score': 3, 'prompt': 'Refund scope',
                    'fingerprint': 'b' * 64, 'dependencies': [], 'approval': approval, 'parent': 18}
        proof = dict(original, parent_children=[1, 2])
        result = scope_proof_authority(proof, original)
        self.assertEqual(result['parent_children'], [1, 2]); self.assertEqual(result['approval'], approval)
        with self.assertRaisesRegex(w.WorkflowError, 'AUTHORITY_CHANGED'):
            scope_proof_authority(dict(proof, approval=dict(approval, approved_by='stranger')), original)

    def test_historical_recovery_enriches_parent_membership_without_replacing_approval(self):
        approval = {'approved_by': 'owner', 'approved_at': '2026-10-24', 'analysis_sha256': 'a' * 64}
        original = {'repo': 'acme/app', 'issue': 1, 'score': 3, 'prompt': 'Refund scope',
                    'fingerprint': 'b' * 64, 'dependencies': [], 'approval': approval, 'parent': 18}
        label = 'specs/412-refund-approval/evidence/scope/gate.json'
        data = json.dumps(dict(original, parent_children=[1, 2])).encode()
        receipt = {'evidence': [label], 'fingerprints': {label: recovery.sha(data)}}
        with patch.object(recovery, 'proof_blob', return_value=(data, 'immutable-anchor')), \
                patch.object(recovery, 'historical_attributes', return_value={label: 'unspecified'}):
            restored = recovery.historical_scope_authority(Path.cwd(), 'immutable-anchor', receipt, original)
            self.assertEqual(restored['parent_children'], [1, 2])
            self.assertEqual(restored['approval'], approval)
            with self.assertRaisesRegex(w.WorkflowError, 'HISTORY_UNPROVEN'):
                recovery.historical_scope_authority(Path.cwd(), 'immutable-anchor',
                    {'evidence': [label], 'fingerprints': {label: '0' * 64}}, original)

    def parent_fixture(self, **nodes_change):
        approval = {'approved_by': 'owner', 'approved_at': '2026-10-24', 'analysis_sha256': 'a' * 64, 'child_count': 2}
        original = {'repo': 'acme/app', 'issue': 1, 'score': 3, 'prompt': 'Refund scope',
                    'fingerprint': 'b' * 64, 'dependencies': [], 'approval': approval, 'parent': 18}
        gate_label, parent_label = 'f/evidence/gate.json', 'f/scope/approved-parent-context/publication-result.json'
        gate = json.dumps({'issue': 1, 'score': 3, 'prompt': 'Refund scope', 'fingerprint': 'b' * 64}).encode()
        parent = json.dumps({'issue': 18, 'nodes': {'root': 18, 'a': 1, 'b': 2, **nodes_change}}).encode()
        receipt = {'evidence': [gate_label], 'fingerprints': {gate_label: recovery.sha(gate)}}
        files = {gate_label: gate, parent_label: parent}
        return original, receipt, {parent_label: {recovery.sha(parent)}}, files

    def recover(self, original, receipt, bound, files):
        with patch.object(recovery, 'proof_blob', side_effect=lambda r, a, name, h, attr: (files[name], a)),                 patch.object(recovery, 'historical_attributes', return_value={n: None for n in files}):
            return recovery.historical_scope_authority(Path.cwd(), 'anchor', receipt, original, 'f', bound)

    def test_parent_children_come_from_the_accepted_native_parent_proof(self):
        original, receipt, bound, files = self.parent_fixture()
        restored = self.recover(original, receipt, bound, files)
        self.assertEqual((restored['parent_children'], restored['approval']), ([1, 2], original['approval']))

    def test_unbound_changed_or_mismatched_parent_proof_is_rejected(self):
        original, receipt, bound, files = self.parent_fixture()
        for case, args in {
                'unbound': (original, receipt, {}, files),
                'two hashes': (original, receipt, {k: v | {'0' * 64} for k, v in bound.items()}, files),
                'wrong parent': (dict(original, parent=19), receipt, bound, files),
                'no membership': (dict(original, issue=7), receipt, bound, files),
                'child count': (dict(original, approval=dict(original['approval'], child_count=3)), receipt, bound, files)}.items():
            with self.subTest(case), self.assertRaisesRegex(w.WorkflowError, 'APPROVAL_HISTORY_REQUIRED|PROOF_INVALID'):
                self.recover(*args)
        original, receipt, bound, files = self.parent_fixture(extra=20)
        with self.assertRaisesRegex(w.WorkflowError, 'APPROVAL_HISTORY_REQUIRED'):
            self.recover(original, receipt, bound, files)
        original.pop('approval')
        with self.assertRaisesRegex(w.WorkflowError, 'APPROVAL_HISTORY_REQUIRED'):
            self.recover(original, receipt, bound, files)


if __name__ == '__main__': unittest.main()
