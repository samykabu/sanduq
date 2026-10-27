"""Repository and checkpoint identity: the GitHub repository, root commit, remote and issue bindings."""
from __future__ import annotations

import re
import unicodedata
import sanduq_remote
import yaml
from sanduq_remote import normalize_remote_url, same_github_repository
from wf_core import WorkflowError, require, read, run_git, git_ok, git, _memo


def github_repository(root):
    """The bound GitHub repository (`owner/repo`) of this repository's own
    `origin` remote, in whatever form it is written -- any scheme, an
    embedded token or other userinfo, the bare `git@host:path` shorthand,
    with or without a trailing `.git` -- because it is derived from the
    same `normalize_remote_url` the portable identity uses (round 2,
    finding N1: the previous ad-hoc regex accepted only two literal forms
    and rejected, for example, `ssh://git@github.com/acme/app` and a
    token URL like `https://x-access-token:TOKEN@github.com/acme/app`).

    Case is preserved, not folded here: GitHub repository names are not
    case sensitive, so compare the result with `same_github_repository`,
    never `==`.
    """
    remote = origin_url(root)
    require(remote is not None, 'GIT_ERROR: no remote.origin.url in ' + str(root) + '; Sanduq binds issues of the '
            '"origin" remote. Check "git remote -v", then add it with "git remote add origin '
            'https://github.com/<owner>/<repo>.git"')
    slug = sanduq_remote.github_slug(remote)
    require(slug, 'GITHUB_REMOTE_REQUIRED')
    return slug


def previous_branch(root):
    """The branch checked out immediately before the current one, via Git's own
    reflog-backed `@{-1}` shorthand -- the target the feature branch forked
    from, captured once at Start before any later checkout can shadow it.

    Best-effort: None on a shallow or single-branch checkout, a detached HEAD
    with no prior checkout in this reflog, or any other Git failure.
    """
    result = run_git(root, 'rev-parse', '--abbrev-ref', '@{-1}', text=True, encoding='utf-8')
    value = result.stdout.strip()
    return value if result.returncode == 0 and value and value != '@' else None


def normalized_remote(root):
    """The normalised `origin` URL, or None when no remote is configured.

    Never raises: a repository with no remote (a fresh `git init`, a
    tarball checkout, a throwaway CI scratch clone) is a supported, if
    less strongly identified, state -- see `repo_identity`.
    """
    url = origin_url(root)
    return normalize_remote_url(url) if url else None


def origin_url(root):
    """The raw `remote.origin.url`, or None when it is not configured (memoised per operation)."""
    return _memo('origin', root, lambda: sanduq_remote.origin_url(root))


def root_commit_sha(root):
    """The repository's earliest commit reachable from HEAD, or None when it
    cannot be resolved (no commits yet).

    Caveat, by design not worked around: a *shallow* clone's shallow boundary
    commit has no parents Git can see locally, so it is indistinguishable
    from a genuine root commit here. This is why `repo_identity` treats the
    root commit as a fallback used only when neither side has a remote --
    a shallow CI checkout of a repository that has a remote is identified by
    that remote instead, so the truncated history never matters there.
    """
    def walk():
        result = run_git(root, 'rev-list', '--max-parents=0', '--reverse', 'HEAD', text=True, encoding='utf-8')
        if result.returncode != 0:
            return None
        shas = [line for line in result.stdout.split() if line]
        # Reverse chronological order puts the true earliest root first; with
        # more than one root (unrelated histories merged -- rare), that first
        # entry is still a deterministic, reproducible choice.
        return shas[0] if shas else None
    return _memo('root_commit', root, walk)


def is_shallow_clone(root):
    """True/False, or None when Git cannot say (an old Git, or any other
    failure -- treated as "don't know", never as a mismatch)."""
    def ask():
        result = run_git(root, 'rev-parse', '--is-shallow-repository', text=True, encoding='utf-8')
        return {'true': True, 'false': False}.get(result.stdout.strip()) if result.returncode == 0 else None
    return _memo('shallow', root, ask)


def repo_identity(root):
    """This repository's portable identity: the normalised `origin` remote
    and/or the root commit SHA -- never an absolute path, which is the
    checkpoint-identity design bug this replaces (a path is machine- and
    clone-specific; a remote URL and a commit SHA are not). Also records
    whether this clone is shallow, which `identity_matches` uses -- never
    an identity signal by itself, only a reason to skip the extra check it
    would otherwise make.
    """
    return {'remote': normalized_remote(root), 'root_commit': root_commit_sha(root), 'shallow': is_shallow_clone(root)}


