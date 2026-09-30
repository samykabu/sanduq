#!/usr/bin/env python3
"""Sanduq workflow state machine. Commands dispatch agents; this runtime never simulates them."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import unicodedata
import urllib.parse
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# Also supports importlib loading directly from the canonical source tree.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sanduq_hash import eol_drift, portable_files
import sanduq_ci
import skill_inventory
import source_key as sk

import yaml
from packaging.specifiers import SpecifierSet
from packaging.version import Version

SCHEMA = 1
RANGES = {'scope': '>=1.4,<2', 'assure': '>=2.2,<3', 'user-manual': '>=1.2,<2',
          'pr': '>=4.1,<5', 'superspec': '>=1.0.2,<2', 'project': '>=2.1,<3'}
BASE_STAGES = ['scope', 'specify', 'clarify', 'plan', 'tasks', 'qa_analyze',
               'manual_analyze', 'analyze', 'taskstoissues', 'execute', 'verify',
               'review', 'qa_document', 'manual_update', 'ready', 'pr']
COMMANDS = {'scope': 'speckit.scope.run', 'specify': 'speckit.specify',
            'clarify': 'speckit.clarify', 'plan': 'speckit.plan', 'tasks': 'speckit.tasks',
            'qa_analyze': 'speckit.assure.analyze', 'manual_analyze': 'speckit.user-manual.analyze',
            'analyze': 'speckit.analyze', 'taskstoissues': 'speckit.taskstoissues',
            'execute': 'speckit.implement', 'qa_document': 'speckit.assure.document',
            'manual_update': 'speckit.user-manual.update', 'pr': 'speckit.pr.generate',
            'verify': 'workflow:verification', 'review': 'workflow:review', 'ready': 'workflow:gates'}
CORE_INPUTS = ['spec.md', 'plan.md', 'tasks.md', 'data-model.md', 'research.md', 'quickstart.md']
# Receipt input roles. A receipt without `input_roles` is read as all-dependency.
INPUT_ROLES = ('dependency', 'consulted')
# Keys of the optional `receipts` policy section and their types.
RECEIPT_POLICY_KEYS = {'require_input_roles': bool}
AMENDMENT_ASSESSMENTS = ('unchanged', 'changed')
# Receipts whose conclusion rests on earlier evidence; a `changed` amendment stales them.
AMENDMENT_DEPENDENTS = ('verify', 'review', 'ready')
# Receipt fields only the runtime writes; a submitted receipt may not carry them.
RUNTIME_RECEIPT_FIELDS = ('amendments', 'stale', 'head', 'source_key', 'ci_evidence', 'diff_reviewed',
                          'revalidations', 'delegation_ledger_trust')
# Stages whose receipts also inventory source (`source_fingerprints`) and record `head` and `source_key`.
SOURCE_STAGES = ('verify', 'review', 'ready')
# How recovery recipes name the runtime in a consumer project.
WORKFLOW_SCRIPT = 'python .specify/extensions/workflow/scripts/workflow.py'
# Where the workflow package lands inside a consumer project, so `claim`'s `reference`
# field is directly usable by a reader without knowing the installed layout separately.
WORKFLOW_PACKAGE_PREFIX = '.specify/extensions/workflow/'
# Where `claim` tells the dispatcher to read this stage's own instructions, project-relative
# (matches the installed layout, e.g. `.specify/extensions/workflow/skills/workflow/
# references/stage-scope.md`). One file per BASE_STAGES entry; see SKILL.md's stage
# reference map and extensions/workflow/tests/test_workflow.py for the completeness check.
def stage_reference(stage):
    return WORKFLOW_PACKAGE_PREFIX + 'skills/workflow/references/stage-' + stage + '.md'


class WorkflowError(Exception):
    pass


def require(value, message):
    if not value:
        raise WorkflowError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


POLICY_DIGEST_VERSION = 3
# Sections that place or route work without changing what feature evidence means.
OPERATIONAL_POLICY = ('ci', 'delegation')


def delivery_digest(policy):
    """CI placement and delegation routing do not change the meaning of feature-stage evidence."""
    return digest({key: value for key, value in policy.items() if key not in OPERATIONAL_POLICY})


def checkpoint_policy_digest(state, policy):
    """Express the current policy in the digest format the checkpoint recorded.

    Version 2 excluded only CI and pre-split checkpoints hashed the full policy.
    Both hashed whatever delegation section their policy snapshot carried (none
    before delegation existed), so that section is reused here: enabling,
    disabling or rerouting delegation mid-lifecycle is never a semantic change.
    """
    version = state.get('policy_digest_version')
    if version == POLICY_DIGEST_VERSION:
        return delivery_digest(policy)
    shaped = {key: value for key, value in policy.items()
              if key != 'delegation' and not (version == 2 and key == 'ci')}
    snapshot = state.get('policy')
    if isinstance(snapshot, dict) and 'delegation' in snapshot:
        shaped['delegation'] = snapshot['delegation']
    return digest(shaped)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temp, path)


def inside(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), 'PATH_OUTSIDE_PROJECT: ' + str(relative))
    return path


def git(root, *args):
    result = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, encoding='utf-8')
    require(result.returncode == 0, 'GIT_ERROR: ' + result.stderr.strip())
    return result.stdout.strip()


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
    remote = git(root, 'config', '--get', 'remote.origin.url')
    normalized = normalize_remote_url(remote)
    match = re.fullmatch(r'github\.com(?::\d+)?/([^/]+/[^/]+)', normalized)
    require(match, 'GITHUB_REMOTE_REQUIRED')
    return match[1]


def same_github_repository(a, b):
    """Case-insensitive equality for two `owner/repo` strings, either of
    which may be `None` (no GitHub remote resolved at all). GitHub
    repository names are not case sensitive, but a checkpoint's `issue`
    field and this repository's own remote may disagree only in case
    (round 2, finding N1) -- comparing them with `==` would treat that as
    a different repository and refuse, or (in `relocate`) treat it as a
    rename that needs an explicit new issue.
    """
    return a is not None and b is not None and a.lower() == b.lower()


def previous_branch(root):
    """The branch checked out immediately before the current one, via Git's own
    reflog-backed `@{-1}` shorthand -- the target the feature branch forked
    from, captured once at Start before any later checkout can shadow it.

    Best-effort: None on a shallow or single-branch checkout, a detached HEAD
    with no prior checkout in this reflog, or any other Git failure.
    """
    result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', '@{-1}'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8')
    value = result.stdout.strip()
    return value if result.returncode == 0 and value and value != '@' else None


def _strip_dotgit(path):
    """Drop one trailing `.git` (case-insensitively -- real hosts vary), once."""
    return path[:-4] if path[-4:].lower() == '.git' else path


def _normalize_path_remote(path):
    """A local-filesystem remote (a bare path, `file://`, a Windows drive path):
    fold separator style only, never case -- these are real filesystem paths,
    and folding case could merge two distinct case-sensitive paths into one
    identity (round 1, finding 3). The one exception is a leading Windows
    drive letter (`C:`/`c:`), which is folded to lower case: unlike the rest
    of the path, a drive letter genuinely is case-insensitive on Windows,
    so `C:/repos/App` and `c:/repos/App` name the same location (round 2,
    LOW, optional).
    """
    path = path.replace('\\', '/')
    while len(path) > 1 and path.endswith('/'):
        path = path[:-1]
    path = _strip_dotgit(path)
    drive = re.match(r'[A-Za-z]:(?=/|$)', path)
    if drive:
        path = drive.group().lower() + path[drive.end():]
    return path


def normalize_remote_url(url):
    """Fold scheme, credential, case and port-vs-path differences that name
    the same remote (round 1, finding 3 -- see the earlier revision's
    docstring for the original rationale, which still holds for the host
    and case handling below).

    ``https://user:pass@Github.com/Acme/App.git``, ``git@github.com:Acme/App.git``
    and ``ssh://git@github.com/Acme/App/`` all normalise to ``github.com/Acme/App``:
    the scheme and any embedded credentials carry no identity, the host is
    case-insensitive by DNS convention (so it is lowered, and a trailing
    root ``.`` is folded), and a trailing ``.git``/``/`` is cosmetic. The
    repository *path* keeps its case.

    A real URL is parsed with `urllib.parse` rather than an ad-hoc regex:
    its `.hostname`/`.port` correctly separate a userinfo trick
    (``https://github.com@evil.com/...`` is ``evil.com``, not
    ``github.com``) and correctly reject a malformed one
    (``https://evil.com:github.com/...`` has a non-numeric "port" and is
    refused down to the opaque, unfolded fallback below -- never
    misread as a path). An explicit, resolvable port is kept as
    ``host:port``, distinct from a URL with no port at all: an SSH URL's
    ``:22`` is a port, never the start of the path, which a shared regex
    for both the URL and the legacy SCP-shorthand forms could not tell
    apart from a path that happens to start with a numeric segment (the
    ``ssh://host:22/team/app`` vs ``https://host/22/team/app`` collision
    this replaces). Anything with no scheme and no resolvable host --
    SCP shorthand (``[user@]host:path``, but never a single-letter
    "host" immediately followed by ``/`` or ``\\``, which is a Windows
    drive letter, not a hostname) or a bare local path -- falls through to
    ``_normalize_path_remote``, which never folds case.
    """
    url = url.strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == 'file':
        return _normalize_path_remote(parts.path or url)
    if parts.scheme and parts.netloc:
        try:
            host = parts.hostname
            if host is None:
                raise ValueError('no host')
            host = host.rstrip('.').lower()
            port = parts.port
            # A port equal to its scheme's well-known default carries no
            # identity (round 2, LOW, optional): ssh://host:22/... and
            # ssh://host/... (or https://host:443/...) name the same thing.
            if port and port != {'ssh': 22, 'https': 443, 'http': 80}.get(parts.scheme):
                host += ':' + str(port)
            return host + '/' + _strip_dotgit(parts.path.strip('/'))
        except ValueError:
            pass  # malformed (e.g. a non-numeric port): fall through, unfolded
    if '://' not in url:
        scp = re.fullmatch(r'(?:[^@/\s]*@)?([^@/:\s]+):(.+)', url)
        if scp:
            host, path = scp.groups()
            if not (len(host) == 1 and host.isalpha()):  # else a Windows drive letter, not SCP
                return host.rstrip('.').lower() + '/' + _strip_dotgit(path.rstrip('/'))
    return _normalize_path_remote(url)


def normalized_remote(root):
    """The normalised `origin` URL, or None when no remote is configured.

    Never raises: a repository with no remote (a fresh `git init`, a
    tarball checkout, a throwaway CI scratch clone) is a supported, if
    less strongly identified, state -- see `repo_identity`.
    """
    result = subprocess.run(['git', 'config', '--get', 'remote.origin.url'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8')
    url = result.stdout.strip()
    return normalize_remote_url(url) if result.returncode == 0 and url else None


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
    result = subprocess.run(['git', 'rev-list', '--max-parents=0', '--reverse', 'HEAD'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        return None
    shas = [line for line in result.stdout.split() if line]
    # Reverse chronological order puts the true earliest root first; with
    # more than one root (unrelated histories merged -- rare), that first
    # entry is still a deterministic, reproducible choice.
    return shas[0] if shas else None


def is_shallow_clone(root):
    """True/False, or None when Git cannot say (an old Git, or any other
    failure -- treated as "don't know", never as a mismatch)."""
    result = subprocess.run(['git', 'rev-parse', '--is-shallow-repository'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return {'true': True, 'false': False}.get(value)


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
    result = subprocess.run(['git', 'merge-base', '--is-ancestor', commit_sha, 'HEAD'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8')
    return result.returncode == 0


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
        if recorded['remote'] != current['remote']:
            return False
        if recorded.get('shallow') is False and current.get('shallow') is False:
            return root_commit_matches(recorded.get('root_commit'))
        return True
    if not recorded.get('remote') and not current.get('remote'):
        return root_commit_matches(recorded.get('root_commit'))
    return False


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
    item = gh.api(f'repos/{repo}/issues/{issue}')
    require(item.get('number') == int(issue) and 'pull_request' not in item,
            'GITHUB_ISSUE_REQUIRED')
    title = unicodedata.normalize('NFKC', item.get('title', '')).casefold()
    slug = re.sub(r'[^\w]+', '-', title, flags=re.UNICODE).strip('-_')[:56].strip('-_') or 'issue'
    name = str(issue) + '-' + slug
    require(subprocess.run(['git', 'check-ref-format', '--branch', name], cwd=root,
                           capture_output=True).returncode == 0, 'ISSUE_TITLE_UNSAFE_FOR_BRANCH')
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
        exists = subprocess.run(['git', 'show-ref', '--verify', '--quiet',
                                 'refs/heads/' + identity['branch']], cwd=root).returncode == 0
        require(not exists, 'ISSUE_BRANCH_EXISTS: inspect its owner before switching')
        git(root, 'switch', '-c', identity['branch'])
    return {**identity, 'branch_owner': 'sanduq'}


def default_policy(qa, manual):
    require(type(qa) is bool and type(manual) is bool, 'Select QA and User Manual explicitly.')
    from delegation import DEFAULT_TIERS
    return {'schema_version': SCHEMA, 'processes': {'qa': qa, 'user_manual': manual},
            'execution': {'engine': 'auto', 'checkpoints': 'required-only'},
            'providers': {'clarification': 'prefer-superspec', 'tasks': 'prefer-superspec'},
            'issue_sync': {'taskstoissues': 'required', 'parent_link': 'native-subissue'},
            'clarification': {'transport': 'github-comments', 'resume_on_reinvoke': 'reread-answers'},
            'decisions': {'transport': 'github-issue', 'authorized_users': [],
                          'project_field': 'Decision'},
            'context': {'mode': 'measured-only', 'max_fraction': .60,
                        'checkpoint_fraction': .50, 'reserve_fraction': .10},
            'finalize': {'create_pr': True, 'merge': False}, 'updates': {'policy': 'reviewed'},
            'delegation': {
                'enabled': False, 'install_scope': 'project', 'stronger_retry': 1,
                'models': {
                    'codex': {'high': 'gpt-6-astra', 'standard': 'gpt-6-sol', 'light': 'gpt-6-terra',
                              'documentation': 'gpt-6-sol', 'review': 'gpt-6-sol'},
                    'claude': {'high': 'opus', 'standard': 'sonnet', 'light': 'haiku',
                               'documentation': 'opus', 'review': 'opus'},
                },
                'routes': {
                    name: {'preferred': {'harness': 'selected', 'tier': tier},
                           'fallbacks': [{'harness': 'selected', 'model': None}]}
                    for name, tier in DEFAULT_TIERS.items()
                },
                'overrides': {},
                'fixed_collection_commands': {},
            },
            'receipts': {'require_input_roles': False},
            'ci': sanduq_ci.default_ci()}


def select_gate(ci, mode=None, scope=None, rules=(), keys=None):
    """Apply explicit gate choices while preserving unmentioned project settings.

    `keys` sets optional gate keys (`affected_command`, `verification_check`);
    None leaves one unchanged and "none" removes it.
    """
    keys = {name: value for name, value in (keys or {}).items() if value is not None}
    if mode is None and scope is None and not rules and not keys:
        return ci
    gate = copy.deepcopy(sanduq_ci.gate_config(ci))
    for name, value in keys.items():
        if value.strip().lower() == 'none':
            gate.pop(name, None)
        else:
            gate[name] = value
    if mode is not None:
        gate['mode'] = mode
    if scope is not None:
        gate['scope'] = scope
    for selection in rules:
        name, separator, value = selection.partition('=')
        require(separator and name in sanduq_ci.GATE_RULES and value in ('on', 'off'),
                'CI_GATE_RULE_SELECTION_INVALID: expected name=on|off')
        gate['rules'][name] = value == 'on'
    sanduq_ci.validate_gate(gate)
    ci['gate'] = gate
    return ci


def validate_policy(policy):
    require(isinstance(policy, dict) and policy.get('schema_version') == SCHEMA, 'POLICY_SCHEMA_UNSUPPORTED')
    for section in ('processes','execution','providers','issue_sync','clarification','context','finalize','updates'):
        require(isinstance(policy.get(section), dict), 'POLICY_SECTION_INVALID: ' + section)
    for key in ('qa', 'user_manual'):
        require(type(policy.get('processes', {}).get(key)) is bool, 'POLICY_SELECTION_REQUIRED: ' + key)
    require(policy.get('execution', {}).get('engine') in ('auto', 'speckit', 'superspec'), 'EXECUTOR_UNSUPPORTED')
    require(policy.get('execution', {}).get('checkpoints') in ('required-only', 'every-phase'), 'CHECKPOINT_POLICY_INVALID')
    for key in ('clarification', 'tasks'):
        require(policy.get('providers', {}).get(key) in ('prefer-superspec', 'core', 'superspec'), 'PROVIDER_POLICY_INVALID: ' + key)
    context = policy.get('context', {})
    require(context.get('mode') in ('strict', 'measured-only', 'measured-with-estimated-fallback'), 'CONTEXT_MODE_INVALID')
    cap, checkpoint, reserve = (context.get(k) for k in ('max_fraction', 'checkpoint_fraction', 'reserve_fraction'))
    require(all(type(v) in (int, float) for v in (cap, checkpoint, reserve)), 'CONTEXT_LIMIT_INVALID')
    require(0 < checkpoint < cap <= .60 and 0 < reserve < cap, 'CONTEXT_LIMIT_INVALID')
    require(policy.get('issue_sync') == {'taskstoissues': 'required', 'parent_link': 'native-subissue'}, 'TASK_ISSUES_REQUIRED')
    require(policy.get('finalize') == {'create_pr': True, 'merge': False}, 'FINALIZE_POLICY_INVALID')
    require(policy.get('clarification', {}).get('resume_on_reinvoke') in ('reread-answers', 'manual-status'), 'CLARIFICATION_POLICY_INVALID')
    # Older consumer policies remain valid and opt out until the project selects delegation.
    if 'delegation' not in policy:
        policy['delegation'] = copy.deepcopy(default_policy(False, False)['delegation'])
    from delegation import migrate_qa_route, validate_delegation
    # Pre-1.7 policies predate fixed_collection_commands; empty means no stage
    # is ever inferred as qa_collect, matching today's behaviour exactly.
    policy['delegation'].setdefault('fixed_collection_commands', {})
    # Pre-1.7 policies routed everything QA-shaped through a single ``qa`` key;
    # read in place as qa_author, with a fresh light-eligible qa_collect added.
    migrate_qa_route(policy['delegation'])
    try:
        validate_delegation(policy['delegation'])
    except ValueError as exc:
        raise WorkflowError(str(exc)) from exc
    decisions = policy.get('decisions')
    if decisions is not None:
        require(isinstance(decisions, dict) and decisions.get('transport') == 'github-issue',
                'DECISION_POLICY_INVALID')
        users = decisions.get('authorized_users')
        require(isinstance(users, list) and all(isinstance(user, str) and user.strip() for user in users)
                and len({user.casefold() for user in users}) == len(users), 'DECISION_AUTHORITY_INVALID')
        require(isinstance(decisions.get('project_field'), str) and decisions['project_field'].strip(),
                'DECISION_FIELD_INVALID')
    # Optional and never filled in: an older policy keeps its digest.
    receipts = policy.get('receipts')
    if receipts is not None:
        require(isinstance(receipts, dict) and all(
            key in RECEIPT_POLICY_KEYS and type(value) is RECEIPT_POLICY_KEYS[key]
            for key, value in receipts.items()), 'RECEIPTS_POLICY_INVALID')
    skills = policy.get('skills')
    if skills is not None:
        require(isinstance(skills, dict), 'POLICY_SECTION_INVALID: skills')
        overrides = skills.get('inventory_thresholds')
        if overrides is not None:
            require(isinstance(overrides, dict) and overrides
                    and set(overrides) <= set(skill_inventory.DEFAULT_THRESHOLDS)
                    and all(type(value) is int and value > 0 for value in overrides.values()),
                    'SKILL_INVENTORY_THRESHOLDS_INVALID: expected positive integers for '
                    + ', '.join(sorted(skill_inventory.DEFAULT_THRESHOLDS)))
    scope = policy.get('scope', {})
    require(isinstance(scope, dict), 'POLICY_SECTION_INVALID: scope')
    status_names = scope.get('statuses', {})
    require(isinstance(status_names, dict) and all(isinstance(k, str) and isinstance(v, str) and v for k, v in status_names.items())
            and len(set(status_names.values())) == len(status_names), 'SCOPE_STATUS_MAPPING_INVALID')
    # A project written before CI selection existed keeps its current behaviour:
    # the shipped GitHub-hosted default is filled in rather than rejected.
    if 'ci' not in policy:
        legacy_ci = sanduq_ci.default_ci()
        legacy_ci.pop('gate')
        policy['ci'] = legacy_ci
    try:
        sanduq_ci.validate_ci(policy['ci'])
    except sanduq_ci.CIPolicyError as exc:
        raise WorkflowError(str(exc)) from exc
    band = scope.get('keep_together')
    if band:
        require(isinstance(band, dict), 'SCOPE_BAND_INVALID')
        require(type(band.get('target')) in (int, float) and type(band.get('tolerance')) in (int, float), 'SCOPE_BAND_INVALID')
        require(band['target'] >= 0 and band['tolerance'] >= 0 and bool(band.get('unit')), 'SCOPE_UNIT_REQUIRED')
        require(band.get('inclusive') is True, 'SCOPE_BAND_MUST_BE_INCLUSIVE')
    return policy


def load_policy(root):
    path = root / '.specify/workflow.yml'
    require(path.is_file(), 'WORKFLOW_INIT_REQUIRED')
    return validate_policy(yaml.safe_load(path.read_text(encoding='utf-8-sig')))


def scope_decision(policy, estimate, unit):
    band = policy.get('scope', {}).get('keep_together')
    if not band:
        return {'decision': 'needs-assessment', 'reason': 'No project keep-together preference'}
    require(unit == band['unit'], 'SCOPE_UNIT_MISMATCH')
    require(type(estimate) in (int, float) and estimate >= 0, 'SCOPE_ESTIMATE_INVALID')
    keep = band['target'] - band['tolerance'] <= estimate <= band['target'] + band['tolerance']
    return {'decision': 'keep-together' if keep else 'needs-assessment', 'automatic': keep,
            'estimate': estimate, 'unit': unit, 'policy_digest': digest(band)}


def stages(policy):
    return [s for s in BASE_STAGES if not (s.startswith('qa_') and not policy['processes']['qa'])
            and not (s.startswith('manual_') and not policy['processes']['user_manual'])]


def policy_cutoff(previous, current):
    if not previous: return 0
    affected = []
    for key, stage in {'scope':'scope','clarification':'clarify','decisions':'clarify','providers':'clarify',
                       'processes':'tasks','issue_sync':'taskstoissues','execution':'execute',
                       'finalize':'ready'}.items():
        if previous.get(key) != current.get(key): affected.append(BASE_STAGES.index(stage))
    # Context, update scheduling and receipt-contract keys (`receipts`) do not
    # retroactively invalidate semantic work: requiring input roles applies to
    # receipts written after the change, never to completed ones.
    return min(affected, default=len(BASE_STAGES))


def registry(root):
    return read(root / '.specify/extensions/.registry', {}).get('extensions', {})


def compatible(root, name):
    entry = registry(root).get(name, {})
    try:
        return entry.get('enabled') is True and Version(entry['version']) in SpecifierSet(RANGES[name])
    except (KeyError, ValueError):
        return False


def active_host(root):
    integration = read(root / '.specify/integration.json', {})
    options = read(root / '.specify/init-options.json', {})
    return integration.get('default_integration') or integration.get('integration') or options.get('integration') or options.get('ai')


def command_exists(root, command):
    name = command.replace('.', '-')
    host = active_host(root)
    if host == 'codex': return (root / '.agents/skills' / name / 'SKILL.md').is_file()
    if host == 'claude': return (root / '.claude/skills' / name / 'SKILL.md').is_file()
    return False


def package_digest(root):
    """Ignore install timestamps but detect versions, enablement and source drift."""
    entries = {key: {k: value.get(k) for k in ('version', 'enabled')} for key, value in registry(root).items()}
    paths = []
    for folder in (root / '.specify/extensions', root / '.specify/presets'):
        if folder.is_dir():
            paths += [p.relative_to(root).as_posix() for p in folder.rglob('*') if p.is_file()
                      and p.suffix in ('.py', '.md', '.yml')
                      and not any(part in ('state', '__pycache__', 'tests') for part in p.relative_to(folder).parts)]
    paths += [p.relative_to(root).as_posix() for p in (root / '.agents/skills').glob('speckit-*/SKILL.md')]
    paths += [p.relative_to(root).as_posix() for p in (root / '.claude/skills').glob('speckit-*/SKILL.md')]
    paths += ['.specify/integration.json', '.specify/init-options.json']
    return digest({'registrations': entries, 'sources': fingerprint_files(root, paths)})


def resolve_commands(root, policy):
    commands = dict(COMMANDS)
    for stage, suffix, choice in [('clarify', 'brainstorm', policy['providers']['clarification']),
                                  ('tasks', 'tasks', policy['providers']['tasks']),
                                  ('execute', 'execute', policy['execution']['engine'])]:
        candidate = 'speckit.superspec.' + suffix
        available = compatible(root, 'superspec') and command_exists(root, candidate)
        if choice == 'superspec':
            require(available, 'REQUIRED_PROVIDER_UNAVAILABLE: ' + candidate)
        if available and choice not in ('core', 'speckit'):
            commands[stage] = candidate
    if compatible(root, 'superspec') and command_exists(root, 'speckit.superspec.review'):
        commands['review'] = 'speckit.superspec.review'
    return commands


def project_errors(root, policy):
    config = read(root / '.specify/extensions/project/config.json', {})
    if not isinstance(config, dict): return ['PROJECT_CONFIG_INVALID: expected a JSON object']
    errors = []
    for key in ('owner', 'projectId', 'statusFieldId', 'stateFile'):
        if not isinstance(config.get(key), str) or not config[key]: errors.append('PROJECT_CONFIG_REQUIRED: ' + key)
    if type(config.get('projectNumber')) is not int or config['projectNumber'] < 1: errors.append('PROJECT_CONFIG_REQUIRED: projectNumber')
    if config.get('hookMode') != 'required': errors.append('PROJECT_SYNC_MUST_BE_REQUIRED: managed workflow updates the board automatically')
    options, phases = config.get('statusOptions', {}), config.get('phaseToStatus', {})
    if not isinstance(options, dict) or not options or not all(isinstance(v, str) and v for v in options.values()):
        errors.append('PROJECT_STATUS_OPTIONS_REQUIRED'); options = {}
    if not isinstance(phases, dict): phases = {}
    logical = ('Backlog', 'Feature Specification', 'Need Clarifications', 'Ready', 'In progress', 'In review', 'Done')
    mapping = policy.get('scope', {}).get('statuses', {})
    for status in logical:
        if mapping.get(status, status) not in options: errors.append('PROJECT_SCOPE_STATUS_MISSING: ' + mapping.get(status, status))
    for phase in ('open', 'analysis', 'engineer-review', 'ready', 'in-progress', 'in-review', 'done'):
        if phases.get(phase) not in options: errors.append('PROJECT_PHASE_UNMAPPED: ' + phase)
    if config.get('stateFile'):
        try: inside(root, config['stateFile'])
        except (WorkflowError, TypeError): errors.append('PROJECT_STATE_PATH_INVALID')
    return errors


def project_defaults(root, policy):
    mapping = policy.get('scope', {}).get('statuses', {})
    phases = {'open': 'Feature Specification', 'analysis': 'Ready', 'engineer-review': 'Ready',
              'ready': 'Ready', 'in-progress': 'In progress', 'in-review': 'In review', 'done': 'Done'}
    phases = {phase: mapping.get(status, status) for phase, status in phases.items()}
    existing = read(root / '.specify/extensions/project/config.json', {})
    require(isinstance(existing, dict), 'PROJECT_CONFIG_INVALID: expected a JSON object')
    if existing.get('projectId') and isinstance(existing.get('phaseToStatus'), dict):
        phases.update({phase: status for phase, status in existing['phaseToStatus'].items() if phase in phases and isinstance(status, str) and status})
    return {'phaseToStatus': phases, 'source': 'managed policy with preserved configured phase choices'}


# Workflow files Sanduq renders into a consumer project, and the installed asset
# each one is rendered from.
MANAGED_CI = {
    '.github/workflows/sanduq-workflow-gates.yml': '.specify/extensions/workflow/assets/github/workflow-gates.yml',
    '.github/workflows/documentation-gates.yml': '.specify/extensions/assure/assets/github/documentation-gates.yml',
    '.github/workflows/user-manual-preview.yml': '.specify/extensions/user-manual/assets/github/user-manual-preview.yml',
    '.github/workflows/user-manual-release.yml': '.specify/extensions/user-manual/assets/github/user-manual-release.yml',
}


def preserved_ci_path(root):
    """The CI file a --preserve-ci install handed to the project, if any.

    The tracked install lock is authoritative so every clone, worktree and
    machine agrees, including when it records that nothing is preserved; the
    git-excluded receipt only covers installs made before the lock had the key.
    """
    lock = read(root / '.specify/workflow/install-lock.json', {})
    source = lock if 'preserved_ci' in lock else read(root / '.specify/workflow/install-receipt.json', {})
    preserved = (source.get('preserved_ci') or {}).get('path')
    return Path(preserved).as_posix() if preserved else None


def ci_errors(root, policy, preserved=None):
    """Check the project's CI selection against the workflow files on disk.

    Two failures matter: a runner the project's own policy forbids without a
    recorded reason, and a workflow file that no longer matches what the current
    selection renders, which means the selection was changed but never applied.
    An installer that is preserving a file passes it as ``preserved`` because
    nothing on disk records that choice until the install succeeds.
    """
    ci = policy.get('ci') or sanduq_ci.default_ci()
    evidence_file = root / '.github/workflows/sanduq-workflow-gates.yml'
    if ci.get('provider') == 'none':
        return (['CI_PROVIDER_NONE_FILE_PRESENT: remove a managed gate through the installer']
                if evidence_file.is_file() else [])
    gate = sanduq_ci.gate_config(ci)
    if gate['mode'] == 'disabled' and evidence_file.is_file():
        return ['CI_GATE_DISABLED_FILE_PRESENT: remove a managed gate through the installer or review custom CI']
    present = {name: root / name for name in MANAGED_CI if (root / name).is_file()}
    errors = list(sanduq_ci.exception_errors(ci, [Path(name).name for name in present]))
    preserved = Path(preserved).as_posix() if preserved else preserved_ci_path(root)
    for name, target in sorted(present.items()):
        if preserved == name:
            continue  # explicitly kept by --preserve-ci; the project owns it
        asset = root / MANAGED_CI[name]
        if not asset.is_file():
            continue  # that extension is not installed; nothing to render from
        try:
            expected = sanduq_ci.render(asset.read_bytes(), ci)
        except sanduq_ci.CIPolicyError as exc:
            errors.append('CI_TEMPLATE_UNRENDERABLE: ' + name + ': ' + str(exc))
            continue
        if target.read_bytes().replace(b'\r\n', b'\n') != expected.replace(b'\r\n', b'\n'):
            errors.append('CI_WORKFLOW_STALE: ' + name + ' does not match the current ci selection; '
                          'run the workflow installer to re-render it')
    return errors


def delegation_errors(root, policy):
    """Read-only delegation health with the command that repairs a missing skill."""
    from delegation import doctor as delegation_doctor
    health = delegation_doctor(root, active_host(root))
    if not health['ok']:
        error = health['error']
        if error == 'DELEGATE_SKILL_DOCTOR_FAILED' and health.get('owned') is False:
            # Installing cannot help: the first usable copy is not Sanduq's to replace.
            error += ': ' + health['path'] + ': ' + health['action']
        elif error in ('DELEGATE_SKILL_MISSING', 'DELEGATE_SKILL_BROKEN', 'DELEGATE_SKILL_INCOMPATIBLE',
                       'DELEGATE_SKILL_DOCTOR_FAILED'):
            scope = policy['delegation']['install_scope']
            details = [item['path'] + ' (' + item['reason'] + ')' for item in health.get('incompatible') or []]
            if details:
                error += ': ' + '; '.join(details)
            error += (': delegation is enabled but the delegate-task skill is not usable; run '
                      '"python .specify/extensions/workflow/scripts/delegation.py install" to install it at '
                      'the configured ' + scope + ' scope (delegation.install_scope), or set '
                      'delegation.enabled to false')
        return [error]
    if not any(health['harnesses'].values()):
        return ['DELEGATE_AGENT_CLI_UNAVAILABLE: no supported Codex or Claude CLI']
    return []


def host_warnings(root):
    """Another installed host that lost managed skills or aliases still works as the default.

    It becomes a failure only once that host is selected, so it is a warning
    with the command that repairs it.
    """
    import hosts
    installed = hosts.installed_hosts(root)
    others = [host for host in installed if host != active_host(root)]
    if not others:
        return []
    problems = hosts.skill_errors(hosts.skill_report(root, others))
    try:
        problems += hosts.alias_errors(root, Path(__file__).resolve().parents[1], others)
    except OSError:
        pass  # a source tree without the packaged aliases
    repair = WORKFLOW_SCRIPT + ' host --use ' + str(active_host(root))
    return [problem + '; run "' + repair + '" to re-register every installed host' for problem in problems]


def doctor(root, policy, project=False, preserved_ci=None, check_delegation=True):
    needed = ['scope', 'project', 'pr'] + (['assure'] if policy['processes']['qa'] else []) + (['user-manual'] if policy['processes']['user_manual'] else [])
    errors = ['DEPENDENCY_UNAVAILABLE: ' + name + ' ' + RANGES[name] for name in needed if not compatible(root, name)]
    if active_host(root) not in ('codex','claude'):
        errors.append('HOST_UNSUPPORTED: this release supports Codex and Claude skills mode')
    if (check_delegation and policy.get('delegation', {}).get('enabled') and
            active_host(root) in ('codex', 'claude')):
        errors += delegation_errors(root, policy)
    bridge = read(root / '.specify/superpowers-handoff.json', {})
    if bridge.get('status') in ('executing', 'blocked'):
        errors.append('LEGACY_EXECUTOR_OWNS_FEATURE: reconcile the recorded bridge handoff before managed execution')
    agent = '.agents' if active_host(root) == 'codex' else '.claude'
    alias = root / agent / 'skills/speckit-superpowers-bridge/SKILL.md'
    if alias.is_file() and '<!-- sanduq-workflow-alias:v1 -->' not in alias.read_text(encoding='utf-8-sig'):
        errors.append('LEGACY_ALIAS_RECONCILIATION_REQUIRED: run the workflow installer; do not patch the upstream command')
    for name in needed:
        manifest = root / '.specify/extensions' / name / 'extension.yml'
        doc = yaml.safe_load(manifest.read_text(encoding='utf-8-sig')) if manifest.exists() else {}
        if (doc or {}).get('extension', {}).get('repository', '').rstrip('/') != 'https://github.com/samykabu/sanduq':
            errors.append('DEPENDENCY_SOURCE_MISMATCH: ' + name + ' must come from samykabu/sanduq')
    try:
        commands = resolve_commands(root, policy)
        errors += ['COMMAND_UNAVAILABLE: ' + commands[s] for s in stages(policy)
                   if not commands[s].startswith('workflow:') and not command_exists(root, commands[s])]
    except WorkflowError as exc:
        errors.append(str(exc))
    hooks_path = root / '.specify/extensions.yml'
    if not hooks_path.exists():
        errors.append('HOOK_RECONCILIATION_REQUIRED')
    else:
        hooks = yaml.safe_load(hooks_path.read_text(encoding='utf-8-sig')) or {}
        require(isinstance(hooks, dict) and isinstance(hooks.get('hooks'), dict), 'HOOK_CONFIG_INVALID')
        for event, items in hooks.get('hooks', {}).items():
            require(isinstance(items, list) and all(isinstance(item, dict) for item in items), 'HOOK_LIST_INVALID: ' + event)
            for hook in items:
                owned = hook.get('extension') in ('assure', 'user-manual', 'superspec', 'speckit-superpowers-bridge', 'project') or hook.get('command') == 'speckit.scope.after-specify' or (hook.get('extension') == 'pr' and event == 'after_implement')
                if owned and hook.get('enabled', True): errors.append('DUPLICATE_STAGE_OWNER: ' + event + ':' + hook.get('command', ''))
    preset_registry = read(root / '.specify/presets/.registry', {}).get('presets', {})
    for preset in ('workflow', 'scope-gate', 'scope-brainstorm'):
        if not (root / '.specify/presets' / preset / 'preset.yml').is_file():
            errors.append('PRESET_REQUIRED: ' + preset)
        if preset_registry.get(preset, {}).get('enabled') is not True:
            errors.append('PRESET_NOT_ENABLED: ' + preset)
    errors += ci_errors(root, policy, preserved_ci)
    if project: errors += project_errors(root, policy)
    warnings = host_warnings(root)
    # Only a --project doctor run pays for this (migrate/upgrade doctor calls do
    # not), and a scan failure (an unreadable plugin manifest, an odd path) is
    # reported, never allowed to fail doctor itself.
    skill_inventory_result = None
    if project:
        try:
            skill_inventory_result = skill_inventory.inventory(root, policy)
            warnings += skill_inventory.warnings(skill_inventory_result)
        except Exception as exc:
            skill_inventory_result = None
            warnings.append('SKILL_INVENTORY_UNAVAILABLE: ' + str(exc))
    if isinstance(policy.get('delegation'), dict):
        from delegation import light_tier_route_warnings
        warnings += light_tier_route_warnings(policy['delegation'])
    drift = eol_drift(root)
    if drift:
        warnings.append(
            f'BYTE_SENSITIVE_EOL_DRIFT: {len(drift)} tracked byte-sensitive file(s) (.sql or -text, e.g. {drift[0]}) '
            'have working-tree line endings that differ from the index (i/lf w/crlf or i/crlf w/lf). Evidence '
            'fingerprints use the committed blob while such a file is otherwise unchanged, but tools reading the '
            'working tree see different bytes than CI. Remedy: commit or stash edits, add "*.sql -text" to '
            '.gitattributes (or set core.autocrlf=false), then re-checkout the files listed by "git ls-files --eol" '
            'with "git -c core.autocrlf=false checkout -- <path>".')
    result = {'ok': not errors, 'errors': errors, 'warnings': warnings, 'project_checked': project,
              'context': 'Only fresh reliable measurements can trigger context pauses; unavailable or estimated usage is nonblocking outside explicit strict mode'}
    if project:
        result['skill_inventory'] = skill_inventory_result
    return result


def context_gate(policy, usage):
    require(isinstance(usage, dict) and usage.get('session_id'), 'CONTEXT_USAGE_REQUIRED')
    try:
        return measured_context_gate(policy, usage)
    except WorkflowError as exc:
        if policy['context']['mode'] == 'strict':
            raise
        return {'pause': False, 'method': 'unavailable', 'guaranteed': False,
                'session_id': usage['session_id'], 'reason': 'context-monitoring-unavailable: ' + str(exc)}


def measured_context_gate(policy, usage):
    require(usage.get('method') in ('measured', 'estimated'), 'CONTEXT_METHOD_REQUIRED')
    require(usage.get('method') == 'measured' and usage.get('reliable', True) is True,
            'CONTEXT_LIMIT_UNENFORCEABLE: reliable host measurement unavailable')
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(usage['observed_at'])).total_seconds()
    except (KeyError, ValueError, TypeError):
        raise WorkflowError('CONTEXT_TIMESTAMP_INVALID')
    require(0 <= age <= 120, 'CONTEXT_TELEMETRY_STALE')
    measured = usage['method'] == 'measured'
    require(policy['context']['mode'] != 'strict' or (measured and usage.get('pre_call_bound') is True), 'CONTEXT_LIMIT_UNENFORCEABLE')
    fraction, next_fraction = usage.get('fraction'), usage.get('next_fraction')
    require(all(type(n) in (float, int) and 0 <= n <= 1 for n in (fraction, next_fraction)), 'CONTEXT_FRACTION_INVALID')
    reserve = policy['context']['reserve_fraction']
    pause = fraction >= policy['context']['checkpoint_fraction'] or fraction + next_fraction + reserve >= policy['context']['max_fraction']
    return {'pause': pause, 'method': usage['method'], 'guaranteed': measured and usage.get('pre_call_bound') is True,
            'fraction': fraction, 'session_id': usage['session_id'], 'reason': 'checkpoint-required' if pause else 'within-budget'}


def fingerprint_files(root, paths):
    result = {}
    paths = sorted(set(paths))
    for relative in paths:
        inside(root, relative)
    # Byte-sensitive files read as their committed blob when the working tree
    # differs only by checkout conversion, so a Windows autocrlf checkout and a
    # clean CI checkout of the same commit fingerprint identically.
    for relative, content in portable_files(root, paths).items():
        if content is not None:
            # Checkbox bookkeeping must not invalidate task publication or planning.
            if Path(relative).name == 'tasks.md':
                content = re.sub(rb'(?m)^(\s*- )\[[ xX]\]', rb'\1[ ]', content)
                # Routing comments are operational metadata. Route policy changes
                # invalidate future dispatch, not earlier semantic task receipts.
                # A marker drops together with the newline that precedes it, so a
                # final task line annotated without a terminal newline, or one an
                # earlier release joined to its marker, hashes like the original.
                marker = rb'[ \t]*<!-- sanduq-delegation \{[^\r\n]*\} -->[ \t]*(?=\r?\n|\Z)'
                content = re.sub(rb'(?<=[^ \t\r\n])' + marker + rb'\r?\n\Z', b'', content)
                content = re.sub(rb'\A' + marker + rb'(?:\r?\n)?', b'', content)
                content = re.sub(rb'(?:\r?\n)?' + marker, b'', content)
            result[relative] = hashlib.sha256(content).hexdigest()
        else:
            result[relative] = None
    return result


def required_inputs(root, feature, stage):
    """Minimum artifact coverage is enforced even if an agent omits a path."""
    index = BASE_STAGES.index(stage)
    paths = []
    if index >= BASE_STAGES.index('specify'):
        paths += [feature + '/spec.md', feature + '/scope-source.json']
    if index >= BASE_STAGES.index('plan'):
        paths += [feature + '/plan.md']
    if index >= BASE_STAGES.index('tasks'):
        paths += [feature + '/tasks.md']
    if index >= BASE_STAGES.index('taskstoissues'):
        paths += [feature + '/workflow/task-issues.json']
    constitution = '.specify/memory/constitution.md'
    if (root / constitution).is_file(): paths.append(constitution)
    if index >= BASE_STAGES.index('plan'):
        for name in ('research.md', 'data-model.md', 'quickstart.md'):
            if (root / feature / name).is_file(): paths.append(feature + '/' + name)
        contracts = root / feature / 'contracts'
        if contracts.is_dir():
            paths += [p.relative_to(root).as_posix() for p in contracts.rglob('*') if p.is_file()]
    return sorted(set(paths))


def source_fingerprints(root):
    """Inventory code and build inputs, including additions and deletion tombstones."""
    paths = git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0')
    excluded = {'.git', 'node_modules', '__pycache__', 'dist', 'build', 'coverage', 'obj'}
    operational = {'.specify', '.agents', '.claude', '.codex', 'specs', 'User-Manual', 'docs', 'graphify-out', 'keys_cert'}
    selected = []
    for path in filter(None, paths):
        parts = Path(path).parts
        if parts[0] in operational or any(p in excluded for p in parts): continue
        if Path(path).name.startswith('.env') or Path(path).suffix.lower() in ('.pem', '.key', '.p12', '.pfx'): continue
        selected.append(path)
    return fingerprint_files(root, selected)


def consulted_inputs(receipt):
    """Inputs the receipt declared as read for context only.

    A receipt without `input_roles` (every receipt written before 1.6.0) has
    none, so every input stays a dependency: never weaker than before.
    """
    roles = receipt.get('input_roles') or {}
    return {path for path, entry in roles.items()
            if isinstance(entry, dict) and entry.get('role') == 'consulted'}


def dependency_fingerprints(receipt, required=()):
    """The recorded hashes a receipt's conclusion rests on. Consulted inputs keep
    their hash for provenance but do not decide whether the receipt is current;
    a required input of the stage is always a dependency."""
    consulted = consulted_inputs(receipt) - set(required)
    return {path: value for path, value in receipt.get('fingerprints', {}).items() if path not in consulted}


def role_exempt(feature, path):
    """Feature artifacts and project memory are dependencies without a declaration."""
    return path.startswith(feature + '/') or path.startswith('.specify/memory/')


def require_input_roles(policy):
    return (policy.get('receipts') or {}).get('require_input_roles') is True


def validate_input_roles(root, feature, stage, receipt, policy):
    """Check declared roles against the receipt's own input manifest.

    Evidence and the stage's required inputs can never be consulted: the
    stage's conclusion rests on them by definition. When the policy sets
    `receipts.require_input_roles`, every input outside the feature directory
    and `.specify/memory/` must carry a declared role, so nothing becomes
    advisory by omission.
    """
    roles = receipt.get('input_roles')
    if roles is None:
        roles = {}
    require(isinstance(roles, dict), 'INPUT_ROLES_INVALID: expected a map of input path to role')
    inputs = receipt['inputs']
    protected = set(receipt['evidence']) | set(required_inputs(root, feature, stage))
    for path, entry in roles.items():
        require(path in inputs, 'INPUT_ROLE_NOT_IN_MANIFEST: ' + str(path))
        require(isinstance(entry, dict) and entry.get('role') in INPUT_ROLES and set(entry) <= {'role', 'because'},
                'INPUT_ROLE_INVALID: ' + path + ' (expected {role: dependency|consulted, because: text})')
        because = entry.get('because')
        require(because is None or (isinstance(because, str) and because.strip()), 'INPUT_ROLE_REASON_INVALID: ' + path)
        if entry['role'] == 'consulted':
            require(because, 'INPUT_ROLE_REASON_REQUIRED: a consulted input states why the conclusion '
                             'does not depend on its current content: ' + path)
            require(path not in protected, 'INPUT_ROLE_CONSULTED_NOT_ALLOWED: ' + path +
                    ' is evidence or a required input of ' + stage)
    if require_input_roles(policy):
        missing = [path for path in inputs if path not in roles and not role_exempt(feature, path)]
        require(not missing, 'INPUT_ROLE_UNDECLARED: ' + ', '.join(missing))


def consulted_drift(root, feature, receipts):
    """Changed consulted inputs: reported as advisory drift, never as staleness."""
    drift = []
    for stage, receipt in receipts.items():
        consulted = consulted_inputs(receipt) - set(required_inputs(root, feature, stage))
        saved = {path: receipt['fingerprints'][path] for path in consulted
                 if path in receipt.get('fingerprints', {})}
        if not saved:
            continue
        current = fingerprint_files(root, saved)
        for path in sorted(p for p in saved if current[p] != saved[p]):
            drift.append({'stage': stage, 'path': path, 'because': receipt['input_roles'][path].get('because')})
    return drift


def gate_settings(policy):
    """The gate section of a policy, or {} when none (legacy or no policy)."""
    ci = (policy or {}).get('ci') or {}
    return ci.get('gate') if isinstance(ci.get('gate'), dict) else {}


def affected_command(policy):
    try:
        return sanduq_ci.affected_command(gate_settings(policy))
    except sanduq_ci.CIPolicyError as exc:
        raise WorkflowError(str(exc)) from exc


def verification_check(policy):
    try:
        return sanduq_ci.verification_check(gate_settings(policy))
    except sanduq_ci.CIPolicyError as exc:
        raise WorkflowError(str(exc)) from exc


def affected_lanes(root, command, paths):
    """Classify paths through the project's affected-lane hook (`ci.gate.affected_command`).

    The hook reads a JSON list of paths on stdin and prints
    `{"paths": {"<path>": ["<lane>", ...]}}`. Any failure -- a non-zero exit,
    output that is not that shape, or a path left unclassified -- raises, so
    every caller fails closed.
    """
    try:
        result = subprocess.run(command, cwd=root, input=json.dumps(sorted(paths)), capture_output=True,
                                text=True, encoding='utf-8', timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkflowError('AFFECTED_COMMAND_FAILED: ' + str(exc)) from exc
    require(result.returncode == 0, 'AFFECTED_COMMAND_FAILED: exit ' + str(result.returncode) + ': ' +
            (result.stderr or result.stdout).strip()[:300])
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        raise WorkflowError('AFFECTED_COMMAND_OUTPUT_INVALID: not JSON') from exc
    mapping = data.get('paths') if isinstance(data, dict) else None
    require(isinstance(mapping, dict), 'AFFECTED_COMMAND_OUTPUT_INVALID: expected {"paths": {"<path>": [lanes]}}')
    missing = [path for path in paths if path not in mapping]
    require(not missing, 'AFFECTED_COMMAND_OUTPUT_INVALID: no lanes for ' + ', '.join(sorted(missing)[:5]))
    lanes = {}
    for path in paths:
        value = mapping[path]
        require(isinstance(value, list) and all(isinstance(lane, str) and lane for lane in value),
                'AFFECTED_COMMAND_OUTPUT_INVALID: lanes of ' + path)
        lanes[path] = sorted(set(value))
    return lanes


def source_drift(receipt, current):
    """Source paths added, removed or changed since the receipt's inventory."""
    old = receipt.get('source_fingerprints') or {}
    return sorted(path for path in set(old) | set(current)
                  if path not in old or path not in current or old[path] != current[path])


