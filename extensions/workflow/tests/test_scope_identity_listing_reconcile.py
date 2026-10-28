"""Scope: repository identity, a split publish refused before any write, messages instead of tracebacks,
compact inspect output, one issue listing, ancestor reconcile and the Specify overlay split."""
import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_scope as ts
from test_scope import m
import test_scope_clarification as tc
from test_scope_github_calls import CountingGitHub

ROOT = Path(__file__).resolve().parents[3]
REMOTE = 'sanduq_remote.origin_url'


class TreeGitHub(CountingGitHub):
    """Adds the native `parent` read and bulky GitHub metadata on issues and comments."""

    def __init__(self):
        super().__init__()
        self.comments = {}

    def add(self, n, title=None, body='', status='Backlog'):
        issue = super().add(n, title, body, status)
        issue.update(user={'login': 'creator', 'id': 7, 'avatar_url': 'https://avatars.example/' + 'x' * 200},
                     reactions={'url': 'https://api.github.com/x' * 4, 'total_count': 0}, timeline_url='t' * 300)
        return issue

    def api(self, endpoint, method='GET', payload=None, pages=False):
        parts = endpoint.split('?')[0].split('/')
        if len(parts) == 6 and parts[5] == 'parent':
            self.calls[('GET', 'N/parent')] += 1
            n = int(parts[4])
            parent = next((p for p, kids in self.children.items() if n in kids), None)
            if parent is None:
                raise m.ScopeError('GitHub request failed (api ...): gh: Not Found (HTTP 404)')
            return dict(self.issues[parent])
        if len(parts) == 6 and parts[5] == 'comments' and method == 'GET':
            self.calls[('GET', 'N/comments')] += 1
            return [dict(c) for c in self.comments.get(int(parts[4]), [])]
        return super().api(endpoint, method, payload, pages)


class Base(unittest.TestCase):
    setUp, tearDown = ts.ScopeTests.setUp, ts.ScopeTests.tearDown
    analysis, publish_approved = ts.ScopeTests.analysis, ts.ScopeTests.publish_approved

    def use(self, gh=None):
        gh = gh or TreeGitHub()
        gh.issues, gh.statuses, gh.deps, gh.children = self.gh.issues, self.gh.statuses, self.gh.deps, self.gh.children
        self.gh = self.app.gh = gh
        return gh

    def scope(self, remote='https://github.com/acme/app.git'):
        with patch(REMOTE, return_value=remote):
            return m.Scope(self.root, self.gh)


class RepositoryIdentity(Base):
    def test_every_github_remote_form_reads_the_same_repository(self):
        for remote in ('ssh://git@github.com/acme/app/', 'https://github.com/acme/app/', 'ssh://git@github.com:22/acme/app.git',
                       'https://GitHub.com/acme/app.git', 'git@github.com:acme/app.git', 'https://u:t@github.com/acme/app'):
            self.assertEqual(self.scope(remote).repo, 'acme/app', remote)

    def test_a_look_alike_or_missing_origin_is_refused_with_a_message(self):
        for remote in ('https://evil.example/github.com/acme/app', 'https://github.com.evil.example/acme/app', None):
            with self.assertRaisesRegex(m.ScopeError, 'A GitHub origin remote is required'):
                self.scope(remote)

    def test_a_checkout_without_origin_exits_2_with_a_message(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(['inspect', '1', '--root', str(self.root)]), 2)
        self.assertIn('no remote.origin.url is set', err.getvalue())

    def test_a_mixed_case_remote_reads_the_board_and_native_dependencies(self):
        self.gh.add(2, status='Done')
        self.gh.deps[1] = {2}
        self.app = self.scope('https://github.com/Acme/App.git')
        self.assertEqual(self.app.status(self.gh.issues[1]), 'Backlog')
        result = self.app.inspect('1')
        self.assertTrue(result['ready'])
        self.assertEqual(result['prerequisites'][0]['status'], 'Done')


