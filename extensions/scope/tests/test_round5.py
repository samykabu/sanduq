"""Round 5 Scope changes: the cancel command (SC21) and the client module on the shared transport (SC8)."""
import contextlib
import subprocess
import io
import json
import os
import unittest
from unittest.mock import patch

import test_scope as ts
from test_scope import m


class Cancel(unittest.TestCase):
    setUp, tearDown = ts.ScopeTests.setUp, ts.ScopeTests.tearDown
    analysis, publish_approved = ts.ScopeTests.analysis, ts.ScopeTests.publish_approved

    def interrupted(self):
        """A split publish that stopped after creating its first child; returns (analysis, operation id)."""
        self.gh.add(5, 'Dependent', body='Depends on #1')
        self.gh.deps[5] = {1}
        snap, analysis = self.analysis(True)
        self.gh.fail_once = '/sub_issues'
        with self.assertRaisesRegex(m.ScopeError, 'interruption'):
            self.publish_approved(snap, analysis)
        return snap, analysis, f'1-{m.analysis_hash(analysis)[:16]}'

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(m, 'Scope', return_value=self.app), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = m.main(list(argv) + ['--root', str(self.root)])
        return code, (json.loads(out.getvalue()) if out.getvalue() else err.getvalue())

    def test_cancel_marks_the_journal_and_prints_the_before_images(self):
        snap, analysis, operation = self.interrupted()
        writes = len(self.gh.writes)
        code, preview = self.cli('cancel', operation)
        self.assertEqual((code, preview['dry_run'], preview['rolled_back']), (0, True, False))
        code, result = self.cli('cancel', operation, '--apply')
        self.assertEqual((code, result['rolled_back'], result['published']), (0, True, False))
        self.assertEqual(len(self.gh.writes), writes)  # no GitHub write
        created = max(self.gh.issues)
        self.assertEqual(list(result['created'].values()), [created])
        self.assertEqual(result['before']['1']['body'], '')
        folder = f'.specify/scope/runs/{operation}'
        self.assertEqual(result['backups'], [f'{folder}/{name}' for name in
                                             ('snapshot.json', 'analysis.json', 'catalog-before.json', 'issue-map-before.json')])
        self.assertIn('dependencies_before', result)
        journal = m.read_json(self.root / folder / 'journal.json')
        self.assertTrue(journal['rolled_back'])
        with self.assertRaisesRegex(m.ScopeError, 'SCOPE_ROLLED_BACK'):
            self.publish_approved(self.app.inspect('1'), analysis)
        self.assertEqual(self.cli('cancel', operation, '--apply')[1]['rolled_back'], True)  # repeatable

    def test_cancel_refuses_ambiguous_unknown_and_outside_names(self):
        _, _, operation = self.interrupted()
        code, err = self.cli('cancel', '1')
        self.assertEqual(code, 2)
        self.assertIn('SCOPE_CANCEL_AMBIGUOUS', err)
        self.assertIn(operation, err)
        for bad in ('../1-0123456789abcdef', str(self.root / '.specify/scope/runs' / operation), 'plan-export-1', '1-abc', ''):
            code, err = self.cli('cancel', bad, '--apply')
            self.assertEqual(code, 2, bad)
            self.assertIn('SCOPE_CANCEL_OPERATION', err)
        code, err = self.cli('cancel', '1-0123456789abcdef', '--apply')
        self.assertIn('SCOPE_CANCEL_UNKNOWN', err)

    def test_cancel_refuses_a_journal_folder_that_leaves_the_runs_directory(self):
        outside = self.root / 'elsewhere'
        m.write_json(outside / 'journal.json', {'nodes': {}, 'before': {}, 'operation': '0123456789abcdef'})
        runs = self.root / '.specify/scope/runs'
        runs.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(outside, runs / '1-0123456789abcdef', target_is_directory=True)
        except OSError:
            self.skipTest('symbolic links unavailable')
        code, err = self.cli('cancel', '1-0123456789abcdef', '--apply')
        self.assertIn('SCOPE_CANCEL_UNKNOWN', err)
        self.assertNotIn('rolled_back', m.read_json(outside / 'journal.json'))

    def test_cancel_refuses_a_runs_directory_linked_outside_the_project(self):
        # Codex finding 6: with runs/ itself linked away, both sides of the folder check resolved outside and matched.
        import tempfile
        from pathlib import Path
        links = [('symlink', lambda target, link: os.symlink(target, link, target_is_directory=True))]
        if os.name == 'nt':
            import _winapi
            links.append(('junction', lambda target, link: _winapi.CreateJunction(str(target), str(link))))
        tested = 0
        for kind, make in links:
            with self.subTest(kind), tempfile.TemporaryDirectory() as elsewhere:
                outside = Path(elsewhere)
                journal = outside / '1-0123456789abcdef' / 'journal.json'
                m.write_json(journal, {'nodes': {}, 'before': {}, 'operation': '0123456789abcdef'})
                runs = self.root / '.specify/scope/runs'
                runs.parent.mkdir(parents=True, exist_ok=True)
                try:
                    make(outside, runs)
                except OSError:
                    continue
                try:
                    for argv in (('cancel', '1-0123456789abcdef', '--apply'), ('cancel', '1')):
                        code, err = self.cli(*argv)
                        self.assertEqual(code, 2, argv)
                        self.assertIn('resolves outside the project', err)
                    self.assertNotIn('rolled_back', m.read_json(journal))
                    tested += 1
                finally:
                    os.rmdir(runs) if os.name == 'nt' else os.unlink(runs)
        if not tested:
            self.skipTest('neither symbolic links nor junctions are available')

    def test_cancel_holds_the_mutation_lock(self):
        _, _, operation = self.interrupted()
        lock = self.root / '.specify/scope/mutation.lock'
        lock.write_text('123')
        code, err = self.cli('cancel', operation, '--apply')
        self.assertEqual(code, 2)
        self.assertIn('mutation is already running', err)
        self.assertNotIn('rolled_back', m.read_json(self.root / f'.specify/scope/runs/{operation}/journal.json'))