def current_source_key(root):
    """HEAD and its source key, or (None, None) when HEAD does not describe the working tree.

    The key is of a commit; a receipt inventories the working tree, so the two
    are bound only while no source path the key counts differs from HEAD.
    """
    try:
        if sk.dirty_source_paths(root):
            return None, None
        return git(root, 'rev-parse', 'HEAD'), sk.source_key(root, 'HEAD')
    except (sk.SourceKeyError, WorkflowError):
        return None, None


_HEX40 = re.compile(r'[0-9a-f]{40}')
_HEX64 = re.compile(r'[0-9a-f]{64}')


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def diff_review_command(base, head):
    """The one command whose output a recorded incremental review is bound to (`Diff sha256:`).

    `git diff-tree` is plumbing, so user diff configuration (prefixes, colour,
    renames, algorithm, external drivers, textconv) cannot change its bytes;
    `--binary` puts binary changes in the hash; the pathspec keeps exactly the
    paths the source key counts (`source_key.is_source_path`): no excluded
    prefix and no `*.md` in any ASCII case.
    """
    pathspec = ['.'] + [':(exclude)' + prefix for prefix in sk.EXCLUDED_PREFIXES] + [':(exclude,glob,icase)**/*.md']
    return ['git', '-c', 'core.quotePath=true', 'diff-tree', '-r', '-p', '--binary', '--no-renames', base, head,
            '--', *pathspec]


