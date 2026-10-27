"""PJ4: project_sync.py (one stdlib script, replacing the bash and PowerShell twins), and PM5's project_init.py
(likewise, with the init twins left as one-release stubs).

The --summary/--json contract the twins had is kept: under --summary stdout is exactly one line,
`ok issue=<n> status=<status> created=<n> closed=<n>`, `skipped reason=<why>` (a skip is never `ok`)
or `error exit=<rc> reason=<message>`; the run log goes to stderr. Behaviour tests run the script
in-process inside a real temporary git repository with `gh` replaced by FakeGh, so nothing reaches
GitHub: create, advance, no-regress, --force, sub-issue create and close, in-review on an open PR,
dry run, and the GraphQL-to-REST fallback. Round 4: malformed state refuses (P1), existing task issues
are adopted, never duplicated (P1), managed mode skips the node lookup and labels are made once (PM16),
remotes go through the shared `sanduq_remote` (D4), and init detects org owners and keeps the
sub-issue, parent and state settings on a rerun (PM12).
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'project/scripts/project_sync.py'
sys.path.insert(0, str(SCRIPT.parent))
import project_sync  # noqa: E402

STATUSES = ['Backlog', 'Analysis', 'Ready', 'In progress', 'In review', 'Done']
PHASES = {'open': 'Backlog', 'analysis': 'Analysis', 'ready': 'Ready', 'in-progress': 'In progress',
          'in-review': 'In review', 'done': 'Done'}
CONFIG = {
    'projectNumber': 1, 'projectId': 'PVT_1', 'owner': 'acme', 'ownerType': 'org', 'statusFieldId': 'F1',
    'stateFile': '.specify/project-sync-state.json', 'statusOrder': STATUSES,
    'statusOptions': {name: 'OPT_' + str(i) for i, name in enumerate(STATUSES)}, 'phaseToStatus': PHASES,
    'subIssues': {'enabled': False, 'maxCount': 0, 'warnAboveCount': 0, 'labels': ['spec-task'],
                  'titleTemplate': '{slug} {taskId}: {desc}'},
    'parentIssue': {'labels': ['spec-feature'], 'titleTemplate': '[{slug}] {title}'},
}


class FakeGh:
    """`gh` for one run: GraphQL-backed subcommands, or the REST paths once the budget is 0."""

    def __init__(self, budget='5000', open_pr=False, scopes="'project', 'repo'", listed=(), fail_create_after=None,
                 fail_link=False, parents=None):
        self.budget, self.open_pr, self.calls, self.next_issue, self.scopes = budget, open_pr, [], 42, scopes
        self.listed, self.fail_create_after = list(listed), fail_create_after  # task issues already on GitHub
        self.fail_link, self.parents = fail_link, dict(parents or {})  # addSubIssue refused; {issue: parent}

    def __call__(self, args, stdin=None):
        self.calls.append(list(args))
        head = args[:2]
        if head == ['auth', 'status']:
            return 0, "Logged in to github.com as fixture\nToken scopes: " + self.scopes
        if head == ['api', 'graphql']:
            if self.fail_link and 'GraphQL-Features: sub_issues' in args:
                return 1, 'GraphQL: Issue may not contain duplicate sub-issues'
            return (0, self.budget) if any('rateLimit' in arg for arg in args) else (0, '{}')
        if head[0] == 'api' and head[1].endswith('/parent'):
            number = int(head[1].split('/')[-2])
            return (0, json.dumps({'number': self.parents[number]})) if number in self.parents else (1, 'Not Found (HTTP 404)')
        if self.budget == '0' and args[0] != 'api':  # GraphQL-backed gh subcommands fail once exhausted
            return 1, 'GraphQL: API rate limit exceeded for user ID 1.'
        if head == ['issue', 'create']:
            if self.fail_create_after is not None and len(self.used('issue', 'create')) > self.fail_create_after:
                raise RuntimeError('timeout: gh issue create gave no answer in 120 s')  # an interrupted run
            return 0, 'https://github.com/acme/app/issues/' + str(self.new_issue())
        if head == ['issue', 'list'] and '--search' not in args:
            return 0, json.dumps(self.listed)
        answers = {('issue', 'list'): '[]', ('label', 'create'): '', ('issue', 'close'): '',
                   ('project', 'item-add'): '{"id":"ITEM_1"}', ('project', 'item-edit'): '',
                   ('pr', 'list'): '[{"number":7}]' if self.open_pr else '[]'}
        if tuple(head) in answers:
            return 0, answers[tuple(head)]
        if head == ['issue', 'view']:
            return 0, json.dumps({'id': 'NODE_' + args[2]})
        if args[0] == 'api':
            return 0, json.dumps(self.rest(args[1], args[args.index('--method') + 1] if '--method' in args else 'GET'))
        return 1, 'unexpected gh call'

    def new_issue(self):
        self.next_issue += 1
        return self.next_issue - 1

    def rest(self, path, method):
        base = 'orgs/acme/projectsV2/1/'
        if path.startswith('repos/acme/app/issues?'):
            return [[]]
        if path == 'repos/acme/app/issues' and method == 'POST':
            return {'html_url': 'https://github.com/acme/app/issues/' + str(self.new_issue())}
        if path.startswith('repos/acme/app/issues/') and method == 'GET':
            number = path.rsplit('/', 1)[1]
            return {'node_id': 'NODE_' + number, 'id': int(number) * 100}
        if path == base + 'items' and method == 'POST':
            return {'node_id': 'ITEM_1'}
        if path.startswith(base + 'items?'):
            return [[{'id': 11, 'node_id': 'ITEM_1'}]]
        if path.startswith(base + 'fields?'):
            return [[{'id': 5, 'node_id': 'F1'}]]
        return {}

    def used(self, *prefix):
        return [call for call in self.calls if call[:len(prefix)] == list(prefix)]


class ProjectSyncTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        self.root = Path(tmp.name).resolve()
        for args in (['init', '-q', '-b', '001-refunds'], ['remote', 'add', 'origin', 'https://github.com/acme/app.git'],
                     ['-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q', '--allow-empty', '-m', 'init']):
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        os.chdir(self.root)

    def configure(self, **changes):
        config = json.loads(json.dumps(CONFIG))
        for key, value in changes.items():
            config[key] = value
        path = self.root / '.specify/extensions/project/config.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config), encoding='utf-8')

    def state(self, value=None):
        path = self.root / '.specify/project-sync-state.json'
        if value is not None:
            path.write_text(json.dumps(value), encoding='utf-8')
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None

    def tasks(self, text):
        path = self.root / 'specs/001-refunds/tasks.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def sync(self, *args, gh=None):
        gh = gh or FakeGh()
        out, err = io.StringIO(), io.StringIO()
        with patch.object(project_sync, 'gh_raw', gh), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = project_sync.main(list(args))
        return code, out.getvalue().splitlines(), err.getvalue(), gh

    # -- the --summary/--json contract ------------------------------------

    def test_cli_rejects_summary_with_json_and_skips_without_config(self):
        run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), *a], cwd=self.root, text=True, capture_output=True)
        both = run('--phase', 'open', '--summary', '--json')
        self.assertEqual((both.returncode, both.stdout.strip()), (2, 'error exit=2 reason=--summary and --json cannot be combined'))
        skip = run('--phase', 'open', '--summary', '--bogus-flag')
        self.assertEqual(skip.returncode, 0, skip.stderr)
        self.assertEqual(len(skip.stdout.splitlines()), 1, skip.stdout)
        self.assertRegex(skip.stdout.strip(), r'^skipped reason=not configured')
        self.assertIn('unknown arg: --bogus-flag', skip.stderr)

    def test_missing_scope_is_a_skip_and_json_reports_it(self):
        self.configure()
        code, out, _, _ = self.sync('--phase', 'open', '--json', gh=lambda args, stdin=None: (0, 'Logged in'))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out[-1])['skipped'], True)
        self.assertIn("lacks 'project' scope", json.loads(out[-1])['reason'])

    def test_open_creates_the_parent_and_prints_one_ok_line(self):
        self.configure()
        code, out, err, gh = self.sync('--phase', 'open', '--summary')
        self.assertEqual((code, out), (0, ['ok issue=42 status=Backlog created=0 closed=0']), err)
        self.assertIn('[project]', err)
        self.assertEqual(self.state()['001-refunds']['itemId'], 'ITEM_1')
        self.assertEqual(gh.used('project', 'item-edit')[0][-1], 'OPT_0')
        self.assertFalse([c for c in gh.calls if any('rateLimit' in arg for arg in c)])  # no probe on the happy path
        code, out, _, _ = self.sync('--phase', 'open', '--json')
        payload = json.loads(out[-1])
        self.assertEqual((payload['issue'], payload['status'], payload['transport']), (42, 'Backlog', 'graphql'))

    def test_mid_run_failures_are_one_error_line(self):
        (self.root / '.specify/extensions/project').mkdir(parents=True)
        (self.root / '.specify/extensions/project/config.json').write_text('not json{', encoding='utf-8')
        code, out, _, _ = self.sync('--phase', 'open', '--summary')
        self.assertEqual(code, 1)
        self.assertEqual(len(out), 1)
        self.assertRegex(out[0], r'^error exit=1 reason=.+')
        self.configure()
        (self.root / '.specify/workflow.yml').write_text('schema: 1\n', encoding='utf-8')
        code, out, _, _ = self.sync('--phase', 'open', '--summary')
        self.assertEqual((code, out), (1, ['error exit=1 reason=Managed workflow requires scope-source.json']))

    # -- board behaviour ---------------------------------------------------

    def test_no_regress_unless_forced_and_dry_run_mutates_nothing(self):
        self.configure()
        self.state({'001-refunds': {'issue': 42, 'issueNodeId': 'NODE_42', 'itemId': 'ITEM_1', 'status': 'Done', 'subIssues': {}}})
        code, out, _, gh = self.sync('--phase', 'open', '--summary')
        self.assertEqual(out, ['ok issue=42 status=Done created=0 closed=0'])
        self.assertFalse(gh.used('project', 'item-edit'))
        _, out, err, gh = self.sync('--phase', 'open', '--summary', '--force', '--dry-run')
        self.assertIn('DRYRUN gh project item-edit', err)
        self.assertFalse(gh.used('project', 'item-edit'))
        self.assertEqual(self.state()['001-refunds']['status'], 'Done')
        _, out, _, _ = self.sync('--phase', 'open', '--summary', '--force')
        self.assertEqual(out, ['ok issue=42 status=Backlog created=0 closed=0'])

    def test_ready_creates_sub_issues_and_in_progress_closes_checked_ones(self):
        self.configure(subIssues={**CONFIG['subIssues'], 'enabled': True})
        self.tasks('- [ ] T001 [P] Add refund model\n- [ ] **T002** Wire the API\n')
        _, out, _, gh = self.sync('--phase', 'ready', '--summary')
        self.assertEqual(out, ['ok issue=42 status=Ready created=2 closed=0'])
        self.assertEqual(len(gh.used('api', 'graphql', '-H')), 2)
        self.assertEqual(sorted(self.state()['001-refunds']['subIssues']), ['T001', 'T002'])
        _, out, _, _ = self.sync('--phase', 'ready', '--summary', '--no-sub-issues')
        self.assertEqual(out, ['ok issue=42 status=Ready created=0 closed=0'])
        self.tasks('- [x] T001 Add refund model\n- [ ] T002 Wire the API\n')
        _, out, _, gh = self.sync('--phase', 'in-progress', '--summary')
        self.assertEqual(out, ['ok issue=42 status=In progress created=0 closed=1'])
        self.assertEqual(gh.used('issue', 'close')[0][2], '43')

    def test_an_open_pr_advances_in_progress_to_in_review(self):
        self.configure()
        _, out, _, _ = self.sync('--phase', 'in-progress', '--summary', gh=FakeGh(open_pr=True))
        self.assertEqual(out, ['ok issue=42 status=In review created=0 closed=0'])

    def test_exhausted_graphql_falls_back_to_rest(self):
        self.configure()
        code, out, err, gh = self.sync('--phase', 'open', '--json', gh=FakeGh(budget='0'))
        self.assertEqual(code, 0, err)
        payload = json.loads(out[-1])
        self.assertEqual((payload['issue'], payload['status'], payload['transport']), (42, 'Backlog', 'rest'))
        self.assertFalse(gh.used('issue', 'create') or gh.used('project'))
        self.assertTrue([c for c in gh.calls if c[:2] == ['api', 'orgs/acme/projectsV2/1/items/11']])


    # -- remotes, scopes, timeouts (PM4) -----------------------------------

    REMOTES = {'https://github.com/acme/my.app.git': 'acme/my.app', 'git@github.com:acme/my.app.git': 'acme/my.app',
               'ssh://git@github.com:443/acme/app.git': 'acme/app', 'ssh://git@github.com:22/acme/app': 'acme/app',
               'https://x-access-token:T@GitHub.com/Acme/App/': 'Acme/App', 'git@GITHUB.COM:Acme/App.GIT': 'Acme/App',
               'https://github.com@evil.com/acme/app': None, 'https://gitlab.com/acme/app': None, '/srv/git/app.git': None}

    def test_remotes_go_through_the_shared_rule_and_never_load_workflow_py(self):
        import sanduq_remote
        self.assertIs(project_sync.sanduq_remote, sanduq_remote)
        for remote, repo in {**self.REMOTES, 'https://evil.example/github.com/acme/app': None, '': None}.items():
            self.assertEqual(project_sync.github_repo(remote), repo, remote)
        installed = self.root / '.specify/extensions/workflow/scripts/workflow.py'  # D4: its load cost 0.3 s per sync
        installed.parent.mkdir(parents=True)
        installed.write_text('raise SystemExit("workflow.py loaded")\n', encoding='utf-8')
        self.configure()
        code, out, err, _ = self.sync('--phase', 'open', '--summary')
        self.assertEqual((code, out), (0, ['ok issue=42 status=Backlog created=0 closed=0']), err)

    def test_a_dotted_repository_syncs(self):
        self.configure()
        subprocess.run(['git', 'remote', 'set-url', 'origin', 'git@github.com:acme/my.app.git'], cwd=self.root, check=True)
        code, out, err, gh = self.sync('--phase', 'open', '--json')
        self.assertEqual((code, json.loads(out[-1])['repo']), (0, 'acme/my.app'), err)
        self.assertEqual(gh.used('issue', 'list')[0][3], 'acme/my.app')

    def test_a_managed_binding_that_differs_only_in_case_is_the_same_repository(self):
        self.configure()
        (self.root / '.specify/workflow.yml').write_text('schema: 1\n', encoding='utf-8')
        (self.root / 'specs/001-refunds').mkdir(parents=True)
        (self.root / 'specs/001-refunds/scope-source.json').write_text('{"repo": "Acme/App", "issue": 42}', encoding='utf-8')
        code, out, err, _ = self.sync('--phase', 'open', '--summary')
        self.assertEqual((code, out), (0, ['ok issue=42 status=Backlog created=0 closed=0']), err)

    # -- state integrity and task identities (P1) ---------------------------

    def test_a_malformed_state_file_stops_the_run_and_is_kept(self):
        self.configure()
        path = self.root / '.specify/project-sync-state.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        for text in ('{"001-refunds": {"issue": 42,', '[]', '{"001-refunds": "broken"}'):
            path.write_text(text, encoding='utf-8')
            code, out, _, gh = self.sync('--phase', 'open', '--summary')
            self.assertEqual(code, 1, text)
            self.assertRegex(out[0], r'^error exit=1 reason=.*project-sync-state\.json .*restore it from git', text)
            self.assertEqual(path.read_text(encoding='utf-8'), text)
            self.assertFalse(gh.used('issue', 'create') or gh.used('project'))

    def test_existing_task_issues_are_adopted_not_created_again(self):
        self.configure(subIssues={**CONFIG['subIssues'], 'enabled': True})
        self.tasks('- [ ] T001 Add refund model\n- [ ] T002 Wire the API\n')
        self.state({'001-refunds': {'issue': 42, 'issueNodeId': 'NODE_42', 'itemId': 'ITEM_1', 'status': '', 'subIssues': {}}})
        listed = [{'number': 50, 'title': '001-refunds T001: Add the refund model (renamed)', 'id': 'NODE_50'},
                  {'number': 51, 'title': '002-other T002: Wire the API', 'id': 'NODE_51'}]
        _, out, err, gh = self.sync('--phase', 'ready', '--summary', gh=FakeGh(listed=listed))
        self.assertEqual(out, ['ok issue=42 status=Ready created=1 closed=0'], err)
        self.assertEqual(len(gh.used('issue', 'create')), 1)
        subs = self.state()['001-refunds']['subIssues']
        self.assertEqual((subs['T001']['number'], subs['T002']['number']), (50, 42))
        self.assertEqual(len(gh.used('api', 'graphql', '-H')), 2)  # the adopted issue is linked too

    def test_a_matching_issue_whose_link_fails_is_adopted_only_when_it_is_already_this_features_child(self):
        self.configure(subIssues={**CONFIG['subIssues'], 'enabled': True})
        self.tasks('- [ ] T001 Add refund model\n')
        listed = [{'number': 50, 'title': '001-refunds T001: Add refund model', 'id': 'NODE_50'}]
        for parents, adopted in (({50: 7}, False), ({}, False), ({50: 42}, True)):
            self.state({'001-refunds': {'issue': 42, 'issueNodeId': 'NODE_42', 'itemId': 'ITEM_1', 'status': '', 'subIssues': {}}})
            _, _, err, gh = self.sync('--phase', 'ready', '--summary', gh=FakeGh(listed=listed, fail_link=True, parents=parents))
            subs = self.state()['001-refunds']['subIssues']
            self.assertEqual('T001' in subs, adopted, parents)
            self.assertFalse(gh.used('issue', 'create'), parents)  # never recreated either
            if not adopted:
                self.assertIn('not linked to #42', err)

    def test_a_run_interrupted_after_one_create_resumes_without_duplicates(self):
        self.configure(subIssues={**CONFIG['subIssues'], 'enabled': True})
        self.tasks('- [ ] T001 Add refund model\n- [ ] T002 Wire the API\n')
        code, out, _, _ = self.sync('--phase', 'ready', '--summary', gh=FakeGh(fail_create_after=2))  # the parent, T001, then T002 fails
        self.assertEqual(code, 1)
        self.assertEqual(sorted(self.state()['001-refunds']['subIssues']), ['T001'])  # saved before the failure
        _, out, _, gh = self.sync('--phase', 'ready', '--summary')
        self.assertEqual(out, ['ok issue=42 status=Ready created=1 closed=0'])
        self.assertEqual([c[c.index('--title') + 1] for c in gh.used('issue', 'create')], ['001-refunds T002: Wire the API'])

    def test_a_failed_task_issue_lookup_creates_nothing(self):
        self.configure(subIssues={**CONFIG['subIssues'], 'enabled': True})
        self.tasks('- [ ] T001 Add refund model\n')
        self.state({'001-refunds': {'issue': 42, 'issueNodeId': 'NODE_42', 'itemId': 'ITEM_1', 'status': '', 'subIssues': {}}})
        gh = FakeGh()
        real = gh.__call__
        gh_fail = lambda args, stdin=None: (1, 'HTTP 502') if args[:2] == ['issue', 'list'] else real(args, stdin)
        gh_fail.used = gh.used
        code, out, _, _ = self.sync('--phase', 'ready', '--summary', gh=gh_fail)
        self.assertEqual(code, 1, out)
        self.assertFalse(gh.used('issue', 'create'))

    # -- fewer gh calls (PM16) ---------------------------------------------

    def test_managed_syncs_skip_the_issue_node_lookup(self):
        self.configure()
        (self.root / '.specify/workflow.yml').write_text('schema: 1\n', encoding='utf-8')
        (self.root / 'specs/001-refunds').mkdir(parents=True)
        (self.root / 'specs/001-refunds/scope-source.json').write_text('{"repo": "acme/app", "issue": 42}', encoding='utf-8')
        self.state({'001-refunds': {'issue': 42, 'issueNodeId': 'NODE_SCOPE', 'itemId': '', 'status': '', 'subIssues': {}}})
        for phase in ('open', 'analysis', 'in-progress'):
            _, out, err, gh = self.sync('--phase', phase, '--summary')
            self.assertTrue(out[0].startswith('ok issue=42'), err)
            self.assertFalse(gh.used('issue', 'view'), phase)
        self.assertEqual(self.state()['001-refunds']['issueNodeId'], 'NODE_SCOPE')  # the binding fingerprint is stable

    def test_each_label_is_created_once_per_run(self):
        self.configure(subIssues={**CONFIG['subIssues'], 'enabled': True, 'labels': ['spec-task', 'refunds']})
        self.tasks(''.join('- [ ] T%03d Task %d\n' % (n, n) for n in range(1, 11)))
        _, out, _, gh = self.sync('--phase', 'ready', '--summary')
        self.assertEqual(out, ['ok issue=42 status=Ready created=10 closed=0'])
        made = sorted(call[2] for call in gh.used('label', 'create'))
        self.assertEqual(made, ['refunds', 'spec-feature', 'spec-task'])

    def test_a_read_project_only_token_is_a_skip(self):
        self.configure()
        code, out, _, gh = self.sync('--phase', 'open', '--summary', gh=FakeGh(scopes="'read:project', 'repo'"))
        self.assertEqual(code, 0)
        self.assertRegex(out[0], r"^skipped reason=gh token lacks 'project' scope")
        self.assertEqual(gh.calls, [['auth', 'status']])

    def test_gh_calls_go_through_the_shared_transport_never_retried(self):
        """SC8: the runner, timeout, scopes and rate-limit test are sanduq_gh's; (rc, output) and 127 stay."""
        import sanduq_gh
        self.assertIs(project_sync.sanduq_gh, sanduq_gh)
        self.assertFalse(hasattr(project_sync, 'token_scopes'))
        seen = []

        def run_gh(args, **kwargs):
            seen.append(kwargs)
            answers = {'ok': ' out \n', 'missing': sanduq_gh.GhError('gh CLI not installed', returncode=127),
                       'fail': sanduq_gh.GhError('x', returncode=1, stdout='partial\n', stderr='HTTP 502\n')}
            if isinstance(answers[args[0]], Exception):
                raise answers[args[0]]
            return answers[args[0]]
        with patch.object(sanduq_gh, 'run_gh', run_gh):
            self.assertEqual(project_sync.gh_raw(['ok'], stdin='{}'), (0, 'out'))
            self.assertEqual(project_sync.gh_raw(['missing']), (127, 'gh CLI not installed'))
            self.assertEqual(project_sync.gh_raw(['fail']), (1, 'partial\nHTTP 502'))
        self.assertEqual(seen[0], {'payload': '{}', 'timeout': project_sync.TIMEOUT})
        self.assertFalse(any(kwargs.get('retry') for kwargs in seen))
        # The shared rate-limit rule: GraphQL's RATE_LIMITED type counts too.
        self.configure()
        gh = FakeGh()
        real = gh.__call__
        limited = lambda args, stdin=None: (1, 'GraphQL: RATE_LIMITED') if args[:2] == ['api', 'graphql'] or \
            args[0] != 'api' and args[:2] != ['auth', 'status'] else real(args, stdin)
        limited.used = gh.used
        code, out, err, _ = self.sync('--phase', 'open', '--json', gh=limited)
        self.assertEqual((code, json.loads(out[-1])['transport']), (0, 'rest'), err)

    def test_a_hung_gh_is_an_error_line_and_a_missing_git_a_skip(self):
        self.configure()
        real = subprocess.run

        def hung_gh(cmd, *a, **k):
            if Path(cmd[0]).stem.lower() == 'gh':  # gh runs by its absolute PATH entry (stream E, SEC-15)
                self.assertEqual(k.get('timeout'), project_sync.TIMEOUT)
                raise subprocess.TimeoutExpired(cmd, k['timeout'])
            return real(cmd, *a, **k)
        out = io.StringIO()
        with patch.object(project_sync.subprocess, 'run', hung_gh), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(project_sync.main(['--phase', 'open', '--summary']), 1)
        self.assertEqual(out.getvalue().splitlines(), ['error exit=1 reason=timeout: gh auth status gave no answer in 120 s'])
        out = io.StringIO()
        with patch.object(project_sync.subprocess, 'run', side_effect=FileNotFoundError('git')), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(project_sync.main(['--phase', 'open', '--summary']), 0)
        self.assertEqual(out.getvalue().splitlines(), ['skipped reason=not a git repo'])


