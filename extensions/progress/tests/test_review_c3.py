"""Regression tests for the cycle-3 review findings (A1 durable host observations, A2/F1 blocker references through child
identities, A3 lifecycle freshness when linking, A4 provisional reconciliation, A5 completed split, F2 late child events,
F3 package-local safelog)."""
import json
import shutil
import subprocess
import sys
import unittest
from datetime import datetime, timezone

from helpers import SCRIPTS, Project
from sanduq_progress import model, paths, snapshot
from test_review_c1 import stamp

NOW = datetime(2026, 10, 15, 12, 30, tzinfo=timezone.utc)


def child_lanes(report):
    return [l for l in report['lanes'] if l['origin'] == 'host-child']


class Children(Project):
    def put(self, key, at, by_agent=False, session='claude-sess-1', **update):
        base = {'kind': 'subagent', 'description': f'work {key}', 'last_observed_at': at}
        snapshot.merge(self.ctx, 'claude', session, stamp(at), child={'key': key, 'by_agent': by_agent, 'update': {**base, **update}})

    def entries(self, session='claude-sess-1'):
        return json.loads(snapshot.snapshot_path(self.ctx, 'claude', session).read_text(encoding='utf-8'))['children']

    def build(self):
        return model.build(self.ctx, NOW, 1, {})

    def owners(self, report):
        return {l['owner']: l['id'] for l in child_lanes(report)}

    def setup_children(self, *names):
        self.init(debounce_seconds=0)
        self.bind()
        for i, name in enumerate(names, 1):
            self.put(name, f'2026-10-15T12:0{i}:00Z', status='running', started_at=f'2026-10-15T12:0{i}:00Z', agent_id=name)

    def lane(self, report, lane_id):
        return next(l for l in report['lanes'] if l['id'] == lane_id)

    def blockers(self, report):
        return sorted((b['target'], b['by'].get('ref')) for b in report['blockers'])


class A1DurableHostObservations(Children):
    def test_host_snapshots_live_outside_the_disposable_view(self):
        self.assertNotIn(self.ctx.view, self.ctx.host_dir.parents)
        self.assertIn('specs/*/progress/.host/', paths.EXCLUDES)

    def test_deleting_the_whole_view_changes_no_child_id_or_blocker(self):
        self.setup_children('agent-a', 'agent-b', 'agent-c')
        self.cli('block', 'C2', '--by', 'ext:waiting')
        self.cli('refresh')
        before = self.owners(self.report())
        shutil.rmtree(self.ctx.view)
        report = self.build()
        self.assertEqual(self.owners(report), before)
        self.assertEqual(before, {'agent-a': 'C1', 'agent-b': 'C2', 'agent-c': 'C3'})
        self.assertTrue(any(b['target'] == 'C2' for b in report['blockers']))

    def test_an_existing_view_host_directory_is_migrated_on_first_access(self):
        self.setup_children('agent-a', 'agent-b')
        legacy = self.ctx.view / 'host'
        shutil.move(str(self.ctx.host_dir), str(legacy))
        self.assertFalse(self.ctx.host_dir.exists())
        self.put('agent-c', '2026-10-15T12:05:00Z', status='running', agent_id='agent-c')
        self.assertFalse(legacy.exists())
        self.assertEqual({k: v['lane_no'] for k, v in self.entries().items()}, {'agent-a': 1, 'agent-b': 2, 'agent-c': 3})
        shutil.rmtree(self.ctx.view)
        self.assertEqual(self.owners(self.build()), {'agent-a': 'C1', 'agent-b': 'C2', 'agent-c': 'C3'})


class A2BlockerReferences(Children):
    def test_a_blocker_follows_a_child_merged_into_another_child(self):
        self.setup_children('agent-a')
        self.put('toolu_A', '2026-10-15T12:02:00Z', status='running', started_at='2026-10-15T12:02:00Z')
        self.cli('block', 'T002', '--by', 'C2')
        self.cli('block', 'C2', '--by', 'ext:waiting')
        self.put('toolu_A', '2026-10-15T12:03:00Z', agent_id='agent-a')
        report = self.build()
        self.assertEqual([l['id'] for l in child_lanes(report)], ['C1'])
        self.assertEqual(self.blockers(report), [('C1', 'waiting'), ('T002', 'C1')])

    def test_a_blocker_on_a_child_assigned_to_a_lane_shows_on_that_lane(self):
        self.setup_children('agent-a', 'agent-b')
        self.cli('block', 'C2', '--by', 'ext:waiting')
        self.cli('block', 'T003', '--by', 'C2')
        self.cli('lane', 'L1', '--tasks', 'T002', '--owner', 'agent-b')
        report = self.build()
        self.assertEqual([l['id'] for l in child_lanes(report)], ['C1'])
        self.assertEqual(self.blockers(report), [('L1', 'waiting'), ('T003', 'L1')])
        self.assertEqual(self.lane(report, 'L1')['status'], 'blocked')


