"""P03/P08/P12 execution helpers: each test fails if the named behavior breaks."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'execution_tools.py'
sys.path.insert(0, str(SCRIPT.parent))
import execution_tools as et  # noqa: E402

NOW = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, name, data):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
        return path

    def manifest(self, **content):
        return self.write('m.json', json.dumps(content))


class PreflightTests(Base):
    def failed(self, **content):
        return et.preflight(self.manifest(**content))['failed']

    def test_encoding_and_newlines(self):
        self.write('ok.txt', 'a\nb\n')
        self.write('crlf.txt', 'a\r\nb\n')
        self.write('bad.txt', b'\xff\xfe')
        self.write('bom.txt', b'\xef\xbb\xbfx\n')
        files = [{'path': n, 'newlines': 'lf'} for n in ('ok.txt', 'crlf.txt', 'bad.txt', 'bom.txt')]
        self.assertEqual(self.failed(files=files), ['file:crlf.txt', 'file:bad.txt', 'file:bom.txt'])

    def test_identity_hash_and_stale_fixture_binary(self):
        src = self.write('src.c', 'x')
        binary = self.write('fixture.bin', 'b')
        os.utime(binary, (1, 1))
        digest = et.sha256_file(src)
        ids = [{'name': 'src', 'kind': 'source', 'path': 'src.c', 'sha256': digest},
               {'name': 'wrong', 'kind': 'base', 'path': 'src.c', 'sha256': '0' * 64},
               {'name': 'fix', 'kind': 'fixture', 'path': 'fixture.bin', 'built_from': ['src.c']}]
        self.assertEqual(self.failed(identities=ids), ['identity:wrong', 'identity:fix'])
        detail = et.preflight(self.manifest(identities=ids))['checks'][2]['detail']
        self.assertIn('stale', detail)

    def test_identity_without_proof_is_malformed(self):
        self.write('a', 'x')
        with self.assertRaises(et.InputError):
            et.preflight(self.manifest(identities=[{'name': 'a', 'kind': 'source', 'path': 'a'}]))

    def test_commands(self):
        cmds = [{'name': 'py', 'executable': sys.executable, 'args': ['-m', 'unittest'], 'required_args': ['-m']},
                {'name': 'nope', 'executable': 'definitely-not-installed-xyz', 'args': []},
                {'name': 'empty', 'executable': sys.executable, 'args': ['']},
                {'name': 'req', 'executable': sys.executable, 'args': [], 'required_args': ['--x']},
                {'name': 'forb', 'executable': sys.executable, 'args': ['--force'], 'forbidden_args': ['--force']}]
        self.assertEqual(self.failed(commands=cmds), ['command:nope', 'command:empty', 'command:req', 'command:forb'])

    def test_interpreter_requires_script_module_or_code_before_execution(self):
        for args in ([], ['-m'], ['-c'], ['-u', 'missing-checker.py']):
            self.assertFalse(et.check_command({'name': 'python', 'executable': sys.executable, 'args': args})['ok'])

    def test_manifest_command_paths_use_manifest_directory_and_refuse_caller_decoys(self):
        caller = self.dir / 'caller'
        caller.mkdir()
        self.write('project/check.py', 'print("project checker")')
        executable = self.write('project/tools/python.exe', 'declared executable')
        self.write('caller/check.py', 'print("unrelated checker")')
        self.write('caller/tools/python.exe', 'unrelated executable')
        manifest = self.write('project/checks.json', json.dumps({'commands': [
            {'name': 'local', 'executable': 'tools/python.exe', 'args': ['check.py']}]}))
        with chdir(caller):
            self.assertTrue(et.preflight(manifest)['ok'])
            # A caller-local executable with the same relative name is insufficient.
            executable.unlink()
            self.assertFalse(et.preflight(manifest)['ok'])
            executable.write_text('declared executable', encoding='utf-8')
            # Likewise, a caller-local script cannot satisfy the manifest guard.
            (manifest.parent / 'check.py').unlink()
            self.assertFalse(et.preflight(manifest)['ok'])

    def test_manifest_path_lookup_and_direct_command_compatibility(self):
        script = self.write('project/check.py', '# checker')
        manifest = self.write('project/checks.json', json.dumps({'commands': [
            {'name': 'path', 'executable': Path(sys.executable).name, 'args': ['check.py']}]}))
        self.write(Path(sys.executable).name, 'caller-local decoy')
        with chdir(self.dir), patch.object(et.os, 'get_exec_path', return_value=[str(Path(sys.executable).parent)]), \
                patch.object(et.check_inputs, 'command_input', wraps=et.check_inputs.command_input) as guard:
            self.assertTrue(et.preflight(manifest)['ok'])
            self.assertEqual(Path(guard.call_args.args[1][0]), Path(sys.executable))
        with chdir(self.dir), patch.object(et.os, 'get_exec_path', return_value=[str(self.dir / 'absent-path')]):
            self.assertFalse(et.preflight(manifest)['ok'])
        with chdir(script.parent):
            self.assertTrue(et.check_command({'name': 'direct', 'executable': sys.executable,
                                              'args': ['check.py']})['ok'])
        self.write('project/python.exe', 'local interpreter')
        with patch.object(et.shutil, 'which', side_effect=AssertionError('local executable needs no PATH lookup')):
            self.assertTrue(et.check_command({'name': 'bare-local', 'executable': 'python.exe',
                                              'args': ['check.py']}, script.parent)['ok'])

    def test_browser_existence(self):
        self.write('chrome', 'x')
        b = [{'name': 'a', 'path': 'chrome'}, {'name': 'b', 'path': 'gone'}]
        self.assertEqual(self.failed(browsers=b), ['browser:b'])

    def runtime(self, status, **spec):
        self.write('rt.json', status if isinstance(status, str) else json.dumps(status))
        return et.preflight(self.manifest(runtime_status=dict(
            {'path': 'rt.json', 'owner': 'me', 'state': 'running'}, **spec)))

    def test_runtime_status_strict(self):
        self.assertTrue(self.runtime({'owner': 'me', 'state': 'running', 'pid': 4})['ok'])
        for bad in ({'owner': 'me', 'state': 'running'},                      # running needs pid
                    {'owner': 'me', 'state': 'running', 'pid': True},
                    {'owner': 'me', 'state': 'running', 'pid': 4, 'extra': 1},
                    {'owner': 'other', 'state': 'running', 'pid': 4},
                    {'owner': 'me', 'state': 'stopped'},
                    [1], '{broken'):
            self.assertFalse(self.runtime(bad)['ok'], bad)

    def test_malformed_manifests(self):
        for bad in ('[]', '{}', '{"files": {}}', '{"unknown": 1}', '{"files": [{}]}', 'nope'):
            self.write('m.json', bad)
            with self.assertRaises(et.InputError, msg=bad):
                et.preflight(self.dir / 'm.json')
        with self.assertRaises(et.InputError):
            et.preflight(self.dir / 'absent.json')


class ScopeCommandTests(unittest.TestCase):
    """The printed commands are run through Scope's real parser and main(); only the GitHub-facing
    Scope class is replaced by a recorder, so flag spelling and routing are checked natively."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scope' / 'scripts'))
        import scope
        import workflow_policy
        cls.scope, cls.policy = scope, workflow_policy

    def run_scope(self, printed):
        import shlex
        from unittest import mock
        calls = []

        class Recorder:
            gh = None
            repo = 'o/r'

            def __init__(self, root):
                self.root = Path(root)

            def gate(self, issue, *a, **kw):
                calls.append(('gate', issue, kw))
                return {'issue': 1}

            def bind(self, issue, apply=False, **kw):
                calls.append(('bind', issue, dict(kw, apply=apply)))
                return {'issue': 1}

        argv = shlex.split(printed)[2:]
        with mock.patch.object(self.scope, 'Scope', Recorder), mock.patch.object(self.scope, 'write_json', create=True),                 mock.patch.object(sys, 'stdout', new=__import__('io').StringIO()),                 mock.patch.object(self.policy, 'fresh_claim', lambda *a, **k: {}):
            previous = os.getcwd()
            with tempfile.TemporaryDirectory() as scratch:
                os.chdir(scratch)  # --apply takes a mutation lock under the root
                try:
                    code = self.scope.main(argv)
                finally:
                    os.chdir(previous)
        return code, calls

    def test_initial_gate_and_bind_reach_scope_with_every_claim_flag(self):
        for command in ('gate', 'bind'):
            printed = et.scope_command('initial', command, '8', 'specs/001-x', 'tok', 'ses', 'a b.json')['command']
            code, calls = self.run_scope(printed)
            self.assertEqual(code, 0, printed)
            name, issue, kw = calls[0]
            self.assertEqual((name, issue), (command, '8'))
            self.assertEqual((kw['feature'], kw['token'], kw['session']), ('specs/001-x', 'tok', 'ses'))
            self.assertEqual(str(kw['analysis_path']), 'a b.json')
            if command == 'bind':
                self.assertTrue(kw['apply'])

    def test_revalidate_reaches_scope_with_no_claim_flags(self):
        for command in ('gate', 'bind'):
            code, calls = self.run_scope(et.scope_command('revalidate', command, 8)['command'])
            self.assertEqual(code, 0)
            kw = calls[0][2]
            self.assertEqual((kw['feature'], kw['token'], kw['session']), (None, None, None))
            if command == 'bind':
                self.assertTrue(kw['apply'])

    def test_scope_itself_rejects_the_old_guess_of_feature_only(self):
        with self.assertRaises(ValueError) as caught:
            self.policy.fresh_claim(Path('.'), 'o/r', 8, 'specs/001-x', None, None)
        self.assertIn('SCOPE_WORKFLOW_BINDING_REQUIRED', str(caught.exception))

    def test_rejections(self):
        for args in (('initial', 'gate', '8', 'f', None, 's', 'a.json'), ('initial', 'bind', '8', 'f', 't', 's'),
                     ('revalidate', 'gate', '8', 'f'), ('revalidate', 'bind', '8', None, 't'),
                     ('initial', 'gate', '#8', 'f', 't', 's', 'a'), ('initial', 'gate', '0', 'f', 't', 's', 'a'),
                     ('later', 'gate', '8'), ('initial', 'plan', '8', 'f', 't', 's', 'a')):
            with self.assertRaises(et.InputError, msg=args):
                et.scope_command(*args)


