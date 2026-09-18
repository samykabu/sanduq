import copy
import importlib.util
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

    def comment(self, body, login='creator', association='OWNER', user_type='User'):
        item = {'id': len(self.comments) + 1000, 'body': body, 'user': {'login': login, 'type': user_type},
                'author_association': association, 'updated_at': '2026-09-10T00:00:00Z',
                'html_url': f'https://github.com/acme/app/issues/1#issuecomment-{len(self.comments) + 1000}'}
        self.comments.append(item)
        return copy.deepcopy(item)

    def api(self, endpoint, method='GET', payload=None, pages=False):
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
        self.root = Path(self.temp.name)
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

    def test_plan_requires_ready(self):
        with self.assertRaisesRegex(sm.ScopeError, 'planning requires Ready'):
            self.app.plan_gate('1')
        self.move('Ready')
        self.assertEqual(self.app.plan_gate('1')['status'], 'Ready')


if __name__ == '__main__':
    unittest.main()
