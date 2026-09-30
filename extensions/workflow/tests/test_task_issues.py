import contextlib
import copy
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import task_issues as t


class FakeGitHub:
    def __init__(self):
        self.issues = {10: {'number': 10, 'id': 100, 'state': 'open', 'body': 'Parent'},
                       20: {'number': 20, 'id': 200, 'state': 'open', 'body': 'Other parent'}}
        self.parents = {}
        self.writes = []
        self.lose_response = False

    def api(self, path, method='GET', payload=None, pages=False):
        if method != 'GET': self.writes.append((path, method, payload))
        parts = path.split('?')[0].split('/')
        if len(parts) == 4:
            if method == 'GET': return copy.deepcopy(list(self.issues.values()))
            n = max(self.issues) + 1
            self.issues[n] = {'number': n, 'id': n * 10, 'state': 'open', **payload}
            if self.lose_response:
                self.lose_response = False
                raise t.WorkflowError('Lost response')
            return copy.deepcopy(self.issues[n])
        n = int(parts[4])
        if len(parts) == 5:
            if method == 'PATCH': self.issues[n].update(payload)
            return copy.deepcopy(self.issues[n])
        if parts[5] == 'sub_issues':
            if method == 'GET': return [copy.deepcopy(self.issues[c]) for c, p in self.parents.items() if p == n]
            child = next(i['number'] for i in self.issues.values() if i['id'] == payload['sub_issue_id'])
            self.parents[child] = n
            return {}
        if parts[5] == 'parent':
            return {'number': self.parents[n], 'repository_url': 'https://api.github.com/repos/acme/app'}
        raise AssertionError((path, method))


class TaskIssueTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        subprocess.run(['git', 'remote', 'add', 'origin', 'git@github.com:acme/app.git'], cwd=self.root, check=True)
        self.gh = FakeGitHub()

    def feature(self, name, parent):
        folder = self.root / 'specs' / name; folder.mkdir(parents=True, exist_ok=True)
        (folder / 'scope-source.json').write_text(json.dumps({'repo': 'acme/app', 'issue': parent}))
        (folder / 'tasks.md').write_text('- [ ] T001 [P] First behavior\n- [ ] T1000 Second behavior\n')
        return 'specs/' + name

    def test_parent_feature_scoped_dedup_and_repair(self):
        a = self.feature('001-a', 10); b = self.feature('002-b', 20)
        first = t.sync(self.root, a, 10, {'T1000': ['T001']}, True, self.gh)
        second = t.sync(self.root, b, 20, {}, True, self.gh)
        self.assertNotEqual(first['tasks']['T001']['number'], second['tasks']['T001']['number'])
        child = first['tasks']['T001']['number']; del self.gh.parents[child]
        size = len(self.gh.issues)
        rerun = t.sync(self.root, a, 10, {'T1000': ['T001']}, True, self.gh)
        self.assertEqual(len(self.gh.issues), size)
        self.assertEqual(self.gh.parents[child], 10)
        self.assertTrue(rerun['native_links_verified'])

    def test_lost_create_response_recovers_without_duplicate(self):
        feature = self.feature('001-a', 10); self.gh.lose_response = True
        with self.assertRaisesRegex(t.WorkflowError, 'Lost response'): t.sync(self.root, feature, 10, {}, True, self.gh)
        result = t.sync(self.root, feature, 10, {}, True, self.gh)
        self.assertEqual(len(self.gh.issues), 4)
        self.assertTrue(result['native_links_verified'])

    def test_dry_run_never_writes(self):
        feature = self.feature('001-a', 10)
        result = t.sync(self.root, feature, 10, {}, False, self.gh)
        self.assertFalse(result['native_links_verified']); self.assertEqual(self.gh.writes, [])

    def test_dependencies_order_unknown_and_cycle(self):
        self.assertEqual(t.dependency_order({'T002': {}, 'T001': {}}, {'T002': ['T001']}), ['T001', 'T002'])
        with self.assertRaises(t.WorkflowError): t.dependency_order({'T001': {}}, {'T001': ['T404']})
        with self.assertRaises(t.WorkflowError): t.dependency_order({'T001': {}, 'T002': {}}, {'T001': ['T002'], 'T002': ['T001']})

    def test_duplicate_tasks_and_wrong_binding_rejected(self):
        with self.assertRaises(t.WorkflowError): t.parse_tasks('- [ ] T001 first\n- [ ] T001 second')
        feature = self.feature('001-a', 10)
        with self.assertRaisesRegex(t.WorkflowError, 'BINDING_MISMATCH'): t.sync(self.root, feature, 20, {}, True, self.gh)

    def test_updated_managed_body_preserves_notes(self):
        feature = self.feature('001-a', 10)
        result = t.sync(self.root, feature, 10, {}, True, self.gh)
        number = result['tasks']['T001']['number']
        self.gh.issues[number]['body'] += '\nHuman note to preserve\n'
        (self.root / feature / 'tasks.md').write_text('- [ ] T001 Revised behavior\n')
        t.sync(self.root, feature, 10, {}, True, self.gh)
        self.assertIn('Human note to preserve', self.gh.issues[number]['body'])
        self.assertIn('Revised behavior', self.gh.issues[number]['body'])

    def test_native_legacy_mapping_is_adopted_without_duplicate(self):
        feature = self.feature('001-a', 10)
        self.gh.issues[21] = {'number':21,'id':210,'state':'open','title':'T001: Old task','body':'Legacy human notes'}
        self.gh.parents[21] = 10
        t.write(self.root / '.specify/project-sync-state.json', {'001-a':{'issue':10,'subIssues':{'T001':{'number':21}}}})
        result = t.sync(self.root, feature, 10, {}, True, self.gh)
        self.assertEqual(result['tasks']['T001']['number'],21)
        self.assertIn('Legacy human notes', self.gh.issues[21]['body'])
        self.assertEqual(len(self.gh.issues),4)

    def test_unmapped_native_task_blocks_duplicate_creation(self):
        feature=self.feature('001-a',10)
        self.gh.issues[21]={'number':21,'id':210,'state':'open','title':'T001: Existing','body':'Legacy'}
        self.gh.parents[21]=10
        with self.assertRaisesRegex(t.WorkflowError,'UNMAPPED_EXISTING_TASK'):t.sync(self.root,feature,10,{},True,self.gh)
        self.assertEqual(self.gh.writes,[])

    def test_issue_title_deterministic_and_within_github_limit(self):
        self.assertEqual(t.issue_title('T001', 'Short task'), 'T001: Short task')
        long_description = 'B' * 500
        title = t.issue_title('T001', long_description)
        self.assertLessEqual(len(title), 256)
        self.assertTrue(title.endswith('...'))
        self.assertEqual(title, t.issue_title('T001', long_description))

    def test_long_task_title_is_shortened_with_full_text_kept_in_body(self):
        feature = self.feature('001-a', 10)
        long_description = 'A' * 300
        (self.root / feature / 'tasks.md').write_text('- [ ] T001 ' + long_description + '\n')
        result = t.sync(self.root, feature, 10, {}, True, self.gh)
        number = result['tasks']['T001']['number']
        issue = self.gh.issues[number]
        self.assertLessEqual(len(issue['title']), 256)
        self.assertTrue(issue['title'].startswith('T001: '))
        self.assertTrue(issue['title'].endswith('...'))
        self.assertIn(long_description, issue['body'])
        # A re-sync of the unchanged task must not create a duplicate issue,
        # relink it, or keep rewriting the (already up to date) title/body.
        writes_before = len(self.gh.writes)
        issues_before = len(self.gh.issues)
        rerun = t.sync(self.root, feature, 10, {}, True, self.gh)
        self.assertEqual(rerun['tasks']['T001']['number'], number)
        self.assertEqual(len(self.gh.issues), issues_before)
        self.assertEqual(len(self.gh.writes), writes_before)
        self.assertEqual(self.gh.issues[number]['title'], issue['title'])
        self.assertEqual(self.gh.issues[number]['body'], issue['body'])

    def test_state_sync_closes_reopens_and_preserves_mapping(self):
        feature=self.feature('001-a',10);result=t.sync(self.root,feature,10,{},True,self.gh)
        before=(self.root/feature/'workflow/task-issues.json').read_bytes()
        tasks=self.root/feature/'tasks.md';tasks.write_text('- [x] T001 First behavior\n- [ ] T1000 Second behavior\n')
        t.sync_states(self.root,feature,10,True,self.gh)
        self.assertEqual(self.gh.issues[result['tasks']['T001']['number']]['state'],'closed')
        tasks.write_text('- [ ] T001 First behavior\n- [ ] T1000 Second behavior\n')
        t.sync_states(self.root,feature,10,True,self.gh)
        self.assertEqual(self.gh.issues[result['tasks']['T001']['number']]['state'],'open')
        self.assertEqual((self.root/feature/'workflow/task-issues.json').read_bytes(),before)

    def test_sync_states_handles_a_batch_of_tasks_in_one_call(self):
        # B7: `--sync-states` must be callable once per phase for a batch of
        # tasks. sync_states() already walks every task in tasks.md on each
        # call, so completing several tasks in the same phase and syncing once
        # reports (and applies) every transition together; no new code needed.
        feature = self.feature('001-a', 10)
        result = t.sync(self.root, feature, 10, {}, True, self.gh)
        tasks = self.root / feature / 'tasks.md'
        tasks.write_text('- [x] T001 First behavior\n- [x] T1000 Second behavior\n')
        outcome = t.sync_states(self.root, feature, 10, True, self.gh)
        self.assertEqual({c['task'] for c in outcome['changes']}, {'T001', 'T1000'})
        self.assertEqual(self.gh.issues[result['tasks']['T001']['number']]['state'], 'closed')
        self.assertEqual(self.gh.issues[result['tasks']['T1000']['number']]['state'], 'closed')


