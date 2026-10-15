"""Regression tests for the cycle-4 review findings: safe, lossless migration of host snapshots to `.host`."""
import json
import os
import subprocess
import shutil
import unittest
from unittest import mock

import helpers  # noqa: F401  (sets sys.path)
from sanduq_progress import snapshot
from test_review_c1 import can_symlink
from test_review_c3 import Children


class C4Migration(Children):
    def legacy_setup(self):
        self.setup_children('agent-a')
        legacy = self.ctx.view / 'host'
        shutil.move(str(self.ctx.host_dir), str(legacy))
        return legacy

    def test_a_linked_legacy_directory_is_left_alone(self):
        if not can_symlink():
            self.skipTest('cannot create symlinks')
        legacy = self.legacy_setup()
        outside = self.root / 'outside'
        shutil.move(str(legacy), str(outside))
        os.symlink(outside, legacy, target_is_directory=True)
        self.assertFalse(snapshot.migrate_host_dir(self.ctx))
        self.assertFalse(snapshot.merge(self.ctx, 'claude', 'claude-sess-1', __import__('test_review_c1').stamp('2026-10-15T12:09:00Z')))
        self.assertTrue(legacy.is_symlink())
        self.assertEqual(len(list(outside.glob('*.json'))), 1)
        self.assertFalse(self.ctx.host_dir.exists())
        self.assertIn('migration skipped', self.ctx.diag.read_text(encoding='utf-8'))

    def test_a_linked_entry_inside_the_legacy_directory_is_left_alone(self):
        if not can_symlink():
            self.skipTest('cannot create symlinks')
        legacy = self.legacy_setup()
        target = self.root / 'elsewhere.json'
        target.write_text('{}', encoding='utf-8')
        os.symlink(target, legacy / 'x.json')
        self.assertFalse(snapshot.migrate_host_dir(self.ctx))
        self.assertTrue((legacy / 'x.json').is_symlink())
        self.assertTrue(target.exists())

    def test_a_failed_move_keeps_identity_and_retries(self):
        legacy = self.legacy_setup()
        real = os.replace
        with mock.patch('sanduq_progress.snapshot.os.replace', side_effect=PermissionError('sharing violation')):
            self.assertFalse(snapshot.migrate_host_dir(self.ctx))
            self.assertFalse(snapshot.merge(self.ctx, 'claude', 'claude-sess-2', __import__('test_review_c1').stamp('2026-10-15T12:09:00Z'),
                                            child={'key': 'agent-b', 'by_agent': False, 'update': {'kind': 'subagent', 'status': 'running', 'agent_id': 'agent-b', 'last_observed_at': '2026-10-15T12:09:00Z'}}))
        self.assertTrue(legacy.is_dir())
        self.assertFalse(self.ctx.host_dir.exists())
        self.put('agent-b', '2026-10-15T12:10:00Z', status='running', agent_id='agent-b', session='claude-sess-2')
        report = self.build()
        self.assertEqual(self.owners(report), {'agent-a': 'C1', 'agent-b': 'C2'})
        self.assertFalse(legacy.exists())

    def test_both_directories_keep_conflicting_files(self):
        legacy = self.legacy_setup()
        self.ctx.host_dir.mkdir()
        name = next(legacy.glob('*.json')).name
        (self.ctx.host_dir / name).write_text('{"new": true}', encoding='utf-8')
        (legacy / 'other.json').write_text('{"o": 1}', encoding='utf-8')
        self.assertTrue(snapshot.migrate_host_dir(self.ctx))
        self.assertFalse(legacy.exists())
        self.assertEqual(json.loads((self.ctx.host_dir / name).read_text(encoding='utf-8')), {'new': True})
        self.assertIn('children', json.loads((self.ctx.host_dir / ('legacy-' + name)).read_text(encoding='utf-8')))
        self.assertTrue((self.ctx.host_dir / 'other.json').exists())

    def test_migration_adds_the_exclude_for_an_older_project(self):
        legacy = self.legacy_setup()
        info = self.root / '.git' / 'info' / 'exclude'
        lines = [l for l in info.read_text(encoding='utf-8').splitlines() if '.host/' not in l]
        info.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.assertTrue(legacy.exists())
        snapshot.migrate_host_dir(self.ctx)
        self.assertIn('specs/*/progress/.host/', info.read_text(encoding='utf-8').splitlines())
        status = subprocess.run(['git', 'status', '--porcelain', '--ignored=no', '-uall'], cwd=self.root, capture_output=True, text=True).stdout
        self.assertNotIn('.host/', status)


if __name__ == '__main__':
    unittest.main()


class C4ReadAllDedupe(Children):
    def test_a_conflict_copy_of_the_same_session_is_read_once(self):
        self.setup_children('agent-a')
        current = next(self.ctx.host_dir.glob('*.json'))
        shutil.copyfile(current, self.ctx.host_dir / ('legacy-' + current.name))
        sessions = [(s.get('host'), s.get('session_id')) for s in snapshot.read_all(self.ctx)]
        self.assertEqual(len(sessions), len(set(sessions)))