class SplitPublish(Base):
    def test_an_unrelated_prose_dependency_does_not_stop_a_split(self):
        self.gh.add(2, 'Unrelated', '## Depends on\n\n- the design review sign-off')
        snap, analysis = self.analysis(True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = self.publish_approved(snap, analysis)
        self.assertTrue(m.read_json(self.root / result['journal'])['published'])
        self.assertIn('#2 not rewired', err.getvalue())
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)

    def test_prose_naming_the_parent_refuses_before_any_write(self):
        self.gh.add(2, 'Consumer', '## Depends on\n\n- UC-missing\n\nWaits for #1.')
        snap, analysis = self.analysis(True)
        with self.assertRaisesRegex(m.ScopeError, 'Unresolved prerequisite key'):
            self.publish_approved(snap, analysis)
        self.assertEqual(self.gh.writes, [])


class Messages(Base):
    def project(self, root):
        m.write_json(root / '.specify/extensions/project/config.json', {'projectId': 'P', 'projectNumber': 2, 'owner': 'acme',
                     'statusFieldId': 'F', 'statusOptions': {}, 'stateFile': '.specify/project-sync-state.json'})

    def test_a_gh_timeout_in_a_clarification_hook_exits_2_with_a_message(self):
        timeout = subprocess.TimeoutExpired(['gh', 'api'], 120)
        err = io.StringIO()
        with patch(REMOTE, return_value='https://github.com/acme/app.git'), \
                patch.object(m.subprocess, 'run', side_effect=timeout), contextlib.redirect_stderr(err):
            self.assertEqual(tc.m.main(['dispatch', '1', '--root', str(self.root)]), 2)
        self.assertIn('timed out', err.getvalue())

    def test_a_hung_illustrate_export_is_a_failed_step_not_a_hang(self):
        path = ROOT / 'extensions/workflow/scripts/scope/accept_plan.py'
        spec = importlib.util.spec_from_file_location('accept_plan_messages', path)
        accept = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(accept)
        receipt = {'commands': []}
        with patch.object(accept.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['x'], 300)) as run:
            result = accept.run_tool(receipt, 'export', ['x'])
        self.assertEqual(run.call_args.kwargs['timeout'], accept.TOOL_TIMEOUT)
        self.assertEqual(result.returncode, 124)
        self.assertEqual(receipt['commands'][0]['exit_code'], 124)


class CompactInspect(Base):
    def test_inspect_output_prints_a_summary_and_saves_a_slim_snapshot(self):
        gh = self.use()
        gh.add(1, body='Body ![shot](https://x.example/a.png)')
        for n in (2, 3, 4):
            gh.add(n, status='Done', body='Prerequisite body')
        gh.deps[1] = {2, 3, 4}
        gh.comments[1] = [{'id': i, 'body': 'comment text ' * 20, 'user': {'login': 'creator', 'type': 'User', 'id': 1,
                           'avatar_url': 'a' * 300}, 'author_association': 'OWNER', 'created_at': 't', 'updated_at': 't',
                           'html_url': 'u', 'reactions': {'url': 'r' * 300}, 'node_id': 'n' * 40} for i in range(8)]
        snapshot = self.root / 'snap.json'
        out = io.StringIO()
        with patch.object(m, 'Scope', lambda root: self.app), contextlib.redirect_stdout(out):
            self.assertEqual(m.main(['inspect', '1', '--root', str(self.root), '--output', str(snapshot)]), 0)
        self.assertLess(len(out.getvalue().encode()), 2048)
        summary = json.loads(out.getvalue())
        self.assertEqual((summary['issue'], summary['comments'], summary['images']), (1, 8, 1))
        saved = m.read_json(snapshot)
        self.assertNotIn('reactions', saved['issue'])
        self.assertEqual(set(saved['comments'][0]['user']), {'login', 'type'})
        self.assertEqual(saved['prerequisites'][0]['body'], 'Prerequisite body')
        self.assertNotIn('issue', saved['prerequisites'][0])
        # Approve, publish and gate succeed from the slim snapshot file.
        tree = ts.node()
        analysis = {'issue': 1, 'fingerprint': saved['fingerprint'], 'requirements': ['AC-1'], 'alignment': 'Reuses tested behavior',
                    'evidence': ['src/feature.py:10'], 'images': [{'url': 'https://x.example/a.png', 'viewed': True,
                                                                     'observations': 'A form'}], 'tree': tree}
        self.app.approve(saved, analysis, 0, 'test owner', 'I approve this exact proposal.')
        self.app.publish(saved, analysis, True)
        self.assertEqual(self.app.gate('1', snapshot_path=snapshot)['issue'], 1)