class PrLintTests(unittest.TestCase):
    def lint(self, body, prereq=(3,)):
        return et.pr_lint(body, 'Acme/App', 8, prereq)

    def codes(self, body, prereq=(3,)):
        return [v['code'] for v in self.lint(body, prereq)['violations']]

    def test_bound_issue_allowed_in_all_forms(self):
        for body in ('Closes #8', 'fixes: acme/app#8', 'Resolved https://github.com/acme/app/issues/8',
                     'No closing words, refs #3 and #9'):
            self.assertTrue(self.lint(body)['ok'], body)

    def test_rejections(self):
        self.assertEqual(self.codes('Closes #3'), ['PREREQUISITE_CLOSE'])
        self.assertEqual(self.codes('Fixes other/repo#8'), ['FOREIGN_REPO_CLOSE'])
        self.assertEqual(self.codes('resolves https://github.com/other/x/issues/3'), ['FOREIGN_REPO_CLOSE'])
        self.assertEqual(self.codes('Closes #8\nfix #9'), ['UNBOUND_ISSUE_CLOSE'])

    def test_code_spans_do_not_count(self):
        self.assertTrue(self.lint('Closes #8\n```\ncloses #3\n```\nand `fixes #4`')['ok'])

    def test_body_hash_and_receipt_output_file(self):
        out = self.dir_out = tempfile.mkdtemp()
        self.addCleanup(__import__('shutil').rmtree, out, True)
        target = Path(out) / 'lint.json'
        proc = subprocess.run([sys.executable, str(SCRIPT), 'pr-lint', '--repo', 'a/b', '--issue', '8', '--body',
                               'Closes #8', '--output', str(target)], capture_output=True, text=True, encoding='utf-8')
        written = json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual(written, json.loads(proc.stdout))
        self.assertEqual(written['body_sha256'], __import__('hashlib').sha256(b'Closes #8').hexdigest())

    def test_pr_generate_procedure_lints_before_any_github_write(self):
        text = (Path(__file__).resolve().parents[2] / 'pr/commands/speckit.pr.generate.md').read_text(encoding='utf-8')
        # PM21: PR bundles the shared sanduq_pr_lint rule, so the text no longer names execution_tools.py.
        lint = text.index('lints its closing references')
        self.assertLess(lint, text.index('gh pr edit'))
        self.assertLess(lint, text.index('gh pr create'))
        self.assertIn('after a nonzero exit', ' '.join(text.split()))

    def test_cli_exit_codes(self):
        run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), 'pr-lint', '--repo', 'a/b', '--issue', '8', *a],
                                        capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run('--body', 'closes #8').returncode, 0)
        bad = run('--body', 'closes #3', '--prerequisite', '3')
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)['violations'][0]['code'], 'PREREQUISITE_CLOSE')
        self.assertEqual(run('--body-file', 'missing.md').returncode, 2)