def diff_review_shell(base, head):
    """`diff_review_command` spelled for a POSIX shell (Git Bash on Windows)."""
    return shlex.join(diff_review_command(base, head))


def diff_review_sha256(root, base, head):
    """The SHA-256 of the bytes `diff_review_command(base, head)` prints."""
    env = {key: value for key, value in os.environ.items()
           if key not in ('GIT_LITERAL_PATHSPECS', 'GIT_GLOB_PATHSPECS', 'GIT_NOGLOB_PATHSPECS', 'GIT_ICASE_PATHSPECS')}
    result = subprocess.run(diff_review_command(base, head), cwd=root, capture_output=True, env=env)
    require(result.returncode == 0,
            'DIFF_REVIEW_DIFF_FAILED: ' + result.stderr.decode('utf-8', 'replace').strip()[:300])
    return hashlib.sha256(result.stdout).hexdigest()


def ci_evidence_complete(receipt):
    """Whether a receipt's `ci_evidence` is the complete record `revalidate --stage verify` writes.

    `ci_evidence` lives in a committed checkpoint, so a hand-edited or partial
    record must never pass: every field the runtime writes is required and
    well-formed (fail closed), not defaulted.
    """
    evidence = receipt.get('ci_evidence')
    if not isinstance(evidence, dict):
        return False
    head, key = evidence.get('head'), evidence.get('source_key')
    return (_positive_int(evidence.get('run_id')) and _positive_int(evidence.get('attempt'))
            and isinstance(head, str) and bool(_HEX40.fullmatch(head))
            and isinstance(receipt.get('head'), str) and bool(_HEX40.fullmatch(receipt['head']))
            and isinstance(key, str) and bool(_HEX64.fullmatch(key))
            and isinstance(evidence.get('tier'), str) and bool(evidence['tier'].strip())
            and _string_list(evidence.get('lanes')) and _string_list(evidence.get('required_lanes'))
            and evidence.get('conclusion') == 'success'
            and 'lane_gap' in evidence and evidence['lane_gap'] == []
            and set(evidence['required_lanes']) <= set(evidence['lanes']))


