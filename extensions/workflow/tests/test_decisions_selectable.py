import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/decisions.py'
sys.path.insert(0, str(SOURCE.parent))
SPEC = importlib.util.spec_from_file_location('sanduq_decisions_selectable', SOURCE)
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)

ISSUE = {'number': 12, 'user': {'login': 'creator'}, 'html_url': 'https://github.com/acme/app/issues/12',
         'repository_url': 'https://api.github.com/repos/acme/app'}
POLICY = {'decisions': {'authorized_users': ['reviewer']},
          'clarification': {'resume_on_reinvoke': 'reread-answers'},
          'scope': {'statuses': {'Feature Specification': 'Specifying',
                                 'Need Clarifications': 'Waiting for answers'}}}


def tick(comment, *letters):
    """What GitHub stores after someone ticks boxes in the rendered task list."""
    lines = comment['body'].split('\n')
    for index, line in enumerate(lines):
        if any(line.startswith(f'- [ ] **{letter}.**') for letter in letters):
            lines[index] = '- [x]' + line[5:]
    return dict(comment, body='\n'.join(lines))


def posted(qid='SD1', options=('First', 'Second', 'Third'), mode='single', recommended=None, cid=1):
    body = d.render_body(qid, 'Which path?', list(options), mode, recommended)
    marker = {'version': 1, 'id': qid, 'options': list(options), 'body_digest': d.digest(body),
              'request_digest': 'r', 'choice_format': 1, 'mode': mode, 'recommended': recommended}
    return {'id': cid, 'user': {'login': 'creator', 'type': 'User'},
            'html_url': f'https://github.com/acme/app/issues/12#issuecomment-{cid}',
            'body': '<!-- sanduq-decision:question ' + json.dumps(marker, sort_keys=True) + ' -->\n' + body}


def legacy(qid='SD1', options=('First', 'Second'), cid=1):
    body = f'**{qid}: Which path?**\n\n' + '\n'.join(f'- {chr(65 + i)}. {o}' for i, o in enumerate(options))
    body += f'\n\nReply with `{qid}: A` (or another letter) in a new comment. Decisions are reviewed in this issue.'
    marker = {'version': 1, 'id': qid, 'options': list(options), 'body_digest': d.digest(body),
              'request_digest': 'legacy'}
    return {'id': cid, 'user': {'login': 'creator', 'type': 'User'},
            'html_url': f'https://github.com/acme/app/issues/12#issuecomment-{cid}',
            'body': '<!-- sanduq-decision:question ' + json.dumps(marker, sort_keys=True) + ' -->\n' + body}


def reply(cid, author, body, association='NONE'):
    return {'id': cid, 'user': {'login': author, 'type': 'User'}, 'author_association': association,
            'body': body, 'updated_at': f'2026-01-0{cid}T00:00:00Z'}


def rows(*comments):
    return d.answers(list(comments), ISSUE, POLICY)


class FormatTests(unittest.TestCase):
    def test_native_task_list_is_unchecked_with_recommendation_suffix(self):
        body = posted(recommended=1)['body']
        self.assertIn('- [ ] **A.** First\n', body)
        self.assertIn('- [ ] **B.** Second **(Recommended)**\n', body)
        self.assertNotIn('[x]', body)
        self.assertEqual(rows(posted(recommended=1))[0]['status'], 'pending')

    def test_ask_posts_selectable_question_and_reuses_it(self):
        gh = FakeGitHub()
        with ledger_root(gh) as root:
            first = d.ask(root, 'specs/001', 'Which path?', ['First', 'Second'], gh, 'single', 'B')
            again = d.ask(root, 'specs/001', 'Which path?', ['First', 'Second'], gh, 'single', 'B')
            other = d.ask(root, 'specs/001', 'Which path?', ['First', 'Second'], gh, 'multiple')
        self.assertEqual((first['id'], again['id'], again['reused'], other['id']), ('SD1', 'SD1', True, 'SD2'))
        marker = json.loads(gh.comments[0]['body'].split('\n', 1)[0][len('<!-- sanduq-decision:question '):-4])
        self.assertEqual((marker['choice_format'], marker['mode'], marker['recommended']), (1, 'single', 1))
        self.assertIn('**(Recommended)**', gh.comments[0]['body'])

    def test_invalid_mode_and_recommendation_are_refused(self):
        with ledger_root(FakeGitHub()) as root:
            for kwargs in ({'mode': 'many'}, {'recommended': 'C'}, {'mode': 'multiple', 'recommended': 'A'}):
                with self.assertRaisesRegex(d.WorkflowError, 'DECISION_(MODE|RECOMMENDATION)_INVALID'):
                    d.ask(root, 'specs/001', 'Which?', ['One', 'Two'], FakeGitHub(), **kwargs)