FAKE_GH = """import json, re, sys
args = sys.argv[1:]
COLUMNS = COLUMNS or ['Backlog', 'Analysis', 'Engineer-Review', 'Ready', 'In progress', 'In review', 'Done']
import os
def log(*entry): open('edits.json', 'a').write(json.dumps(entry) + '\\n')
def unarchived(): return json.load(open('unarchived.json')) if os.path.exists('unarchived.json') else []
if args[:2] == ['api', 'graphql'] and 'updateProjectV2Field' in args[-1]:
    # updateProjectV2Field replaces every option, so every option comes back with a new id.
    names = [json.loads('"' + n + '"') for n in re.findall(r'name:"((?:[^"\\\\]|\\\\.)*)"', args[-1])]
    open('mutation.json', 'w').write(json.dumps(names))
    print(json.dumps({'data': {'updateProjectV2Field': {'projectV2Field': {
        'options': [{'id': 'N%d' % i, 'name': n} for i, n in enumerate(names)]}}}}))
elif args[:2] == ['api', 'graphql'] and 'archivedStates:[ARCHIVED,NOT_ARCHIVED]' in args[-1]:
    # Every item, archived ones too, two per page (`gh project item-list` would leave archived ones out).
    if ITEMS is None: raise SystemExit('HTTP 403: Resource not accessible by integration')
    if os.path.exists('mutation.json'): raise SystemExit('items read after the column update')
    start = int((re.search(r'after:"(\\d+)"', args[-1]) or [0, 0])[1])
    page = [{'id': i['id'], 'isArchived': i.get('archived', False),
             'fieldValueByName': {'name': i['status']} if i.get('status') else None} for i in ITEMS[start:start + 2]]
    more = start + 2 < len(ITEMS)
    print(json.dumps({'data': {'node': {'items': {'pageInfo': {'hasNextPage': more, 'endCursor': str(start + 2) if more else None},
                                                  'nodes': page}}}}))
elif args[:2] == ['api', 'graphql'] and 'archiveProjectV2Item' in args[-1]:
    item = re.search(r'itemId:"([^"]+)"', args[-1])[1]
    undo = 'unarchiveProjectV2Item' in args[-1]
    json.dump(unarchived() + [item] if undo else [i for i in unarchived() if i != item], open('unarchived.json', 'w'))
    log('unarchive' if undo else 'archive', item)
    print('{}')
elif args[:2] == ['project', 'item-edit']:
    item = args[args.index('--id') + 1]
    if item in FAIL_EDIT: raise SystemExit('edit refused')
    if any(i['id'] == item and i.get('archived') for i in ITEMS) and item not in unarchived():
        raise SystemExit('GraphQL: The item is archived and cannot be updated (updateProjectV2ItemFieldValue)')
    log('edit', item, args[args.index('--single-select-option-id') + 1])
elif args[:2] == ['auth', 'status']: print("Logged in to github.com\\n  - Token scopes: " + SCOPES)
elif args[:2] == ['api', 'user']: print('acme')
elif args[:2] == ['api', 'users/acme']:
    if KIND is None: raise SystemExit('HTTP 404: Not Found')
    print(KIND)
elif args[:2] == ['repo', 'view']: print(json.dumps({'owner': {'login': 'acme'}, 'name': 'app'}))
elif args[:2] == ['api', 'graphql'] and 'projectsV2' in args[-1]:
    print(json.dumps({'data': {'repository': {'projectsV2': {'nodes': LINKED}}}}))
elif args[:2] == ['project', 'list']: print(json.dumps({'projects': [{'number': 1, 'title': 'Alpha'}, {'number': 3, 'title': 'Beta'}]}))
elif args[:2] == ['project', 'view']: print(json.dumps({'id': 'PVT_1', 'url': 'https://github.com/orgs/acme/projects/1'}))
elif args[:2] == ['project', 'field-list']:
    print(json.dumps({'fields': [{'id': 'F1', 'name': 'Status', 'options': [{'id': 'O%d' % i, 'name': n} for i, n in enumerate(COLUMNS)]}]}))
else: raise SystemExit('unexpected gh ' + ' '.join(args))
"""
HOOKS = """hooks:
  after_tasks:
  - extension: project
    command: speckit.project.sync
    enabled: true
    optional: true
"""