def ci_evidence_current(root, receipt):
    """A Verify receipt's recorded CI run still covers the current source.

    The record is complete (`ci_evidence_complete`); the run concluded success
    with no lane gap and covered every lane the drift it was accepted for
    required; its head is the receipt's head or a commit of it (revalidate
    accepts a run on an ancestor with the same source key); and its source key
    (the receipt's own) is the key of the current, clean HEAD.
    """
    if not ci_evidence_complete(receipt):
        return False
    evidence = receipt['ci_evidence']
    if evidence['head'] != receipt['head']:
        ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', evidence['head'], receipt['head']],
                                  cwd=root, capture_output=True)
        if ancestor.returncode != 0:
            return False
    _, key = current_source_key(root)
    return key is not None and evidence['source_key'] == key == receipt.get('source_key')


def receipt_status(root, feature, stage, receipt, policy=None):
    """Whether a receipt is current, and why not.

    Explicit fingerprints (inputs and evidence) always keep their byte-hash
    check. For Verify, Review and Ready the source inventory is compared next:
    identical is current. A drifted inventory stays current only for a receipt
    that records a `source_key` (1.6.0 and later) when, with no drifted path
    among its explicit fingerprints, either (Verify only) its recorded CI run
    covers the current source key, or the project's affected-lane hook maps
    every drifted path to no lane. A legacy receipt without `source_key`, or a
    project without the hook, keeps the identity rule; a failing hook fails closed.
    """
    if receipt.get('stale'):
        return {'current': False, 'reason': 'marked-stale', 'stale': receipt['stale']}
    saved = receipt.get('fingerprints', {})
    required = set(required_inputs(root, feature, stage))
    if not saved or not required <= set(saved):
        return {'current': False, 'reason': 'explicit-drift', 'paths': sorted(required - set(saved))}
    dependencies = dependency_fingerprints(receipt, required)
    now_hashes = fingerprint_files(root, dependencies)
    if now_hashes != dependencies:
        return {'current': False, 'reason': 'explicit-drift',
                'paths': sorted(path for path in dependencies if now_hashes.get(path) != dependencies[path])}
    if stage not in SOURCE_STAGES:
        return {'current': True, 'via': 'identity'}
    current = source_fingerprints(root)
    if receipt.get('source_fingerprints') == current:
        return {'current': True, 'via': 'identity'}
    drift = source_drift(receipt, current)
    stale = {'current': False, 'reason': 'source-drift', 'paths': drift}
    if not receipt.get('source_key'):
        return {**stale, 'rule': 'identity'}
    explicit = sorted(set(drift) & set(saved))
    if explicit:
        return {**stale, 'rule': 'explicit-fingerprint', 'explicit': explicit}
    if stage == 'verify' and ci_evidence_current(root, receipt):
        return {'current': True, 'via': 'ci-evidence', 'paths': drift, 'run_id': receipt['ci_evidence'].get('run_id')}
    command = affected_command(policy)
    if not command:
        return {**stale, 'rule': 'identity'}
    try:
        lanes = affected_lanes(root, command, drift)
    except WorkflowError as exc:
        return {**stale, 'rule': 'classification-failed', 'error': str(exc)}
    laned = {path: value for path, value in lanes.items() if value}
    if not laned:
        return {'current': True, 'via': 'lane-free-drift', 'paths': drift}
    return {**stale, 'rule': 'affected-lanes', 'lanes': laned}


def receipt_current(root, feature, stage, receipt, policy=None):
    return receipt_status(root, feature, stage, receipt, policy)['current']


def recovery_recipe(feature, stage, status, policy, receipt):
    """The exact commands that make a stale receipt current again (G6).

    Offers `amend` for changed evidence, `revalidate` when a checked route
    exists for source drift, and otherwise the claim/complete re-record.
    """
    at = ' --feature ' + feature
    rerecord = (f'{WORKFLOW_SCRIPT} claim{at} --usage <usage.json> (it claims {stage}; if a claim is active, '
                f'{WORKFLOW_SCRIPT} recover{at} --token <token> --reason "<why>" first), re-run {stage}, then '
                f'{WORKFLOW_SCRIPT} complete{at} --token <token> --receipt <receipt.json>')
    reason = status.get('reason')
    if reason == 'marked-stale':
        mark = status.get('stale') or {}
        if mark.get('reason') == 'ci-lane-gap':
            return [f'Run the verification check on a commit with the current source key covering lanes '
                    f'{", ".join(mark.get("lanes") or [])}, then {WORKFLOW_SCRIPT} revalidate{at} --stage verify '
                    f'--check-run <run id>', 'or re-record: ' + rerecord]
        return ['Re-record (a changed amendment undermined this receipt): ' + rerecord]
    if reason == 'explicit-drift':
        evidence = set(receipt.get('evidence') or [])
        steps = [f'{WORKFLOW_SCRIPT} amend{at} --stage {stage} --evidence {path} --reason "<why>" '
                 f'--assessment unchanged|changed' for path in status.get('paths', []) if path in evidence]
        if any(path not in evidence for path in status.get('paths', [])):
            steps.append('An input changed, which no amendment covers; re-record: ' + rerecord)
        return steps or [rerecord]
    steps = []
    if status.get('rule') == 'classification-failed':
        steps.append('The affected-lane hook failed and the gate fails closed (' + str(status.get('error')) +
                     '); fix ci.gate.affected_command, or continue below.')
    if stage == 'verify':
        check = verification_check(policy)
        if check:
            steps.append(f'Push HEAD, wait for the "{check["name"]}" check to pass on it, then '
                         f'{WORKFLOW_SCRIPT} revalidate{at} --stage verify --check-run <run id>')
    elif stage == 'review' and receipt.get('head'):
        steps.append(f'Review the source diff {receipt["head"]}..HEAD and record it in {feature}/evidence/<file>.md '
                     f'with the lines "Diff reviewed: {receipt["head"]}..<HEAD sha>", "Diff sha256: <hash>" (the '
                     f'SHA-256 of the exact bytes of: {diff_review_shell(receipt["head"], "HEAD")} | sha256sum), '
                     f'"Reviewer: <who reviewed it>" and "Blocking findings: 0", then '
                     f'{WORKFLOW_SCRIPT} revalidate{at} --stage review --diff-reviewed <that file>')
    elif stage == 'ready':
        steps.append(f'Once Verify and Review are current: {WORKFLOW_SCRIPT} revalidate{at} --stage ready')
    steps.append(('or re-record: ' if steps else '') + rerecord)
    return steps


def receipt_drift(root, feature, stage, receipt):
    """Explain staleness without printing source content or weakening the gate."""
    saved = dependency_fingerprints(receipt, required_inputs(root, feature, stage))
    current = fingerprint_files(root, set(saved) | set(required_inputs(root, feature, stage)))
    changed = {p for p in set(saved) | set(current) if saved.get(p) != current.get(p)}
    changed.update(set(required_inputs(root, feature, stage)) - set(receipt.get('fingerprints', {})))
    if stage in SOURCE_STAGES:
        old = receipt.get('source_fingerprints', {})
        new = source_fingerprints(root)
        changed.update(p for p in set(old) | set(new) if p not in old or p not in new or old[p] != new[p])
    return sorted(changed)


def ready_checks(root, feature, policy, state, base=None, rules=None, warnings=None):
    """Task completion, task-issue mapping and selected documentation freshness.

    The Ready stage's automated checks, shared by `ci_gate.py` (under the
    project's gate rules) and `revalidate --stage ready` (all of them).
    Returns the names of the checks that ran. When given, `warnings` collects
    non-fatal advisories in place (for example a local-only trust read on a
    fresh checkout or CI runner, round 3 finding 1); the caller decides how
    to surface them.
    """
    rules = rules or {'tasks': True, 'task_links': True, 'documentation': True}
    directory = inside(root, feature)
    ran = []
    tasks = None
    if rules.get('tasks') or rules.get('task_links'):
        from task_issues import parse_tasks
        tasks = parse_tasks((directory / 'tasks.md').read_text(encoding='utf-8-sig'))
    if rules.get('tasks'):
        require(all(t['done'] for t in tasks.values()), 'INCOMPLETE_TASKS')
        if policy.get('delegation', {}).get('enabled'):
            # A checked task delegated through the dispatcher must have a
            # verified, successful outcome, not merely a checkbox (finding 1):
            # a light-tier result the guard left unverified, or any other
            # non-successful status (running, starting, failed, abandoned --
            # finding 2c, round 2), never earns Ready on its own. The ledger
            # itself must still be trustworthy: 'untrusted' (a genuine,
            # persisted tamper, or a marker that disagrees with the current
            # bytes) refuses; 'unverified-local' (no local write marker at
            # all -- the normal state for a CI checkout or a fresh clone,
            # since delegations.json is committed but the marker is local
            # runtime state) is a warning only, and status is still enforced
            # (round 3, findings 1-2).
            from delegation import latest_attempt, ledger_trust_state, task_line_content_sha256, task_lines
            trust = ledger_trust_state(root, feature)
            require(trust != 'untrusted',
                    'DELEGATION_LEDGER_UNTRUSTED: the delegation ledger for ' + feature + ' was tampered '
                    'with (a hand-edit, or one not yet cleared by trust-reset); run '
                    '"delegate_dispatch.py trust-reset --feature ' + feature + ' --reason <text>" only '
                    'after reviewing exactly what changed')
            if trust == 'unverified-local' and warnings is not None:
                warnings.append('DELEGATION_LEDGER_TRUST_UNVERIFIED_LOCAL: no local dispatcher-write '
                                'marker for ' + feature + ' (expected on a fresh checkout or CI runner); '
                                'delegated task status is still enforced, but local tamper detection '
                                'cannot vouch for this ledger on this machine')
            # A checked task with NO attempt at all previously slipped through
            # unnoticed (round 6, finding 2): the previous check only rejected
            # a task whose latest attempt *existed* and had failed, never one
            # missing outright. Fixed by requiring 'successful' from an empty
            # record too. Round 7 removed two exemptions reviewed as bypasses:
            # a stage-wide 'delegation_enabled_for_execute: false' checkpoint
            # field (mutable, unfingerprinted, and never read here again), and
            # a per-task 'orchestrator-executed' self-certification a worker
            # could invoke. There is now exactly one way a checked task
            # without its own dispatcher attempt earns Ready: run
            # "delegate_dispatch.py adopt" to independently verify it with a
            # real acceptance check, which records an ordinary successful
            # attempt latest_attempt reads like any other -- except that an
            # adopted attempt also carries a binding (round 8, finding 1): a
            # sha256 of the task line's content (minus its checkbox state,
            # whitespace normalised) at the moment it was adopted. A task
            # whose current line no longer matches that digest -- edited,
            # or a different task entirely reusing the same id -- must not
            # ride the earlier adoption to Ready.
            current_lines = task_lines((directory / 'tasks.md').read_text(encoding='utf-8-sig'))
            not_verified, changed = [], []
            for task_id in tasks:
                attempt = latest_attempt(root, feature, task_id) or {}
                if attempt.get('status') != 'successful':
                    not_verified.append(task_id)
                    continue
                if (attempt.get('adopted') and attempt.get('task_line_sha256') and
                        task_line_content_sha256(current_lines[task_id]) != attempt['task_line_sha256']):
                    changed.append(task_id)
                    continue
                # An orchestrator-run check resolving a task -- adopt for one
                # with no dispatcher attempt at all, accept for an unverified
                # light-tier one -- is exactly the kind of self-certification
                # this whole guard exists to police everywhere else; a
                # reviewer must be able to see every task that reached Ready
                # this way, not only ones a worker actually attempted (round
                # 9, finding 1b). Advisory only: status is already enforced
                # above, and ci_gate already forwards every warning here to
                # stderr and $GITHUB_STEP_SUMMARY.
                if warnings is None:
                    continue
                source = (attempt.get('accepted_evidence') or {}).get('source')
                if source == 'adopt':
                    warnings.append('DELEGATION_TASK_ADOPTED: ' + task_id + ' via "' +
                                    str(attempt.get('command')) + '" (' + str(attempt.get('expect')) +
                                    ', exit ' + str(attempt.get('exit_code')) + ')')
                elif source == 'accept':
                    resolved = next((a for a in attempt.get('acceptance_attempts', []) if a.get('accepted')),
                                    None)
                    if resolved:
                        warnings.append('DELEGATION_TASK_ACCEPTED: ' + task_id + ' via "' +
                                        str(resolved.get('command')) + '" (' + str(resolved.get('expect')) +
                                        ', exit ' + str(resolved.get('exit_code')) + ')')
            require(not not_verified, 'DELEGATION_TASK_UNVERIFIED: ' + ', '.join(sorted(not_verified)) +
                    ' - resolve with delegate_dispatch.py accept or reassign, or adopt it with an '
                    'acceptance check, before Ready')
            require(not changed, 'DELEGATION_ADOPT_TASK_CHANGED: ' + ', '.join(sorted(changed)) +
                    ' - the task line changed since it was adopted; re-run delegate_dispatch.py adopt '
                    'with a fresh acceptance check before Ready')
        ran.append('tasks')
    if rules.get('task_links'):
        mapping = read(directory / 'workflow/task-issues.json', {})
        repo, parent = state['issue'].split('#')
        require((mapping.get('repo'), mapping.get('parent'), mapping.get('feature')) == (repo, int(parent), feature),
                'TASK_MAPPING_IDENTITY_MISMATCH')
        require(set(tasks) <= set(mapping.get('tasks', {})) and all(mapping['tasks'][t].get('linked') for t in tasks),
                'TASK_MAPPING_INCOMPLETE')
        ran.append('task_links')
    checks = []
    if rules.get('documentation') and policy['processes']['qa']:
        checks.append(['.specify/extensions/assure/scripts/assure_state.py', 'status', '--kind', 'document'])
    if rules.get('documentation') and policy['processes']['user_manual']:
        checks.append(['.specify/extensions/user-manual/scripts/manual_state.py', 'status'])
    for args in checks:
        require((root / args[0]).is_file(), 'SELECTED_PROCESS_MISSING: ' + args[0])
        command = [sys.executable, *args, '--feature', feature, '--repo-root', str(root)]
        if base: command += ['--base-ref', base]
        result = subprocess.run(command, cwd=root, text=True, encoding='utf-8', capture_output=True)
        require(result.returncode == 0, 'DOCUMENTATION_GATE_FAILED: ' + result.stdout + result.stderr)
        require(json.loads(result.stdout).get('current') is True, 'DOCUMENTATION_NOT_CURRENT')
        ran.append('documentation:' + Path(args[0]).stem)
    return ran