class SelectionTests(unittest.TestCase):
    def test_single_tick_answers_without_inventing_an_actor(self):
        item = rows(tick(posted(), 'B'))[0]
        self.assertEqual((item['status'], item['option'], item['selected']), ('answered', 'B', ['B']))
        self.assertEqual([(a['source'], a['author']) for a in item['answers']], [('checkbox', None)])

    def test_single_two_ticks_is_a_conflict(self):
        self.assertEqual(rows(tick(posted(), 'A', 'B'))[0]['status'], 'conflict')

    def test_single_tick_and_text_reply_agree_or_conflict(self):
        self.assertEqual(rows(tick(posted(), 'A'), reply(2, 'reviewer', 'SD1: A'))[0]['status'], 'answered')
        self.assertEqual(rows(tick(posted(), 'A'), reply(2, 'reviewer', 'SD1: B'))[0]['status'], 'conflict')

    def test_multiple_accepts_several_ticks_and_text_list(self):
        item = rows(tick(posted(mode='multiple'), 'A', 'C'))[0]
        self.assertEqual((item['status'], item['selected'], item['option']), ('answered', ['A', 'C'], None))
        item = rows(posted(mode='multiple'), reply(2, 'reviewer', 'SD1: A, C'))[0]
        self.assertEqual((item['status'], item['selected']), ('answered', ['A', 'C']))
        item = rows(tick(posted(mode='multiple'), 'A', 'C'), reply(2, 'reviewer', 'SD1: A,C'))[0]
        self.assertEqual(item['status'], 'answered')

    def test_multiple_disagreement_is_a_conflict(self):
        item = rows(tick(posted(mode='multiple'), 'A'), reply(2, 'reviewer', 'SD1: A, B'))[0]
        self.assertEqual((item['status'], item['selected']), ('conflict', []))

    def test_single_ignores_a_letter_list(self):
        self.assertEqual(rows(posted(), reply(2, 'reviewer', 'SD1: A, B'))[0]['status'], 'pending')

    def test_unauthorized_text_and_quoted_text_do_not_answer(self):
        item = rows(posted(), reply(2, 'outsider', 'SD1: A'), reply(3, 'reviewer', '> SD1: B'))[0]
        self.assertEqual(item['status'], 'pending')

    def test_changed_answer_reopens_an_applied_decision(self):
        with ledger_root(FakeGitHub()) as root:
            old = rows(tick(posted(), 'A'))[0]
            old.update(status='applied', answer_digest=d.digest(old['answers']),
                       application={'answer_digest': d.digest(old['answers']), 'evidence': {'x': 'y'}})
            d.write(root / 'specs/001/workflow/decisions.json',
                    {'version': 1, 'feature': 'specs/001', 'issue': 'acme/app#12', 'decisions': [old]})
            same = d.reconcile(root, 'specs/001', FakeGitHub([tick(posted(), 'A')]))
            self.assertEqual(same['decisions'][0]['status'], 'applied')
            changed = d.reconcile(root, 'specs/001', FakeGitHub([tick(posted(), 'B')]))
        self.assertEqual((changed['decisions'][0]['status'], changed['decisions'][0]['option']), ('answered', 'B'))
        self.assertNotIn('application', changed['decisions'][0])


