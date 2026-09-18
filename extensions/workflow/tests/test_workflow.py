import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

SPEC = importlib.util.spec_from_file_location('sanduq_workflow', Path(__file__).resolve().parents[1] / 'scripts/workflow.py')
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for args in [('init', '-q'), ('config', 'user.name', 'Test'), ('config', 'user.email', 'test@example.invalid'), ('commit', '--allow-empty', '-qm', 'init')]:
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        self.feature = 'specs/001-example'
        self.policy = w.default_policy(True, True)
        self.configure()

    def configure(self, superspec=False):
        path = self.root / '.specify/workflow.yml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(self.policy), encoding='utf-8')
        (self.root / '.specify/extensions.yml').write_text('hooks: {}\n', encoding='utf-8')
        for preset in ('workflow', 'scope-gate', 'scope-brainstorm'):
            p = self.root / '.specify/presets' / preset / 'preset.yml'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('schema_version: "1.0"\n', encoding='utf-8')
        w.write(self.root / '.specify/presets/.registry', {'presets': {p: {'enabled':True} for p in ('workflow','scope-gate','scope-brainstorm')}})
        versions = {'scope': '1.4.0', 'project': '2.1.0', 'pr': '4.1.0', 'assure': '2.1.0', 'user-manual': '1.1.0'}
        if superspec: versions['superspec'] = '1.0.2'
        w.write(self.root / '.specify/extensions/.registry', {'extensions': {n: {'version': v, 'enabled': True} for n, v in versions.items()}})
        for n, v in versions.items():
            p = self.root / '.specify/extensions' / n / 'extension.yml'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(yaml.safe_dump({'extension':{'id':n,'version':v,'repository':'https://github.com/samykabu/sanduq'}}), encoding='utf-8')
        commands = list(w.COMMANDS.values())
        if superspec: commands += ['speckit.superspec.' + suffix for suffix in ('brainstorm', 'tasks', 'execute', 'review')]
        for command in commands:
            if command.startswith('workflow:'): continue
            p = self.root / '.agents/skills' / command.replace('.', '-') / 'SKILL.md'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('fixture command', encoding='utf-8')

    def usage(self, fraction=.1, method='estimated'):
        return {'session_id': 'new-session', 'observed_at': w.now(), 'method': method,
                'fraction': fraction, 'next_fraction': .05}

    def run_object(self):
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        return run

    def receipt(self, stage, inputs=None):
        path = self.feature + '/evidence/' + stage + '.txt'
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('actual fixture evidence', encoding='utf-8')
        return {'stage': stage, 'summary': stage + ' tested', 'outcome': 'passed', 'inputs': inputs or [path],
                'evidence': [path], 'unresolved': 0, 'answers_applied': True, 'blocking_findings': 0,
                'parent_issue': 'acme/app#10', 'native_links_verified': True,
                'images_verified': True, 'pr_url': 'https://github.com/acme/app/pull/11'}

    def test_four_process_combinations_and_provider_choices(self):
        for qa in (False, True):
            for manual in (False, True):
                for superspec in (False, True):
                    with self.subTest(qa=qa, manual=manual, superspec=superspec):
                        self.policy = w.default_policy(qa, manual)
                        self.configure(superspec)
                        ordered = w.stages(self.policy)
                        self.assertEqual('qa_analyze' in ordered, qa)
                        self.assertEqual('manual_update' in ordered, manual)
                        self.assertLess(ordered.index('analyze'), ordered.index('taskstoissues'))
                        self.assertLess(ordered.index('taskstoissues'), ordered.index('execute'))
                        commands = w.resolve_commands(self.root, self.policy)
                        self.assertEqual(commands['tasks'], 'speckit.superspec.tasks' if superspec else 'speckit.tasks')
                        self.assertEqual(commands['execute'], 'speckit.superspec.execute' if superspec else 'speckit.implement')

    def test_installed_but_unselected_dependencies_do_not_enable_process(self):
        self.policy = w.default_policy(False, False)
        self.configure()
        self.assertNotIn('manual_analyze', w.stages(self.policy))
        self.assertTrue(w.doctor(self.root, self.policy)['ok'])

    def test_scope_inclusive_boundaries_and_units(self):
        self.policy['scope'] = {'keep_together': {'target': 20, 'tolerance': 3, 'unit': 'points', 'inclusive': True}}
        for value in (17, 20, 23): self.assertTrue(w.scope_decision(self.policy, value, 'points')['automatic'])
        for value in (16, 24): self.assertFalse(w.scope_decision(self.policy, value, 'points')['automatic'])
        with self.assertRaisesRegex(w.WorkflowError, 'UNIT_MISMATCH'): w.scope_decision(self.policy, 20, 'hours')

    def test_context_reserves_space_and_labels_estimation(self):
        gate = w.context_gate(self.policy, self.usage(.46))
        self.assertTrue(gate['pause'])  # .46 + .05 + .10 crosses the .60 ceiling
        self.assertFalse(gate['guaranteed'])
        self.assertEqual(gate['method'], 'estimated')
        self.policy['context']['mode'] = 'strict'
        with self.assertRaisesRegex(w.WorkflowError, 'UNENFORCEABLE'): w.context_gate(self.policy, self.usage())
        usage = self.usage(method='measured'); usage['pre_call_bound'] = True
        self.assertTrue(w.context_gate(self.policy, usage)['guaranteed'])

    def test_stale_context_rejected(self):
        usage = self.usage(); usage['observed_at'] = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
        with self.assertRaisesRegex(w.WorkflowError, 'STALE'): w.context_gate(self.policy, usage)

    def test_claim_resume_and_explicit_finalize(self):
        run = self.run_object()
        for stage in w.stages(self.policy):
            if stage == 'pr':
                self.assertEqual(run.next(run.load())['status'], 'ready_to_finalize')
            claim = run.claim(self.usage(), finalize=stage == 'pr')
            self.assertEqual(claim['stage'], stage)
            with self.assertRaisesRegex(w.WorkflowError, 'ALREADY_ACTIVE'): run.claim(self.usage())
            run.complete(claim['token'], self.receipt(stage))
            run = w.Run(self.root, self.feature)  # fresh runtime instance every stage
        self.assertEqual(run.next(run.load())['status'], 'pr_open')

    def test_missing_evidence_and_unresolved_answers_never_advance(self):
        run = self.run_object()
        for stage in ('scope', 'specify'):
            c = run.claim(self.usage()); run.complete(c['token'], self.receipt(stage))
        c = run.claim(self.usage()); r = self.receipt('clarify'); r['unresolved'] = 1
        with self.assertRaisesRegex(w.WorkflowError, 'UNRESOLVED'): run.complete(c['token'], r)
        self.assertEqual(run.load()['active']['stage'], 'clarify')

    def test_changed_or_deleted_evidence_invalidates_stage(self):
        run = self.run_object(); claim = run.claim(self.usage()); r = self.receipt('scope')
        run.complete(claim['token'], r)
        (self.root / r['evidence'][0]).unlink()
        self.assertEqual(run.next(run.load())['stage'], 'scope')
        self.assertEqual(run.next(run.load())['reason'], 'inputs-or-evidence-changed')

    def test_checkpoint_generated_before_context_ceiling(self):
        run = self.run_object(); result = run.claim(self.usage(.51))
        self.assertEqual(result['status'], 'paused')
        self.assertTrue((run.path.parent / 'resume-prompt.md').is_file())
        self.assertIsNone(run.load()['active'])

    def test_policy_change_invalidates_and_preserves_explicit_selection(self):
        run = self.run_object(); c = run.claim(self.usage()); run.complete(c['token'], self.receipt('scope'))
        self.policy['processes']['qa'] = False; self.configure()
        run = w.Run(self.root, self.feature)
        self.assertEqual(run.next(run.load())['reason'], 'policy-changed')

    def test_checkbox_changes_do_not_invalidate_semantic_tasks(self):
        p = self.root / self.feature / 'tasks.md';p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('- [ ] T001 Implement behavior\n')
        a = w.fingerprint_files(self.root, [p.relative_to(self.root).as_posix()])
        p.write_text('- [x] T001 Implement behavior\n')
        self.assertEqual(a, w.fingerprint_files(self.root, a))
        p.write_text('- [x] T001 Implement different behavior\n')
        self.assertNotEqual(a, w.fingerprint_files(self.root, a))

    def test_path_traversal_and_binding_conflict_rejected(self):
        with self.assertRaises(w.WorkflowError): w.Run(self.root, '../other')
        run = self.run_object()
        with self.assertRaisesRegex(w.WorkflowError, 'BINDING_CONFLICT'): run.start('acme/app#12')

    def test_unknown_explicit_executor_never_falls_back(self):
        self.policy['execution']['engine'] = 'superspec'
        with self.assertRaisesRegex(w.WorkflowError, 'UNAVAILABLE'): w.resolve_commands(self.root, self.policy)

    def test_specify_can_bind_created_branch_only_with_matching_source(self):
        run = self.run_object(); claim = run.claim(self.usage())
        run.complete(claim['token'], self.receipt('scope'))
        claim = run.claim(self.usage())
        subprocess.run(['git', 'switch', '-qc', 'feature-example'], cwd=self.root, check=True)
        with self.assertRaisesRegex(w.WorkflowError, 'BRANCH_MISMATCH'): run.load()
        with self.assertRaisesRegex(w.WorkflowError, 'BINDING_MISMATCH'): run.bind(claim['token'])
        w.write(run.feature / 'scope-source.json', {'repo':'acme/app','issue':10})
        (run.feature / 'spec.md').write_text('# Example', encoding='utf-8')
        self.assertEqual(run.bind(claim['token'])['branch'], 'feature-example')
        run.complete(claim['token'], self.receipt('specify'))

    def test_changed_package_requires_reviewed_migration(self):
        run = self.run_object(); c = run.claim(self.usage()); run.complete(c['token'], self.receipt('scope'))
        (self.root / '.specify/presets/workflow/preset.yml').write_text('schema_version: "1.0"\n# updated', encoding='utf-8')
        with self.assertRaisesRegex(w.WorkflowError, 'DEPENDENCY_CHANGED'): run.claim(self.usage())
        self.assertEqual(run.migrate('Reviewed compatible package update')['next']['stage'], 'scope')
        self.assertEqual(len(list((run.path.parent / 'backups').glob('*.json'))), 1)

    def test_doctor_blocks_duplicate_hook_ownership(self):
        (self.root / '.specify/extensions.yml').write_text('hooks:\n  after_tasks:\n    - extension: project\n      command: speckit.project.sync\n', encoding='utf-8')
        self.assertIn('DUPLICATE_STAGE_OWNER', str(w.doctor(self.root, self.policy)))


if __name__ == '__main__':
    unittest.main()