class PolicyCache(unittest.TestCase):
    """Round 3 leftovers in SC8: one parse per policy text, CSafeLoader when present, Workflow modules loaded once."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / '.specify').mkdir()
        self.policy = self.root / '.specify/workflow.yml'
        self.addCleanup(self.temp.cleanup)

    def test_policy_is_parsed_once_per_text_and_returned_as_a_copy(self):
        import yaml
        wp = m.workflow_policy
        self.policy.write_text('schema_version: 1\nscope:\n  board_cache_seconds: 30\n', encoding='utf-8')
        with patch.object(yaml, 'load', wraps=yaml.load) as parse:
            first = wp.load(self.root)
            first['scope']['board_cache_seconds'] = 1
            self.assertEqual(wp.setting(self.root, 'scope', 'board_cache_seconds'), 30)
            self.assertEqual(parse.call_count, 1)
            self.assertIs(parse.call_args.kwargs['Loader'], getattr(yaml, 'CSafeLoader', yaml.SafeLoader))
            self.policy.write_text('schema_version: 1\nscope:\n  board_cache_seconds: 40\n', encoding='utf-8')  # same size
            self.assertEqual(wp.setting(self.root, 'scope', 'board_cache_seconds'), 40)
            self.assertEqual(parse.call_count, 2)
            self.policy.write_text('schema_version: 2\n', encoding='utf-8')
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, 'Unsupported workflow policy'):
                    wp.load(self.root)
            self.policy.unlink()
            self.assertIsNone(wp.load(self.root))

    def test_workflow_modules_load_once_without_growing_sys_path(self):
        import sys
        wp = m.workflow_policy
        decisions, workflow = wp._decisions_module(), wp._workflow_module()
        size = len(sys.path)
        self.assertIs(wp._decisions_module(), decisions)
        self.assertIs(wp._workflow_module(), workflow)
        self.assertIsNotNone(workflow)
        self.assertEqual(len(sys.path), size)


class Transport(unittest.TestCase):
    """SC8: Scope's client lives in `sanduq_scope_github` on the shared `sanduq_gh` runner."""

    def test_scope_reexports_the_client_and_its_error(self):
        import sanduq_scope_github as client
        self.assertIs(m.GitHub, client.GitHub)
        self.assertIs(m.ProjectRest, client.ProjectRest)
        self.assertIs(m.ScopeError, client.GitHubError)
        self.assertIs(m.rate_limited, client.sanduq_gh.rate_limited)

    def test_a_get_is_retried_once_after_a_5xx_and_a_write_never(self):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 1, '', 'gh: Server Error (HTTP 502)')
        with patch.object(m.subprocess, 'run', side_effect=run), patch('sanduq_gh.time.sleep') as sleep:
            with self.assertRaisesRegex(m.ScopeError, r'GitHub request failed \(api repos/acme/app/issues/1 -H\): .*HTTP 502'):
                m.GitHub().api('repos/acme/app/issues/1')
            self.assertEqual((len(calls), sleep.call_count), (2, 1))
            calls.clear()
            with self.assertRaisesRegex(m.ScopeError, 'HTTP 502'):
                m.GitHub().api('repos/acme/app/issues/1', 'PATCH', {'body': 'x'})
            self.assertEqual(len(calls), 1)

    def test_timeout_and_missing_gh_are_scope_errors(self):
        with patch.object(m.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['gh'], 30)), patch('sanduq_gh.time.sleep'):
            with self.assertRaisesRegex(m.ScopeError, r'timed out \(api repos/acme/app/labels -H\) after 30 s'):
                m.GitHub().api('repos/acme/app/labels', 'POST', {'name': 'x'})
        with patch.object(m.subprocess, 'run', side_effect=FileNotFoundError('gh')):
            with self.assertRaisesRegex(m.ScopeError, 'gh CLI not installed'):
                m.GitHub().command(['project', 'item-list', '7'])

    def test_the_client_imports_without_scope_workflow_or_pyyaml(self):
        import shutil
        import sys
        import tempfile
        from pathlib import Path
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as folder:
            # The installed layout: both files side by side in an extension's scripts folder.
            for source in (root / 'extensions/scope/scripts/sanduq_scope_github.py', root / 'extensions/scripts/shared/sanduq_gh.py'):
                shutil.copy(source, folder)
            code = ('import sys; sys.modules["yaml"] = None; import sanduq_scope_github as c; '
                    'assert not {"scope", "workflow", "workflow_policy", "yaml"} & {k for k, v in sys.modules.items() if v}; '
                    'print(c.GitHub().project_transport)')
            done = subprocess.run([sys.executable, '-E', '-s', '-c', code], cwd=folder, capture_output=True, text=True)
            self.assertEqual((done.returncode, done.stdout.strip()), (0, 'None'), done.stderr)


if __name__ == '__main__':
    unittest.main()
