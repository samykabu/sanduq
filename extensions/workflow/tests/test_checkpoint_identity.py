"""Workflow 1.8.0 checkpoint-identity design fix, plus round-1 review fixes.

A checkpoint used to hard-gate every command on the absolute `repo_path` it
was started from, which is machine- and clone-specific and failed
`CHECKPOINT_IDENTITY_MISMATCH` on any other clone, worktree, instance,
delegated worker or CI runner (the checkpoint-identity design bug). These
tests cover the portable replacement: `repo_identity` (a normalised remote
and/or a root-commit SHA), the legacy-checkpoint upgrade path, the security
property that a checkpoint from a different repository is still refused, and
the explicit `relocate` command for a repository that legitimately moved.

Round 1 review additionally requires (and is tested here): the checkpoint's
bound issue must name this repository's own GitHub remote, for legacy and
new checkpoints alike, refusing when there is no GitHub remote to check
(finding 1); `relocate` itself refuses a foreign checkpoint's repository
change unless explicitly allowed (finding 2); `normalize_remote_url` parses
a real URL with `urllib.parse` rather than an ad-hoc regex (finding 3); the
root commit is also required to match when neither clone is shallow, even
when the remote does (finding 4); `repo_path` is still written for an older
reader (finding 5); and the delegated-context env read is shared with
`delegate_dispatch` (finding 7).
"""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow as w  # noqa: E402
import fixture_008  # noqa: E402
import test_workflow as fixture  # noqa: E402


def git(root, *args, check=True):
    return subprocess.run(['git', *args], cwd=root, check=check, capture_output=True, text=True, encoding='utf-8')


