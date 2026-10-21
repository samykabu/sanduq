"""PM2a: pr_feedback.py gather pages the review threads, filters resolved, outdated, author-only and
chatter items, and never calls a writing gh command. PM2b: reply and resolve only from an approved plan
file. gh is replaced by a fake."""
import io
import json
import sys
import tempfile
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


class TransportTests(unittest.TestCase):
    def test_gh_runs_through_the_shared_transport_never_retried(self):
        """SC8: 120 s as before, no retry (reply and resolve are writes); failures keep exit 3 and their text."""
        import sanduq_gh
        seen = []

        def run_gh(args, **kwargs):
            seen.append(kwargs)
            if args[0] == 'missing':
                raise sanduq_gh.GhError('gh CLI not installed', returncode=127)
            if args[0] == 'api':
                raise sanduq_gh.GhError('x', returncode=1, stdout='', stderr='HTTP 404: Not Found\n')
            return '{}'
        with patch.object(sanduq_gh, 'run_gh', run_gh):
            self.assertEqual(pr_feedback.run(['repo', 'view']), '{}')
            for args, text in ((['missing'], 'gh unavailable: gh CLI not installed'),
                               (['api', 'graphql'], 'gh api graphql failed: HTTP 404: Not Found')):
                with self.assertRaises(pr_feedback.Failure) as caught:
                    pr_feedback.run(args)
                self.assertEqual((caught.exception.code, str(caught.exception)), (3, text))
        self.assertEqual(seen, [{'timeout': 120}] * 3)


HEAD, PUSHED = 'b' * 40, 'c' * 40


class FakeBoard:
    """gh for the plan actions: PR acme/app#7 with threads T1 (comments 10, 11) and T6 (60) on two pages, T2
    resolved (20). Records every call; replies and resolves change its state; `fail` names writes that fail."""

    def __init__(self, compare=None, fail=(), forbidden=(), long=()):
        self.calls, self.compare, self.fail, self.forbidden = [], compare or {}, set(fail), set(forbidden)
        comment = lambda i, who, body: {'databaseId': i, 'author': {'login': who}, 'body': body}
        self.threads = {'T1': {'id': 'T1', 'isResolved': False, 'comments': {'pageInfo': {'hasNextPage': False}, 'nodes': [
                            comment(10, 'rev', 'This leaks the token'), comment(11, 'me', 'fixing')]}},
                        'T2': {'id': 'T2', 'isResolved': True, 'comments': {'pageInfo': {'hasNextPage': False}, 'nodes': [
                            comment(20, 'rev', 'nit')]}},
                        'T6': {'id': 'T6', 'isResolved': False, 'comments': {'pageInfo': {'hasNextPage': False}, 'nodes': [
                            comment(60, 'bot[bot]', 'Possible None')]}}}
        for thread in long:  # GitHub returned only the first 100 comments of these threads
            self.threads[thread]['comments']['pageInfo']['hasNextPage'] = True

    def writes(self):
        return [c for c in self.calls if 'mutation' in ' '.join(c) or any(a.startswith('in_reply_to=') for a in c)]

    def __call__(self, args):
        self.calls.append(args)
        query = next((a[6:] for a in args if a.startswith('query=')), '')
        if args[:2] == ['api', 'graphql'] and 'viewer{login}' in query:
            assert ['-F', 'num=7'] == args[args.index('num=7') - 1:args.index('num=7') + 1], args
            second = 'after=P1' in args
            nodes = [self.threads['T6']] if second else [self.threads['T1'], self.threads['T2']]
            pr = {'headRefOid': HEAD, 'reviewThreads': {'pageInfo': {'hasNextPage': not second, 'endCursor': 'P1'},
                                                         'nodes': json.loads(json.dumps(nodes))}}
            return json.dumps({'data': {'viewer': {'login': 'me'}, 'repository': {'pullRequest': pr}}})
        if args[:2] == ['api', 'graphql'] and 'resolveReviewThread' in query:
            thread = args[-1][3:]
            if thread in self.fail:
                raise pr_feedback.Failure(3, 'gh api graphql failed: HTTP 502')
            if thread in self.forbidden:  # GraphQL reports errors with a successful exit
                return json.dumps({'data': {'resolveReviewThread': None}, 'errors': [{'message': 'Forbidden'}]})
            self.threads[thread]['isResolved'] = True
            return json.dumps({'data': {'resolveReviewThread': {'thread': {'id': thread, 'isResolved': True}}}})
        if args[:2] == ['api', 'repos/acme/app/pulls/7/comments']:
            target = int(args[-1].split('=')[1])
            if target in self.fail:
                raise pr_feedback.Failure(3, 'gh api repos/acme/app/pulls/7/comments failed: HTTP 502')
            thread = next(t for t in self.threads.values() if target in {c['databaseId'] for c in t['comments']['nodes']})
            thread['comments']['nodes'].append({'databaseId': 900 + target, 'author': {'login': 'me'}, 'body': args[3][5:]})
            return '{}'
        if args[0] == 'api' and args[1].startswith('repos/acme/app/compare/'):
            status = self.compare.get(args[1].rsplit('/', 1)[1])
            if status is None:
                raise pr_feedback.Failure(3, 'gh api failed: HTTP 404: No commit found')
            return status + '\n'
        raise AssertionError('unexpected gh ' + ' '.join(args))