class Listing(Base):
    def test_a_split_publish_lists_issues_once(self):
        gh = self.use()
        for n in range(10, 30):
            gh.add(n, body='Unrelated work')
        snap, analysis = self.analysis(True)
        self.app.approve(snap, analysis, 2, 'test owner', 'I approve this exact proposal.')
        gh.calls.clear()
        self.app.publish(snap, analysis, True)
        self.assertEqual(gh.calls[('GET', 'issues')], 1)  # three before SC14

    def test_paginated_reads_get_the_longer_timeout(self):
        seen = []

        def run(args, **kwargs):
            seen.append(kwargs['timeout'])
            return subprocess.CompletedProcess(args, 0, '[[]]' if '--paginate' in args else '{}', '')
        with patch.object(m.subprocess, 'run', side_effect=run):
            m.GitHub().api('repos/acme/app/issues', pages=True)
            m.GitHub().api('repos/acme/app/issues/1')
        self.assertEqual(seen, [m.PAGE_TIMEOUT, 30])


class AncestorReconcile(Base):
    def parent(self, n, children):
        receipt = {'version': 2, 'children': children, 'score': 8}
        self.gh.add(n, f'Parent {n}', m.replace_block('', 'Aggregate\n\n<!-- speckit-scope:metadata ' + json.dumps(receipt) + ' -->'))
        self.gh.children[n] = set(children)

    def tree(self, parents):
        """`parents` unrelated Scope parents with one child each, plus leaf 1 under parent 900 under 901."""
        gh = self.use()
        for i in range(parents):
            gh.add(1000 + i)
            self.parent(2000 + i, [1000 + i])
        self.parent(900, [1])
        self.parent(901, [900])
        self.app.reconcile(True)  # settle every table and status first
        self.app._board = None
        gh.calls.clear()
        return gh

    def test_the_hook_form_reconciles_only_the_issues_ancestors(self):
        gh = self.tree(3)
        self.gh.statuses[1] = 'Done'
        result = self.app.reconcile(True, '1')
        self.assertEqual([r['parent'] for r in result], [900, 901])
        self.assertEqual(self.gh.statuses[900], 'Done')
        self.assertEqual(self.gh.statuses[901], 'Done')
        self.assertEqual(self.gh.issues[901]['state'], 'closed')
        self.assertEqual(gh.calls[('GET', 'issues')], 0)
        self.assertEqual(gh.calls[('GET', 'N/sub_issues')], 2)

    def test_call_counts_full_sweep_and_chain(self):
        counts = {}
        for parents in (1, 10, 50):
            self.tearDown()
            self.setUp()
            gh = self.tree(parents)
            self.app.reconcile(True)
            full = gh.total()
            gh.calls.clear()
            self.app._board = None
            self.app.reconcile(True, '1')
            counts[parents] = (full, gh.total())
        # Nothing changes: a full sweep reads each parent's sub-issues once (no reread); the chain is constant.
        for parents, (full, chain) in counts.items():
            self.assertEqual(full, 1 + 1 + (parents + 2), parents)  # listing, board, sub_issues per parent
            self.assertEqual(chain, 1 + 3 + 2, parents)  # board, three parent reads, two sub_issues
        print('\n[SC15] calls (full sweep, chain) by unrelated parents:', counts)


class SpecifyOverlay(unittest.TestCase):
    def test_the_always_on_header_names_no_after_specify_chain(self):
        gate = (ROOT / 'presets/scope-gate/commands/specify-gate.md').read_text(encoding='utf-8')
        standalone = (ROOT / 'extensions/workflow/references/specify-standalone.md').read_text(encoding='utf-8')
        for word in ('after-specify', 'after_specify', 'Brainstorm', 'Project sync', 'Backlog'):
            self.assertNotIn(word, gate)
        self.assertIn('after-specify', standalone)
        self.assertIn('Without\n`.specify/workflow.yml`, also follow `.specify/extensions/workflow/references/specify-standalone.md`', gate)
        self.assertIn('no three-marker cap', gate)


if __name__ == '__main__':
    unittest.main()
