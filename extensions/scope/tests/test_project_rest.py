import importlib.util
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/scope.py'
spec = importlib.util.spec_from_file_location('scope', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
sys.modules['scope'] = m

CFG = {'owner': 'acme', 'ownerType': 'org', 'projectNumber': 7, 'projectId': 'PVT_1'}
BASE = 'orgs/acme/projectsV2/7'
FIELDS = [
    {'id': 101, 'node_id': 'PVTSSF_status', 'name': 'Status', 'data_type': 'single_select',
     'options': [{'id': 'opt-ready', 'name': {'raw': 'Ready', 'html': 'Ready'}}]},
    {'id': 102, 'node_id': 'PVTF_blocked', 'name': 'Blocked by', 'data_type': 'text'},
    {'id': 103, 'node_id': 'PVTF_title', 'name': 'Title', 'data_type': 'title'},
]
ITEMS = [
    {'id': 9001, 'node_id': 'PVTI_a', 'content_type': 'Issue',
     'content': {'number': 5, 'title': 'Five', 'html_url': 'https://github.com/acme/app/issues/5',
                 'repository_url': 'https://api.github.com/repos/acme/app'},
     'fields': [{'id': 101, 'name': 'Status', 'data_type': 'single_select',
                 'value': {'id': 'opt-ready', 'name': {'raw': 'Ready', 'html': 'Ready'}}},
                {'id': 102, 'name': 'Blocked by', 'data_type': 'text', 'value': '#3, #4'},
                {'id': 103, 'name': 'Title', 'data_type': 'title', 'value': {'raw': 'Five'}}]},
    {'id': 9002, 'node_id': 'PVTI_b', 'content_type': 'PullRequest',
     'content': {'number': 6, 'title': 'PR', 'repository_url': 'https://api.github.com/repos/acme/other'},
     'fields': []},
    {'id': 9003, 'node_id': 'PVTI_c', 'content_type': 'DraftIssue', 'content': {'title': 'Draft'}, 'fields': []},
]


def done(stdout='', returncode=0, stderr=''):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class FakeGh:
    """Routes `gh` subprocess calls: `gh project` and GraphQL behave as configured, REST is served."""

    def __init__(self, project_ok=True, remaining=0, project_error='unknown owner type'):
        self.project_ok, self.remaining, self.project_error = project_ok, remaining, project_error
        self.calls = []
        self.writes = []

    def __call__(self, cmd, input=None, **_):
        args = cmd[1:]
        self.calls.append(args)
        if args[0] == 'project':
            if self.project_ok:
                return done(json.dumps({'items': [], 'totalCount': 0, 'fields': [], 'id': 'PVTI_gql'}))
            return done(returncode=1, stderr=self.project_error)
        if args[:2] == ['api', 'graphql']:
            if self.remaining is None:
                return done(returncode=1, stderr='GraphQL: API rate limit exceeded for user ID 1.')
            return done(json.dumps({'data': {'rateLimit': {'remaining': self.remaining, 'resetAt': '2026-09-25T12:00:00Z'}}}))
        endpoint = args[1]
        method = args[args.index('--method') + 1] if '--method' in args else 'GET'
        payload = json.loads(input) if input else None
        path = endpoint.split('?')[0]
        if method != 'GET':
            self.writes.append((method, endpoint, payload))
        if path == f'{BASE}/fields':
            return done(json.dumps([FIELDS]))
        if path == f'{BASE}/items' and method == 'GET':
            return done(json.dumps([ITEMS[:2], ITEMS[2:]]))
        if path == f'{BASE}/items' and method == 'POST':
            return done(json.dumps({'id': 9010, 'node_id': 'PVTI_new'}))
        if path.startswith(f'{BASE}/items/') and method == 'PATCH':
            return done(json.dumps({'id': int(path.rsplit('/', 1)[1])}))
        if path == 'repos/acme/app/issues/12':
            return done(json.dumps({'id': 555012, 'number': 12}))
        raise AssertionError(args)

    def rest_calls(self):
        return [c for c in self.calls if c[0] == 'api' and c[1] != 'graphql']


class ProjectRestFallbackTests(unittest.TestCase):
    def client(self, fake):
        gh = m.GitHub()
        gh.project_cfg = CFG
        self.patcher = patch.object(m.subprocess, 'run', fake)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        return gh

    def run_quiet(self, fn, *args):
        err = io.StringIO()
        with redirect_stderr(err):
            result = fn(*args)
        return result, err.getvalue()

    def test_graphql_success_does_not_use_fallback(self):
        fake = FakeGh(project_ok=True)
        gh = self.client(fake)
        gh.command(['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        self.assertEqual(fake.rest_calls(), [])
        self.assertNotIn(['api', 'graphql', '-f', 'query={rateLimit{remaining resetAt}}'], fake.calls)
        self.assertEqual(gh.project_transport, 'graphql')

    def test_misleading_error_with_budget_left_is_not_masked(self):
        fake = FakeGh(project_ok=False, remaining=4200)
        gh = self.client(fake)
        with self.assertRaisesRegex(m.ScopeError, 'unknown owner type'):
            gh.command(['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        self.assertEqual(fake.rest_calls(), [])
        self.assertIsNone(gh.project_transport)

    def test_misleading_error_with_exhausted_budget_uses_rest(self):
        fake = FakeGh(project_ok=False, remaining=0, project_error='unknown owner type')
        gh = self.client(fake)
        data, err = self.run_quiet(gh.command, ['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        self.assertEqual(data['totalCount'], 3)
        self.assertIn('GraphQL rate-limited', err)
        self.assertIn('REST Projects API', err)
        self.assertEqual(gh.project_transport, 'rest')

    def test_rate_limited_budget_probe_also_uses_rest(self):
        fake = FakeGh(project_ok=False, remaining=None, project_error='')
        gh = self.client(fake)
        data, _ = self.run_quiet(gh.command, ['project', 'field-list', '7', '--owner', 'acme', '--format', 'json'])
        self.assertEqual([f['name'] for f in data['fields']], ['Status', 'Blocked by', 'Title'])

    def test_rest_stays_selected_until_reset_without_retrying_graphql(self):
        fake = FakeGh(project_ok=False, remaining=0)
        gh = self.client(fake)
        self.run_quiet(gh.command, ['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        attempts = len([c for c in fake.calls if c[0] == 'project'])
        self.run_quiet(gh.command, ['project', 'field-list', '7', '--owner', 'acme', '--format', 'json'])
        self.assertEqual(len([c for c in fake.calls if c[0] == 'project']), attempts)

    def test_non_project_failures_are_not_rerouted(self):
        fake = FakeGh(remaining=0)
        gh = self.client(fake)
        with patch.object(m.subprocess, 'run', lambda *a, **k: done(returncode=1, stderr='boom')):
            with self.assertRaisesRegex(m.ScopeError, 'boom'):
                gh.command(['issue', 'view', '1'])

    def test_item_list_mapping_matches_gh_shape(self):
        fake = FakeGh(project_ok=False, remaining=0)
        gh = self.client(fake)
        data, _ = self.run_quiet(gh.command, ['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        issue, pull, draft = data['items']
        self.assertEqual(issue['id'], 'PVTI_a')
        self.assertEqual(issue['status'], 'Ready')
        self.assertEqual(issue['blocked by'], '#3, #4')
        self.assertEqual(issue['title'], 'Five')
        self.assertEqual(issue['content']['repository'], 'acme/app')
        self.assertEqual(issue['content']['type'], 'Issue')
        self.assertEqual(issue['content']['number'], 5)
        self.assertEqual(pull['content']['type'], 'PullRequest')
        self.assertEqual(pull['content']['repository'], 'acme/other')
        self.assertEqual(draft['content']['type'], 'DraftIssue')
        listing = next(c for c in fake.rest_calls() if c[1].startswith(f'{BASE}/items'))
        self.assertEqual(listing[1], f'{BASE}/items?per_page=100&fields=101,102,103')
        self.assertIn('--paginate', listing)

    def test_field_list_mapping_includes_types_and_options(self):
        fake = FakeGh(project_ok=False, remaining=0)
        gh = self.client(fake)
        data, _ = self.run_quiet(gh.command, ['project', 'field-list', '7', '--owner', 'acme', '--format', 'json'])
        status = data['fields'][0]
        self.assertEqual(status, {'id': 'PVTSSF_status', 'name': 'Status', 'type': 'ProjectV2SingleSelectField',
                                  'options': [{'id': 'opt-ready', 'name': 'Ready'}]})
        self.assertEqual(data['fields'][1]['type'], 'ProjectV2Field')

    def test_item_edit_single_select_patch_uses_database_ids(self):
        fake = FakeGh(project_ok=False, remaining=0)
        gh = self.client(fake)
        self.run_quiet(gh.command, ['project', 'item-edit', '--id', 'PVTI_a', '--project-id', 'PVT_1',
                                    '--field-id', 'PVTSSF_status', '--single-select-option-id', 'opt-ready'])
        self.assertEqual(fake.writes, [('PATCH', f'{BASE}/items/9001', {'fields': [{'id': 101, 'value': 'opt-ready'}]})])

    def test_item_edit_text_patch_and_clear(self):
        fake = FakeGh(project_ok=False, remaining=0)
        gh = self.client(fake)
        self.run_quiet(gh.command, ['project', 'item-edit', '--id', 'PVTI_b', '--project-id', 'PVT_1',
                                    '--field-id', 'PVTF_blocked', '--text', '#1, #2'])
        self.run_quiet(gh.command, ['project', 'item-edit', '--id', 'PVTI_a', '--project-id', 'PVT_1',
                                    '--field-id', 'PVTF_blocked', '--text', ''])
        self.assertEqual(fake.writes, [
            ('PATCH', f'{BASE}/items/9002', {'fields': [{'id': 102, 'value': '#1, #2'}]}),
            ('PATCH', f'{BASE}/items/9001', {'fields': [{'id': 102, 'value': None}]}),
        ])

    def test_listings_are_cached_across_operations(self):
        fake = FakeGh(project_ok=False, remaining=0)
        gh = self.client(fake)
        self.run_quiet(gh.command, ['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        for item in ('PVTI_a', 'PVTI_b'):
            self.run_quiet(gh.command, ['project', 'item-edit', '--id', item, '--project-id', 'PVT_1',
                                        '--field-id', 'PVTSSF_status', '--single-select-option-id', 'opt-ready'])
        reads = [c[1].split('?')[0] for c in fake.rest_calls() if '--method' not in c]
        self.assertEqual(reads.count(f'{BASE}/fields'), 1)
        self.assertEqual(reads.count(f'{BASE}/items'), 1)

    def test_item_add_posts_issue_database_id_and_resolves_new_item(self):
        fake = FakeGh(project_ok=False, remaining=0)
        gh = self.client(fake)
        self.run_quiet(gh.command, ['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        added, _ = self.run_quiet(gh.command, ['project', 'item-add', '7', '--owner', 'acme', '--url',
                                               'https://github.com/acme/app/issues/12', '--format', 'json'])
        self.assertEqual(added, {'id': 'PVTI_new'})
        self.run_quiet(gh.command, ['project', 'item-edit', '--id', 'PVTI_new', '--project-id', 'PVT_1',
                                    '--field-id', 'PVTSSF_status', '--single-select-option-id', 'opt-ready'])
        self.assertEqual(fake.writes, [
            ('POST', f'{BASE}/items', {'type': 'Issue', 'id': 555012}),
            ('PATCH', f'{BASE}/items/9010', {'fields': [{'id': 101, 'value': 'opt-ready'}]}),
        ])

    def test_user_owned_board_uses_users_path(self):
        rest = m.ProjectRest(None, {'owner': 'sam', 'ownerType': 'user', 'projectNumber': 3})
        self.assertEqual(rest.base, 'users/sam/projectsV2/3')

    def test_unsupported_actions_raise(self):
        fake = FakeGh(project_ok=False, remaining=0)
        gh = self.client(fake)
        with self.assertRaisesRegex(m.ScopeError, 'does not support `gh project field-create`'):
            self.run_quiet(gh.command, ['project', 'field-create', '7', '--owner', 'acme', '--name', 'X'])
        with self.assertRaisesRegex(m.ScopeError, 'single-select and text'):
            self.run_quiet(gh.command, ['project', 'item-edit', '--id', 'PVTI_a', '--project-id', 'PVT_1',
                                        '--field-id', 'PVTF_blocked', '--number', '3'])

    def test_transport_is_reported_on_stdout_results_only(self):
        gh = m.GitHub()
        self.assertEqual(m.with_transport({'a': 1}, gh), {'a': 1})
        gh.transports.update({'rest', 'graphql'})
        self.assertEqual(m.with_transport({'a': 1}, gh), {'a': 1, 'transport': 'graphql+rest'})
        self.assertEqual(m.with_transport([1], gh), [1])


if __name__ == '__main__':
    unittest.main()
