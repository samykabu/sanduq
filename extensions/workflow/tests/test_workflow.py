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
        subprocess.run(['git','remote','add','origin','https://github.com/acme/app.git'],cwd=self.root,check=True)
        self.feature = 'specs/001-example'
        self.policy = w.default_policy(True, True)
        self.configure()

    def configure(self, superspec=False):
        path = self.root / '.specify/workflow.yml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(self.policy), encoding='utf-8')
        w.write(self.root/'.specify/init-options.json',{'integration':'codex','ai_skills':True})
        w.write(self.root / '.specify/extensions/project/config.json', {
            'owner': 'acme', 'projectNumber': 1, 'projectId': 'P', 'statusFieldId': 'F',
            'stateFile': '.specify/project-sync-state.json', 'hookMode': 'required',
            'statusOptions': {name: name for name in ('Backlog', 'Feature Specification', 'Need Clarifications', 'Ready', 'In progress', 'In review', 'Done')},
            'phaseToStatus': {'open': 'Feature Specification', 'analysis': 'Ready', 'engineer-review': 'Ready',
                              'ready': 'Ready', 'in-progress': 'In progress', 'in-review': 'In review', 'done': 'Done'},
        })
        (self.root / '.specify/extensions.yml').write_text('hooks: {}\n', encoding='utf-8')
        for preset in ('workflow', 'scope-gate', 'scope-brainstorm'):
            p = self.root / '.specify/presets' / preset / 'preset.yml'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('schema_version: "1.0"\n', encoding='utf-8')
        w.write(self.root / '.specify/presets/.registry', {'presets': {p: {'enabled':True} for p in ('workflow','scope-gate','scope-brainstorm')}})
        versions = {'scope': '1.4.0', 'project': '2.1.0', 'pr': '4.1.0', 'assure': '2.2.0', 'user-manual': '1.2.0'}
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
        # Semantic commands create these artifacts; fixtures provide the minimal outputs.
        directory = self.root / self.feature
        directory.mkdir(parents=True, exist_ok=True)
        for name, first in (('spec.md', 'specify'), ('plan.md', 'plan'), ('tasks.md', 'tasks')):
            path = directory / name
            if w.BASE_STAGES.index(stage) >= w.BASE_STAGES.index(first) and not path.exists():
                path.write_text('- [x] T001 Done behavior' if name == 'tasks.md' else '# Fixture ' + name, encoding='utf-8')
        if w.BASE_STAGES.index(stage) >= w.BASE_STAGES.index('specify') and not (directory / 'scope-source.json').exists():
            w.write(directory / 'scope-source.json', {'repo': 'acme/app', 'issue': 10})
        if w.BASE_STAGES.index(stage) >= w.BASE_STAGES.index('taskstoissues') and not (directory / 'workflow/task-issues.json').exists():
            w.write(directory / 'workflow/task-issues.json', {'repo': 'acme/app', 'parent': 10, 'feature': self.feature,
                                                           'tasks': {'T001': {'number': 11, 'linked': True}}})
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
        self.assertFalse(gate['pause'])  # Estimates must never force a fresh session
        self.assertFalse(gate['guaranteed'])
        self.assertEqual(gate['method'], 'unavailable')
        self.policy['context']['mode'] = 'strict'
        with self.assertRaisesRegex(w.WorkflowError, 'UNENFORCEABLE'): w.context_gate(self.policy, self.usage())
        usage = self.usage(method='measured'); usage['pre_call_bound'] = True
        self.assertTrue(w.context_gate(self.policy, usage)['guaranteed'])

    def test_stale_context_rejected(self):
        self.policy['context']['mode'] = 'strict'
        usage = self.usage(method='measured'); usage['pre_call_bound'] = True; usage['observed_at'] = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
        with self.assertRaisesRegex(w.WorkflowError, 'STALE'): w.context_gate(self.policy, usage)

    def test_unreliable_context_never_pauses_or_blocks_default_claims(self):
        cases = [self.usage(.99), {'session_id': 'host-without-telemetry'},
                 dict(self.usage(.99, 'measured'), reliable=False),
                 dict(self.usage(.99, 'measured'), observed_at='invalid'),
                 dict(self.usage(.99, 'measured'), fraction=None),
                 dict(self.usage(.99, 'measured'), observed_at=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat())]
        for usage in cases:
            with self.subTest(usage=usage):
                self.assertFalse(w.context_gate(self.policy, usage)['pause'])
        run = self.run_object()
        self.assertEqual(run.claim({'session_id': 'host-without-telemetry'})['stage'], 'scope')

    def test_legacy_estimated_mode_also_continues_without_reliable_measurements(self):
        self.policy['context']['mode'] = 'measured-with-estimated-fallback'
        self.assertFalse(w.context_gate(self.policy, self.usage(.99))['pause'])

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
        run = self.run_object(); result = run.claim(self.usage(.51, method='measured'))
        self.assertEqual(result['status'], 'paused')
        self.assertTrue((run.path.parent / 'resume-prompt.md').is_file())
        self.assertIsNone(run.load()['active'])

    def test_policy_change_invalidates_and_preserves_explicit_selection(self):
        run = self.run_object(); c = run.claim(self.usage()); run.complete(c['token'], self.receipt('scope'))
        self.policy['processes']['qa'] = False; self.configure()
        run = w.Run(self.root, self.feature)
        self.assertEqual(run.next(run.load())['stage'], 'specify')  # Scope does not repeat for a QA toggle.

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
        self.assertEqual(run.migrate('Reviewed compatible package update')['next']['stage'], 'specify')
        self.assertEqual(len(list((run.path.parent / 'backups').glob('*.json'))), 1)

    def test_migration_rebinds_a_policy_section_an_upgrade_added(self):
        """A release that only adds a policy section must not orphan finished evidence."""
        run = self.run_object(); claim = run.claim(self.usage()); run.complete(claim['token'], self.receipt('scope'))
        self.policy['ci'] = {'provider': 'github-actions', 'policy': 'self-hosted-required',
                             'runners': {'linux': ['private-runner']},
                             'capabilities': {'system_packages': 'sudo-apt', 'python': 'setup-action', 'python_version': '3.13'},
                             'exceptions': []}
        self.configure()
        run = self.run_object()
        state = w.read(run.path)
        self.assertNotEqual(state['policy_digest'], w.digest(run.policy))
        result = run.migrate('Upgrade added the ci selection')
        state = w.read(run.path)
        self.assertEqual(state['policy_digest'], w.digest(run.policy))
        self.assertIn('scope', state['receipts'])
        self.assertEqual(state['policy_changes'][-1]['via'], 'migrate')
        self.assertEqual(state['migrations'][-1]['invalidated'], [])
        self.assertEqual(result['next']['stage'], 'specify')

    def test_migration_still_invalidates_a_semantic_policy_change(self):
        run = self.run_object(); claim = run.claim(self.usage()); run.complete(claim['token'], self.receipt('scope'))
        self.policy['scope'] = dict(self.policy.get('scope', {}), artifact_directory='design/scope')
        self.configure()
        run = self.run_object()
        run.migrate('Scope artifact location changed')
        state = w.read(run.path)
        self.assertEqual(state['policy_digest'], w.digest(run.policy))
        self.assertNotIn('scope', state['receipts'])

    def test_explicit_upgrade_revalidation_invalidates_from_selected_stage(self):
        run=self.run_object();c=run.claim(self.usage());run.complete(c['token'],self.receipt('scope'))
        self.assertEqual(run.migrate('Scope contract changed',invalidate_from='scope')['next']['stage'],'scope')

    def test_claim_activates_explicit_feature_and_prevents_concurrent_other_feature(self):
        run=self.run_object();run.claim(self.usage())
        self.assertEqual(w.read(self.root/'.specify/feature.json')['feature_directory'],self.feature)
        other=w.Run(self.root,'specs/002-other');other.start('acme/app#20')
        with self.assertRaisesRegex(w.WorkflowError,'OTHER_FEATURE'):other.claim(self.usage())

    def test_existing_wrong_feature_and_wrong_repository_rejected(self):
        w.write(self.root/self.feature/'scope-source.json',{'repo':'acme/app','issue':20})
        with self.assertRaisesRegex(w.WorkflowError,'FEATURE_BINDING'):self.run_object()
        with self.assertRaisesRegex(w.WorkflowError,'REPOSITORY_MISMATCH'):w.Run(self.root,'specs/002-other').start('other/app#1')

    def test_doctor_blocks_duplicate_hook_ownership(self):
        (self.root / '.specify/extensions.yml').write_text('hooks:\n  after_tasks:\n    - extension: project\n      command: speckit.project.sync\n', encoding='utf-8')
        self.assertIn('DUPLICATE_STAGE_OWNER', str(w.doctor(self.root, self.policy)))

    def test_active_legacy_bridge_blocks_competing_executor(self):
        w.write(self.root/'.specify/superpowers-handoff.json',{'status':'executing','feature_directory':self.feature})
        self.assertIn('LEGACY_EXECUTOR_OWNS_FEATURE',str(w.doctor(self.root,self.policy)))

    def test_inactive_host_commands_cannot_satisfy_active_host(self):
        w.write(self.root/'.specify/integration.json',{'default_integration':'claude'})
        self.assertFalse(w.command_exists(self.root,'speckit.plan'))
        w.write(self.root/'.specify/integration.json',{'default_integration':'unsupported'})
        self.assertIn('HOST_UNSUPPORTED',str(w.doctor(self.root,self.policy)))

    def test_core_command_drift_requires_reviewed_upgrade(self):
        run=self.run_object()
        path=self.root/'.agents/skills/speckit-specify/SKILL.md';path.write_text('Changed upstream contract')
        with self.assertRaisesRegex(w.WorkflowError,'DEPENDENCY_CHANGED'):run.claim(self.usage())

    def test_required_spec_cannot_be_omitted_from_receipt_inputs(self):
        run = self.run_object()
        for stage in ('scope', 'specify'):
            claim = run.claim(self.usage()); run.complete(claim['token'], self.receipt(stage))
        self.assertIn(self.feature + '/spec.md', run.load()['receipts']['specify']['fingerprints'])
        (run.feature / 'spec.md').write_text('Changed requirement', encoding='utf-8')
        self.assertEqual(run.next(run.load())['stage'], 'specify')

    def test_missing_required_plan_cannot_pass(self):
        run = self.run_object()
        for stage in ('scope', 'specify', 'clarify'):
            claim = run.claim(self.usage()); run.complete(claim['token'], self.receipt(stage))
        claim = run.claim(self.usage()); receipt = self.receipt('plan')
        (run.feature / 'plan.md').unlink()
        with self.assertRaisesRegex(w.WorkflowError, 'INPUT_MISSING'):
            run.complete(claim['token'], receipt)

    def test_explicit_clarify_refresh_preserves_artifacts_and_rechecks_remote_stage(self):
        run = self.run_object()
        for stage in ('scope', 'specify', 'clarify', 'plan', 'tasks'):
            claim = run.claim(self.usage()); run.complete(claim['token'], self.receipt(stage))
        before = {name: (run.feature / name).read_bytes() for name in ('spec.md', 'plan.md', 'tasks.md')}
        result = run.refresh('clarify', 'Explicit invocation must reread current GitHub answers')
        self.assertEqual(result['next']['stage'], 'clarify')
        self.assertEqual(set(run.load()['receipts']), {'scope', 'specify'})
        self.assertEqual(before, {name: (run.feature / name).read_bytes() for name in before})
        self.assertEqual(len(list((run.path.parent / 'backups').glob('*.json'))), 1)
        claim = run.claim(self.usage())
        self.assertEqual(claim['mode'], 'revalidate')
        with self.assertRaisesRegex(w.WorkflowError, 'ACTIVE_CLAIM'):
            run.refresh('clarify', 'Cannot take over a running claim')

    def test_refresh_cannot_skip_stale_scope_evidence(self):
        run = self.run_object()
        for stage in ('scope', 'specify', 'clarify'):
            claim = run.claim(self.usage()); run.complete(claim['token'], self.receipt(stage))
        (run.feature / 'evidence/scope.txt').unlink()
        self.assertEqual(run.refresh('clarify', 'New issue comments')['next']['stage'], 'scope')

    def test_claim_requires_project_setup_but_installation_doctor_does_not(self):
        (self.root / '.specify/extensions/project/config.json').unlink()
        self.assertTrue(w.doctor(self.root, self.policy)['ok'])
        run = self.run_object()
        with self.assertRaisesRegex(w.WorkflowError, 'PROJECT_CONFIG_REQUIRED'):
            run.claim(self.usage())

    def test_project_doctor_uses_real_column_names_and_detects_missing_mapping(self):
        path = self.root / '.specify/extensions/project/config.json'; config = w.read(path)
        names = {name: 'Custom ' + name for name in config['statusOptions']}
        config['statusOptions'] = {names[name]: value for name, value in config['statusOptions'].items()}
        config['phaseToStatus'] = {phase: names[name] for phase, name in config['phaseToStatus'].items()}
        w.write(path, config); self.policy['scope'] = {'statuses': names}
        self.assertEqual(w.project_errors(self.root, self.policy), [])
        config['phaseToStatus'].pop('ready'); w.write(path, config)
        self.assertIn('PROJECT_PHASE_UNMAPPED: ready', w.project_errors(self.root, self.policy))

    def test_managed_project_defaults_do_not_regress_new_spec_to_backlog(self):
        path = self.root / '.specify/extensions/project/config.json'; path.unlink()
        self.policy['scope'] = {'statuses': {'Feature Specification': 'Discovery', 'Ready': 'Planned'}}
        phases = w.project_defaults(self.root, self.policy)['phaseToStatus']
        self.assertEqual(phases['open'], 'Discovery')
        self.assertEqual(phases['analysis'], 'Planned')
        w.write(path, {'projectId': 'P', 'phaseToStatus': {'analysis': 'Technical planning'}})
        self.assertEqual(w.project_defaults(self.root, self.policy)['phaseToStatus']['analysis'], 'Technical planning')
        w.write(path, [])
        with self.assertRaisesRegex(w.WorkflowError, 'PROJECT_CONFIG_INVALID'):
            w.project_defaults(self.root, self.policy)
        self.assertEqual(w.project_errors(self.root, self.policy), ['PROJECT_CONFIG_INVALID: expected a JSON object'])

    def test_malformed_policy_and_hooks_fail_before_dispatch(self):
        policy=w.default_policy(False,False);policy['processes']='invalid'
        with self.assertRaisesRegex(w.WorkflowError,'SECTION_INVALID'):w.validate_policy(policy)
        (self.root/'.specify/extensions.yml').write_text('hooks: wrong')
        with self.assertRaisesRegex(w.WorkflowError,'HOOK_CONFIG_INVALID'):w.doctor(self.root,self.policy)


if __name__ == '__main__':
    unittest.main()