class TamperingTests(unittest.TestCase):
    def test_changed_choice_text_fails_closed(self):
        comment = posted()
        for old, new in (('First', 'Evil'), ('- [ ] **B.**', '- [ ] **A.**'), ('**(Recommended)**', '')):
            tampered = dict(comment, body=comment['body'].replace(old, new))
            if tampered['body'] != comment['body']:
                with self.assertRaisesRegex(d.WorkflowError, 'DECISION_QUESTION_EDITED'):
                    rows(tampered)

    def test_removed_or_added_marker_lines_fail_closed(self):
        comment = posted()
        for text in (comment['body'].replace('<!-- sanduq-decision:choices:end -->', ''),
                     comment['body'].replace('\n\nPrefer text?', '\nextra\n\nPrefer text?')):
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_QUESTION_EDITED'):
                rows(dict(comment, body=text))

    def test_recommendation_marker_is_validated(self):
        comment = posted()
        head, body = comment['body'].split('\n', 1)
        marker = json.loads(head[len('<!-- sanduq-decision:question '):-4])
        marker['recommended'] = 9
        with self.assertRaisesRegex(d.WorkflowError, 'DECISION_RECOMMENDATION_INVALID'):
            rows(dict(comment, body='<!-- sanduq-decision:question ' + json.dumps(marker) + ' -->\n' + body))

    def test_choice_format_marker_cannot_be_forged_onto_a_legacy_body(self):
        comment = legacy()
        head, body = comment['body'].split('\n', 1)
        marker = json.loads(head[len('<!-- sanduq-decision:question '):-4])
        marker['choice_format'] = 1
        marker['mode'] = 'single'
        with self.assertRaisesRegex(d.WorkflowError, 'DECISION_QUESTION_EDITED'):
            rows(dict(comment, body='<!-- sanduq-decision:question ' + json.dumps(marker) + ' -->\n' + body))

    def test_verify_ledger_recomputes_the_choice(self):
        with ledger_root(FakeGitHub()) as root:
            evidence = root / 'specs/001/spec.md'
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text('x', encoding='utf-8')
            item = rows(tick(posted(mode='multiple'), 'A', 'B'))[0]
            digest = d.digest(item['answers'])
            item.update(status='applied', answer_digest=digest, application={
                'answer_digest': digest,
                'evidence': {'specs/001/spec.md': __import__('hashlib').sha256(b'x').hexdigest()}})
            ledger = {'version': 1, 'feature': 'specs/001', 'decisions': [item]}
            d.verify_ledger(root, 'specs/001', ledger)
            item['selected'] = ['A']
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_CHOICE_MISMATCH'):
                d.verify_ledger(root, 'specs/001', ledger)


class LegacyTests(unittest.TestCase):
    def test_legacy_question_and_text_reply_still_parse(self):
        item = rows(legacy(), reply(2, 'reviewer', 'SD1: B'))[0]
        self.assertEqual((item['status'], item['option'], item['mode']), ('answered', 'B', 'single'))
        with self.assertRaisesRegex(d.WorkflowError, 'DECISION_QUESTION_EDITED'):
            comment = legacy()
            rows(dict(comment, body=comment['body'] + 'x'))

    def test_upgrade_makes_questions_selectable_and_keeps_real_replies(self):
        gh = FakeGitHub([legacy(), reply(2, 'reviewer', 'SD1: B')])
        with ledger_root(gh) as root:
            answered = d.reconcile(root, 'specs/001', gh)
            before = answered['decisions'][0]
            result = d.upgrade_questions(root, 'specs/001', gh)
            after = d.reconcile(root, 'specs/001', gh)['decisions'][0]
            again = d.upgrade_questions(root, 'specs/001', gh)
        self.assertEqual(result, {'upgraded': ['SD1'], 'unchanged': []})
        self.assertEqual(again, {'upgraded': [], 'unchanged': ['SD1']})
        self.assertEqual(gh.patches, 1)
        self.assertIn('- [ ] **A.** First', gh.comments[0]['body'])
        self.assertNotIn('[x]', gh.comments[0]['body'])
        self.assertEqual((after['id'], after['options'], after['request_digest']),
                         (before['id'], before['options'], before['request_digest']))
        self.assertEqual((after['status'], after['option'], after['answers']),
                         (before['status'], before['option'], before['answers']))
        self.assertEqual(after['answer_digest'], before['answer_digest'])
        self.assertEqual(after['choice_format'], 1)

    def test_upgrade_keeps_an_applied_decision_applied(self):
        gh = FakeGitHub([legacy(), reply(2, 'reviewer', 'SD1: A')])
        with ledger_root(gh) as root:
            ledger = d.reconcile(root, 'specs/001', gh)
            item = ledger['decisions'][0]
            item.update(status='applied', application={'answer_digest': item['answer_digest'],
                                                       'evidence': {'a': 'b'}})
            d.write(root / 'specs/001/workflow/decisions.json', ledger)
            d.upgrade_questions(root, 'specs/001', gh)
            self.assertEqual(d.reconcile(root, 'specs/001', gh)['decisions'][0]['status'], 'applied')

    def test_upgrade_refuses_an_edited_legacy_question(self):
        edited = legacy()
        edited['body'] += '\nextra'
        gh = FakeGitHub([edited])
        with ledger_root(gh) as root:
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_QUESTION_EDITED'):
                d.upgrade_questions(root, 'specs/001', gh)
        self.assertEqual(gh.patches, 0)

    def test_upgrade_requires_confirmed_remote_write(self):
        gh = FakeGitHub([legacy()])
        gh.confirm = False
        with ledger_root(gh) as root:
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_UPGRADE_NOT_CONFIRMED'):
                d.upgrade_questions(root, 'specs/001', gh)


