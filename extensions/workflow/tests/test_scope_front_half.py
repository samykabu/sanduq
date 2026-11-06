"""Scope 1.8.0: board cache, inspect snapshot reuse and render-spec."""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import test_scope as ts
from test_scope import m

CACHE = m.BOARD_CACHE


class BoardCacheTests(unittest.TestCase):
    setUp, tearDown = ts.ScopeTests.setUp, ts.ScopeTests.tearDown
    analysis, publish_approved = ts.ScopeTests.analysis, ts.ScopeTests.publish_approved

    def lists(self):
        calls = []
        real = self.gh.command
        self.gh.command = lambda args, payload=None: (calls.append(args[:2]), real(args, payload))[1]
        return calls

    def another_process(self):
        with patch('sanduq_remote.origin_url', return_value='https://github.com/acme/app.git'):
            return m.Scope(self.root, self.gh)

    def test_a_second_process_reads_the_cache_and_a_reload_is_live(self):
        self.app.board()
        cache = m.read_json(self.root / CACHE)
        self.assertEqual((cache['repo'], [i['content']['number'] for i in cache['items']]), ('acme/app', [1]))
        calls = self.lists()
        other = self.another_process()
        self.assertEqual(other.status(self.gh.issues[1]), 'Backlog')
        self.assertEqual(calls, [])
        other._board = None
        other.board()
        self.assertEqual(calls, [['project', 'item-list']])

    def test_stale_foreign_or_disabled_cache_is_not_used(self):
        self.app.board()
        cache = m.read_json(self.root / CACHE)
        calls = self.lists()
        m.write_json(self.root / CACHE, dict(cache, fetched_at='2020-01-01T00:00:00+00:00'))
        self.another_process().board()
        m.write_json(self.root / CACHE, dict(cache, repo='acme/other'))
        self.another_process().board()
        self.assertEqual(len(calls), 2)
        (self.root / '.specify/workflow.yml').write_text('schema_version: 1\nscope:\n  board_cache_seconds: 0\n', encoding='utf-8')
        (self.root / CACHE).unlink()
        self.another_process().board()
        self.assertFalse((self.root / CACHE).exists())

    def test_every_board_or_issue_write_removes_the_cache(self):
        issue = self.gh.issues[1]
        for write in (lambda: self.app.set_labels(issue, 3), lambda: self.app.add_to_board(issue),
                      lambda: self.app.set_status(issue, 'Feature Specification'),
                      lambda: self.app.export_plan(),
                      lambda: self.app.reconcile(True)):
            self.app._board = None
            self.app.board()
            stale = m.read_json(self.root / CACHE)
            stale['items'].append({'id': 'PX', 'status': 'Done', 'content': {'number': 99, 'repository': 'acme/app', 'type': 'Issue'}})
            m.write_json(self.root / CACHE, stale)
            write()
            after = m.read_json(self.root / CACHE, {'items': []})
            self.assertNotIn(99, [i['content']['number'] for i in after['items']])

    def test_field_writes_drop_the_cache_too(self):
        self.gh.command = lambda args, payload=None, real=self.gh.command: (
            {'fields': [{'id': 'B', 'name': 'Blocked by'}]} if args[:2] == ['project', 'field-list'] else
            None if args[:2] == ['project', 'item-edit'] else real(args, payload))
        self.app.board()
        self.app.sync_dependency_fields(self.gh.issues[1], [])
        self.assertFalse((self.root / CACHE).exists())

    def test_publish_and_bind_apply_leave_no_stale_cache(self):
        snap, analysis = self.analysis()
        self.app.board(fresh=True)
        m.write_json(self.root / CACHE, dict(m.read_json(self.root / CACHE), fetched_at='2099-01-01T00:00:00+00:00'))
        self.publish_approved(snap, analysis)
        self.assertNotEqual(m.read_json(self.root / CACHE, {}).get('fetched_at'), '2099-01-01T00:00:00+00:00')
        directory = self.root / 'specs/001-example'
        directory.mkdir(parents=True)
        (directory / 'spec.md').write_text('# Example')
        m.write_json(self.root / '.specify/feature.json', {'feature_directory': 'specs/001-example'})
        self.app.board(fresh=True)
        m.write_json(self.root / CACHE, dict(m.read_json(self.root / CACHE), fetched_at='2099-01-01T00:00:00+00:00'))
        self.app.bind('1', True)
        self.assertNotEqual(m.read_json(self.root / CACHE, {}).get('fetched_at'), '2099-01-01T00:00:00+00:00')
        self.assertEqual(self.another_process().status(self.gh.issues[1]), 'Feature Specification')

    def test_a_cached_status_never_refuses_the_specify_gate(self):
        snap, analysis = self.analysis()
        self.publish_approved(snap, analysis)
        self.gh.statuses[1] = 'Ready'
        self.another_process().board()  # caches Ready
        self.gh.statuses[1] = 'Backlog'  # moved on GitHub; the cache does not know
        self.assertEqual(self.another_process().gate('1')['issue'], 1)


