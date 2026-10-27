import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/decisions.py'
sys.path.insert(0, str(SOURCE.parent))
SPEC = importlib.util.spec_from_file_location('sanduq_decisions', SOURCE)
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.issue = {'number': 12, 'user': {'login': 'creator'}}
        self.policy = {'decisions': {'authorized_users': ['reviewer']}}
        body = '**SD1: Which path?**\n\n- A. First\n- B. Second'
        marker = {'version': 1, 'id': 'SD1', 'options': ['First', 'Second'],
                  'body_digest': d.digest(body)}
        self.question = {'id': 1, 'user': {'login': 'creator', 'type': 'User'},
                         'body': '<!-- sanduq-decision:question ' + json.dumps(marker) + ' -->\n' + body}

    def reply(self, number, author, body, association='NONE'):
        return {'id': number, 'user': {'login': author, 'type': 'User'},
                'author_association': association, 'body': body,
                'updated_at': f'2026-01-0{number}T00:00:00Z'}

    def test_authorized_answer_and_untrusted_text(self):
        rows = d.answers([self.question, self.reply(2, 'outsider', 'SD1: B'),
                          self.reply(3, 'reviewer', 'SD1: A')], self.issue, self.policy)
        self.assertEqual((rows[0]['status'], rows[0]['option']), ('answered', 'A'))
        self.assertEqual([item['comment_id'] for item in rows[0]['answers']], [3])

    def test_conflicting_authorized_answers_require_review(self):
        rows = d.answers([self.question, self.reply(2, 'reviewer', 'SD1: A'),
                          self.reply(3, 'creator', 'SD1: B')], self.issue, self.policy)
        self.assertEqual(rows[0]['status'], 'conflict')

    def test_quoted_or_fenced_answer_is_not_counted(self):
        rows = d.answers([self.question, self.reply(2, 'reviewer', '> SD1: A\n```\nSD1: B\n```')],
                         self.issue, self.policy)
        self.assertEqual(rows[0]['status'], 'pending')

    def test_tolerant_answer_forms_count(self):
        # AHMED-15: punctuation, `-` or `=` separators and a ` - feedback` tail never hide a plain letter.
        for body in ('SD1: B.', 'SD1 - B', 'SD1 = b', 'SD1: B!', 'sd1: B - keep the drafts'):
            rows = d.answers([self.question, self.reply(2, 'reviewer', body)], self.issue, self.policy)
            self.assertEqual((rows[0]['status'], rows[0]['option'], rows[0]['unparsed']), ('answered', 'B', []), body)

    def test_an_unparsed_answer_is_reported_with_its_comment_and_never_inferred(self):
        prose = {**self.reply(2, 'reviewer', 'I pick B for SD1'), 'html_url': 'https://x/2'}
        rows = d.answers([self.question, prose, self.reply(3, 'reviewer', 'SD1: A, B'),
                          self.reply(4, 'outsider', 'SD1: B')], self.issue, self.policy)
        self.assertEqual((rows[0]['status'], rows[0]['answers']), ('pending', []))
        self.assertEqual([(u['comment_id'], u['url'], u['author'], u['reason']) for u in rows[0]['unparsed']],
                         [(2, 'https://x/2', 'reviewer', 'not understood; reply `SD1: A` on its own line or tick the box'),
                          (3, None, 'reviewer', 'several letters for a single-choice question')])

    def test_agent_posted_and_pre_question_comments_are_never_answers(self):
        # SEC-05: a comment a Sanduq process posted, or one older than the question, is reported, not counted.
        rows = d.answers([self.reply(0, 'reviewer', 'SD1: A'), self.question, self.reply(2, 'reviewer', 'SD1: A')],
                         self.issue, self.policy, agent_ids={2})
        self.assertEqual((rows[0]['status'], rows[0]['answers']), ('pending', []))
        self.assertEqual([(u['comment_id'], u['reason']) for u in rows[0]['unparsed']],
                         [(0, 'posted before the question'), (2, 'posted by a Sanduq process, not a reviewer')])

    def test_question_edit_fails_closed(self):
        altered = dict(self.question, body=self.question['body'] + '\nnew text')
        with self.assertRaisesRegex(d.WorkflowError, 'DECISION_QUESTION_EDITED'):
            d.answers([altered], self.issue, self.policy)

    def test_application_evidence_and_answer_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = root / 'specs/001/workflow/answer.md'
            evidence.parent.mkdir(parents=True)
            evidence.write_text('A', encoding='utf-8')
            replies = [self.reply(2, 'reviewer', 'SD1: A')]
            item = d.answers([self.question, *replies], self.issue, self.policy)[0]
            item.update(status='applied', answer_digest=d.digest(item['answers']),
                        application={'answer_digest': d.digest(item['answers']),
                                     'evidence': {'specs/001/workflow/answer.md':
                                                  __import__('hashlib').sha256(evidence.read_bytes()).hexdigest()}})
            ledger = {'version': 1, 'feature': 'specs/001', 'decisions': [item]}
            d.verify_ledger(root, 'specs/001', ledger)
            evidence.write_text('B', encoding='utf-8')
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_APPLICATION_STALE'):
                d.verify_ledger(root, 'specs/001', ledger)

    def test_reconcile_reuses_posted_question_after_lost_response(self):
        class FakeRun:
            policy = {'decisions': {'authorized_users': []}}

            def __init__(self, root, feature):
                self.feature = Path(root) / feature

            def load(self, allow_branch_change=False):
                return {'issue': 'acme/app#12'}

        class FakeGitHub:
            comments = []
            posts = 0

            def api(self, endpoint, method='GET', payload=None, pages=False):
                if method == 'POST':
                    self.posts += 1
                    result = {'id': 10, 'html_url': 'https://github.com/acme/app/issues/12#issuecomment-10',
                              'body': payload['body'], 'user': {'login': 'creator', 'type': 'User'}}
                    self.comments.append(result)
                    return result
                if endpoint.endswith('/comments?per_page=100'):
                    return self.comments
                return {'number': 12, 'user': {'login': 'creator'}}

        with tempfile.TemporaryDirectory() as folder, patch.object(d, 'Run', FakeRun):
            root = Path(folder)
            source = root / 'specs/001/scope-source.json'
            source.parent.mkdir(parents=True)
            source.write_text('{"repo":"acme/app","issue":12}', encoding='utf-8')
            gh = FakeGitHub()
            first = d.ask(root, 'specs/001', 'Which path?', ['First', 'Second'], gh)
            second = d.ask(root, 'specs/001', 'Which path?', ['First', 'Second'], gh)
            self.assertEqual((first['id'], second['id'], gh.posts), ('SD1', 'SD1', 1))
            self.assertTrue(second['reused'])

    def test_a_comment_posted_through_sanduq_gh_in_this_project_is_not_a_decision(self):
        class FakeRun:
            policy = {'decisions': {'authorized_users': ['reviewer']}}

            def __init__(self, root, feature):
                self.feature = Path(root) / feature

            def load(self, allow_branch_change=False):
                return {'issue': 'acme/app#12'}

        class FakeGitHub:
            def api(self, endpoint, method='GET', payload=None, pages=False):
                if endpoint.endswith('/comments?per_page=100'):
                    return [test.question, test.reply(2, 'reviewer', 'SD1: A', 'OWNER')]
                return {'number': 12, 'user': {'login': 'creator'}}

        test = self
        with tempfile.TemporaryDirectory() as folder, patch.object(d, 'Run', FakeRun):
            root = Path(folder)
            (root / 'specs/001').mkdir(parents=True)
            (root / 'specs/001/scope-source.json').write_text('{"repo":"acme/app","issue":12}', encoding='utf-8')
            self.assertEqual(d.reconcile(root, 'specs/001', FakeGitHub())['decisions'][0]['status'], 'answered')
            log = root / d.sanduq_gh.POSTED_COMMENTS
            log.parent.mkdir(parents=True)
            log.write_text('{"id": 2, "endpoint": "repos/acme/app/issues/12/comments"}\n', encoding='utf-8')
            item = d.reconcile(root, 'specs/001', FakeGitHub())['decisions'][0]
            self.assertEqual((item['status'], item['answers'], item['unparsed'][0]['reason']),
                             ('pending', [], 'posted by a Sanduq process, not a reviewer'))

    def test_local_transport_writes_the_question_to_the_file_and_reads_the_reply_from_it(self):
        # REQ-21: no GitHub call at all; the ledger records the quoted line with source local.
        class FakeRun:
            policy = {'decisions': {'authorized_users': []}}

            def __init__(self, root, feature):
                self.feature = Path(root) / feature

            def load(self, allow_branch_change=False):
                return {'issue': 'acme/app#12', 'clarification_transport': 'local'}

        class NoGitHub:
            def api(self, *args, **kwargs):
                raise AssertionError('GitHub was called in local mode: ' + str(args))

        with tempfile.TemporaryDirectory() as folder, patch.object(d, 'Run', FakeRun):
            root = Path(folder)
            (root / 'specs/001').mkdir(parents=True)
            (root / 'specs/001/scope-source.json').write_text('{"repo":"acme/app","issue":12}', encoding='utf-8')
            asked = d.ask(root, 'specs/001', 'Which path?', ['First', 'Second'], NoGitHub(), recommended='B')
            self.assertEqual(asked, {'id': 'SD1', 'url': 'specs/001/clarifications.md#sd1', 'status': 'pending',
                                     'transport': 'local'})
            path = root / 'specs/001/clarifications.md'
            text = path.read_text(encoding='utf-8')
            self.assertIn('\n## SD1: Which path?\n\n- [ ] **A.** First\n- [ ] **B.** Second **(Recommended)**\n', text)
            self.assertEqual(d.reconcile(root, 'specs/001', NoGitHub(), publish_field=True)['decisions'][0]['status'], 'pending')
            path.write_text(text + '\nSD1: B. - as discussed\nthe user also mentioned SD1 later\n', encoding='utf-8')
            ledger = d.reconcile(root, 'specs/001', NoGitHub())
            item = ledger['decisions'][0]
            self.assertEqual((ledger['transport'], item['status'], item['option'], item['question_comment_id']),
                             ('local', 'answered', 'B', None))
            self.assertEqual([(a['source'], a['quote'], a['author']) for a in item['answers']],
                             [('local', 'SD1: B. - as discussed', None)])
            self.assertEqual([u['quote'] for u in item['unparsed']], ['the user also mentioned SD1 later'])
            path.write_text(text.replace('- [ ] **A.**', '- [x] **A.**') + '\nSD1: B\n', encoding='utf-8')
            self.assertEqual(d.reconcile(root, 'specs/001', NoGitHub())['decisions'][0]['status'], 'conflict')
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_TRANSPORT_LOCAL'):
                d.upgrade_questions(root, 'specs/001', NoGitHub())

    def test_local_sections_parse_both_id_kinds_and_text_answers(self):
        text = ('# Clarifications\n\n## C1Q1: Keep drafts?\n\n- [ ] **A.** Yes\n- [x] **B.** No\n\n'
                '## C1Q2: How long?\n\nC1Q2: thirty days\n\n## SD1: Which path?\n\n- [ ] **A.** First\n'
                '- [ ] **B.** Second\n\nSD1 = A\nSD1 might also be C\n')
        sections = d.local_sections(text)
        self.assertEqual({k: (v['ticked'], v['answers'], v['unparsed']) for k, v in sections.items()}, {
            'C1Q1': (['B'], [], []), 'C1Q2': ([], [([], 'C1Q2: thirty days')], []),
            'SD1': ([], [(['A'], 'SD1 = A')], ['SD1 might also be C'])})

    def test_a_local_letter_the_question_does_not_offer_is_unparsed_with_the_reason(self):
        text = ('## C1Q1: Keep drafts?\n\n- [ ] **A.** Yes\n- [ ] **B.** No\n\nC1Q1: Z\n\n'
                '## C1Q2: How long?\n\nC1Q2: Z\n')
        sections = d.local_sections(text)
        self.assertEqual((sections['C1Q1']['answers'], sections['C1Q1']['unparsed']),
                         ([], ['C1Q1: Z (Z is not an option of C1Q1)']))
        self.assertEqual(sections['C1Q2']['answers'], [(['Z'], 'C1Q2: Z')])  # no options: free text still answers

    def test_project_field_sync_does_not_touch_lifecycle_status(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / '.specify/extensions/project/config.json'
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({'projectId': 'P', 'projectNumber': 1,
                                          'owner': 'acme', 'statusFieldId': 'STATUS'}), encoding='utf-8')
            class GitHub:
                edit = None

                def command(self, args):
                    if args[1] == 'field-list':
                        return {'totalCount': 1, 'fields': [{'name': 'Decision', 'id': 'DEC',
                                 'type': 'ProjectV2SingleSelectField',
                                 'options': [{'name': 'Waiting', 'id': 'WAIT'}]}]}
                    if args[1] == 'item-list':
                        return {'totalCount': 1, 'items': [{'id': 'ITEM', 'decision': 'Waiting' if self.edit else None, 'content': {
                            'type': 'Issue', 'number': 12, 'repository': 'acme/app'}}]}
                    self.edit = args
                    return {}
            gh = GitHub()
            issue = {'number': 12, 'repository_url': 'https://api.github.com/repos/acme/app'}
            summary = d.sync_project_field(root, issue,
                      {'decisions': [{'status': 'pending'}]}, gh,
                      {'decisions': {'project_field': 'Decision'}})
            self.assertEqual(summary, 'Waiting')
            self.assertIn('DEC', gh.edit)
            self.assertNotIn('STATUS', gh.edit)

    def test_edited_answer_reopens_applied_decision(self):
        class FakeRun:
            policy = {'decisions': {'authorized_users': ['reviewer']}}

            def __init__(self, root, feature):
                self.feature = Path(root) / feature

            def load(self, allow_branch_change=False):
                return {'issue': 'acme/app#12'}

        class FakeGitHub:
            def __init__(self, comments):
                self.comments = comments

            def api(self, endpoint, pages=False):
                return self.comments if '/comments?' in endpoint else self.issue

            issue = {'number': 12, 'user': {'login': 'creator'}}

        with tempfile.TemporaryDirectory() as folder, patch.object(d, 'Run', FakeRun):
            root = Path(folder)
            source = root / 'specs/001/scope-source.json'
            source.parent.mkdir(parents=True)
            source.write_text('{"repo":"acme/app","issue":12}', encoding='utf-8')
            original = d.answers([self.question, self.reply(2, 'reviewer', 'SD1: A')],
                                 self.issue, self.policy)[0]
            original.update(status='applied', answer_digest=d.digest(original['answers']),
                            application={'answer_digest': d.digest(original['answers']),
                                         'evidence': {'specs/001/spec.md': 'previous'}})
            d.write(root / 'specs/001/workflow/decisions.json',
                    {'version': 1, 'feature': 'specs/001', 'issue': 'acme/app#12',
                     'decisions': [original]})
            revised = d.reconcile(root, 'specs/001',
                                  FakeGitHub([self.question, self.reply(2, 'reviewer', 'SD1: B')]))
            self.assertEqual((revised['decisions'][0]['status'], revised['decisions'][0]['option']),
                             ('answered', 'B'))
            self.assertNotIn('application', revised['decisions'][0])

    def test_competing_question_publishers_cannot_duplicate_remote_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lock = root / '.specify/workflow/runtime' / ('decision-' + d.digest('specs/001') + '.lock')
            with d.locked(lock):
                with self.assertRaisesRegex(d.WorkflowError, 'WORKFLOW_BUSY'):
                    d.ask(root, 'specs/001', 'Choose?', ['A', 'B'])

    def test_post_succeeded_but_response_lost_reuses_remote_question(self):
        class FakeRun:
            policy = {'decisions': {'authorized_users': []}}
            def __init__(self, root, feature):
                self.feature = Path(root) / feature
            def load(self, allow_branch_change=False):
                return {'issue': 'acme/app#12'}
        class FakeGitHub:
            def __init__(self):
                self.comments = []
                self.posts = 0
            def api(self, endpoint, method='GET', payload=None, pages=False):
                if method == 'POST':
                    self.posts += 1
                    self.comments.append({'id': 10, 'html_url': 'https://github.com/acme/app/issues/12#issuecomment-10',
                                          'body': payload['body'], 'user': {'login': 'creator', 'type': 'User'}})
                    raise d.WorkflowError('Simulated response lost after remote write')
                return self.comments if '/comments?' in endpoint else {'number': 12,
                            'user': {'login': 'creator'}}
        with tempfile.TemporaryDirectory() as folder, patch.object(d, 'Run', FakeRun):
            root = Path(folder)
            source = root / 'specs/001/scope-source.json'
            source.parent.mkdir(parents=True)
            source.write_text('{"repo":"acme/app","issue":12}', encoding='utf-8')
            gh = FakeGitHub()
            with self.assertRaisesRegex(d.WorkflowError, 'response lost'):
                d.ask(root, 'specs/001', 'Choose?', ['A', 'B'], gh)
            result = d.ask(root, 'specs/001', 'Choose?', ['A', 'B'], gh)
            self.assertEqual((result['id'], result['reused'], gh.posts), ('SD1', True, 1))


if __name__ == '__main__':
    unittest.main()