def default_actor(root):
    """Who recorded an amendment: the Git identity, else the OS user."""
    try:
        name = git(root, 'config', 'user.name')
    except WorkflowError:
        name = ''
    return name or os.environ.get('USER') or os.environ.get('USERNAME') or 'unknown'


def require_not_delegated_context(command):
    """Refuse a command inside any delegated process tree, worker or
    orchestrator alike.

    Reads the same two environment variables `delegate_dispatch`'s
    `require_not_worker_context` does, through the shared
    `delegation.delegated_run_id`/`delegated_role` (round 1, finding 7):
    `workflow.py` cannot import `delegate_dispatch` itself (that module
    imports `workflow`, so the reverse would be a cycle), but `delegation`
    imports neither, so both sides read the same fact and can never drift
    on what the variables currently hold, even though each then applies
    its own policy on top. Unlike `require_not_worker_context`, this one
    also refuses the delegated orchestrator (`SANDUQ_DELEGATED_ROLE` set
    at all, not just when misread as a worker): that role-aware exception
    exists there to scope a worker-dispatching command to its own
    feature's tasks, which has no analogue for a repo-identity operation.
    `relocate` bypasses the identity gate by design, so it must never be
    reachable from a sandboxed process that inherited a stale or unrelated
    delegation environment; only an ordinary, undelegated invocation may
    call it. Defence in depth only, not a security boundary on its own.
    """
    from delegation import delegated_run_id, delegated_role
    require(not delegated_run_id() and not delegated_role(),
            'DELEGATION_WORKER_CONTEXT: ' + command + ' is not callable from a delegated worker or orchestrator '
            'context; run it directly, outside any delegated process tree')


