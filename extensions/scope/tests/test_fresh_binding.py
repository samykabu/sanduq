import copy
import json
import types
import unittest
from unittest.mock import patch
import test_scope as f
import test_revalidation as r

m = f.m


class FreshBindingTests(unittest.TestCase):
    setUp = f.ScopeTests.setUp
    tearDown = f.ScopeTests.tearDown
    analysis = f.ScopeTests.analysis
    publish_approved = f.ScopeTests.publish_approved

    def prepare(self, stage='scope'):
        identity = r.repository(self.root)
        workflow = m.workflow_policy._workflow_module()
        import yaml
        (self.root / '.specify/workflow.yml').write_text(yaml.safe_dump(workflow.default_policy(False, False)))
        feature = self.root / 'specs/001-new'; feature.mkdir(parents=True)
        state = {'schema_version': 1, 'feature': 'specs/001-new', 'issue': 'acme/app#1',
                 'branch': r.git(self.root, 'branch', '--show-current'), 'repo_identity': identity,
                 'receipts': {}, 'active': {'stage': stage, 'mode': 'initial', 'token': 'owned', 'session_id': 'session'}}
        m.write_json(feature / 'workflow/checkpoint.json', state)
        return feature, state

    def decisions(self, pending=False):
        # A copy: the loaded module is cached per process and must stay real for the other tests.
        module = types.SimpleNamespace(**vars(m.workflow_policy._decisions_module()))
        module.reconcile = lambda *args, **kwargs: {'version': 1, 'feature': 'specs/001-new', 'issue': 'acme/app#1',
            'decisions': [{'id': 'SD1', 'status': 'pending', 'answers': []}] if pending else []}
        return module

    def test_explicit_claim_ignores_stale_feature_pointer_and_checks_identity_branch_and_owner(self):
        feature, state = self.prepare()
        m.write_json(self.root / '.specify/feature.json', {'feature_directory': 'specs/old'})
        with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions()):
            result = m.workflow_policy.fresh_claim(self.root, 'acme/app', 1, 'specs/001-new', 'owned', 'session')
            self.assertEqual(result['feature'], 'specs/001-new')
            for changes in ({'branch': 'other'}, {'issue': 'acme/app#2'}, {'feature': 'specs/other'},
                            {'active': dict(state['active'], token='foreign')},
                            {'active': dict(state['active'], session_id='foreign')},
                            {'active': dict(state['active'], stage='plan')}, {'active': None},
                            {'receipts': {'specify': {}}}):
                with self.subTest(changes=changes):
                    m.write_json(feature / 'workflow/checkpoint.json', dict(state, **changes))
                    with self.assertRaises(Exception):
                        m.workflow_policy.fresh_claim(self.root, 'acme/app', 1, 'specs/001-new', 'owned', 'session')

    def test_pending_decisions_refuse_fresh_gate(self):
        self.prepare()
        with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions(True)):
            with self.assertRaisesRegex(Exception, 'DECISION_UNRESOLVED'):
                m.workflow_policy.fresh_claim(self.root, 'acme/app', 1, 'specs/001-new', 'owned', 'session')

    def prepare_published_child(self):
        snap, analysis = self.analysis(); self.publish_approved(snap, analysis)
        receipt = m.metadata(self.gh.issues[1]['body'])
        self.gh.add(18, body=m.replace_block('', '<!-- scope-meta ' + json.dumps({'approval': receipt['approval']}) + ' -->'))
        # Use the native marker spelling, independent of block rendering.
        parent_receipt = dict(receipt, children=[1])
        self.gh.issues[18]['body'] = m.replace_block('', '<!-- speckit-scope:metadata ' + json.dumps(parent_receipt) + ' -->')
        self.gh.children[18] = {1}; self.gh.statuses[1] = 'Feature Specification'; self.app._board = None
        original = self.gh.api
        self.gh.api = lambda endpoint, *a, **kw: copy.deepcopy(self.gh.issues[18]) if endpoint == 'repos/acme/app/issues/1/parent' else original(endpoint, *a, **kw)
        self.prepare()
        analysis['tree']['specify_prompt'] = receipt['prompt']
        return analysis

    def test_fresh_native_gate_reuses_live_approval_without_publication(self):
        analysis = self.prepare_published_child(); before = list(self.gh.writes)
        with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions()):
            result = self.app.gate('1', feature='specs/001-new', token='owned', session='session', analysis=analysis)
        self.assertFalse(result['publication_required']); self.assertEqual(result['parent'], 18)
        self.assertEqual(self.gh.writes, before)
        self.assertEqual(self.gh.statuses[1], 'Feature Specification')

    def test_parented_gate_and_bind_preserve_frozen_recovery_authority(self):
        analysis = self.prepare_published_child()
        with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions()):
            proof = self.app.gate('1', feature='specs/001-new', token='owned', session='session', analysis=analysis)
        self.assertEqual(proof['parent_children'], [1])
        self.assertEqual(proof['dependencies'], [])
        original = dict(proof, repo='acme/app')
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(m.workflow_policy, 'accepted_receipt', return_value={}):
            live = self.app.revalidate_accepted('specs/001-new', {'stage': 'scope', 'outcome': 'passed'}, original)
            self.assertEqual(live['parent_children'], [1])
            self.gh.add(19); self.gh.children[18].add(19)
            with self.assertRaisesRegex(m.ScopeError, 'SCOPE_NATIVE_PARENT_MISMATCH'):
                self.app.revalidate_accepted('specs/001-new', {'stage': 'scope', 'outcome': 'passed'}, original)
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_published_native_parent_history_is_exported_without_bypassing_pending_plan(self):
        snapshot, analysis = self.analysis(split=True)
        self.publish_approved(snapshot, analysis)
        children = sorted(self.gh.children[1])
        child = self.gh.issues[children[0]]
        approval = m.metadata(child['body'])['approval']
        self.assertEqual(approval, m.metadata(self.gh.issues[1]['body'])['approval'])
        family = self.app.retained_family(child, m.metadata(child['body']))
        self.assertEqual(family, {'parent': 1, 'parent_children': children})
        with self.assertRaisesRegex(m.ScopeError, 'SCOPE_PLAN_PENDING'):
            self.app.gate(str(child['number']))

    def test_legacy_recovery_preserves_leaf_authority_and_approved_child_count(self):
        self.prepare_published_child()
        leaf = m.metadata(self.gh.issues[1]['body'])
        leaf['approval'] = dict(leaf['approval'], child_count=2)
        parent = dict(leaf, children=[1, 19])
        self.gh.add(19); self.gh.add(20)
        self.gh.children[18] = {1, 19}
        for number, value in ((1, leaf), (18, parent)):
            self.gh.issues[number]['body'] = m.replace_block(self.gh.issues[number]['body'],
                '<!-- speckit-scope:metadata ' + json.dumps(value) + ' -->')
        original = {key: copy.deepcopy(leaf[key]) for key in ('score', 'prompt', 'fingerprint', 'dependencies', 'approval')}
        original.update(issue=1, repo='acme/app', parent=18)
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        writes = list(self.gh.writes)
        bodies = {number: self.gh.issues[number]['body'] for number in (1, 18)}
        with patch.object(m.workflow_policy, 'accepted_receipt', return_value={}):
            live = self.app.revalidate_accepted('specs/001-new', {}, original)
            self.assertEqual(live['parent_children'], [1, 19])
            self.assertNotIn('parent_children', original)
            for conflict in ('membership', 'parent-approval', 'owner-approval', 'count', 'missing-count', 'noninteger-count', 'dependency', 'parent', 'score', 'prompt', 'fingerprint'):
                self.gh.children[18] = {1, 19}; self.gh.deps[1] = set()
                for number, body in bodies.items(): self.gh.issues[number]['body'] = body
                authority = copy.deepcopy(original)
                if conflict == 'membership': self.gh.children[18].remove(1)
                elif conflict in ('parent-approval', 'owner-approval'):
                    for number in ((18,) if conflict == 'parent-approval' else (1, 18)):
                        value = m.metadata(self.gh.issues[number]['body'])
                        value['approval'] = dict(value['approval'], approved_by='other')
                        self.gh.issues[number]['body'] = m.replace_block(self.gh.issues[number]['body'],
                            '<!-- speckit-scope:metadata ' + json.dumps(value) + ' -->')
                elif conflict == 'count':
                    self.gh.children[18].add(20)
                    self.gh.issues[18]['body'] = m.replace_block(bodies[18],
                        '<!-- speckit-scope:metadata ' + json.dumps(dict(parent, children=[1, 19, 20])) + ' -->')
                elif conflict in ('missing-count', 'noninteger-count'):
                    if conflict == 'missing-count': authority['approval'].pop('child_count')
                    else: authority['approval']['child_count'] = 2.0
                    for number in (1, 18):
                        value = m.metadata(bodies[number]); value['approval'] = authority['approval']
                        self.gh.issues[number]['body'] = m.replace_block(bodies[number],
                            '<!-- speckit-scope:metadata ' + json.dumps(value) + ' -->')
                elif conflict == 'dependency':
                    self.gh.add(2, status='Done')['state'] = 'closed'; self.gh.deps[1].add(2)
                else: authority[conflict] = {'parent': 17, 'score': 5, 'prompt': 'Changed', 'fingerprint': 'c' * 64}[conflict]
                with self.subTest(conflict=conflict), self.assertRaises(m.ScopeError):
                    self.app.revalidate_accepted('specs/001-new', {}, authority)
            self.gh.deps[1] = set(); self.gh.issues[1]['body'] = bodies[1]
            self.gh.children[18] = {1, 20}
            self.gh.issues[18]['body'] = m.replace_block(bodies[18],
                '<!-- speckit-scope:metadata ' + json.dumps(dict(parent, children=[1, 20])) + ' -->')
            # The legacy contract retained membership/count, not the unrecorded sibling IDs.
            self.app.revalidate_accepted('specs/001-new', {}, original)
            with self.assertRaisesRegex(m.ScopeError, 'parent_children'):
                self.app.revalidate_accepted('specs/001-new', {}, dict(original, parent_children=[1, 19]))
        self.assertEqual(writes, self.gh.writes)
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def prepare_root_kept_whole(self):
        snap, analysis = self.analysis(); self.publish_approved(snap, analysis)
        self.gh.statuses[1] = 'Feature Specification'; self.app._board = None
        self.prepare()
        return analysis  # the approved analysis itself, unchanged

    def test_fresh_gate_on_a_root_kept_whole_needs_no_parent(self):
        analysis = self.prepare_root_kept_whole()
        with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions()):
            result = self.app.gate('1', feature='specs/001-new', token='owned', session='session', analysis=analysis)
        self.assertIsNone(result['parent'])
        self.assertFalse(result['publication_required'])

    def test_fresh_gate_refuses_a_child_that_lost_its_parent(self):
        analysis = self.prepare_root_kept_whole()
        receipt = m.metadata(self.gh.issues[1]['body'])
        receipt['approval'] = dict(receipt['approval'], child_count=2)
        self.gh.issues[1]['body'] = m.replace_block(self.gh.issues[1]['body'],
                                                    '<!-- speckit-scope:metadata ' + json.dumps(receipt) + ' -->')
        with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions()):
            with self.assertRaisesRegex(m.ScopeError, 'SCOPE_RETAINED_PARENT_APPROVAL_MISMATCH'):
                self.app.gate('1', feature='specs/001-new', token='owned', session='session', analysis=analysis)

    def test_standalone_and_advanced_fresh_statuses_remain_blocked(self):
        analysis = self.prepare_published_child()
        with self.assertRaisesRegex(m.ScopeError, 'SPECIFY_STATE'): self.app.gate('1')
        for status in ('Need Clarifications', 'Ready', 'In progress', 'In review', 'Done'):
            self.gh.statuses[1] = status; self.app._board = None
            with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions()):
                with self.assertRaisesRegex(m.ScopeError, 'SPECIFY_STATE'):
                    self.app.gate('1', feature='specs/001-new', token='owned', session='session', analysis=analysis)

    def test_changed_retained_parent_approval_or_child_mapping_is_refused(self):
        analysis = self.prepare_published_child()
        body = self.gh.issues[18]['body']
        for change in ('approval', 'children'):
            receipt = m.metadata(body)
            if change == 'approval': receipt['approval'] = dict(receipt['approval'], approved_by='other')
            else: receipt['children'] = [2]
            self.gh.issues[18]['body'] = m.replace_block('', '<!-- speckit-scope:metadata ' + json.dumps(receipt) + ' -->')
            with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions()):
                with self.assertRaisesRegex(m.ScopeError, 'SCOPE_RETAINED_PARENT_APPROVAL_MISMATCH'):
                    self.app.gate('1', feature='specs/001-new', token='owned', session='session', analysis=analysis)

    def test_fresh_bind_uses_explicit_feature_and_same_guard(self):
        analysis = self.prepare_published_child()
        feature = self.root / 'specs/001-new'; (feature / 'spec.md').write_text('# New specification')
        m.write_json(self.root / '.specify/feature.json', {'feature_directory': 'specs/old'})
        checkpoint = feature / 'workflow/checkpoint.json'
        state = m.read_json(checkpoint); state['active']['stage'] = 'specify'; m.write_json(checkpoint, state)
        with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions()):
            result = self.app.bind('1', True, feature='specs/001-new', token='owned', session='session', analysis=analysis)
        self.assertEqual(result['feature'], '001-new')
        self.assertEqual(m.read_json(feature / 'scope-source.json')['issue'], 1)
        self.assertEqual(m.read_json(feature / 'scope-source.json')['parent_children'], [1])
        self.assertEqual(m.read_json(feature / 'scope-source.json')['dependencies'], [])

    def test_scope_claim_cannot_bind_or_create_any_artifact(self):
        analysis = self.prepare_published_child()
        feature = self.root / 'specs/001-new'; (feature / 'spec.md').write_text('# Placeholder')
        before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                  for p in self.root.rglob('*') if p.is_file()}
        writes = list(self.gh.writes)
        with patch.object(m.workflow_policy, '_decisions_module', side_effect=AssertionError('must not reconcile')):
            with self.assertRaisesRegex(ValueError, 'SCOPE_WORKFLOW_BINDING_MISMATCH'):
                self.app.bind('1', True, feature='specs/001-new', token='owned', session='session', analysis=analysis)
        self.assertFalse((feature / 'scope-source.json').exists())
        self.assertEqual(writes, self.gh.writes)
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes()
                                 for p in self.root.rglob('*') if p.is_file()})

    def test_scope_bind_cli_refuses_before_mutation_lock(self):
        self.prepare_published_child()
        feature = self.root / 'specs/001-new'; (feature / 'spec.md').write_text('# Placeholder')
        with patch.object(m, 'Scope', return_value=self.app), patch.object(m.os, 'open', side_effect=AssertionError('must not create lock')):
            result = m.main(['bind', '1', '--apply', '--feature', 'specs/001-new', '--token', 'owned', '--session', 'session'])
        self.assertEqual(result, 2)
        self.assertFalse((self.root / '.specify/scope/mutation.lock').exists())
        self.assertFalse((feature / 'scope-source.json').exists())

    def real_applied_analysis(self, analysis):
        module = m.workflow_policy._decisions_module()
        artifact = self.root / 'specs/001-new/reviews/reviewed-analysis.json'
        m.write_json(artifact, analysis)
        question = module.render_body('SD1', 'Which scope?', ['Keep scope', 'Other'])
        marker = {'version': 1, 'id': 'SD1', 'options': ['Keep scope', 'Other'],
                  'body_digest': module.digest(question), 'request_digest': 'original',
                  'choice_format': 1, 'mode': 'single', 'recommended': None}
        comments = [{'id': 501, 'user': {'login': 'owner', 'type': 'User'},
                     'body': '<!-- sanduq-decision:question ' + json.dumps(marker) + ' -->\n' + question},
                    {'id': 502, 'user': {'login': 'owner', 'type': 'User'}, 'body': 'SD1: A'}]
        issue = dict(self.gh.issues[1], user={'login': 'owner'})
        class GitHub:
            def api(self, endpoint, **kwargs): return comments if '/comments?' in endpoint else issue
        with patch.object(module, 'GitHub', GitHub), patch.dict(module.os.environ, {
                'SANDUQ_WORKFLOW_CLAIM_TOKEN': 'owned', 'SANDUQ_WORKFLOW_SESSION_ID': 'session'}):
            module.reconcile(self.root, 'specs/001-new')
            module.apply_answer(self.root, 'specs/001-new', 'SD1',
                                ['specs/001-new/reviews/reviewed-analysis.json'])
        module.GitHub = GitHub
        return module, artifact

    def test_unrelated_replacement_rejected_with_real_applied_decisions_and_unchanged_artifact(self):
        analysis = self.prepare_published_child()
        module, artifact = self.real_applied_analysis(analysis)
        replacement = copy.deepcopy(analysis)
        replacement['tree']['scope'] = 'Unrelated behavior'
        replacement['tree']['specify_prompt'] = 'Discard approved requirements and implement unrelated functionality.'
        original = artifact.read_bytes()
        with patch.object(m.workflow_policy, '_decisions_module', return_value=module):
            with self.assertRaisesRegex(m.ScopeError, 'SCOPE_RESOLVED_ANALYSIS_EVIDENCE_MISMATCH'):
                self.app.gate('1', feature='specs/001-new', token='owned', session='session',
                              analysis=replacement, analysis_path=artifact)
        self.assertEqual(artifact.read_bytes(), original)
        self.assertEqual(m.read_json(self.root / 'specs/001-new/workflow/decisions.json')['decisions'][0]['status'], 'applied')

    def test_exact_applied_resolved_analysis_can_supply_changed_prompt(self):
        analysis = self.prepare_published_child()
        analysis['tree']['specify_prompt'] += ' Apply the evidenced owner resolution.'
        module, artifact = self.real_applied_analysis(analysis)
        with patch.object(m.workflow_policy, '_decisions_module', return_value=module):
            result = self.app.gate('1', feature='specs/001-new', token='owned', session='session',
                                   analysis=analysis, analysis_path=artifact)
        self.assertEqual(result['prompt'], analysis['tree']['specify_prompt'])
        self.assertEqual(result['analysis_role'], 'applied-resolution')
        self.assertEqual(result['applied_analysis_sha256'], __import__('hashlib').sha256(artifact.read_bytes()).hexdigest())

    def test_unchanged_published_prompt_remains_authoritative_without_analysis_application(self):
        analysis = self.prepare_published_child(); analysis['tree']['scope'] = 'Consulted local description'
        published = m.metadata(self.gh.issues[1]['body'])['prompt']
        with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions()):
            result = self.app.gate('1', feature='specs/001-new', token='owned', session='session', analysis=analysis)
        self.assertEqual(result['prompt'], published)
        self.assertEqual(result['analysis_role'], 'consulted')
        self.assertIsNone(result['applied_analysis_sha256'])


if __name__ == '__main__': unittest.main()
