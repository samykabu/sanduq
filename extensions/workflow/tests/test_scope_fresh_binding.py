import copy
import json
import types
import unittest
from unittest.mock import patch
import test_scope as f
import test_scope_revalidation as r

m = f.m


class FreshBindingTests(unittest.TestCase):
    setUp = f.ScopeTests.setUp
    tearDown = f.ScopeTests.tearDown
    analysis = f.ScopeTests.analysis
    publish_approved = f.ScopeTests.publish_approved

    def prepare(self, stage='scope', issue=1):
        identity = r.repository(self.root)
        workflow = m.workflow_policy._workflow_module()
        import yaml
        (self.root / '.specify/workflow.yml').write_text(yaml.safe_dump(workflow.default_policy(False, False)))
        feature = self.root / 'specs/001-new'; feature.mkdir(parents=True)
        state = {'schema_version': 1, 'feature': 'specs/001-new', 'issue': f'acme/app#{issue}',
                 'branch': r.git(self.root, 'branch', '--show-current'), 'repo_identity': identity,
                 'receipts': {}, 'active': {'stage': stage, 'mode': 'initial', 'token': 'owned', 'session_id': 'session'}}
        m.write_json(feature / 'workflow/checkpoint.json', state)
        return feature, state

    def decisions(self, pending=False, issue=1):
        # A copy: the loaded module is cached per process and must stay real for the other tests.
        module = types.SimpleNamespace(**vars(m.workflow_policy._decisions_module()))
        module.reconcile = lambda *args, **kwargs: {'version': 1, 'feature': 'specs/001-new', 'issue': f'acme/app#{issue}',
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

    def carried_child(self, revisions=2):
        """A parent approved with two children; child #2 kept whole and re-scoped after `revisions`
        body edits, so its receipt carries the parent's approval through that many revisions."""
        snap, analysis = self.analysis(True); self.publish_approved(snap, analysis)
        prompt = m.metadata(self.gh.issues[2]['body'])['prompt']
        for n in range(revisions):
            self.gh.issues[2]['body'] += f'\n\nOwner note {n}.'
            child = self.app.inspect('2')
            revision = dict(analysis, issue=2, fingerprint=child['fingerprint'], tree=dict(f.node('first'), specify_prompt=prompt))
            self.app.publish(child, revision, True)
        self.gh.statuses[2] = 'Feature Specification'; self.app._board = None
        self.prepare(issue=2)
        return revision

    def fresh_gate_child(self, analysis):
        with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions(issue=2)):
            return self.app.gate('2', feature='specs/001-new', token='owned', session='session', analysis=analysis)

    def test_fresh_gate_accepts_a_carried_child_revision_traced_to_the_live_parent_approval(self):
        for revisions in (1, 2):
            with self.subTest(revisions=revisions):
                self.tearDown(); self.setUp()
                analysis = self.carried_child(revisions)
                parent = m.metadata(self.gh.issues[1]['body'])['approval']
                receipt = m.metadata(self.gh.issues[2]['body'])['approval']
                self.assertNotEqual(receipt, parent)
                writes = list(self.gh.writes)
                result = self.fresh_gate_child(analysis)
                self.assertEqual((result['parent'], result['approval']), (1, receipt))
                self.assertEqual(self.gh.writes, writes)

    def set_receipt(self, number, **changes):
        receipt = m.metadata(self.gh.issues[number]['body']); receipt.update(changes)
        self.gh.issues[number]['body'] = m.replace_block(self.gh.issues[number]['body'],
                                                         '<!-- speckit-scope:metadata ' + json.dumps(receipt) + ' -->')

    def test_fresh_gate_refuses_a_carried_child_whose_native_parent_was_removed(self):
        # The parent's approval covered #2 as its child; with the link gone it covers nothing.
        for revisions, records in ((1, True), (2, True), (2, False)):
            with self.subTest(revisions=revisions, records=records):
                self.tearDown(); self.setUp()
                analysis = self.carried_child(revisions)
                self.gh.children = {}
                if not records:
                    for path in (self.root / '.specify/scope/approvals').glob('*.json'): path.unlink()
                with self.assertRaisesRegex(m.ScopeError, 'SCOPE_CARRIED_APPROVAL_WITHOUT_PARENT'):
                    self.fresh_gate_child(analysis)

    def test_fresh_gate_accepts_a_root_kept_whole_carrying_its_own_approval(self):
        for records in (True, False):
            with self.subTest(records=records):
                self.tearDown(); self.setUp()
                snap, analysis = self.analysis(); self.publish_approved(snap, analysis)
                for n in range(2):
                    self.gh.issues[1]['body'] += f'\n\nOwner note {n}.'
                    snap = self.app.inspect('1'); analysis = dict(analysis, fingerprint=snap['fingerprint'])
                    self.app.publish(snap, analysis, True)
                receipt = m.metadata(self.gh.issues[1]['body'])['approval']
                self.assertTrue(receipt['carried_forward'])
                if not records:  # gated in another checkout than the one that approved and revised it
                    for path in (self.root / '.specify/scope/approvals').glob('*.json'): path.unlink()
                self.gh.statuses[1] = 'Feature Specification'; self.app._board = None
                self.prepare()
                with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions()):
                    result = self.app.gate('1', feature='specs/001-new', token='owned', session='session', analysis=analysis)
                self.assertEqual((result['parent'], result['approval']), (None, receipt))

    def test_fresh_gate_refuses_a_root_whose_carried_chain_leads_to_another_issue(self):
        snap, analysis = self.analysis(); self.publish_approved(snap, analysis)
        self.gh.issues[1]['body'] += '\n\nOwner note.'
        snap = self.app.inspect('1'); analysis = dict(analysis, fingerprint=snap['fingerprint'])
        self.app.publish(snap, analysis, True)
        receipt = m.metadata(self.gh.issues[1]['body'])['approval']
        folder = self.root / '.specify/scope/approvals'
        origin = folder / f'1-{receipt["revision_of"]}.json'
        m.write_json(origin, dict(m.read_json(origin), issue=7))
        self.gh.statuses[1] = 'Feature Specification'; self.app._board = None
        self.prepare()
        with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions()):
            with self.assertRaisesRegex(m.ScopeError, 'SCOPE_CARRIED_APPROVAL_WITHOUT_PARENT'):
                self.app.gate('1', feature='specs/001-new', token='owned', session='session', analysis=analysis)

    def test_fresh_gate_refuses_forged_missing_cyclic_foreign_or_revoked_carried_lineage(self):
        folder = lambda: self.root / '.specify/scope/approvals'
        receipt = lambda: m.metadata(self.gh.issues[2]['body'])['approval']
        parent = lambda: m.metadata(self.gh.issues[1]['body'])['approval']
        head = lambda: folder() / f'2-{receipt()["analysis_sha256"]}.json'
        middle = lambda: folder() / f'2-{receipt()["revision_of"]}.json'
        owner = lambda: folder() / f'1-{parent()["analysis_sha256"]}.json'

        def edit(path, **changes):
            m.write_json(path, dict(m.read_json(path), **changes))

        def reparent():
            other = dict(parent(), analysis_sha256='f' * 64)
            self.gh.add(9, body=m.replace_block('', '<!-- speckit-scope:metadata ' + json.dumps(
                dict(m.metadata(self.gh.issues[1]['body']), children=[2], approval=other)) + ' -->'))
            m.write_json(folder() / f'9-{"f" * 64}.json', dict(m.read_json(owner()), issue=9, analysis_sha256='f' * 64))
            self.gh.children = {9: {2}}

        cases = {
            # Forged receipts: a skipped hop, an unrecorded hash, the parent approval relabelled as carried.
            'skipped hop': lambda: self.set_receipt(2, approval=dict(receipt(), revision_of=parent()['analysis_sha256'])),
            'unrecorded hash': lambda: self.set_receipt(2, approval=dict(receipt(), analysis_sha256='e' * 64)),
            'relabelled parent': lambda: self.set_receipt(2, approval=dict(parent(), carried_forward=True, revision_of='e' * 64)),
            'other approver': lambda: self.set_receipt(2, approval=dict(receipt(), approved_by='someone else')),
            'forged record approver': lambda: (edit(head(), approved_by='someone else'),
                                               self.set_receipt(2, approval=dict(receipt(), approved_by='someone else'))),
            # Missing provenance.
            'missing head record': lambda: head().unlink(),
            'missing middle record': lambda: middle().unlink(),
            'missing owner record': lambda: owner().unlink(),
            'owner statement missing': lambda: edit(owner(), approval_text=''),
            'broken link': lambda: edit(middle(), revision_of=None),
            # A cycle, and a hop recorded for another issue or repository or with children.
            'cycle': lambda: edit(middle(), revision_of=receipt()['analysis_sha256']),
            'foreign issue hop': lambda: edit(middle(), issue=3),
            'foreign repository hop': lambda: edit(middle(), repo='other/app'),
            'split hop': lambda: edit(middle(), child_count=1),
            'uncarried hop': lambda: edit(middle(), carried_forward=False),
            # Wrong parent: the live native parent's approval is not where the lineage leads.
            'wrong parent': reparent,
            # The parent's approval revoked or changed since the child carried it.
            'parent approval changed': lambda: self.set_receipt(1, approval=dict(parent(), approved_by='someone else')),
            'parent re-approved': lambda: self.set_receipt(1, approval=dict(parent(), analysis_sha256='d' * 64)),
            'parent child count changed': lambda: self.set_receipt(1, approval=dict(parent(), child_count=3)),
            'owner record changed': lambda: edit(owner(), approved_at='2000-01-01T00:00:00+00:00'),
            'child removed from parent': lambda: self.set_receipt(1, children=[3]),
        }
        for name, tamper in cases.items():
            with self.subTest(name):
                self.tearDown(); self.setUp()
                analysis = self.carried_child(2)
                tamper()
                with self.assertRaisesRegex(m.ScopeError, 'SCOPE_RETAINED_PARENT_APPROVAL_MISMATCH'):
                    self.fresh_gate_child(analysis)

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
        with patch.object(m, 'Scope', return_value=self.app), patch.object(m, 'mutation_lock', side_effect=AssertionError('must not create lock')):
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

    def test_minus_text_resolved_analysis_is_compared_byte_exact(self):
        # A `-text` file keeps its CRLF bytes; a CRLF-normalised evidence hash must not vouch for it (F6).
        analysis = self.prepare_published_child()
        analysis['tree']['specify_prompt'] += ' Apply the evidenced owner resolution.'
        module, artifact = self.real_applied_analysis(analysis)
        (self.root / '.gitattributes').write_text('specs/001-new/reviews/*.json -text\n')
        artifact.write_bytes(artifact.read_bytes().replace(b'\n', b'\r\n'))
        name = artifact.relative_to(self.root).as_posix()
        real = m.workflow_policy.fresh_claim
        def normalised(*args, **kwargs):
            fresh = real(*args, **kwargs)
            fresh['decision_evidence'][name] = __import__('hashlib').sha256(
                artifact.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            return fresh
        with patch.object(m.workflow_policy, '_decisions_module', return_value=module), \
                patch.object(module, 'verify_ledger', lambda *args: None), \
                patch.object(m.workflow_policy, 'fresh_claim', normalised):
            with self.assertRaisesRegex(m.ScopeError, 'SCOPE_RESOLVED_ANALYSIS_EVIDENCE_MISMATCH'):
                self.app.gate('1', feature='specs/001-new', token='owned', session='session',
                              analysis=analysis, analysis_path=artifact)

    def test_unchanged_published_prompt_remains_authoritative_without_analysis_application(self):
        analysis = self.prepare_published_child(); analysis['tree']['scope'] = 'Consulted local description'
        published = m.metadata(self.gh.issues[1]['body'])['prompt']
        with patch.object(m.workflow_policy, '_decisions_module', return_value=self.decisions()):
            result = self.app.gate('1', feature='specs/001-new', token='owned', session='session', analysis=analysis)
        self.assertEqual(result['prompt'], published)
        self.assertEqual(result['analysis_role'], 'consulted')
        self.assertIsNone(result['applied_analysis_sha256'])


if __name__ == '__main__': unittest.main()