class HelperTests(unittest.TestCase):
    """Unit coverage of the identity primitives, independent of a checkpoint."""

    def test_normalize_remote_url_folds_scheme_credentials_and_case(self):
        forms = [
            'https://github.com/Acme/App.git',
            'https://x-access-token:ghs_secret@Github.com/Acme/App.git',
            'git@github.com:Acme/App.git',
            'ssh://git@GITHUB.COM/Acme/App/',
            'https://github.com/Acme/App',
            'https://github.com./Acme/App',  # DNS-rooted form of the same host
        ]
        normalised = {w.normalize_remote_url(url) for url in forms}
        self.assertEqual(normalised, {'github.com/Acme/App'})

    def test_normalize_remote_url_keeps_path_case(self):
        # The host folds by DNS convention; the path does not, because some
        # hosts (self-hosted GitLab/Bitbucket) are case sensitive there.
        self.assertNotEqual(w.normalize_remote_url('https://example.com/Acme/App.git'),
                            w.normalize_remote_url('https://example.com/acme/app.git'))

    def test_normalize_remote_url_strips_dotgit_case_insensitively_once(self):
        self.assertEqual(w.normalize_remote_url('https://github.com/Acme/App.GIT'), 'github.com/Acme/App')
        # Only one suffix is stripped -- a doubled one is not a real convention to fold further.
        self.assertEqual(w.normalize_remote_url('https://github.com/Acme/App.git.git'), 'github.com/Acme/App.git')

    def test_normalize_remote_url_strips_trailing_slashes_and_trailing_dotgit_slash(self):
        self.assertEqual(w.normalize_remote_url('https://github.com/Acme/App//'), 'github.com/Acme/App')
        self.assertEqual(w.normalize_remote_url('https://github.com/Acme/App.git/'), 'github.com/Acme/App')

    def test_normalize_remote_url_keeps_an_explicit_port_distinct_from_a_numeric_path_segment(self):
        # Round 1, finding 3: the original regex read an SSH URL's explicit
        # port as the first path segment, so this pair collided into one
        # identity even though they name unrelated things. A non-default
        # port (2222, not ssh's default 22) so it is kept, not folded away.
        port_form = w.normalize_remote_url('ssh://git@git.example.com:2222/team/app.git')
        path_form = w.normalize_remote_url('https://git.example.com/2222/team/app')
        self.assertEqual(port_form, 'git.example.com:2222/team/app')
        self.assertEqual(path_form, 'git.example.com/2222/team/app')
        self.assertNotEqual(port_form, path_form)

    def test_normalize_remote_url_folds_a_default_port(self):
        # Round 2, LOW (optional): a port equal to its scheme's well-known
        # default carries no identity.
        self.assertEqual(w.normalize_remote_url('ssh://git@github.com:22/acme/app.git'),
                         w.normalize_remote_url('ssh://git@github.com/acme/app.git'))
        self.assertEqual(w.normalize_remote_url('https://github.com:443/acme/app.git'),
                         w.normalize_remote_url('https://github.com/acme/app.git'))

    def test_normalize_remote_url_folds_windows_drive_letter_case(self):
        # Round 2, LOW (optional): unlike the rest of the path, a Windows
        # drive letter genuinely is case-insensitive.
        self.assertEqual(w.normalize_remote_url('C:/repos/App.git'), w.normalize_remote_url('c:/repos/App.git'))
        self.assertEqual(w.normalize_remote_url('c:/repos/App.git'), 'c:/repos/App')

    def test_normalize_remote_url_drops_query_and_fragment(self):
        self.assertEqual(w.normalize_remote_url('https://github.com/Acme/App?x=1'), 'github.com/Acme/App')
        self.assertEqual(w.normalize_remote_url('https://github.com/Acme/App#frag'), 'github.com/Acme/App')

    def test_normalize_remote_url_resists_userinfo_host_confusion(self):
        # The real host is whichever comes after the last unescaped '@';
        # a remote crafted to *look* like it starts with github.com must
        # never be read as github.com.
        self.assertEqual(w.normalize_remote_url('https://github.com@evil.com/Acme/App'), 'evil.com/Acme/App')
        self.assertEqual(w.normalize_remote_url('https://user:pass@github.com/Acme/App'), 'github.com/Acme/App')

    def test_normalize_remote_url_never_crashes_on_a_malformed_port_and_never_case_folds_it(self):
        # A non-numeric "port" (a URL-confusion attempt, or just malformed
        # input) must not crash and must not be misparsed as SCP shorthand
        # (which would read "https" as the host and evil.com's "://" tail
        # as its path).
        for original in ('https://evil.com:github.com/Acme/App', 'https://gitlab.com:Acme/App'):
            value = w.normalize_remote_url(original)
            self.assertEqual(value, original)  # opaque, unfolded fallback -- never crashes, never case-folds

    def test_normalize_remote_url_windows_drive_paths_collide_by_separator_only(self):
        forward = w.normalize_remote_url('C:/repos/App.git')
        back = w.normalize_remote_url('C:\\repos\\App.git')
        self.assertEqual(forward, 'c:/repos/App')  # drive letter folded to lower case (round 2, LOW)
        self.assertEqual(forward, back)
        # A single-letter "host" is a drive letter, never SCP shorthand;
        # the rest of the path still keeps its case.
        self.assertEqual(forward, w.normalize_remote_url('c:/repos/App.git'))
        self.assertNotEqual(w.normalize_remote_url('C:/Repos/App.git'), w.normalize_remote_url('C:/repos/App.git'))

    def test_normalize_remote_url_file_uri_and_bare_path_are_not_case_folded(self):
        self.assertEqual(w.normalize_remote_url('file:///srv/git/App.git'), '/srv/git/App')
        self.assertEqual(w.normalize_remote_url('/srv/git/App.git'), '/srv/git/App')
        self.assertEqual(w.normalize_remote_url('../App'), '../App')

    def test_identity_matches_remote_is_authoritative_over_shared_root_commit_when_shallow_or_unknown(self):
        # A fork shares root-commit history but has a different remote --
        # exactly the case `relocate` exists for, so an automatic match here
        # would defeat it.
        recorded = {'remote': 'github.com/acme/app', 'root_commit': 'a' * 40}
        forked = {'remote': 'github.com/acme/app-fork', 'root_commit': 'a' * 40}
        self.assertFalse(w.identity_matches(recorded, forked))

    def test_identity_matches_same_remote_regardless_of_root_commit_when_shallow(self):
        # A shallow CI clone only sees a truncated (shallow-boundary) root
        # commit, not the true root; the remote alone must still match.
        recorded = {'remote': 'github.com/acme/app', 'root_commit': 'a' * 40, 'shallow': False}
        shallow = {'remote': 'github.com/acme/app', 'root_commit': 'b' * 40, 'shallow': True}
        self.assertTrue(w.identity_matches(recorded, shallow))

    def test_identity_matches_requires_root_commit_too_when_neither_side_is_shallow(self):
        # Round 1, finding 4: a shared remote is still just local Git
        # config, spoofable by whoever controls the clone; when we can tell
        # neither side's history was truncated by a shallow clone, also
        # require the root commit to match, catching a remote simply
        # copied into an unrelated clone.
        recorded = {'remote': 'github.com/acme/app', 'root_commit': 'a' * 40, 'shallow': False}
        unrelated = {'remote': 'github.com/acme/app', 'root_commit': 'b' * 40, 'shallow': False}
        same = {'remote': 'github.com/acme/app', 'root_commit': 'a' * 40, 'shallow': False}
        self.assertFalse(w.identity_matches(recorded, unrelated))
        self.assertTrue(w.identity_matches(recorded, same))

    def test_identity_matches_stricter_root_commit_check_never_refuses_a_legacy_identity(self):
        # `shallow` absent (a repo_identity recorded before this check
        # existed) must stay lenient, not newly refuse a previously-accepted
        # checkpoint.
        recorded = {'remote': 'github.com/acme/app', 'root_commit': 'a' * 40}
        unrelated = {'remote': 'github.com/acme/app', 'root_commit': 'b' * 40}
        self.assertTrue(w.identity_matches(recorded, unrelated))

    def test_identity_matches_falls_back_to_root_commit_without_a_remote(self):
        no_remote = {'remote': None, 'root_commit': 'c' * 40}
        self.assertTrue(w.identity_matches(no_remote, {'remote': None, 'root_commit': 'c' * 40}))
        self.assertFalse(w.identity_matches(no_remote, {'remote': None, 'root_commit': 'd' * 40}))

    def test_identity_matches_refuses_when_only_one_side_has_a_remote(self):
        self.assertFalse(w.identity_matches({'remote': 'github.com/acme/app', 'root_commit': 'a' * 40},
                                            {'remote': None, 'root_commit': 'a' * 40}))
        self.assertFalse(w.identity_matches({'remote': None, 'root_commit': 'a' * 40},
                                            {'remote': 'github.com/acme/app', 'root_commit': 'a' * 40}))

    def test_identity_matches_refuses_a_malformed_recorded_root_commit(self):
        """Round 3: the recorded root commit comes from an editable file and
        must be a full hex object id before it reaches git. `HEAD` or a
        branch name would be "reachable" from any unrelated clone, a short
        sha is ambiguous, and `--foo` would be read as an option."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            git(root, 'init', '-q')
            git(root, 'config', 'user.name', 'Test')
            git(root, 'config', 'user.email', 'test@example.invalid')
            git(root, 'commit', '--allow-empty', '-qm', 'root')
            head = w.root_commit_sha(root)
            branch = git(root, 'branch', '--show-current').stdout.strip()
            current = {'remote': None, 'root_commit': 'f' * 40}
            for bad in ('HEAD', branch, '--foo', head[:12], head.upper(), 'HEAD~0', '', None):
                self.assertFalse(w.root_commit_still_reachable(root, bad), repr(bad))
                self.assertFalse(w.identity_matches({'remote': None, 'root_commit': bad}, current, current_root=root),
                                 repr(bad))
            self.assertTrue(w.root_commit_still_reachable(root, head))

    def test_identity_matches_compares_github_remotes_case_insensitively(self):
        """Round 3, LOW: GitHub owner/repo names are not case sensitive."""
        recorded = {'remote': 'github.com/acme/app', 'root_commit': 'a' * 40}
        self.assertTrue(w.identity_matches(recorded, {'remote': 'github.com/Acme/App', 'root_commit': 'a' * 40}))
        self.assertTrue(w.identity_matches({'remote': 'github.com:2222/acme/app'},
                                           {'remote': 'github.com:2222/ACME/app'}))
        # Other hosts may be case sensitive: still exact.
        self.assertFalse(w.identity_matches({'remote': 'git.example.com/acme/app'},
                                            {'remote': 'git.example.com/Acme/App'}))
        self.assertFalse(w.identity_matches({'remote': 'github.com.evil.io/acme/app'},
                                            {'remote': 'github.com.evil.io/Acme/app'}))

    def test_identity_matches_accepts_a_still_reachable_older_root_commit(self):
        """Round 2, finding N4: without a live repository to check ancestry
        against, a differing root commit is still refused (unchanged,
        pure-dict behaviour); with one, the recorded root is accepted if
        it is still an ancestor of HEAD there, even though it is no longer
        what `root_commit_sha` itself would currently pick."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            git(root, 'init', '-q')
            git(root, 'config', 'user.name', 'Test')
            git(root, 'config', 'user.email', 'test@example.invalid')
            git(root, 'commit', '--allow-empty', '-qm', 'root')
            recorded_root = w.root_commit_sha(root)
            git(root, 'commit', '--allow-empty', '-qm', 'second')
            recorded = {'remote': None, 'root_commit': recorded_root}
            current = {'remote': None, 'root_commit': 'f' * 40}  # e.g. a differently-picked root after a merge
            self.assertFalse(w.identity_matches(recorded, current))
            self.assertTrue(w.identity_matches(recorded, current, current_root=root))
            # An unrelated commit (not actually in this repo's history at all) is still refused.
            self.assertFalse(w.identity_matches({'remote': None, 'root_commit': 'e' * 40}, current, current_root=root))

    def test_repo_identity_reads_a_real_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            git(root, 'init', '-q')
            git(root, 'config', 'user.name', 'Test')
            git(root, 'config', 'user.email', 'test@example.invalid')
            git(root, 'commit', '--allow-empty', '-qm', 'init')
            no_remote = w.repo_identity(root)
            self.assertIsNone(no_remote['remote'])
            self.assertRegex(no_remote['root_commit'], r'^[0-9a-f]{40}$')
            self.assertFalse(no_remote['shallow'])
            git(root, 'remote', 'add', 'origin', 'git@github.com:acme/app.git')
            with_remote = w.repo_identity(root)
            self.assertEqual(with_remote['remote'], 'github.com/acme/app')
            self.assertEqual(with_remote['root_commit'], no_remote['root_commit'])