class LifecycleTests(unittest.TestCase):
    def run_sync(self, status, decisions, ledger_extra=None, policy=POLICY):
        gh = FakeProject(status)
        with ledger_root(gh) as root:
            ledger = {'version': 1, 'decisions': [{'status': value} for value in decisions]}
            ledger.update(ledger_extra or {})
            result = d.sync_lifecycle(root, ISSUE, ledger, gh, policy)
        return result, gh.edits

    def test_pending_decision_parks_a_feature_specification_issue_in_the_mapped_status(self):
        result, edits = self.run_sync('Specifying', ['pending'])
        self.assertEqual(result, {'parked': True})
        self.assertEqual(edits, [('STATUS', 'OPT-Waiting for answers')])

    def test_conflict_also_parks(self):
        self.assertEqual(self.run_sync('Specifying', ['conflict'])[1], [('STATUS', 'OPT-Waiting for answers')])

    def test_answered_or_applied_returns_only_what_decisions_parked_under_the_return_policy(self):
        for decisions in (['answered'], ['applied'], ['answered', 'applied']):
            result, edits = self.run_sync('Waiting for answers', decisions, {'lifecycle': {'parked': True}})
            self.assertEqual((result, edits), ({}, [('STATUS', 'OPT-Specifying')]))

    def test_manual_return_policy_does_not_move_the_issue(self):
        policy = {**POLICY, 'clarification': {'resume_on_reinvoke': 'manual-status'}}
        result, edits = self.run_sync('Waiting for answers', ['applied'], {'lifecycle': {'parked': True}}, policy)
        self.assertEqual((result, edits), ({'parked': True}, []))

    def test_a_status_decisions_did_not_park_is_not_returned(self):
        result, edits = self.run_sync('Waiting for answers', ['applied'])
        self.assertEqual((result, edits), ({}, []))

    def test_advanced_states_never_regress(self):
        for status in ('Ready', 'In progress', 'In review', 'Done'):
            self.assertEqual(self.run_sync(status, ['pending'])[1], [], status)
            result, edits = self.run_sync(status, ['applied'], {'lifecycle': {'parked': True}})
            self.assertEqual((result, edits), ({}, []), status)

    def test_already_waiting_is_left_alone_and_unmapped_defaults_are_used(self):
        self.assertEqual(self.run_sync('Waiting for answers', ['pending'])[1], [])
        result, edits = self.run_sync('Feature Specification', ['pending'], policy={'decisions': {}})
        self.assertEqual(edits, [('STATUS', 'OPT-Need Clarifications')])

    def test_opt_out_and_missing_status_option(self):
        policy = {**POLICY, 'decisions': {'lifecycle_status': False}}
        self.assertEqual(self.run_sync('Specifying', ['pending'], policy=policy)[1], [])
        gh = FakeProject('Specifying')
        gh.options = {}
        with ledger_root(FakeGitHub()) as root:
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_STATUS_OPTION_MISSING'):
                d.sync_lifecycle(root, ISSUE, {'decisions': [{'status': 'pending'}]}, gh, POLICY)

    def test_failed_board_write_is_surfaced(self):
        gh = FakeProject('Specifying')
        gh.fail = True
        with ledger_root(FakeGitHub()) as root:
            with self.assertRaises(d.WorkflowError):
                d.sync_lifecycle(root, ISSUE, {'decisions': [{'status': 'pending'}]}, gh, POLICY)

    def test_reconcile_publishes_decision_field_then_lifecycle_and_records_the_park(self):
        gh = FakeProject('Specifying', [posted()])
        with ledger_root(gh) as root:
            ledger = d.reconcile(root, 'specs/001', gh, publish_field=True)
            self.assertEqual(ledger['lifecycle'], {'parked': True})
            self.assertEqual(d.read(root / 'specs/001/workflow/decisions.json')['lifecycle'], {'parked': True})
            gh.comments[:] = [tick(posted(), 'A')]
            gh.status = 'Waiting for answers'
            resumed = d.reconcile(root, 'specs/001', gh, publish_field=True)
        self.assertEqual(resumed['lifecycle'] if 'lifecycle' in resumed else {}, {})
        self.assertEqual([edit for edit in gh.edits if edit[0] == 'STATUS'],
                         [('STATUS', 'OPT-Waiting for answers'), ('STATUS', 'OPT-Specifying')])