class ProgressTests(Base):
    def final(self, rel, **fields):
        data = {'run_id': 'r1', 'harness': 'codex', 'status': 'successful', 'started_at': '2026-10-12T09:00:00Z',
                'ended_at': '2026-10-12T10:00:00Z',
                'tokens': {'input_total': 10, 'input_fresh': 4, 'cache_read': 6, 'cache_write': 1,
                           'output_total': 3, 'reasoning': 2, 'fidelity': 'exact', 'total': 13}}
        data.update(fields)
        return self.write(rel + '/result.json', json.dumps(data))

    def live(self, rel, run_id, events, started='2026-10-12T11:00:00Z', harness='claude'):
        self.write(rel + '/meta.json', json.dumps({'run_id': run_id, 'harness': harness, 'started_at': started,
                                                   'task': 'SECRET PROMPT TEXT'}))
        self.write(rel + '/journal.jsonl', '\n'.join(json.dumps(e) for e in events) + '\n')
        self.write(rel + '/stdout.log', '{"run_id": "leak", "state": "terminal", "t": "2026-10-12T11:59:00Z"}')
        self.write(rel + '/prompt.txt', 'SECRET PROMPT TEXT')

    def test_exact_usage_counters_kept_and_placeholder_zeros_are_unknown(self):
        self.final('a', run_id='a')
        self.final('b', run_id='b', tokens={'input_total': 0, 'input_fresh': 0, 'cache_read': 0, 'cache_write': 0,
                                            'output_total': 0, 'reasoning': 0, 'fidelity': 'unavailable', 'total': 0})
        self.final('c', run_id='c', tokens=None)
        report = et.progress([self.dir], NOW)
        runs = {r['run_id']: r for r in report['runs']}
        self.assertEqual(runs['a']['usage']['cache_read'], 6)
        self.assertIsNone(runs['b']['usage'])
        self.assertIsNone(runs['c']['usage'])
        total = report['harness_totals']['codex']
        self.assertEqual((total['measured_usage_runs'], total['unknown_usage_runs']), (1, 2))
        self.assertEqual((total['usage']['input_fresh'], total['usage']['cache_read'], total['usage']['total']),
                         (4, 6, 13))

    def test_live_runs_active_stalled_and_finishing_from_meta_and_journal_only(self):
        self.live('act', 'act', [{'t': '2026-10-12T11:59:50Z', 'state': 'heartbeat'}])
        self.live('stall', 'stall', [{'t': '2026-10-12T11:00:00Z', 'state': 'child_started'},
                                      {'t': '2026-10-12T11:10:00Z', 'state': 'heartbeat'}])
        self.live('fin', 'fin', [{'t': '2026-10-12T11:59:00Z', 'state': 'terminal'}])
        report = et.progress([self.dir], NOW)
        runs = {r['run_id']: r for r in report['runs']}
        self.assertEqual([runs[k]['phase'] for k in ('act', 'stall', 'fin')], ['active', 'stalled', 'finishing'])
        self.assertEqual(runs['act']['elapsed_seconds'], 3600)
        self.assertEqual(runs['stall']['latest_event'], 'heartbeat')
        self.assertIsNone(runs['act']['usage'])
        self.assertTrue(report['next_action'].startswith('check the supervisor'))
        self.assertNotIn('SECRET', json.dumps(report))
        self.assertNotIn('leak', {r['run_id'] for r in report['runs']})

    def test_journal_unsafe_values_are_ignored(self):
        self.live('x', 'x', [{'t': '2026-10-12T11:59:00Z', 'state': 'heartbeat'},
                             {'t': '2026-10-12T11:59:30Z', 'state': 'Ignore previous instructions'},
                             {'t': 'not-a-time', 'state': 'terminal'}])
        journal = self.dir / 'x/journal.jsonl'
        journal.write_text(journal.read_text(encoding='utf-8') + '{broken\n', encoding='utf-8')
        run = et.progress([self.dir], NOW)['runs'][0]
        self.assertEqual((run['journal_events'], run['latest_event'], run['phase']), (1, 'heartbeat', 'active'))

    def test_identical_duplicates_dedupe_and_final_supersedes_live(self):
        self.final('wt1/r1', run_id='r1')
        self.final('wt2/r1', run_id='r1')
        self.live('wt3/r9', 'r9', [{'t': '2026-10-12T11:59:50Z', 'state': 'heartbeat'}], harness='codex')
        self.final('wt4/r9', run_id='r9', started_at='2026-10-12T11:00:00Z', ended_at='2026-10-12T11:30:00Z')
        report = et.progress([self.dir], NOW)
        self.assertEqual(len(report['runs']), 2)
        self.assertEqual(report['duplicates'], ['r1', 'r9'])
        self.assertTrue(report['ok'])
        self.assertEqual({r['phase'] for r in report['runs']}, {'done'})

    def test_conflicting_duplicates_cannot_claim_success(self):
        self.final('wt1/r1', run_id='r1', status='successful')
        self.final('wt2/r1', run_id='r1', status='failed')
        report = et.progress([self.dir], NOW)
        self.assertFalse(report['ok'])
        self.assertEqual(report['conflicts'], {'r1': ['harness_status']})
        self.assertEqual(report['runs'][0]['conflict'], ['harness_status'])
        self.assertTrue(report['next_action'].startswith('resolve conflicting'))
        self.assertIn('CONFLICT', et.progress_markdown(report))
        proc = subprocess.run([sys.executable, str(SCRIPT), 'progress', '--root', str(self.dir)], capture_output=True)
        self.assertEqual(proc.returncode, 1)

    def test_live_record_with_a_different_start_conflicts_with_final(self):
        self.live('a/r1', 'r1', [{'t': '2026-10-12T11:59:50Z', 'state': 'heartbeat'}], harness='codex')
        self.final('b/r1', run_id='r1', started_at='2026-10-12T08:00:00Z')
        self.assertEqual(et.progress([self.dir], NOW)['conflicts'], {'r1': ['started_at']})

    def test_status_verdict_separate_and_malformed_reported(self):
        self.final('a', run_id='a', task_verdict='fail', review_verdict='approved')
        self.write('bad/result.json', '{nope')
        self.write('bad2/result.json', '{"harness": "x"}')
        self.write('bad3/meta.json', '[]')
        report = et.progress([self.dir], NOW)
        run = report['runs'][0]
        self.assertEqual((run['harness_status'], run['task_verdict'], run['review_verdict']),
                         ('successful', 'fail', 'approved'))
        self.assertEqual(len(report['malformed']), 3)
        self.assertFalse(report['ok'])

    def test_missing_root_and_markdown(self):
        with self.assertRaises(et.InputError):
            et.progress([self.dir / 'nope'], NOW)
        self.final('m', run_id='m', tokens=None)
        md = et.progress_markdown(et.progress([self.dir], NOW))
        self.assertIn('| m | codex | successful | unknown | unknown | unknown | 3600s |', md)

    PILOT = Path(__file__).resolve().parents[3] / '.delegate' / 'pilot-history'

    @unittest.skipUnless((PILOT / 'claude-20261010165502-2fc5bb').is_dir(), 'pilot history is local, ignored data')
    def test_pilot_history_counts(self):
        report = et.progress([self.PILOT], NOW)
        self.assertTrue(report['ok'], report['conflicts'])
        self.assertEqual(len(report['runs']), 121)
        self.assertEqual(report['duplicates'], [])
        status = {}
        for r in report['runs']:
            status[r['harness_status']] = status.get(r['harness_status'], 0) + 1
        self.assertEqual(status, {'successful': 90, 'failed': 17, 'abandoned': 14})
        self.assertEqual({k: v['runs'] for k, v in report['harness_totals'].items()}, {'codex': 61, 'claude': 60})
        self.assertEqual(sum(v['unknown_usage_runs'] for v in report['harness_totals'].values()), 13)
        self.assertEqual(sum(v['measured_usage_runs'] for v in report['harness_totals'].values()), 108)


class CliTests(unittest.TestCase):
    def test_help_and_contracts(self):
        for args in (['--help'], ['preflight', '--help'], ['progress', '--help']):
            self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True).returncode, 0)
        out = subprocess.run([sys.executable, str(SCRIPT), 'contracts'], capture_output=True, text=True, encoding='utf-8')
        contract = json.loads(out.stdout)
        self.assertEqual(contract['progress']['schema'], et.PROGRESS_SCHEMA)
        self.assertEqual(contract['evidence']['max_records'], et.evidence_snapshot.MAX_RECORDS)
        self.assertEqual(contract['evidence']['max_payload_bytes'], et.evidence_snapshot.MAX_TOTAL_BYTES)
        self.assertEqual(contract['evidence']['max_snapshot_bytes'], et.evidence_snapshot.MAX_BYTES)

    def test_malformed_cli_exits_2(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), 'preflight', '--manifest', 'missing.json'],
                              capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(json.loads(proc.stdout)['ok'])


if __name__ == '__main__':
    unittest.main()
