import contextlib
import copy
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_scope import m as sm, FakeGitHub

path = Path(__file__).resolve().parents[1] / 'scripts/clarification.py'
spec = importlib.util.spec_from_file_location('clarification', path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ReviewGitHub(FakeGitHub):
    def __init__(self):
        super().__init__()
        self.comments = []
        self.fail_after_post = False
        self.viewer = 'creator'

    def comment(self, body, login='creator', association='OWNER', user_type='User'):
        item = {'id': len(self.comments) + 1000, 'body': body, 'user': {'login': login, 'type': user_type},
                'author_association': association, 'updated_at': '2026-09-10T00:00:00Z',
                'html_url': f'https://github.com/acme/app/issues/1#issuecomment-{len(self.comments) + 1000}'}
        self.comments.append(item)
        return copy.deepcopy(item)

    def api(self, endpoint, method='GET', payload=None, pages=False):
        if endpoint == 'user':
            return {'login': self.viewer}
        if endpoint.split('?')[0].endswith('/1/comments'):
            if method == 'POST':
                self.writes.append((method, endpoint, payload))
                item = self.comment(payload['body'])
                if self.fail_after_post:
                    self.fail_after_post = False
                    raise sm.ScopeError('HTTP response lost after successful comment creation')
                return item
            return copy.deepcopy(self.comments)
        return super().api(endpoint, method, payload, pages)


def question(key='failure', follows=None):
    return {'key': key, 'question': 'What should happen if the request fails?', 'why': 'The user needs a way to recover.',
            'recommendation': 'Keep the form and offer retry.', 'justification': 'This avoids losing entered information.',
            'details': 'The success path exists but the failure path is unspecified.', 'options': ['Retry', 'Start again'],
            'recommended_option': 1, 'follows_up': follows or []}


class ClarificationTests(unittest.TestCase):
    def test_mixed_case_answer_ids_match_without_prefix_collisions(self):
        q = {'version': 1, 'id': 'C2Q2', 'round': 2, 'question': 'Which platform?'}
        comments = [
            {'id': 1, 'user': {'login': 'creator'}, 'body': m.managed_comment('question', q, 'Question')},
            {'id': 2, 'user': {'login': 'creator'}, 'body': 'c2Q2: ArgoCD'},
            {'id': 3, 'user': {'login': 'creator'}, 'body': 'C2Q20: unrelated'},
        ]
        result = m.history(comments, 'creator')
        self.assertEqual([c['id'] for c in result['reply_candidates']['C2Q2']], [2])
        self.assertEqual([c['id'] for c in result['unmatched_comments']], [3])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # Windows hosted runners may expose TEMP through an 8.3 path alias.
        # Match the runtime's canonical path instead of comparing two aliases.
        self.root = Path(self.temp.name).resolve()
        sm.write_json(self.root / '.specify/extensions/project/config.json', {'projectId': 'P', 'projectNumber': 2,
                      'owner': 'acme', 'statusFieldId': 'F', 'statusOptions': {x: x for x in ['Backlog', m.FEATURE, m.WAITING, 'Ready', 'In progress', 'In review', 'Done']}, 'stateFile': '.specify/project-sync-state.json'})
        self.gh = ReviewGitHub()
        self.gh.add(1, status=m.FEATURE)['user'] = {'login': 'creator'}
        with patch.object(subprocess, 'check_output', return_value='https://github.com/acme/app.git'):
            self.scope = sm.Scope(self.root, self.gh)
        self.app = m.Clarification(self.scope)
        self.feature = self.root / 'specs/001-example'
        self.feature.mkdir(parents=True)
        (self.feature / 'spec.md').write_text('# Example\n\nThe form can be submitted.\n', encoding='utf-8')
        sm.write_json(self.feature / 'scope-source.json', {'repo': 'acme/app', 'issue': 1})
        sm.write_json(self.root / '.specify/feature.json', {'feature_directory': 'specs/001-example'})

    def tearDown(self):
        self.temp.cleanup()

    def move(self, status):
        self.gh.statuses[1] = status
        self.scope._board = None

    def analysis(self, questions=None, answers=None, engine='clarify'):
        snapshot = self.app.inspect('1')
        return {'version': 1, 'issue': 1, 'snapshot_digest': snapshot['snapshot_digest'], 'engine': engine,
                'coverage': {'functional': 'Reviewed', 'failure': 'Missing' if questions else 'Clear'},
                'summary': 'The failure behavior requires a decision.' if questions else 'All decisions are resolved.',
                'questions': questions or [], 'answers': answers or [], 'spec_edits': []}

    def test_waiting_stops_before_reading_comments_or_spec(self):
        self.move(m.WAITING)
        with patch.object(self.app, 'spec_path', side_effect=AssertionError('must not read spec')):
            with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_WAITING'):
                self.app.inspect('1')
        self.assertEqual(self.gh.writes, [])

    def test_only_feature_specification_eligible(self):
        for status in ('Backlog', 'Ready', 'In review', 'Done'):
            self.move(status)
            with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_STATE'):
                self.app.inspect('1')

    def test_active_binding_resolves_identity(self):
        self.assertEqual(self.app.inspect()['issue']['number'], 1)

    def test_dispatch_falls_back_and_prefers_available_brainstorm(self):
        self.assertEqual(self.app.dispatch('1')['engine'], 'clarify')
        sm.write_json(self.root / '.specify/extensions/.registry', {'extensions': {'superspec': {'enabled': True}}})
        command = self.root / '.specify/extensions/superspec/commands/brainstorm.md'
        command.parent.mkdir(parents=True)
        command.write_text('# Brainstorm')
        skill = self.root / '.agents/skills/speckit-superspec-brainstorm/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('# Brainstorm skill')
        self.assertEqual(self.app.dispatch('1')['engine'], 'brainstorm')
        sm.write_json(self.root / '.specify/extensions/.registry', {'extensions': {'superspec': {'enabled': False}}})
        self.assertEqual(self.app.dispatch('1')['engine'], 'clarify')

    def test_more_than_five_questions_each_separate_and_creator_tagged(self):
        analysis = self.analysis([question(f'q-{n}') for n in range(12)])
        result = self.app.publish('1', analysis, True)
        qs = [c for c in self.gh.comments if m.record(c)['kind'] == 'question']
        self.assertEqual(len(qs), 12)
        self.assertEqual(result['status'], m.WAITING)
        self.assertIsNone(result['next_action'])
        self.assertTrue(all('@creator' in c['body'] and '**AI recommendation:' in c['body'] and '**Why I recommend it:**' in c['body'] for c in qs))

    def test_dry_run_posts_nothing_and_preserves_spec(self):
        before = (self.feature / 'spec.md').read_text()
        result = self.app.publish('1', self.analysis([question()]))
        self.assertTrue(result['dry_run'])
        self.assertFalse(result.get('next_action'))
        self.assertFalse(self.gh.writes)
        self.assertEqual((self.feature / 'spec.md').read_text(), before)

    def test_checkbox_choices_mark_exact_recommended_option_and_start_unchecked(self):
        q = question()
        q['recommended_option'] = 2
        body = self.app.publish('1', self.analysis([q]))['comment_previews'][0]
        self.assertIn('- [ ] **A.** Retry\n', body)
        self.assertIn('- [ ] **B.** Start again **(Recommended)**\n', body)
        self.assertEqual(body.count('**(Recommended)**'), 1)
        self.assertNotIn('- [x]', body)
        self.assertIn('No Quote reply is needed', body)
        self.assertIn('<summary>More context</summary>', body)

    def test_options_require_explicit_recommendation_without_guessing(self):
        for index in (None, 0, 3, True):
            q = question()
            q['recommended_option'] = index
            with self.assertRaisesRegex(sm.ScopeError, 'recommended_option'):
                self.app.publish('1', self.analysis([q]))

    def test_checkbox_answer_updates_spec_without_reply_comment(self):
        self.app.publish('1', self.analysis([question()]), True)
        q = self.gh.comments[0]
        q['body'] = q['body'].replace('- [ ] **A.**', '- [x] **A.**')
        self.move(m.FEATURE)
        observed = self.app.inspect('1')['history']['questions']['C1Q1']['selection']
        self.assertEqual(observed, {'state': 'selected', 'labels': ['A'], 'options': ['Retry']})
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [q['id']], 'explanation': 'Retry was selected.'}
        review = self.analysis(answers=[answer])
        review['spec_edits'] = [{'before': 'The form can be submitted.', 'after': 'The form can be submitted. Offer retry on failure.'}]
        self.app.publish('1', review, True)
        self.assertEqual(self.gh.statuses[1], 'Ready')
        self.assertIn('Checkbox selection observed: A — Retry.', (self.feature / 'spec.md').read_text(encoding='utf-8'))

    def test_selected_followup_resolves_ambiguous_parent_but_not_unrelated(self):
        self.app.publish('1', self.analysis([question('parent'), question('unrelated')]), True)
        self.gh.comments[0]['body'] = self.gh.comments[0]['body'].replace('- [ ]', '- [x]')
        self.move(m.FEATURE)
        pending = [{'question_id': qid, 'disposition': 'unresolved', 'comment_ids': [],
                    'explanation': 'Needs an answer.'} for qid in ['C1Q1', 'C1Q2']]
        self.app.publish('1', self.analysis([question('followup', ['C1Q1']),
                                            question('other-followup', ['C1Q2'])], pending), True)
        followup = next(c for c in self.gh.comments if (m.record(c) or {}).get('id') == 'C2Q1')
        followup['body'] = followup['body'].replace('- [ ] **B.**', '- [x] **B.**')
        self.move(m.FEATURE)
        observed = self.app.inspect('1')['history']['reply_candidates']
        self.assertIn(followup['id'], [c['id'] for c in observed['C1Q1']])
        self.assertNotIn(followup['id'], [c['id'] for c in observed['C1Q2']])
        answers = [{'question_id': qid, 'disposition': 'answered', 'comment_ids': [followup['id']],
                    'explanation': 'The explicit follow-up settles this question.'} for qid in ['C1Q1', 'C2Q1']]
        answers += [{'question_id': qid, 'disposition': 'unresolved', 'comment_ids': [],
                     'explanation': 'Still pending.'} for qid in ['C1Q2', 'C2Q2']]
        self.app.publish('1', self.analysis([question('remaining', ['C1Q2', 'C2Q2'])], answers))
        followup['body'] = followup['body'].replace('- [ ] **A.**', '- [x] **A.**')
        self.assertNotIn(followup['id'], [c['id'] for c in self.app.inspect('1')['history']['reply_candidates']['C1Q1']])

    def test_multiple_checked_options_are_not_a_single_choice_answer(self):
        self.app.publish('1', self.analysis([question()]), True)
        q = self.gh.comments[0]
        q['body'] = q['body'].replace('- [ ]', '- [x]')
        self.move(m.FEATURE)
        self.assertEqual(self.app.inspect('1')['history']['questions']['C1Q1']['selection']['state'], 'ambiguous')
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [q['id']], 'explanation': 'Pick the first.'}
        with self.assertRaisesRegex(sm.ScopeError, 'human comment evidence'):
            self.app.publish('1', self.analysis(answers=[answer]), True)

    def test_edited_option_text_is_not_silently_accepted_as_original_choice(self):
        self.app.publish('1', self.analysis([question()]), True)
        q = self.gh.comments[0]
        q['body'] = q['body'].replace('- [ ] **A.** Retry', '- [x] **A.** Send email')
        self.move(m.FEATURE)
        self.assertEqual(self.app.inspect('1')['history']['questions']['C1Q1']['selection']['state'], 'edited')

    def test_single_feedback_comment_can_answer_multiple_questions(self):
        self.app.publish('1', self.analysis([question('first'), question('second')]), True)
        reply = self.gh.comment('C1Q1: A, but preserve drafts for 24 hours.\nC1Q2: B')
        self.move(m.FEATURE)
        snapshot = self.app.inspect('1')
        self.assertEqual([c['id'] for c in snapshot['history']['reply_candidates']['C1Q1']], [reply['id']])
        self.assertEqual([c['id'] for c in snapshot['history']['reply_candidates']['C1Q2']], [reply['id']])

    def test_checkbox_change_during_partial_publication_stops_retry(self):
        review = self.analysis([question()])
        self.gh.fail_after_post = True
        with self.assertRaisesRegex(sm.ScopeError, 'response lost'):
            self.app.publish('1', review, True)
        self.gh.comments[0]['body'] = self.gh.comments[0]['body'].replace('- [ ] **A.**', '- [x] **A.**')
        with self.assertRaisesRegex(sm.ScopeError, 'STALE'):
            self.app.publish('1', review, True)
        self.assertEqual(len(self.gh.comments), 1)

    def test_choice_letters_do_not_cap_options_at_26(self):
        self.assertEqual(m.option_label(27), 'AA')
        self.assertEqual(m.option_label(703), 'AAA')

    def test_no_questions_moves_ready(self):
        sm.write_json(self.root / '.specify/project-sync-state.json', {'001-example': {'issue': 1, 'status': m.FEATURE}})
        self.app.publish('1', self.analysis(), True)
        self.assertEqual(self.gh.statuses[1], 'Ready')
        self.assertEqual(sm.read_json(self.root / '.specify/project-sync-state.json')['001-example']['status'], 'Ready')

    def test_both_engines_dispatch_plan_after_resolved_publication(self):
        for engine in ('clarify', 'brainstorm'):
            self.move(m.FEATURE)
            result = self.app.publish('1', self.analysis(engine=engine), True)
            action = result['next_action']
            self.assertEqual(action['command'], '/speckit-plan')
            self.assertEqual(action['issue'], 1)
            self.assertEqual(Path(action['spec_path']), self.feature / 'spec.md')
            self.assertEqual(Path(action['feature_directory']), Path('specs/001-example'))
            self.assertEqual(action['feature_name'], '001-example')
            self.assertEqual(self.gh.statuses[1], 'Ready')

    def test_resolved_dry_run_does_not_dispatch_plan(self):
        result = self.app.publish('1', self.analysis())
        self.assertFalse(result.get('next_action'))
        self.assertEqual(self.gh.statuses[1], m.FEATURE)

    def test_failed_ready_transition_never_returns_plan_handoff(self):
        review = self.analysis()
        with patch.object(self.scope, 'set_status', side_effect=sm.ScopeError('Project update failed')):
            with self.assertRaisesRegex(sm.ScopeError, 'Project update failed'):
                self.app.publish('1', review, True)
        journals = list((self.root / '.specify/scope/clarifications').glob('*/journal.json'))
        self.assertEqual(len(journals), 1)
        self.assertFalse(sm.read_json(journals[0]).get('complete'))

    def test_plan_handoff_uses_reviewed_issue_not_another_active_feature(self):
        sm.write_json(self.root / '.specify/feature.json', {'feature_directory': 'specs/002-another'})
        result = self.app.publish('1', self.analysis(), True)
        self.assertEqual(Path(result['next_action']['spec_path']), self.feature / 'spec.md')

    def test_waiting_rerun_does_not_count_or_post(self):
        analysis = self.analysis([question()])
        self.app.publish('1', analysis, True)
        count = len(self.gh.comments)
        with self.assertRaisesRegex(sm.ScopeError, 'WAITING'):
            self.app.publish('1', analysis, True)
        self.assertEqual(len(self.gh.comments), count)

    def test_managed_reinvoke_waits_without_spam_then_consumes_reply(self):
        (self.root / '.specify/workflow.yml').write_text('schema_version: 1\nclarification:\n  resume_on_reinvoke: reread-answers\n', encoding='utf-8')
        self.app.publish('1', self.analysis([question()]), True)
        count = len(self.gh.comments)
        result = self.app.publish('1', self.analysis(), True)
        self.assertTrue(result['unchanged'])
        self.assertEqual(len(self.gh.comments), count)
        reply = self.gh.comment('C1Q1: Retry and keep form data.')
        answer = {'question_id':'C1Q1','disposition':'answered','comment_ids':[reply['id']], 'explanation':'The creator chose retry.'}
        review = self.analysis(answers=[answer])
        review['spec_edits'] = [{'before':'The form can be submitted.', 'after':'The form can be submitted; failures preserve input and permit retry.'}]
        result = self.app.publish('1', review, True)
        self.assertEqual(result['status'], 'Ready')
        self.assertIn('preserve input', (self.feature / 'spec.md').read_text())

    def test_answer_id_correlates_and_spec_is_updated(self):
        self.app.publish('1', self.analysis([question()]), True)
        reply = self.gh.comment('C1Q1: Keep the form and offer retry.')
        self.move(m.FEATURE)
        snapshot = self.app.inspect('1')
        self.assertEqual(snapshot['history']['reply_candidates']['C1Q1'][0]['id'], reply['id'])
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [reply['id']], 'explanation': 'The creator chose retry without data loss.'}
        review = self.analysis(answers=[answer])
        review['spec_edits'] = [{'before': 'The form can be submitted.', 'after': 'The form can be submitted. A failed request preserves input and offers retry.'}]
        self.app.publish('1', review, True)
        self.assertEqual(self.gh.statuses[1], 'Ready')
        self.assertIn('preserves input and offers retry', (self.feature / 'spec.md').read_text())

    def test_quote_reply_not_misread_as_generated_question(self):
        self.app.publish('1', self.analysis([question()]), True)
        q = self.gh.comments[0]
        quoted = '\n'.join('> ' + line for line in q['body'].splitlines())
        reply = self.gh.comment(quoted + '\n\nI choose retry.')
        self.move(m.FEATURE)
        snapshot = self.app.inspect('1')
        self.assertEqual(len(snapshot['history']['questions']), 1)
        self.assertEqual(snapshot['history']['reply_candidates']['C1Q1'][0]['id'], reply['id'])

    def test_control_authorization_and_quoted_controls(self):
        self.gh.comment('/clarification max-rounds 20', 'outsider', 'NONE')
        self.gh.comment('> /clarification close\n\nThis is a quote.')
        self.gh.comment('```text\n/clarification close\n```')
        self.gh.comment('20')
        self.assertEqual(self.app.inspect('1')['policy']['max_rounds'], 7)
        self.assertFalse(self.app.inspect('1')['policy']['closed'])
        self.gh.comment('Maximum clarification iterations: 10')
        self.assertEqual(self.app.inspect('1')['policy']['max_rounds'], 10)

    def test_creator_closure_records_waivers_and_ready(self):
        self.app.publish('1', self.analysis([question()]), True)
        self.gh.comment('Close the clarification process')
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'unresolved', 'comment_ids': [], 'explanation': 'The creator waived this decision; retry is an explicit proposed assumption.'}
        review = self.analysis(answers=[answer])
        review['summary'] = 'Failure behavior remains uncertain and was explicitly waived by the creator.'
        result = self.app.publish('1', review, True)
        self.assertEqual(self.gh.statuses[1], 'Ready')
        self.assertIn('waived, not answered', (self.feature / 'spec.md').read_text())
        self.assertIsNone(result['next_action'])

    def test_cannot_accept_ai_recommendation_as_human_answer(self):
        self.app.publish('1', self.analysis([question()]), True)
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [self.gh.comments[0]['id']], 'explanation': 'Accept the recommendation.'}
        with self.assertRaisesRegex(sm.ScopeError, 'human comment evidence'):
            self.app.publish('1', self.analysis(answers=[answer]), True)

    def test_cannot_drop_old_questions(self):
        self.app.publish('1', self.analysis([question()]), True)
        self.move(m.FEATURE)
        with self.assertRaisesRegex(sm.ScopeError, 'every prior question'):
            self.app.publish('1', self.analysis(), True)

    def test_uncorrelated_comment_cannot_silently_resolve_a_question(self):
        self.app.publish('1', self.analysis([question()]), True)
        reply = self.gh.comment('Looks fine to me.')
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [reply['id']], 'explanation': 'Assume retry.'}
        with self.assertRaisesRegex(sm.ScopeError, 'reference this question'):
            self.app.publish('1', self.analysis(answers=[answer]), True)

    def test_superseded_question_requires_human_evidence(self):
        self.app.publish('1', self.analysis([question()]), True)
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'superseded', 'comment_ids': [], 'explanation': 'Ignore the error path.'}
        with self.assertRaisesRegex(sm.ScopeError, 'human comment evidence'):
            self.app.publish('1', self.analysis(answers=[answer]), True)

    def test_superseding_human_requirement_updates_spec(self):
        self.app.publish('1', self.analysis([question()]), True)
        reply = self.gh.comment('C1Q1: Remove form submission from this feature; it is now read-only.')
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'superseded', 'comment_ids': [reply['id']], 'explanation': 'The creator removed submission, so submission failure is out of scope.'}
        review = self.analysis(answers=[answer])
        review['spec_edits'] = [{'before': 'The form can be submitted.', 'after': 'The form is read-only. Submission is out of scope.'}]
        self.app.publish('1', review, True)
        self.assertIn('read-only', (self.feature / 'spec.md').read_text())
        self.assertEqual(self.gh.statuses[1], 'Ready')

    def test_followups_are_next_round_across_engines(self):
        self.app.publish('1', self.analysis([question()]), True)
        self.gh.comment('C1Q1: It depends on the failure.')
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'unresolved', 'comment_ids': [], 'explanation': 'Failure types are not distinguished.'}
        self.app.publish('1', self.analysis([question('which-failures', ['C1Q1'])], [answer], 'brainstorm'), True)
        self.assertTrue(any((m.record(c) or {}).get('id') == 'C2Q1' for c in self.gh.comments))

    def test_cap_never_automatically_approves_unresolved_questions(self):
        for n in range(1, 8):
            meta = {'version': 1, 'round': n, 'id': f'C{n}Q1', 'batch': f'old-{n}', 'question': 'What should happen?'}
            self.gh.comment('<!-- speckit-clarification:question ' + json.dumps(meta) + ' -->\nQuestion')
        answers = [{'question_id': f'C{n}Q1', 'disposition': 'unresolved', 'comment_ids': [], 'explanation': 'Still no answer.'} for n in range(1, 8)]
        result = self.app.publish('1', self.analysis([question()], answers), True)
        self.assertEqual(result['outcome'], 'limit')
        self.assertIsNone(result['next_action'])
        self.assertEqual(result['questions'], 0)
        self.assertEqual(self.gh.statuses[1], m.WAITING)

    def test_higher_limit_allows_another_round(self):
        meta = {'version': 1, 'round': 7, 'id': 'C7Q1', 'batch': 'old-7', 'question': 'What should happen?'}
        self.gh.comment('<!-- speckit-clarification:question ' + json.dumps(meta) + ' -->\nQuestion')
        self.gh.comment('/clarification max-rounds 10')
        answer = {'question_id': 'C7Q1', 'disposition': 'unresolved', 'comment_ids': [], 'explanation': 'Needs an answer.'}
        result = self.app.publish('1', self.analysis([question('more', ['C7Q1'])], [answer]), True)
        self.assertEqual(result['round'], 8)
        self.assertEqual(result['questions'], 1)

    def test_lost_response_retry_does_not_duplicate_question(self):
        review = self.analysis([question()])
        self.gh.fail_after_post = True
        with self.assertRaisesRegex(sm.ScopeError, 'response lost'):
            self.app.publish('1', review, True)
        self.app.publish('1', review, True)
        self.assertEqual(len([c for c in self.gh.comments if m.record(c)['kind'] == 'question']), 1)

    def test_edited_answer_or_new_comment_invalidates_analysis(self):
        review = self.analysis([question()])
        self.gh.comment('A new requirement has arrived.')
        with self.assertRaisesRegex(sm.ScopeError, 'STALE'):
            self.app.publish('1', review, True)

    def illustrated(self):
        image = self.root / 'docs/clarify/c1.png'
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b'png bytes')
        return dict(question(), diagram_image={'path': 'docs/clarify/c1.png', 'alt': 'Retry keeps the form'},
                    diagram_text='- Submit -> fails -> Retry keeps entered data')

    def git(self, head='a' * 40, blob='b' * 40):
        def run(args, **kwargs):
            if 'rev-parse' in args:
                return subprocess.CompletedProcess(args, 0, head, '')
            return subprocess.CompletedProcess(args, 0, blob, '')
        return patch.object(subprocess, 'run', side_effect=run)

    def test_private_repo_image_is_commit_pinned_blob_url_never_raw(self):
        contents = []
        original = self.gh.api
        def api(endpoint, *args, **kwargs):
            if '/contents/' in endpoint:
                contents.append(endpoint)
                return {'sha': 'b' * 40}
            return original(endpoint, *args, **kwargs)
        with self.git(), patch.object(self.gh, 'api', side_effect=api):
            result = self.app.publish('1', self.analysis([self.illustrated()]))
        body = result['comment_previews'][0]
        self.assertIn(f'![Retry keeps the form](https://github.com/acme/app/blob/{"a" * 40}/docs/clarify/c1.png?raw=true)', body)
        self.assertNotIn('raw.githubusercontent.com', body)
        self.assertIn('Retry keeps entered data', body)
        self.assertEqual(contents, [f'repos/acme/app/contents/docs/clarify/c1.png?ref={"a" * 40}'])
        self.assertNotIn('image_fallbacks', result)

    def test_unhosted_image_falls_back_to_text_with_reason(self):
        original = self.gh.api
        def missing(endpoint, *args, **kwargs):
            if '/contents/' in endpoint:
                raise sm.ScopeError('HTTP 404: Not Found')
            return original(endpoint, *args, **kwargs)
        with self.git(), patch.object(self.gh, 'api', side_effect=missing):
            result = self.app.publish('1', self.analysis([self.illustrated()]))
        body = result['comment_previews'][0]
        self.assertNotIn('![', body)
        self.assertIn('Diagram image not embedded', body)
        self.assertIn('commit and push it', body)
        self.assertIn('- Submit -> fails -> Retry keeps entered data', body)
        self.assertIn('C1Q1', result['image_fallbacks'])
        # A pushed file whose bytes differ is not embedded either.
        def stale(endpoint, *args, **kwargs):
            return {'sha': 'c' * 40} if '/contents/' in endpoint else original(endpoint, *args, **kwargs)
        with self.git(), patch.object(self.gh, 'api', side_effect=stale):
            body = self.app.publish('1', self.analysis([self.illustrated()]))['comment_previews'][0]
        self.assertIn('differs from the local export', body)

    def test_image_outside_project_or_not_png_is_not_hosted(self):
        q = self.illustrated()
        for path in ('../outside.png', 'docs/clarify/c1.html', 'docs/clarify/missing.png'):
            q['diagram_image']['path'] = path
            result = self.app.publish('1', self.analysis([q]))
            self.assertIn('not an exported PNG inside the project', result['comment_previews'][0])

    def test_image_requires_text_version_and_alt(self):
        q = self.illustrated()
        del q['diagram_text']
        with self.assertRaisesRegex(sm.ScopeError, 'diagram_text'):
            self.app.publish('1', self.analysis([q]))
        q = self.illustrated()
        q['diagram_image']['alt'] = ''
        with self.assertRaisesRegex(sm.ScopeError, 'alt text'):
            self.app.publish('1', self.analysis([q]))

    def test_managed_questions_render_mermaid_but_refuse_raw_urls(self):
        (self.root / '.specify/workflow.yml').write_text('schema_version: 1\nclarification:\n  resume_on_reinvoke: reread-answers\n', encoding='utf-8')
        preview = self.app.publish('1', self.analysis([dict(question(), diagram='graph TD; A-->B')]))['comment_previews'][0]
        self.assertIn('\n```mermaid\ngraph TD; A-->B\n```\n', preview)
        self.assertIn('More context and diagram', preview)
        legacy = dict(question(), diagram_markdown='![x](https://raw.githubusercontent.com/acme/app/main/x.png)')
        with self.assertRaisesRegex(sm.ScopeError, 'INLINE_IMAGE_REQUIRED'):
            self.app.publish('1', self.analysis([legacy]))

    def test_plan_requires_ready(self):
        with self.assertRaisesRegex(sm.ScopeError, 'planning requires Ready'):
            self.app.plan_gate('1')
        self.move('Ready')
        self.assertEqual(self.app.plan_gate('1')['status'], 'Ready')

    # ---- workflow/clarifications.json (Scope 1.7.0) -------------------------------------------------------------

    def records_path(self):
        return self.feature / 'workflow/clarifications.json'

    def records(self):
        return sm.read_json(self.records_path())

    def test_a_published_question_is_recorded_as_pending(self):
        self.app.publish('1', self.analysis([question()]), True)
        document = self.records()
        self.assertEqual(document['v'], 1)
        item, = document['items']
        comment = self.gh.comments[0]
        self.assertEqual((item['source_id'], item['revision'], item['state']), ('C1Q1', 1, 'pending'))
        self.assertEqual(item['question'], 'What should happen if the request fails?')
        self.assertEqual(item['options'], ['Retry', 'Start again'])
        self.assertIsNone(item['answer'])
        self.assertIsNone(item['editor'])
        self.assertIsNone(item['answered_at'])
        self.assertIsNone(item['applied'])
        self.assertEqual(item['url'], f'https://github.com/acme/app/issues/1#issuecomment-{comment["id"]}')
        self.assertTrue(item['observed_at'])
        self.assertEqual(item['evidence'][0]['kind'], 'comment')
        self.assertNotIn(b'\r', self.records_path().read_bytes())
        self.assertEqual(list(self.records_path().parent.glob('*.tmp')), [])

    def test_a_dry_run_writes_no_records(self):
        self.app.publish('1', self.analysis([question()]))
        self.assertFalse(self.records_path().exists())

    def test_a_failed_transition_or_stale_publication_writes_no_records(self):
        review = self.analysis([question()])
        with patch.object(self.scope, 'set_status', side_effect=sm.ScopeError('Project update failed')):
            with self.assertRaisesRegex(sm.ScopeError, 'Project update failed'):
                self.app.publish('1', review, True)
        self.assertFalse(self.records_path().exists())
        stale = self.analysis([question()])
        self.gh.comment('A new human comment')
        with self.assertRaisesRegex(sm.ScopeError, 'STALE'):
            self.app.publish('1', stale, True)
        self.assertFalse(self.records_path().exists())

    def test_the_records_are_written_after_the_spec_and_before_the_journal_completes(self):
        order = []
        real = m.persist_clarifications

        def watch(path, items, batch):
            order.append(('persist', 'Offer retry' in (self.feature / 'spec.md').read_text(encoding='utf-8'),
                          sorted(bool(sm.read_json(j).get('complete')) for j in
                                 (self.root / '.specify/scope/clarifications').glob('*/journal.json'))))
            return real(path, items, batch)

        self.app.publish('1', self.analysis([question()]), True)
        q = self.gh.comments[0]
        q['body'] = q['body'].replace('- [ ] **A.**', '- [x] **A.**')
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [q['id']], 'explanation': 'Retry.'}
        review = self.analysis(answers=[answer])
        review['spec_edits'] = [{'before': 'The form can be submitted.', 'after': 'The form can be submitted. Offer retry.'}]
        with patch.object(m, 'persist_clarifications', watch):
            self.app.publish('1', review, True)
        # Only the earlier batch's journal is complete; this batch's is marked after the records are written.
        self.assertEqual(order, [('persist', True, [False, True])])
        self.assertTrue(all(sm.read_json(j).get('complete') for j in
                            (self.root / '.specify/scope/clarifications').glob('*/journal.json')))

    def test_a_checkbox_answer_is_applied_and_keeps_the_pending_revision(self):
        self.app.publish('1', self.analysis([question()]), True)
        q = self.gh.comments[0]
        q['body'] = q['body'].replace('- [ ] **A.**', '- [x] **A.**')
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [q['id']], 'explanation': 'Retry was selected.'}
        self.app.publish('1', self.analysis(answers=[answer]), True)
        pending, applied = self.records()['items']
        self.assertEqual((pending['revision'], pending['state']), (1, 'pending'))
        self.assertEqual((applied['source_id'], applied['revision'], applied['state']), ('C1Q1', 2, 'applied'))
        self.assertEqual(applied['answer'], {'kind': 'single', 'value': 'A'})
        self.assertIsNone(applied['editor'])  # who ticked the box is not recorded
        self.assertIsNone(applied['answered_at'])
        self.assertEqual(applied['applied']['evidence'], ['specs/001-example/spec.md#speckit-clarification:spec ' + applied['batch']])
        self.assertTrue(applied['applied']['at'])
        self.assertEqual([e['kind'] for e in applied['evidence']], ['selection', 'disposition'])
        self.assertEqual(applied['options'], ['Retry', 'Start again'])

    def test_a_reply_answer_records_its_author_and_the_option_it_names(self):
        self.app.publish('1', self.analysis([question()]), True)
        reply = self.gh.comment('C1Q1: B - start again please')
        self.gh.comments[-1]['created_at'] = '2026-09-11T10:00:00Z'
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [reply['id']], 'explanation': 'B chosen.'}
        self.app.publish('1', self.analysis(answers=[answer]), True)
        item = self.records()['items'][-1]
        self.assertEqual(item['answer'], {'kind': 'single', 'value': 'B'})
        self.assertEqual(item['editor'], 'creator')
        self.assertEqual(item['answered_at'], '2026-09-11T10:00:00Z')

    def test_a_free_text_reply_is_a_text_answer(self):
        self.app.publish('1', self.analysis([question()]), True)
        reply = self.gh.comment('C1Q1: Keep the form and offer retry.')
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [reply['id']], 'explanation': 'Text.'}
        self.app.publish('1', self.analysis(answers=[answer]), True)
        self.assertEqual(self.records()['items'][-1]['answer'], {'kind': 'text', 'value': 'Keep the form and offer retry.'})

    def test_several_ticked_options_without_an_answer_are_a_conflict(self):
        self.app.publish('1', self.analysis([question()]), True)
        q = self.gh.comments[0]
        q['body'] = q['body'].replace('- [ ] **A.**', '- [x] **A.**').replace('- [ ] **B.**', '- [x] **B.**')
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'unresolved', 'comment_ids': [], 'explanation': 'Two boxes are ticked.'}
        self.app.publish('1', self.analysis([question('again', ['C1Q1'])], [answer]), True)
        by_id = {}
        for item in self.records()['items']:
            by_id[item['source_id']] = item
        self.assertEqual(by_id['C1Q1']['state'], 'conflict')
        self.assertEqual(by_id['C2Q1']['state'], 'pending')

    def test_a_creator_closure_records_the_open_question_as_waived(self):
        self.app.publish('1', self.analysis([question()]), True)
        control = self.gh.comment('Close the clarification process')
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'unresolved', 'comment_ids': [], 'explanation': 'Waived by the creator.'}
        review = self.analysis(answers=[answer])
        review['summary'] = 'Failure behavior was explicitly waived by the creator.'
        self.app.publish('1', review, True)
        waived = self.records()['items'][-1]
        self.assertEqual(waived['state'], 'waived')
        self.assertIsNone(waived['answer'])
        self.assertEqual(waived['evidence'][0]['kind'], 'closure')
        self.assertEqual(waived['evidence'][0]['comment_id'], control['id'])

    def test_a_superseded_question_is_recorded_as_superseded(self):
        self.app.publish('1', self.analysis([question()]), True)
        reply = self.gh.comment('C1Q1: Neither; the form is replaced by a wizard.')
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'superseded', 'comment_ids': [reply['id']], 'explanation': 'Replaced.'}
        review = self.analysis(answers=[answer])
        review['spec_edits'] = [{'before': 'The form can be submitted.', 'after': 'The wizard can be submitted.'}]
        self.app.publish('1', review, True)
        self.assertEqual(self.records()['items'][-1]['state'], 'superseded')

    def test_building_the_records_makes_no_github_calls(self):
        self.app.publish('1', self.analysis([question()]), True)
        q = self.gh.comments[0]
        q['body'] = q['body'].replace('- [ ] **A.**', '- [x] **A.**')
        self.move(m.FEATURE)
        snapshot = self.app.inspect('1')
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [q['id']], 'explanation': 'Retry.'}
        analysis = self.analysis(answers=[answer])
        with patch.object(self.gh, 'api', side_effect=AssertionError('no GitHub call while rendering')):
            items = m.clarification_items(snapshot, analysis, 'ready', 2, 'b1', 'acme/app', {}, 'specs/001-example/spec.md', 'now')
        self.assertEqual(items[0]['state'], 'applied')

    def test_replaying_a_batch_replaces_its_records_and_unchanged_ones_keep_their_revision(self):
        item = {'source_id': 'C1Q1', 'question': 'Q?', 'options': ['A'], 'answer': None, 'state': 'pending', 'url': 'u',
                'editor': None, 'observed_at': 't1', 'answered_at': None, 'applied': None, 'evidence': [], 'batch': 'b1'}
        path = self.root / 'out/clarifications.json'
        first = m.persist_clarifications(path, [item], 'b1')
        self.assertEqual([(i['revision'], i['batch']) for i in first['items']], [(1, 'b1')])
        # Replay of the same batch (a repair after an interrupted publication): replaced in place.
        replay = m.persist_clarifications(path, [dict(item, observed_at='t2')], 'b1')
        self.assertEqual([(i['revision'], i['observed_at']) for i in replay['items']], [(1, 't2')])
        # A later batch that observes the same facts adds nothing.
        same = m.persist_clarifications(path, [dict(item, observed_at='t3', batch='b2')], 'b2')
        self.assertEqual(len(same['items']), 1)
        # A later batch with a change adds the next revision and keeps the earlier one.
        answered = dict(item, state='applied', answer={'kind': 'single', 'value': 'A'}, observed_at='t4', batch='b3',
                        applied={'at': 't4', 'evidence': ['spec.md']})
        changed = m.persist_clarifications(path, [answered], 'b3')
        self.assertEqual([(i['revision'], i['state']) for i in changed['items']], [(1, 'pending'), (2, 'applied')])
        self.assertEqual(sm.read_json(path), changed)

    def test_an_unreadable_records_file_is_moved_aside_not_overwritten(self):
        item = {'source_id': 'C1Q1', 'question': 'Q?', 'options': [], 'answer': None, 'state': 'pending', 'url': 'u',
                'editor': None, 'observed_at': 't1', 'answered_at': None, 'applied': None, 'evidence': [], 'batch': 'b1'}
        for bad in ('{"v": 2, "items": "x"}', '{not json', '[]'):
            path = self.root / 'out/clarifications.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            for old in path.parent.glob('clarifications.json*'):
                old.unlink()
            path.write_text(bad, encoding='utf-8')
            with patch('sys.stderr') as err:
                document = m.persist_clarifications(path, [item], 'b1')
            self.assertEqual([i['source_id'] for i in document['items']], ['C1Q1'])
            self.assertEqual(sm.read_json(path), document)
            self.assertEqual((path.parent / 'clarifications.json.unreadable-b1').read_text(encoding='utf-8'), bad)
            self.assertIn('CLARIFICATIONS_UNREADABLE', ''.join(c.args[0] for c in err.write.call_args_list))

    # ---- an interrupted publication, after the board moved -----------------------------------------------------

    def interrupted(self, review, target):
        """Publish `review` with the record write failing after the board moved to `target`."""
        with patch.object(m, 'persist_clarifications', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.app.publish('1', review, True)
        self.assertEqual(self.gh.statuses[1], target)
        self.assertFalse(self.records_path().exists())
        journal, = [j for j in (self.root / '.specify/scope/clarifications').glob('*/journal.json')
                    if not sm.read_json(j).get('complete')]
        self.assertFalse(sm.read_json(journal).get('complete'))
        return journal

    def interrupted_after_move(self, review, target):
        with patch.object(m, 'persist_clarifications', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.app.publish('1', review, True)
        self.assertEqual(self.gh.statuses[1], target)
        journal, = [j for j in (self.root / '.specify/scope/clarifications').glob('*/journal.json')
                    if not sm.read_json(j).get('complete')]
        return journal

    def retry_repairs_without_a_second_publication(self, review, target):
        posts = len([w for w in self.gh.writes if w[0] == 'POST'])
        transitions = []
        real = self.scope.set_status
        with patch.object(self.scope, 'set_status', side_effect=lambda *a: transitions.append(a) or real(*a)):
            result = self.app.publish('1', review, True)
        self.assertEqual(len([w for w in self.gh.writes if w[0] == 'POST']), posts)  # nothing posted twice
        self.assertEqual(transitions, [])  # the board is not moved again
        self.assertEqual(self.gh.statuses[1], target)
        self.assertTrue(self.records_path().exists())
        journal, = (self.root / '.specify/scope/clarifications').glob('*/journal.json')
        self.assertTrue(sm.read_json(journal).get('complete'))
        return result

    def test_a_retry_after_the_move_to_need_clarifications_repairs_the_records(self):
        review = self.analysis([question()])
        self.interrupted(review, m.WAITING)
        self.retry_repairs_without_a_second_publication(review, m.WAITING)
        item, = self.records()['items']
        self.assertEqual((item['source_id'], item['state']), ('C1Q1', 'pending'))
        self.assertEqual(len([c for c in self.gh.comments if m.record(c)['kind'] == 'question']), 1)

    def test_a_retry_after_the_move_to_ready_repairs_the_records_and_hands_off(self):
        review = self.analysis()
        self.interrupted(review, 'Ready')
        result = self.retry_repairs_without_a_second_publication(review, 'Ready')
        self.assertEqual(result['next_action']['command'], '/speckit-plan')
        self.assertEqual(self.records()['v'], 1)

    def test_a_retry_with_an_unreadable_records_file_moves_it_aside_and_finishes(self):
        review = self.analysis([question()])
        self.interrupted(review, m.WAITING)
        self.records_path().parent.mkdir(parents=True, exist_ok=True)
        self.records_path().write_text('{broken', encoding='utf-8')
        with patch('sys.stderr'):
            self.retry_repairs_without_a_second_publication(review, m.WAITING)
        self.assertEqual(len(self.records()['items']), 1)
        self.assertEqual(len(list(self.records_path().parent.glob('clarifications.json.unreadable-*'))), 1)

    def test_a_human_reply_after_the_crash_does_not_block_the_repair(self):
        review = self.analysis([question()])
        self.interrupted(review, m.WAITING)
        self.gh.comment('C1Q1: B - I changed my mind')  # a human replies before the retry
        preview = self.app.publish('1', review)
        self.assertTrue(preview['unfinished'])
        self.assertTrue(preview['dry_run'])
        self.assertIn('unfinished', preview['reason'])
        self.assertFalse(self.records_path().exists())
        result = self.retry_repairs_without_a_second_publication(review, m.WAITING)
        self.assertEqual(result['comment_ids'], {'C1Q1': 1000, 'summary': 1001})
        item, = self.records()['items']
        self.assertEqual((item['source_id'], item['state']), ('C1Q1', 'pending'))

    def test_a_repair_keeps_an_answer_that_arrived_after_the_crash_new(self):
        (self.root / '.specify/workflow.yml').write_text('schema_version: 1\nclarification:\n  resume_on_reinvoke: reread-answers\n', encoding='utf-8')
        review = self.analysis([question()])
        self.interrupted(review, m.WAITING)
        reply = self.gh.comment('C1Q1: B - start again please')
        self.retry_repairs_without_a_second_publication(review, m.WAITING)
        observed = sm.read_json(self.root / '.specify/scope/clarifications/1-observed.json')
        # The next run sees the reply as new input: the digest was not taken over the live thread.
        self.assertNotEqual(observed['waiting_digest'], self.app.inspect('1', gate=False)['snapshot_digest'])
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [reply['id']], 'explanation': 'B chosen.'}
        result = self.app.publish('1', self.analysis(answers=[answer]), True)
        self.assertNotIn('unchanged', result)
        self.assertEqual(result['outcome'], 'ready')
        applied = self.records()['items'][-1]
        self.assertEqual((applied['source_id'], applied['state'], applied['answer']),
                         ('C1Q1', 'applied', {'kind': 'single', 'value': 'B'}))

    def open_answer(self, qid):
        return {'question_id': qid, 'disposition': 'unresolved', 'comment_ids': [], 'explanation': 'Still open.'}

    def repaired_then_edited(self, edit):
        (self.root / '.specify/workflow.yml').write_text('schema_version: 1\nclarification:\n  resume_on_reinvoke: reread-answers\n', encoding='utf-8')
        self.app.publish('1', self.analysis([question()]), True)
        self.move(m.FEATURE)
        reply = self.gh.comment('C1Q1: A')
        second = self.analysis([question('again', ['C1Q1'])], [
            {'question_id': 'C1Q1', 'disposition': 'unresolved', 'comment_ids': [], 'explanation': 'Not yet.'}])
        journal = self.interrupted_after_move(second, m.WAITING)
        edit(reply)  # between the crash and the repair
        posts = len([w for w in self.gh.writes if w[0] == 'POST'])
        with patch('sys.stderr'):
            self.app.publish('1', second, True)
        self.assertEqual(len([w for w in self.gh.writes if w[0] == 'POST']), posts)
        self.assertTrue(sm.read_json(journal).get('complete'))
        self.move(m.FEATURE)
        return reply

    def test_a_checkbox_ticked_between_the_crash_and_the_repair_is_still_new(self):
        first = self.gh.comments

        def tick(reply):
            q = first[0]
            q['body'] = q['body'].replace('- [ ] **A.**', '- [x] **A.**')

        self.repaired_then_edited(tick)
        q = self.gh.comments[0]
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [q['id']], 'explanation': 'Ticked.'}
        third = self.analysis([question('more', ['C2Q1'])], [answer, self.open_answer('C2Q1')])
        # Nothing about the thread is unchanged: the tick is evaluated, not swallowed.
        result = self.app.publish('1', third, True)
        self.assertNotIn('unchanged', result)

    def test_an_existing_reply_edited_between_the_crash_and_the_repair_is_still_new(self):
        def edit_reply(reply):
            item = [c for c in self.gh.comments if c['id'] == reply['id']][0]
            item['body'] = 'C1Q1: B - actually this'
            item['updated_at'] = '2026-09-12T00:00:00Z'

        reply = self.repaired_then_edited(edit_reply)
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [reply['id']], 'explanation': 'B.'}
        third = self.analysis([question('more', ['C2Q1'])], [answer, self.open_answer('C2Q1')])
        result = self.app.publish('1', third, True)
        self.assertNotIn('unchanged', result)
        applied = [i for i in self.records()['items'] if i['source_id'] == 'C1Q1' and i['state'] == 'applied']
        self.assertEqual(applied[-1]['answer'], {'kind': 'single', 'value': 'B'})

    def test_the_repair_requires_every_journaled_comment_to_exist(self):
        review = self.analysis([question()])
        self.interrupted(review, m.WAITING)
        del self.gh.comments[0]
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_JOURNAL_INVALID'):
            self.app.publish('1', review, True)
        self.assertFalse(self.records_path().exists())

    def test_malformed_items_in_an_existing_file_are_quarantined_not_fatal(self):
        item = {'source_id': 'C1Q1', 'question': 'Q?', 'options': [], 'answer': None, 'state': 'pending', 'url': 'u',
                'editor': None, 'observed_at': 't1', 'answered_at': None, 'applied': None, 'evidence': [], 'batch': 'b1'}
        bad_documents = ['{"v":1,"items":[{}]}', '{"v":1,"items":[null]}', '{"v":1,"items":["x"]}',
                         '{"v":1,"items":[{"source_id":"C1Q1","revision":"2"}]}',
                         '{"v":1,"items":[{"source_id":"C1Q1","revision":0}]}',
                         '{"v":1,"items":[{"source_id":"C1Q1","revision":true}]}',
                         '{"v":1,"items":[{"source_id":null,"revision":1}]}']
        for bad in bad_documents:
            path = self.root / 'out/clarifications.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            for old in path.parent.glob('clarifications.json*'):
                old.unlink()
            path.write_text(bad, encoding='utf-8')
            with patch('sys.stderr'):
                document = m.persist_clarifications(path, [item], 'b1')
                replay = m.persist_clarifications(path, [item], 'b1')  # the replay merges into the fresh file
            self.assertEqual([i['revision'] for i in document['items']], [1], bad)
            self.assertEqual(replay, document)
            self.assertEqual((path.parent / 'clarifications.json.unreadable-b1').read_text(encoding='utf-8'), bad)

    def test_an_empty_or_falsy_existing_file_is_quarantined_not_overwritten(self):
        item = {'source_id': 'C1Q1', 'question': 'Q?', 'options': [], 'answer': None, 'state': 'pending', 'url': 'u',
                'editor': None, 'observed_at': 't1', 'answered_at': None, 'applied': None, 'evidence': [], 'batch': 'b1'}
        for bad in ('{}', '[]', '""', '', '0', 'null'):
            path = self.root / 'out/clarifications.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            for old in path.parent.glob('clarifications.json*'):
                old.unlink()
            path.write_text(bad, encoding='utf-8')
            with patch('sys.stderr') as err:
                m.persist_clarifications(path, [item], 'b1')
            self.assertEqual((path.parent / 'clarifications.json.unreadable-b1').read_text(encoding='utf-8'), bad, repr(bad))
            self.assertIn('CLARIFICATIONS_UNREADABLE', ''.join(c.args[0] for c in err.write.call_args_list))
        # A file that does not exist is simply created, with nothing set aside.
        fresh = self.root / 'new/clarifications.json'
        m.persist_clarifications(fresh, [item], 'b1')
        self.assertEqual(list(fresh.parent.glob('*.unreadable-*')), [])

    def link(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=target.is_dir())
        except (OSError, NotImplementedError):
            self.skipTest('this OS does not allow creating symbolic links here')

    def test_records_are_never_written_through_a_link(self):
        item = {'source_id': 'C1Q1', 'question': 'Q?', 'options': [], 'answer': None, 'state': 'pending', 'url': 'u',
                'editor': None, 'observed_at': 't1', 'answered_at': None, 'applied': None, 'evidence': [], 'batch': 'b1'}
        outside = self.root / 'outside.json'
        outside.write_text('keep', encoding='utf-8')
        path = self.root / 'feat/workflow/clarifications.json'
        path.parent.mkdir(parents=True)
        self.link(path, outside)
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATIONS_UNSAFE'):
            m.persist_clarifications(path, [item], 'b1')
        self.assertEqual(outside.read_text(encoding='utf-8'), 'keep')
        path.unlink()
        folder = self.root / 'other'
        folder.mkdir()
        (self.root / 'moved').mkdir()
        self.link(folder / 'workflow', self.root / 'moved')
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATIONS_UNSAFE'):
            m.persist_clarifications(folder / 'workflow/clarifications.json', [item], 'b1')
        self.assertEqual(list((self.root / 'moved').iterdir()), [])

    def test_publication_and_replay_survive_malformed_existing_items(self):
        review = self.analysis([question()])
        self.records_path().parent.mkdir(parents=True, exist_ok=True)
        self.records_path().write_text('{"v":1,"items":[{}]}', encoding='utf-8')
        with patch('sys.stderr'):
            self.app.publish('1', review, True)
        self.assertEqual(len(self.records()['items']), 1)
        self.assertEqual(len(list(self.records_path().parent.glob('clarifications.json.unreadable-*'))), 1)
        # An interrupted publication whose retry meets malformed items repairs too.
        q = self.gh.comments[0]
        q['body'] = q['body'].replace('- [ ] **A.**', '- [x] **A.**')
        self.move(m.FEATURE)
        answer = {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [q['id']], 'explanation': 'Retry.'}
        second = self.analysis(answers=[answer])
        journal = self.interrupted_after_move(second, 'Ready')
        self.records_path().write_text('{"v":1,"items":[null]}', encoding='utf-8')
        with patch('sys.stderr'):
            self.app.publish('1', second, True)
        self.assertTrue(sm.read_json(journal).get('complete'))

    def test_a_journal_that_no_longer_matches_does_not_bypass_the_status_gate(self):
        review = self.analysis([question()])
        journal = self.interrupted(review, m.WAITING)
        (journal.parent / 'analysis.json').unlink()
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_JOURNAL_INVALID'):
            self.app.publish('1', review, True)
        value = sm.read_json(journal)
        (journal.parent / 'analysis.json').write_text(json.dumps(review), encoding='utf-8')
        (self.feature / 'spec.md').write_text('# Changed by hand\n', encoding='utf-8')
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_JOURNAL_INVALID'):
            self.app.publish('1', review, True)
        self.assertFalse(value.get('complete'))

    def test_a_new_publication_still_meets_the_status_gate(self):
        self.move(m.WAITING)
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_WAITING'):
            self.app.publish('1', {'version': 1, 'issue': 1, 'snapshot_digest': 'x', 'engine': 'clarify', 'questions': []}, True)

    # ---- Scope 1.8.0: question cap and in-session first round ----------------------------------------------------

    def policy(self, text):
        (self.root / '.specify/workflow.yml').write_text('schema_version: 1\nclarification:\n' + text, encoding='utf-8')

    def test_the_question_cap_names_the_lowest_priority_keys_to_defer(self):
        self.policy('  max_questions_per_round: 2\n')
        questions = [dict(question('a'), priority=2), question('b'), dict(question('c'), priority=1), dict(question('d'), priority=3)]
        with self.assertRaisesRegex(sm.ScopeError, r'^CLARIFICATION_TOO_MANY_QUESTIONS: 4 > 2; defer d, b$'):
            self.app.publish('1', self.analysis(questions))
        self.assertEqual(self.gh.writes, [])
        for bad in (0, True, '1'):
            with self.assertRaisesRegex(sm.ScopeError, 'priority'):
                self.app.publish('1', self.analysis([dict(question(), priority=bad)]))
        result = self.app.publish('1', self.analysis(questions[:2]), True)
        self.assertEqual(result['questions'], 2)
        summary = next(c for c in self.gh.comments if m.record(c)['kind'] == 'round')
        self.assertEqual(m.record(summary)['max_questions_per_round'], 2)
        self.assertNotIn('no question-count cap', summary['body'])

    def test_no_cap_keeps_unlimited_questions(self):
        self.assertEqual(self.app.publish('1', self.analysis([question(f'q-{n}') for n in range(9)]))['questions'], 9)

    def session(self, edits=True):
        self.policy('  in_session_first_round: true\n')
        analysis = self.analysis([question('retry'), dict(question('draft'), options=[])])
        if edits:
            analysis['spec_edits'] = [{'before': 'The form can be submitted.',
                                       'after': 'The form can be submitted. A failed request keeps the form and offers retry.'}]
        answers = [{'key': 'retry', 'option': 1, 'answered_by': 'creator', 'answered_at': '2026-10-18T09:00:00Z'},
                   {'key': 'draft', 'answer': 'Keep a local draft.', 'answered_by': 'Creator', 'answered_at': '2026-10-18T09:01:00Z'}]
        return analysis, answers

    def test_in_session_dry_run_previews_one_comment_and_writes_nothing(self):
        analysis, answers = self.session()
        before = (self.feature / 'spec.md').read_text()
        result = self.app.publish('1', analysis, False, answers)
        self.assertEqual((result['dry_run'], result['status'], result['in_session']), (True, 'Ready', True))
        preview = result['comment_preview']
        self.assertTrue(preview.startswith('<!-- speckit-clarification:round-in-session '))
        self.assertIn('#### C1Q1: What should happen if the request fails?\n\n**Answer:** **A.** Retry', preview)
        self.assertIn('**Answer:** Keep a local draft.', preview)
        self.assertIn('**Answered by:** @creator at 2026-10-18T09:00:00Z', preview)
        self.assertEqual(self.gh.writes, [])
        self.assertEqual((self.feature / 'spec.md').read_text(), before)
        self.assertFalse(self.records_path().exists())

    def test_in_session_apply_posts_once_edits_the_spec_records_and_moves_ready(self):
        analysis, answers = self.session()
        result = self.app.publish('1', analysis, True, answers)
        self.assertEqual(len(self.gh.comments), 1)
        posted = m.record(self.gh.comments[0])
        self.assertEqual((posted['kind'], posted['round'], posted['question_ids']), ('round-in-session', 1, ['C1Q1', 'C1Q2']))
        self.assertEqual(self.gh.statuses[1], 'Ready')
        self.assertEqual(result['next_action']['command'], '/speckit-plan')
        spec = (self.feature / 'spec.md').read_text(encoding='utf-8')
        self.assertIn('A failed request keeps the form and offers retry.', spec)
        self.assertIn('- C1Q2 (draft): Keep a local draft.\n  Answered in session by @Creator at 2026-10-18T09:01:00Z.\n', spec)
        items = self.records()['items']
        self.assertEqual([(i['source_id'], i['state']) for i in items], [('C1Q1', 'applied'), ('C1Q2', 'applied')])
        self.assertEqual(items[0]['answer'], {'kind': 'single', 'value': 'A'})
        self.assertEqual(items[1]['answer'], {'kind': 'text', 'value': 'Keep a local draft.'})
        self.assertEqual(items[0]['evidence'][0]['kind'], 'in-session')
        self.assertEqual(items[0]['evidence'][0]['comment_id'], self.gh.comments[0]['id'])
        self.move(m.FEATURE)
        self.assertEqual(self.app.inspect('1')['next_round'], 2)  # the in-session round counts
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_IN_SESSION_ROUND'):
            self.app.publish('1', self.session()[0], False, answers)

    def test_in_session_rerun_after_a_failed_move_finishes_without_a_second_comment(self):
        analysis, answers = self.session()
        with patch.object(self.scope, 'set_status', side_effect=sm.ScopeError('board unavailable')):
            with self.assertRaisesRegex(sm.ScopeError, 'board unavailable'):
                self.app.publish('1', analysis, True, answers)
        self.assertEqual(self.gh.statuses[1], m.FEATURE)
        self.app.publish('1', analysis, True, answers)
        self.assertEqual(len(self.gh.comments), 1)
        self.assertEqual(self.gh.statuses[1], 'Ready')
        self.assertEqual(len(self.records()['items']), 2)

    def test_in_session_refusals(self):
        analysis, answers = self.session(edits=False)
        self.policy('  in_session_first_round: false\n')
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_IN_SESSION_DISABLED'):
            self.app.publish('1', analysis, False, answers)
        self.policy('  in_session_first_round: true\n')
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_IN_SESSION_UNANSWERED: .*draft'):
            self.app.publish('1', analysis, False, answers[:1])
        for change in ({'option': 3}, {'option': 1, 'answer': 'x'}, {'key': 'other'}, {'answered_at': 'yesterday'}):
            with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_ANSWERS_INVALID'):
                self.app.publish('1', analysis, False, [dict(answers[0], **change), answers[1]])
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_IN_SESSION_IDENTITY'):
            self.app.publish('1', analysis, False, [answers[0], dict(answers[1], answered_by='someone')])
        self.gh.viewer = 'someone'
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_IN_SESSION_IDENTITY'):
            self.app.publish('1', analysis, False, answers)
        self.gh.viewer = 'creator'
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_IN_SESSION_STATE'):
            self.app.publish('1', self.analysis(), False, [])
        self.assertEqual(self.gh.writes, [])

    def test_the_answers_example_is_accepted(self):
        example = json.loads((Path(m.__file__).parents[1] / 'examples/answers.json').read_text(encoding='utf-8'))
        analysis = {'questions': [dict(question('failed-delivery')), dict(question('retry-limit'), options=[])]}
        given = self.app.session_answers(analysis, [dict(a, answered_by='creator') for a in example], 'creator')
        self.assertEqual([given[k]['answer']['kind'] for k in ('failed-delivery', 'retry-limit')], ['single', 'text'])

    def test_in_session_cli_reads_the_answers_file(self):
        analysis, answers = self.session()
        sm.write_json(self.root / 'a.json', analysis)
        sm.write_json(self.root / 'answers.json', answers)
        out = io.StringIO()
        with patch.object(m, 'Scope', return_value=self.scope), contextlib.redirect_stdout(out):
            code = m.main(['publish', '1', '--root', str(self.root), '--analysis', str(self.root / 'a.json'),
                           '--answers', str(self.root / 'answers.json')])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.getvalue())['in_session'])

    def test_a_cached_waiting_status_is_reread_before_refusing(self):
        self.move(m.WAITING)
        self.scope.board()  # the shared cache now says Need Clarifications
        self.gh.statuses[1] = m.FEATURE  # the creator moved it back on GitHub
        with patch.object(subprocess, 'check_output', return_value='https://github.com/acme/app.git'):
            fresh = m.Clarification(sm.Scope(self.root, self.gh))
        self.assertEqual(fresh.inspect('1')['issue']['number'], 1)

    # ---- the shared test vector ---------------------------------------------------------------------------------

    VECTOR = Path(__file__).resolve().parent / 'fixtures/clarifications-vector.json'

    def build_vector(self):
        """Run `clarification_items` over a realistic snapshot: every state and evidence kind Scope writes."""
        self.app.publish('1', self.analysis([question(f'q-{n}') for n in range(1, 5)]), True)
        for n, c in enumerate(self.gh.comments):
            c['created_at'] = '2026-09-10T08:0%d:00Z' % n
        q1, q2, q3, q4 = [c for c in self.gh.comments if m.record(c)['kind'] == 'question']
        q1['body'] = q1['body'].replace('- [ ] **A.**', '- [x] **A.**')  # a ticked box
        q2['body'] = q2['body'].replace('- [ ] **A.**', '- [x] **A.**').replace('- [ ] **B.**', '- [x] **B.**')  # two ticks
        reply = self.gh.comment('C1Q3: B - start again please')
        self.gh.comments[-1]['created_at'] = '2026-09-11T10:00:00Z'
        wizard = self.gh.comment('C1Q4: Neither; the form is replaced by a wizard.')
        self.gh.comments[-1]['created_at'] = '2026-09-11T10:05:00Z'
        self.move(m.FEATURE)
        snapshot = self.app.inspect('1')
        answers = [
            {'question_id': 'C1Q1', 'disposition': 'answered', 'comment_ids': [q1['id']], 'explanation': 'Retry was ticked.'},
            {'question_id': 'C1Q2', 'disposition': 'unresolved', 'comment_ids': [], 'explanation': 'Two boxes are ticked.'},
            {'question_id': 'C1Q3', 'disposition': 'answered', 'comment_ids': [reply['id']], 'explanation': 'B chosen in a reply.'},
            {'question_id': 'C1Q4', 'disposition': 'superseded', 'comment_ids': [wizard['id']], 'explanation': 'Replaced.'}]
        waiting = {'questions': [question('again', ['C1Q2'])], 'answers': answers}
        closing = {'questions': [], 'answers': [dict(a, disposition='unresolved', comment_ids=[]) for a in answers]}
        now = '2026-09-12T09:00:00+00:00'
        cases = []
        snapshot['policy'] = dict(snapshot['policy'], closed=False, control_comment_ids=[])
        cases.append({'name': 'round-two-publication', 'outcome': 'waiting', 'items': m.clarification_items(
            snapshot, waiting, 'waiting', 2, 'batch-round-two', 'acme/app', {'C2Q1': 2000},
            'specs/001-example/spec.md', now)})
        closed = dict(snapshot, policy=dict(snapshot['policy'], closed=True, control_comment_ids=[3001]))
        cases.append({'name': 'creator-closure', 'outcome': 'closed', 'items': m.clarification_items(
            closed, closing, 'closed', 2, 'batch-closed', 'acme/app', {}, 'specs/001-example/spec.md', now)})
        first = {'issue': snapshot['issue'], 'comments': [], 'history': {'questions': {}}, 'policy': snapshot['policy']}
        session = {'questions': [question('retry'), question('draft')], 'answers': []}
        given = {'retry': {'answer': {'kind': 'single', 'value': 'A'}, 'answered_by': 'creator', 'answered_at': '2026-09-12T08:55:00Z'},
                 'draft': {'answer': {'kind': 'text', 'value': 'Keep a draft.'}, 'answered_by': 'creator', 'answered_at': '2026-09-12T08:56:00Z'}}
        cases.append({'name': 'in-session-first-round', 'outcome': 'ready', 'items': m.clarification_items(
            first, session, 'ready', 1, 'batch-in-session', 'acme/app', {'summary': 3002}, 'specs/001-example/spec.md',
            now, in_session=given)})
        return {'v': 1,
                'note': 'Produced by clarification_items in extensions/scope/scripts/clarification.py. Regenerate with '
                        'UPDATE_CLARIFICATIONS_VECTOR=1 python -m unittest test_clarification.',
                'cases': cases}

    def test_the_shared_vector_matches_what_scope_writes(self):
        import os
        vector = self.build_vector()
        text = json.dumps(vector, indent=2, ensure_ascii=False) + '\n'
        if os.environ.get('UPDATE_CLARIFICATIONS_VECTOR'):
            self.VECTOR.parent.mkdir(parents=True, exist_ok=True)
            self.VECTOR.write_text(text, encoding='utf-8', newline='\n')
        self.assertEqual(json.loads(self.VECTOR.read_text(encoding='utf-8')), vector)
        states = {i['state'] for case in vector['cases'] for i in case['items']}
        self.assertEqual(states, {'applied', 'conflict', 'superseded', 'pending', 'waived'})
        kinds = {e['kind'] for case in vector['cases'] for i in case['items'] for e in i['evidence']}
        self.assertEqual(kinds, {'comment', 'disposition', 'selection', 'closure', 'in-session'})
        for case in vector['cases']:
            for item in case['items']:
                self.assertTrue(all(set(e) == {'kind', 'url', 'comment_id', 'explanation'} for e in item['evidence']))
                if item['applied']:
                    self.assertIsInstance(item['applied']['evidence'], list)
                    self.assertTrue(all(isinstance(x, str) for x in item['applied']['evidence']))


if __name__ == '__main__':
    unittest.main()