def current_identity(root, recorded):
    """`repo_identity(root)` for comparison with `recorded`. A recorded root commit still reachable from HEAD stands
    in for the current one, which `identity_matches` accepts either way, so the full-history `rev-list` runs only
    when one `merge-base --is-ancestor` cannot answer."""
    if root_commit_still_reachable(root, recorded.get('root_commit')):
        return {'remote': normalized_remote(root), 'root_commit': recorded['root_commit'],
                'shallow': is_shallow_clone(root)}
    return repo_identity(root)


def root_commit_still_reachable(root, commit_sha):
    """Whether `commit_sha` (a previously recorded root commit) is still an
    ancestor of (or equal to) the current HEAD in the repository at `root`
    (round 2, finding N4). Merging in an unrelated history
    (`git merge --allow-unrelated-histories`) adds another root commit
    reachable from HEAD, often older, which can change which one
    `root_commit_sha`'s deterministic pick returns even though this is
    still, genuinely, the same repository: its original history is still
    fully present and reachable, just no longer the sole root. Checking
    ancestry instead of re-deriving a single "the" root commit accepts
    exactly that case without weakening the refusal of a repository that
    never shared this history at all -- an unrelated commit is never an
    ancestor of this HEAD.
    """
    # The value comes from a checkpoint file anyone can edit: only a full hex
    # object id is ever handed to git, never `HEAD`, a branch name (either
    # would be "reachable" from an unrelated clone) or a dash-prefixed value
    # (read as an option). `^{commit}` additionally refuses a non-commit object.
    if not isinstance(commit_sha, str) or not re.fullmatch(r'[0-9a-f]{40,64}', commit_sha):
        return False
    return git_ok(root, 'merge-base', '--is-ancestor', commit_sha + '^{commit}', 'HEAD')


def same_remote(a, b):
    """Equality of two normalised remotes. GitHub owner/repo names are not case
    sensitive, so for github.com the comparison ignores case (a stored
    `github.com/acme/app` matches an origin now written `github.com/Acme/App`);
    every other host compares exactly, since some hosts are case sensitive."""
    if a == b:
        return True
    return bool(a) and bool(b) and a.lower().startswith(('github.com/', 'github.com:')) and a.lower() == b.lower()


def identity_matches(recorded, current, current_root=None):
    """Whether `current` may be treated as the same repository as `recorded`.

    The remote is authoritative whenever both sides have one: two unrelated
    repositories are not expected to share a normalised remote, and relying
    on it alone (rather than also requiring the root commit to match) is
    what lets a shallow CI checkout -- whose visible root-commit history is
    truncated at the shallow boundary, not the repository's true root --
    match its own origin without a spurious CHECKPOINT_IDENTITY_MISMATCH.

    A shared remote is still just local Git config, spoofable by whoever
    controls the working tree (see the README's threat model); when both
    sides are confidently *not* shallow (`shallow is False`, not merely
    absent or unknown -- a legacy identity or an old Git that could not say
    stays lenient), the root commit is also required to match, catching a
    remote that was simply copied into an unrelated clone. `shallow` absent
    on either side (a legacy `repo_identity` predating this check) never
    makes a previously-accepted checkpoint newly refused. When the root
    commits differ and `current_root` (the live repository to check
    against) is given, the recorded one is also accepted if it is still
    reachable there (`root_commit_still_reachable`, round 2, finding N4)
    rather than refusing outright -- `current_root` is omitted by pure
    dict-level callers (e.g. unit tests with no real repository to check
    against), which keeps this exact-match-only, as before.

    The root commit is used as the sole fallback only when *neither* side
    has a remote (a repo with no `origin` configured on both ends); both
    must resolve one and it must be equal or (with `current_root`) still
    reachable. Every other combination -- one side has a remote and the
    other does not, or neither side can resolve any signal at all -- is
    refused. That refusal is deliberate: a fork, a renamed remote or a
    migrated org all change the remote (and often keep the same root
    commit), so accepting a root-commit match on its own would silently
    accept exactly the cases the design calls for routing through the
    reviewed, logged `relocate` command instead.
    """
    def root_commit_matches(recorded_root):
        if not recorded_root:
            return False
        if recorded_root == current.get('root_commit'):
            return True
        return current_root is not None and root_commit_still_reachable(current_root, recorded_root)

    if recorded.get('remote') and current.get('remote'):
        if not same_remote(recorded['remote'], current['remote']):
            return False
        if recorded.get('shallow') is False and current.get('shallow') is False:
            return root_commit_matches(recorded.get('root_commit'))
        return True
    if not recorded.get('remote') and not current.get('remote'):
        return root_commit_matches(recorded.get('root_commit'))
    return False


