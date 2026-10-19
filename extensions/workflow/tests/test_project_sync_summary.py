"""PJ4: project_sync.py (one stdlib script, replacing the bash and PowerShell twins).

The --summary/--json contract the twins had is kept: under --summary stdout is exactly one line,
`ok issue=<n> status=<status> created=<n> closed=<n>`, `skipped reason=<why>` (a skip is never `ok`)
or `error exit=<rc> reason=<message>`; the run log goes to stderr. Behaviour tests run the script
in-process inside a real temporary git repository with `gh` replaced by FakeGh, so nothing reaches
GitHub: create, advance, no-regress, --force, sub-issue create and close, in-review on an open PR,
dry run, and the GraphQL-to-REST fallback.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
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

    def __init__(self, budget='5000', open_pr=False):
        self.budget, self.open_pr, self.calls, self.next_issue = budget, open_pr, [], 42

    def __call__(self, args, stdin=None):
        self.calls.append(list(args))
        head = args[:2]
        if head == ['auth', 'status']:
            return 0, "Logged in to github.com as fixture\nToken scopes: 'project', 'repo'"
        if head == ['api', 'graphql']:
            return (0, self.budget) if any('rateLimit' in arg for arg in args) else (0, '{}')
        if head == ['issue', 'create']:
            return 0, 'https://github.com/acme/app/issues/' + str(self.new_issue())
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


if __name__ == '__main__':
    unittest.main()
