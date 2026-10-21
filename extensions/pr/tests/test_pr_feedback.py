"""PM2a: pr_feedback.py gather pages the review threads, filters resolved, outdated, author-only and
chatter items, and never calls a writing gh command. gh is replaced by a fake."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pr_feedback  # noqa: E402

WRITES = ('mutation', '--method', 'in_reply_to')


def thread(tid, comments, resolved=False, outdated=False):
    return {'id': tid, 'isResolved': resolved, 'isOutdated': outdated, 'path': 'app.py', 'line': 3,
            'comments': {'nodes': [{'databaseId': i, 'body': body, 'diffHunk': '@@ -1 +1 @@', 'author': {'login': who}}
                                   for i, (who, body) in enumerate(comments, start=int(tid[1:]) * 10)]}}


PAGES = [
    [thread('T1', [('rev', 'This leaks the token'), ('me', 'fixing')]), thread('T2', [('rev', 'nit')], resolved=True),
     thread('T3', [('rev', 'old')], outdated=True)],
    [thread('T4', [('me', 'note to self')]), thread('T5', [('rev', 'LGTM!')]), thread('T6', [('bot[bot]', 'Possible None')])],
]


class FakeGh:
    def __init__(self):
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        assert not any(word in arg for arg in args for word in WRITES), args
        assert args[0] == 'api' or args[:2] in (['repo', 'view'], ['pr', 'view']), args
        if args[:2] == ['repo', 'view']:
            return 'acme/app\n'
        if args[:2] == ['pr', 'view']:
            return 'https://github.com/acme/app/pull/7\n'
        if args[:2] == ['api', 'graphql']:
            page = 1 if any(a == 'after=C1' for a in args) else 0
            pr = {'number': 7, 'url': 'https://github.com/acme/app/pull/7', 'title': 'X', 'state': 'OPEN', 'isDraft': False,
                  'author': {'login': 'me'}, 'headRefName': 'feat/x', 'baseRefName': 'main',
                  'reviews': {'nodes': [{'author': {'login': 'rev'}, 'state': 'CHANGES_REQUESTED', 'body': 'See inline'},
                                        {'author': {'login': 'rev2'}, 'state': 'APPROVED', 'body': ''},
                                        {'author': {'login': 'rev3'}, 'state': 'APPROVED', 'body': ':+1: :tada:'}]},
                  'reviewThreads': {'pageInfo': {'hasNextPage': page == 0, 'endCursor': 'C1' if page == 0 else None},
                                    'nodes': PAGES[page]}}
            return json.dumps({'data': {'repository': {'pullRequest': pr}}})
        if args[0] == 'api' and args[1].endswith('/issues/7/comments'):
            return json.dumps([[{'id': 900, 'user': {'login': 'rev'}, 'body': 'Please add a test'},
                                {'id': 901, 'user': {'login': 'me'}, 'body': 'Done'}], [{'id': 902, 'user': {'login': 'x'}, 'body': '+1'}]])
        raise AssertionError('unexpected gh ' + ' '.join(args))


class GatherTests(unittest.TestCase):
    def gather(self, *argv):
        gh, out = FakeGh(), io.StringIO()
        with patch.object(pr_feedback, 'run', gh), redirect_stdout(out):
            code = pr_feedback.main(['gather', *argv])
        return code, json.loads(out.getvalue()), gh

    def test_pages_threads_and_keeps_only_open_substantive_feedback(self):
        code, result, gh = self.gather('acme/app#7')
        self.assertEqual(code, 0, result)
        self.assertEqual([t['thread'] for t in result['threads']], ['T1', 'T6'])
        self.assertEqual(result['threads'][0]['comments'][0], {'id': 10, 'author': 'rev', 'body': 'This leaks the token'})
        self.assertEqual(result['threads'][0]['diffHunk'], '@@ -1 +1 @@')
        self.assertEqual(result['reviews'], [{'author': 'rev', 'state': 'CHANGES_REQUESTED', 'body': 'See inline'}])
        self.assertEqual(result['comments'], [{'id': 900, 'author': 'rev', 'body': 'Please add a test'}])
        self.assertEqual(result['skipped'], {'resolved': 1, 'outdated': 1, 'author': 2, 'chatter': 3})
        self.assertEqual(result['pr']['head'], 'feat/x')
        self.assertEqual(sum(c[:2] == ['api', 'graphql'] for c in gh.calls), 2)  # two pages, one query
        self.assertEqual(len(gh.calls), 3)

    def test_connections_cut_at_100_are_reported_not_silently_dropped(self):
        self.assertNotIn('truncated', self.gather('acme/app#7')[1])
        original = FakeGh.__call__

        def cut(gh, args):
            out = original(gh, args)
            if args[:2] == ['api', 'graphql']:
                data = json.loads(out)
                pr = data['data']['repository']['pullRequest']
                pr['reviews']['pageInfo'] = {'hasPreviousPage': True}
                pr['reviewThreads']['nodes'][0]['comments']['pageInfo'] = {'hasNextPage': True}
                out = json.dumps(data)
            return out
        with patch.object(FakeGh, '__call__', cut):
            code, result, _ = self.gather('acme/app#7')
        self.assertEqual(code, 0)
        self.assertEqual(result['truncated'], {'reviews': True, 'threads': ['T1', 'T4']})

    def test_identifiers(self):
        self.assertEqual(self.gather('https://github.com/acme/app/pull/7')[0], 0)
        code, _, gh = self.gather('7')
        self.assertEqual((code, gh.calls[0][:2]), (0, ['repo', 'view']))
        code, _, gh = self.gather()
        self.assertEqual((code, gh.calls[0][:2]), (0, ['pr', 'view']))
        self.assertEqual(self.gather('not a pr')[0], 2)

    def test_a_gh_failure_exits_3(self):
        def failing(args):
            raise pr_feedback.Failure(3, 'gh auth status failed: not logged in')
        out = io.StringIO()
        with patch.object(pr_feedback, 'run', failing), redirect_stdout(out):
            self.assertEqual(pr_feedback.main(['gather', '7']), 3)
        self.assertIn('not logged in', json.loads(out.getvalue())['error'])


if __name__ == '__main__':
    unittest.main()
