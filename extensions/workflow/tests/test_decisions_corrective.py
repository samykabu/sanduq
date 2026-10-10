import copy
import json
import subprocess
import unittest
from unittest.mock import patch
import test_decisions_selectable as f

d = f.d


def marker_edit(comment, **changes):
    result = copy.deepcopy(comment)
    match = d.MARKER.match(result['body'])
    data = json.loads(match[1]); data.update(changes)
    result['body'] = '<!-- sanduq-decision:question ' + json.dumps(data) + ' -->\n' + result['body'][match.end():]
    return result


class CorrectiveTests(unittest.TestCase):
    def test_backlog_parks_and_answers_return_to_specification(self):
        gh = f.FakeProject('Todo', [f.posted()])
        policy = copy.deepcopy(f.POLICY); policy['scope']['statuses']['Backlog'] = 'Todo'
        with f.ledger_root(gh) as root, patch.dict(f.POLICY['scope']['statuses'], {'Backlog': 'Todo'}):
            parked = d.reconcile(root, 'specs/001', gh, publish_field=True)
            self.assertEqual((gh.status, parked['lifecycle']), ('Waiting for answers', {'parked': True}))
            gh.comments = [f.tick(f.posted(), 'A')]
            resumed = d.reconcile(root, 'specs/001', gh, publish_field=True)
            self.assertEqual((gh.status, resumed['lifecycle']), ('Specifying', {}))

    def test_marker_semantics_cannot_change_visible_question(self):
        for changes in ({'options': ['Changed', 'Second', 'Third']}, {'mode': 'multiple'},
                        {'recommended': 1}, {'id': 'SD2'}):
            with self.subTest(changes=changes), self.assertRaises(d.WorkflowError):
                f.rows(marker_edit(f.tick(f.posted(), 'A', 'B'), **changes))

    def test_recorded_marker_and_application_cannot_be_replaced(self):
        gh = f.FakeGitHub([f.tick(f.posted(), 'A')])
        with f.ledger_root(gh) as root:
            ledger = d.reconcile(root, 'specs/001', gh)
            item = ledger['decisions'][0]; item['status'] = 'applied'
            item['application'] = {'answer_digest': item['answer_digest'], 'evidence': {'x': 'y'}}
            d.write(root / 'specs/001/workflow/decisions.json', ledger)
            # A complete self-consistent replacement still conflicts with trusted evidence.
            gh.comments = [f.tick(f.posted(options=('Different', 'Second', 'Third')), 'A')]
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_QUESTION_EDITED'):
                d.reconcile(root, 'specs/001', gh)
            gh.comments = [marker_edit(f.tick(f.posted(), 'A'), request_digest='changed')]
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_QUESTION_EDITED'):
                d.reconcile(root, 'specs/001', gh)

    def test_noop_remote_status_write_fails_verification(self):
        gh = f.FakeProject('Specifying', [f.posted()]); original = gh.command
        def noop(args):
            if args[1] == 'item-edit' and 'STATUS' in args: return {}
            return original(args)
        gh.command = noop
        with f.ledger_root(gh) as root:
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_STATUS_VERIFICATION_FAILED'):
                d.reconcile(root, 'specs/001', gh, publish_field=True)
            self.assertNotIn('parked', d.read(root / 'specs/001/workflow/decisions.json')['lifecycle'])

    def test_noop_remote_decision_write_fails_verification(self):
        gh = f.FakeProject('Specifying', [f.posted()]); original = gh.command
        gh.command = lambda args: {} if args[1] == 'item-edit' else original(args)
        with f.ledger_root(gh) as root:
            with self.assertRaisesRegex(d.WorkflowError, 'DECISION_FIELD_VERIFICATION_FAILED'):
                d.reconcile(root, 'specs/001', gh, publish_field=True)
            self.assertEqual(gh.status, 'Specifying')

    def test_lost_response_recovers_owned_park_and_answered_return(self):
        gh = f.FakeProject('Specifying', [f.posted()]); original = gh.command
        def lost(args):
            result = original(args)
            if args[1] == 'item-edit' and 'STATUS' in args:
                raise d.WorkflowError('lost response')
            return result
        gh.command = lost
        with f.ledger_root(gh) as root:
            with self.assertRaisesRegex(d.WorkflowError, 'lost response'):
                d.reconcile(root, 'specs/001', gh, publish_field=True)
            self.assertEqual(gh.status, 'Waiting for answers')
            gh.command = original; gh.comments = [f.tick(f.posted(), 'A')]
            result = d.reconcile(root, 'specs/001', gh, publish_field=True)
            self.assertEqual((gh.status, result['lifecycle']), ('Specifying', {}))

    def test_active_checkpoint_branch_enforced(self):
        class Run:
            feature = f.Path('specs/001')
            def load(self, allow_branch_change=False):
                if not allow_branch_change: raise d.WorkflowError('CHECKPOINT_BRANCH_MISMATCH')
                return {'issue': 'acme/app#12', 'active': {'stage': 'scope'}}
        with self.assertRaisesRegex(d.WorkflowError, 'CHECKPOINT_BRANCH_MISMATCH'):
            d.bound_state(Run())

    def test_decisions_use_shared_rest_transport_after_rate_limit(self):
        client = d.GitHub(); module = d.scope_transport(); transport = module.GitHub()
        client._project = transport
        client.project_cfg = {'owner': 'acme', 'ownerType': 'org', 'projectNumber': 7}
        fields = [{'id': 1, 'node_id': 'F', 'name': 'Decision', 'data_type': 'single_select', 'options': []}]
        def run(args, **kwargs):
            if args[1] == 'project': return subprocess.CompletedProcess(args, 1, '', 'API rate limit exceeded')
            if args[2] == 'graphql': return subprocess.CompletedProcess(args, 1, '', 'API rate limit exceeded')
            if args[2].endswith('projectsV2/7'):
                return subprocess.CompletedProcess(args, 0, json.dumps({'number': 7, 'owner': {'login': 'acme', 'type': 'Organization'}}), '')
            return subprocess.CompletedProcess(args, 0, json.dumps([fields]), '')
        with patch.object(module.subprocess, 'run', run):
            result = client.command(['project', 'field-list', '7', '--owner', 'acme'])
        self.assertEqual(result['fields'][0]['id'], 'F')
        self.assertEqual(client.project_transport, 'rest')


if __name__ == '__main__': unittest.main()