def fake_gh(bindir, source):
    """Puts a `gh` that runs `source` with this interpreter first on PATH. On Windows, where a subprocess finds
    only .exe files, it is pip's console-script launcher with the script appended as a zip."""
    bindir.mkdir(exist_ok=True)
    if os.name != 'nt':
        (bindir / 'gh').write_text('#!' + sys.executable + '\n' + source, encoding='utf-8', newline='\n')
        (bindir / 'gh').chmod(0o755)
        return
    pip = importlib.util.find_spec('pip')
    launcher = pip and Path(pip.origin).parent / '_vendor/distlib/t64.exe'
    if not launcher or not launcher.is_file():
        raise unittest.SkipTest("no pip launcher to build a fake gh.exe from")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('__main__.py', source)
    (bindir / 'gh.exe').write_bytes(launcher.read_bytes() + b'#!"' + sys.executable.encode() + b'"\r\n' + archive.getvalue())


class ProjectInitTests(unittest.TestCase):
    """PM4/PM5: project_init.py (and the one-release shell stubs) need the whole 'project' scope, name the
    choice they cannot make, and keep every board and config guard the shell twins had. `gh` is a fake on PATH."""

    def init(self, *flags, scopes="'project', 'repo'", kind='User', existing=None, columns=None, managed=None,
             dry_run=True, items=(), fail_edit=(), shell='python', hooks=HOOKS, hang=(), linked=()):
        """(exit code, output) of one init run; `existing` is a config.json, `managed` the `workflow.py
        project-defaults` answer of a Workflow-managed project, `shell` python or a stub (bash, pwsh)."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        self.root = root
        subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
        (root / '.specify/extensions/project').mkdir(parents=True)
        (root / '.specify/extensions.yml').write_bytes(hooks.encode('utf-8'))
        if existing is not None:
            (root / '.specify/extensions/project/config.json').write_text(json.dumps(existing), encoding='utf-8')
        if managed is not None:
            (root / '.specify/workflow.yml').write_text('schema_version: 1\n', encoding='utf-8')
            stub = root / '.specify/extensions/workflow/scripts/workflow.py'
            stub.parent.mkdir(parents=True)
            stub.write_text('print(' + repr(json.dumps(managed)) + ')\n', encoding='utf-8')
        fake_gh(root / 'bin', 'SCOPES = ' + repr(scopes) + '\nKIND = ' + repr(kind) + '\nCOLUMNS = ' + repr(columns)
                + '\nITEMS = ' + repr(None if items is None else list(items)) + '\nFAIL_EDIT = ' + repr(list(fail_edit))
                + '\nLINKED = ' + repr(list(linked))
                + '\n' + FAKE_GH)
        # The stubs run `python` from PATH: this interpreter's folder comes right after the fake gh.
        env = dict(os.environ, PATH=os.pathsep.join([str(root / 'bin'), str(Path(sys.executable).parent),
                                                     os.environ.get('PATH', '')]))
        scripts = ROOT / 'project/scripts'
        flags = [*flags, *(['--dry-run'] if dry_run else [])]
        if shell == 'python':
            args = [sys.executable, str(scripts / 'project_init.py'), *flags]
        elif shell == 'bash':
            args = [shutil.which('bash'), (scripts / 'bash/project-init.sh').as_posix(), *flags]
        else:
            args = ['pwsh', '-NoProfile', '-File', str(scripts / 'powershell/project-init.ps1'), *flags]
        if hang:  # in process, so `gh project item-edit` on these items can time out without waiting 120 s
            import project_init
            real = project_sync.gh_raw

            def hung(args, stdin=None):
                if args[:2] == ['project', 'item-edit'] and args[3] in hang:
                    raise RuntimeError('timeout: gh project item-edit gave no answer in 120 s')
                return real(args, stdin)
            out, cwd = io.StringIO(), os.getcwd()
            self.addCleanup(os.chdir, cwd)
            os.chdir(root)
            # sanduq_gh resolves gh from PATH once at import (stream E, SEC-15), so point it at the fake too.
            fake = root / 'bin' / ('gh.exe' if os.name == 'nt' else 'gh')
            with patch.dict(os.environ, {'PATH': env['PATH']}), patch.object(project_sync, 'gh_raw', hung), \
                    patch.object(project_sync.sanduq_gh, 'GH', str(fake)), contextlib.redirect_stdout(out):
                code = project_init.main(flags)
            return code, out.getvalue()
        done = subprocess.run(args, cwd=root, env=env, input='', capture_output=True, text=True, encoding='utf-8', timeout=120)
        return done.returncode, done.stdout + done.stderr

    def stubs(self):
        # Windows' System32 bash.exe is the WSL launcher, not a POSIX shell the stub can run in.
        posix_bash = shutil.which('bash') and 'system32' not in shutil.which('bash').lower()
        return [shell for shell in ('bash', 'pwsh') if (posix_bash if shell == 'bash' else shutil.which(shell))]

    def test_read_project_alone_is_refused_with_the_refresh_command(self):
        code, output = self.init(scopes="'read:project', 'repo'")
        self.assertEqual(code, 1, output)
        self.assertIn("lacks 'project' scope - run: gh auth refresh", output)

    def test_several_projects_are_a_missing_choice_with_the_flag_to_pass(self):
        code, output = self.init()
        self.assertEqual(code, 4, output)
        self.assertIn('#1 Alpha, #3 Beta', output)
        self.assertIn('rerun with --number', output)
        needs = json.loads(output.strip().splitlines()[-1])
        self.assertEqual(needs, {'ok': False, 'needs': [{'flag': '--number', 'why': 'several projects for acme',
                                                         'options': [{'number': 1, 'title': 'Alpha'},
                                                                     {'number': 3, 'title': 'Beta'}]}]})
        self.assertFalse((self.root / '.specify/extensions/project/config.json').exists())

    def test_the_one_board_linked_to_the_repository_needs_no_number(self):
        beta = {'number': 3, 'title': 'Beta', 'owner': {'login': 'acme'}}
        code, output = self.init('--json', linked=[beta])
        self.assertEqual(code, 0, output)
        self.assertIn('board linked to the repository: #3 Beta', output)
        self.assertEqual(self.config(output)['projectNumber'], 3)
        # Another owner's board, or two linked boards, fall back to the owner's list and its choice.
        code, output = self.init('--json', linked=[{**beta, 'owner': {'login': 'other'}}])
        self.assertEqual(code, 4, output)
        code, output = self.init('--json', linked=[beta, {'number': 1, 'title': 'Alpha', 'owner': {'login': 'acme'}}])
        self.assertEqual(code, 4, output)

    def test_an_unreadable_owner_type_is_a_missing_choice(self):
        code, output = self.init('--number', '1', kind=None)
        self.assertEqual(code, 4, output)
        self.assertEqual(json.loads(output.strip().splitlines()[-1])['needs'][0]['flag'], '--owner-type')
        code, output = self.init('--number', '1', '--owner-type', 'org', '--json', kind=None)
        self.assertEqual((code, self.config(output)['ownerType']), (0, 'org'), output)

    PICK = ('--number', '1', '--json')

    def config(self, output):
        return json.loads([line for line in output.splitlines() if line.startswith('{"owner"')][-1])

    def test_an_organization_owner_is_recorded_as_org(self):
        for kind, expected in (('Organization', 'org'), ('User', 'user')):
            code, output = self.init(*self.PICK, kind=kind)
            self.assertEqual(code, 0, output)
            self.assertEqual(self.config(output)['ownerType'], expected, kind)

    def test_a_rerun_keeps_the_sub_issue_parent_and_state_settings(self):
        custom = {'owner': 'acme', 'hookMode': 'required',
                  'subIssues': {'enabled': False, 'labels': ['my-task'], 'maxCount': 5, 'titleTemplate': '{taskId} {desc}'},
                  'parentIssue': {'labels': ['epic'], 'titleTemplate': '{title}'}, 'stateFile': '.specify/board.json'}
        defaults = json.loads((ROOT / 'project/config.default.json').read_text(encoding='utf-8'))
        code, output = self.init(*self.PICK, existing=custom)
        self.assertEqual(code, 0, output)
        written = self.config(output)
        for key in ('subIssues', 'parentIssue', 'stateFile', 'hookMode'):
            self.assertEqual(written[key], custom[key], key)
        code, output = self.init(*self.PICK)
        self.assertEqual(self.config(output)['subIssues'], defaults['subIssues'])
        self.assertEqual(self.config(output)['hookMode'], 'optional')

    def test_the_hook_mode_is_set_on_every_project_hook_keeping_line_endings(self):
        hooks = HOOKS.replace('\n', '\r\n') + '  after_plan:\r\n  - extension: other\r\n    optional: true\r\n'
        code, output = self.init(*self.PICK, '--hooks-mode', 'required', dry_run=False, hooks=hooks)
        self.assertEqual(code, 0, output)
        self.assertEqual((self.root / '.specify/extensions.yml').read_bytes().decode('utf-8'),
                         hooks.replace('optional: true\r\n  after_plan', 'optional: false\r\n  after_plan', 1))
        code, output = self.init(*self.PICK, '--hooks-mode', 'required', dry_run=False, hooks='hooks: {}\n')
        self.assertEqual(code, 1, output)
        self.assertIn('no project sync hooks', output)

    def test_both_spellings_reach_the_script_directly_and_through_the_stubs(self):
        """PM5: the shell scripts are one-release stubs; each passes either spelling through and says so."""
        bash = ('--number', '1', '--owner-type', 'org', '--hooks-mode', 'required', '--non-interactive', '--json')
        pwsh = ('-Number', '1', '-OwnerType', 'org', '-HooksMode', 'required', '-NonInteractive', '-json')
        code, output = self.init(*bash)
        self.assertEqual(code, 0, output)
        expected = self.config(output)
        self.assertEqual((expected['ownerType'], expected['hookMode']), ('org', 'required'))
        for shell in ['python', *self.stubs()]:
            for flags in (bash, pwsh):
                code, output = self.init(*flags, shell=shell)
                self.assertEqual((code, self.config(output)), (0, expected), (shell, flags, output))
                if shell != 'python':
                    self.assertIn('deprecated; run: python .specify/extensions/project/scripts/project_init.py', output)
            code, output = self.init(shell=shell)
            self.assertEqual(code, 4, (shell, output))  # the stubs pass the exit code through

    def test_managed_auto_create_makes_each_doctor_column_once_with_current_ids(self):
        """B3: GitHub's default board under a Workflow policy: one column per name, the case variant renamed,
        every id from the update's answer, and every name Workflow's doctor requires present."""
        statuses = ['Backlog', 'Feature Specification', 'Need Clarifications', 'Ready', 'In progress', 'In review', 'Done']
        phases = {'open': 'Feature Specification', 'analysis': 'Ready', 'engineer-review': 'Ready', 'ready': 'Ready',
                  'in-progress': 'In progress', 'in-review': 'In review', 'done': 'Done'}
        code, output = self.init(*self.CREATE, columns=['Todo', 'In Progress', 'Done'],
                                 managed={'phaseToStatus': phases, 'statuses': statuses}, dry_run=False)
        self.assertEqual(code, 0, output)
        sent = json.loads((self.root / 'mutation.json').read_text())
        self.assertEqual(sorted(sent), sorted(set(statuses) | {'Todo'}))
        written = json.loads((self.root / '.specify/extensions/project/config.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(written['statusOptions'], {name: 'N%d' % i for i, name in enumerate(sent)})
        self.assertEqual(written['phaseToStatus'], phases)
        self.assertEqual(written['hookMode'], 'required')
        self.assertEqual((self.root / '.specify/extensions.yml').read_text(encoding='utf-8'), HOOKS)

    STATUSES = ['Backlog', 'Feature Specification', 'Need Clarifications', 'Ready', 'In progress', 'In review', 'Done']
    MANAGED = {'phaseToStatus': {'open': 'Feature Specification', 'analysis': 'Ready', 'engineer-review': 'Ready',
                                 'ready': 'Ready', 'in-progress': 'In progress', 'in-review': 'In review',
                                 'done': 'Done'}, 'statuses': STATUSES}
    CREATE = ('--number', '1', '--json', '--auto-create-columns')
    ITEMS = [{'id': 'I1', 'status': 'In Progress'}, {'id': 'I2', 'status': 'Todo'}, {'id': 'I3'},
             {'id': 'I4', 'status': 'Done', 'archived': True}]

    def events(self):
        path = self.root / 'edits.json'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def edits(self):
        return {event[1]: event[2] for event in self.events() if event[0] == 'edit'}

    def test_a_column_change_sets_every_item_status_again_by_name(self):
        """Board guard: the option update clears every item's Status, so init restores each one by name."""
        code, output = self.init(*self.CREATE, columns=['Todo', 'In Progress', 'Done'], managed=self.MANAGED,
                                 dry_run=False, items=self.ITEMS)
        self.assertEqual(code, 0, output)
        options = json.loads((self.root / '.specify/extensions/project/config.json')
                             .read_text(encoding='utf-8-sig'))['statusOptions']
        # The renamed column keeps its items; an item without a Status is left alone; the items span two pages.
        self.assertEqual(self.edits(), {'I1': options['In progress'], 'I2': options['Todo'], 'I4': options['Done']})
        # G1: an archived item cannot be edited, so it is unarchived, set and archived again.
        self.assertEqual([e for e in self.events() if e[1] == 'I4'],
                         [['unarchive', 'I4'], ['edit', 'I4', options['Done']], ['archive', 'I4']])
        self.assertIn('restored Status on 3 of 3 item(s)', output)

    def test_a_dry_run_changes_no_column(self):
        code, output = self.init(*self.CREATE, columns=['Todo', 'In Progress', 'Done'], managed=self.MANAGED,
                                 items=self.ITEMS)
        self.assertEqual(code, 0, output)
        self.assertIn("DRYRUN rename column 'In Progress' to 'In progress'", output)
        self.assertIn("DRYRUN create column 'Backlog'", output)
        self.assertFalse((self.root / 'mutation.json').exists() or self.events())
        self.assertFalse((self.root / '.specify/extensions/project/config.json').exists())

    def test_unreadable_items_refuse_the_column_change_unless_allowed(self):
        code, output = self.init(*self.CREATE, columns=['Todo', 'In Progress', 'Done'], managed=self.MANAGED,
                                 dry_run=False, items=None)
        self.assertEqual(code, 1, output)
        self.assertIn('--allow-status-reset', output)
        self.assertFalse((self.root / 'mutation.json').exists())
        self.assertFalse((self.root / '.specify/extensions/project/config.json').exists())
        code, output = self.init(*self.CREATE, '--allow-status-reset', columns=['Todo', 'In Progress', 'Done'],
                                 managed=self.MANAGED, dry_run=False, items=None)
        self.assertEqual(code, 0, output)
        self.assertTrue((self.root / 'mutation.json').exists())

    def test_a_timed_out_item_edit_rearchives_continues_and_still_writes_the_config(self):
        """Codex 3: a timeout on one item must not abandon the rest, leave an item unarchived, or keep the old ids."""
        code, output = self.init(*self.CREATE, columns=['Todo', 'In Progress', 'Done'], managed=self.MANAGED,
                                 dry_run=False, items=self.ITEMS, hang={'I1', 'I4'})
        self.assertEqual(code, 1, output)
        options = json.loads((self.root / '.specify/extensions/project/config.json')
                             .read_text(encoding='utf-8-sig'))['statusOptions']
        self.assertEqual(self.edits(), {'I2': options['Todo']})
        self.assertEqual([e for e in self.events() if e[1] == 'I4'], [['unarchive', 'I4'], ['archive', 'I4']])
        self.assertIn("I1 was 'In Progress': timeout", output)
        self.assertIn("I4 (archived) was 'Done': timeout", output)
        self.assertIn('restored Status on 1 of 3 item(s)', output)

    def test_an_item_whose_status_cannot_be_set_again_is_reported_and_fails_the_run(self):
        code, output = self.init(*self.CREATE, columns=['Todo', 'In Progress', 'Done'], managed=self.MANAGED,
                                 dry_run=False, items=self.ITEMS, fail_edit=['I2'])
        self.assertEqual(code, 1, output)
        self.assertIn("I2 was 'Todo'", output)
        self.assertIn('I1', self.edits())
        written = json.loads((self.root / '.specify/extensions/project/config.json').read_text(encoding='utf-8-sig'))
        self.assertTrue(all(value.startswith('N') for value in written['statusOptions'].values()), written)  # current ids


class DescriptionTests(unittest.TestCase):
    """D1: each command's frontmatter description equals its manifest entry, and sync says sub-issues are standalone."""

    def test_frontmatter_and_manifest_agree(self):
        import re
        manifest = (ROOT / 'project/extension.yml').read_text(encoding='utf-8')
        for name in ('init', 'sync'):
            text = (ROOT / 'project/commands/speckit.project.{}.md'.format(name)).read_text(encoding='utf-8')
            front = re.search(r'^description: (".*")$', text, re.M).group(1)
            self.assertIn('description: ' + front, manifest, name)
            if name == 'sync':
                self.assertIn('standalone', front)
        self.assertNotIn('all sub-issues closed', (ROOT / 'project/README.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