def legacy_history_signal(root, state):
    """Whether a pre-1.8.0 checkpoint records a commit still reachable from
    HEAD (Codex round 1, finding 1). A legacy checkpoint has no portable
    identity, only the `head` every `save()` recorded (plus any receipt
    `head` a 1.6.0+ receipt carries), and
    a full-hex commit id that is an ancestor of this repository's HEAD is
    the one verifiable proof on file that this history is the one the
    checkpoint was written in. Matching the issue to `origin` alone proves
    nothing: origin is local Git config, so a recreated or unrelated clone
    that copies it would otherwise adopt any checkpoint for that issue.
    """
    # Only the fields 1.7.0 defines as a commit id are read, never a
    # recursive scan: an unrelated hex string (a fingerprint, a policy digest)
    # that happens to name a reachable commit is not a history signal. They
    # are the top-level `head` (written by every `save()`) and each receipt's
    # `head` (`receipt['head']`, recorded by the verify/review/ready stages).
    candidates = [state.get('head')]
    receipts = state.get('receipts')
    if isinstance(receipts, dict):
        candidates.extend(r.get('head') for r in receipts.values() if isinstance(r, dict))
    return any(root_commit_still_reachable(root, sha) for sha in dict.fromkeys(candidates)
               if isinstance(sha, str))


def verify_checkpoint_identity(root, state, relative):
    """The single identity gate for a checkpoint, shared by `Run.load` and
    the scope extension's `bound_claim` so both refuse the same things.
    Raises `WorkflowError` on any refusal. Returns the `repo_identity` to
    adopt for a legacy checkpoint (which the caller records), else None.
    """
    require_issue_repository_binding(root, state, relative)
    if 'repo_identity' in state:
        recorded = state['repo_identity']
        require(isinstance(recorded, dict) and identity_matches(recorded, current_identity(root, recorded),
                                                                current_root=root),
                'CHECKPOINT_IDENTITY_MISMATCH: this checkpoint belongs to a different repository. If this is '
                'the same project relocated (a fork, a renamed remote, a migrated org), run: workflow.py '
                'relocate --feature ' + relative + ' --reason "<why>"')
        return None
    # A pre-1.8.0 checkpoint recorded only the absolute `repo_path` it was
    # started from, which is machine- and clone-specific and is never
    # compared (that comparison was the checkpoint-identity design bug). It
    # is accepted once this repository's own identity can be established
    # AND the checkpoint's recorded history is verifiably this repository's
    # (`legacy_history_signal`); otherwise only an explicit, logged
    # `relocate --allow-history-change` may adopt it.
    current = repo_identity(root)
    require(current['remote'] or current['root_commit'],
            'CHECKPOINT_IDENTITY_UNRESOLVABLE: this repository has no remote and no resolvable root '
            'commit, so a legacy checkpoint cannot be safely accepted here')
    require(legacy_history_signal(root, state),
            'CHECKPOINT_IDENTITY_MISMATCH: this legacy checkpoint records no commit that is reachable from '
            'this repository HEAD, so it cannot be verified as belonging to this history. If it is the same '
            'project with rewritten or recreated history, run: workflow.py relocate --feature ' + relative +
            ' --allow-history-change --reason "<why>"')
    return current


def root_history_changed(root, state, current):
    """Whether the checkpoint's recorded history is no longer this
    repository's (Codex round 1, finding 2). `identity_matches` ignores the
    root commit unless both sides are confidently non-shallow, and accepts
    one that is still reachable; when the recorded root is neither equal nor
    reachable on a non-shallow clone, or a legacy checkpoint records no
    reachable commit, the history is a different one -- a recreated or
    unrelated repository that merely shares the remote and issue. `relocate`
    must not rebind such a checkpoint without an explicit acknowledgement.
    """
    recorded = state.get('repo_identity')
    if isinstance(recorded, dict):
        old_root, new_root = recorded.get('root_commit'), current.get('root_commit')
        if recorded.get('shallow') is False and current.get('shallow') is False and old_root and new_root:
            return not (old_root == new_root or root_commit_still_reachable(root, old_root))
        return False
    return not legacy_history_signal(root, state)