class SnapshotTests(unittest.TestCase):
    setUp, tearDown = ts.ScopeTests.setUp, ts.ScopeTests.tearDown
    analysis, publish_approved = ts.ScopeTests.analysis, ts.ScopeTests.publish_approved

    def saved(self):
        path = self.root / 'inspect.json'
        m.write_json(path, self.app.inspect('1'))
        return path

    def test_a_current_snapshot_is_reused_with_the_live_issue(self):
        path = self.saved()
        self.gh.issues[1]['labels'] = [{'name': 'effort:3'}]  # outside the fingerprint
        with patch.object(self.app, 'inspect', side_effect=AssertionError('must reuse')):
            snapshot = self.app.load_snapshot('1', path)
        self.assertTrue(self.app.snapshot_reused)
        self.assertEqual(snapshot['issue']['labels'], [{'name': 'effort:3'}])

    def test_changed_old_or_disabled_snapshot_falls_back_to_inspect(self):
        path = self.saved()
        self.gh.issues[1]['title'] = 'Changed'
        self.app.load_snapshot('1', path)
        self.assertFalse(self.app.snapshot_reused)
        path = self.saved()
        old = time.time() - 301
        os.utime(path, (old, old))
        self.app.load_snapshot('1', path)
        self.assertFalse(self.app.snapshot_reused)
        path = self.saved()
        (self.root / '.specify/workflow.yml').write_text('schema_version: 1\nscope:\n  board_cache_seconds: 0\n', encoding='utf-8')
        self.app.load_snapshot('1', path)
        self.assertFalse(self.app.snapshot_reused)
        self.app.load_snapshot('1', self.root / 'missing.json')
        self.assertFalse(self.app.snapshot_reused)

    def run_cli(self, *argv):
        out = io.StringIO()
        with patch.object(m, 'Scope', return_value=self.app), contextlib.redirect_stdout(out):
            code = m.main(list(argv) + ['--root', str(self.root)])
        return code, (json.loads(out.getvalue()) if out.getvalue() else None)

    def test_cli_reports_whether_the_snapshot_was_reused(self):
        snap, analysis = self.analysis()
        analysis_path = self.root / 'analysis.json'
        m.write_json(analysis_path, analysis)
        path = self.saved()
        code, result = self.run_cli('publish', '1', '--analysis', str(analysis_path), '--snapshot', str(path))
        self.assertEqual((code, result['dry_run'], result['snapshot_reused']), (0, True, True))
        self.publish_approved(snap, analysis)
        code, result = self.run_cli('gate', '1', '--snapshot', str(path))
        self.assertEqual((code, result['score'], result['snapshot_reused']), (0, 3, True))
        self.gh.issues[1]['title'] = 'Changed'
        code, result = self.run_cli('gate', '1', '--snapshot', str(path))
        self.assertEqual(code, 2)  # a full inspect sees the changed requirements
        code, result = self.run_cli('gate', '1')
        self.assertEqual(code, 2)