class TaskIssuesSummaryTests(unittest.TestCase):
    def test_sync_summary_counts_created_and_reused(self):
        result = {'tasks': {'T001': {'action': 'create'}, 'T002': {'action': 'reuse'}, 'T003': {'action': 'reuse'}},
                  'dry_run': False}
        self.assertEqual(t.sync_summary(result), 'ok created=1 reused=2 total=3 dry_run=0')

    def test_sync_summary_reports_dry_run(self):
        result = {'tasks': {'T001': {'action': 'create'}}, 'dry_run': True}
        self.assertEqual(t.sync_summary(result), 'ok created=1 reused=0 total=1 dry_run=1')

    def test_sync_states_summary_counts_transitions(self):
        result = {'changes': [{'task': 'T001', 'to': 'closed'}, {'task': 'T002', 'to': 'open'}], 'dry_run': False}
        self.assertEqual(t.sync_states_summary(result), 'ok opened=1 closed=1 changed=2 dry_run=0')

    def test_cli_summary_error_line_without_gh(self):
        # DEPENDENCY_FILE_REQUIRED is raised before any GitHub call, so this
        # exercises --summary's error line with no gh/network dependency.
        with tempfile.TemporaryDirectory() as directory:
            argv = ['task_issues.py', '--root', directory, '--feature', 'specs/example',
                    '--parent', '1', '--summary']
            buf = io.StringIO()
            with mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(buf):
                code = t.main()
            self.assertEqual(code, 1)
            self.assertEqual(buf.getvalue().strip(), 'error DEPENDENCY_FILE_REQUIRED')

    def test_cli_rejects_summary_and_json_together(self):
        argv = ['task_issues.py', '--feature', 'specs/example', '--parent', '1', '--summary', '--json']
        with mock.patch.object(sys, 'argv', argv), self.assertRaises(SystemExit) as ctx:
            t.main()
        self.assertEqual(ctx.exception.code, 2)

    def test_cli_summary_reports_any_unhandled_exception_as_one_line(self):
        # F7: a missing tasks.md raises a plain FileNotFoundError, outside the
        # WorkflowError/ValueError/KeyError set the previous except clause
        # covered; --summary must still print one `error <Type>: <msg>` line
        # and exit 1, not a raw traceback.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / 'specs/example'
            feature.mkdir(parents=True)
            (feature / 'scope-source.json').write_text(json.dumps({'repo': 'acme/app', 'issue': 1}))
            deps = root / 'deps.json'
            deps.write_text('{}')
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            subprocess.run(['git', 'remote', 'add', 'origin', 'git@github.com:acme/app.git'], cwd=root, check=True)
            argv = ['task_issues.py', '--root', str(root), '--feature', 'specs/example',
                    '--parent', '1', '--dependencies', str(deps), '--summary']
            buf = io.StringIO()
            with mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(buf):
                code = t.main()
            self.assertEqual(code, 1)
            line = buf.getvalue().strip()
            self.assertTrue(line.startswith('error FileNotFoundError: '), line)
            self.assertEqual(len(line.splitlines()), 1)

    def test_cli_default_still_raises_the_unhandled_exception(self):
        # Default (no --summary) behaviour for an exception outside the
        # existing except clause is unchanged: it still raises/tracebacks.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / 'specs/example'
            feature.mkdir(parents=True)
            (feature / 'scope-source.json').write_text(json.dumps({'repo': 'acme/app', 'issue': 1}))
            deps = root / 'deps.json'
            deps.write_text('{}')
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            subprocess.run(['git', 'remote', 'add', 'origin', 'git@github.com:acme/app.git'], cwd=root, check=True)
            argv = ['task_issues.py', '--root', str(root), '--feature', 'specs/example',
                    '--parent', '1', '--dependencies', str(deps)]
            with mock.patch.object(sys, 'argv', argv):
                with self.assertRaises(FileNotFoundError):
                    t.main()

    def test_json_flag_matches_the_unflagged_default_byte_for_byte(self):
        # F8: --json is not a new format; it is the same
        # `json.dumps(result, indent=2)`/error JSON the no-flag default
        # already printed, on the error path (deterministic, no gh needed)
        # and the success path (via FakeGitHub).
        def run(argv):
            buf = io.StringIO()
            with mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(buf):
                code = t.main()
            return code, buf.getvalue()

        with tempfile.TemporaryDirectory() as directory:
            base = ['task_issues.py', '--root', directory, '--feature', 'specs/example', '--parent', '1']
            default_code, default_out = run(base)
            json_code, json_out = run(base + ['--json'])
            self.assertEqual((default_code, default_out), (json_code, json_out))

        gh = FakeGitHub()
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
        subprocess.run(['git', 'remote', 'add', 'origin', 'git@github.com:acme/app.git'], cwd=root, check=True)
        folder = root / 'specs/001-a'; folder.mkdir(parents=True)
        (folder / 'scope-source.json').write_text(json.dumps({'repo': 'acme/app', 'issue': 10}))
        (folder / 'tasks.md').write_text('- [ ] T001 First behavior\n')
        deps = root / 'deps.json'; deps.write_text('{}')
        with mock.patch.object(t, 'GitHub', return_value=gh):
            default_code, default_out = run(['task_issues.py', '--root', str(root), '--feature', 'specs/001-a',
                                              '--parent', '10', '--dependencies', str(deps)])
        with mock.patch.object(t, 'GitHub', return_value=gh):
            json_code, json_out = run(['task_issues.py', '--root', str(root), '--feature', 'specs/001-a',
                                        '--parent', '10', '--dependencies', str(deps), '--json'])
        self.assertEqual((default_code, default_out), (json_code, json_out))
        self.assertIn('"action": "create"', default_out)
