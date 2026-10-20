"""GitHub call counts of publish, gate, bind and clarification publish, and dependent completeness (SC3, SC4)."""
import collections
import subprocess
import unittest
from unittest.mock import patch

import test_scope as ts
from test_scope import m
import test_clarification as tc


class CountingGitHub(ts.FakeGitHub):
    def __init__(self):
        super().__init__()
        self.calls = collections.Counter()
        self.board_text = {}  # issue number -> Project "Blocked by" text

    def api(self, endpoint, method='GET', payload=None, pages=False):
        parts = endpoint.split('?')[0].split('/')
        self.calls[(method, '/'.join('N' if p.isdigit() else p for p in parts[4:]) or parts[-1])] += 1
        return super().api(endpoint, method, payload, pages)

    def command(self, args, payload=None):
        self.calls[('project', args[1])] += 1
        result = super().command(args, payload)
        if args[:2] == ['project', 'item-list']:
            for item in result['items']:
                if item['content']['number'] in self.board_text:
                    item['blocked by'] = self.board_text[item['content']['number']]
        return result

    def total(self):
        return sum(self.calls.values())


class Calls(unittest.TestCase):
    setUp, tearDown = ts.ScopeTests.setUp, ts.ScopeTests.tearDown
    analysis, publish_approved = ts.ScopeTests.analysis, ts.ScopeTests.publish_approved

    def use_counter(self):
        gh = CountingGitHub()
        gh.issues, gh.statuses, gh.deps, gh.children = self.gh.issues, self.gh.statuses, self.gh.deps, self.gh.children
        self.gh = self.app.gh = gh
        return gh

    def new_process(self):
        (self.root / m.BOARD_CACHE).unlink(missing_ok=True)
        with patch('sanduq_remote.origin_url', return_value='https://github.com/acme/app.git'):
            self.app = m.Scope(self.root, self.gh)
        self.gh.calls.clear()

    def split(self, unrelated=0):
        gh = self.use_counter()
        for n in range(10, 10 + unrelated):
            gh.add(n, body='Unrelated work')
        snap, analysis = self.analysis(True)
        analysis['tree']['children'].append(ts.node('third'))
        analysis['tree']['children'][2]['depends_on'] = ['second']
        self.app.approve(snap, analysis, 3, 'test owner', 'I approve this exact proposal.')
        self.new_process()
        return snap, analysis

    def test_split_publish_does_not_scale_with_unrelated_issues(self):
        counts = []
        for unrelated in (0, 200):
            self.tearDown()
            self.setUp()
            snap, analysis = self.split(unrelated)
            self.app.publish(snap, analysis, True)
            counts.append(self.gh.total())
            calls = self.gh.calls
            self.assertEqual(calls[('project', 'item-list')], 1)
            self.assertEqual(calls[('project', 'field-list')], 1)
            self.assertEqual(calls[('GET', 'labels')], 1)
        self.assertEqual(counts[0], counts[1])
        self.assertLess(counts[1], 70)  # 290 before SC3 with 200 unrelated issues

    def test_rewire_finds_every_kind_of_dependent(self):
        gh = self.use_counter()
        gh.add(2, 'Native link only')
        gh.deps[2] = {1}
        gh.add(3, 'Body text only', 'Depends on: #1')
        gh.add(4, 'Board field only')
        gh.board_text[4] = '#1'
        gh.add(5, 'Catalogue only')
        self.app.keymap['UC-5'] = 5
        self.app.catalog['issues'].append({'key': 'UC-5', 'blockedBy': ['#1']})
        gh.add(6, 'Depends on another issue', 'Depends on: #2')
        for n in range(10, 60):
            gh.add(n, body='Unrelated work')
        self.app._board = None
        expected = sorted(n for n, x in gh.issues.items() if n != 1 and 1 in self.app.dependencies(x))
        self.assertEqual(expected, [2, 3, 4, 5])
        others = [x for x in gh.issues.values() if x['number'] != 1]
        targeted = sorted(x['number'] for x, _ in self.app.rewire_candidates(gh.issues[1], others))
        self.assertEqual(targeted, expected)
        snap, analysis = self.analysis(True)
        result = self.publish_approved(snap, analysis)
        leaves = {result['nodes']['first'], result['nodes']['second']}
        gh.board_text.clear()  # the field now holds the leaves; the fake board does not store text edits
        self.app._board = None
        for n in (2, 3, 5):
            self.assertEqual(set(self.app.dependencies(gh.issues[n])), leaves, n)
        self.assertEqual(self.app.dependencies(gh.issues[4]), sorted(leaves))
        self.assertNotIn(6, [int(k) for k in m.read_json(self.root / result['journal'])['dependencies_before']])

    def test_unreadable_blocking_list_falls_back_to_the_full_scan(self):
        gh = self.use_counter()
        gh.add(2, 'Consumer')
        gh.deps[2] = {1}
        for n in range(10, 30):
            gh.add(n, body='Unrelated work')
        gh.blocking_unavailable = True
        snap, analysis = self.analysis(True)
        result = self.publish_approved(snap, analysis)
        self.assertEqual(gh.deps[2], {result['nodes']['first'], result['nodes']['second']})
        self.assertGreaterEqual(gh.calls[('GET', 'N/dependencies/blocked_by')], 21)

    def test_memory_board_matches_a_live_read_after_publish(self):
        snap, analysis = self.split()
        self.app.publish(snap, analysis, True)
        memory = {n: (row['id'], row.get('status')) for n, row in self.app.board().items()}
        live = {n: (row['id'], row.get('status')) for n, row in self.app.board(fresh=True).items()}
        self.assertEqual(memory, live)

    def published_leaf(self):
        gh = self.use_counter()
        snap, analysis = self.analysis()
        self.publish_approved(snap, analysis)
        self.new_process()
        return gh

    def test_gate_without_snapshot_reads_no_comments_or_timelines(self):
        gh = self.published_leaf()
        gh.add(2, status='Done')
        gh.deps[1] = {2}  # a prerequisite whose timeline the full inspect would read
        with self.assertRaisesRegex(m.ScopeError, 'prerequisites changed'):
            self.app.gate('1')
        self.assertFalse([k for k in gh.calls if k[1].endswith(('comments', 'timeline'))])

    def test_gate_and_bind_reuse_the_analysts_snapshot(self):
        gh = self.published_leaf()
        m.write_json(self.root / '.specify/scope/issue-1-snapshot.json', self.app.inspect('1'))
        self.new_process()
        self.app.gate('1')
        self.assertTrue(self.app.snapshot_reused)
        self.assertEqual(gh.total(), 2)  # one issue read and one board read
        directory = self.root / 'specs/001-example'
        directory.mkdir(parents=True)
        (directory / 'spec.md').write_text('# Example')
        m.write_json(self.root / '.specify/feature.json', {'feature_directory': 'specs/001-example'})
        self.new_process()
        self.app.bind('1', True)
        self.assertEqual(gh.calls[('GET', 'N')], 1)  # 3 before: resume check, gate, binding
        self.assertNotIn(('project', 'item-add'), gh.calls)  # already on the board


class ClarificationCalls(unittest.TestCase):
    setUp, tearDown, analysis = tc.ClarificationTests.setUp, tc.ClarificationTests.tearDown, tc.ClarificationTests.analysis

    def test_six_question_publish(self):
        gh = tc.ReviewGitHub.__new__(type('CountingReview', (CountingGitHub, tc.ReviewGitHub), {}))
        CountingGitHub.__init__(gh)
        gh.comments, gh.fail_after_post, gh.viewer = [], False, 'creator'
        gh.issues, gh.statuses = self.gh.issues, self.gh.statuses
        self.gh = self.scope.gh = self.app.gh = gh
        analysis = self.analysis([tc.question(f'q-{n}') for n in range(6)])
        self.scope._board, self.scope._board_cached = None, None
        gh.calls.clear()
        self.app.publish('1', analysis, True)
        self.assertEqual(gh.calls[('GET', 'N/comments')], 9)  # 10 before: the first post reuses the fresh read
        self.assertEqual(gh.calls[('GET', 'N')], 4)  # 6 before: gate and transition share one read
        self.assertLessEqual(gh.total(), 23)  # 27 before


if __name__ == '__main__':
    unittest.main()
