"""Approved fixture parents remain compatible with strict discovery freshness."""
from pathlib import Path
import unittest
from unittest.mock import patch

import test_archive as legacy
import test_archive_v2 as delta
from repo_template import TemplateRepo
from archive import ArchiveError, POLICY
from git_state import write_json


class MigrationDiscoveryChecks:
    def declare_discovery(self):
        self.archive.policy['checks']['consumer']['inputs'] = {
            'schema_version': 1, 'complete': True, 'files': ['tests/consumer.py', 'src/app.py'],
            'directories': ['tests', 'specs'], 'environment': [], 'unresolved': []}
        write_json(self.root / POLICY, self.archive.policy)
        self.git('add', '-A')
        self.git('commit', '-m', 'Declare fixture discovery inputs')
        self.assertIsNotNone(self.archive.check_identity('consumer')[0])
        self.before_discovery = self.archive.declared_hashes(['consumer'])
        self.original_fixture = (self.root / self.source).read_bytes()

    def pause_after_publication(self):
        with patch.object(self.archive.repo, 'expected_tree', side_effect=ArchiveError('pause before commit')):
            with self.assertRaisesRegex(ArchiveError, 'pause before commit'):
                self.archive.finalize(self.prepared['run_id'])
        run = self.archive.journal(self.prepared['run_id'])
        self.assertEqual('checking', run['phase'])
        self.assertEqual(self.original_fixture, (self.root / self.destination).read_bytes())
        return run

    def test_finalize_records_exact_new_migration_parents(self):
        expected = set()
        outputs, _ = self.archive.validate(self.archive.journal(self.prepared['run_id']))
        for name, content in outputs.items():
            if content is None:
                continue
            parent = Path(name).parent
            while parent != Path('.'):
                if not (self.root / parent).exists():
                    expected.add(parent.as_posix())
                parent = parent.parent
        result = self.archive.finalize(self.prepared['run_id'])
        self.assertEqual('done', result['phase'])
        run = self.archive.journal(self.prepared['run_id'])
        self.assertEqual(expected, set(run['created_output_directories']))
        self.assertEqual(self.original_fixture, (self.root / self.destination).read_bytes())
        self.assertFalse((self.root / self.source).exists())
        self.assertEqual('', self.git('status', '--short'))

    def test_rollback_restores_discovery_membership_and_can_resume(self):
        run = self.pause_after_publication()
        real_path = self.archive.repo.path
        deepest = max(run['created_output_directories'], key=lambda p: len(p.split('/')))
        # repo.path uses the resolved root; the fixture may retain a Windows 8.3 alias.
        cleanup_target = real_path(deepest).resolve()
        self.assertTrue(cleanup_target.is_dir())
        path_type = type(cleanup_target)
        original_rmdir = path_type.rmdir

        def interrupted(directory):
            if directory.resolve() == cleanup_target:
                raise OSError('directory cleanup interrupted')
            return original_rmdir(directory)

        with patch.object(path_type, 'rmdir', interrupted):
            with self.assertRaisesRegex(OSError, 'directory cleanup interrupted'):
                self.archive.rollback(run['run_id'])
        self.assertEqual('rolling-back', self.archive.journal(run['run_id'])['phase'])
        self.assertTrue(cleanup_target.is_dir())
        self.assertEqual('rolled-back', self.archive.rollback(run['run_id'])['phase'])
        self.assertEqual(self.before_discovery, self.archive.declared_hashes(['consumer']))
        self.assertEqual(self.original_fixture, real_path(self.source).read_bytes())
        self.assertFalse(real_path(self.destination).exists())
        self.assertEqual('', self.git('status', '--short'))

    def test_unrelated_discovery_file_and_directory_block_finalize_and_rollback(self):
        run = self.pause_after_publication()
        for kind in ('file', 'directory'):
            with self.subTest(kind=kind):
                extra = (self.root / self.destination).parent / ('unrelated-' + kind)
                if kind == 'file':
                    extra.write_bytes(b'owner work')
                else:
                    extra.mkdir()
                error = ('Implementation evidence changed during publication' if kind == 'file'
                         else 'Declared input changed during publication')
                for action in (self.archive.finalize, self.archive.rollback):
                    with self.assertRaisesRegex(ArchiveError, error):
                        action(run['run_id'])
                    self.assertTrue(extra.exists())
                    self.assertEqual('checking', self.archive.journal(run['run_id'])['phase'])
                    self.assertEqual(self.original_fixture, (self.root / self.destination).read_bytes())
                if kind == 'file':
                    self.assertEqual(b'owner work', extra.read_bytes())
                    extra.unlink()
                else:
                    extra.rmdir()
        self.assertEqual('rolled-back', self.archive.rollback(run['run_id'])['phase'])
        self.assertEqual(self.before_discovery, self.archive.declared_hashes(['consumer']))

    def test_output_parent_admission_validates_paths_and_excludes_deletions(self):
        for name in ('../outside/file', 'tests//noncanonical/file', '.git/objects/file'):
            with self.subTest(name=name), self.assertRaises(ArchiveError):
                self.archive.output_parents({name: 'approved-hash'})
        self.assertEqual(set(), self.archive.output_parents({'tests/deleted/file': None}))
        linked = self.root / 'linked-fixtures'
        try:
            linked.symlink_to(self.root / 'tests', target_is_directory=True)
        except OSError:
            return  # Windows may require symlink privileges; path assertions still ran.
        with self.assertRaisesRegex(ArchiveError, 'links'):
            self.archive.output_parents({'linked-fixtures/nested/file': 'approved-hash'})


class LegacyMigrationDiscoveryTests(MigrationDiscoveryChecks, unittest.TestCase):
    git = legacy.ArchiveIntegrationTests.git
    write = legacy.ArchiveIntegrationTests.write

    def setUp(self):
        legacy.ArchiveIntegrationTests.setUp(self)
        self.source, self.destination = legacy.CONTRACT, legacy.FIXTURE
        self.declare_discovery()
        self.prepared = legacy.ArchiveIntegrationTests.prepare(self)
        legacy.ArchiveIntegrationTests.candidate(self, self.prepared)

    save_candidate = legacy.ArchiveIntegrationTests.save_candidate


class DeltaMigrationDiscoveryTests(TemplateRepo, MigrationDiscoveryChecks, unittest.TestCase):
    git = delta.ArchiveV2Tests.git
    write = delta.ArchiveV2Tests.write
    read = delta.ArchiveV2Tests.read
    journal = delta.ArchiveV2Tests.journal
    build = delta.ArchiveV2Tests.build

    def restored(self):
        delta.ArchiveV2Tests.restored(self)
        self.archive.abandon(self.prepared['run_id'])
        self.source = delta.SPEC
        self.destination = 'tests/Fixtures/spec-memory/' + self.source.removeprefix('specs/')
        self.write('tests/consumer.py', "from pathlib import Path\nassert Path('src/app.py').is_file()\n")
        self.archive.policy['checks']['consumer'] = {
            'argv': ['{python}', 'tests/consumer.py'], 'covers': ['src/*', 'tests/*'], 'timeout_seconds': 20}
        self.declare_discovery()
        self.archive.verify(delta.FEATURE, ['consumer'])
        self.prepared = self.archive.prepare([delta.FEATURE], [], ['consumer'])
        self.run_dir = self.archive.run_path(self.prepared['run_id'])
        candidate = delta.ArchiveV2Tests.candidate(self)
        candidate['migrations'] = [{'source': self.source, 'destination': self.destination}]
        delta.ArchiveV2Tests.save(self, candidate)
