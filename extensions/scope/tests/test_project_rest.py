import importlib.util
import io
import json
import subprocess
import sys
import time
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

    def __init__(self, project_ok=True, remaining=0, project_error='unknown owner type',
                 owner_blocked=False, project_lookup='ok', extra_items=(), post_error=None, race_items=()):
        self.extra_items, self.post_error, self.race_items = list(extra_items), post_error, list(race_items)
        self.project_ok, self.remaining, self.project_error = project_ok, remaining, project_error
        self.owner_blocked, self.project_lookup = owner_blocked, project_lookup
        self.calls = []
        self.writes = []

    def __call__(self, cmd, input=None, **_):
        args = cmd[1:]
        self.calls.append(args)
        if args[0] == 'project':
            if self.project_ok:
                return done(json.dumps({'items': [], 'totalCount': 0, 'fields': [], 'id': 'PVTI_gql'}))
            return done(returncode=1, stderr=self.project_error)
        if args[:2] == ['api', 'graphql'] and any('repositoryOwner' in a for a in args):
            if self.owner_blocked:
                return done(returncode=1, stderr='GraphQL: API rate limit already exceeded (type RATE_LIMIT)')
            return done(json.dumps({'data': {'repositoryOwner': {'login': 'acme'}}}))
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
        if path == 'users/acme/projectsV2/7':
            return done(returncode=1, stderr='HTTP 404: Not Found')
        if path == BASE:
            self.project_lookups = getattr(self, 'project_lookups', 0) + 1
            if self.project_lookup == 'ok':
                return done(json.dumps({'number': 7, 'node_id': 'PVT_1', 'owner': {'login': 'acme', 'type': 'Organization'}}))
            if self.project_lookup == 'other':
                return done(json.dumps({'number': 8, 'node_id': 'PVT_1', 'owner': {'login': 'acme', 'type': 'Organization'}}))
            if self.project_lookup == 'node':
                return done(json.dumps({'number': 7, 'node_id': 'PVT_other', 'owner': {'login': 'acme', 'type': 'Organization'}}))
            if self.project_lookup == 'user':
                return done(json.dumps({'number': 7, 'node_id': 'PVT_1', 'owner': {'login': 'acme', 'type': 'User'}}))
            return done(returncode=1, stderr={'missing': 'HTTP 404: Not Found', 'denied': 'HTTP 403: Forbidden'}[self.project_lookup])
        if path == f'{BASE}/fields':
            return done(json.dumps([FIELDS]))
        if path == f'{BASE}/items' and method == 'GET':
            return done(json.dumps([ITEMS[:2], ITEMS[2:] + self.extra_items]))
        if path == f'{BASE}/items' and method == 'POST' and self.post_error:
            self.extra_items += self.race_items
            return done(returncode=1, stderr=self.post_error)
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
        fake = FakeGh(project_ok=False, remaining=4200, project_lookup='missing')
        gh = self.client(fake)
        with self.assertRaisesRegex(m.ScopeError, 'unknown owner type'):
            gh.command(['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        self.assertEqual(fake.rest_calls(), [['api', BASE, '-H', 'Accept: application/vnd.github+json']])
        self.assertIsNone(gh.project_transport)
        self.assertEqual(gh._rest_until, 0.0)

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

    def test_explicit_rate_limit_with_positive_budget_uses_rest(self):
        fake = FakeGh(project_ok=False, remaining=67,
                      project_error='GraphQL: API rate limit exceeded for user ID 1.')
        gh = self.client(fake)
        data, err = self.run_quiet(gh.command, ['project', 'item-list', '7', '--owner', 'acme',
                                                '--limit', '10000', '--format', 'json'])
        self.assertEqual(data['totalCount'], 3)
        self.assertIn('GraphQL rate-limited', err)
        self.assertEqual(gh.project_transport, 'rest')
        self.assertGreater(gh._rest_until, time.time())

    def test_explicit_rate_limit_with_failed_probe_uses_rest(self):
        fake = FakeGh(project_ok=False, remaining=None,
                      project_error='GraphQL: API rate limit exceeded for user ID 1.')
        gh = self.client(fake)
        data, _ = self.run_quiet(gh.command, ['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        self.assertEqual(data['totalCount'], 3)
        self.assertEqual(gh.project_transport, 'rest')

    ITEM_LIST = ['project', 'item-list', '7', '--owner', 'acme', '--limit', '10000', '--format', 'json']

    def test_masked_owner_error_with_positive_budget_and_blocked_owner_query_uses_rest(self):
        fake = FakeGh(project_ok=False, remaining=4200, owner_blocked=True)
        gh = self.client(fake)
        data, err = self.run_quiet(gh.command, self.ITEM_LIST)
        self.assertEqual(data['totalCount'], 3)
        self.assertIn('GraphQL rate-limited', err)
        self.assertEqual(gh.project_transport, 'rest')
        self.assertGreater(gh._rest_until, time.time())

    def test_masked_owner_error_verified_by_rest_project_uses_rest(self):
        fake = FakeGh(project_ok=False, remaining=4200)
        gh = self.client(fake)
        data, _ = self.run_quiet(gh.command, self.ITEM_LIST)
        self.assertEqual(data['totalCount'], 3)
        self.assertEqual(gh.project_transport, 'rest')
        self.assertEqual(fake.project_lookups, 1)

    def test_masked_owner_error_is_not_accepted_for_wrong_or_inaccessible_project(self):
        for lookup in ('missing', 'denied', 'other'):
            with self.subTest(lookup=lookup):
                fake = FakeGh(project_ok=False, remaining=4200, project_lookup=lookup)
                gh = self.client(fake)
                with self.assertRaisesRegex(m.ScopeError, 'unknown owner type'):
                    gh.command(self.ITEM_LIST)
                self.assertIsNone(gh.project_transport)
                self.assertFalse([c for c in fake.rest_calls() if c[1] != BASE])
                self.patcher.stop()

    def test_masked_owner_error_rejects_wrong_owner_type_config(self):
        fake = FakeGh(project_ok=False, remaining=4200, project_lookup='missing')
        gh = self.client(fake)
        gh.project_cfg = {**CFG, 'ownerType': 'user'}
        with self.assertRaisesRegex(m.ScopeError, 'unknown owner type'):
            gh.command(self.ITEM_LIST)
        self.assertEqual(fake.rest_calls()[0][1], 'users/acme/projectsV2/7')

    def test_other_errors_with_positive_budget_never_probe_the_owner_or_rest_project(self):
        fake = FakeGh(project_ok=False, remaining=4200, project_error='accepts at most 1 arg(s)',
                      owner_blocked=True)
        gh = self.client(fake)
        with self.assertRaisesRegex(m.ScopeError, 'accepts at most'):
            gh.command(self.ITEM_LIST)
        self.assertEqual(fake.rest_calls(), [])
        self.assertFalse([c for c in fake.calls if any('repositoryOwner' in a for a in c)])

    def test_throttling_variants_use_rest(self):
        for message in ('GraphQL: API rate limit exceeded for user ID 1.', 'HTTP 403: You have exceeded a secondary rate limit',
                        'was submitted too quickly: rate limited (RATE_LIMIT)'):
            with self.subTest(message=message):
                fake = FakeGh(project_ok=False, remaining=4200, project_error=message)
                gh = self.client(fake)
                data, _ = self.run_quiet(gh.command, self.ITEM_LIST)
                self.assertEqual(data['totalCount'], 3)
                self.assertEqual(gh.project_transport, 'rest')
                self.patcher.stop()

    def test_rest_fallback_after_masked_error_keeps_write_before_reread(self):
        fake = FakeGh(project_ok=False, remaining=4200)
        gh = self.client(fake)
        self.run_quiet(gh.command, self.ITEM_LIST)
        self.run_quiet(gh.command, ['project', 'item-edit', '--id', 'PVTI_a', '--field-id', 'PVTF_blocked',
                                    '--project-id', 'PVT_1', '--text', 'x'])
        self.assertEqual(fake.writes, [('PATCH', f'{BASE}/items/9001', {'fields': [{'id': 102, 'value': 'x'}]})])
        self.assertEqual(gh.project_transport, 'rest')

    def mismatch_fake(self, **kw):
        fake = FakeGh(project_ok=False, remaining=4200, **kw)
        return fake, self.client(fake)

    def test_mismatched_request_identity_is_rejected_before_any_rest_operation(self):
        requests = {
            'owner': ['project', 'item-list', '7', '--owner', 'typo', '--format', 'json'],
            'number': ['project', 'item-list', '999', '--owner', 'acme', '--format', 'json'],
            'missing number': ['project', 'item-list', '--owner', 'acme', '--format', 'json'],
            'project id': ['project', 'item-edit', '--id', 'PVTI_a', '--project-id', 'WRONG', '--field-id', 'PVTF_blocked', '--text', 'x'],
            'no project id': ['project', 'item-edit', '--id', 'PVTI_a', '--field-id', 'PVTF_blocked', '--text', 'x'],
            'unsupported option': ['project', 'item-list', '7', '--owner', 'acme', '--query', 'is:open'],
            'format': ['project', 'item-list', '7', '--owner', 'acme', '--format', 'csv'],
            'two values': ['project', 'item-edit', '--id', 'PVTI_a', '--project-id', 'PVT_1', '--field-id', 'PVTF_blocked',
                           '--text', 'x', '--single-select-option-id', 'o'],
        }
        for name, request in requests.items():
            for error, extra in (('unknown owner type', {}), ('GraphQL: API rate limit exceeded', {}), ('blocked (type RATE_LIMIT)', {})):
                with self.subTest(request=name, error=error):
                    fake, gh = self.mismatch_fake(project_error=error, **extra)
                    with self.assertRaises(m.ScopeError):
                        self.run_quiet(gh.command, request)
                    self.assertEqual(fake.writes, [])
                    self.assertEqual([c for c in fake.rest_calls() if c[1] != BASE], [])
                    self.assertNotEqual(gh.project_transport, 'rest')
                    self.patcher.stop()

    def test_live_project_identity_must_match_before_rest_operations(self):
        for lookup in ('node', 'user', 'other'):
            with self.subTest(lookup=lookup):
                fake, gh = self.mismatch_fake(project_error='GraphQL: API rate limit exceeded', project_lookup=lookup)
                with self.assertRaisesRegex(m.ScopeError, 'not the configured Project'):
                    self.run_quiet(gh.command, ['project', 'item-edit', '--id', 'PVTI_a', '--project-id', 'PVT_1',
                                                '--field-id', 'PVTF_blocked', '--text', 'x'])
                self.assertEqual(fake.writes, [])
                self.assertEqual([c for c in fake.rest_calls() if c[1] != BASE], [])
                self.patcher.stop()

    def test_isolated_rate_limit_token_with_positive_budget_uses_rest(self):
        for message in ('GraphQL blocked (type RATE_LIMIT)', 'RATE-LIMIT', 'API  rate	limit hit'):
            with self.subTest(message=message):
                fake, gh = self.mismatch_fake(project_error=message)
                data, _ = self.run_quiet(gh.command, self.ITEM_LIST)
                self.assertEqual(data['totalCount'], 3)
                self.assertEqual(gh.project_transport, 'rest')
                self.patcher.stop()

    def test_permission_and_invalid_command_errors_are_not_converted(self):
        for message in ('HTTP 403: Resource not accessible by personal access token', 'unknown flag: --bogus',
                        'GraphQL: Could not resolve to a ProjectV2'):
            with self.subTest(message=message):
                fake, gh = self.mismatch_fake(project_error=message)
                with self.assertRaises(m.ScopeError):
                    gh.command(self.ITEM_LIST)
                self.assertEqual(fake.rest_calls(), [])
                self.assertIsNone(gh.project_transport)
                self.patcher.stop()

    def test_unrelated_failure_with_positive_budget_is_raised(self):
        fake = FakeGh(project_ok=False, remaining=67, project_error='GraphQL: Could not resolve to a ProjectV2')
        gh = self.client(fake)
        with self.assertRaisesRegex(m.ScopeError, 'Could not resolve'):
            gh.command(['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        self.assertEqual(fake.rest_calls(), [])
        self.assertIsNone(gh.project_transport)
        self.assertEqual(gh._rest_until, 0.0)

    def test_zero_budget_with_unrelated_message_uses_rest(self):
        fake = FakeGh(project_ok=False, remaining=0, project_error='GraphQL: Could not resolve to a ProjectV2')
        gh = self.client(fake)
        data, _ = self.run_quiet(gh.command, ['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        self.assertEqual(data['totalCount'], 3)
        self.assertEqual(gh.project_transport, 'rest')

    def test_graphql_is_used_again_after_reset(self):
        fake = FakeGh(project_ok=False, remaining=67,
                      project_error='GraphQL: API rate limit exceeded for user ID 1.')
        gh = self.client(fake)
        self.run_quiet(gh.command, ['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        self.assertEqual(gh.project_transport, 'rest')
        gh._rest_until = time.time() - 1
        fake.project_ok = True
        _, err = self.run_quiet(gh.command, ['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        self.assertIn('GraphQL budget recovered', err)
        self.assertEqual(gh._rest_until, 0.0)
        self.assertEqual(gh.project_transport, 'graphql+rest')

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

    ADD = ['project', 'item-add', '7', '--owner', 'acme', '--url', 'https://github.com/acme/app/issues/12', '--format', 'json']
    EXISTING = {'id': 9020, 'node_id': 'PVTI_old', 'content_type': 'Issue',
                'content': {'number': 12, 'id': 555012, 'repository_url': 'https://api.github.com/repos/acme/app'}, 'fields': []}
    DUPLICATE = 'HTTP 422: Content already exists in this project'

    def listings(self, fake):
        return [c for c in fake.rest_calls() if c[1].startswith(f'{BASE}/items') and '--method' not in c]

    def test_item_add_returns_existing_item_without_writing(self):
        fake = FakeGh(project_ok=False, remaining=0, extra_items=[self.EXISTING])  # on the second listing page
        gh = self.client(fake)
        added, _ = self.run_quiet(gh.command, self.ADD)
        self.assertEqual(added, {'id': 'PVTI_old'})
        self.assertEqual(fake.writes, [])
        self.assertEqual(gh._rest._item_ids['PVTI_old'], 9020)

    def test_item_add_same_number_in_other_repository_or_kind_is_added(self):
        other = {**self.EXISTING, 'node_id': 'PVTI_x', 'content': {**self.EXISTING['content'], 'repository_url': 'https://api.github.com/repos/acme/other'}}
        pull = {**self.EXISTING, 'node_id': 'PVTI_y', 'content_type': 'PullRequest'}
        wrong_id = {**self.EXISTING, 'node_id': 'PVTI_z', 'content': {**self.EXISTING['content'], 'id': 1}}
        fake = FakeGh(project_ok=False, remaining=0, extra_items=[other, pull, wrong_id])
        gh = self.client(fake)
        added, _ = self.run_quiet(gh.command, self.ADD)
        self.assertEqual(added, {'id': 'PVTI_new'})
        self.assertEqual([w[0] for w in fake.writes], ['POST'])

    def test_item_add_duplicate_race_rereads_once_and_returns_the_item(self):
        fake = FakeGh(project_ok=False, remaining=0, post_error=self.DUPLICATE, race_items=[self.EXISTING])
        gh = self.client(fake)
        added, _ = self.run_quiet(gh.command, self.ADD)
        self.assertEqual(added, {'id': 'PVTI_old'})
        self.assertEqual([w[0] for w in fake.writes], ['POST'])
        self.assertEqual(len(self.listings(fake)), 2)

    def test_item_add_duplicate_error_without_matching_item_is_raised(self):
        fake = FakeGh(project_ok=False, remaining=0, post_error=self.DUPLICATE)
        gh = self.client(fake)
        with self.assertRaisesRegex(m.ScopeError, 'already exists'):
            self.run_quiet(gh.command, self.ADD)
        self.assertEqual([w[0] for w in fake.writes], ['POST'])
        self.assertEqual(len(self.listings(fake)), 2)

    def test_item_add_unrelated_errors_are_raised_without_a_reread(self):
        for error in ('HTTP 422: Validation Failed', 'HTTP 404: Not Found', 'HTTP 403: Forbidden'):
            with self.subTest(error=error):
                fake = FakeGh(project_ok=False, remaining=0, post_error=error, race_items=[self.EXISTING])
                gh = self.client(fake)
                with self.assertRaisesRegex(m.ScopeError, error[:8]):
                    self.run_quiet(gh.command, self.ADD)
                self.assertEqual([w[0] for w in fake.writes], ['POST'])
                self.assertEqual(len(self.listings(fake)), 1)
                self.patcher.stop()

    def test_item_add_rereads_board_instead_of_trusting_the_listing_cache(self):
        fake = FakeGh(project_ok=False, remaining=0)
        gh = self.client(fake)
        self.run_quiet(gh.command, ['project', 'item-list', '7', '--owner', 'acme', '--format', 'json'])
        fake.extra_items.append(self.EXISTING)  # added elsewhere after the cached listing
        added, _ = self.run_quiet(gh.command, self.ADD)
        self.assertEqual(added, {'id': 'PVTI_old'})
        self.assertEqual(fake.writes, [])

    def test_user_owned_board_uses_users_path(self):
        rest = m.ProjectRest(None, {'owner': 'sam', 'ownerType': 'user', 'projectNumber': 3})
        self.assertEqual(rest.base, 'users/sam/projectsV2/3')

    def test_unsupported_actions_raise(self):
        fake = FakeGh(project_ok=False, remaining=0)
        gh = self.client(fake)
        with self.assertRaisesRegex(m.ScopeError, 'does not support `gh project field-create`'):
            self.run_quiet(gh.command, ['project', 'field-create', '7', '--owner', 'acme', '--name', 'X'])
        with self.assertRaisesRegex(m.ScopeError, 'unsupported argument --number'):
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


class FieldCreationTests(unittest.TestCase):
    def test_single_select_creation_and_fresh_field_discovery(self):
        class Gh:
            def __init__(self): self.calls = []; self.fields = []
            def api(self, endpoint, method='GET', payload=None, pages=False):
                self.calls.append((endpoint, method, payload))
                if method == 'POST':
                    self.fields.append({'id': 1, 'node_id': 'F', 'name': payload['name'],
                                        'data_type': payload['data_type'], 'options': []})
                    return self.fields[-1]
                return self.fields
        gh = Gh(); rest = m.ProjectRest(gh, CFG)
        self.assertEqual(rest.run(['project', 'field-list'])['fields'], [])
        rest.run(['project', 'field-create', '7', '--name', 'Decision', '--data-type', 'SINGLE_SELECT',
                  '--single-select-options', 'None,Waiting,Needs review,Applied'])
        self.assertEqual(rest.run(['project', 'field-list'])['fields'][0]['name'], 'Decision')
        body = next(call[2] for call in gh.calls if call[1] == 'POST')
        self.assertEqual([option['name'] for option in body['single_select_options']],
                         ['None', 'Waiting', 'Needs review', 'Applied'])