class RenderSpecTests(unittest.TestCase):
    setUp, tearDown = ts.ScopeTests.setUp, ts.ScopeTests.tearDown
    analysis, publish_approved = ts.ScopeTests.analysis, ts.ScopeTests.publish_approved

    def approved(self, **extra):
        snap, analysis = self.analysis()
        analysis.update(requirements=['AC-1', 'AC-2'], **extra)
        analysis['tree']['covers'] = ['AC-1', 'AC-2']
        analysis['tree']['acceptance'] = ['Given a user, when they submit, then it is saved', 'Given a failure, then retry']
        self.publish_approved(snap, analysis)
        path = self.root / 'analysis.json'
        path.write_text(json.dumps(analysis, indent=2), encoding='utf-8')
        return path

    def test_dry_run_renders_the_spec_kit_shape_and_writes_nothing(self):
        path = self.approved(uncertainty=['Which retry limit applies?'], open_questions=[{'question': 'Who sees errors?'}])
        result = self.app.render_spec('1', path, 'specs/001-example')
        text = result['text']
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertTrue(text.startswith(f'<!-- sanduq-scope:rendered {sha} -->\n# Feature Specification: Issue 1\n'))
        for heading in ('## Overview', '## User Scenarios & Testing', '### User Story 1 - root (Priority: P1)',
                        '## Requirements', '### Functional Requirements', '## Success Criteria', '## Out of Scope', '## Open Questions'):
            self.assertIn(heading, text)
        self.assertIn('- **FR-001**: AC-1\n- **FR-002**: AC-2\n', text)
        self.assertIn('- **SC-001**: Given a user, when they submit, then it is saved\n- **SC-002**: Given a failure, then retry\n', text)
        self.assertIn('- [NEEDS CLARIFICATION: Which retry limit applies?]\n- [NEEDS CLARIFICATION: Who sees errors?]\n', text)
        self.assertIn('Implement the specified behavior.', text)
        self.assertIn('Reuses tested existing behavior', text)
        self.assertEqual((result['dry_run'], result['analysis_sha256']), (True, sha))
        self.assertFalse((self.root / 'specs').exists())

    def test_apply_writes_reruns_and_refuses_a_hand_written_spec_without_force(self):
        path = self.approved()
        result = self.app.render_spec('1', path, 'specs/001-example', apply=True)
        spec = self.root / 'specs/001-example/spec.md'
        self.assertEqual(result['path'], 'specs/001-example/spec.md')
        self.assertIn('## Open Questions\n\nNone.\n', spec.read_text(encoding='utf-8'))
        self.assertNotIn(b'\r', spec.read_bytes())
        self.app.render_spec('1', path, 'specs/001-example', apply=True)  # a rendered spec can be rerendered
        spec.write_text('# Hand written\n', encoding='utf-8')
        with self.assertRaisesRegex(m.ScopeError, 'SCOPE_RENDER_EXISTS'):
            self.app.render_spec('1', path, 'specs/001-example')
        self.app.render_spec('1', path, 'specs/001-example', apply=True, force=True)
        self.assertTrue(spec.read_text(encoding='utf-8').startswith('<!-- sanduq-scope:rendered '))

    def test_only_the_published_approved_leaf_analysis_renders(self):
        path = self.approved()
        changed = json.loads(path.read_text(encoding='utf-8'))
        changed['alignment'] = 'Something else'
        path.write_text(json.dumps(changed), encoding='utf-8')
        with self.assertRaisesRegex(m.ScopeError, 'SCOPE_RENDER_UNAPPROVED'):
            self.app.render_spec('1', path, 'specs/001-example')
        with self.assertRaisesRegex(m.ScopeError, 'SCOPE_RENDER_FEATURE_REQUIRED'):
            self.app.render_spec('1', path, '../outside')
        snap, split = self.analysis(True)
        self.publish_approved(snap, split)
        path.write_text(json.dumps(split), encoding='utf-8')
        with self.assertRaisesRegex(m.ScopeError, 'SCOPE_RENDER_LEAF_REQUIRED'):
            self.app.render_spec('1', path, 'specs/001-example')

    def test_cli_render_spec(self):
        path = self.approved()
        out = io.StringIO()
        with patch.object(m, 'Scope', return_value=self.app), contextlib.redirect_stdout(out):
            code = m.main(['render-spec', '1', '--analysis', str(path), '--feature', 'specs/001-example', '--root', str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn('# Feature Specification: Issue 1', json.loads(out.getvalue())['text'])


if __name__ == '__main__':
    unittest.main()
