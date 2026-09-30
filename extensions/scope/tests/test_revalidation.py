"""Existing-feature revalidation keeps identity without bypassing lifecycle evidence."""
import subprocess
import unittest
import test_scope as scope_fixture
import test_clarification as clarify_fixture

sm = scope_fixture.m


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def repository(root, remote='https://github.com/acme/app.git'):
    """A real repository whose origin is the GitHub repo the claim names; the
    claim's identity is now verified against it, not just the issue string."""
    if not (root / '.git').exists():
        git(root, 'init', '-q')
        git(root, 'config', 'user.name', 'Test')
        git(root, 'config', 'user.email', 'test@example.invalid')
        git(root, 'commit', '--allow-empty', '-qm', 'init')
        git(root, 'remote', 'add', 'origin', remote)
    workflow = sm.workflow_policy._workflow_module()
    return workflow.repo_identity(root)


def claim(root, stage, issue=1, receipts=None, identity=True):
    root = root.resolve()
    recorded = repository(root)
    feature = root / 'specs/001-example'
    feature.mkdir(parents=True, exist_ok=True)
    if not (feature / 'spec.md').exists():
        (feature / 'spec.md').write_text('# Existing behavior', encoding='utf-8')
    (root / '.specify/workflow.yml').write_text('schema_version: 1\nclarification:\n  resume_on_reinvoke: reread-answers\n', encoding='utf-8')
    sm.write_json(feature / 'scope-source.json', {'repo': 'acme/app', 'issue': 1})
    sm.write_json(root / '.specify/feature.json', {'feature_directory': 'specs/001-example'})
    sm.write_json(feature / 'workflow/checkpoint.json', {
        'schema_version': 1, 'repo_path': str(root), 'feature': 'specs/001-example',
        **({'repo_identity': recorded} if identity else {'head': git(root, 'rev-parse', 'HEAD')}),
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

    def test_bound_claim_ignores_a_foreign_repo_path(self):
        """A checkpoint's absolute `repo_path` (pre-1.8.0, or copied from
        elsewhere) never gates the claim; the GitHub issue binding above it
        already establishes portable identity (the checkpoint-identity
        design fix applies here too, not only to workflow.py's own load)."""
        feature = self.prepare()
        checkpoint = feature / 'workflow/checkpoint.json'
        state = sm.read_json(checkpoint)
        state['repo_path'] = '/some/other/machine/workspace'
        sm.write_json(checkpoint, state)
        self.gh.statuses[1] = 'In progress'; self.app._board = None
        self.assertEqual(self.app.gate('1')['issue'], 1)

    def test_bound_claim_refuses_a_foreign_repo_identity(self):
        """Codex round 1, finding 5: `bound_claim` accepted a checkpoint
        whose `repo_identity` belongs to another repository as long as the
        issue string matched; it now applies workflow's own identity gate."""
        feature = self.prepare()
        checkpoint = feature / 'workflow/checkpoint.json'
        state = sm.read_json(checkpoint)
        state['repo_identity'] = {'remote': 'github.com/evil/other', 'root_commit': 'b' * 40, 'shallow': False}
        sm.write_json(checkpoint, state)
        self.gh.statuses[1] = 'In progress'; self.app._board = None
        with self.assertRaisesRegex(sm.ScopeError, 'SPECIFY_STATE'): self.app.gate('1')

    def test_bound_claim_accepts_a_legacy_checkpoint_only_with_reachable_history(self):
        feature = self.prepare()
        checkpoint = feature / 'workflow/checkpoint.json'
        state = sm.read_json(checkpoint)
        del state['repo_identity']
        state['head'] = git(self.root, 'rev-parse', 'HEAD')
        sm.write_json(checkpoint, state)
        self.gh.statuses[1] = 'In progress'; self.app._board = None
        self.assertEqual(self.app.gate('1')['issue'], 1)
        state['head'] = 'c' * 40  # a commit this repository never had
        sm.write_json(checkpoint, state)
        with self.assertRaisesRegex(sm.ScopeError, 'SPECIFY_STATE'): self.app.gate('1')

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