def require_issue_repository_binding(root, state, relative):
    """The checkpoint's bound issue must name *this* repository's own GitHub
    remote -- the same binding `start` (see below) and the scope
    extension's `bound_claim` (`workflow_policy.py`) already require, and
    for the same reason: `repo_identity`'s remote/root-commit match is only
    ever as strong as this repository's own, locally-editable Git config
    (round 1, finding 1). A *legacy* checkpoint has no portable
    `repo_identity` at all to check against, so without this, a legacy
    checkpoint bound to some other repository's issue was accepted by
    almost any repository whose own identity happened to resolve at all --
    then silently rebound to it on the next write. Applies to a new-style
    checkpoint too, for the same defence in depth.

    Fails closed when there is no GitHub remote to check against at all
    (a repo with no `origin`, or one on a non-GitHub host): the binding
    cannot be verified, so it is refused rather than trusted, and pointed
    at `relocate` -- which raises its own, explicit, logged version of
    this same check (`_relocate_repository_binding`) rather than silently
    trusting a caller who supplies `--allow-repository-rename`.
    """
    try:
        current_repo = github_repository(root)
    except WorkflowError:
        raise WorkflowError(
            'CHECKPOINT_IDENTITY_MISMATCH: this repository has no GitHub remote, so the checkpoint\'s bound '
            'issue (' + state['issue'] + ') cannot be verified against it. If this is the same project '
            'relocated (a fork, a renamed remote, a migrated org), run: workflow.py relocate --feature ' +
            relative + ' --reason "<why>"')
    require(same_github_repository(state['issue'].split('#')[0], current_repo),
            'CHECKPOINT_IDENTITY_MISMATCH: this checkpoint is bound to ' + state['issue'].split('#')[0] +
            ', not this repository (' + current_repo + '). If this is the same project relocated (a fork, a '
            'renamed remote, a migrated org), run: workflow.py relocate --feature ' + relative + ' --reason "<why>"')


def issue_identity(root, issue, gh=None):
    """Derive a stable safe initial path and branch from the bound GitHub issue."""
    require(re.fullmatch(r'[1-9]\d*', str(issue)), 'ISSUE_NUMBER_REQUIRED')
    repo = github_repository(root)
    if gh is None:
        from decisions import GitHub
        gh = GitHub()
    # AHMED-13: a fork's issues live upstream, so binding #n on the fork would bind the wrong issue.
    origin = gh.api(f'repos/{repo}') or {}
    require(not origin.get('fork'), 'ORIGIN_IS_FORK: the "origin" remote ' + repo + ' is a fork of '
            + str((origin.get('parent') or {}).get('full_name') or 'another repository') + ', whose issues are not '
            'on the fork. Sanduq binds issues of "origin" only: clone the parent repository and run Scope there '
            '(check "git remote -v")')
    item = gh.api(f'repos/{repo}/issues/{issue}')
    require(item.get('number') == int(issue) and 'pull_request' not in item,
            'GITHUB_ISSUE_REQUIRED: #' + str(issue) + ' is not an issue of ' + repo + ' (the "origin" remote, '
            '"git remote get-url origin"); it is missing or a pull request')
    title = unicodedata.normalize('NFKC', item.get('title', '')).casefold()
    slug = re.sub(r'[^\w]+', '-', title, flags=re.UNICODE).strip('-_')[:56].strip('-_') or 'issue'
    name = str(issue) + '-' + slug
    require(git_ok(root, 'check-ref-format', '--branch', name), 'ISSUE_TITLE_UNSAFE_FOR_BRANCH')
    return {'issue': repo + '#' + str(issue), 'title': item['title'],
            'feature': 'specs/' + name, 'branch': name}


def prepare_issue(root, issue, gh=None):
    """Reserve issue-derived identity and create a branch only without a Git hook."""
    identity = issue_identity(root, issue, gh)
    matches = [read(path, {}) for path in (root / 'specs').glob('*/workflow/checkpoint.json')
               if read(path, {}).get('issue') == identity['issue']]
    require(len(matches) <= 1, 'ISSUE_HAS_MULTIPLE_WORKFLOW_FEATURES')
    if matches:
        saved = matches[0]
        return {**identity, 'feature': saved['feature'], 'branch': saved['branch'],
                'branch_owner': 'existing-run'}
    checkpoint = root / identity['feature'] / 'workflow/checkpoint.json'
    if checkpoint.is_file():
        saved = read(checkpoint, {})
        require(saved.get('issue') == identity['issue'], 'ISSUE_IDENTITY_CONFLICT')
        return {**identity, 'branch': saved['branch'], 'branch_owner': 'existing-run'}
    require(not (root / identity['feature']).exists(), 'ISSUE_FEATURE_PATH_OCCUPIED')
    hooks = yaml.safe_load((root / '.specify/extensions.yml').read_text(encoding='utf-8-sig')) if (
        root / '.specify/extensions.yml').is_file() else {}
    git_hook = any(hook.get('extension') == 'git' and hook.get('command') == 'speckit.git.feature'
                   and hook.get('enabled') is True for hook in (hooks or {}).get('hooks', {}).get('before_specify', []))
    if git_hook:
        return {**identity, 'branch_owner': 'git-hook'}
    current = git(root, 'branch', '--show-current')
    require(current, 'DETACHED_HEAD_UNSUPPORTED')
    if current != identity['branch']:
        exists = git_ok(root, 'show-ref', '--verify', '--quiet', 'refs/heads/' + identity['branch'])
        require(not exists, 'ISSUE_BRANCH_EXISTS: inspect its owner before switching')
        git(root, 'switch', '-c', identity['branch'])
    return {**identity, 'branch_owner': 'sanduq'}