def ensure_local_excludes(root):
    """Keep runtime/backup files local, including preserved consumer credentials."""
    value = git(root, 'rev-parse', '--git-path', 'info/exclude')
    path = Path(value)
    if not path.is_absolute(): path = root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.read_text(encoding='utf-8') if path.exists() else ''
    patterns = ('/.specify/workflow/backups/', '/.specify/workflow/runtime/',
                '/.specify/workflow/install-receipt.json', '/specs/*/workflow/backups/',
                '/specs/*/workflow/progress/', '/.delegate/')
    missing = [pattern for pattern in patterns if pattern not in current.splitlines()]
    if missing:
        path.write_text(current.rstrip('\n') + '\n# Sanduq local backups and runtime\n' + '\n'.join(missing) + '\n', encoding='utf-8')


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise WorkflowError('WORKFLOW_BUSY: inspect owner before removing ' + str(path))
    try:
        os.write(fd, json.dumps({'pid': os.getpid(), 'created': now()}).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


class Run:
    def __init__(self, root, feature):
        self.root = root.resolve()
        self.feature = inside(self.root, feature)
        require(self.feature.is_relative_to(self.root / 'specs') and self.feature != self.root / 'specs', 'FEATURE_PATH_INVALID')
        self.relative = self.feature.relative_to(self.root).as_posix()
        self.path = self.feature / 'workflow/checkpoint.json'
        self.lock = self.root / '.specify/workflow/runtime' / (digest(self.relative) + '.lock')
        self.policy = load_policy(self.root)

    def load(self, allow_branch_change=False):
        state = read(self.path)
        require(state and state.get('schema_version') == SCHEMA, 'WORKFLOW_START_REQUIRED')
        require(state['feature'] == self.relative, 'CHECKPOINT_IDENTITY_MISMATCH')
        require_issue_repository_binding(self.root, state, self.relative)
        if 'repo_identity' in state:
            require(identity_matches(state['repo_identity'], repo_identity(self.root), current_root=self.root),
                    'CHECKPOINT_IDENTITY_MISMATCH: this checkpoint belongs to a different repository. If this is '
                    'the same project relocated (a fork, a renamed remote, a migrated org), run: workflow.py '
                    'relocate --feature ' + self.relative + ' --reason "<why>"')
        else:
            # A pre-1.8.0 checkpoint recorded only the absolute `repo_path` it
            # was started from, which is machine- and clone-specific and is
            # never compared (that comparison was the checkpoint-identity
            # design bug). There is no portable signal on file to check
            # against, so it is accepted once this repository's own identity
            # can be established at all, and upgraded to compare portably
            # from here on. The upgrade is recorded on `state` in memory only
            # -- every mutating command loads through here and then calls
            # `save`, which persists whatever `state` it was handed -- so a
            # read-only `load` (e.g. `next`) never writes anything itself.
            current = repo_identity(self.root)
            require(current['remote'] or current['root_commit'],
                    'CHECKPOINT_IDENTITY_UNRESOLVABLE: this repository has no remote and no resolvable root '
                    'commit, so a legacy checkpoint cannot be safely accepted here')
            state['repo_identity'] = current
            state['repo_path'] = str(self.root)  # never compared; kept only for an older reader (see CHANGELOG)
        require(allow_branch_change or state['branch'] == git(self.root, 'branch', '--show-current'), 'CHECKPOINT_BRANCH_MISMATCH')
        return state

    def _relocate_plan(self, state, allow_branch_rebind, allow_repository_rename, new_issue, keep_issue_number):
        """Everything a `relocate` decision needs, computed fresh from the
        given `state` -- never from values a caller cached before acquiring
        the lock (round 1, finding 2: `old_identity` and `branch_matches`
        used to be computed once, before the lock, so a concurrent write
        between that read and the lock could make the recorded entry
        describe a `state` that was no longer current by the time it was
        applied). The apply path in `relocate` always calls this on a
        `state` it just read *inside* the lock.

        The rebound issue (`new_issue` in the result) is never chosen
        automatically (round 2, finding N2): a rename or transfer keeps the
        same issue number on GitHub, but a fork's issue numbering is
        independent of the repository it forked from, and there is no
        offline way to tell the two apart. The caller must say which this
        is -- `keep_issue_number` for a rename/transfer, or an explicit
        `new_issue` (`owner/repo#n`, and it must name this repository) for
        anything else, most of all a fork -- or the repository change is
        left blocked pending that choice.
        """
        old_identity = state.get('repo_identity') or {'remote': None, 'root_commit': None,
                                                       'legacy_repo_path': state.get('repo_path')}
        new_identity = repo_identity(self.root)
        current_branch = git(self.root, 'branch', '--show-current')
        branch_matches = state['branch'] == current_branch
        old_repo, old_number = state['issue'].split('#')
        try:
            new_repo = github_repository(self.root)
        except WorkflowError:
            new_repo = None
        repository_renamed = not same_github_repository(new_repo, old_repo)
        resolved_issue = None
        if repository_renamed:
            if new_issue is not None:
                require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9]\d*', new_issue),
                        'RELOCATE_ISSUE_INVALID: --issue must look like owner/repo#N')
                require(new_repo is None or same_github_repository(new_issue.split('#')[0], new_repo),
                        'RELOCATE_ISSUE_REPOSITORY_MISMATCH: --issue must name this repository (' +
                        str(new_repo) + '), not ' + new_issue.split('#')[0])
                resolved_issue = new_issue
            elif keep_issue_number:
                require(new_repo, 'RELOCATE_REPOSITORY_RENAME_NEEDS_GITHUB_REMOTE: this repository has no '
                                  'GitHub remote to rebind the issue to')
                resolved_issue = new_repo + '#' + old_number
        blockers = []
        if state['active']:
            blockers.append('ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_RELOCATE')
        if not branch_matches and not allow_branch_rebind:
            blockers.append('CHECKPOINT_BRANCH_MISMATCH: pass --allow-branch-rebind to also rebind the branch '
                            '(from ' + state['branch'] + ' to ' + current_branch + ')')
        if repository_renamed and not allow_repository_rename:
            blockers.append('REPOSITORY_CHANGED: this checkpoint is bound to issue repository ' + old_repo +
                            ', this repository resolves to ' + (new_repo or '<no GitHub remote>') +
                            '; pass --allow-repository-rename to confirm this is the same project legitimately '
                            'renamed or moved, not a foreign checkpoint')
        elif repository_renamed and not resolved_issue:
            blockers.append('RELOCATE_ISSUE_REQUIRED: this checkpoint is bound to issue ' + state['issue'] +
                            '; a repository rename or transfer keeps the same issue number automatically -- '
                            'pass --keep-issue-number to assume that (never valid for a fork, whose issue '
                            'numbering is independent of what it forked from) -- or pass --issue <owner/repo#n> '
                            'to name the exact new issue directly')
        return {'old_identity': old_identity, 'new_identity': new_identity, 'current_branch': current_branch,
                'branch_matches': branch_matches, 'old_repo': old_repo, 'new_repo': new_repo,
                'repository_renamed': repository_renamed, 'new_issue': resolved_issue, 'blockers': blockers}

    def relocate(self, reason, preview=False, allow_branch_rebind=False, allow_repository_rename=False,
                new_issue=None, keep_issue_number=False, actor=None):
        """Explicit, logged rebind of a checkpoint whose recorded identity no
        longer matches this repository but is legitimately the same project:
        a fork, a renamed remote, or a migrated org (`identity_matches`
        refuses all three on purpose). This is the reviewed escape hatch for
        exactly that refusal, so it must reach the checkpoint despite the
        identity gate -- it reads and writes the file directly rather than
        through `load`/`save`'s identity check, by design.

        Every receipt is preserved untouched and no stage is invalidated:
        relocating never revisits what evidence means, only who owns the
        machine-independent identity it is filed under. A branch mismatch is
        refused unless `allow_branch_rebind` says to rebind that too. A
        checkpoint whose bound issue names a different GitHub repository
        than this one now resolves to is refused the same way unless
        `allow_repository_rename` says this is a real rename or move, not a
        foreign checkpoint being laundered into this repository (round 1,
        finding 2).

        A repository change never rebinds the issue automatically (round 2,
        finding N2): `keep_issue_number` says this is a GitHub rename or
        transfer, where the issue number carries over -- never valid for a
        fork, whose issue numbering is independent of what it forked from
        and would otherwise silently claim the wrong issue there -- and
        `new_issue` (`owner/repo#n`, which must name this repository) says
        exactly which issue to bind instead. Passing neither leaves a real
        repository change blocked pending that choice; passing both is
        refused outright. `scope-source.json` is rebound in the same locked
        write as the checkpoint (round 2, finding N3), so a later `start`
        for the same issue does not fail `FEATURE_BINDING_MISMATCH` against
        a source file still naming the old repository -- either both are
        written or neither is, since the checkpoint write happens last.

        Either way, the whole decision is appended to `relocations[]` with
        its actor, reason and both identities/repositories, never silently.
        """
        require_not_delegated_context('relocate')
        require(isinstance(reason, str) and reason.strip(), 'RELOCATE_REASON_REQUIRED')
        require(not (new_issue and keep_issue_number),
                'RELOCATE_ISSUE_OPTIONS_CONFLICT: pass --issue or --keep-issue-number, not both')
        if preview:
            state = read(self.path)
            require(state and state.get('schema_version') == SCHEMA, 'WORKFLOW_START_REQUIRED')
            require(state['feature'] == self.relative, 'RELOCATE_FEATURE_MISMATCH')
            plan = self._relocate_plan(state, allow_branch_rebind, allow_repository_rename, new_issue, keep_issue_number)
            return {'preview': True, 'feature': self.relative, 'old_identity': plan['old_identity'],
                    'new_identity': plan['new_identity'], 'branch_from': state['branch'],
                    'branch_to': plan['current_branch'], 'branch_matches': plan['branch_matches'],
                    'allow_branch_rebind': allow_branch_rebind, 'old_repository': plan['old_repo'],
                    'new_repository': plan['new_repo'], 'repository_renamed': plan['repository_renamed'],
                    'allow_repository_rename': allow_repository_rename, 'new_issue': plan['new_issue'],
                    'blockers': plan['blockers'], 'can_apply': not plan['blockers']}
        with locked(self.lock):
            state = read(self.path)
            require(state and state.get('schema_version') == SCHEMA, 'WORKFLOW_START_REQUIRED')
            require(state['feature'] == self.relative, 'RELOCATE_FEATURE_MISMATCH')
            require(not state['active'], 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_RELOCATE')
            plan = self._relocate_plan(state, allow_branch_rebind, allow_repository_rename, new_issue, keep_issue_number)
            require(not plan['blockers'], '; '.join(plan['blockers']))
            entry = {'actor': actor or default_actor(self.root), 'at': now(), 'reason': reason.strip(),
                     'old_identity': plan['old_identity'], 'new_identity': plan['new_identity'],
                     'branch_rebound': False}
            if not plan['branch_matches']:
                entry.update(branch_rebound=True, branch_from=state['branch'], branch_to=plan['current_branch'])
                state['branch'] = plan['current_branch']
            if plan['repository_renamed']:
                entry.update(repository_renamed=True, old_repository=plan['old_repo'],
                            new_repository=plan['new_repo'], new_issue=plan['new_issue'])
                # `scope-source.json` binds the same issue independently (`start`,
                # `bind` and the scope extension's `bound_claim` all compare it);
                # rebind it here too, before the checkpoint write below, so a
                # crash between the two never leaves the checkpoint looking
                # relocated while scope-source.json still names the old repo --
                # re-running relocate afterwards recomputes and rewrites both
                # identically, so this is safe to retry.
                source_path = self.feature / 'scope-source.json'
                source = read(source_path, {})
                if source:
                    new_owner_repo, new_number = plan['new_issue'].split('#')
                    write(source_path, {**source, 'repo': new_owner_repo, 'issue': int(new_number)})
                state['issue'] = plan['new_issue']
            state['repo_path'] = str(self.root)  # never compared; kept only for an older reader (see CHANGELOG)
            state['repo_identity'] = plan['new_identity']
            state.setdefault('relocations', []).append(entry)
            self.save(state)
            return {'relocated': True, 'feature': self.relative, 'relocation': copy.deepcopy(entry)}

    def bind(self, token):
        with locked(self.lock):
            state = self.load(allow_branch_change=True)
            require(state['active'] and state['active']['stage'] == 'specify' and state['active']['token'] == token, 'SPECIFY_CLAIM_REQUIRED')
            source = read(self.feature / 'scope-source.json', {})
            require(f"{source.get('repo')}#{source.get('issue')}" == state['issue'], 'FEATURE_BINDING_MISMATCH')
            require((self.feature / 'spec.md').is_file(), 'SPECIFICATION_MISSING')
            branch = git(self.root, 'branch', '--show-current')
            require(branch, 'DETACHED_HEAD_UNSUPPORTED')
            state.setdefault('branch_history', []).append({'from': state['branch'], 'to': branch, 'at': now()})
            state['branch'] = branch
            self.save(state)
            return {'bound': True, 'branch': branch, 'feature': self.relative}

    def migrate(self, reason, invalidate_from=None):
        """Preserve immutable historical evidence; invalidate changed command contracts.

        An upgrade can change the policy as well as the packages: a release that
        adds a policy section leaves every checkpoint bound to the previous
        policy hash, which the CI gate reads as `POLICY_CHANGED` on a feature
        whose work never changed. A reviewed migration therefore rebinds the
        checkpoint to the current policy, invalidating exactly the stages the
        policy cutoff says a semantic change reached and preserving the rest.
        """
        with locked(self.lock):
            state = self.load()
            require(not state['active'], 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_UPGRADE')
            health = doctor(self.root, self.policy)
            require(health['ok'], '; '.join(health['errors']))
            require(isinstance(reason, str) and reason.strip(), 'MIGRATION_REASON_REQUIRED')
            plan = self.migration_plan(state, invalidate_from)
            ensure_local_excludes(self.root)
            write(self.path.parent / 'backups' / (uuid.uuid4().hex + '.json'), state)
            entry = {'reason': reason, 'from': plan['from'], 'to': plan['to'], 'at': now(),
                     'policy_from': plan['policy_from'], 'policy_to': plan['policy_to'],
                     'invalidated': plan['invalidated'], 'preserved_as_historical': plan['preserved_as_historical']}
            state.setdefault('migrations', []).append(entry)
            state['dependency_digest'] = plan['to']
            state['commands'] = plan['commands']
            state['policy_digest_version'] = POLICY_DIGEST_VERSION
            state['ci_policy_digest'] = digest(self.policy['ci'])
            if plan['policy_to'] != plan['policy_from']:
                state.setdefault('policy_changes', []).append({'from': plan['policy_from'], 'to': plan['policy_to'],
                                                               'at': now(), 'via': 'migrate', 'reason': reason})
                state['policy_digest'] = plan['policy_to']
                state['policy'] = copy.deepcopy(self.policy)
            for stage in plan['invalidated']: state['receipts'].pop(stage)
            self.save(state)
            return {'migrated': True, 'migration': copy.deepcopy(entry), 'next': self.next(state)}

    def migration_plan(self, state, invalidate_from=None):
        """What a migration of this checkpoint would record, computed without writing.

        `preview_migration` and `migrate` share this, so the reviewed lists are
        exactly the lists the write records.
        """
        if invalidate_from:
            require(invalidate_from in BASE_STAGES, 'INVALID_MIGRATION_STAGE')
        old_policy_digest = state['policy_digest']
        policy_digest = delivery_digest(self.policy)
        commands = resolve_commands(self.root, self.policy)
        changed = [stage for stage in stages(self.policy) if state['commands'].get(stage) != commands[stage]]
        if policy_digest != old_policy_digest:
            reached = policy_cutoff(state.get('policy'), self.policy)
            if reached < len(BASE_STAGES): changed.append(BASE_STAGES[reached])
        if invalidate_from:
            changed.append(invalidate_from)
        cutoff = min((BASE_STAGES.index(stage) for stage in changed), default=len(BASE_STAGES))
        invalidated = [stage for stage in state['receipts'] if BASE_STAGES.index(stage) >= cutoff]
        return {'from': state['dependency_digest'], 'to': package_digest(self.root),
                'policy_from': old_policy_digest, 'policy_to': policy_digest,
                'commands': commands, 'changed_commands': sorted(
                    stage for stage in stages(self.policy) if state['commands'].get(stage) != commands[stage]),
                'invalidated': invalidated,
                'preserved_as_historical': [s for s in state['receipts'] if s not in invalidated]}

    def preview_migration(self, invalidate_from=None):
        """Non-mutating migrate: the exact lists the write would record, and what
        would stop it. Loads through the same bound-branch check as `migrate`."""
        state = self.load()
        plan = self.migration_plan(state, invalidate_from)
        blockers = []
        if state['active']:
            blockers.append('ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_UPGRADE')
        blockers += doctor(self.root, self.policy)['errors']
        return {'preview': True, 'feature': self.relative, 'invalidated': plan['invalidated'],
                'preserved_as_historical': plan['preserved_as_historical'],
                'dependency_from': plan['from'], 'dependency_to': plan['to'],
                'policy_from': plan['policy_from'], 'policy_to': plan['policy_to'],
                'changed_commands': plan['changed_commands'], 'blockers': blockers, 'can_apply': not blockers}

    def refresh(self, stage, reason):
        """Explicit invocation rereads remote requirements even when local files are unchanged."""
        require(stage in ('scope', 'clarify'), 'REFRESH_STAGE_UNSUPPORTED')
        with locked(self.lock):
            state = self.load()
            require(not state['active'], 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_REFRESH')
            require(reason.strip(), 'REFRESH_REASON_REQUIRED')
            cutoff = BASE_STAGES.index(stage)
            affected = {name: receipt for name, receipt in state['receipts'].items() if BASE_STAGES.index(name) >= cutoff}
            if affected:
                ensure_local_excludes(self.root)
                backup = self.path.parent / 'backups' / (uuid.uuid4().hex + '.json')
                write(backup, state)
                state.setdefault('refreshes', []).append({'stage': stage, 'reason': reason, 'at': now(),
                                                         'invalidated': list(affected), 'backup': str(backup.relative_to(self.root))})
                for name in affected: state['receipts'].pop(name)
                self.save(state)
            return {'refreshed': list(affected), 'next': self.next(state)}

    def amend(self, stage, evidence, reason, assessment, actor=None):
        """Re-hash one evidence entry of a completed receipt under a recorded assessment.

        Every other fingerprint keeps its hash. `unchanged` asserts the stage's
        conclusion and claimed checks still hold (an editorial fix); `changed`
        says they moved, so the receipts resting on them (verify, review, ready,
        from the amended stage on) are marked stale and must be re-recorded.
        """
        require(stage in BASE_STAGES, 'INVALID_AMEND_STAGE: ' + str(stage))
        require(assessment in AMENDMENT_ASSESSMENTS, 'AMENDMENT_ASSESSMENT_INVALID: expected unchanged or changed')
        require(isinstance(reason, str) and reason.strip(), 'AMENDMENT_REASON_REQUIRED')
        with locked(self.lock):
            state = self.load()
            require(not state['active'], 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_AMEND')
            receipt = state['receipts'].get(stage)
            require(receipt, 'RECEIPT_MISSING: ' + stage)
            require(evidence in receipt.get('evidence', []) and evidence in receipt.get('fingerprints', {}),
                    'AMEND_PATH_NOT_EVIDENCE: ' + str(evidence) + ' is not listed as evidence of ' + stage)
            inside(self.root, evidence)
            new_hash = fingerprint_files(self.root, [evidence])[evidence]
            require(new_hash is not None, 'EVIDENCE_MISSING: ' + evidence)
            old_hash = receipt['fingerprints'][evidence]
            require(new_hash != old_hash, 'AMENDMENT_NOT_NEEDED: ' + evidence + ' still matches the receipt')
            ensure_local_excludes(self.root)
            write(self.path.parent / 'backups' / (uuid.uuid4().hex + '.json'), state)
            record = {'path': evidence, 'old_hash': old_hash, 'new_hash': new_hash, 'reason': reason.strip(),
                      'assessment': assessment, 'actor': actor or default_actor(self.root), 'at': now()}
            staled = []
            if assessment == 'changed':
                for name in AMENDMENT_DEPENDENTS:
                    if BASE_STAGES.index(name) >= BASE_STAGES.index(stage) and name in state['receipts']:
                        state['receipts'][name]['stale'] = {'reason': 'evidence-amended', 'stage': stage,
                                                            'path': evidence, 'at': record['at']}
                        staled.append(name)
            record['staled'] = staled
            receipt['fingerprints'][evidence] = new_hash
            receipt.setdefault('amendments', []).append(record)
            self.save(state)
            return {'amended': True, 'stage': stage, 'amendment': copy.deepcopy(record),
                    'current': receipt_current(self.root, self.relative, stage, receipt, self.policy),
                    'stale': staled, 'next': self.next(state)}

    def revalidate(self, stage, check_run=None, attempt=None, diff_reviewed=None, base_ref=None, reason=None,
                   actor=None, github=None):
        """Make a Verify, Review or Ready receipt current after source drift, through a check.

        Nothing is re-stamped on a note: `verify` needs a successful CI run
        (`--check-run`) on the current source key whose lanes cover every lane
        the drift affects, `review` a recorded incremental review of
        `git diff <review head>..HEAD` (`--diff-reviewed`), and `ready` passes
        the Ready checks again. Explicit fingerprints must still byte-match and
        are never re-hashed; `blocking_findings` and the stage's own evidence
        are kept. A lane gap is recorded and keeps the Verify receipt stale.
        """
        require(stage in SOURCE_STAGES, 'REVALIDATE_STAGE_UNSUPPORTED: verify, review or ready')
        require((check_run is not None) == (stage == 'verify'), 'REVALIDATE_VERIFY_NEEDS_CHECK_RUN: '
                '--check-run <run id> applies to, and is required by, --stage verify')
        require((diff_reviewed is not None) == (stage == 'review'), 'REVALIDATE_REVIEW_NEEDS_DIFF_REVIEW: '
                '--diff-reviewed <evidence> applies to, and is required by, --stage review')
        with locked(self.lock):
            state = self.load()
            require(not state['active'], 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_REVALIDATE')
            require(stage in stages(self.policy), 'STAGE_NOT_SELECTED: ' + stage)
            receipt = state['receipts'].get(stage)
            require(receipt, 'RECEIPT_MISSING: ' + stage)
            if state['policy_digest'] != checkpoint_policy_digest(state, self.policy):
                require(BASE_STAGES.index(stage) < policy_cutoff(state.get('policy'), self.policy),
                        'POLICY_CHANGED: the policy change reaches ' + stage + '; re-record it')
            for earlier in stages(self.policy)[:stages(self.policy).index(stage)]:
                prior = state['receipts'].get(earlier)
                require(prior, 'EARLIER_STAGE_NOT_CURRENT: ' + earlier + ' has no receipt')
                prior_status = receipt_status(self.root, self.relative, earlier, prior, self.policy)
                require(prior_status['current'], 'EARLIER_STAGE_NOT_CURRENT: ' + earlier + ' (make it current before ' +
                        stage + '). Recovery: ' + ' | '.join(
                            recovery_recipe(self.relative, earlier, prior_status, self.policy, prior)))
            mark = receipt.get('stale')
            require(not mark or (stage == 'verify' and mark.get('reason') == 'ci-lane-gap'),
                    'RECEIPT_MARKED_STALE: ' + json.dumps(mark) + '; a changed amendment needs a re-record')
            status = receipt_status(self.root, self.relative, stage, {**receipt, 'stale': None}, self.policy)
            if status.get('reason') == 'explicit-drift':
                raise WorkflowError('EXPLICIT_FINGERPRINTS_CHANGED: ' + json.dumps(status['paths']) +
                                    '; revalidation never re-hashes inputs or evidence. Recovery: ' +
                                    ' | '.join(recovery_recipe(self.relative, stage, status, self.policy, receipt)))
            require(not status['current'] or mark, 'REVALIDATION_NOT_NEEDED: ' + stage + ' is current')
            dirty = sk.dirty_source_paths(self.root)
            require(not dirty, 'SOURCE_TREE_DIRTY: commit or stash source changes first: ' + ', '.join(dirty[:10]))
            head, key = git(self.root, 'rev-parse', 'HEAD'), sk.source_key(self.root, 'HEAD')
            inventory = source_fingerprints(self.root)
            drift = source_drift(receipt, inventory)
            explicit = sorted(set(drift) & set(receipt.get('fingerprints', {})))
            require(not explicit, 'EXPLICIT_FINGERPRINTS_CHANGED: ' + json.dumps(explicit) +
                    ' drifted as source and are explicit fingerprints of ' + stage + '; re-record it')
            record = {'via': {'verify': 'check-run', 'review': 'diff-review', 'ready': 'ready-checks'}[stage],
                      'at': now(), 'actor': actor or default_actor(self.root), 'reason': reason,
                      'from': {'head': receipt.get('head'), 'source_key': receipt.get('source_key')},
                      'to': {'head': head, 'source_key': key}, 'drift': drift}
            if stage == 'verify':
                evidence, lanes = self.check_run_evidence(state, receipt, check_run, attempt, head, key, drift, github)
                record.update(run_id=evidence['run_id'], attempt=evidence['attempt'],
                              required_lanes=evidence['required_lanes'], lanes=evidence['lanes'],
                              lane_gap=lanes['gap'], lanes_by_path=lanes['by_path'])
                if lanes['gap']:
                    record['outcome'] = 'stale'
                    ensure_local_excludes(self.root)
                    write(self.path.parent / 'backups' / (uuid.uuid4().hex + '.json'), state)
                    receipt['stale'] = {'reason': 'ci-lane-gap', 'stage': 'verify', 'lanes': lanes['gap'],
                                        'run_id': evidence['run_id'], 'at': record['at']}
                    receipt.setdefault('revalidations', []).append(record)
                    self.save(state)
                    return {'revalidated': False, 'stage': stage, 'lane_gap': lanes['gap'],
                            'run_id': evidence['run_id'], 'revalidation': copy.deepcopy(record),
                            'recovery': recovery_recipe(self.relative, stage, {'reason': 'marked-stale',
                                                        'stale': receipt['stale']}, self.policy, receipt),
                            'next': self.next(state)}
                receipt['ci_evidence'] = evidence
            elif stage == 'review':
                receipt['diff_reviewed'] = self.diff_review_evidence(receipt, diff_reviewed, head)
                path = receipt['diff_reviewed']['evidence']
                record['evidence'] = path
                if path not in receipt['evidence']:
                    receipt['evidence'].append(path)
                receipt['fingerprints'][path] = receipt['diff_reviewed']['hash']
            else:
                try:
                    record['checks'] = ready_checks(self.root, self.relative, self.policy, state,
                                                    base_ref or state.get('target_branch'))
                except Exception as exc:  # the task parser raises the importing module's error class
                    if type(exc).__name__ != 'WorkflowError':
                        raise
                    raise WorkflowError('READY_CHECKS_FAILED: ' + str(exc)) from exc
            record['outcome'] = 'current'
            ensure_local_excludes(self.root)
            write(self.path.parent / 'backups' / (uuid.uuid4().hex + '.json'), state)
            receipt.pop('stale', None)
            receipt['source_fingerprints'] = inventory
            receipt['head'], receipt['source_key'] = head, key
            receipt.setdefault('revalidations', []).append(record)
            self.save(state)
            return {'revalidated': True, 'stage': stage, 'revalidation': copy.deepcopy(record),
                    'current': receipt_current(self.root, self.relative, stage, receipt, self.policy),
                    'next': self.next(state)}

    def check_run_evidence(self, state, receipt, run_id, attempt, head, key, drift, github=None):
        """Read and validate one CI run as Verify evidence (the A9a plan contract).

        Returns the `ci_evidence` record and the lane coverage: the lanes the
        affected-lane hook assigns to the drifted source paths must all be in
        the run's lanes, otherwise the gap is returned for the caller to record.
        """
        import ci_evidence
        check = verification_check(self.policy)
        require(check, 'CI_VERIFICATION_CHECK_UNSET: set ci.gate.verification_check to the job that certifies '
                       'a verification run (e.g. "Bootstrap required lanes")')
        require(re.fullmatch(r'[1-9]\d*', str(run_id)), 'CHECK_RUN_ID_INVALID: ' + str(run_id))
        require(attempt is None or re.fullmatch(r'[1-9]\d*', str(attempt)), 'CHECK_RUN_ATTEMPT_INVALID')
        command = affected_command(self.policy)
        require(command or not drift, 'CI_AFFECTED_COMMAND_REQUIRED: the lanes the source drift affects cannot be '
                                      'established without ci.gate.affected_command; re-record Verify instead')
        by_path = affected_lanes(self.root, command, drift) if drift else {}
        required = sorted({lane for lanes in by_path.values() for lane in lanes})
        repository = github_repository(self.root)
        client = github or ci_evidence.GhClient()
        try:
            evidence = ci_evidence.collect(client, repository, int(run_id), attempt and int(attempt),
                                           check['artifact_prefix'])
        except ci_evidence.EvidenceError as exc:
            raise WorkflowError('CHECK_RUN_UNREADABLE: ' + str(exc)) from exc
        plan = evidence['plan'] if isinstance(evidence['plan'], dict) else {}
        local = None
        if isinstance(plan.get('headSha'), str) and ci_evidence.SHA.match(plan['headSha']):
            try:
                local = {'tree': sk.tree_of(self.root, plan['headSha']), 'key': sk.source_key(self.root, plan['headSha'])}
            except sk.SourceKeyError:
                local = {'tree': 'unavailable (fetch ' + plan['headSha'] + ')', 'key': 'unavailable'}
        errors = ci_evidence.validate(evidence, repository, int(run_id), check['name'], check['workflow'],
                                      attempt and int(attempt), local, check['artifact_prefix'])
        if not errors and plan['headSha'] != head:
            ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', plan['headSha'], head], cwd=self.root,
                                      capture_output=True)
            if ancestor.returncode != 0:
                errors.append(f'Run head {plan["headSha"]} is not a commit of this branch (an ancestor of {head}).')
        if not errors and plan['sourceKey'] != key:
            errors.append(f'Run {run_id} verified source key {plan["sourceKey"]}, not the current {key}: the source '
                          f'changed after {plan["headSha"]}; use a run on a commit with the current source.')
        require(not errors, 'CHECK_RUN_REJECTED: run ' + str(run_id) + ': ' + ' '.join(errors))
        gap = sorted(set(required) - set(plan['lanes']))
        record = {'run_id': int(run_id), 'attempt': int(evidence['attempt']), 'head': plan['headSha'],
                  'source_key': plan['sourceKey'], 'tier': plan['tier'], 'lanes': list(plan['lanes']),
                  'conclusion': 'success', 'check': check['name'], 'artifact': evidence['artifact'],
                  'event': plan.get('event'), 'pull_request': plan.get('pullRequest'),
                  'required_lanes': required, 'lane_gap': [], 'at': now()}
        return record, {'gap': gap, 'by_path': {path: lanes for path, lanes in by_path.items() if lanes}}

    def diff_review_evidence(self, receipt, evidence, head):
        """A recorded incremental review of the source diff `<review head>..HEAD`.

        The file lives in the feature directory (portable, outside the source
        key) and carries four lines: `Diff reviewed: <review head>..<HEAD>`,
        `Diff sha256: <hash>` (the SHA-256 of the bytes `diff_review_command`
        prints for that range, which binds the note to the exact diff so it
        cannot be written blind or reused for another), a non-empty
        `Reviewer: <name>` and `Blocking findings: 0`.
        """
        base = receipt.get('head')
        require(base, 'RECEIPT_HEAD_UNKNOWN: this review receipt predates 1.6.0 and records no head to diff from; '
                      're-record Review')
        require(isinstance(evidence, str) and evidence.startswith(self.relative + '/'),
                'DIFF_REVIEW_EVIDENCE_OUTSIDE_FEATURE: record it under ' + self.relative + '/')
        path = inside(self.root, evidence)
        require(path.is_file(), 'EVIDENCE_MISSING: ' + evidence)
        require(base != head, 'DIFF_REVIEW_EMPTY: the review head is HEAD; nothing was committed to review')
        require(subprocess.run(['git', 'merge-base', '--is-ancestor', base, head], cwd=self.root,
                               capture_output=True).returncode == 0,
                'DIFF_REVIEW_BASE_NOT_ANCESTOR: ' + base + ' is not an ancestor of HEAD; re-record Review')
        text = path.read_text(encoding='utf-8-sig', errors='replace')
        marks = r'[\s*_`]*'
        ranges = re.findall(r'(?im)^\W*Diff reviewed:' + marks + r'([0-9a-f]{7,40})' + marks + r'\.\.' + marks +
                            r'([0-9a-f]{7,40})', text)
        require(any(base.startswith(old) and head.startswith(new) for old, new in ranges),
                'DIFF_REVIEW_RANGE_MISSING: ' + evidence + ' must name the reviewed range on a line '
                '"Diff reviewed: ' + base + '..' + head + '"')
        require(re.search(r'(?im)^\W*Blocking findings:' + marks + r'0\b', text),
                'DIFF_REVIEW_OUTCOME_MISSING: ' + evidence + ' must state "Blocking findings: 0"')
        # Within the line only: an empty "Reviewer:" must not borrow the next line.
        reviewers = [value.strip(' \t*_`') for value in re.findall(r'(?im)^[^\w\n]*Reviewer:[ \t*_`]*(.*)$', text)]
        reviewers = [value for value in reviewers if value]
        require(reviewers, 'DIFF_REVIEW_REVIEWER_MISSING: ' + evidence + ' must name who reviewed the diff on a '
                           'line "Reviewer: <name>"')
        expected = diff_review_sha256(self.root, base, head)
        recipe = ('compute it with: ' + diff_review_shell(base, head) + ' | sha256sum  (in a POSIX shell such as '
                  'Git Bash: the hash is of the exact bytes), review that diff, and record the hash on the line '
                  '"Diff sha256: <hash>"')
        hashes = [value.lower() for value in
                  re.findall(r'(?im)^\W*Diff sha256:' + marks + r'([0-9a-f]{64})\b', text)]
        require(hashes, 'DIFF_REVIEW_HASH_MISSING: ' + evidence + ' must bind the review to the diff on a line '
                        '"Diff sha256: <hash>". Recovery: ' + recipe)
        require(expected in hashes, 'DIFF_REVIEW_HASH_MISMATCH: ' + evidence + ' records Diff sha256 ' +
                ', '.join(hashes) + ', which is not the hash of the diff ' + base + '..' + head +
                ' (a stale note, or a note for another diff). Recovery: ' + recipe)
        return {'evidence': evidence, 'base': base, 'head': head, 'diff_sha256': expected, 'reviewer': reviewers[0],
                'hash': fingerprint_files(self.root, [evidence])[evidence], 'at': now()}

    def start(self, issue):
        require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9]\d*', issue), 'EXPLICIT_ISSUE_REQUIRED')
        require(same_github_repository(github_repository(self.root), issue.split('#')[0]), 'ISSUE_REPOSITORY_MISMATCH')
        source = read(self.feature / 'scope-source.json', {})
        require(not source or f"{source.get('repo')}#{source.get('issue')}" == issue, 'FEATURE_BINDING_MISMATCH')
        with locked(self.lock):
            if self.path.exists():
                state = self.load()
                require(state['issue'] == issue, 'ISSUE_BINDING_CONFLICT')
                return state
            commands = resolve_commands(self.root, self.policy)
            state = {'schema_version': SCHEMA, 'run_id': uuid.uuid4().hex, 'repo_identity': repo_identity(self.root),
                     # `repo_path` is never read or compared by this version; it is written only so an
                     # older reader (pre-1.8.0) does not KeyError on a checkpoint this version writes.
                     # Slated for removal once no supported release still needs it (see CHANGELOG).
                     'repo_path': str(self.root),
                     'branch': git(self.root, 'branch', '--show-current'), 'feature': self.relative,
                     'issue': issue, 'policy_digest_version': POLICY_DIGEST_VERSION,
                     'policy_digest': delivery_digest(self.policy),
                     'ci_policy_digest': digest(self.policy['ci']), 'commands': commands,
                     'policy': copy.deepcopy(self.policy), 'target_branch': previous_branch(self.root),
                     'receipts': {}, 'generation': 0, 'active': None, 'status': 'in-progress'}
            state['dependency_digest'] = package_digest(self.root)
            self.save(state)
            return state

    def save(self, state):
        state['generation'] += 1
        state['updated_at'] = now()
        state['head'] = git(self.root, 'rev-parse', 'HEAD')
        write(self.path, state)

    def next(self, state, finalize=False):
        result = self.next_stage(state, finalize)
        drift = consulted_drift(self.root, self.relative, state['receipts'])
        if drift:
            # Advisory only: a consulted input never stales its receipt.
            result['advisory_drift'] = drift
        return result

    def next_stage(self, state, finalize=False):
        policy_changed = state['policy_digest'] != checkpoint_policy_digest(state, self.policy)
        cutoff = policy_cutoff(state.get('policy'), self.policy) if policy_changed else len(BASE_STAGES)
        for stage in stages(self.policy):
            receipt = state['receipts'].get(stage)
            if receipt and BASE_STAGES.index(stage) >= cutoff:
                return {'stage':stage,'command':state['commands'][stage],'reason':'policy-changed'}
            if receipt:
                status = receipt_status(self.root, self.relative, stage, receipt, self.policy)
                if status['current']:
                    continue
                return {'stage': stage, 'reason': 'inputs-or-evidence-changed',
                        'recovery': recovery_recipe(self.relative, stage, status, self.policy, receipt)}
            if stage == 'pr' and not finalize:
                return {'stage': None, 'status': 'ready_to_finalize', 'command': 'speckit.workflow.finalize'}
            return {'stage': stage, 'command': state['commands'][stage], 'reason': 'pending'}
        return {'stage': None, 'status': 'pr_open'}

    def claim(self, usage, finalize=False):
        with locked(self.root / '.specify/workflow/runtime/dispatch.lock'), locked(self.lock):
            require(not (self.root / '.specify/workflow/runtime/upgrade.lock').exists(), 'WORKFLOW_UPGRADE_IN_PROGRESS')
            state = self.load()
            require(not state['active'], 'STAGE_ALREADY_ACTIVE: recover or finish the recorded claim')
            for path in (self.root / 'specs').glob('*/workflow/checkpoint.json'):
                require(path == self.path or not read(path, {}).get('active'), 'OTHER_FEATURE_STAGE_ACTIVE: ' + str(path))
            require(state['dependency_digest'] == package_digest(self.root), 'DEPENDENCY_CHANGED: review upgrade and migrate the checkpoint before execution')
            # Delegation health is checked below, after every rejection, because
            # the claim may install the skill it would otherwise report missing.
            health = doctor(self.root, self.policy, project=True, check_delegation=False)
            require(health['ok'], '; '.join(health['errors']))
            gate = context_gate(self.policy, usage)
            if gate['pause']:
                return self.checkpoint(state, 'context-budget', gate)
            nxt = self.next(state, finalize)
            if not nxt.get('stage'):
                return nxt
            stage = nxt['stage']
            if self.policy['delegation']['enabled']:
                # Side effects only once a stage will be claimed: a rejected claim
                # leaves tasks.md and every skill location untouched.
                from delegation import annotate_tasks, doctor as delegation_doctor, health_error
                delegation_health = delegation_doctor(self.root, active_host(self.root), install=True,
                                                      scope=self.policy['delegation']['install_scope'])
                require(delegation_health['ok'], health_error(delegation_health))
                require(any(delegation_health['harnesses'].values()),
                        'DELEGATE_AGENT_CLI_UNAVAILABLE: no supported Codex or Claude CLI')
                annotate_tasks(self.root, self.relative, self.policy['delegation'])
                notices = delegation_health.get('notices') or []
            else:
                notices = []
            current_policy_digest = checkpoint_policy_digest(state, self.policy)
            if state['policy_digest'] != current_policy_digest:
                state.setdefault('policy_changes', []).append({'from':state['policy_digest'],'to':current_policy_digest,'at':now()})
                state['policy_digest'] = current_policy_digest
                state['policy'] = copy.deepcopy(self.policy)
                state['commands'] = resolve_commands(self.root, self.policy)
            for downstream in BASE_STAGES[BASE_STAGES.index(stage):]:
                state['receipts'].pop(downstream, None)
            state['active'] = {'stage': stage, 'token': uuid.uuid4().hex, 'claimed_at': now(),
                               'session_id': usage['session_id'], 'context': gate}
            source = read(self.feature / 'scope-source.json', {})
            existing = (self.feature / 'spec.md').is_file() and f"{source.get('repo')}#{source.get('issue')}" == state['issue']
            state['active']['mode'] = 'revalidate' if existing and stage in ('scope', 'specify', 'clarify', 'plan', 'tasks') else 'initial'
            if self.policy['delegation']['enabled']:
                from delegation import selected_route, stage_work_type
                work_type = stage_work_type(state['commands'], stage,
                                            self.policy['delegation'].get('fixed_collection_commands'))
                state['active']['delegation'] = {
                    'identity': self.relative + '/stage:' + stage,
                    'task_type': work_type,
                    'candidates': selected_route(self.policy['delegation'], work_type, active_host(self.root)),
                }
            state['active']['baseline'] = fingerprint_files(self.root, [p for r in state['receipts'].values() for p in r['fingerprints']])
            state['status'] = 'in-progress'
            write(self.root / '.specify/feature.json', {'feature_directory': self.relative})
            self.save(state)
            claimed = {**state['active'], 'command': state['commands'][stage], 'feature': self.relative, 'issue': state['issue'],
                       'reference': stage_reference(stage)}
            if notices:
                # Reported to the caller only; the checkpoint keeps the claim itself.
                claimed['notices'] = notices
            return claimed

    def complete(self, token, receipt):
        with locked(self.lock):
            state = self.load()
            active = state['active']
            require(active and active['token'] == token, 'CLAIM_TOKEN_MISMATCH')
            stage = active['stage']
            require(receipt.get('stage') == stage and receipt.get('outcome') == 'passed', 'STAGE_NOT_PASSED')
            require(receipt.get('summary') and receipt.get('evidence'), 'EVIDENCE_REQUIRED')
            require(isinstance(receipt.get('inputs'), list) and receipt['inputs'], 'INPUT_MANIFEST_REQUIRED')
            require(not any(field in receipt for field in RUNTIME_RECEIPT_FIELDS),
                    'RECEIPT_FIELD_RESERVED: ' + ', '.join(f for f in RUNTIME_RECEIPT_FIELDS if f in receipt))
            validate_input_roles(self.root, self.relative, stage, receipt, self.policy)
            for path in receipt['evidence']:
                require(inside(self.root, path).is_file(), 'EVIDENCE_MISSING: ' + path)
            delegation_ledger_trust = None
            if self.policy['delegation']['enabled'] and active.get('delegation'):
                # The claim recorded a delegation route for this stage; require the
                # dispatcher's own ledger (never the receipt's self-report) to show
                # the delegated attempt actually succeeded, following any reassignment
                # to its terminal end (finding 1: the guard was previously unread).
                # The ledger itself must still be trustworthy: 'untrusted' (a
                # genuine, persisted tamper, or a marker that disagrees with the
                # current bytes) refuses; 'unverified-local' (no local write
                # marker at all -- the normal state for a CI checkout or a fresh
                # clone) is recorded on the receipt as a warning, not a block
                # (round 3, findings 1-2). The attempt must also have been
                # started under this exact claim (finding 2a, round 2): a
                # successful attempt left over from an earlier claim of this
                # same stage (for example one abandoned and re-claimed) must
                # not satisfy a different, later claim it was never part of.
                from delegation import latest_attempt, ledger_trust_state
                delegation_ledger_trust = ledger_trust_state(self.root, self.relative)
                require(delegation_ledger_trust != 'untrusted',
                        'DELEGATION_LEDGER_UNTRUSTED: the delegation ledger for ' + self.relative +
                        ' was tampered with (a hand-edit, or one not yet cleared by trust-reset); run '
                        '"delegate_dispatch.py trust-reset --feature ' + self.relative +
                        ' --reason <text>" only after reviewing exactly what changed')
                stage_attempt = latest_attempt(self.root, self.relative, 'stage:' + stage)
                require(stage_attempt is not None and stage_attempt.get('status') == 'successful' and
                        stage_attempt.get('claim_token') == token,
                        'DELEGATION_STAGE_NOT_VERIFIED: the latest delegate_dispatch attempt for stage:' +
                        stage + ' is ' + (str(stage_attempt.get('status')) if stage_attempt else 'missing') +
                        ' or was not started under this claim; collect, accept or reassign it before '
                        'completing this stage. A legacy attempt recorded before claim_token existed has '
                        'none and will never match; re-delegate the stage once under this workflow release')
            if stage == 'clarify':
                require(receipt.get('unresolved') == 0 and receipt.get('answers_applied') is True, 'CLARIFICATION_UNRESOLVED')
            if BASE_STAGES.index(stage) >= BASE_STAGES.index('specify'):
                source = read(self.feature / 'scope-source.json', {})
                require(f"{source.get('repo')}#{source.get('issue')}" == state['issue'], 'FEATURE_BINDING_MISMATCH')
            ledger_path = self.feature / 'workflow/decisions.json'
            if ledger_path.is_file():
                from decisions import reconcile, verify_ledger
                verify_ledger(self.root, self.relative, reconcile(self.root, self.relative))
            if stage == 'taskstoissues':
                require(receipt.get('parent_issue') == state['issue'] and receipt.get('native_links_verified') is True, 'TASK_PARENT_NOT_VERIFIED')
            if stage in SOURCE_STAGES:
                require(receipt.get('blocking_findings') == 0, 'BLOCKING_FINDINGS_REMAIN')
            if stage == 'pr':
                require(receipt.get('images_verified') is True and receipt.get('pr_url', '').startswith('https://github.com/' + state['issue'].split('#')[0] + '/pull/'), 'PR_EVIDENCE_INCOMPLETE')
            if stage in ('tasks', 'qa_analyze', 'manual_analyze') and self.policy['delegation']['enabled']:
                from delegation import annotate_tasks
                annotate_tasks(self.root, self.relative, self.policy['delegation'])
            # Known semantic transformations advance upstream artifact snapshots with an
            # explicit lineage record. They do not pretend the old artifact remained current.
            permitted = {'clarify': ['spec.md'], 'qa_analyze': ['tasks.md'], 'manual_analyze': ['tasks.md']}.get(stage, [])
            after = fingerprint_files(self.root, active['baseline'])
            changed = [p for p, before in active['baseline'].items() if after[p] != before]
            # Only an earlier receipt's dependency can be undermined by this stage.
            # A path every earlier receipt only consulted keeps its recorded hash
            # (nothing is re-stamped) and `next` reports it as advisory drift.
            dependencies = set()
            for name, prior in state['receipts'].items():
                dependencies.update(dependency_fingerprints(prior, required_inputs(self.root, self.relative, name)))
            consulted = [p for p in changed if p not in dependencies]
            changed = [p for p in changed if p in dependencies]
            unexpected = [p for p in changed if p not in [self.relative + '/' + f for f in permitted]]
            require(not unexpected, 'UPSTREAM_INPUT_CHANGED_DURING_STAGE: ' + ', '.join(unexpected))
            if consulted:
                state.setdefault('lineage', []).append({'stage': stage, 'advisory': True, 'consulted': {
                    p: {'before': active['baseline'][p], 'after': after[p]} for p in consulted}, 'at': now()})
            if changed:
                state.setdefault('lineage', []).append({'stage': stage, 'changes': {p: {'before': active['baseline'][p], 'after': after[p]} for p in changed}, 'at': now()})
                for prior in state['receipts'].values():
                    for path in changed:
                        if path in prior['fingerprints']:
                            prior['fingerprints'][path] = after[path]
            stored = copy.deepcopy(receipt)
            if stored.get('input_roles') is None:
                stored.pop('input_roles', None)  # absent means all-dependency
            if delegation_ledger_trust is not None:
                # A warning record, never a block: 'unverified-local' means no
                # local dispatcher-write marker existed to check against (a
                # fresh checkout or CI runner), not that anything was wrong.
                stored['delegation_ledger_trust'] = delegation_ledger_trust
            stored['command'] = state['commands'][stage]
            stored['dependency_digest'] = state['dependency_digest']
            decision_input = [self.relative + '/workflow/decisions.json'] if (self.feature / 'workflow/decisions.json').is_file() else []
            stored['fingerprints'] = fingerprint_files(self.root, receipt['inputs'] + receipt['evidence'] + required_inputs(self.root, self.relative, stage) + decision_input)
            require(all(v is not None for v in stored['fingerprints'].values()), 'INPUT_MISSING')
            if stage in SOURCE_STAGES:
                stored['source_fingerprints'] = source_fingerprints(self.root)
                # The commit and its source key bind the inventory; with source
                # changes outside HEAD the key would not describe it, so none is
                # recorded and the identity rule applies to this receipt.
                head, key = current_source_key(self.root)
                if key:
                    stored['head'], stored['source_key'] = head, key
            stored['completed_at'] = now()
            state['receipts'][stage] = stored
            state['active'] = None
            self.save(state)
            return self.next(state)

    def checkpoint(self, state, reason, context=None):
        state['status'] = 'paused'
        state['pause'] = {'reason': reason, 'context': context, 'at': now()}
        self.save(state)
        pending = self.next(state)
        task_path = self.feature / 'tasks.md'
        pending_tasks = re.findall(r'(?m)^\s*- \[ \]\s+(T\d{3,})\b', task_path.read_text(encoding='utf-8-sig')) if task_path.is_file() else []
        active_summary = {k: state['active'].get(k) for k in ('stage', 'session_id', 'claimed_at')} if state['active'] else None
        text = '# Workflow handoff\n\n' + '\n'.join([
            '- Feature: ' + self.relative, '- Issue: ' + state['issue'], '- Branch: ' + state['branch'],
            '- Head: ' + state['head'], '- Reason: ' + reason, '- Next: ' + str(pending),
            '- Completed stages: ' + ', '.join(state['receipts']),
            '- Active claim: ' + str(active_summary),
            '- Pending task IDs: ' + ', '.join(pending_tasks[:100]) + (' (more in tasks.md)' if len(pending_tasks) > 100 else ''),
            '\nRead evidence paths and summaries in checkpoint.json; do not infer skipped tests passed.',
            '\nInspect git status before continuing; do not discard uncommitted files.'])
        (self.path.parent / 'handoff.md').write_text(text + '\n', encoding='utf-8')
        prompt = f'Continue the Sanduq workflow in {self.root}. Read {self.relative}/workflow/checkpoint.json and handoff.md. Invoke speckit.workflow.continue for {self.relative}; validate inputs and resolve any active claim before resuming. Preserve policy and unresolved approvals.\n'
        (self.path.parent / 'resume-prompt.md').write_text(prompt, encoding='utf-8')
        return {'status': 'paused', 'checkpoint': str(self.path), 'prompt': prompt}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='action', required=True)
    init = sub.add_parser('init')
    init.add_argument('--qa', choices=['on', 'off'], required=True)
    init.add_argument('--manual', choices=['on', 'off'], required=True)
    init.add_argument('--delegate', choices=['on', 'off'],
                      help='Opt into model-aware delegation; omitted on existing projects preserves their selection')
    init.add_argument('--gate-mode', choices=sanduq_ci.GATE_MODES,
                      help='Disabled, advisory or required workflow evidence gate; fresh policies default to advisory')
    init.add_argument('--gate-scope', choices=sanduq_ci.GATE_SCOPES,
                      help='Managed-only keeps unrelated bug-fix PRs out of the evidence gate')
    init.add_argument('--gate-rule', action='append', default=[], metavar='NAME=on|off')
    init.add_argument('--decision-owner', action='append', default=[], metavar='GITHUB_LOGIN',
                      help='GitHub login allowed to settle issue decisions; repeat for a team of reviewers')
    init.add_argument('--replace', action='store_true')
    ci_parser = sub.add_parser('ci', help='Record where this project runs its CI, once')
    ci_parser.add_argument('--show', action='store_true', help='Print the recorded selection without changing it')
    ci_parser.add_argument('--provider', choices=list(sanduq_ci.PROVIDERS))
    ci_parser.add_argument('--policy', choices=list(sanduq_ci.RUNNER_POLICIES),
                           help='self-hosted-required makes every GitHub-hosted runner need a recorded exception')
    for platform in sanduq_ci.PLATFORMS:
        ci_parser.add_argument('--' + platform, metavar='LABELS',
                               help='Comma-separated ' + platform + ' runner labels, or "none" to remove')
    ci_parser.add_argument('--system-packages', choices=list(sanduq_ci.SYSTEM_PACKAGES),
                           help='sudo-apt keeps the apt install steps; preinstalled drops them and expects the runner image to carry them')
    ci_parser.add_argument('--python', choices=list(sanduq_ci.PYTHON_PROVISIONING),
                           help='setup-action keeps actions/setup-python; preinstalled expects Python on the runner')
    ci_parser.add_argument('--python-version')
    ci_parser.add_argument('--gate-mode', choices=sanduq_ci.GATE_MODES)
    ci_parser.add_argument('--gate-scope', choices=sanduq_ci.GATE_SCOPES)
    ci_parser.add_argument('--gate-rule', action='append', default=[], metavar='NAME=on|off')
    ci_parser.add_argument('--affected-command', metavar='COMMAND',
                           help='Affected-lane hook for source drift (JSON paths on stdin), or "none" to remove')
    ci_parser.add_argument('--verification-check', metavar='CHECK',
                           help='CI job accepted as Verify evidence by revalidate --check-run, or "none" to remove')
    decisions_parser = sub.add_parser('decisions', help='Show or update decision authority and field policy')
    decisions_parser.add_argument('--show', action='store_true')
    decisions_parser.add_argument('--owner', action='append', default=[], metavar='GITHUB_LOGIN')
    decisions_parser.add_argument('--field-name')
    host_parser = sub.add_parser('host', help='Show installed hosts, or switch the default host without losing skills')
    host_parser.add_argument('--use', choices=['codex', 'claude'],
                             help='Make this installed integration the default; omit to report host status')
    host_parser.add_argument('--preview', action='store_true', help='Report the switch plan without changing anything')
    host_parser.add_argument('--replace-unrecognized-aliases', action='store_true',
                             help='Back up, then replace, a managed alias file whose content Sanduq does not recognise')
    doctor_parser = sub.add_parser('doctor')
    doctor_parser.add_argument('--project', action='store_true', help='Also validate configured board identities, phase/status mapping and required sync')
    sub.add_parser('project-defaults')
    identity_parser = sub.add_parser('identity', help='Resolve initial issue-derived branch and spec directory')
    identity_parser.add_argument('--issue', required=True)
    prepare_parser = sub.add_parser('prepare', help='Prepare an issue-bound feature and its branch')
    prepare_parser.add_argument('--issue', required=True)
    relocate_parser = sub.add_parser('relocate', help='Rebind a checkpoint whose repository identity legitimately '
                                                       'moved (a fork, a renamed remote, a migrated org)')
    relocate_parser.add_argument('--feature', required=True)
    relocate_parser.add_argument('--preview', action='store_true',
                                 help='Report the old and new identity without changing anything')
    relocate_parser.add_argument('--reason', required=True)
    relocate_parser.add_argument('--allow-branch-rebind', action='store_true',
                                 help='Also rebind the checkpoint to the current branch if it differs; logged either way')
    relocate_parser.add_argument('--allow-repository-rename', action='store_true',
                                 help='Confirm the checkpoint\'s bound issue naming a different GitHub repository '
                                      'than this one is a real rename or move, not a foreign checkpoint; logged either way')
    relocate_parser.add_argument('--issue', metavar='OWNER/REPO#N',
                                 help='The exact new issue to bind when the repository changed; required unless '
                                      '--keep-issue-number, never both')
    relocate_parser.add_argument('--keep-issue-number', action='store_true',
                                 help='Keep the same issue number under the new repository when it changed; only '
                                      'valid for a GitHub rename or transfer, never a fork')
    relocate_parser.add_argument('--actor', help='Defaults to the Git user name')
    for name in ('start', 'next', 'claim', 'complete', 'pause', 'recover', 'bind', 'migrate', 'refresh', 'amend',
                 'revalidate'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--feature', required=True)
        if name == 'start': cmd.add_argument('--issue', required=True)
        if name in ('next', 'claim'): cmd.add_argument('--finalize', action='store_true')
        if name == 'claim': cmd.add_argument('--usage', type=Path, required=True)
        if name == 'complete':
            cmd.add_argument('--token', required=True)
            cmd.add_argument('--receipt', type=Path, required=True)
        if name in ('pause', 'recover', 'refresh', 'amend'): cmd.add_argument('--reason', required=True)
        if name == 'migrate': cmd.add_argument('--reason', help='Required unless --preview')
        if name in ('recover', 'bind'): cmd.add_argument('--token', required=True)
        if name == 'migrate':
            cmd.add_argument('--invalidate-from', choices=BASE_STAGES)
            cmd.add_argument('--preview', action='store_true',
                             help='Report the exact invalidated and preserved stages without writing')
        if name == 'amend':
            cmd.add_argument('--stage', required=True, choices=BASE_STAGES)
            cmd.add_argument('--evidence', required=True, help='One evidence path listed in that receipt')
            cmd.add_argument('--assessment', required=True, choices=AMENDMENT_ASSESSMENTS)
            cmd.add_argument('--actor', help='Defaults to the Git user name')
        if name == 'refresh': cmd.add_argument('--from-stage', choices=('scope', 'clarify'), required=True)
        if name == 'revalidate':
            cmd.add_argument('--stage', required=True, choices=SOURCE_STAGES)
            cmd.add_argument('--check-run', metavar='RUN_ID',
                             help='verify: the workflow run id whose plan artifact and ci.gate.verification_check '
                                  'job are read through the GitHub REST API')
            cmd.add_argument('--attempt', help='verify: the run attempt (default: the latest)')
            cmd.add_argument('--diff-reviewed', metavar='EVIDENCE',
                             help='review: the recorded incremental review of git diff <review head>..HEAD')
            cmd.add_argument('--base-ref', help='ready: the base for documentation freshness (default: the bound target)')
            cmd.add_argument('--reason', help='Recorded with the revalidation; never sufficient on its own')
            cmd.add_argument('--actor', help='Defaults to the Git user name')
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.action == 'init':
            ensure_local_excludes(root)
            path = root / '.specify/workflow.yml'
            policy = default_policy(args.qa == 'on', args.manual == 'on')
            if path.exists():
                old = load_policy(root)
                require(args.replace or old['processes'] == policy['processes'], 'POLICY_EXISTS: use --replace after reviewing changed selections')
                if args.delegate is not None:
                    require(args.replace or old['delegation']['enabled'] == (args.delegate == 'on'),
                            'DELEGATION_SELECTION_EXISTS: use --replace after reviewing the changed selection')
                policy = old
                policy['processes'] = {'qa': args.qa == 'on', 'user_manual': args.manual == 'on'}
                write(root / '.specify/workflow/backups' / (uuid.uuid4().hex + '.json'), load_policy(root))
            if args.delegate is not None:
                policy['delegation']['enabled'] = args.delegate == 'on'
            select_gate(policy['ci'], args.gate_mode, args.gate_scope, args.gate_rule)
            if args.decision_owner:
                policy.setdefault('decisions', default_policy(False, False)['decisions'])['authorized_users'] = args.decision_owner
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(validate_policy(policy), sort_keys=False), encoding='utf-8')
            result = {'configured': True, 'processes': policy['processes'],
                      'gate': sanduq_ci.gate_config(policy['ci']), 'doctor': doctor(root, policy)}
        elif args.action == 'ci':
            policy = load_policy(root)
            ci = policy['ci']
            if not args.show:
                for key, value in (('provider', args.provider), ('policy', args.policy)):
                    if value: ci[key] = value
                for platform in sanduq_ci.PLATFORMS:
                    labels = getattr(args, platform)
                    if labels is None: continue
                    if labels.strip().lower() == 'none': ci['runners'].pop(platform, None)
                    else: ci['runners'][platform] = [l.strip() for l in labels.split(',') if l.strip()]
                for key, value in (('system_packages', args.system_packages), ('python', args.python),
                                   ('python_version', args.python_version)):
                    if value: ci['capabilities'][key] = value
                select_gate(ci, args.gate_mode, args.gate_scope, args.gate_rule,
                            {'affected_command': args.affected_command,
                             'verification_check': args.verification_check})
                write(root / '.specify/workflow/backups' / (uuid.uuid4().hex + '.json'), load_policy(root))
                (root / '.specify/workflow.yml').write_text(
                    yaml.safe_dump(validate_policy(policy), sort_keys=False), encoding='utf-8')
            # The recorded selection is not live until the installer re-renders
            # each managed workflow file from it.
            result = {'ci': ci, 'saved': not args.show, 'doctor': doctor(root, policy)}
        elif args.action == 'decisions':
            policy = load_policy(root)
            config = policy.setdefault('decisions', default_policy(False, False)['decisions'])
            if not args.show and (args.owner or args.field_name):
                if args.owner: config['authorized_users'] = args.owner
                if args.field_name: config['project_field'] = args.field_name
                validate_policy(policy)
                write(root / '.specify/workflow/backups' / (uuid.uuid4().hex + '.json'), load_policy(root))
                (root / '.specify/workflow.yml').write_text(yaml.safe_dump(policy, sort_keys=False), encoding='utf-8')
            result = {'decisions': config, 'saved': bool(not args.show and (args.owner or args.field_name))}
        elif args.action == 'host':
            import hosts
            if args.use:
                result = hosts.switch(root, args.use, preview=args.preview,
                                      replace_unrecognized_aliases=args.replace_unrecognized_aliases)
                if args.preview and not result['can_apply']:
                    result['ok'] = False
            else:
                result = hosts.status(root)
        elif args.action == 'doctor':
            result = doctor(root, load_policy(root), project=args.project)
        elif args.action == 'project-defaults':
            result = project_defaults(root, load_policy(root))
        elif args.action == 'identity':
            result = issue_identity(root, args.issue)
        elif args.action == 'prepare':
            result = prepare_issue(root, args.issue)
        else:
            run = Run(root, args.feature)
            if args.action == 'start': result = run.start(args.issue)
            elif args.action == 'next': result = run.next(run.load(), args.finalize)
            elif args.action == 'claim': result = run.claim(read(args.usage), args.finalize)
            elif args.action == 'complete': result = run.complete(args.token, read(args.receipt, {}))
            elif args.action == 'bind': result = run.bind(args.token)
            elif args.action == 'relocate':
                result = run.relocate(args.reason, args.preview, args.allow_branch_rebind,
                                      args.allow_repository_rename, args.issue, args.keep_issue_number, args.actor)
                if args.preview and not result['can_apply']: result['ok'] = False
            elif args.action == 'migrate' and args.preview: result = run.preview_migration(args.invalidate_from)
            elif args.action == 'migrate': result = run.migrate(args.reason, args.invalidate_from)
            elif args.action == 'amend':
                result = run.amend(args.stage, args.evidence, args.reason, args.assessment, args.actor)
            elif args.action == 'refresh': result = run.refresh(args.from_stage, args.reason)
            elif args.action == 'revalidate':
                result = run.revalidate(args.stage, args.check_run, args.attempt, args.diff_reviewed, args.base_ref,
                                        args.reason, args.actor)
                if not result['revalidated']:
                    result['ok'] = False
            else:
                with locked(run.lock):
                    state = run.load()
                    if args.action == 'recover':
                        require(state['active'] and state['active']['token'] == args.token, 'CLAIM_TOKEN_MISMATCH')
                        state.setdefault('recoveries', []).append({'claim': state['active'], 'reason': args.reason, 'at': now()})
                        state['active'] = None
                    result = run.checkpoint(state, args.reason)
        print(json.dumps(result, indent=2))
        return 1 if result.get('ok') is False else 0
    except (WorkflowError, ValueError, KeyError, yaml.YAMLError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
