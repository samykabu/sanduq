"""Workflow runtime core: constants, errors, file and git primitives, path containment, the operation
memo, locks and the foreign-claim scan. Every other runtime module builds on this one."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    import sanduq_fs
except ModuleNotFoundError:  # the source tree; package.py copies it into scripts/
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'shared'))
    import sanduq_fs


SCHEMA = 1  # the policy schema
# The checkpoint has its own version (W27): 2 drops `repo_path`. Readers accept 1 and 2; every write is 2.
CHECKPOINT_SCHEMA = 2
CHECKPOINT_SCHEMAS = (1, 2)
RANGES = {'scope': '>=1.11,<2', 'assure': '>=2.2,<3', 'user-manual': '>=1.2,<2',
          'pr': '>=4.1,<5', 'superspec': '>=1.0.2,<2', 'project': '>=2.1,<3', 'progress': '>=1.0,<2'}
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
                          'revalidations', 'delegation_ledger_trust', 'verification_snapshot', 'pr_lint_binding',
                          'source_inventory', 'text_fingerprints', 'revalidated_upstream')
# Stages whose receipts also inventory source (`source_inventory`) and record `head` and `source_key`.
SOURCE_STAGES = ('verify', 'review', 'ready')
# Effort scores a Scope receipt may carry (`effort_score`), and the tier bands they map to.
EFFORT_SCORES = (1, 2, 3, 5, 8, 13, 21)
TIERS = ('lite', 'standard', 'full')
DEFAULT_PROFILES = {'lite': {'max_score': 3}, 'standard': {'max_score': 8}}
# Stages a lite feature skips; `tasks` is merged into `plan` on lite and standard.
LITE_SKIPPED = ('qa_analyze', 'manual_analyze', 'qa_document', 'manual_update')
LITE_OPTIONAL_INPUTS = ('research.md', 'data-model.md', 'quickstart.md')
LINT_COMMAND = 'workflow:lint'
ARTIFACT_BUDGETS = ('spec_kb', 'plan_kb', 'research_kb', 'tasks_detail_lines')
ARTIFACT_ENFORCE = ('lite-standard', 'all', 'warn')
# Stage -> Project Sync phase, run after the stage (execute: before it); `project_sync.points` narrows the stages.
PROJECT_SYNC_PHASES = {'specify': 'open', 'plan': 'analysis', 'analyze': 'engineer-review',
                       'taskstoissues': 'ready', 'execute': 'in-progress', 'pr': 'in-review'}
PROJECT_SYNC_POINTS = tuple(PROJECT_SYNC_PHASES)
PROJECT_SYNC_SCRIPT = '.specify/extensions/project/scripts/project_sync.py'
# Phases `project-sync` runs: the scheduled ones and the post-merge `done`.
PROJECT_SYNC_STEPS = tuple(PROJECT_SYNC_PHASES.values()) + ('done',)
DEFAULT_SYNC_STATE = '.specify/project-sync-state.json'
# A dependency on the configured Project Sync state is fingerprinted as the bound feature's entry without its
# administrative fields (status, timestamps), so a board move never stales evidence while a binding change does.
SYNC_BINDING_PREFIX = 'sync-binding:v1:'
SYNC_ADMINISTRATIVE = re.compile(r'status|\w*(?:At|_at|[Tt]imestamp)')
TASK_ISSUE_MODES = ('required', 'phase-lazy')
# Files a stage may change although earlier receipts depend on them (glob `*` stays within one folder).
# The lineage records each such change; anything else changed during a stage refuses the completion.
SIDE_EFFECTS = {'clarify': ['<feature>/spec.md', '.specify/project-sync-state.json', '<feature>/checklists/*.md'],
                'qa_analyze': ['<feature>/tasks.md'],
                'manual_analyze': ['<feature>/tasks.md'],
                # Assure Document refreshes this generated source inventory.
                # It is project context, not requirements authority.
                'qa_document': ['.github/memory/project-memory.md']}
RENDER_MARKER = re.compile(r'<!-- sanduq-scope:rendered ([0-9a-f]{64}) -->')
HANDOFF_BEGIN, HANDOFF_END = '<!-- sanduq-handoff:begin -->', '<!-- sanduq-handoff:end -->'
DOCTOR_CACHE = '.specify/workflow/runtime/doctor-cache.json'
DOCTOR_CACHE_SECONDS = 600
DOCTOR_CACHE_FILES = ('.specify/extensions/.registry', '.specify/presets/.registry', '.specify/extensions.yml',
                      '.specify/extensions/project/config.json')
# How recovery recipes name the runtime in a consumer project.
WORKFLOW_SCRIPT = 'python .specify/extensions/workflow/scripts/workflow.py'
# Where the workflow package lands inside a consumer project, so `claim`'s `reference`
# field is directly usable by a reader without knowing the installed layout separately.
WORKFLOW_PACKAGE_PREFIX = '.specify/extensions/workflow/'


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


def replace_file(source, target, attempts=10):
    """`os.replace` with the shared bounded Windows retry (`sanduq_fs.replace_file`)."""
    _wrote(target)
    return sanduq_fs.replace_file(source, target, attempts)


def write(path, value):
    _wrote(path)
    sanduq_fs.write_json(path, value)


def inside(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(_memo('resolved', root, root.resolve)), 'PATH_OUTSIDE_PROJECT: ' + str(relative))
    return path


def portable_label(label):
    """A stored path label with Windows separators read as the forward-slash identifier. Used only to compare
    labels; a stored label itself is never rewritten."""
    return label.replace('\\', '/') if isinstance(label, str) else label


def canonical_path(root, label):
    """Forward-slash, root-relative path for a label that may carry Windows separators.

    Refuses empty, NUL, absolute, drive-letter, UNC and `..` labels, and anything resolving outside the project,
    so a legacy `dir\\file` label reads the same file on POSIX and Windows without widening what may be read."""
    require(isinstance(label, str) and label and '\0' not in label, 'PATH_INVALID: ' + repr(label))
    text = label.replace('\\', '/')
    require(not text.startswith('/') and not re.match(r'^[A-Za-z]:', text), 'PATH_OUTSIDE_PROJECT: ' + label)
    parts = [part for part in text.split('/') if part not in ('', '.')]
    require(parts and '..' not in parts, 'PATH_OUTSIDE_PROJECT: ' + label)
    canonical = '/'.join(parts)
    if not _no_link_below(root, parts):
        inside(root, canonical)
    return canonical


REPARSE_POINT = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT: a Windows symlink, junction or mount point


def _no_link_below(root, parts):
    """True when no existing component of `root/parts` below `root` is a link or reparse point, so the path cannot
    leave the root (W19): one `lstat` per component instead of a full resolve. False means a full resolve decides.
    Checked on every call and never memoised, so an ancestor replaced by a link mid-operation is still caught."""
    path = os.fspath(root)
    for part in parts:
        if ':' in part or part.endswith(('.', ' ')):
            return False  # Windows reads these as a stream or trims them
        path = os.path.join(path, part)
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            return True  # nothing below a missing component exists
        except OSError:
            return False
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & REPARSE_POINT:
            return False
    return True


GIT_READS = ('rev-parse', 'branch', 'ls-files', 'config', 'rev-list', 'merge-base', 'check-ref-format', 'show-ref',
             'show')


def run_git(root, *args, **options):
    """This package's one git runner (W26): unchecked, the caller reads the result."""
    result = subprocess.run(['git', *args], cwd=root, capture_output=True, **options)
    if args and args[0] not in GIT_READS and args[:2] != ('worktree', 'list'):
        _wrote(None)  # anything else may move HEAD, the index or the configuration
    elif args[:1] == ('config',) and '--get' not in args and len(args) > 2:
        _wrote(None)
    return result


