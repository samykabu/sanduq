import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