class PreSpecifyTests(unittest.TestCase):
    def bound(self, state, previous=None):
        class Run:
            feature = Path(tempfile.gettempdir()) / 'sanduq-no-such-feature'

            def load(self, allow_branch_change=False):
                self.allowed = allow_branch_change
                return state
        run = Run()
        return d.bound_state(run, previous), run

    def test_paused_pre_specify_run_binds_without_a_source_or_active_claim(self):
        state = {'issue': 'acme/app#12', 'receipts': {'scope': {}}, 'active': None, 'status': 'paused'}
        result, run = self.bound(state)
        self.assertIs(result, state)
        self.assertTrue(run.allowed)
        self.assertFalse((run.feature / 'scope-source.json').exists())

    def test_active_foreign_executor_is_refused(self):
        for stage in ('scope', 'specify'):
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_ACTIVE_EXECUTOR_MISMATCH'):
                self.bound({'issue': 'acme/app#12', 'receipts': {}, 'active': {'stage': stage}})

    def test_active_owned_executor_requires_strict_branch_load(self):
        with patch.dict(d.os.environ, {'SANDUQ_WORKFLOW_CLAIM_TOKEN': 't', 'SANDUQ_WORKFLOW_SESSION_ID': 's'}):
            _, run = self.bound({'issue': 'acme/app#12', 'receipts': {},
                                 'active': {'stage': 'scope', 'token': 't', 'session_id': 's'}})
        self.assertFalse(run.allowed)

    def test_foreign_ledger_feature_is_refused(self):
        with self.assertRaisesRegex(d.WorkflowError, 'DECISION_BINDING_MISMATCH'):
            self.bound({'issue': 'acme/app#12', 'active': None}, {'feature': 'specs/other'})

    def test_specify_receipt_or_later_stage_requires_the_source_binding(self):
        for state in ({'issue': 'acme/app#12', 'receipts': {'specify': {}}, 'active': None},
                      {'issue': 'acme/app#12', 'receipts': {}, 'active': {'stage': 'plan'}}):
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_SOURCE_BINDING_REQUIRED'):
                self.bound(state)

    def test_resume_refuses_a_ledger_bound_to_another_issue(self):
        state = {'issue': 'acme/app#12', 'receipts': {}, 'active': None}
        self.bound(state, {'issue': 'acme/app#12'})
        with self.assertRaisesRegex(d.WorkflowError, 'DECISION_BINDING_MISMATCH'):
            self.bound(state, {'issue': 'acme/app#99'})

    def test_resume_reads_answers_and_never_writes_a_scope_source(self):
        gh = FakeGitHub([tick(posted(), 'B')])
        with ledger_root(gh, source=False) as root:
            ledger = d.reconcile(root, 'specs/001', gh)
            self.assertEqual(ledger['decisions'][0]['option'], 'B')
            self.assertFalse((root / 'specs/001/scope-source.json').exists())
            self.assertFalse((root / 'specs/001/spec.md').exists())


