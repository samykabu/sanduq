"""Exact-input verification and adversarial evidence reuse regressions."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verification_plan as vp
import workflow as w


class VerificationPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for label in ('src/a.py', 'src/b.py', 'fixtures/a.json'):
            path = self.root / label
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('original\n', encoding='utf-8')
        self.plan_path = 'verification.json'
        self.plan = {'schema_version': 1, 'checks': [
            {'id': 'a', 'sources': ['src/a.py'], 'fixtures': ['fixtures/a.json'],
             'command': [sys.executable, '-c', 'print("a passed")'],
             'environment': ['SANDUQ_TEST_LEAN_ENV'], 'evidence': 'evidence/a.json'},
            {'id': 'b', 'sources': ['src/b.py'], 'fixtures': [],
             'command': [sys.executable, '-c', 'print("b passed")'],
             'environment': [], 'evidence': 'evidence/b.json'}]}
        self.save_plan()

    def save_plan(self):
        (self.root / self.plan_path).write_text(json.dumps(self.plan), encoding='utf-8')

    def passing_snapshot(self):
        self.assertEqual(vp.run_checks(self.root, self.plan_path, timeout=10), {'a': 'passed', 'b': 'passed'})
        return vp.snapshot(self.root, self.plan_path)

    def test_symlink_invocation_and_resolved_target_are_bound_separately(self):
        link = self.root / 'bin' / 'py-link'
        link.parent.mkdir()
        try:
            link.symlink_to(sys.executable)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable on this platform; invocation proven by the runner-capture test')
        self.plan['checks'][0]['command'] = ['bin/py-link', '-c', 'print("a")']
        executable = vp.identity(self.root, self.plan['checks'][0])['environment']['executable']
        self.assertEqual(Path(executable['invocation']), link)
        self.assertEqual(Path(executable['path']), Path(sys.executable).resolve())
        self.assertNotEqual(executable['invocation'], executable['path'])

    def test_runner_executes_selected_invocation_path(self):
        import delegate_dispatch as dispatch
        tool = self.root / 'bin' / 'tool'
        tool.parent.mkdir()
        tool.write_text('x', encoding='utf-8')
        self.plan['checks'][0]['command'] = ['bin/tool', '--flag']
        self.save_plan()
        seen = []

        def capture(argv, cwd, timeout):
            seen.append(argv)
            return {'exit_code': 0, 'timed_out': False, 'output': '', 'truncated': False}
        with patch.object(dispatch, 'run_capped', side_effect=capture):
            vp.run_checks(self.root, self.plan_path, ['a'], timeout=10)
        self.assertEqual(seen, [[os.path.abspath(tool), '--flag']])

    def test_changed_invocation_or_target_changes_identity(self):
        tool = self.root / 'bin' / 'tool.py'
        tool.parent.mkdir()
        tool.write_text('x', encoding='utf-8')
        check = self.plan['checks'][0]
        check['command'] = ['bin/tool.py']
        base = vp.identity(self.root, check)['environment']['executable']
        tool.write_text('y', encoding='utf-8')
        changed = vp.identity(self.root, check)['environment']['executable']
        self.assertEqual(changed['invocation'], base['invocation'])
        self.assertNotEqual(changed['sha256'], base['sha256'])
        (self.root / 'bin' / 'other.py').write_text('y', encoding='utf-8')
        check['command'] = ['bin/other.py']
        self.assertNotEqual(vp.identity(self.root, check)['environment']['executable']['invocation'],
                            changed['invocation'])

    def test_exact_unchanged_passing_evidence_reuses_checks(self):
        saved = self.passing_snapshot()
        self.assertEqual(vp.affected_checks(self.root, self.plan_path, saved)['reusable'], ['a', 'b'])
        self.assertTrue(vp.current(self.root, self.plan_path, saved)['current'])
        self.assertEqual(vp.affected_checks(self.root, self.plan_path)['affected'], ['a', 'b'])

    def test_source_fixture_command_and_environment_select_only_affected_check(self):
        saved = self.passing_snapshot()
        for label in ('src/a.py', 'fixtures/a.json'):
            with self.subTest(label=label):
                path = self.root / label
                before = path.read_bytes()
                path.write_text('changed', encoding='utf-8')
                selected = vp.affected_checks(self.root, self.plan_path, saved)
                self.assertEqual(selected['affected'], ['a'])
                self.assertEqual(selected['reusable'], ['b'])
                with self.assertRaisesRegex(vp.VerificationPlanError, 'PASSING_EVIDENCE_REQUIRED'):
                    vp.snapshot(self.root, self.plan_path)
                path.write_bytes(before)
        with patch.dict(os.environ, {'SANDUQ_TEST_LEAN_ENV': 'changed'}):
            self.assertEqual(vp.affected_checks(self.root, self.plan_path, saved)['affected'], ['a'])
        with patch.dict(os.environ, {'PATH': os.environ.get('PATH', '') + os.pathsep + 'changed'}):
            self.assertEqual(vp.affected_checks(self.root, self.plan_path, saved)['affected'], ['a', 'b'])
        self.plan['checks'][0]['command'].append('new-argument')
        self.save_plan()
        self.assertEqual(vp.affected_checks(self.root, self.plan_path, saved)['affected'], ['a'])

    def test_tampered_receipt_or_passing_output_cannot_be_reused(self):
        saved = self.passing_snapshot()
        tampered = copy.deepcopy(saved)
        tampered['checks']['a']['identity']['command'] = ['different']
        self.assertEqual(vp.affected_checks(self.root, self.plan_path, tampered)['affected'], ['a'])
        path = self.root / 'evidence/a.json'
        evidence = json.loads(path.read_text(encoding='utf-8'))
        evidence['output'] = 'invented passing output'
        path.write_text(json.dumps(evidence), encoding='utf-8')
        self.assertEqual(vp.affected_checks(self.root, self.plan_path, saved)['affected'], ['a'])
        self.assertFalse(vp.current(self.root, self.plan_path, saved)['current'])

    def test_failed_timeout_and_changed_during_execution_do_not_pass(self):
        self.plan['checks'][0]['command'] = [sys.executable, '-c', 'raise SystemExit(3)']
        self.save_plan()
        self.assertEqual(vp.run_checks(self.root, self.plan_path, ['a'], timeout=10), {'a': 'failed'})
        with self.assertRaises(vp.VerificationPlanError):
            vp.snapshot(self.root, self.plan_path)
        with patch('delegate_dispatch.run_capped', return_value={
                'exit_code': 0, 'timed_out': True, 'truncated': False, 'output': 'partial'}):
            self.assertEqual(vp.run_checks(self.root, self.plan_path, ['a'], timeout=10), {'a': 'failed'})
        def mutation(*args):
            (self.root / 'src/a.py').write_text('changed while running', encoding='utf-8')
            return {'exit_code': 0, 'timed_out': False, 'truncated': False, 'output': 'OK'}
        with patch('delegate_dispatch.run_capped', side_effect=mutation):
            self.assertEqual(vp.run_checks(self.root, self.plan_path, ['a'], timeout=10), {'a': 'failed'})

    def test_missing_deleted_and_added_checks_fail_closed(self):
        saved = self.passing_snapshot()
        (self.root / 'src/a.py').unlink()
        self.assertEqual(vp.affected_checks(self.root, self.plan_path, saved)['affected'], ['a'])
        self.plan['checks'] = [self.plan['checks'][1]]
        self.save_plan()
        selected = vp.affected_checks(self.root, self.plan_path, saved)
        self.assertEqual(selected['removed'], ['a'])
        self.assertFalse(vp.current(self.root, self.plan_path, saved)['current'])

    def test_manifest_rejects_escape_collisions_empty_and_unknown_fields(self):
        for change in (lambda c: c.update(sources=['../escape']),
                       lambda c: c.update(command=[]), lambda c: c.update(sources=[]),
                       lambda c: c.update(evidence='src/a.py'), lambda c: c.update(unknown=True),
                       lambda c: c.update(environment=['HOME', 'HOME'])):
            original = copy.deepcopy(self.plan)
            change(self.plan['checks'][0])
            self.save_plan()
            with self.assertRaises(vp.VerificationPlanError):
                vp.read_plan(self.root, self.plan_path)
            self.plan = original

    def test_workflow_selected_plan_rejects_stale_reuse_without_copying_hashes(self):
        saved = self.passing_snapshot()
        policy = w.default_policy(False, False)
        policy['lean_execution'] = {'enabled': True, 'verification_plan': self.plan_path}
        receipt = {'fingerprints': {'input.md': 'hash'}, 'source_fingerprints': {'src/a.py': 'old'},
                   'verification_snapshot': saved}
        with patch.object(w, 'required_inputs', return_value=[]), \
             patch.object(w, 'fingerprint_files', return_value={'input.md': 'hash'}):
            self.assertTrue(w.receipt_status(self.root, 'specs/example', 'verify', receipt, policy)['current'])
            (self.root / 'src/a.py').write_text('changed', encoding='utf-8')
            self.assertFalse(w.receipt_status(self.root, 'specs/example', 'verify', receipt, policy)['current'])
        self.assertEqual(receipt['source_fingerprints'], {'src/a.py': 'old'})

    def test_legacy_receipts_keep_whole_source_identity_gate(self):
        policy = w.default_policy(False, False)
        receipt = {'fingerprints': {'input.md': 'hash'}, 'source_fingerprints': {'src/a.py': 'old'}}
        with patch.object(w, 'required_inputs', return_value=[]), \
             patch.object(w, 'fingerprint_files', return_value={'input.md': 'hash'}), \
             patch.object(w, 'source_fingerprints', return_value={'src/a.py': 'new'}):
            status = w.receipt_status(self.root, 'specs/example', 'verify', receipt, policy)
        self.assertFalse(status['current'])
        self.assertEqual(status['rule'], 'identity')


if __name__ == '__main__':
    unittest.main()