class PlanTests(unittest.TestCase):
    """PM2b: replies and resolves only from an approved plan file, bound to its repository, PR and digest."""
    PLAN = {'schema': pr_feedback.PLAN_SCHEMA, 'repo': 'acme/app', 'pr': 7, 'head': None,
            'replies': [{'thread': 'T1', 'comment': 10, 'body': 'The token is masked at line 3.'},
                        {'thread': 'T6', 'comment': 60, 'body': 'None is checked by the caller.'}],
            'resolves': ['T1', 'T6', 'T2']}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'plan.json'
        self.write()

    def write(self, **changes):
        self.plan = dict(json.loads(json.dumps(self.PLAN)), **changes)
        self.path.write_text(json.dumps(self.plan), encoding='utf-8')

    def run_action(self, action, gh, approved=None, approved_head=None):
        out = io.StringIO()
        argv = [action, '--plan', str(self.path)] + (['--approved', approved] if approved else []) + \
            (['--approved-head', approved_head] if approved_head else [])
        with patch.object(pr_feedback, 'run', gh), redirect_stdout(out):
            code = pr_feedback.main(argv)
        return code, json.loads(out.getvalue())

    def approved(self):
        return self.run_action('plan', FakeBoard())[1]['digest']

    def head_approved(self):
        """The second approval: the digest `plan` shows once `head` is set after the push."""
        return self.run_action('plan', FakeBoard())[1].get('head_digest', 'no head yet')

    def test_plan_checks_read_only_and_its_digest_leaves_out_only_the_head(self):
        gh = FakeBoard()
        code, result = self.run_action('plan', gh)
        self.assertEqual((code, result['replies'], result['resolves']), (0, 2, 3), result)
        self.assertEqual(result['digest'], pr_feedback.digest(self.plan))
        self.assertFalse(gh.writes())
        self.assertEqual(len(gh.calls), 2)  # the two thread pages
        self.write(head=PUSHED)
        self.assertEqual(self.approved(), result['digest'])
        self.write(replies=[dict(self.PLAN['replies'][0], body='Other text')])
        self.assertNotEqual(self.approved(), result['digest'])

    def test_a_changed_plan_is_refused_before_any_gh_call(self):
        approved = self.approved()
        self.write(resolves=['T1'])
        for action in ('reply', 'resolve'):
            gh = FakeBoard()
            code, result = self.run_action(action, gh, approved, 'x' if action == 'resolve' else None)
            self.assertEqual(code, 1, result)
            self.assertIn('plan changed since it was approved', result['error'])
            self.assertEqual(gh.calls, [])

    def test_threads_and_comments_of_another_pr_are_refused_before_any_write(self):
        for changes in ({'replies': [{'thread': 'TX', 'comment': 10, 'body': 'x'}]},
                        {'replies': [{'thread': 'T1', 'comment': 60, 'body': 'x'}]},
                        {'resolves': ['T1', 'OTHER_PR_THREAD']}):
            self.write(**changes)
            for action in ('plan', 'reply', 'resolve'):
                gh = FakeBoard()
                code, result = self.run_action(action, gh, pr_feedback.digest(self.plan), 'x')
                self.assertEqual(code, 1, (changes, action, result))
                self.assertIn('nothing written', result['error'])
                self.assertFalse(gh.writes())

    def test_reply_posts_each_approved_reply_once(self):
        gh, approved = FakeBoard(), self.approved()
        code, result = self.run_action('reply', gh, approved)
        self.assertEqual((code, result['replied'], result['already']), (0, [10, 60], []), result)
        posted = [c for c in gh.writes()]
        self.assertEqual([c[-1] for c in posted], ['in_reply_to=10', 'in_reply_to=60'])
        self.assertEqual(posted[0][2:4], ['-f', 'body=The token is masked at line 3.'])
        gh.calls.clear()
        code, result = self.run_action('reply', gh, approved)
        self.assertEqual((code, result['replied'], result['already']), (0, [], [10, 60]))
        self.assertFalse(gh.writes())

    def test_a_reply_run_that_fails_halfway_finishes_on_rerun(self):
        gh, approved = FakeBoard(fail={60}), self.approved()
        code, result = self.run_action('reply', gh, approved)
        self.assertEqual(code, 3, result)
        self.assertIn('replied so far: [10]', result['error'])
        gh.fail.clear()
        gh.calls.clear()
        code, result = self.run_action('reply', gh, approved)
        self.assertEqual((code, result['replied'], result['already']), (0, [60], [10]))

    def test_resolve_waits_for_a_pushed_head(self):
        approved = self.approved()
        board = FakeBoard()
        self.run_action('reply', board, approved)
        for head, compare in ((None, {}), (PUSHED, {}), (PUSHED, {PUSHED + '...' + HEAD: 'behind'}),
                              (PUSHED, {PUSHED + '...' + HEAD: 'diverged'})):
            self.write(head=head)
            board.calls.clear()
            board.compare = compare
            code, result = self.run_action('resolve', board, approved, self.head_approved())
            self.assertEqual(code, 1, (head, compare, result))
            self.assertIn('nothing resolved', result['error'])
            self.assertIn('set "head"' if head is None else 'does not contain the pushed commit', result['error'])
            self.assertIn(compare and list(compare.values())[0] or ('unknown' if head else 'head'), result['error'])
            self.assertFalse(board.writes())
        for head, compare in ((HEAD, {}), (PUSHED, {PUSHED + '...' + HEAD: 'ahead'})):
            board.compare = compare
            for thread in ('T1', 'T6'):
                board.threads[thread]['isResolved'] = False
            self.write(head=head)
            code, result = self.run_action('resolve', board, approved, self.head_approved())
            self.assertEqual((code, result['resolved'], result['already']), (0, ['T1', 'T6'], ['T2']), result)

    def test_resolve_waits_for_the_threads_approved_reply(self):
        self.write(head=HEAD)
        gh = FakeBoard()
        code, result = self.run_action('resolve', gh, self.approved(), self.head_approved())
        self.assertEqual(code, 1, result)
        self.assertIn('T1, T6', result['error'])
        self.assertFalse(gh.writes())

    def test_a_resolve_run_that_fails_halfway_finishes_on_rerun(self):
        self.write(head=HEAD)
        gh, approved = FakeBoard(fail={'T6'}), self.approved()
        self.run_action('reply', gh, approved)
        code, result = self.run_action('resolve', gh, approved, self.head_approved())
        self.assertEqual(code, 3, result)
        self.assertIn("resolved so far: ['T1']", result['error'])
        gh.fail.clear()
        gh.calls.clear()
        code, result = self.run_action('resolve', gh, approved, self.head_approved())
        self.assertEqual((code, result['resolved'], result['already']), (0, ['T6'], ['T1', 'T2']))
        self.assertEqual(len(gh.writes()), 1)

    def test_resolve_needs_a_second_approval_covering_the_pushed_head(self):
        """Codex 5: `head` is set after the first approval, so it gets its own; editing it voids that approval."""
        approved, board = self.approved(), FakeBoard(compare={PUSHED + '...' + HEAD: 'ahead'})
        self.run_action('reply', board, approved)
        self.write(head=PUSHED)
        shown = self.run_action('plan', FakeBoard())[1]
        self.assertEqual((shown['digest'], shown['head']), (approved, PUSHED))
        self.assertNotEqual(shown['head_digest'], approved)
        self.write(head=HEAD)  # edited to the PR's current head after the user approved PUSHED
        board.calls.clear()
        code, result = self.run_action('resolve', board, approved, shown['head_digest'])
        self.assertEqual(code, 1, result)
        self.assertIn('head changed since it was approved', result['error'])
        self.assertEqual(board.calls, [])
        out = io.StringIO()
        with redirect_stdout(out):  # no second approval at all
            self.assertEqual(pr_feedback.main(['resolve', '--plan', str(self.path), '--approved', approved]), 2)
        self.write(head=PUSHED)
        code, result = self.run_action('resolve', board, approved, shown['head_digest'])
        self.assertEqual((code, result['resolved']), (0, ['T1', 'T6']), result)

    def test_a_graphql_error_on_a_successful_exit_is_not_a_resolution(self):
        """Codex 8: gh exits 0 with `errors`; the thread must not count as resolved."""
        self.write(head=HEAD)
        gh, approved = FakeBoard(forbidden={'T6'}), self.approved()
        self.run_action('reply', gh, approved)
        code, result = self.run_action('resolve', gh, approved, self.head_approved())
        self.assertEqual(code, 3, result)
        self.assertIn('Forbidden', result['error'])
        self.assertIn("resolved so far: ['T1']", result['error'])
        self.assertFalse(gh.threads['T6']['isResolved'])

    def test_a_thread_with_unread_comments_is_refused_before_any_reply(self):
        """Codex 9: past 100 comments an earlier reply may be unseen, so a rerun could post it twice."""
        gh = FakeBoard(long={'T6'})
        for action in ('plan', 'reply'):
            code, result = self.run_action(action, gh, self.approved())
            self.assertEqual(code, 1, (action, result))
            self.assertIn('T6 has more than 100 comments', result['error'])
        self.assertFalse(gh.writes())
        self.write(replies=self.PLAN['replies'][:1], resolves=['T6'])  # resolving alone reads no comments
        self.assertEqual(self.run_action('plan', gh)[0], 0)

    def test_a_malformed_or_missing_plan_exits_2(self):
        for broken in ({'schema': 'other'}, {'repo': 'acme'}, {'pr': '7'}, {'replies': [{'thread': 'T1', 'comment': 10}]},
                       {'resolves': ['T1', 'T1']}, {'head': 'main'}, {'replies': [], 'resolves': []}, {'extra': 1}):
            self.write(**broken)
            code, result = self.run_action('plan', FakeBoard())
            self.assertEqual(code, 2, (broken, result))
        self.path.unlink()
        self.assertEqual(self.run_action('plan', FakeBoard())[0], 2)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(pr_feedback.main(['reply', '--plan', str(self.path)]), 2)  # no --approved


if __name__ == '__main__':
    unittest.main()