class FakeGitHub:
    def __init__(self, comments=None):
        self.comments = list(comments or [])
        self.patches = 0
        self.confirm = True

    def api(self, endpoint, method='GET', payload=None, pages=False):
        if method == 'POST':
            comment = {'id': len(self.comments) + 1, 'user': {'login': 'creator', 'type': 'User'},
                       'html_url': 'https://github.com/acme/app/issues/12#issuecomment-x',
                       'body': payload['body']}
            self.comments.append(comment)
            return comment
        if method == 'PATCH':
            comment = next(c for c in self.comments if endpoint.endswith('/' + str(c['id'])))
            if not self.confirm:
                return {'id': comment['id'], 'body': 'unchanged'}
            comment['body'] = payload['body']
            self.patches += 1
            return comment
        return self.comments if '/comments?' in endpoint else ISSUE


class FakeProject(FakeGitHub):
    def __init__(self, status, comments=None):
        super().__init__(comments)
        self.status, self.edits, self.fail = status, [], False
        self.decision = None
        self.options = {name: 'OPT-' + name for name in (
            'Specifying', 'Waiting for answers', 'Feature Specification', 'Need Clarifications')}

    def command(self, args):
        if args[1] == 'field-list':
            return {'totalCount': 1, 'fields': [{'name': 'Decision', 'id': 'DEC',
                    'type': 'ProjectV2SingleSelectField', 'options': [
                        {'name': n, 'id': 'D-' + n} for n in ('None', 'Waiting', 'Needs review', 'Applied')]}]}
        if args[1] == 'item-list':
            return {'totalCount': 1, 'items': [{'id': 'ITEM', 'status': self.status, 'decision': self.decision, 'content': {
                'type': 'Issue', 'number': 12, 'repository': 'acme/app'}}]}
        if self.fail:
            raise d.WorkflowError('GITHUB_DECISION_PROJECT_FAILED: boom')
        field = args[args.index('--field-id') + 1]
        option = args[args.index('--single-select-option-id') + 1]
        if field == 'STATUS':
            self.status = option.removeprefix('OPT-')
        if field == 'DEC':
            self.decision = option.removeprefix('D-')
        self.edits.append((field, option) if field == 'STATUS' else ('DEC', option))
        return {}


class ledger_root:
    """A temporary project with a checkpoint-free Run double bound to acme/app#12."""

    def __init__(self, gh, source=True):
        self.source = source
        self.gh = gh

    def __enter__(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        config = root / '.specify/extensions/project/config.json'
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({
            'projectId': 'P', 'projectNumber': 1, 'owner': 'acme', 'statusFieldId': 'STATUS',
            'statusOptions': getattr(self.gh, 'options', {})}), encoding='utf-8')
        if self.source:
            source = root / 'specs/001/scope-source.json'
            source.parent.mkdir(parents=True)
            source.write_text('{"repo":"acme/app","issue":12}', encoding='utf-8')
        else:
            (root / 'specs/001').mkdir(parents=True)

        class FakeRun:
            policy = POLICY

            def __init__(self, base, feature):
                self.feature = Path(base) / feature

            def load(self, allow_branch_change=False):
                return {'issue': 'acme/app#12', 'receipts': {}, 'active': None}
        self.patch = patch.object(d, 'Run', FakeRun)
        self.patch.start()
        return root

    def __exit__(self, *exc):
        self.patch.stop()
        self.folder.cleanup()


if __name__ == '__main__':
    unittest.main()
