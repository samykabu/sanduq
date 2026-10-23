"""Early blockers, independent inputs, bounded inspection and byte-exact blob regressions."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_archive as fixture
import test_archive_v2 as fixture_v2
from repo_template import TemplateRepo
from archive import ArchiveError, POLICY
from git_state import digest, write_json
import bounded_json
from memory import inventory


class MemoryToolingTests(unittest.TestCase):
    setUp = fixture.ArchiveIntegrationTests.setUp
    git = fixture.ArchiveIntegrationTests.git
    write = fixture.ArchiveIntegrationTests.write
    prepare = fixture.ArchiveIntegrationTests.prepare
    candidate = fixture.ArchiveIntegrationTests.candidate
    save_candidate = fixture.ArchiveIntegrationTests.save_candidate

    def sentinel(self):
        self.archive.policy['checks']['consumer']['argv'] = [
            '{python}', '-c', "from pathlib import Path; Path('sentinel').write_text('ran', encoding='utf-8')"]

    def declaration(self):
        self.archive.policy['checks']['consumer']['inputs'] = {
            'schema_version': 1, 'complete': True, 'files': ['tests/consumer.py', 'config.json', 'shared.py'],
            'directories': ['src'], 'environment': ['MEMORY_TEST_PROFILE'], 'unresolved': []}
        self.write('config.json', '{}')
        self.write('shared.py', 'original')

    def test_coverage_missing_inputs_and_branch_config_stop_before_sentinel(self):
        self.sentinel()
        baseline = copy.deepcopy(self.archive.policy)
        for update, error in (({'covers': []}, 'covers repaired consumer'),
                              ({'references': ['missing-checker.py']}, 'missing'),
                              ({'required_branch': 'feature-only'}, 'retiring branch'),
                              ({'required_args': ['--needed']}, 'required argument'),
                              ({'argv': ['{python}', '-m']}, 'argument missing')):
            self.archive.policy = copy.deepcopy(baseline)
            self.archive.policy['checks']['consumer'].update(update)
            with self.assertRaisesRegex(ArchiveError, error):
                self.archive.verify(fixture.FEATURE, ['consumer'])
            self.assertFalse((self.root / 'sentinel').exists())
        self.archive.policy = baseline
        self.write('app-config.json', '{"branch":"feature-only"}')
        self.archive.policy['project_checks'] = [{'path': 'app-config.json', 'json_pointer': '/branch', 'equals': '{target_branch}'}]
        with self.assertRaisesRegex(ArchiveError, 'configuration assumption'):
            self.archive.verify(fixture.FEATURE, ['consumer'])
        self.assertFalse((self.root / 'sentinel').exists())

    def test_missing_declared_input_and_ignored_untracked_source_stop_early(self):
        self.sentinel()
        self.declaration()
        (self.root / 'config.json').unlink()
        with self.assertRaisesRegex(ArchiveError, 'input missing'):
            self.archive.verify(fixture.FEATURE, ['consumer'])
        self.archive.policy['checks']['consumer'].pop('inputs')
        self.write('.gitignore', fixture.FEATURE + '/untracked.json\n')
        self.write(fixture.FEATURE + '/untracked.json', 'unrecoverable evidence')
        with self.assertRaisesRegex(ArchiveError, 'Ignored artifacts'):
            self.archive.verify(fixture.FEATURE, ['consumer'])
        self.assertFalse((self.root / 'sentinel').exists())

    def test_predicted_ignored_output_stops_before_checkpoint_or_sentinel(self):
        self.sentinel()
        self.write('.gitignore', 'specs/project-memory.md\n')
        with patch.object(self.archive.repo, 'commit', side_effect=AssertionError('checkpoint ran')):
            with self.assertRaisesRegex(ArchiveError, 'output would be ignored'):
                self.archive.verify(fixture.FEATURE, ['consumer'])
        self.assertFalse((self.root / 'sentinel').exists())

    def test_precritique_repairs_and_migrations_work_in_format_one(self):
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        (self.archive.run_path(prepared['run_id']) / 'review.json').unlink()
        run = self.archive.journal(prepared['run_id'])
        result = self.archive.preflight(run['specs'], run['checks'], run=run)
        self.assertEqual(result['candidate_guards'], 'passed')
        self.assertEqual(result['review']['status'], 'missing')
        with self.assertRaisesRegex(ArchiveError, 'critique'):
            self.archive.validate(run)
        process = subprocess.run(
            [sys.executable, str(fixture.SCRIPTS / 'archive.py'), '--root', str(self.root),
             'validate', '--run', run['run_id']], capture_output=True,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'})
        self.assertEqual(1, process.returncode, process.stdout.decode('utf-8'))
        self.assertIn('critique', json.loads(process.stdout)['error'])
        candidate['repairs'][0]['replacements'][0]['count'] = 99
        write_json(self.archive.run_path(run['run_id']) / 'candidate.json', candidate)
        with self.assertRaisesRegex(ArchiveError, 'context/count'):
            self.archive.preflight(run['specs'], run['checks'], run=run)

    def test_historical_prose_and_immutable_cites_do_not_create_branch_blockers(self):
        self.write('history.md', 'Old branch feature-only. git:' + self.archive.repo.head() + ':' + fixture.CONTRACT)
        self.git('add', 'history.md')
        self.git('commit', '-m', 'History')
        result = self.archive.preflight([fixture.FEATURE], ['consumer'])
        self.assertNotIn('history.md', [r['path'] for r in result['references']])
        self.assertEqual(result['candidate_guards'], 'pending')

    def test_complete_inputs_reuse_and_checker_shared_config_env_discovery_invalidate(self):
        self.declaration()
        first = self.archive.run_checks(['consumer'])[0]
        proof = Path(first['receipt']).read_bytes()
        self.assertEqual(self.archive.run_checks(['consumer'])[0]['status'], 'reused')
        for label in ('tests/consumer.py', 'shared.py', 'config.json'):
            path = self.root / label
            original = path.read_bytes()
            path.write_bytes(original + b'\n')
            self.assertEqual(self.archive.run_checks(['consumer'])[0]['reuse_status'], 'invalidated')
            path.write_bytes(original)
            self.archive.run_checks(['consumer'])
        with patch.dict(os.environ, {'MEMORY_TEST_PROFILE': 'private-value'}):
            changed = self.archive.run_checks(['consumer'])[0]
            self.assertEqual(changed['reuse_status'], 'invalidated')
            self.assertNotIn('private-value', Path(changed['receipt']).read_text(encoding='utf-8'))
        self.write('src/discovered.py', '# new')
        self.assertEqual(self.archive.run_checks(['consumer'])[0]['reuse_status'], 'invalidated')
        self.assertEqual(Path(first['receipt']).read_bytes(), proof)

    def test_unknown_legacy_tampered_and_missing_proofs_execute_append_only(self):
        first = self.archive.run_checks(['consumer'])[0]
        second = self.archive.run_checks(['consumer'])[0]
        self.assertEqual(second['reuse_status'], 'unknown')
        self.assertNotEqual(first['attempt_id'], second['attempt_id'])
        self.declaration()
        for update in ({'files': []}, {'complete': False}, {'unresolved': ['dynamic import']}, {'schema_version': 2}):
            baseline = copy.deepcopy(self.archive.policy['checks']['consumer']['inputs'])
            self.archive.policy['checks']['consumer']['inputs'].update(update)
            self.assertEqual(self.archive.run_checks(['consumer'])[0]['reuse_status'], 'unknown')
            self.archive.policy['checks']['consumer']['inputs'] = baseline
        passed = self.archive.run_checks(['consumer'])[0]
        Path(passed['log']).write_bytes(b'tampered')
        retry = self.archive.run_checks(['consumer'])[0]
        self.assertEqual(retry['reuse_status'], 'invalidated')
        Path(retry['receipt']).unlink()
        self.assertEqual(self.archive.run_checks(['consumer'])[0]['status'], 'executed')
        self.assertTrue(Path(first['receipt']).exists())

    def test_midrun_input_mutation_cannot_make_a_reusable_passing_receipt(self):
        self.declaration()
        self.archive.policy['checks']['consumer']['argv'] = [
            '{python}', '-c', "from pathlib import Path; Path('config.json').write_text('changed', encoding='utf-8')"]
        with self.assertRaisesRegex(ArchiveError, 'changed declared inputs'):
            self.archive.run_checks(['consumer'])
        receipts = list((self.archive.repo.state / 'checks/attempts').glob('*/receipt.json'))
        self.assertEqual(len(receipts), 1)
        self.assertFalse(json.loads(receipts[0].read_text(encoding='utf-8'))['result']['inputs_unchanged'])

    def test_legacy_global_freshness_and_archive_transaction_guards_remain_strict(self):
        self.archive.verify(fixture.FEATURE, ['consumer'])
        self.write('src/app.py', "CURRENCY = 'GBP'\n")
        with self.assertRaisesRegex(ArchiveError, 'stale'):
            self.archive.eligibility(fixture.FEATURE)

    def test_declared_config_and_retained_proofs_guard_completion_and_stale_candidates(self):
        self.declaration()
        self.archive.verify(fixture.FEATURE, ['consumer'])
        prepared = self.archive.prepare([fixture.FEATURE], [], ['consumer'])
        self.candidate(prepared)
        self.write('config.json', '{"changed":true}')
        with self.assertRaisesRegex(ArchiveError, 'Declared check inputs changed'):
            self.archive.finalize(prepared['run_id'])
        self.assertTrue((self.root / fixture.FEATURE).exists())
        self.write('config.json', '{}')
        self.archive.abandon(prepared['run_id'])
        self.archive.verify(fixture.FEATURE, ['consumer'])
        evidence = json.loads(self.archive.evidence_file(fixture.FEATURE).read_text(encoding='utf-8'))
        Path(evidence['checks'][0]['log']).write_bytes(b'tampered proof')
        with self.assertRaisesRegex(ArchiveError, 'Completion proof'):
            self.archive.eligibility(fixture.FEATURE)

    def test_native_inspection_is_valid_json_inside_the_complete_stdout_byte_budget(self):
        prepared = self.prepare()
        self.candidate(prepared)
        for view in ('status', 'checks', 'inventory', 'coverage'):
            result = subprocess.run([sys.executable, str(fixture.SCRIPTS / 'archive.py'), '--root', str(self.root),
                'inspect', '--run', prepared['run_id'], '--view', view, '--max-bytes', '512'], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
            self.assertLessEqual(len(result.stdout), 512)
            self.assertEqual(json.loads(result.stdout)['schema'], 'sanduq.inspection.v1')

    def test_utf8_child_io_and_candidate_guards_ignore_malformed_critique(self):
        self.archive.policy['checks']['consumer']['argv'] = ['{python}', '-c', "print('مرحبا')"]
        with patch.dict(os.environ, {'PYTHONIOENCODING': 'ascii', 'PYTHONUTF8': '0'}):
            result = self.archive.run_checks(['consumer'])[0]
        self.assertIn('مرحبا', Path(result['log']).read_text(encoding='utf-8'))
        prepared = self.prepare()
        self.candidate(prepared)
        run = self.archive.journal(prepared['run_id'])
        (self.archive.run_path(run['run_id']) / 'review.json').write_text('invalid JSON', encoding='utf-8')
        self.assertEqual(self.archive.preflight(run['specs'], run['checks'], run=run)['candidate_guards'], 'passed')
        with self.assertRaisesRegex(ArchiveError, 'critique'):
            self.archive.validate(run)

    def test_bounded_whole_record_projection_and_content_bound_cursor(self):
        records = [{'type': 'unit', 'id': str(i), 'text': 'مرحبا' * 30} for i in range(10)]
        first = bounded_json.page(records, view='inventory', max_bytes=1024)
        self.assertLessEqual(len(bounded_json.encode(first)) + 1, 1024)
        self.assertEqual(first['records'], records[:first['returned']])
        second = bounded_json.page(records, view='inventory', max_bytes=1024, cursor=first['next_cursor'])
        self.assertEqual(second['offset'], first['returned'])
        huge = bounded_json.page([{'type': 'unit', 'text': 'x' * 100000}], view='inventory', max_bytes=512)
        self.assertEqual(huge['returned'], 0)
        self.assertIsNotNone(huge['oversized_record'])
        self.assertLessEqual(len(bounded_json.encode(huge)) + 1, 512)
        with self.assertRaises(ValueError):
            bounded_json.page(records + [{'new': True}], view='inventory', max_bytes=1024, cursor=first['next_cursor'])

    def test_inventory_batches_and_validates_git_blobs_without_changing_units(self):
        for i in range(36):
            self.write(fixture.FEATURE + f'/batch-{i}.txt', f'# {i}\r\n\r\nExact bytes {i}\r\n')
        self.git('add', fixture.FEATURE)
        self.git('commit', '-m', 'Batch inputs')
        files = list(self.archive.spec_files([fixture.FEATURE]))
        head = self.archive.repo.head()
        with patch.object(self.archive.repo, 'git', wraps=self.archive.repo.git) as calls:
            result = inventory(self.archive.repo, head, files)
        batches = [c for c in calls.call_args_list if c.args[:2] == ('cat-file', '--batch')]
        self.assertEqual(len(batches), 2)
        self.assertEqual({u['path'] for u in result}, set(files))
        self.assertEqual(self.archive.repo.blob(head, files[0]), (self.root / files[0]).read_bytes())
        for commit, path in (('HEAD', files[0]), (head, '../escape'), (head, 'missing'), (head, fixture.FEATURE)):
            with self.assertRaises(ArchiveError):
                self.archive.repo.blob(commit, path)
        with self.assertRaisesRegex(ArchiveError, 'byte limit'):
            self.archive.repo.blobs(head, [files[0]], max_blob_bytes=1)
        real = self.archive.repo.git
        def broken(*args, **kwargs):
            value = real(*args, **kwargs)
            return value[:-1] if args[:2] == ('cat-file', '--batch') else value
        with patch.object(self.archive.repo, 'git', side_effect=broken):
            with self.assertRaisesRegex(ArchiveError, 'Truncated'):
                self.archive.repo.blob(head, files[0])


class MemoryV2ToolingTests(TemplateRepo, unittest.TestCase):
    build = fixture_v2.ArchiveV2Tests.build
    restored = fixture_v2.ArchiveV2Tests.restored
    git = fixture_v2.ArchiveV2Tests.git
    write = fixture_v2.ArchiveV2Tests.write
    read = fixture_v2.ArchiveV2Tests.read
    journal = fixture_v2.ArchiveV2Tests.journal
    candidate = fixture_v2.ArchiveV2Tests.candidate
    save = fixture_v2.ArchiveV2Tests.save

    def test_precritique_candidate_guards_and_final_admission_in_format_two(self):
        self.archive.abandon(self.prepared['run_id'])
        self.write('README.md', 'Contract: ' + fixture_v2.SPEC)
        self.git('add', 'README.md')
        self.git('commit', '-m', 'Live reference fixture')
        self.prepared = self.archive.prepare(self.journal()['specs'], [], [], skip_verification=fixture_v2.REASON)
        self.run_dir = self.archive.run_path(self.prepared['run_id'])
        candidate = self.candidate()
        candidate['repairs'] = [{'path': 'README.md', 'replacements': [{'before': fixture_v2.SPEC,
            'after': 'git:' + self.journal()['checkpoint'] + ':' + fixture_v2.SPEC, 'count': 1}]}]
        self.save(candidate, review=False)
        run = self.journal()
        result = self.archive.preflight(run['specs'], run['checks'], run=run, skip_verification=True)
        self.assertEqual(result['candidate_guards'], 'passed')
        self.assertEqual(result['review']['status'], 'missing')
        with self.assertRaisesRegex(ArchiveError, 'critique'):
            self.archive.validate(run)
        candidate = self.candidate()
        candidate['repairs'] = [{'path': 'README.md', 'replacements': [{'before': fixture_v2.SPEC,
            'after': 'git:' + run['checkpoint'] + ':' + fixture_v2.SPEC, 'count': 1}]}]
        candidate['migrations'] = [{'source': fixture_v2.SPEC,
            'destination': 'tests/Fixtures/spec-memory/' + fixture_v2.SPEC.removeprefix('specs/')}]
        self.save(candidate, review=False)
        self.assertEqual(self.archive.preflight(run['specs'], run['checks'], run=run, skip_verification=True)['candidate_guards'], 'passed')
        self.write('.gitignore', 'tests/Fixtures/spec-memory/**\n')
        with self.assertRaisesRegex(ArchiveError, 'output would be ignored'):
            self.archive.preflight(run['specs'], run['checks'], run=run, skip_verification=True)

    def test_all_inspection_views_are_bounded_format_two(self):
        self.save(self.candidate(), review=False)
        for view in ('status', 'checks', 'inventory', 'coverage'):
            result = self.archive.inspect(view, self.prepared['run_id'], max_bytes=1024)
            self.assertLessEqual(len(bounded_json.encode(result)) + 1, 1024)
            self.assertTrue(all('type' in r for r in result['records']))
