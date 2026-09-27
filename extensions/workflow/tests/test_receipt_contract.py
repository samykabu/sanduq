"""Workflow 1.6.0 receipt contract: compatibility (B0), input roles (B1), amendments (B2)."""
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_gate as c  # noqa: E402
import workflow as w  # noqa: E402
import fixture_008  # noqa: E402
import test_workflow as fixture  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def checkpoint_validator():
    directory = Path(__file__).resolve().parents[1] / 'schemas'
    schemas = {path.name: json.loads(path.read_text(encoding='utf-8')) for path in directory.glob('*.schema.json')}
    registry = Registry()
    for name, schema in schemas.items():
        Draft202012Validator.check_schema(schema)
        registry = registry.with_resource('https://sanduq.local/schemas/' + name, Resource.from_contents(schema))
    return Draft202012Validator(schemas['checkpoint-v1.schema.json'], registry=registry, format_checker=FormatChecker())


class Harness(unittest.TestCase):
    setUp = fixture.WorkflowTests.setUp
    configure = fixture.WorkflowTests.configure
    usage = fixture.WorkflowTests.usage
    receipt = fixture.WorkflowTests.receipt

    def run_object(self):
        # The shared fixture loads its own copy of workflow.py; the gate imports
        # `workflow`, so runs here use that module and raise its WorkflowError.
        run = w.Run(self.root, self.feature)
        run.start('acme/app#10')
        return run

    def commit_all(self, message='fixture'):
        subprocess.run(['git', 'add', '-A'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-qm', message], cwd=self.root, check=True, capture_output=True)

    def write(self, relative, text='content'):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return relative

    def set_policy(self, **receipts):
        self.policy['receipts'] = receipts
        self.configure()

    def complete_through(self, run, last):
        for stage in w.stages(self.policy):
            claim = run.claim(self.usage(), finalize=stage == 'pr')
            run.complete(claim['token'], self.receipt(stage))
            if stage == last:
                return

    def gate_rules(self, policy):
        rules = dict(policy['ci']['gate']['rules'])
        # QA and manual scripts, live GitHub answers and a PR merge ref are outside these fixtures.
        rules.update(documentation=False, live_answers=False, candidate_merge=False)
        return rules


class LegacyCheckpointTests(Harness):
    """An anonymised 1.3.0 checkpoint of a finished feature, read and continued by this release."""
    target_branch = None  # 1.3.0 checkpoints predate `target_branch`

    def setUp(self):
        super().setUp()
        self.policy = copy.deepcopy(fixture_008.load()['policy'])
        self.configure(superspec=True)
        subprocess.run(['git', 'switch', '-qc', fixture_008.BRANCH], cwd=self.root, check=True)
        self.original = fixture_008.materialise(self.root)
        self.feature = fixture_008.FEATURE
        if self.target_branch is not None:
            # A checkpoint started by 1.6.0 records the branch it forked from.
            self.original['target_branch'] = self.target_branch
            w.write(self.root / self.feature / 'workflow/checkpoint.json', self.original)
        self.commit_all('Materialise the anonymised 1.3.0 checkpoint')
        self.run = w.Run(self.root, self.feature)

    def gate(self):
        policy = w.load_policy(self.root)
        c.check_index(self.root, self.feature)
        result = c.check(self.root, self.feature, policy, None, self.gate_rules(policy))
        return {key: result[key] for key in ('feature', 'passed', 'rules')}

    def test_legacy_checkpoint_is_read_with_nothing_invalidated(self):
        state = self.run.load()
        checkpoint_validator().validate(state)
        self.assertTrue(all(w.receipt_current(self.root, self.feature, stage, receipt)
                            for stage, receipt in state['receipts'].items()))
        self.assertEqual(self.run.next(state), {'stage': None, 'status': 'ready_to_finalize',
                                                'command': 'speckit.workflow.finalize'})

    def test_preview_migrate_and_continue_with_the_same_gate_verdict(self):
        before = self.gate()
        self.assertTrue(before['passed'])
        with self.assertRaisesRegex(w.WorkflowError, 'DEPENDENCY_CHANGED'):
            self.run.claim(self.usage(), finalize=True)
        raw = self.run.path.read_bytes()

        preview = self.run.preview_migration()
        self.assertEqual(self.run.path.read_bytes(), raw)  # preview never writes
        self.assertFalse(list((self.run.path.parent / 'backups').glob('*.json')))
        self.assertEqual(preview['invalidated'], [])
        self.assertEqual(preview['preserved_as_historical'], list(self.original['receipts']))
        self.assertEqual(preview['changed_commands'], [])
        self.assertEqual(preview['blockers'], [])
        self.assertTrue(preview['can_apply'])

        result = self.run.migrate('workflow 1.6.0')
        migration = result['migration']
        self.assertEqual((migration['invalidated'], migration['preserved_as_historical']),
                         (preview['invalidated'], preview['preserved_as_historical']))
        self.assertEqual(migration['from'], preview['dependency_from'])
        self.assertEqual(migration['to'], preview['dependency_to'])
        saved = self.run.load()
        self.assertEqual(saved['migrations'][-1], migration)
        self.assertEqual(saved['migrations'][:-1], self.original['migrations'])
        self.assertEqual('target_branch' in saved, 'target_branch' in self.original)
        self.assertEqual(saved.get('target_branch'), self.original.get('target_branch'))
        # Every receipt kept, byte for byte: nothing re-stamped.
        self.assertEqual(saved['receipts'], self.original['receipts'])
        checkpoint_validator().validate(saved)

        self.commit_all('Record the 1.6.0 migration')
        self.assertEqual(self.gate(), before)
        claim = self.run.claim(self.usage(), finalize=True)
        self.assertEqual(claim['stage'], 'pr')

    def test_turning_on_required_roles_invalidates_no_completed_receipt(self):
        self.run.migrate('workflow 1.6.0')
        self.policy['receipts'] = {'require_input_roles': True}
        self.configure(superspec=True)
        run = w.Run(self.root, self.feature)
        preview = run.preview_migration()
        self.assertNotEqual(preview['policy_from'], preview['policy_to'])
        self.assertEqual(preview['invalidated'], [])
        result = run.migrate('Require declared input roles')
        self.assertEqual(result['migration']['invalidated'], [])
        self.assertEqual(run.load()['receipts'], self.original['receipts'])

    def test_amend_unchanged_clears_the_recorded_failure_shape(self):
        """The original feature failed `STALE_RECEIPT: execute` on an editorial evidence edit."""
        self.run.migrate('workflow 1.6.0')
        path = self.root / fixture_008.AMENDED_EVIDENCE
        path.write_bytes(path.read_bytes() + b'Grammar fix.\n')
        self.commit_all('Editorial evidence fix')
        with self.assertRaisesRegex(w.WorkflowError, r'STALE_RECEIPT: execute; changed paths: \["' +
                                    fixture_008.AMENDED_EVIDENCE):
            self.gate()
        stages = [s for s, r in self.original['receipts'].items() if fixture_008.AMENDED_EVIDENCE in r['evidence']]
        self.assertEqual(stages, ['execute', 'review'])
        for stage in stages:
            result = self.run.amend(stage, fixture_008.AMENDED_EVIDENCE, 'Grammar fix; findings unchanged', 'unchanged')
            self.assertEqual(result['stale'], [])
        self.commit_all('Record the amendments')
        policy = w.load_policy(self.root)
        verdict = c.check(self.root, self.feature, policy, None, self.gate_rules(policy))
        self.assertTrue(verdict['passed'])
        self.assertEqual([(a['stage'], a['path'], a['assessment']) for a in verdict['amendments']],
                         [(s, fixture_008.AMENDED_EVIDENCE, 'unchanged') for s in stages])
        receipts = self.run.load()['receipts']
        for stage, receipt in receipts.items():
            changed = {p for p in receipt['fingerprints'] if receipt['fingerprints'][p] != self.original['receipts'][stage]['fingerprints'][p]}
            self.assertEqual(changed, {fixture_008.AMENDED_EVIDENCE} if stage in stages else set())


class LegacyCheckpointWithTargetBranchTests(LegacyCheckpointTests):
    """The same checkpoint carrying the optional `target_branch` a 1.6.0 start records."""
    target_branch = 'main'


class InputRoleTests(Harness):
    def test_roles_bearing_receipt_round_trips(self):
        run = self.run_object()
        claim = run.claim(self.usage())
        receipt = self.receipt('scope')
        target = self.write('src/service.py', 'print(1)')
        roles = {target: {'role': 'consulted', 'because': 'implementation target; scope does not rest on its content'},
                 receipt['evidence'][0]: {'role': 'dependency'}}
        receipt['inputs'] = receipt['inputs'] + [target]
        receipt['input_roles'] = roles
        run.complete(claim['token'], receipt)
        stored = w.read(run.path)['receipts']['scope']
        self.assertEqual(stored['input_roles'], roles)
        self.assertEqual(stored['inputs'], receipt['inputs'])
        self.assertIn(target, stored['fingerprints'])  # consulted inputs keep their hash
        checkpoint_validator().validate(w.read(run.path))

    def test_role_validation(self):
        run = self.run_object()
        claim = run.claim(self.usage())
        outside = self.write('reference/brief.md')
        cases = [
            ({'other.md': {'role': 'dependency'}}, 'INPUT_ROLE_NOT_IN_MANIFEST'),
            ({outside: {'role': 'optional'}}, 'INPUT_ROLE_INVALID'),
            ({outside: {'role': 'consulted'}}, 'INPUT_ROLE_REASON_REQUIRED'),
            ({outside: {'role': 'consulted', 'because': '  '}}, 'INPUT_ROLE_REASON_INVALID'),
            ({outside: {'role': 'dependency', 'note': 'x'}}, 'INPUT_ROLE_INVALID'),
            ('all', 'INPUT_ROLES_INVALID'),
        ]
        for roles, error in cases:
            with self.subTest(error=error):
                receipt = self.receipt('scope')
                receipt['inputs'] = receipt['inputs'] + [outside]
                receipt['input_roles'] = roles
                with self.assertRaisesRegex(w.WorkflowError, error):
                    run.complete(claim['token'], receipt)
        receipt = self.receipt('scope')
        receipt['input_roles'] = {receipt['evidence'][0]: {'role': 'consulted', 'because': 'context'}}
        with self.assertRaisesRegex(w.WorkflowError, 'INPUT_ROLE_CONSULTED_NOT_ALLOWED'):
            run.complete(claim['token'], receipt)
        for field in w.RUNTIME_RECEIPT_FIELDS:
            receipt = self.receipt('scope')
            receipt[field] = []
            with self.assertRaisesRegex(w.WorkflowError, 'RECEIPT_FIELD_RESERVED'):
                run.complete(claim['token'], receipt)

    def test_required_input_can_never_be_consulted(self):
        run = self.run_object()
        claim = run.claim(self.usage()); run.complete(claim['token'], self.receipt('scope'))
        claim = run.claim(self.usage())
        receipt = self.receipt('specify')
        spec = self.feature + '/spec.md'
        receipt['inputs'] = receipt['inputs'] + [spec]
        receipt['input_roles'] = {spec: {'role': 'consulted', 'because': 'context'}}
        with self.assertRaisesRegex(w.WorkflowError, 'INPUT_ROLE_CONSULTED_NOT_ALLOWED'):
            run.complete(claim['token'], receipt)

    def test_required_roles_only_when_the_policy_asks(self):
        feature_input = self.write(self.feature + '/notes.md')
        memory_input = self.write('.specify/memory/decisions.md')
        outside = self.write('reference/brief.md')
        for required in (False, True):
            with self.subTest(required=required):
                self.set_policy(require_input_roles=required)
                (self.root / self.feature / 'workflow/checkpoint.json').unlink(missing_ok=True)
                run = self.run_object()
                claim = run.claim(self.usage())
                receipt = self.receipt('scope')
                receipt['inputs'] = receipt['inputs'] + [feature_input, memory_input, outside]
                if required:
                    with self.assertRaisesRegex(w.WorkflowError, 'INPUT_ROLE_UNDECLARED: ' + outside + '$'):
                        run.complete(claim['token'], receipt)
                    receipt['input_roles'] = {outside: {'role': 'dependency', 'because': 'the brief defines scope'}}
                run.complete(claim['token'], receipt)

    def test_receipts_policy_is_validated(self):
        for value in ({'require_input_roles': 'yes'}, {'unknown': True}, ['require_input_roles']):
            with self.subTest(value=value):
                policy = w.default_policy(False, False)
                policy['receipts'] = value
                with self.assertRaisesRegex(w.WorkflowError, 'RECEIPTS_POLICY_INVALID'):
                    w.validate_policy(policy)
        legacy = w.default_policy(False, False)
        legacy.pop('receipts')
        self.assertNotIn('receipts', w.validate_policy(legacy))  # never filled in: the digest stays
        self.assertFalse(w.require_input_roles(legacy))

    def test_legacy_receipt_reads_every_input_as_dependency(self):
        run = self.run_object()
        claim = run.claim(self.usage())
        receipt = self.receipt('scope')
        target = self.write('src/service.py', 'print(1)')
        receipt['inputs'] = receipt['inputs'] + [target]
        run.complete(claim['token'], receipt)
        self.write(target, 'print(2)')
        state = run.load()
        self.assertFalse(w.receipt_current(self.root, self.feature, 'scope', state['receipts']['scope']))
        self.assertEqual(run.next(state)['stage'], 'scope')
        self.assertNotIn('advisory_drift', run.next(state))


class CascadeTests(Harness):
    """The #14 pattern: an early receipt lists a file that implementation later changes."""

    def scope_with_target(self, role):
        run = self.run_object()
        claim = run.claim(self.usage())
        receipt = self.receipt('scope')
        target = self.write('src/service.py', 'print(1)')
        receipt['inputs'] = receipt['inputs'] + [target]
        if role:
            receipt['input_roles'] = {target: {'role': role, 'because': 'implementation target of T012; '
                                               'the scope does not rest on its current content'}}
        run.complete(claim['token'], receipt)
        return run, target

    def test_consulted_input_changed_during_stage_is_advisory(self):
        run, target = self.scope_with_target('consulted')
        recorded = run.load()['receipts']['scope']['fingerprints'][target]
        claim = run.claim(self.usage())
        self.write(target, 'print(2)')
        result = run.complete(claim['token'], self.receipt('specify'))
        state = run.load()
        self.assertEqual(state['receipts']['scope']['fingerprints'][target], recorded)  # not re-stamped
        self.assertTrue(w.receipt_current(self.root, self.feature, 'scope', state['receipts']['scope']))
        self.assertEqual(state['lineage'][-1]['stage'], 'specify')
        self.assertTrue(state['lineage'][-1]['advisory'])
        self.assertIn(target, state['lineage'][-1]['consulted'])
        self.assertEqual(result['stage'], 'clarify')
        self.assertEqual(result['advisory_drift'], [{'stage': 'scope', 'path': target, 'because': state['receipts']['scope']['input_roles'][target]['because']}])

    def test_dependency_changed_during_stage_still_fails(self):
        for role in ('dependency', None):
            with self.subTest(role=role):
                (self.root / self.feature / 'workflow/checkpoint.json').unlink(missing_ok=True)
                run, target = self.scope_with_target(role)
                claim = run.claim(self.usage())
                self.write(target, 'print(2)')
                with self.assertRaisesRegex(w.WorkflowError, 'UPSTREAM_INPUT_CHANGED_DURING_STAGE: ' + target):
                    run.complete(claim['token'], self.receipt('specify'))
                state = run.load(); state['active'] = None; w.write(run.path, state)

    def test_dependency_in_any_earlier_receipt_wins(self):
        run, target = self.scope_with_target('consulted')
        claim = run.claim(self.usage())
        receipt = self.receipt('specify')
        receipt['inputs'] = receipt['inputs'] + [target]
        run.complete(claim['token'], receipt)  # specify depends on the target
        claim = run.claim(self.usage())
        self.write(target, 'print(2)')
        with self.assertRaisesRegex(w.WorkflowError, 'UPSTREAM_INPUT_CHANGED_DURING_STAGE'):
            run.complete(claim['token'], self.receipt('clarify'))


class AmendmentTests(Harness):
    def ready(self):
        self.policy = w.default_policy(False, False)
        self.configure()
        run = self.run_object()
        self.complete_through(run, 'ready')
        self.commit_all()
        return run

    def gate(self):
        policy = w.load_policy(self.root)
        return c.check(self.root, self.feature, policy, None, self.gate_rules(policy))

    def edit_execute_evidence(self):
        path = self.feature + '/evidence/execute.txt'
        self.write(path, 'actual fixture evidence, grammar fixed')
        return path

    def test_unchanged_amendment_passes_the_gate_and_is_listed(self):
        run = self.ready()
        before = copy.deepcopy(run.load()['receipts'])
        path = self.edit_execute_evidence()
        with self.assertRaisesRegex(w.WorkflowError, 'STALE_RECEIPT: execute'):
            self.gate()
        result = run.amend('execute', path, 'Grammar fix only', 'unchanged', actor='reviewer')
        amendment = result['amendment']
        self.assertTrue(result['current'])
        self.assertEqual(result['stale'], [])
        self.assertEqual((amendment['old_hash'], amendment['new_hash']),
                         (before['execute']['fingerprints'][path], w.fingerprint_files(self.root, [path])[path]))
        self.assertEqual((amendment['reason'], amendment['assessment'], amendment['actor']),
                         ('Grammar fix only', 'unchanged', 'reviewer'))
        after = run.load()['receipts']
        for stage, receipt in after.items():  # only that one entry was re-hashed
            expected = dict(before[stage]['fingerprints'])
            if stage == 'execute':
                expected[path] = amendment['new_hash']
            self.assertEqual(receipt['fingerprints'], expected)
        self.assertEqual(len(list((run.path.parent / 'backups').glob('*.json'))), 1)
        verdict = self.gate()
        self.assertTrue(verdict['passed'])
        self.assertEqual(verdict['amendments'][0]['stage'], 'execute')
        self.assertEqual(verdict['amendments'][0]['path'], path)
        checkpoint_validator().validate(run.load())

    def test_changed_amendment_stales_verify_review_and_ready(self):
        run = self.ready()
        path = self.edit_execute_evidence()
        result = run.amend('execute', path, 'A finding was reclassified', 'changed')
        self.assertEqual(result['stale'], ['verify', 'review', 'ready'])
        state = run.load()
        self.assertTrue(w.receipt_current(self.root, self.feature, 'execute', state['receipts']['execute']))
        for stage in ('verify', 'review', 'ready'):
            self.assertFalse(w.receipt_current(self.root, self.feature, stage, state['receipts'][stage]))
        self.assertEqual(run.next(state)['stage'], 'verify')
        with self.assertRaisesRegex(w.WorkflowError, 'STALE_RECEIPT: verify.*changed amendment of execute'):
            self.gate()
        checkpoint_validator().validate(state)
        claim = run.claim(self.usage())  # re-recording verify clears the stale receipts
        self.assertEqual(claim['stage'], 'verify')
        self.assertNotIn('review', run.load()['receipts'])

    def test_unlisted_path_and_other_misuse_are_refused(self):
        run = self.ready()
        receipt = run.load()['receipts']['execute']
        input_only = self.write(self.feature + '/notes.md', 'x')
        cases = [
            (('execute', self.feature + '/spec.md', 'why', 'unchanged'), 'AMEND_PATH_NOT_EVIDENCE'),
            (('execute', input_only, 'why', 'unchanged'), 'AMEND_PATH_NOT_EVIDENCE'),
            (('execute', self.feature + '/evidence/verify.txt', 'why', 'unchanged'), 'AMEND_PATH_NOT_EVIDENCE'),
            (('execute', receipt['evidence'][0], 'why', 'unchanged'), 'AMENDMENT_NOT_NEEDED'),
            (('execute', receipt['evidence'][0], ' ', 'unchanged'), 'AMENDMENT_REASON_REQUIRED'),
            (('execute', receipt['evidence'][0], 'why', 'minor'), 'AMENDMENT_ASSESSMENT_INVALID'),
            (('pr', receipt['evidence'][0], 'why', 'unchanged'), 'RECEIPT_MISSING'),
        ]
        raw = run.path.read_bytes()
        for args, error in cases:
            with self.subTest(error=error):
                with self.assertRaisesRegex(w.WorkflowError, error):
                    run.amend(*args)
        self.assertEqual(run.path.read_bytes(), raw)
        path = self.edit_execute_evidence()
        (self.root / path).unlink()
        with self.assertRaisesRegex(w.WorkflowError, 'EVIDENCE_MISSING'):
            run.amend('execute', path, 'why', 'unchanged')

    def test_amend_waits_for_an_active_claim(self):
        run = self.ready()
        path = self.edit_execute_evidence()
        run.claim(self.usage(), finalize=True)
        with self.assertRaisesRegex(w.WorkflowError, 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_AMEND'):
            run.amend('execute', path, 'why', 'unchanged')


class CommandLineTests(Harness):
    def cli(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'workflow.py'), '--root', str(self.root), *args],
                                capture_output=True, text=True, encoding='utf-8')
        return result.returncode, json.loads(result.stdout)

    def test_migrate_preview_and_amend_commands(self):
        run = self.run_object()
        self.complete_through(run, 'execute')
        code, preview = self.cli('migrate', '--feature', self.feature, '--preview')
        self.assertEqual(code, 0, preview)
        self.assertEqual((preview['preview'], preview['invalidated']), (True, []))
        code, result = self.cli('migrate', '--feature', self.feature)
        self.assertEqual((code, result['error']), (1, 'MIGRATION_REASON_REQUIRED'))
        code, result = self.cli('migrate', '--feature', self.feature, '--reason', 'reviewed')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['migration']['preserved_as_historical'], preview['preserved_as_historical'])
        path = self.feature + '/evidence/execute.txt'
        self.write(path, 'edited')
        code, result = self.cli('amend', '--feature', self.feature, '--stage', 'execute', '--evidence', path,
                                '--reason', 'typo', '--assessment', 'unchanged')
        self.assertEqual(code, 0, result)
        self.assertTrue(result['amended'])
        self.assertEqual(result['amendment']['actor'], 'Test')


if __name__ == '__main__':
    unittest.main()
