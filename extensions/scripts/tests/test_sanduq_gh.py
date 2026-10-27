"""The shared `gh` transport (SC8 / X22): every error shape, the opt-in retry rule and its classification of safe
reads, and GraphQL errors on a successful exit. Archive copies and the installed-layout import are pinned with
the other shared helpers in test_sanduq_remote.py."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shared'))
import sanduq_gh as gh  # noqa: E402


def done(returncode=0, stdout='', stderr=''):
    return subprocess.CompletedProcess(['gh'], returncode, stdout, stderr)


class Fake:
    """Answers `subprocess.run` from a script of results; an exception class or instance is raised."""

    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        result = self.results.pop(0)
        if isinstance(result, BaseException) or (isinstance(result, type) and issubclass(result, BaseException)):
            raise result
        return result


class Base(unittest.TestCase):
    def fake(self, *results):
        fake = Fake(*results)
        run = mock.patch.object(gh.subprocess, 'run', fake)
        sleep = mock.patch.object(gh.time, 'sleep')
        path = mock.patch.object(gh, 'GH', 'gh')  # the argv assertions name the bare tool
        run.start()
        path.start()
        self.addCleanup(path.stop)
        self.sleep = sleep.start()
        self.addCleanup(run.stop)
        self.addCleanup(sleep.stop)
        return fake


class ErrorShapes(Base):
    def test_missing_gh_is_127(self):
        self.fake(FileNotFoundError())
        with self.assertRaises(gh.GhError) as caught:
            gh.run_gh(['auth', 'status'])
        self.assertEqual((caught.exception.returncode, caught.exception.timeout), (gh.GH_MISSING, False))
        self.assertEqual(str(caught.exception), 'gh CLI not installed')

    def test_timeout_is_flagged_and_names_the_call(self):
        self.fake(subprocess.TimeoutExpired(['gh'], 60))
        with self.assertRaises(gh.GhError) as caught:
            gh.run_gh(['api', 'repos/a/b'], timeout=7)
        error = caught.exception
        self.assertTrue(error.timeout)
        self.assertIsNone(error.returncode)
        self.assertEqual(str(error), 'timeout: gh api repos/a/b gave no answer in 7 s')

    def test_failure_keeps_returncode_streams_and_a_short_message(self):
        self.fake(done(1, '{"message":"Not Found"}', 'gh: Not Found (HTTP 404)\n'))
        with self.assertRaises(gh.GhError) as caught:
            gh.run_gh(['api', 'repos/a/b'])
        error = caught.exception
        self.assertEqual((error.returncode, error.stdout, error.rate_limited), (1, '{"message":"Not Found"}', False))
        self.assertEqual(error.stderr, 'gh: Not Found (HTTP 404)\n')
        self.assertEqual(str(error), 'gh api repos/a/b failed: gh: Not Found (HTTP 404)')
        self.assertIsNone(error.reset_at)

    def test_rate_limit_message_sets_rate_limited(self):
        for text in ('API rate limit exceeded for user', 'RATE_LIMITED', 'secondary rate-limit'):
            with self.subTest(text=text):
                self.fake(done(1, '', text))
                with self.assertRaises(gh.GhError) as caught:
                    gh.run_gh(['api', 'graphql'])
                self.assertTrue(caught.exception.rate_limited)

    def test_rate_limited_and_token_scopes(self):
        self.assertTrue(gh.rate_limited('You have exceeded a secondary rate limit'))
        self.assertFalse(gh.rate_limited(None))
        self.assertFalse(gh.rate_limited('rated limits'))
        auth = "  - Token: gho_x\n  - Token scopes: 'gist', 'read:org', 'read:project', 'repo'\n"
        self.assertEqual(gh.token_scopes(auth), {'gist', 'read:org', 'read:project', 'repo'})
        self.assertNotIn('project', gh.token_scopes(auth))
        self.assertEqual(gh.token_scopes(None), set())

    def test_graphql_errors_on_exit_zero_raise(self):
        body = {'data': None, 'errors': [{'type': 'NOT_FOUND', 'message': 'Could not resolve'}]}
        self.fake(done(0, json.dumps(body)))
        with self.assertRaises(gh.GhError) as caught:
            gh.graphql('query{viewer{login}}')
        error = caught.exception
        self.assertEqual((error.returncode, error.rate_limited), (0, False))
        self.assertIn('Could not resolve', str(error))

    def test_graphql_rate_limit_on_exit_zero_is_flagged(self):
        self.fake(done(0, json.dumps({'errors': [{'type': 'RATE_LIMITED', 'message': 'quota'}]})))
        with self.assertRaises(gh.GhError) as caught:
            gh.graphql('query{viewer{login}}')
        self.assertTrue(caught.exception.rate_limited)


class Calls(Base):
    def test_graphql_sends_query_and_variables_on_stdin(self):
        fake = self.fake(done(0, '{"data":{"viewer":{"login":"me"}}}'))
        self.assertEqual(gh.graphql('query($n:Int!){x}', n=3, cwd='/w'), {'viewer': {'login': 'me'}})
        argv, kwargs = fake.calls[0]
        self.assertEqual(argv, ['gh', 'api', 'graphql', '--input', '-'])
        self.assertEqual(json.loads(kwargs['input']), {'query': 'query($n:Int!){x}', 'variables': {'n': 3}})
        self.assertEqual((kwargs['timeout'], kwargs['cwd']), (60, '/w'))

    def test_api_builds_arguments_and_flattens_pages(self):
        fake = self.fake(done(0, '[[1,2],[3]]'), done(0, ''), done(0, '[{"total_count":1}]'))
        self.assertEqual(gh.api('repos/a/b/issues', pages=True, timeout=120), [1, 2, 3])
        self.assertIsNone(gh.api('repos/a/b/issues/1', method='PATCH', payload={'body': 'x'}))
        self.assertEqual(gh.api('search/issues', pages=True), [{'total_count': 1}])
        self.assertEqual(fake.calls[0][0], ['gh', 'api', 'repos/a/b/issues', '-H', 'Accept: application/vnd.github+json',
                                            '--paginate', '--slurp'])
        self.assertEqual(fake.calls[0][1]['timeout'], 120)
        self.assertEqual(fake.calls[1][0][-4:], ['--method', 'PATCH', '--input', '-'])
        self.assertEqual(json.loads(fake.calls[1][1]['input']), {'body': 'x'})

    def test_binary_returns_bytes_and_text_payload_passes_through(self):
        fake = self.fake(subprocess.CompletedProcess(['gh'], 0, b'PK\x03\x04', b''), done(0, 'ok'))
        self.assertEqual(gh.run_gh(['api', 'repos/a/b/actions/artifacts/1/zip'], binary=True, timeout=300), b'PK\x03\x04')
        self.assertNotIn('text', fake.calls[0][1])
        self.assertEqual(gh.run_gh(['issue', 'comment', '1', '--body-file', '-'], payload='plain'), 'ok')
        self.assertEqual(fake.calls[1][1]['input'], 'plain')


class Retry(Base):
    BAD_GATEWAY = done(1, '', 'gh: HTTP 502: Bad Gateway (https://api.github.com/x)')

    def test_safe_get_is_retried_once_after_a_5xx_or_a_timeout(self):
        for first in (self.BAD_GATEWAY, subprocess.TimeoutExpired(['gh'], 60)):
            with self.subTest(first=type(first).__name__):
                fake = self.fake(first, done(0, '{"id":1}'))
                self.assertEqual(gh.api('repos/a/b', retry=True), {'id': 1})
                self.assertEqual(len(fake.calls), 2)
                self.sleep.assert_called_once_with(2)

    def test_second_failure_is_raised_without_a_third_call(self):
        fake = self.fake(self.BAD_GATEWAY, self.BAD_GATEWAY)
        with self.assertRaises(gh.GhError):
            gh.run_gh(['api', 'repos/a/b'], retry=True)
        self.assertEqual(len(fake.calls), 2)

    def test_no_retry_by_default_or_for_other_failures(self):
        for kwargs, first in (({}, self.BAD_GATEWAY),
                              ({'retry': True}, done(1, '', 'gh: Not Found (HTTP 404)')),
                              ({'retry': True}, done(1, '', 'API rate limit exceeded (HTTP 403)'))):
            with self.subTest(kwargs=kwargs, stderr=first.stderr):
                fake = self.fake(first)
                with self.assertRaises(gh.GhError):
                    gh.run_gh(['api', 'repos/a/b'], **kwargs)
                self.assertEqual(len(fake.calls), 1)
                self.sleep.assert_not_called()

    def test_writes_are_never_retried_even_when_asked(self):
        timeout = subprocess.TimeoutExpired(['gh'], 60)
        cases = {
            'POST': lambda: gh.api('repos/a/b/issues', method='POST', payload={'title': 't'}, retry=True),
            'PATCH': lambda: gh.api('repos/a/b/issues/1', method='PATCH', payload={}, retry=True),
            'DELETE': lambda: gh.api('repos/a/b/labels/x', method='DELETE', retry=True),
            'GET with a body': lambda: gh.api('repos/a/b', payload={'q': 1}, retry=True),
            'field': lambda: gh.run_gh(['api', 'repos/a/b/labels', '-f', 'name=x'], retry=True),
            'typed field': lambda: gh.run_gh(['api', 'repos/a/b/labels', '-F', 'n=1'], retry=True),
            'input file': lambda: gh.run_gh(['api', 'repos/a/b/labels', '--input', 'body.json'], retry=True),
            '-XPOST': lambda: gh.run_gh(['api', '-XPOST', 'repos/a/b/labels'], retry=True),
            '--method=PUT': lambda: gh.run_gh(['api', '--method=PUT', 'repos/a/b/x'], retry=True),
            'mutation': lambda: gh.graphql('mutation{addStar(input:{starrableId:"x"}){clientMutationId}}', retry=True),
            'named mutation': lambda: gh.graphql('  # add\nmutation Add($p:ID!){x}', retry=True, p='1'),
            'mutation field': lambda: gh.run_gh(['api', 'graphql', '-f', 'query=mutation{x}'], retry=True),
            'query from file': lambda: gh.run_gh(['api', 'graphql', '-F', 'query=@q.graphql'], retry=True),
            # Codex review finding 1: an option form the classifier does not recognise is never retried.
            'clustered -iXPOST': lambda: gh.run_gh(['api', 'repos/a/b/actions/runs/1/rerun', '-iXPOST'], retry=True),
            'clustered -if': lambda: gh.run_gh(['api', 'repos/a/b/labels', '-if', 'name=x'], retry=True),
            'unknown flag': lambda: gh.run_gh(['api', 'repos/a/b', '--future-flag'], retry=True),
            'unknown --x=y': lambda: gh.run_gh(['api', 'repos/a/b', '--future=POST'], retry=True),
            'end of options': lambda: gh.run_gh(['api', '--', 'repos/a/b'], retry=True),
            'second positional': lambda: gh.run_gh(['api', 'repos/a/b', 'extra'], retry=True),
            'gh project': lambda: gh.run_gh(['project', 'item-list', '1', '--format', 'json'], retry=True),
            'gh issue': lambda: gh.run_gh(['issue', 'view', '1'], retry=True),
        }
        for name, call in cases.items():
            for first in (self.BAD_GATEWAY, timeout):
                with self.subTest(name=name, first=type(first).__name__):
                    fake = self.fake(first)
                    with self.assertRaises(gh.GhError):
                        call()
                    self.assertEqual(len(fake.calls), 1)
                    self.sleep.assert_not_called()

    def test_graphql_queries_are_safe_reads(self):
        fake = self.fake(self.BAD_GATEWAY, done(0, '{"data":{"rateLimit":{"remaining":5}}}'))
        self.assertEqual(gh.graphql('query{rateLimit{remaining}}', retry=True), {'rateLimit': {'remaining': 5}})
        self.assertEqual(len(fake.calls), 2)
        self.assertTrue(gh.safe_read(['api', 'graphql', '-f', 'query={rateLimit{remaining resetAt}}']))
        self.assertTrue(gh.safe_read(['api', 'graphql', '-f', 'query=query($l:String!){x}', '-f', 'l=me']))
        self.assertTrue(gh.safe_read(['api', 'repos/a/b/pulls', '-H', 'Accept: x', '--paginate', '--slurp', '-q', '.[]']))
        self.assertTrue(gh.safe_read(['api', '-X', 'GET', 'repos/a/b']))
        self.assertTrue(gh.safe_read(['api', '-XGET', 'repos/a/b', '-i', '--include', '--silent', '--verbose',
                                      '--jq=.x', '--hostname', 'github.com']))
        self.assertFalse(gh.safe_read(['api', 'graphql']))
        self.assertFalse(gh.safe_read(['api', 'graphql', '-X', 'GET', '-f', 'query={x}']))
        self.assertFalse(gh.safe_read([]))


class ToolPath(unittest.TestCase):
    def test_windows_search_reads_path_only_so_a_tool_in_the_current_directory_cannot_win(self):
        """SEC-15: a gh.exe committed in a cloned repository must not shadow the installed one."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            cwd, on_path = Path(folder, 'repo'), Path(folder, 'bin')
            cwd.mkdir(), on_path.mkdir()
            (cwd / 'gh.exe').write_bytes(b'')
            (on_path / 'gh.cmd').write_bytes(b'')
            env = {'PATH': str(on_path), 'PATHEXT': '.EXE;.CMD'}
            with mock.patch.object(gh.os, 'name', 'nt'), mock.patch.dict(gh.os.environ, env, clear=True):
                old = os.getcwd()
                os.chdir(cwd)
                try:
                    self.assertEqual(gh.tool_path('gh'), str(on_path / 'gh.cmd'))
                    self.assertEqual(gh.tool_path('missing'), 'missing')
                finally:
                    os.chdir(old)


if __name__ == '__main__':
    unittest.main()