class DelegatedContextSharedReaderTests(unittest.TestCase):
    """Round 1, finding 7: workflow.py and delegate_dispatch.py must never
    disagree about what SANDUQ_DELEGATED_RUN/SANDUQ_DELEGATED_ROLE mean."""

    def test_both_call_sites_read_delegated_run_through_the_same_function(self):
        import delegation
        import delegate_dispatch as dd
        original = delegation.delegated_run_id
        delegation.delegated_run_id = lambda: 'spoofed'
        try:
            with self.assertRaises(delegation.DelegationError):
                dd.require_not_worker_context()
            with self.assertRaises(w.WorkflowError):
                w.require_not_delegated_context('relocate')
        finally:
            delegation.delegated_run_id = original

    def test_real_env_var_refuses_both(self):
        import delegate_dispatch as dd
        os.environ['SANDUQ_DELEGATED_RUN'] = 'run-1'
        try:
            with self.assertRaisesRegex(Exception, 'DELEGATION_WORKER_CONTEXT'):
                dd.require_not_worker_context()
            with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_WORKER_CONTEXT'):
                w.require_not_delegated_context('relocate')
        finally:
            os.environ.pop('SANDUQ_DELEGATED_RUN', None)


class Harness(unittest.TestCase):
    """A fresh repo, ready for `Run`, without the full LegacyCheckpointTests scaffolding."""

    def make_repo(self, remote='https://github.com/acme/app.git', seed=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        git(root, 'init', '-q')
        git(root, 'config', 'user.name', 'Test')
        git(root, 'config', 'user.email', 'test@example.invalid')
        # A distinct seed file guarantees a distinct root-commit tree, so two
        # repos built back to back (same author/message/second) never
        # collide on identical commit bytes -> identical SHA.
        if seed:
            (root / '.seed').write_text(seed, encoding='utf-8')
            git(root, 'add', '.seed')
        git(root, 'commit', '--allow-empty', '-qm', 'init: ' + (seed or 'root'))
        if remote:
            git(root, 'remote', 'add', 'origin', remote)
        policy_path = root / '.specify/workflow.yml'
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(yaml.safe_dump(w.default_policy(True, True)), encoding='utf-8')
        return root

    def commit_all(self, root, message='fixture'):
        git(root, 'add', '-A')
        git(root, 'commit', '-qm', message)


class LegacyUpgradeTests(Harness):
    """A legacy (pre-1.8.0) checkpoint, which only ever recorded `repo_path`."""

    def test_legacy_checkpoint_from_another_path_loads_and_upgrades(self):
        root = self.make_repo()
        self.policy = copy.deepcopy(fixture_008.load()['policy'])
        self.root = root
        fixture.WorkflowTests.configure(self, superspec=True)  # so `migrate`'s doctor check passes
        git(root, 'switch', '-qc', fixture_008.BRANCH)
        original = fixture_008.materialise(root)  # repo_path is a foreign machine's path
        self.assertEqual(original['issue'].split('#')[0], 'acme/app')  # matches this repo's own remote
        self.commit_all(root, 'Materialise the anonymised 1.3.0 checkpoint')
        run = w.Run(root, fixture_008.FEATURE)

        # `load` is a pure read here: it accepts and upgrades in memory, but
        # writes nothing until a real mutating command saves.
        raw_before = run.path.read_bytes()
        state = run.load()
        self.assertIn('repo_identity', state)
        self.assertTrue(state['repo_identity']['remote'] or state['repo_identity']['root_commit'])
        self.assertEqual(run.path.read_bytes(), raw_before)

        # The next real write persists the upgrade and touches no receipt.
        # `repo_path` is refreshed, not dropped: 1.8.0+ never reads it, but
        # an older reader must not KeyError on a checkpoint this version writes
        # (round 1, finding 5).
        result = run.migrate('promote to 1.8.0 identity')
        self.assertEqual(result['migration']['invalidated'], [])
        saved = run.load()
        self.assertEqual(saved['repo_path'], str(root))
        self.assertEqual(saved['repo_identity'], state['repo_identity'])
        self.assertEqual(saved['receipts'], original['receipts'])

    def test_legacy_checkpoint_with_no_remote_is_refused_pointing_to_relocate(self):
        # Round 1, finding 1: a GitHub remote is required to verify the
        # checkpoint's bound issue against this repository, for a legacy
        # checkpoint exactly as for a new one; a repository with none
        # configured cannot load an existing checkpoint at all.
        root = self.make_repo(remote=None)
        git(root, 'switch', '-qc', fixture_008.BRANCH)
        fixture_008.materialise(root)
        self.commit_all(root)
        run = w.Run(root, fixture_008.FEATURE)
        raw_before = run.path.read_bytes()
        with self.assertRaisesRegex(w.WorkflowError, 'CHECKPOINT_IDENTITY_MISMATCH.*relocate'):
            run.load()
        self.assertEqual(run.path.read_bytes(), raw_before)  # never silently upgraded

    def test_legacy_checkpoint_without_a_reachable_commit_is_refused(self):
        # Codex round 1, finding 1: matching the issue to `origin` is not
        # proof of history. A recreated/unrelated clone that copied origin
        # must not adopt a legacy checkpoint whose recorded commits it does
        # not contain; only `relocate --allow-history-change` may.
        original = self.make_repo(seed='original-history')
        git(original, 'switch', '-qc', fixture_008.BRANCH)
        fixture_008.materialise(original)
        recorded = json.loads((original / fixture_008.FEATURE / 'workflow/checkpoint.json').read_text(encoding='utf-8'))
        self.assertRegex(recorded['head'], r'^[0-9a-f]{40}$')
        recreated = self.make_repo(seed='recreated-unrelated-history')  # same origin, unrelated commits
        git(recreated, 'switch', '-qc', fixture_008.BRANCH)
        fixture_008.materialise(recreated)
        path = recreated / fixture_008.FEATURE / 'workflow/checkpoint.json'
        state = json.loads(path.read_text(encoding='utf-8'))
        state['head'] = recorded['head']  # a commit only `original` has
        w.write(path, state)
        self.commit_all(recreated)
        run = w.Run(recreated, fixture_008.FEATURE)
        raw_before = run.path.read_bytes()
        with self.assertRaisesRegex(w.WorkflowError, r'CHECKPOINT_IDENTITY_MISMATCH.*--allow-history-change'):
            run.load()
        self.assertEqual(run.path.read_bytes(), raw_before)

    def test_a_reachable_sha_in_an_unrelated_field_is_not_a_history_signal(self):
        # Codex round 2: the proof was a recursive scan for any hex string, so
        # an unreachable `head` plus a reachable sha in some other field (a
        # fingerprint, a policy digest) was accepted. Only `head` and each
        # receipt's `head` count.
        root = self.make_repo()
        git(root, 'switch', '-qc', fixture_008.BRANCH)
        fixture_008.materialise(root)
        path = root / fixture_008.FEATURE / 'workflow/checkpoint.json'
        state = json.loads(path.read_text(encoding='utf-8'))
        reachable = git(root, 'rev-parse', 'HEAD').stdout.strip()
        state['head'] = '0' * 40
        state['policy_fingerprint'] = reachable
        first = next(iter(state['receipts'].values()))
        first['fingerprints'] = {**first.get('fingerprints', {}), 'x': reachable}
        first['unrelated'] = {'nested': [reachable]}
        w.write(path, state)
        self.commit_all(root)
        self.assertFalse(w.legacy_history_signal(root, state))
        with self.assertRaisesRegex(w.WorkflowError, r'CHECKPOINT_IDENTITY_MISMATCH.*--allow-history-change'):
            w.Run(root, fixture_008.FEATURE).load()

    def test_legacy_checkpoint_with_a_reachable_receipt_head_upgrades(self):
        root = self.make_repo()
        git(root, 'switch', '-qc', fixture_008.BRANCH)
        fixture_008.materialise(root)
        path = root / fixture_008.FEATURE / 'workflow/checkpoint.json'
        state = json.loads(path.read_text(encoding='utf-8'))
        state['head'] = '0' * 40  # unreachable
        first = next(iter(state['receipts'].values()))
        first['head'] = git(root, 'rev-parse', 'HEAD').stdout.strip()  # but a receipt's recorded head is reachable
        w.write(path, state)
        self.commit_all(root)
        self.assertIn('repo_identity', w.Run(root, fixture_008.FEATURE).load())

    def test_legacy_checkpoint_windows_and_posix_repo_path_forms_both_load(self):
        for repo_path in (r'C:\Users\dev\workspace\acme-app', '/home/dev/workspace/acme-app'):
            root = self.make_repo()
            git(root, 'switch', '-qc', fixture_008.BRANCH)
            fixture_008.materialise(root)
            path = root / fixture_008.FEATURE / 'workflow/checkpoint.json'
            state = json.loads(path.read_text(encoding='utf-8'))
            state['repo_path'] = repo_path
            w.write(path, state)
            self.commit_all(root)
            run = w.Run(root, fixture_008.FEATURE)
            loaded = run.load()  # must not raise, regardless of the path's OS form
            self.assertIn('repo_identity', loaded)


class SecurityTests(Harness):
    """A checkpoint from a different repository must still be refused."""

    def test_checkpoint_from_a_different_repository_is_refused(self):
        repo_a = self.make_repo(remote='https://github.com/acme/app.git', seed='repo-a')
        state = w.Run(repo_a, 'specs/001-example').start('acme/app#10')

        repo_b = self.make_repo(remote='https://github.com/other-org/other-app.git', seed='repo-b')
        w.write(repo_b / 'specs/001-example/workflow/checkpoint.json', state)
        run_b = w.Run(repo_b, 'specs/001-example')
        with self.assertRaisesRegex(w.WorkflowError, 'CHECKPOINT_IDENTITY_MISMATCH'):
            run_b.load()

    def test_checkpoint_from_a_repo_with_no_remote_and_unrelated_history_is_refused(self):
        # `start` itself requires a GitHub-style origin to bind an issue (an
        # existing, unrelated constraint), so a no-remote checkpoint is built
        # directly here rather than through `start`. With round 1, finding
        # 1's mandatory GitHub-remote check, this is refused before the
        # repo_identity comparison is even reached (both, independently,
        # require a remote here).
        repo_a = self.make_repo(remote=None, seed='repo-a')
        identity_a = w.repo_identity(repo_a)
        self.assertIsNone(identity_a['remote'])
        self.assertIsNotNone(identity_a['root_commit'])
        state = {'schema_version': w.SCHEMA, 'run_id': 'r' * 8, 'repo_identity': identity_a,
                 'branch': 'whatever', 'feature': 'specs/001-example', 'issue': 'acme/app#10',
                 'policy_digest': 'a' * 64, 'dependency_digest': 'b' * 64,
                 'policy': w.default_policy(True, True), 'commands': {}, 'receipts': {},
                 'generation': 0, 'active': None, 'status': 'in-progress'}

        repo_b = self.make_repo(remote=None, seed='repo-b')  # its own, unrelated history/root commit
        self.assertNotEqual(identity_a['root_commit'], w.repo_identity(repo_b)['root_commit'])
        w.write(repo_b / 'specs/001-example/workflow/checkpoint.json', state)
        run_b = w.Run(repo_b, 'specs/001-example')
        with self.assertRaisesRegex(w.WorkflowError, 'CHECKPOINT_IDENTITY_MISMATCH'):
            run_b.load(allow_branch_change=True)

    def test_foreign_legacy_checkpoint_bound_to_a_different_repo_is_refused(self):
        """Round 1, finding 1: a probe found this legacy checkpoint (bound
        to acme/app#10 by `fixture_008`) was accepted, and then re-saved,
        inside an unrelated repository (evil/other) whose own identity
        simply happened to resolve -- silently laundering it. The issue's
        repository must now be verified against this repository's own
        GitHub remote, closing that gap.
        """
        root = self.make_repo(remote='https://github.com/evil/other.git', seed='evil')
        git(root, 'switch', '-qc', fixture_008.BRANCH)
        original = fixture_008.materialise(root)
        self.assertEqual(original['issue'], fixture_008.ISSUE)
        self.assertEqual(original['issue'].split('#')[0], 'acme/app')
        self.commit_all(root, 'Materialise a foreign checkpoint')
        run = w.Run(root, fixture_008.FEATURE)
        raw_before = run.path.read_bytes()
        with self.assertRaisesRegex(w.WorkflowError, 'CHECKPOINT_IDENTITY_MISMATCH'):
            run.load()
        self.assertEqual(run.path.read_bytes(), raw_before)  # never silently upgraded/rebound

    def test_checkpoint_with_a_copied_remote_and_unrelated_history_is_refused_when_not_shallow(self):
        """Round 1, finding 4: two non-shallow local repositories, one with
        the other's `origin` URL simply copied into it, must not match on
        the remote alone -- the underlying histories are unrelated."""
        repo_a = self.make_repo(remote='https://github.com/acme/app.git', seed='repo-a')
        state = w.Run(repo_a, 'specs/001-example').start('acme/app#10')

        repo_c = self.make_repo(remote='git@github.com:acme/app.git', seed='repo-c-unrelated')
        w.write(repo_c / 'specs/001-example/workflow/checkpoint.json', state)
        run_c = w.Run(repo_c, 'specs/001-example')
        with self.assertRaisesRegex(w.WorkflowError, 'CHECKPOINT_IDENTITY_MISMATCH'):
            run_c.load()


    def test_a_tampered_root_commit_cannot_make_an_unrelated_clone_match(self):
        """Round 3: editing the recorded root commit to `HEAD` (or a branch
        name) must not get an unrelated clone with a copied origin accepted."""
        repo_a = self.make_repo(remote='https://github.com/acme/app.git', seed='repo-a')
        state = w.Run(repo_a, 'specs/001-example').start('acme/app#10')
        repo_c = self.make_repo(remote='git@github.com:acme/app.git', seed='repo-c-unrelated')
        branch = git(repo_c, 'branch', '--show-current').stdout.strip()
        for bad in ('HEAD', branch, '--foo'):
            tampered = copy.deepcopy(state)
            tampered['repo_identity']['root_commit'] = bad
            w.write(repo_c / 'specs/001-example/workflow/checkpoint.json', tampered)
            with self.assertRaisesRegex(w.WorkflowError, 'CHECKPOINT_IDENTITY_MISMATCH'):
                w.Run(repo_c, 'specs/001-example').load()


class CompatibilityTests(Harness):
    """Round 1, finding 5: `repo_path` is still written for an older reader."""

    def test_repo_path_is_still_written_by_start(self):
        root = self.make_repo(remote='https://github.com/acme/app.git')
        state = w.Run(root, 'specs/001-example').start('acme/app#10')
        self.assertIn('repo_path', state)
        self.assertEqual(state['repo_path'], str(root))
        # The exact condition a pre-1.8.0 Run.load() checked still holds,
        # so a checkpoint this version writes does not KeyError there.
        self.assertTrue(state['repo_path'] == str(root) and state['feature'] == 'specs/001-example')


class MergedUnrelatedHistoryTests(Harness):
    """Round 2, finding N4: merging in an unrelated history must not make
    `load` refuse a checkpoint whose original history is still fully
    present and reachable."""

    def test_checkpoint_survives_merging_in_an_older_unrelated_history(self):
        root = self.make_repo(remote='https://github.com/acme/app.git', seed='repo-a')
        state = w.Run(root, 'specs/001-example').start('acme/app#10')
        original_root_commit = state['repo_identity']['root_commit']

        # An unrelated repo whose one commit is dated well before repo_a's.
        unrelated = self.make_repo(remote=None, seed='unrelated')
        env = os.environ.copy()
        env['GIT_AUTHOR_DATE'] = env['GIT_COMMITTER_DATE'] = '2000-01-01T00:00:00'
        subprocess.run(['git', 'commit', '--amend', '--no-edit'], cwd=unrelated, env=env,
                       check=True, capture_output=True)
        older_root_commit = w.repo_identity(unrelated)['root_commit']
        self.assertNotEqual(older_root_commit, original_root_commit)

        subprocess.run(['git', 'fetch', '-q', str(unrelated)], cwd=root, check=True, capture_output=True)
        subprocess.run(['git', 'merge', '-q', '--allow-unrelated-histories', '-X', 'ours',
                        '-m', 'merge unrelated', 'FETCH_HEAD'], cwd=root, check=True, capture_output=True)

        # Confirm the drift this finding is about actually happened: the
        # repository's own root-commit pick changed to the older one.
        self.assertEqual(w.root_commit_sha(root), older_root_commit)

        loaded = w.Run(root, 'specs/001-example').load()  # must not raise
        self.assertEqual(loaded['issue'], 'acme/app#10')
        self.assertEqual(loaded['repo_identity']['root_commit'], original_root_commit)  # unchanged, never rewritten


class GithubRepositoryFormsTests(Harness):
    """Round 2, finding N1: `github_repository` must accept every valid
    GitHub remote form (any scheme, an embedded token, with or without
    `.git`), and every comparison against an issue's bound repository
    must be case-insensitive -- not just refuse cleanly, but actually
    accept these as the same repository."""

    def test_load_accepts_an_ssh_scheme_remote(self):
        root = self.make_repo(remote='ssh://git@github.com/acme/app.git')
        w.Run(root, 'specs/001-example').start('acme/app#10')
        loaded = w.Run(root, 'specs/001-example').load()
        self.assertEqual(loaded['issue'], 'acme/app#10')

    def test_load_accepts_a_token_userinfo_remote(self):
        root = self.make_repo(remote='https://x-access-token:ghs_secret@github.com/acme/app.git')
        w.Run(root, 'specs/001-example').start('acme/app#10')
        loaded = w.Run(root, 'specs/001-example').load()
        self.assertEqual(loaded['issue'], 'acme/app#10')

    def test_load_accepts_a_case_different_owner_repo(self):
        root = self.make_repo(remote='https://github.com/Acme/App.git')
        w.Run(root, 'specs/001-example').start('acme/app#10')
        loaded = w.Run(root, 'specs/001-example').load()
        self.assertEqual(loaded['issue'], 'acme/app#10')

    def test_relocate_does_not_treat_an_ssh_or_token_form_as_a_repository_rename(self):
        root = self.make_repo(remote='https://github.com/acme/app.git')
        w.Run(root, 'specs/001-example').start('acme/app#10')
        git(root, 'remote', 'set-url', 'origin', 'ssh://git@github.com/acme/app.git')
        run = w.Run(root, 'specs/001-example')
        preview = run.relocate('same repo, different URL form', preview=True)
        self.assertFalse(preview['repository_renamed'])
        self.assertTrue(preview['can_apply'])

    def test_relocate_does_not_treat_a_case_difference_as_a_repository_rename(self):
        root = self.make_repo(remote='https://github.com/acme/app.git')
        w.Run(root, 'specs/001-example').start('acme/app#10')
        git(root, 'remote', 'set-url', 'origin', 'https://github.com/Acme/App.git')
        run = w.Run(root, 'specs/001-example')
        preview = run.relocate('same repo, different case', preview=True)
        self.assertFalse(preview['repository_renamed'])
        self.assertTrue(preview['can_apply'])


class RelocateTests(Harness):
    """The explicit, logged rebind for a repository that legitimately moved."""

    def setUp(self):
        super().setUp()
        self.policy = copy.deepcopy(fixture_008.load()['policy'])
        self.root = self.make_repo(remote='https://github.com/acme/app.git')
        fixture.WorkflowTests.configure(self, superspec=True)
        git(self.root, 'switch', '-qc', fixture_008.BRANCH)
        self.original = fixture_008.materialise(self.root)
        self.feature = fixture_008.FEATURE
        self.commit_all(self.root, 'Materialise the anonymised 1.3.0 checkpoint')
        self.run = w.Run(self.root, self.feature)
        self.run.migrate('promote to 1.8.0 identity')  # records repo_identity for github.com/acme/app

    def rename_remote(self, url='https://github.com/acme-renamed/app.git'):
        git(self.root, 'remote', 'set-url', 'origin', url)
        return w.Run(self.root, self.feature)

    def test_a_renamed_remote_is_refused_until_relocate(self):
        run = self.rename_remote()
        with self.assertRaisesRegex(w.WorkflowError, 'CHECKPOINT_IDENTITY_MISMATCH'):
            run.load()

    def test_relocate_preview_and_apply_preserve_receipts_byte_for_byte(self):
        before = self.run.load()
        before_hash = hashlib.sha256(json.dumps(before['receipts'], sort_keys=True).encode()).hexdigest()

        # Renaming the org also changes the GitHub owner/repo the issue was
        # bound to, so this exercises --allow-repository-rename as well as
        # the identity rebind (see the branch-mismatch and repository-
        # rename tests below for each blocker in isolation).
        # --keep-issue-number: round 2, finding N2 requires an explicit
        # choice for a repository rename/transfer rather than assuming one.
        run = self.rename_remote()
        raw_before = run.path.read_bytes()
        preview = run.relocate('Org renamed acme -> acme-renamed', preview=True,
                               allow_repository_rename=True, keep_issue_number=True)
        self.assertTrue(preview['preview'])
        self.assertTrue(preview['can_apply'])
        self.assertEqual(preview['old_identity']['remote'], 'github.com/acme/app')
        self.assertEqual(preview['new_identity']['remote'], 'github.com/acme-renamed/app')
        self.assertTrue(preview['repository_renamed'])
        self.assertEqual(preview['old_repository'], 'acme/app')
        self.assertEqual(preview['new_repository'], 'acme-renamed/app')
        self.assertEqual(preview['new_issue'], 'acme-renamed/app#10')
        self.assertEqual(run.path.read_bytes(), raw_before)  # preview never writes

        result = run.relocate('Org renamed acme -> acme-renamed', allow_repository_rename=True,
                              keep_issue_number=True)
        self.assertTrue(result['relocated'])
        relocation = result['relocation']
        self.assertEqual(relocation['reason'], 'Org renamed acme -> acme-renamed')
        self.assertEqual(relocation['old_identity']['remote'], 'github.com/acme/app')
        self.assertEqual(relocation['new_identity']['remote'], 'github.com/acme-renamed/app')
        self.assertFalse(relocation['branch_rebound'])
        self.assertTrue(relocation['repository_renamed'])
        self.assertEqual(relocation['old_repository'], 'acme/app')
        self.assertEqual(relocation['new_repository'], 'acme-renamed/app')
        self.assertEqual(relocation['new_issue'], 'acme-renamed/app#10')

        after = run.load()  # now accepted under the new identity
        self.assertEqual(after['repo_identity']['remote'], 'github.com/acme-renamed/app')
        self.assertEqual(after['repo_path'], str(self.root))  # refreshed, still written (finding 5)
        self.assertEqual(after['issue'], 'acme-renamed/app#10')
        self.assertEqual(after['relocations'][-1], relocation)
        after_hash = hashlib.sha256(json.dumps(after['receipts'], sort_keys=True).encode()).hexdigest()
        self.assertEqual(before_hash, after_hash)
        self.assertEqual(after['receipts'], self.original['receipts'])

    def test_relocate_refused_on_a_branch_mismatch_unless_allowed(self):
        run = self.rename_remote()
        git(self.root, 'switch', '-qc', 'a-different-branch')
        run = w.Run(self.root, self.feature)

        preview = run.relocate('Org renamed', preview=True, allow_repository_rename=True, keep_issue_number=True)
        self.assertFalse(preview['can_apply'])
        self.assertFalse(preview['branch_matches'])
        self.assertTrue(any('CHECKPOINT_BRANCH_MISMATCH' in b for b in preview['blockers']))

        with self.assertRaisesRegex(w.WorkflowError, 'CHECKPOINT_BRANCH_MISMATCH'):
            run.relocate('Org renamed', allow_repository_rename=True, keep_issue_number=True)

        result = run.relocate('Org renamed', allow_branch_rebind=True, allow_repository_rename=True,
                              keep_issue_number=True)
        self.assertTrue(result['relocation']['branch_rebound'])
        self.assertEqual(result['relocation']['branch_to'], 'a-different-branch')
        self.assertEqual(run.load()['branch'], 'a-different-branch')

    def test_relocate_refused_when_the_bound_repository_changed_unless_allowed(self):
        """Round 1, finding 2: a probe used `relocate` itself to launder a
        checkpoint bound to acme/app#10 into an unrelated repository
        (evil/other) -- preview reported `can_apply: True`. `relocate` must
        block that the same way `load` would, unless the caller explicitly
        confirms the rename with `--allow-repository-rename` -- and (round
        2, finding N2) names the exact new issue explicitly, since a
        changed owner is exactly the fork case where the issue number
        cannot be assumed to carry over.
        """
        run = self.rename_remote('https://github.com/evil/other.git')

        preview = run.relocate('claiming this checkpoint', preview=True)
        self.assertFalse(preview['can_apply'])
        self.assertTrue(preview['repository_renamed'])
        self.assertEqual(preview['old_repository'], 'acme/app')
        self.assertEqual(preview['new_repository'], 'evil/other')
        self.assertTrue(any('REPOSITORY_CHANGED' in b for b in preview['blockers']))

        raw_before = run.path.read_bytes()
        with self.assertRaisesRegex(w.WorkflowError, 'REPOSITORY_CHANGED'):
            run.relocate('claiming this checkpoint')
        self.assertEqual(run.path.read_bytes(), raw_before)  # refused apply never writes

        # --allow-repository-rename alone is still not enough: without an
        # explicit issue choice this is blocked by RELOCATE_ISSUE_REQUIRED.
        with self.assertRaisesRegex(w.WorkflowError, 'RELOCATE_ISSUE_REQUIRED'):
            run.relocate('claiming this checkpoint', allow_repository_rename=True)

        result = run.relocate('claiming this checkpoint', allow_repository_rename=True, new_issue='evil/other#99')
        self.assertTrue(result['relocation']['repository_renamed'])
        self.assertEqual(result['relocation']['old_repository'], 'acme/app')
        self.assertEqual(result['relocation']['new_repository'], 'evil/other')
        self.assertEqual(result['relocation']['new_issue'], 'evil/other#99')
        self.assertEqual(run.load()['repo_identity']['remote'], 'github.com/evil/other')
        self.assertEqual(run.load()['issue'], 'evil/other#99')

    def test_relocate_apply_recomputes_from_a_fresh_read_under_the_lock(self):
        """Round 1, finding 2: `old_identity`/`branch_matches` used to be
        computed once before the lock was acquired. Relocating twice in a
        row on the same `Run` proves each apply re-reads the checkpoint
        fresh: the second call's `old_identity` must be the *first* call's
        `new_identity`, not anything cached from before either call.
        """
        run = self.rename_remote('https://github.com/acme-renamed-once/app.git')
        first = run.relocate('first move', allow_repository_rename=True, keep_issue_number=True)['relocation']
        self.assertEqual(first['old_identity']['remote'], 'github.com/acme/app')
        self.assertEqual(first['new_identity']['remote'], 'github.com/acme-renamed-once/app')

        git(self.root, 'remote', 'set-url', 'origin', 'https://github.com/acme-renamed-twice/app.git')
        run2 = w.Run(self.root, self.feature)
        second = run2.relocate('second move', allow_repository_rename=True, keep_issue_number=True)['relocation']
        self.assertEqual(second['old_identity']['remote'], first['new_identity']['remote'])
        self.assertEqual(second['new_identity']['remote'], 'github.com/acme-renamed-twice/app')

    def test_relocate_needs_an_acknowledgement_when_the_root_history_changed(self):
        """Codex round 1, finding 2: origin and issue still match but the
        recorded root commit is not this repository's (recreated history).
        `relocate` used to rebind that silently; it now needs
        `--allow-history-change`, and the record says so."""
        path = self.run.path
        state = json.loads(path.read_text(encoding='utf-8'))
        self.assertIs(state['repo_identity']['shallow'], False)
        state['repo_identity']['root_commit'] = 'b' * 40  # a history this repository never had
        w.write(path, state)
        run = w.Run(self.root, self.feature)
        with self.assertRaisesRegex(w.WorkflowError, 'CHECKPOINT_IDENTITY_MISMATCH'):
            run.load()

        preview = run.relocate('history recreated', preview=True)
        self.assertFalse(preview['can_apply'])
        self.assertTrue(preview['history_changed'])
        self.assertTrue(any('--allow-history-change' in b for b in preview['blockers']))
        raw_before = path.read_bytes()
        with self.assertRaisesRegex(w.WorkflowError, 'HISTORY_CHANGED.*--allow-history-change'):
            run.relocate('history recreated')
        self.assertEqual(path.read_bytes(), raw_before)

        result = run.relocate('history recreated', allow_history_change=True)
        self.assertTrue(result['relocation']['history_changed'])
        self.assertEqual(run.load()['relocations'][-1]['history_changed'], True)

    def test_relocate_records_history_unchanged_for_a_plain_rename(self):
        run = self.rename_remote()
        result = run.relocate('renamed', allow_repository_rename=True, keep_issue_number=True)
        self.assertIs(result['relocation']['history_changed'], False)

    def test_relocate_without_a_github_remote_is_refused_even_with_an_issue(self):
        """Codex round 1, finding 3: with no resolvable GitHub repository
        `--issue` alone let relocate write a success that `load` then
        refuses. Applying now requires a resolved GitHub repo."""
        git(self.root, 'remote', 'remove', 'origin')
        run = w.Run(self.root, self.feature)
        preview = run.relocate('no remote', preview=True, allow_repository_rename=True, new_issue='acme/app#10')
        self.assertFalse(preview['can_apply'])
        self.assertTrue(any('RELOCATE_GITHUB_REMOTE_REQUIRED' in b for b in preview['blockers']))
        raw_before = run.path.read_bytes()
        with self.assertRaisesRegex(w.WorkflowError, 'RELOCATE_GITHUB_REMOTE_REQUIRED'):
            run.relocate('no remote', allow_repository_rename=True, new_issue='acme/app#10')
        self.assertEqual(run.path.read_bytes(), raw_before)

    def test_relocate_issue_must_name_the_resolved_repository(self):
        run = self.rename_remote()
        with self.assertRaisesRegex(w.WorkflowError, 'RELOCATE_ISSUE_REPOSITORY_MISMATCH'):
            run.relocate('renamed', allow_repository_rename=True, new_issue='acme/app#10')

    def test_relocate_rejects_issue_options_when_the_repository_did_not_change(self):
        """Codex round 1, finding 6: `--issue` used to be silently ignored
        when nothing about the repository changed."""
        path = self.run.path
        state = json.loads(path.read_text(encoding='utf-8'))
        state['repo_identity']['root_commit'] = 'b' * 40  # only the history changed
        w.write(path, state)
        run = w.Run(self.root, self.feature)
        raw_before = path.read_bytes()
        for kwargs in ({'new_issue': 'acme/app#99'}, {'keep_issue_number': True}):
            with self.assertRaisesRegex(w.WorkflowError, 'RELOCATE_ISSUE_NOT_APPLICABLE'):
                run.relocate('same repo', allow_history_change=True, **kwargs)
            with self.assertRaisesRegex(w.WorkflowError, 'RELOCATE_ISSUE_NOT_APPLICABLE'):
                run.relocate('same repo', preview=True, allow_history_change=True, **kwargs)
        self.assertEqual(path.read_bytes(), raw_before)
        run.relocate('same repo', allow_history_change=True)  # without them it applies
        self.assertEqual(run.load()['issue'], 'acme/app#10')

    def test_a_failure_between_the_scope_source_and_checkpoint_writes_splits_nothing(self):
        """Codex round 1, finding 4: `scope-source.json` used to be written
        before the checkpoint save, so a failure in between left the pair
        split (scope rebound, checkpoint not)."""
        from unittest import mock
        run = self.rename_remote()
        source = self.root / self.feature / 'scope-source.json'
        source_before, checkpoint_before = source.read_bytes(), run.path.read_bytes()
        with mock.patch.object(w.Run, 'save', side_effect=OSError('disk full between the two writes')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                run.relocate('renamed', allow_repository_rename=True, keep_issue_number=True)
        self.assertEqual(source.read_bytes(), source_before)
        self.assertEqual(run.path.read_bytes(), checkpoint_before)
        self.assertEqual([p.name for p in source.parent.glob('scope-source.json.*.tmp')], [])
        # Nothing was half-applied, so the same relocate still succeeds.
        run.relocate('renamed', allow_repository_rename=True, keep_issue_number=True)
        self.assertEqual(json.loads(source.read_text(encoding='utf-8'))['repo'], 'acme-renamed/app')
        self.assertEqual(run.load()['issue'], 'acme-renamed/app#10')

    def test_relocate_requires_a_reason(self):
        run = self.rename_remote()
        with self.assertRaisesRegex(w.WorkflowError, 'RELOCATE_REASON_REQUIRED'):
            run.relocate('   ')

    def test_relocate_repository_rename_never_assumes_the_issue_number(self):
        """Round 2, finding N2: --allow-repository-rename on its own must
        never auto-rebind the issue -- a rename/transfer keeps the same
        number, but a fork's numbering is independent, and there is no
        offline way to tell the two apart. Either explicit option works;
        passing both is refused; --issue must name the resolved repository.
        """
        run = self.rename_remote()  # acme/app -> acme-renamed/app

        with self.assertRaisesRegex(w.WorkflowError, 'RELOCATE_ISSUE_REQUIRED'):
            run.relocate('renamed', allow_repository_rename=True)

        with self.assertRaisesRegex(w.WorkflowError, 'RELOCATE_ISSUE_OPTIONS_CONFLICT'):
            run.relocate('renamed', allow_repository_rename=True, keep_issue_number=True,
                        new_issue='acme-renamed/app#10')

        with self.assertRaisesRegex(w.WorkflowError, 'RELOCATE_ISSUE_REPOSITORY_MISMATCH'):
            run.relocate('renamed', allow_repository_rename=True, new_issue='someone-else/app#1')

        result = run.relocate('renamed', allow_repository_rename=True, new_issue='acme-renamed/app#42')
        self.assertEqual(result['relocation']['new_issue'], 'acme-renamed/app#42')
        self.assertEqual(run.load()['issue'], 'acme-renamed/app#42')

    def test_start_after_a_legitimate_rename_succeeds(self):
        """Round 2, finding N3: relocate rebinds the checkpoint's `issue`
        but used to leave `scope-source.json` naming the old repository,
        so a later `start` for the same (now-rebound) issue failed
        FEATURE_BINDING_MISMATCH against it. relocate must rebind
        `scope-source.json` in the same locked write as the checkpoint.
        """
        run = self.rename_remote()
        result = run.relocate('Org renamed acme -> acme-renamed', allow_repository_rename=True,
                              keep_issue_number=True)
        new_issue = result['relocation']['new_issue']
        self.assertEqual(new_issue, 'acme-renamed/app#10')
        source = json.loads((self.root / self.feature / 'scope-source.json').read_text(encoding='utf-8'))
        self.assertEqual(source, {'repo': 'acme-renamed/app', 'issue': 10})

        # This used to fail FEATURE_BINDING_MISMATCH against a
        # scope-source.json still naming acme/app.
        resumed = w.Run(self.root, self.feature).start(new_issue)
        self.assertEqual(resumed['issue'], new_issue)

    def test_relocate_refused_inside_a_delegated_worker_context(self):
        run = self.rename_remote()
        os.environ['SANDUQ_DELEGATED_RUN'] = 'run-1'
        try:
            with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_WORKER_CONTEXT'):
                run.relocate('Org renamed', preview=True)
        finally:
            os.environ.pop('SANDUQ_DELEGATED_RUN', None)

    def test_relocate_refused_inside_a_delegated_orchestrator_context(self):
        run = self.rename_remote()
        os.environ['SANDUQ_DELEGATED_ROLE'] = 'orchestrator'
        os.environ['SANDUQ_DELEGATED_FEATURE'] = self.feature
        try:
            with self.assertRaisesRegex(w.WorkflowError, 'DELEGATION_WORKER_CONTEXT'):
                run.relocate('Org renamed', preview=True)
        finally:
            os.environ.pop('SANDUQ_DELEGATED_ROLE', None)
            os.environ.pop('SANDUQ_DELEGATED_FEATURE', None)


if __name__ == '__main__':
    unittest.main()
