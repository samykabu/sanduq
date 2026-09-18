"""Existing-feature revalidation keeps identity without bypassing lifecycle evidence."""
import unittest
import test_scope as scope_fixture
import test_clarification as clarify_fixture

sm = scope_fixture.m


def claim(root, stage, issue=1, receipts=None):
    root = root.resolve()
    feature = root / 'specs/001-example'
    feature.mkdir(parents=True, exist_ok=True)
    if not (feature / 'spec.md').exists():
        (feature / 'spec.md').write_text('# Existing behavior', encoding='utf-8')
    (root / '.specify/workflow.yml').write_text('schema_version: 1\nclarification:\n  resume_on_reinvoke: reread-answers\n', encoding='utf-8')
    sm.write_json(feature / 'scope-source.json', {'repo': 'acme/app', 'issue': 1})
    sm.write_json(root / '.specify/feature.json', {'feature_directory': 'specs/001-example'})
    sm.write_json(feature / 'workflow/checkpoint.json', {
        'schema_version': 1, 'repo_path': str(root), 'feature': 'specs/001-example',
        'issue': f'acme/app#{issue}', 'active': {'stage': stage, 'token': 'owned', 'mode': 'revalidate'},
        'receipts': receipts or {},
    })
    return feature


class ScopeRevalidationTests(unittest.TestCase):
    setUp = scope_fixture.ScopeTests.setUp
    tearDown = scope_fixture.ScopeTests.tearDown
    analysis = scope_fixture.ScopeTests.analysis
    publish_approved = scope_fixture.ScopeTests.publish_approved

    def prepare(self, stage='scope', issue=1):
        snapshot, analysis = self.analysis()
        self.publish_approved(snapshot, analysis)
        feature = claim(self.root, stage, issue)
        self.gh.statuses[1] = 'In progress'; self.app._board = None
        return feature

    def test_existing_scope_can_be_rechecked_without_status_write(self):
        self.prepare(); before = list(self.gh.writes)
        self.assertEqual(self.app.gate('1')['issue'], 1)
        self.assertEqual(self.gh.writes, before)
        self.assertEqual(self.gh.statuses[1], 'In progress')

    def test_revalidation_still_rejects_changed_requirements(self):
        self.prepare()
        self.gh.issues[1]['body'] += '\nNew unreviewed requirement\n'
        with self.assertRaisesRegex(sm.ScopeError, 'SCOPE_STALE'):
            self.app.gate('1')

    def test_wrong_claim_or_closed_issue_cannot_bypass_backlog_gate(self):
        self.prepare(issue=2)
        with self.assertRaisesRegex(sm.ScopeError, 'SPECIFY_STATE'): self.app.gate('1')
        claim(self.root, 'scope'); self.gh.issues[1]['state'] = 'closed'
        with self.assertRaisesRegex(sm.ScopeError, 'SPECIFY_STATE'): self.app.gate('1')

    def test_rebinding_same_feature_preserves_progressed_board_status(self):
        feature = self.prepare(stage='specify'); before = (feature / 'spec.md').read_bytes()
        self.app.bind('1', apply=True)
        self.assertEqual(self.gh.statuses[1], 'In progress')
        self.assertEqual((feature / 'spec.md').read_bytes(), before)
        self.assertEqual(sm.read_json(feature / 'scope-source.json')['issue'], 1)


class ClarifyRevalidationTests(unittest.TestCase):
    setUp = clarify_fixture.ClarificationTests.setUp
    tearDown = clarify_fixture.ClarificationTests.tearDown
    move = clarify_fixture.ClarificationTests.move

    def test_claim_allows_reading_new_comments_on_advanced_feature(self):
        claim(self.root, 'clarify'); self.move('In progress')
        self.gh.comment('New requirement needs review')
        self.assertEqual(self.app.inspect('1')['comments'][0]['body'], 'New requirement needs review')
        self.assertEqual(self.gh.statuses[1], 'In progress')
        self.assertEqual(self.gh.writes, [])

    def test_policy_alone_does_not_grant_advanced_clarify_access(self):
        feature = claim(self.root, 'clarify'); self.move('In review')
        (feature / 'workflow/checkpoint.json').unlink()
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_STATE'): self.app.inspect('1')

    def test_plan_revalidation_requires_resolved_clarification_and_open_issue(self):
        resolved = {'clarify': {'outcome': 'passed', 'unresolved': 0, 'answers_applied': True}}
        claim(self.root, 'plan', receipts=resolved); self.move('In progress')
        self.assertTrue(self.app.plan_gate('1')['revalidation'])
        resolved['clarify']['unresolved'] = 1
        claim(self.root, 'plan', receipts=resolved)
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_REQUIRED'): self.app.plan_gate('1')
        resolved['clarify']['unresolved'] = 0
        claim(self.root, 'plan', receipts=resolved); self.gh.issues[1]['state'] = 'closed'
        with self.assertRaisesRegex(sm.ScopeError, 'CLARIFICATION_REQUIRED'): self.app.plan_gate('1')