def git_ok(root, *args):
    return run_git(root, *args).returncode == 0


def git(root, *args):
    result = run_git(root, *args, text=True, encoding='utf-8')
    require(result.returncode == 0, 'GIT_ERROR: ' + result.stderr.strip())
    return result.stdout.strip()


# Operation-scoped memo: one CLI command reads the origin URL, shallowness, git text attributes and the
# source inventory once. Outside `operation()` nothing is memoised, so a long-lived importer (a test, Scope)
# always reads live values. Anything the runtime itself writes drops what that write could change (`_wrote`).
_OPERATION = None
OPERATIONAL_DIRS = ('.specify', '.agents', '.claude', '.codex', 'specs', 'User-Manual', 'docs', 'graphify-out',
                    'keys_cert')


@contextmanager
def operation():
    global _OPERATION
    if _OPERATION is not None:
        yield  # nested: share the outer command's memo
        return
    _OPERATION = {}
    try:
        yield
    finally:
        _OPERATION = None


def _memo(kind, root, compute):
    if _OPERATION is None:
        return compute()
    key = (kind, os.path.normcase(os.path.abspath(root)))
    if key not in _OPERATION:
        _OPERATION[key] = compute()
    return _OPERATION[key]


def _wrote(path):
    """The runtime wrote `path` (None: an unknown change). Keeps only memos the write cannot affect: identity is
    git configuration, attributes change with `.gitattributes` or `.git/info`, and the source inventory ignores
    the operational folders."""
    if _OPERATION is None:
        return
    if path is None:
        return _OPERATION.clear()
    target = os.path.normcase(os.path.abspath(path))
    for key in list(_OPERATION):
        kind, root = key
        if kind in ('origin', 'shallow', 'root_commit', 'resolved'):
            continue
        relative = os.path.relpath(target, root) if target.startswith(root) else None
        parts = Path(relative).parts if relative else ()
        if not parts or parts[0] == '..':
            continue
        if kind == 'attributes' and not (parts[-1] == '.gitattributes' or parts[:2] == ('.git', 'info')):
            continue
        if kind == 'source' and parts[0] in OPERATIONAL_DIRS:
            continue
        del _OPERATION[key]


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


# Beside info/exclude: {owner: [the exclude lines that owner writes for its local runtime files]}.
RUNTIME_DECLARATION = 'sanduq-runtime.json'


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
        _wrote(None)  # the exclude file may live in a common git dir outside the root
        path.write_text(current.rstrip('\n') + '\n# Sanduq local backups and runtime\n' + '\n'.join(missing) + '\n', encoding='utf-8')
    # Memory treats a file ignored by exactly one of these lines as disposable runtime, not feature content.
    declaration = path.parent / RUNTIME_DECLARATION
    try:
        declared = read(declaration, {})
    except ValueError:
        declared = {}  # rewritten below; the owners' lists are rebuilt on their next run
    declared = declared if isinstance(declared, dict) else {}
    if declared.get('workflow') != list(patterns):
        _wrote(None)
        write(declaration, {**declared, 'workflow': list(patterns)})


@contextmanager
def locked(path):
    """Workflow's runtime lock: one try (timeout 0), `WORKFLOW_BUSY` naming the live owner, and a lock whose
    recorded pid has exited on this host is reclaimed (SAMY-01)."""
    with sanduq_fs.file_lock(path, 0, 'WORKFLOW_BUSY', WorkflowError, 'WORKFLOW_LOCK_RELEASE_BUSY'):
        yield