class A3FreshnessWhenLinking(Children):
    def test_a_delayed_linking_result_does_not_end_a_newer_generation(self):
        self.init()
        self.put('agent-1', '2026-10-15T12:05:00Z', by_agent=True, status='done', ended_at='2026-10-15T12:05:00Z',
                 started_at='2026-10-15T12:00:00Z')
        self.put('toolu_1', '2026-10-15T12:10:00Z', status='running', started_at='2026-10-15T12:10:00Z')
        self.put('toolu_1', '2026-10-15T12:06:00Z', agent_id='agent-1', status='done', ended_at='2026-10-15T12:06:00Z')
        entries = self.entries()
        self.assertEqual(list(entries), ['toolu_1'])
        entry = entries['toolu_1']
        self.assertEqual((entry['status'], entry['started_at'], entry['ended_at']), ('running', '2026-10-15T12:10:00Z', None))

    def test_a_newer_agent_record_still_ends_the_launch(self):
        self.init()
        self.put('toolu_1', '2026-10-15T12:00:00Z', status='running', started_at='2026-10-15T12:00:00Z')
        self.put('agent-1', '2026-10-15T12:05:00Z', by_agent=True, status='done', ended_at='2026-10-15T12:05:00Z')
        self.put('toolu_1', '2026-10-15T12:06:00Z', agent_id='agent-1')
        entry = self.entries()['toolu_1']
        self.assertEqual((entry['status'], entry['ended_at']), ('done', '2026-10-15T12:05:00Z'))


class A4A5Provisional(Children):
    def launch(self):
        self.init()
        self.put('toolu_1', '2026-10-15T12:00:00Z', status='running', started_at='2026-10-15T12:00:00Z')
        self.put('agent-A', '2026-10-15T12:01:00Z', by_agent=True, status='running')

    def test_a_confirmed_identity_does_not_erase_another_running_child(self):
        self.launch()
        self.assertEqual(self.entries()['toolu_1']['agent_link'], 'provisional')
        self.put('agent-B', '2026-10-15T12:02:00Z', by_agent=True, status='running')
        self.put('toolu_1', '2026-10-15T12:03:00Z', agent_id='agent-B')
        entries = self.entries()
        self.assertEqual(sorted(e['agent_id'] for e in entries.values()), ['agent-A', 'agent-B'])
        self.assertTrue(all(e['status'] == 'running' for e in entries.values()))
        self.assertEqual(entries['toolu_1']['agent_id'], 'agent-B')
        self.assertNotIn('agent_link', entries['toolu_1'])

    def test_confirmation_clears_the_provisional_flag(self):
        self.launch()
        self.put('toolu_1', '2026-10-15T12:03:00Z', agent_id='agent-A')
        self.assertNotIn('agent_link', self.entries()['toolu_1'])

    def test_splitting_a_completed_child_keeps_its_end_time(self):
        self.launch()
        self.put('agent-A', '2026-10-15T12:02:00Z', by_agent=True, status='done', ended_at='2026-10-15T12:02:00Z')
        self.put('toolu_1', '2026-10-15T12:03:00Z', agent_id='agent-other')
        entries = self.entries()
        split = next(e for e in entries.values() if e['agent_id'] == 'agent-A')
        self.assertEqual((split['status'], split['ended_at']), ('done', '2026-10-15T12:02:00Z'))
        self.assertEqual(next(e for e in entries.values() if e['agent_id'] == 'agent-other')['agent_id'], 'agent-other')


class F2LateChildEvents(Children):
    def finished(self):
        self.init()
        self.put('toolu_1', '2026-10-15T12:00:00Z', status='running', started_at='2026-10-15T12:00:00Z')
        self.put('toolu_1', '2026-10-15T12:03:00Z', agent_id='agent-1', status='done', ended_at='2026-10-15T12:03:00Z')

    def test_a_running_observation_not_newer_than_the_result_does_not_reopen(self):
        self.finished()
        for at in ('2026-10-15T12:03:00Z', '2026-10-15T12:02:00Z'):
            self.put('agent-1', at, by_agent=True, status='running')
        entry = self.entries()['toolu_1']
        self.assertEqual((entry['status'], entry['ended_at'], entry.get('generation')), ('done', '2026-10-15T12:03:00Z', None))

    def test_a_newer_running_observation_starts_a_new_generation(self):
        self.finished()
        self.put('agent-1', '2026-10-15T12:04:00Z', by_agent=True, status='running')
        entry = self.entries()['toolu_1']
        self.assertEqual((entry['status'], entry['generation'], entry['ended_at']), ('running', 2, None))


class F3PackageLocalSafelog(unittest.TestCase):
    def test_importing_the_package_needs_no_top_level_safelog(self):
        probe = ("import sys; sys.path.insert(0, %r); import sanduq_progress.util as u; "
                 "print('safelog' in sys.modules, 'sanduq_progress.safelog' in sys.modules, u.DIAG_LIMIT)" % str(SCRIPTS))
        out = subprocess.run([sys.executable, '-c', probe], capture_output=True, text=True, cwd=str(SCRIPTS.parent))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.split()[:2], ['False', 'True'])


if __name__ == '__main__':
    unittest.main()
