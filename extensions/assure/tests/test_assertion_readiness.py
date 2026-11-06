"""Analyze records only a well-formed readiness record (`<feature>/qa/assertions.json`): each acceptance
assertion names its requirement, risk, owning layer, existing proof or linked gap task, and applicability.
The checks are mechanical. They prove cited files, test names and task ids exist; they never judge whether a
cited test is adequate, so every result also says `semantic: not-verified`.

The synthetic feature lives in fixtures/readiness/base: FR-001 is a real gap (add), FR-002 is already proven
(reuse), FR-003 crosses a real keyring/server boundary (extend), FR-004 is not applicable (no mobile surface).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
EXTENSION = TESTS.parent
READINESS = EXTENSION / 'scripts/assure_readiness.py'
STATE = EXTENSION / 'scripts/assure_state.py'
FIXTURE = TESTS / 'fixtures/readiness/base'
FEATURE = 'specs/001-period-rules'
RECORD = FEATURE + '/qa/assertions.json'
TASKS = FEATURE + '/tasks.md'
SPEC = FEATURE + '/spec.md'
UNIT = 'tests/unit/period_rules.spec.ts'
NATIVE = 'tests/native/sign_out.native.ts'
POLICY = 'docs/qa-policy.md'
SIBLING = 'specs/002-other-feature'
# Some runners keep their flows as YAML; a quoted flow name there is a test identity.
YAML_FLOW = ('# Runner flow (synthetic)\nappId: example.periods\nname: "capacity editor rejects 9"\n---\n'
             '- launchApp\n- tapOn: "Capacity"\n- inputText: "9"\n- assertVisible: "Capacity must be 1 to 8"\n')
STATE_FILE = '.specify/extensions/assure/state/001-period-rules-analyze.json'
MANUAL_BLOCK = ('\n<!-- user-manual-tasks:start -->\n### User Manual tasks\n\n- [ ] T090 Document period rules in '
                'User-Manual/docs/en/modules/periods/index.md\n<!-- user-manual-tasks:end -->\n')

sys.path.insert(0, str(EXTENSION.parent / 'scripts/shared'))
import sanduq_freshness  # noqa: E402  the pre-readiness analyze record, used to build a historical state


def copy_lf(source, target):
    """The fixture with LF endings whatever the checkout's autocrlf setting."""
    for path in source.rglob('*'):
        if path.is_file():
            out = target / path.relative_to(source)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))


