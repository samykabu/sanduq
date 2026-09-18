import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/scope.py'
spec = importlib.util.spec_from_file_location('scope', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
sys.modules['scope'] = m


class FakeGitHub:
    def __init__(self):
        self.issues = {}
        self.statuses = {}
        self.deps = {}
        self.children = {}
        self.labels = set()
        self.writes = []
        self.fail_once = None

    def add(self, n, title=None, body='', status='Backlog'):
        self.issues[n] = {'number': n, 'id': n * 100, 'node_id': f'I{n}', 'title': title or f'Issue {n}',
                          'body': body, 'state': 'open', 'state_reason': None, 'labels': [],
                          'html_url': f'https://github.com/acme/app/issues/{n}',
                          'repository_url': 'https://api.github.com/repos/acme/app'}
        self.statuses[n] = status
        return self.issues[n]

    def command(self, args, payload=None):
        if args[:2] == ['project', 'item-list']:
            items = [{'id': f'P{n}', 'status': self.statuses[n], 'content': {'number': n, 'repository': 'acme/app', 'type': 'Issue'}} for n in self.issues]
            return {'totalCount': len(items), 'items': items}
        if args[:2] == ['project', 'field-list']:
            return {'fields': []}
        if args[:2] == ['project', 'item-add']:
            self.writes.append(('item-add', args))
            return {'id': 'P' + args[args.index('--url') + 1].split('/')[-1]}
        if args[:2] == ['project', 'item-edit']:
            self.writes.append(('item-edit', args))
            n = int(args[args.index('--id') + 1][1:])
            self.statuses[n] = args[args.index('--single-select-option-id') + 1]
            return None
        raise AssertionError(args)

    def api(self, endpoint, method='GET', payload=None, pages=False):
        endpoint = endpoint.split('?')[0]
        parts = endpoint.split('/')
        if method != 'GET':
            if self.fail_once and self.fail_once in endpoint:
                self.fail_once = None
                raise m.ScopeError('simulated network interruption')
            self.writes.append((method, endpoint, copy.deepcopy(payload)))
        if endpoint == 'repos/acme/app/labels':
            if method == 'POST':
                self.labels.add(payload['name'])
                return payload
            return [{'name': x} for x in self.labels]
        if len(parts) == 4:
            if method == 'POST':
                return copy.deepcopy(self.add(max(self.issues) + 1, payload['title'], payload['body']))
            return copy.deepcopy(list(self.issues.values()))
        n = int(parts[4])
        if len(parts) == 5:
            if method == 'PATCH':
                self.issues[n].update(payload)
            return copy.deepcopy(self.issues[n])
        suffix = '/'.join(parts[5:])
        if suffix in ('comments', 'timeline'):
            return []
        if suffix.startswith('dependencies/blocked_by'):
            deps = self.deps.setdefault(n, set())
            if method == 'POST':
                deps.add(payload['issue_id'] // 100)
            elif method == 'DELETE':
                deps.discard(int(parts[-1]) // 100)
            return [copy.deepcopy(self.issues[d]) for d in sorted(deps)]
        if suffix == 'sub_issues':
            children = self.children.setdefault(n, set())
            if method == 'POST':
                children.add(payload['sub_issue_id'] // 100)
            return [copy.deepcopy(self.issues[d]) for d in sorted(children)]
        if suffix == 'labels':
            if method == 'POST':
                self.issues[n]['labels'] = [{'name': x} for x in set(payload['labels']) | {x['name'] for x in self.issues[n]['labels']}]
            return self.issues[n]['labels']
        if suffix.startswith('labels/') and method == 'DELETE':
            from urllib.parse import unquote
            self.issues[n]['labels'] = [x for x in self.issues[n]['labels'] if x['name'] != unquote(parts[-1])]
            return None
        raise AssertionError((method, endpoint, payload))


def node(key='root', score=3):
    dims = dict(zip(m.DIMENSIONS, [1, 1, 0, 1, 1]))
    if score == 8:
        dims = dict.fromkeys(m.DIMENSIONS, 2)
    return {'key': key, 'title': key, 'scope': 'A precise behavior', 'out_of_scope': 'Other behavior',
            'acceptance': ['Given a user, when action, then outcome'], 'covers': ['AC-1'],
            'evidence': ['src/feature.py:10'], 'dimensions': dims, 'score': score,
            'rationale': 'Known integration; coordinated verification', 'specify_prompt': 'Implement the specified behavior.'}


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        m.write_json(self.root / '.specify/extensions/project/config.json', {'projectId': 'P', 'projectNumber': 2,
                     'owner': 'acme', 'statusFieldId': 'F', 'statusOptions': {x: x for x in ['Backlog', 'Feature Specification', 'Need Clarifications', 'Ready', 'In progress', 'In review', 'Done']}, 'stateFile': '.specify/project-sync-state.json'})
        self.gh = FakeGitHub()
        self.gh.add(1)
        with patch.object(subprocess, 'check_output', return_value='https://github.com/acme/app.git'):
            self.app = m.Scope(self.root, self.gh)

    def tearDown(self):
        self.temp.cleanup()

    def analysis(self, split=False):
        snap = self.app.inspect('1')
        tree = node(score=8 if split else 3)
        if split:
            tree['children'] = [node('first'), node('second')]
            tree['children'][1]['depends_on'] = ['first']
        return snap, {'issue': 1, 'fingerprint': snap['fingerprint'], 'requirements': ['AC-1'],
                      'alignment': 'Reuses tested existing behavior', 'evidence': ['src/feature.py:10'], 'images': [], 'tree': tree}

    def publish_approved(self, snapshot, analysis):
        if not self.app.approval_path(analysis).exists():
            count = len(self.app.validate_analysis(snapshot, analysis)) - 1
            self.app.approve(snapshot, analysis, count, 'test owner', 'I approve this exact proposal.')
        return self.app.publish(snapshot, analysis, True)

    def test_missing_identity_before_network(self):
        with patch.object(m, 'Scope', side_effect=AssertionError('must not construct gateway')):
            self.assertEqual(m.main(['inspect']), 2)

    def test_project_keep_together_policy_settles_approval(self):
        (self.root / '.specify/workflow.yml').write_text('schema_version: 1\nscope:\n  keep_together:\n    target: 20\n    tolerance: 3\n    unit: points\n    inclusive: true\n', encoding='utf-8')
        snap, analysis = self.analysis()
        analysis['effort_estimate'] = {'value':20,'unit':'points'}
        self.app.publish(snap, analysis, True)
        self.assertEqual(len(self.gh.issues),1)
        self.assertEqual(self.app.gate('1')['issue'],1)
        receipt=m.metadata(self.gh.issues[1]['body'])
        self.assertEqual(receipt['approval']['approved_by'],'project-policy')

    def test_project_status_aliases_use_real_board_options(self):
        (self.root / '.specify/workflow.yml').write_text('schema_version: 1\nscope:\n  statuses:\n    Backlog: Todo\n    Feature Specification: Discovery\n', encoding='utf-8')
        self.app.cfg['statusOptions'].update({'Todo':'Todo','Discovery':'Discovery'})
        self.gh.statuses[1]='Todo'
        self.assertEqual(self.app.status(self.gh.issues[1]),'Backlog')
        self.app.set_status(self.gh.issues[1],'Feature Specification')
        self.assertEqual(self.gh.statuses[1],'Discovery')

    def test_title_exact_and_ambiguous(self):
        self.assertEqual(self.app.resolve('issue 1')['number'], 1)
        with self.assertRaises(m.ScopeError):
            self.app.resolve('issue')
        self.gh.add(2, 'Issue 1')
        with self.assertRaises(m.ScopeError):
            self.app.resolve('Issue 1')

    def test_blocked_report(self):
        self.gh.add(2, 'Foundation')
        self.gh.deps[1] = {2}
        result = self.app.inspect('1')
        self.assertEqual(result['blocked'], [{'number': 2, 'title': 'Foundation', 'status': 'Backlog'}])
        self.assertNotIn('implementation_evidence', result)
        self.assertIn('GitHub Issue Number | Title | Current status', m.rejection(result['blocked']))

    def test_transitive_blocker(self):
        self.gh.add(2, status='Done')
        self.gh.add(3)
        self.gh.deps.update({1: {2}, 2: {3}})
        self.assertEqual(self.app.inspect('1')['blocked'][0]['number'], 3)

    def test_unknown_and_cancelled_do_not_pass(self):
        self.gh.add(2, status='Done')['state_reason'] = 'not_planned'
        self.gh.deps[1] = {2}
        self.assertFalse(self.app.inspect('1')['ready'])
        self.gh.issues[2]['state_reason'] = None
        self.gh.statuses[2] = 'Unknown'
        self.app._board = None
        self.assertFalse(self.app.inspect('1')['ready'])

    def test_review_and_done_are_eligible(self):
        for status in ('In review', 'Done'):
            self.gh.add(2, status=status)
            self.gh.deps[1] = {2}
            self.app._board = None
            self.assertTrue(self.app.inspect('1')['ready'])

    def test_owner_override_excuses_only_the_named_pair(self):
        self.gh.add(2, 'Foundation', status='In progress')
        self.gh.add(3, 'Other', status='In progress')
        self.gh.add(4, 'Sibling')
        self.gh.deps.update({1: {2, 3}, 4: {2}})
        override = {'issue': 1, 'prerequisite': 2, 'reason': 'Foundation tasks need this issue first',
                    'approved_by': 'test owner', 'approval_text': 'Override for this issue only.'}
        m.write_json(self.root / '.specify/scope/prerequisite-overrides.json', {'version': 1, 'overrides': [override]})
        result = self.app.inspect('1')
        self.assertEqual([d['number'] for d in result['blocked']], [3])
        self.assertEqual(result['overridden'][0]['number'], 2)
        self.assertEqual(result['overridden'][0]['approved_by'], 'test owner')
        self.assertEqual([d['number'] for d in self.app.inspect('4')['blocked']], [2])
        self.gh.statuses[3] = 'Done'
        self.app._board = None
        self.assertTrue(self.app.inspect('1')['ready'])

    def test_override_without_approval_is_ignored(self):
        self.gh.add(2, status='In progress')
        self.gh.deps[1] = {2}
        m.write_json(self.root / '.specify/scope/prerequisite-overrides.json',
                     {'overrides': [{'issue': 1, 'prerequisite': 2, 'reason': 'no approval recorded'}]})
        self.assertFalse(self.app.inspect('1')['ready'])

    def test_dependency_cycle_fails(self):
        self.gh.add(2, status='Done')
        self.gh.deps.update({1: {2}, 2: {1}})
        with self.assertRaisesRegex(m.ScopeError, 'cycle'):
            self.app.inspect('1')

    def test_legacy_blocks_not_prerequisites(self):
        body = '### Dependencies\n\n**Blocked by** â€” finish first\n- #2\n\n**Blocks** â€” consumers\n- #3\n'
        self.assertEqual(self.app.refs(m.dependency_text(body)), {2})
        self.assertEqual(m.dependency_text('### Dependencies\n**Blocked by**\n- Nothing. This is the first issue.\n**Blocks**\n- #3'), '')

    def test_cross_repo_and_unresolved_key_fail(self):
        for ref in ['https://github.com/other/repo/issues/2', 'BOOT-99']:
            with self.assertRaises(m.ScopeError):
                self.app.refs(ref)

    def test_images_html_markdown_reference(self):
        text = '<img src="https://a/b.png"> ![x](https://a/c.webp) ![ref][pic]\n[pic]: https://a/d.jpg'
        self.assertEqual(m.images(text), ['https://a/b.png', 'https://a/c.webp', 'https://a/d.jpg'])

    def test_images_must_be_observed(self):
        snap, analysis = self.analysis()
        snap['images'] = ['https://a/image.png']
        with self.assertRaisesRegex(m.ScopeError, 'visually inspected'):
            self.app.validate_analysis(snap, analysis)

    def test_effort_boundaries(self):
        self.assertEqual(m.effort(dict.fromkeys(m.DIMENSIONS, 0)), 1)
        self.assertEqual(m.effort(dict.fromkeys(m.DIMENSIONS, 3)), 21)
        with self.assertRaises(m.ScopeError):
            m.effort(dict.fromkeys(m.DIMENSIONS, True))

    def test_high_leaf_is_reported_without_forced_split(self):
        snap, analysis = self.analysis()
        analysis['tree'] = node(score=8)
        nodes = self.app.validate_analysis(snap, analysis)
        self.assertTrue(any(n['score'] == 8 and not n.get('children') for n in nodes.values()))

    def test_declared_score_must_match(self):
        snap, analysis = self.analysis()
        analysis['tree']['score'] = 1
        with self.assertRaisesRegex(m.ScopeError, 'rubric'):
            self.app.validate_analysis(snap, analysis)

    def test_recursive_high_descendant_keeps_honest_score(self):
        snap, analysis = self.analysis(True)
        analysis['tree']['children'][1] = node('large', 8)
        nodes = self.app.validate_analysis(snap, analysis)
        self.assertTrue(any(n['score'] == 8 and not n.get('children') for n in nodes.values()))

    def test_proposed_cycle_rejected(self):
        snap, analysis = self.analysis(True)
        analysis['tree']['children'][0]['depends_on'] = ['second']
        with self.assertRaisesRegex(m.ScopeError, 'Cycle'):
            self.app.validate_analysis(snap, analysis)

    def test_coverage_required(self):
        snap, analysis = self.analysis(True)
        for child in analysis['tree']['children']:
            child['covers'] = ['AC-2']
        with self.assertRaisesRegex(m.ScopeError, 'omit'):
            self.app.validate_analysis(snap, analysis)

    def test_dry_run_has_no_writes(self):
        snap, analysis = self.analysis(True)
        result = self.app.publish(snap, analysis)
        self.assertEqual(result['leaves'], 2)
        self.assertEqual(self.gh.writes, [])
        self.assertFalse((self.root / '.specify/scope').exists())

    def test_apply_without_user_approval_has_no_github_writes(self):
        snap, analysis = self.analysis(True)
        with self.assertRaisesRegex(m.ScopeError, 'APPROVAL_REQUIRED'):
            self.app.publish(snap, analysis, True)
        self.assertEqual(self.gh.writes, [])
        self.assertEqual(len(self.gh.issues), 1)

    def test_approval_is_local_and_binds_selected_child_count(self):
        snap, analysis = self.analysis(True)
        approved = self.app.approve(snap, analysis, 2, 'product owner', 'I approve these two sub-issues.')
        self.assertEqual(approved['child_count'], 2)
        self.assertEqual(self.gh.writes, [])
        self.assertTrue(self.app.approval_path(analysis).is_file())
        result = self.app.publish(snap, analysis, True)
        self.assertEqual(len(result['nodes']) - 1, 2)

    def test_selected_count_mismatch_cannot_be_approved(self):
        snap, analysis = self.analysis(True)
        with self.assertRaisesRegex(m.ScopeError, 'CHILD_COUNT'):
            self.app.approve(snap, analysis, 3, 'owner', 'Approve three children.')
        self.assertFalse(self.app.approval_path(analysis).exists())
        self.assertEqual(self.gh.writes, [])

    def test_revised_proposal_carries_approval_forward_unattended(self):
        """Constitution, Principle I: revisions of an approved decomposition never re-prompt."""
        snap, analysis = self.analysis(True)
        self.app.approve(snap, analysis, 2, 'owner', 'Approved two scopes.')
        analysis['tree']['children'][0]['scope'] = 'A materially changed scope'
        result = self.app.publish(snap, analysis, True)
        revision = result['revision']
        self.assertTrue(revision['carried_forward'])
        self.assertEqual(revision['approved_by'], 'owner')
        self.assertIn('scope', revision['difference']['changed']['first'])
        self.assertEqual(revision['difference']['changed']['first']['scope']['after'],
                         'A materially changed scope')

    def test_revision_receipt_records_the_difference_for_audit(self):
        snap, analysis = self.analysis(True)
        self.app.approve(snap, analysis, 2, 'owner', 'Approved two scopes.')
        analysis['tree']['children'][0]['title'] = 'Retitled after approval'
        self.app.publish(snap, analysis, True)
        receipt = m.read_json(self.app.approval_path(analysis), {})
        self.assertTrue(receipt['carried_forward'])
        self.assertEqual(receipt['approved_by'], 'owner')
        self.assertTrue(receipt['revision_of'])
        self.assertIn('title', receipt['difference']['changed']['first'])

    def test_revision_diffs_against_approved_baseline_not_prior_revision(self):
        """Successive revisions each diff against what the owner actually approved.

        Exercised through require_approval rather than publish: republishing children that
        already exist under a different analysis operation is refused by a separate guard
        in create(), which this carve-out deliberately does not touch.
        """
        snap, analysis = self.analysis(True)
        self.app.approve(snap, analysis, 2, 'owner', 'Approved two scopes.')
        baseline_title = analysis['tree']['children'][0]['title']

        analysis['tree']['children'][0]['title'] = 'First revision'
        first = self.app.require_approval(snap, analysis, self.app.validate_analysis(snap, analysis))
        self.assertEqual(first['difference']['changed']['first']['title']['before'], baseline_title)

        analysis['tree']['children'][0]['title'] = 'Second revision'
        second = self.app.require_approval(snap, analysis, self.app.validate_analysis(snap, analysis))
        change = second['difference']['changed']['first']['title']
        self.assertEqual(change['after'], 'Second revision')
        # Still the approved baseline, not the intermediate revision.
        self.assertEqual(change['before'], baseline_title)
        self.assertEqual(second['revision_of'], first['revision_of'])

    def test_revision_without_any_prior_approval_still_blocks(self):
        """The carve-out covers revisions only; initial decomposition still needs approval."""
        snap, analysis = self.analysis(True)
        analysis['tree']['children'][0]['scope'] = 'Never approved by anyone'
        with self.assertRaisesRegex(m.ScopeError, 'APPROVAL_REQUIRED'):
            self.app.publish(snap, analysis, True)
        self.assertEqual(self.gh.writes, [])

    def test_nested_aggregate_counts_toward_user_selected_total(self):
        snap, analysis = self.analysis(True)
        analysis['tree']['children'][0]['children'] = [node('nested-first'), node('nested-second')]
        analysis['tree']['children'][1]['depends_on'] = ['nested-first', 'nested-second']
        with self.assertRaisesRegex(m.ScopeError, 'CHILD_COUNT'):
            self.app.approve(snap, analysis, 2, 'owner', 'Approve two issues.')
        approval = self.app.approve(snap, analysis, 4, 'owner', 'Approve all four proposed sub-issues.')
        self.assertEqual(approval['child_count'], 4)
        self.assertEqual(self.gh.writes, [])

    def test_user_selected_two_large_children_are_not_recursively_split(self):
        snap, analysis = self.analysis(True)
        analysis['tree']['children'] = [node('first', 8), node('second', 8)]
        self.app.approve(snap, analysis, 2, 'owner', 'Approve these two larger scopes.')
        result = self.app.publish(snap, analysis, True)
        self.assertEqual(len(result['nodes']) - 1, 2)
        self.assertEqual(len(self.gh.issues), 3)

    def test_cancelled_operation_cannot_be_republished(self):
        snap, analysis = self.analysis(True)
        self.app.approve(snap, analysis, 2, 'owner', 'Approved two scopes.')
        journal = self.root / '.specify/scope/runs' / f'1-{m.analysis_hash(analysis)[:16]}' / 'journal.json'
        m.write_json(journal, {'rolled_back': True})
        with self.assertRaisesRegex(m.ScopeError, 'SCOPE_ROLLED_BACK'):
            self.app.publish(snap, analysis, True)
        self.assertEqual(self.gh.writes, [])

    def test_changed_dependencies_carry_forward_and_are_recorded(self):
        """A moved prerequisite set is a revision too: it proceeds, but is recorded."""
        snap, analysis = self.analysis()
        self.app.approve(snap, analysis, 0, 'owner', 'Keep one issue; approve this scope.')
        self.gh.add(2, status='Done')
        self.gh.deps[1] = {2}
        self.app._board = None
        result = self.app.publish(self.app.inspect('1'), analysis, True)
        difference = result['revision']['difference']
        self.assertEqual(difference['dependencies']['after'], [2])
        self.assertIn('prerequisite set changed since approval', difference['summary'])

    def test_owner_can_keep_high_effort_issue_without_artificial_splitting(self):
        snap, analysis = self.analysis()
        analysis['tree'] = node(score=8)
        self.app.approve(snap, analysis, 0, 'owner', 'Keep this as one 8-point issue; approved.')
        self.app.publish(snap, analysis, True)
        self.assertEqual(len(self.gh.issues), 1)
        self.assertEqual(self.app.gate('1')['score'], 8)
        self.assertIn('scope:large', {x['name'] for x in self.gh.issues[1]['labels']})

    def test_leaf_publish_gate_and_stale_requirements(self):
        snap, analysis = self.analysis()
        self.publish_approved(snap, analysis)
        self.assertEqual(self.app.gate('1')['score'], 3)
        self.gh.issues[1]['body'] += '\nA new requirement'
        with self.assertRaisesRegex(m.ScopeError, 'STALE'):
            self.app.gate('1')

    def test_missing_label_and_parent_gate(self):
        snap, analysis = self.analysis()
        self.publish_approved(snap, analysis)
        self.gh.issues[1]['labels'] = []
        with self.assertRaisesRegex(m.ScopeError, 'label'):
            self.app.gate('1')

    def test_parent_prompt_retired(self):
        body = '## Requirements\nKeep this\n## Speckit Specify prompt\n```text\n/speckit.specify build\n```\n## Notes\nKeep too'
        retired = m.retire_prompts(body)
        self.assertIn('Keep this', retired)
        self.assertIn('Keep too', retired)
        self.assertNotIn('/speckit.specify', retired)

    def test_split_links_scores_rewire_and_gate(self):
        self.gh.add(2, 'Consumer', '### Blocked by\n- #1')
        self.gh.deps[2] = {1}
        snap, analysis = self.analysis(True)
        result = self.publish_approved(snap, analysis)
        first, second = result['nodes']['first'], result['nodes']['second']
        self.assertEqual(self.gh.children[1], {first, second})
        self.assertEqual(self.gh.deps[2], {first, second})
        self.assertEqual(self.gh.deps[second], {first})
        self.assertTrue((self.root / '.specify/scope/plan-pending.json').exists())
        self.assertEqual(m.metadata(self.gh.issues[first]['body'])['score'], 3)
        with self.assertRaisesRegex(m.ScopeError, 'SCOPE_PARENT'):
            self.app.gate('1')
        (self.root / '.specify/scope/plan-pending.json').unlink()
        with self.assertRaisesRegex(m.ScopeError, 'NOT_READY'):
            self.app.gate(str(second))

    def test_reconcile_complete_and_reopen(self):
        snap, analysis = self.analysis(True)
        result = self.publish_approved(snap, analysis)
        children = [result['nodes']['first'], result['nodes']['second']]
        for c in children:
            self.gh.statuses[c] = 'Done'
        self.app._board = None
        self.app.reconcile(True)
        self.assertEqual(self.gh.issues[1]['state'], 'closed')
        self.assertEqual(self.gh.statuses[1], 'Done')
        self.gh.statuses[children[0]] = 'In progress'
        self.app._board = None
        self.app.reconcile(True)
        self.assertEqual(self.gh.issues[1]['state'], 'open')
        self.assertEqual(self.gh.statuses[1], 'In review')

    def test_bind_uses_original_issue(self):
        snap, analysis = self.analysis()
        self.publish_approved(snap, analysis)
        directory = self.root / 'specs/001-example'
        directory.mkdir(parents=True)
        (directory / 'spec.md').write_text('# Example')
        m.write_json(self.root / '.specify/feature.json', {'feature_directory': 'specs/001-example'})
        self.app.bind('1', True)
        state = m.read_json(self.root / '.specify/project-sync-state.json')
        self.assertEqual(state['001-example']['issue'], 1)
        self.assertEqual(len(self.gh.issues), 1)
        self.assertEqual(self.gh.statuses[1], 'Feature Specification')
        self.assertEqual(state['001-example']['status'], 'Feature Specification')
        self.app.bind('1', True)  # A partial after-Specify retry keeps the same issue.
        self.assertEqual(len(self.gh.issues), 1)

    def test_specify_only_accepts_backlog_before_inspection(self):
        for status in ('Feature Specification', 'Need Clarifications', 'Ready', 'In progress', 'In review', 'Done'):
            self.gh.statuses[1] = status
            self.app._board = None
            with patch.object(self.app, 'inspect', side_effect=AssertionError('must not inspect')):
                with self.assertRaisesRegex(m.ScopeError, 'SPECIFY_STATE'):
                    self.app.gate('1')

    def test_split_rerun_preserves_issue_count(self):
        self.gh.issues[1]['body'] = '## Scope\nKeep behavior\n## Specify prompt\n```text\n/speckit.specify behavior\n```'
        snap, analysis = self.analysis(True)
        result = self.publish_approved(snap, analysis)
        again = self.publish_approved(self.app.inspect('1'), analysis)
        self.assertEqual(result['nodes'], again['nodes'])
        self.assertEqual(len(self.gh.issues), 3)

    def test_retry_after_native_link_failure_does_not_duplicate(self):
        snap, analysis = self.analysis(True)
        self.gh.fail_once = '/sub_issues'
        with self.assertRaisesRegex(m.ScopeError, 'interruption'):
            self.publish_approved(snap, analysis)
        self.publish_approved(self.app.inspect('1'), analysis)
        self.assertEqual(len(self.gh.issues), 3)

    def test_changed_dependencies_invalidate_scope(self):
        snap, analysis = self.analysis()
        self.publish_approved(snap, analysis)
        self.gh.add(2, status='Done')
        self.gh.deps[1] = {2}
        self.app._board = None
        with self.assertRaisesRegex(m.ScopeError, 'prerequisites changed'):
            self.app.gate('1')

    def test_progress_rollup_is_idempotent(self):
        snap, analysis = self.analysis(True)
        self.publish_approved(snap, analysis)
        self.app.reconcile(True)
        before = len(self.gh.writes)
        self.app.reconcile(True)
        self.assertEqual(len(self.gh.writes), before)

    def test_nested_parent_rollup(self):
        snap, analysis = self.analysis(True)
        nested = node('nested', 8)
        nested['children'] = [node('part-a'), node('part-b')]
        analysis['tree']['children'][1] = nested
        result = self.publish_approved(snap, analysis)
        for key in ('first', 'part-a', 'part-b'):
            self.gh.statuses[result['nodes'][key]] = 'Done'
        self.app._board = None
        self.app.reconcile(True)
        self.assertEqual(self.gh.statuses[1], 'Done')
        self.assertEqual(self.gh.issues[1]['state'], 'closed')

    def test_dependent_rewire_invalidates_previous_scope(self):
        self.gh.add(2, body='### Dependencies\n**Blocked by**\n- #1\n**Blocks**\n- None.')
        self.gh.statuses[1] = 'Done'
        self.app._board = None
        dep_snap = self.app.inspect('2')
        _, analysis = self.analysis()
        dep_analysis = dict(analysis, issue=2, fingerprint=dep_snap['fingerprint'])
        self.publish_approved(dep_snap, dep_analysis)
        self.assertEqual(self.app.gate('2')['issue'], 2)
        snap, split = self.analysis(True)
        self.publish_approved(snap, split)
        with self.assertRaisesRegex(m.ScopeError, 'STALE'):
            self.app.gate('2')

    def test_export_updates_reverse_links_without_staling_leaves(self):
        snap, analysis = self.analysis(True)
        result = self.publish_approved(snap, analysis)
        first = result['nodes']['first']
        second = result['nodes']['second']
        self.assertIn(f'- #{second}', self.gh.issues[first]['body'])
        with self.assertRaisesRegex(m.ScopeError, 'PLAN_PENDING'):
            self.app.gate(str(first))
        (self.root / '.specify/scope/plan-pending.json').unlink()
        self.assertEqual(self.app.gate(str(first))['score'], 3)

    def test_existing_epic_child_is_preserved_and_rewired(self):
        self.gh.add(2, 'Existing epic', '### Blocked by\n- #1')
        self.gh.children[1] = {2}
        self.gh.deps[2] = {1}
        snap, analysis = self.analysis(True)
        result = self.publish_approved(snap, analysis)
        leaves = {result['nodes']['first'], result['nodes']['second']}
        self.assertEqual(self.gh.children[1], leaves | {2})
        self.assertEqual(self.gh.deps[2], leaves)
        for leaf in leaves:
            self.gh.statuses[leaf] = 'Done'
        self.app._board = None
        self.app.reconcile(True)
        self.assertEqual(self.gh.statuses[1], 'In review')
        self.assertEqual(self.gh.issues[1]['state'], 'open')

    def test_inline_dependency_is_replaced(self):
        self.gh.add(2, body='Depends on: #1\n\n## Scope\nKeep this')
        snap, analysis = self.analysis(True)
        result = self.publish_approved(snap, analysis)
        self.assertEqual(set(self.app.dependencies(self.gh.issues[2])), {result['nodes']['first'], result['nodes']['second']})

    def test_network_read_failure_is_not_a_missing_dependency(self):
        with patch.object(self.gh, 'api', side_effect=m.ScopeError('403 unavailable')):
            with self.assertRaisesRegex(m.ScopeError, '403'):
                self.app.inspect('1')
        self.assertFalse(self.gh.writes)

    def test_reconcile_dry_run_has_no_writes(self):
        snap, analysis = self.analysis(True)
        self.publish_approved(snap, analysis)
        before = len(self.gh.writes)
        self.app.reconcile(False)
        self.assertEqual(len(self.gh.writes), before)

    def test_human_edits_block_publication_retry(self):
        self.gh.issues[1]['body'] = '## Scope\nOne\n## Specify prompt\nOld prompt'
        snap, analysis = self.analysis(True)
        self.publish_approved(snap, analysis)
        self.gh.issues[1]['body'] += '\nHuman added requirement'
        with self.assertRaisesRegex(m.ScopeError, 'Requirements changed during publication'):
            self.publish_approved(self.app.inspect('1'), analysis)


if __name__ == '__main__':
    unittest.main()
