"""Scope (#115): export-plan validates the affected graph before its first write and leaves cancelled history alone."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

import test_scope as ts
from test_scope import m

APPROVAL = {'analysis_sha256': 'a' * 64, 'child_count': 1, 'approved_by': 'test owner', 'approved_at': '2026-10-31T00:00:00+00:00'}


def receipt(**fields):
    return '<!-- speckit-scope:metadata ' + json.dumps(dict({'version': 2, 'score': 3}, **fields)) + ' -->'


RECEIPT = receipt()


class ExportPreflight(unittest.TestCase):
    setUp, tearDown = ts.ScopeTests.setUp, ts.ScopeTests.tearDown
    analysis, publish_approved = ts.ScopeTests.analysis, ts.ScopeTests.publish_approved

    def board_fields(self, blocks):
        """Give the fake board a `Blocks` text field with `blocks` {issue: value}; record item-edit arguments."""
        real = self.gh.command

        def command(args, payload=None):
            if args[:2] == ['project', 'field-list']:
                return {'fields': [{'id': 'FB', 'name': 'Blocks'}]}
            if args[:2] == ['project', 'item-edit']:
                self.gh.writes.append(('item-edit', args))
                return None
            data = real(args, payload)
            if args[:2] == ['project', 'item-list']:
                for item in data['items']:
                    if item['content']['number'] in blocks:
                        item['blocks'] = blocks[item['content']['number']]
            return data
        self.gh.command = command

    def test_cancelled_scoped_history_is_not_rewritten(self):
        cancelled = self.gh.add(2, 'Cancelled history', 'Old scope\n\n' + RECEIPT)
        cancelled.update(state='closed', state_reason='not_planned')
        self.app.export_plan()
        self.assertFalse([w for w in self.gh.writes if w[1].endswith('/issues/2')], self.gh.writes)
        graph = m.read_json(self.app.artifact_directory / 'scope-dependencies.json')
        self.assertNotIn(2, [x['number'] for x in graph['issues']])

    def test_dependency_cycle_is_refused_before_any_write(self):
        self.gh.add(2, 'Booking', RECEIPT)
        self.gh.add(3, 'Refund', RECEIPT)
        self.gh.deps.update({2: {3}, 3: {2}})
        with self.assertRaisesRegex(m.ScopeError, '(?i)cycle'):
            self.app.export_plan()
        self.assertFalse(self.gh.writes)
        self.assertFalse(self.app.catalog_path.exists())

    def test_empty_text_clears_the_field_on_the_cli_route(self):
        self.gh.statuses[1] = 'Backlog'
        with patch.object(self.gh, 'command', return_value=None) as command:
            self.app._board = {1: {'id': 'P1', 'blocks': '#2'}}
            self.app.edit_item({'number': 1}, 'FB', 'blocks', '')
        args = command.call_args.args[0]
        self.assertIn('--clear', args)
        self.assertNotIn('--text', args)

    def test_invalid_graphs_are_refused_before_any_write(self):
        cases = {
            'SCOPE_EXPORT_CANCELLED: .*#3 -> #2': lambda: (self.gh.add(2, 'Cancelled', RECEIPT).update(state='closed', state_reason='not_planned'),
                                                           self.gh.add(3, 'Refund', RECEIPT), self.gh.deps.update({3: {2}})),
            'SCOPE_EXPORT_MISSING: .*#3 -> #40': lambda: self.gh.add(3, 'Refund', 'Depends on: #40\n\n' + RECEIPT),
            'SCOPE_EXPORT_AGGREGATE: .*#3 -> #2': lambda: (self.gh.add(2, 'Parent', receipt(children=[4], approval=APPROVAL)),
                                                           self.gh.add(4, 'Leaf', RECEIPT), self.gh.add(3, 'Refund', RECEIPT),
                                                           self.gh.deps.update({3: {2}})),
            'SCOPE_EXPORT_UNAPPROVED: .*#2': lambda: (self.gh.add(2, 'Parent', receipt(children=[4])), self.gh.add(4, 'Leaf', RECEIPT)),
            'SCOPE_EXPORT_CYCLE: #2 -> #4 -> #2': lambda: (self.gh.add(2, 'Parent', receipt(children=[4], approval=APPROVAL)),
                                                          self.gh.add(4, 'Leaf', receipt(children=[2], approval=APPROVAL))),
        }
        for message, arrange in cases.items():
            with self.subTest(message):
                self.tearDown()  # a fresh repository per case; unittest tears down the last one
                self.setUp()
                arrange()
                with self.assertRaisesRegex(m.ScopeError, message):
                    self.app.export_plan()
                self.assertFalse(self.gh.writes)
                self.assertFalse(self.app.catalog_path.exists())
                self.assertFalse((self.root / '.specify/scope/runs').exists())

    def test_interrupted_export_journals_exact_before_images_and_cancel_reports_them(self):
        self.gh.add(2, 'Booking', 'Booking scope\n\n' + RECEIPT)
        self.gh.add(3, 'Refund', 'Refund scope\n\nDepends on: #2\n\n' + RECEIPT)
        self.gh.deps[3] = {2}
        before = {n: self.gh.issues[n]['body'] for n in (2, 3)}
        self.board_fields({3: '#2'})  # #3 shows a stale reverse link; #2 has none yet
        self.gh.fail_once = '/issues/3'
        with self.assertRaisesRegex(m.ScopeError, 'interruption'):
            self.app.export_plan()
        [folder] = (self.root / '.specify/scope/runs').glob('plan-export-*')
        journal = m.read_json(folder / 'journal.json')
        self.assertEqual(journal['kind'], 'plan-export')
        self.assertEqual({n: journal['before'][str(n)]['body'] for n in (2, 3)}, before)
        self.assertEqual(journal['fields_before'], {'2': {'Blocks': ''}, '3': {'Blocks': '#2'}})
        self.assertEqual(journal['native_dependencies_before'], {'2': [], '3': [2]})
        planned = [(w['issue'], w.get('field', 'body')) for w in journal['export']['planned']]
        self.assertEqual(planned, [(2, 'Blocks'), (2, 'body'), (3, 'Blocks'), (3, 'body')])
        self.assertEqual(journal['export']['applied'], 3)
        edits = [w[1] for w in self.gh.writes if w[0] == 'item-edit']
        self.assertEqual([e[e.index('--field-id') + 2:] for e in edits], [['--text', '#3'], ['--clear']])

        writes = len(self.gh.writes)
        out = io.StringIO()
        with patch.object(m, 'Scope', return_value=self.app), contextlib.redirect_stdout(out):
            self.assertEqual(m.main(['cancel', folder.name, '--apply', '--root', str(self.root)]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual((result['kind'], result['rolled_back'], result['created']), ('plan-export', True, {}))
        self.assertEqual(result['fields_before'], journal['fields_before'])
        self.assertEqual(result['native_dependencies_before'], journal['native_dependencies_before'])
        self.assertEqual(result['export']['applied'], 3)
        self.assertEqual(result['backups'], [f'.specify/scope/runs/{folder.name}/{n}' for n in ('catalog-before.json', 'issue-map-before.json')])
        self.assertEqual(len(self.gh.writes), writes)  # cancel writes nothing to GitHub
        self.assertTrue(m.read_json(folder / 'journal.json')['rolled_back'])

    def test_split_publish_leaves_a_cancelled_dependent_alone(self):
        self.gh.add(5, 'Cancelled dependent', 'Depends on #1')['state_reason'] = 'not_planned'
        self.gh.issues[5]['state'] = 'closed'
        self.gh.deps[5] = {1}
        snap, analysis = self.analysis(True)
        self.publish_approved(snap, analysis)
        self.assertEqual(self.gh.deps[5], {1})
        self.assertFalse([w for w in self.gh.writes if '/issues/5' in w[1]])


if __name__ == '__main__':
    unittest.main()