class ReadinessFixture:
    """Not a TestCase: one committed template repository per class, copied for each test."""

    @classmethod
    def setUpClass(cls):
        holder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(holder.cleanup)
        cls.template = Path(holder.name).resolve() / 'repository'
        copy_lf(FIXTURE, cls.template)
        for args in (('init', '-q'), ('add', '.'),
                     ('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'baseline')):
            subprocess.run(['git', *args], cwd=cls.template, check=True, capture_output=True)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root = base / 'repository'
        shutil.copytree(self.template, self.root)
        # A real file that carries the cited test name, but outside the trusted project.
        self.outside = base / 'outside'
        self.outside.mkdir()
        shutil.copy(self.root / UNIT, self.outside / 'period_rules.spec.ts')
        (self.outside / 'notes.md').write_text('Mobile is planned for a later release.\n', encoding='utf-8')

    # File helpers
    def read(self, rel):
        return (self.root / rel).read_text(encoding='utf-8')

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8', newline='\n')

    def append(self, rel, text):
        self.write(rel, self.read(rel) + text)

    def replace(self, rel, old, new):
        text = self.read(rel)
        self.assertIn(old, text)
        self.write(rel, text.replace(old, new))

    def doc(self):
        return json.loads(self.read(RECORD))

    def save(self, doc):
        self.write(RECORD, json.dumps(doc, indent=2) + '\n')

    def edit(self, ident, **fields):
        """Change one assertion; a None value removes the field."""
        doc = self.doc()
        row = next(r for r in doc['assertions'] if r['id'] == ident)
        for key, value in fields.items():
            row.pop(key, None) if value is None else row.__setitem__(key, value)
        self.save(doc)

    def copy_row(self, ident, **fields):
        doc = self.doc()
        row = dict(next(r for r in doc['assertions'] if r['id'] == ident), **fields)
        doc['assertions'].append(row)
        self.save(doc)

    def drop_row(self, ident):
        doc = self.doc()
        doc['assertions'] = [r for r in doc['assertions'] if r['id'] != ident]
        self.save(doc)

    # Public commands
    def invoke(self, script, *args):
        """One public command in the fixture project (not named `run`: that is unittest.TestCase.run)."""
        return subprocess.run([sys.executable, str(script), *args], cwd=self.root, capture_output=True,
                              text=True, encoding='utf-8')

    def check(self):
        proc = self.invoke(READINESS, 'check', '--feature', FEATURE, '--repo-root', str(self.root), '--json')
        return proc.returncode, json.loads(proc.stdout)

    def state(self, action, *extra):
        proc = self.invoke(STATE, action, '--kind', 'analyze', '--feature', FEATURE, '--repo-root', str(self.root),
                        *extra)
        if '--summary' in extra:
            return proc.returncode, proc.stdout
        return proc.returncode, json.loads(proc.stdout)

    def state_bytes(self):
        path = self.root / STATE_FILE
        return path.read_bytes() if path.is_file() else None

    @staticmethod
    def found(result):
        return {(e['code'], e['assertion']) for e in result.get('errors', [])}

    def assertRejected(self, result, assertion, code=None):
        """The record fails and names `assertion`; `code`, when given, is the documented error code."""
        self.assertFalse(result.get('ok', result.get('current')), result)
        named = {a for _, a in self.found(result)}
        self.assertIn(assertion, named, result)
        if code:
            self.assertIn((code, assertion), self.found(result), result)


class ReadinessCheckTest(ReadinessFixture, unittest.TestCase):
    # (case, mutation, error code, assertion or task the error names)
    REJECTED = [
        ('bogus proof name hides a real gap',
         lambda t: t.edit('A-001', disposition='reuse', tasks=[],
                          proof=[{'path': UNIT, 'name': 'rejects a reversed period'}]),
         'proof-name-not-found', 'A-001'),
        ('reuse without proof', lambda t: t.edit('A-001', disposition='reuse', tasks=[], proof=[]),
         'proof-required', 'A-001'),
        ('extend without proof', lambda t: t.edit('A-003', proof=[]), 'proof-required', 'A-003'),
        ('proof file does not exist',
         lambda t: t.edit('A-002', proof=[{'path': 'tests/unit/removed.spec.ts', 'name': 'rejects capacity 0 and 9'}]),
         'proof-path-missing', 'A-002'),
        ('relative proof path climbs out of the project',
         lambda t: t.edit('A-002', proof=[{'path': '../outside/period_rules.spec.ts',
                                           'name': 'rejects capacity 0 and 9'}]),
         'proof-path-outside-root', 'A-002'),
        ('absolute proof path outside the project',
         lambda t: t.edit('A-002', proof=[{'path': str(t.outside / 'period_rules.spec.ts'),
                                           'name': 'rejects capacity 0 and 9'}]),
         'proof-path-outside-root', 'A-002'),
        ('a feature document is not a test',
         lambda t: t.edit('A-002', proof=[{'path': SPEC, 'name': 'Capacity accepts whole numbers 1 to 8'}]),
         'proof-path-in-feature', 'A-002'),
        # Each file below holds the cited name as a quoted string, so only the path rule can refuse it.
        ('a sibling feature record is not a test',
         lambda t: (t.write(SIBLING + '/qa/assertions.json', json.dumps({'observable': 'rejects capacity 0 and 9'})),
                    t.edit('A-002', proof=[{'path': SIBLING + '/qa/assertions.json',
                                            'name': 'rejects capacity 0 and 9'}])),
         'proof-path-in-feature', 'A-002'),
        ('a project document is not a test',
         lambda t: (t.write('docs/testing-notes.md', 'Covered by `rejects capacity 0 and 9`.\n'),
                    t.edit('A-002', proof=[{'path': 'docs/testing-notes.md', 'name': 'rejects capacity 0 and 9'}])),
         'proof-path-not-test', 'A-002'),
        ('JSON data is not a test',
         lambda t: (t.write('tests/data/capacity.json', json.dumps({'title': 'rejects capacity 0 and 9'})),
                    t.edit('A-002', proof=[{'path': 'tests/data/capacity.json', 'name': 'rejects capacity 0 and 9'}])),
         'proof-path-not-test', 'A-002'),
        ('project governance is not a test, whatever its suffix',
         lambda t: (t.write('.specify/memory/qa-rules.yml', 'name: "rejects capacity 0 and 9"\n'),
                    t.edit('A-002', proof=[{'path': '.specify/memory/qa-rules.yml',
                                            'name': 'rejects capacity 0 and 9'}])),
         'proof-path-not-test', 'A-002'),
        ('requirement absent from spec.md', lambda t: t.edit('A-002', requirement='FR-099'),
         'requirement-unknown', 'A-002'),
        ('requirement matched only as a prefix', lambda t: t.edit('A-002', requirement='FR-00'),
         'requirement-unknown', 'A-002'),
        ('duplicate id', lambda t: t.copy_row('A-002', observable='Capacity 9 is rejected'),
         'assertion-duplicate-id', 'A-002'),
        ('duplicate identity under a new id',
         lambda t: t.copy_row('A-002', id='A-005', observable='  capacity OUTSIDE 1 to 8   is rejected '),
         'assertion-duplicate-identity', 'A-005'),
        ('extend without a task', lambda t: t.edit('A-003', tasks=[]), 'task-required', 'A-003'),
        ('add without a task', lambda t: t.edit('A-001', tasks=[]), 'task-required', 'A-001'),
        ('add links a task that does not exist', lambda t: t.edit('A-001', tasks=['T099']), 'task-unknown', 'A-001'),
        ('a task id mentioned only in prose is not a task',
         lambda t: (t.append(TASKS, '\nFollow-up T010 is tracked separately.\n'), t.edit('A-001', tasks=['T010'])),
         'task-unknown', 'A-001'),
        ('add while citing existing proof',
         lambda t: t.edit('A-001', proof=[{'path': UNIT, 'name': 'accepts a non-overlapping period'}]),
         'add-with-proof', 'A-001'),
        ('not-applicable with no reason or basis', lambda t: t.edit('A-004', reason=None, basis=None),
         'na-unsupported', 'A-004'),
        ('not-applicable citing text its source does not contain',
         lambda t: t.edit('A-004', basis={'source': SPEC, 'cite': 'Mobile is planned for a later release'}),
         'na-unsupported', 'A-004'),
        ('not-applicable basis outside the project',
         lambda t: t.edit('A-004', basis={'source': '../outside/notes.md',
                                          'cite': 'Mobile is planned for a later release'}),
         'na-unsupported', 'A-004'),
        ('not-applicable justified by budget', lambda t: t.edit('A-004', reason='Too slow for the CI budget'),
         'na-waiver', 'A-004'),
        ('not-applicable justified by test count',
         lambda t: t.edit('A-004', reason='Skipped to keep the test count down'), 'na-waiver', 'A-004'),
        ('not-applicable justified by runtime', lambda t: t.edit('A-004', reason='Adds too much suite runtime'),
         'na-waiver', 'A-004'),
        ('not-applicable that still links a task', lambda t: t.edit('A-004', tasks=['T004']),
         'na-has-proof-or-tasks', 'A-004'),
        ('fixture evidence for a real boundary', lambda t: t.edit('A-003', evidence='fixture'),
         'real-boundary-evidence', 'A-003'),
        ('emulated evidence for a real boundary', lambda t: t.edit('A-003', evidence='emulated'),
         'real-boundary-evidence', 'A-003'),
        ('required field missing', lambda t: t.edit('A-002', risk=None), 'field-missing', 'A-002'),
        ('enum value outside the contract', lambda t: t.edit('A-002', risk='high'), 'field-invalid', 'A-002'),
        ('qa-prepare task cites no assertion', lambda t: t.replace(TASKS, '(covers A-001; ', '('),
         'block-task-uncovered', 'T004'),
        ('qa-prepare task cites an unknown assertion', lambda t: t.replace(TASKS, 'covers A-001;', 'covers A-404;'),
         'block-task-uncovered', 'T004'),
        ('record missing', lambda t: (t.root / RECORD).unlink(), 'readiness-missing', None),
        ('record is not JSON', lambda t: t.write(RECORD, '{'), 'readiness-invalid-json', None),
        ('unknown schema', lambda t: t.save({**t.doc(), 'schema': 'assure-readiness/0'}), 'schema-unsupported', None),
        ('no assertions', lambda t: t.save({**t.doc(), 'assertions': []}), 'assertions-empty', None),
    ]

    ACCEPTED = [
        ('baseline', lambda t: None),
        # The validator carries no generic matrix: a consumer-defined context or exception id is free text.
        ('consumer-defined context', lambda t: t.edit('A-001', context='consumer-exception-X-01')),
        ('the consumer policy file is the basis',
         lambda t: t.edit('A-004', basis={'source': 'docs/qa-policy.md',
                                          'cite': 'Mobile clients are not a supported surface'})),
        # No declared mobile surface: nothing requires a mobile row at all.
        ('no mobile assertion', lambda t: t.drop_row('A-004')),
        ('a ticked task still links', lambda t: t.replace(TASKS, '- [ ] T004', '- [x] T004')),
        ('a normalised in-project path',
         lambda t: t.edit('A-002', proof=[{'path': 'tests/unit/../unit/period_rules.spec.ts',
                                           'name': 'rejects capacity 0 and 9'}])),
        ('a YAML runner flow is a test',
         lambda t: (t.write('tests/flows/capacity.flow.yaml', YAML_FLOW),
                    t.edit('A-002', proof=[{'path': 'tests/flows/capacity.flow.yaml',
                                            'name': 'capacity editor rejects 9'}]))),
        # Product terms that share a word with test economy stay legitimate when a real basis supports them.
        ('a reduced-motion exception from the policy',
         lambda t: (t.append(SPEC, '- **FR-005**: Period changes animate unless reduced motion is on.\n'),
                    t.append(POLICY, '\nReduced-motion coverage is not required for this project.\n'),
                    t.copy_row('A-004', id='A-005', requirement='FR-005',
                               observable='Period animations respect reduced motion',
                               reason='Reduced-motion coverage is not required by the QA policy',
                               basis={'source': POLICY, 'cite': 'Reduced-motion coverage is not required'}))),
        ('a budget export outside this feature',
         lambda t: (t.append(SPEC, '- **FR-006**: The budget export is out of scope; a later feature ships it.\n'),
                    t.copy_row('A-004', id='A-006', requirement='FR-006',
                               observable='The budget export downloads a CSV file',
                               reason='The budget export is out of scope',
                               basis={'source': SPEC, 'cite': 'The budget export is out of scope'}))),
        ('a cut-over owned by another feature',
         lambda t: (t.append(SPEC, '- **FR-007**: The migration feature owns the cut-over from the previous '
                                   'scheduler.\n'),
                    t.copy_row('A-004', id='A-007', requirement='FR-007',
                               observable='Existing periods move to the new scheduler',
                               reason='Cut-over tests belong to the migration feature',
                               basis={'source': SPEC, 'cite': 'The migration feature owns the cut-over'}))),
    ]

    def test_each_mechanical_rule_rejects_its_case(self):
        for case, mutate, code, assertion in self.REJECTED:
            with self.subTest(case):
                self.setUp()
                mutate(self)
                exit_code, result = self.check()
                self.assertEqual(exit_code, 1, result)
                self.assertRejected(result, assertion, code)
                self.assertEqual(result['semantic'], 'not-verified')

    def test_well_formed_records_pass_without_a_semantic_claim(self):
        for case, mutate in self.ACCEPTED:
            with self.subTest(case):
                self.setUp()
                mutate(self)
                exit_code, result = self.check()
                self.assertEqual((exit_code, result['ok'], result['errors']), (0, True, []), result)
                self.assertEqual(result['semantic'], 'not-verified')

    def test_already_proven_assertion_reuses_its_cited_test_without_a_task(self):
        exit_code, result = self.check()
        self.assertEqual(exit_code, 0, result)
        reuse = next(r for r in self.doc()['assertions'] if r['id'] == 'A-002')
        self.assertEqual((reuse['disposition'], reuse['tasks']), ('reuse', []))
        block = re.search(r'<!-- qa-prepare:start -->(.*?)<!-- qa-prepare:end -->', self.read(TASKS), re.S).group(1)
        self.assertNotRegex(block, r'(?<![\w-])A-002(?![\w-])')

    def test_a_symlinked_proof_cannot_escape_the_project(self):
        link = self.root / 'tests/unit/linked.spec.ts'
        try:
            os.symlink(self.outside / 'period_rules.spec.ts', link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f'symbolic links unavailable: {exc}')
        self.edit('A-002', proof=[{'path': 'tests/unit/linked.spec.ts', 'name': 'rejects capacity 0 and 9'}])
        exit_code, result = self.check()
        self.assertEqual(exit_code, 1, result)
        self.assertRejected(result, 'A-002', 'proof-path-outside-root')

    def test_check_output_is_stable_across_reruns(self):
        first, second = self.invoke(READINESS, 'check', '--feature', FEATURE, '--repo-root', str(self.root)), \
            self.invoke(READINESS, 'check', '--feature', FEATURE, '--repo-root', str(self.root))
        self.assertEqual((first.returncode, first.stdout), (second.returncode, second.stdout))
        self.assertTrue(first.stdout.startswith('ok assertions=4'), first.stdout)


class ProofAndTaskIdentityTest(ReadinessFixture, unittest.TestCase):
    """Approved rules the record must enforce for a gap to stay visible: false reuse, waived critical risk and
    tasks that are not QA gap tasks."""

    def test_a_critical_assertion_cannot_be_waived_for_test_economy(self):
        # plan.md says "Minimise tests"; quoting it must not make a critical revocation readback not applicable.
        basis = {'source': FEATURE + '/plan.md', 'cite': 'Minimise tests'}
        for reason in ('Minimise tests: the plan asks for the smallest suite',
                       'Minimize the suite for this release',
                       'Keeps CI inside the runtime budget',
                       'The plan settles this'):  # the economy is only in the quoted basis
            with self.subTest(reason):
                self.setUp()
                self.edit('A-003', disposition='not-applicable', proof=[], tasks=[], reason=reason, basis=basis)
                self.replace(TASKS, '(covers A-003; owner layer native)', '(covers A-001)')
                exit_code, result = self.check()
                self.assertEqual(exit_code, 1, result)
                self.assertRejected(result, 'A-003')

    def test_proof_name_must_be_a_whole_test_identity(self):
        # The file has `test('accepts a non-overlapping period')` and a TODO comment; neither proves rejection.
        for name in ('overlapping period', 'rejects an overlapping period'):
            with self.subTest(name):
                self.setUp()
                self.edit('A-001', disposition='reuse', tasks=[], proof=[{'path': UNIT, 'name': name}])
                self.replace(TASKS, 'covers A-001;', 'covers A-003;')  # only the proof rule can name A-001
                exit_code, result = self.check()
                self.assertEqual(exit_code, 1, result)
                self.assertRejected(result, 'A-001')

    def test_a_user_manual_task_is_not_a_qa_task(self):
        # Analyze freshness ignores the User Manual block, so readiness cannot depend on a task inside it.
        self.append(TASKS, MANUAL_BLOCK)
        self.edit('A-001', tasks=['T090'])
        exit_code, result = self.check()
        self.assertEqual(exit_code, 1, result)
        self.assertRejected(result, 'A-001')

    def test_a_qa_prepare_task_must_cover_an_add_or_extend_gap(self):
        for ident in ('A-002', 'A-004'):  # reuse, not-applicable
            with self.subTest(ident):
                self.setUp()
                self.replace(TASKS, '<!-- qa-prepare:end -->',
                             f'- [ ] T006 [US2] Add a capacity bound E2E test (covers {ident})\n\n<!-- qa-prepare:end -->')
                exit_code, result = self.check()
                self.assertEqual(exit_code, 1, result)
                self.assertTrue({'T006', ident} & {a for _, a in self.found(result)}, result)


class AnalyzeRecordTest(ReadinessFixture, unittest.TestCase):
    def test_record_binds_the_contract_and_tracks_the_proof(self):
        exit_code, result = self.state('record')
        self.assertEqual(exit_code, 0, result)
        self.assertEqual((result['current'], result['contract']), (True, 2), result)
        saved = json.loads(self.read(STATE_FILE))
        self.assertEqual((saved['assureContract'], saved['readiness']), (2, RECORD))
        self.assertLessEqual({TASKS, RECORD, UNIT, NATIVE}, set(saved['outputs']))
        exit_code, status = self.state('status', '--json')
        self.assertEqual((exit_code, status['current'], status['reason'], status['contract']),
                         (0, True, 'current', 2), status)

    def test_an_unchanged_rerun_is_byte_identical_and_current(self):
        self.assertEqual(self.state('record')[0], 0)
        first = self.state_bytes()
        self.assertEqual(self.state('record')[0], 0)
        self.assertEqual(self.state_bytes(), first)
        exit_code, line = self.state('status', '--summary')
        self.assertEqual(exit_code, 0, line)
        self.assertTrue(line.startswith('ok action=status kind=analyze'), line)

    def test_an_invalid_or_missing_record_refuses_and_writes_nothing(self):
        cases = [
            ('real gap hidden by bogus proof',
             lambda: self.edit('A-001', disposition='reuse', tasks=[],
                               proof=[{'path': UNIT, 'name': 'rejects a reversed period'}]),
             'proof-name-not-found', 'A-001'),
            ('no readiness record', lambda: (self.root / RECORD).unlink(), 'readiness-missing', None),
        ]
        for case, mutate, code, assertion in cases:
            with self.subTest(case):
                self.setUp()
                mutate()
                exit_code, result = self.state('record')
                self.assertEqual(exit_code, 1, result)
                self.assertEqual(result['reason'], 'readiness-invalid', result)
                self.assertIn((code, assertion), self.found(result), result)
                self.assertIsNone(self.state_bytes())

    def test_the_report_only_check_never_records(self):
        exit_code, result = self.check()
        self.assertEqual(exit_code, 0, result)
        self.assertFalse((self.root / '.specify').exists())

    def test_changes_after_record(self):
        stale = [
            ('a cited proof file changes', lambda: self.append(UNIT, '\n// edited\n'), 'changed_outputs', UNIT),
            ('a cited proof file is deleted', lambda: (self.root / UNIT).unlink(), 'changed_outputs', UNIT),
            ('spec.md changes', lambda: self.append(SPEC, '\n- **FR-005**: New rule.\n'), 'changed_inputs', SPEC),
            ('the readiness record changes', lambda: self.edit('A-002', observable='Capacity 0 is rejected'),
             'changed_outputs', RECORD),
            ('a QA task changes', lambda: self.replace(TASKS, 'Add the overlap', 'Add an overlap'),
             'changed_outputs', TASKS),
            ('a new file in the feature', lambda: self.write(FEATURE + '/notes.md', 'note\n'),
             'changed_inputs', FEATURE + '/notes.md'),
            # (..., prepare before record): the cited exception is removed from a policy outside the feature.
            ('a not-applicable basis outside the feature changes',
             lambda: self.replace(POLICY, 'Mobile clients are not a supported surface.', 'Mobile clients are planned.'),
             'changed_outputs', POLICY,
             lambda: self.edit('A-004', basis={'source': POLICY,
                                               'cite': 'Mobile clients are not a supported surface'})),
        ]
        current = [
            ('an unrelated file outside the feature', lambda: self.append('README.md', 'more\n')),
            ('the User Manual block is added', lambda: self.append(TASKS, MANUAL_BLOCK)),
            ('a checkbox is ticked', lambda: self.replace(TASKS, '- [ ] T001', '- [x] T001')),
            ('a report under the state folder',
             lambda: self.write('.specify/extensions/assure/state/001-period-rules/reports/analyze.log', 'log\n')),
        ]
        for case, mutate, field, path, *prepare in stale:
            with self.subTest(case):
                self.setUp()
                for step in prepare:
                    step()
                self.assertEqual(self.state('record')[0], 0)
                mutate()
                exit_code, status = self.state('status', '--json')
                self.assertEqual((exit_code, status['reason']), (1, 'stale-input-or-output'), status)
                self.assertIn(path, status[field], status)
        for case, mutate in current:
            with self.subTest(case):
                self.setUp()
                self.assertEqual(self.state('record')[0], 0)
                mutate()
                exit_code, status = self.state('status', '--json')
                self.assertEqual((exit_code, status['current']), (0, True), status)


class HistoricalStateTest(ReadinessFixture, unittest.TestCase):
    """A state recorded before the readiness contract stays as recorded and asks for a new analysis."""

    def legacy_record(self):
        sanduq_freshness.record_or_status(self.root, self.root / FEATURE, 'analyze', STATE_FILE, 'record', [TASKS])
        return self.state_bytes()

    def test_a_historical_state_is_reported_not_rewritten(self):
        before = self.legacy_record()
        for legacy_current in (True, False):
            with self.subTest(legacy_current=legacy_current):
                if not legacy_current:
                    self.append(SPEC, '\n- **FR-005**: New rule.\n')
                exit_code, status = self.state('status', '--json')
                self.assertEqual(exit_code, 1, status)
                self.assertEqual((status['current'], status['reason'], status['contract'], status['legacy_current']),
                                 (False, 'needs-reanalysis', 1, legacy_current), status)
                self.assertEqual(self.state_bytes(), before)

    def test_a_historical_state_moves_forward_only_through_a_valid_record(self):
        before = self.legacy_record()
        valid = self.read(RECORD)
        self.edit('A-003', evidence='fixture')
        exit_code, result = self.state('record')
        self.assertEqual((exit_code, result['reason']), (1, 'readiness-invalid'), result)
        self.assertEqual(self.state_bytes(), before)
        self.write(RECORD, valid)
        self.assertEqual(self.state('record')[0], 0)
        exit_code, status = self.state('status', '--json')
        self.assertEqual((exit_code, status['contract']), (0, 2), status)

    def test_a_contract_state_without_its_readiness_binding_needs_reanalysis(self):
        self.assertEqual(self.state('record')[0], 0)
        saved = json.loads(self.read(STATE_FILE))
        del saved['readiness']
        self.write(STATE_FILE, json.dumps(saved, indent=2) + '\n')
        exit_code, status = self.state('status', '--json')
        self.assertEqual((exit_code, status['reason']), (1, 'needs-reanalysis'), status)

    def test_a_schema_one_state_still_asks_for_regeneration(self):
        self.write(STATE_FILE, json.dumps({'schemaVersion': 1}) + '\n')
        exit_code, status = self.state('status', '--json')
        self.assertEqual((exit_code, status['reason']), (1, 'legacy-state-regenerate'), status)

    def test_the_document_kind_needs_no_readiness_record(self):
        (self.root / RECORD).unlink()
        self.write('docs/001-period-rules/QA.md', 'Evidence\n')
        args = ('--kind', 'document', '--feature', FEATURE, '--repo-root', str(self.root), '--base-ref', 'HEAD',
                '--output', 'docs/001-period-rules/QA.md')
        record = self.invoke(STATE, 'record', *args)
        self.assertEqual(record.returncode, 0, record.stdout + record.stderr)
        saved = json.loads(self.read('.specify/extensions/assure/state/001-period-rules-document.json'))
        self.assertNotIn('assureContract', saved)
        status = self.invoke(STATE, 'status', *args)
        self.assertEqual(status.returncode, 0, status.stdout)


COMMANDS = EXTENSION / 'commands'
SKILL = EXTENSION / 'skills/assure'
GUIDANCE = {'analyze': COMMANDS / 'speckit.assure.analyze.md', 'document': COMMANDS / 'speckit.assure.document.md',
            'analysis': SKILL / 'references/analysis.md', 'documentation': SKILL / 'references/documentation.md',
            'skill': SKILL / 'SKILL.ext.md'}
QUALIFIED = re.compile(r'\b(not|never|no|only|instead|rather|unless|without|requirements?|references?|named?|'
                       r'declare[ds]?)\b', re.I)
BLANKET_CAPTURE = re.compile(r'\b(screenshots?|captures?)\b.*\b(each|every|all)\b.*\b(screens?|states?|forms?|'
                             r'dialogs?|pages?)\b|\b(each|every|all)\b.*\b(screens?|states?)\b.*\b(screenshots?|'
                             r'captures?)\b', re.I)
MOBILE_CONDITION = re.compile(r'\b(declare[ds]?|declaring|names?|named|unless|not|never|no)\b', re.I)
HARDCODED_MATRIX = re.compile(r'\b\d{3,4}\s*[x×]\s*\d{3,4}\b|\b\d{3}\s?%')


def text(name):
    return GUIDANCE[name].read_text(encoding='utf-8')


def blocks(source):
    """Bullets, numbered items, headings and paragraphs, wrapped lines joined."""
    return [' '.join(b.split()) for b in re.split(r'\n\s*\n|\n(?=\s*(?:[-*]|\d+\.|#+)\s)', source) if b.strip()]


def sentences(source):
    for block in blocks(source):
        yield from filter(None, re.split(r'(?<=[.;])\s+', block))


class GuidanceTest(unittest.TestCase):
    """Prompt guidance is checked by structure and forbidden patterns, never by pinned sentences."""

    def test_no_stage_demands_a_screenshot_for_every_state(self):
        for name in GUIDANCE:
            for sentence in sentences(text(name)):
                if BLANKET_CAPTURE.search(sentence):
                    with self.subTest(name, sentence=sentence[:80]):
                        self.assertRegex(sentence, QUALIFIED)

    def test_mobile_e2e_is_conditional_on_a_declared_surface(self):
        for name in ('analyze', 'analysis'):
            for sentence in sentences(text(name)):
                if re.search(r'\bmobile\b', sentence, re.I) and re.search(r'\bE2E\b', sentence, re.I):
                    with self.subTest(name, sentence=sentence[:80]):
                        self.assertRegex(sentence, MOBILE_CONDITION)

    def test_no_stage_hardcodes_a_context_matrix(self):
        for name in GUIDANCE:
            with self.subTest(name):
                self.assertIsNone(HARDCODED_MATRIX.search(text(name)))

    def test_analyze_reads_policy_dimensions_and_exceptions_from_the_project(self):
        self.assertTrue(any(re.search(r'\bpolic(y|ies)\b', b, re.I)
                            and re.search(r'\b(dimensions?|exceptions?)\b', b, re.I) for b in blocks(text('analyze'))))

    def test_analyze_validates_the_readiness_record_before_recording(self):
        analyze = text('analyze')
        self.assertIn('qa/assertions.json', analyze)
        self.assertIn('qa/assertions.json', text('analysis'))
        self.assertLess(analyze.index('assure_readiness.py check'),
                        analyze.index('assure_state.py record --kind analyze'))

    def test_report_only_never_records(self):
        self.assertTrue(any('--report-only' in s and re.search(r'\brecord\b', s, re.I)
                            and re.search(r'\b(not|never|no)\b', s, re.I) for s in sentences(text('analyze'))))

    def test_critical_risk_survives_a_test_budget(self):
        source = text('analyze') + '\n\n' + text('analysis')
        self.assertTrue(any(re.search(r'\bcritical\b', s, re.I)
                            and re.search(r'\b(budget|count|runtime|minimi[sz]e\w*|fewer)\b', s, re.I)
                            and re.search(r'\b(not|never|no|cannot)\b', s, re.I)
                            for s in sentences(source)))


if __name__ == '__main__':
    unittest.main()
