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
    import sanduq_gh
except ModuleNotFoundError:  # the source tree; package.py copies it into scripts/
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'shared'))
    import sanduq_fs
    import sanduq_gh

GIT = sanduq_gh.tool_path('git')  # PATH only: a git.exe in the consumer checkout must not win (SEC-15)


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
                          'source_inventory', 'text_fingerprints', 'revalidated_upstream', 'self_attested',
                          'ready_checks')
# Stages whose receipts also inventory source (`source_inventory`) and record `head` and `source_key`.
SOURCE_STAGES = ('verify', 'review', 'ready')
# Effort scores a Scope receipt may carry (`effort_score`), and the tier bands they map to.
EFFORT_SCORES = (1, 2, 3, 5, 8, 13, 21)
TIERS = ('lite', 'standard', 'full')
DEFAULT_PROFILES = {'lite': {'max_score': 3}, 'standard': {'max_score': 8}}
# Stages a lite feature skips; `tasks` is merged into `plan` on lite and standard.
LITE_SKIPPED = ('qa_analyze', 'manual_analyze', 'qa_document', 'manual_update')
# Stages a lite feature folds into a neighbour (Workflow 1.23): recorded in `skipped` when the tier is fixed, so a
# feature fixed earlier keeps its own list. Plan's completion runs the lint Analyze ran; Verify's completion runs
# the Ready checks; Verify also reviews the diff; no task sub-issues.
LITE_FOLDED = {'analyze': 'lite tier: lint runs at Plan completion',
               'taskstoissues': 'lite tier: no task sub-issues',
               'review': 'lite tier: Verify reviews the diff',
               'ready': 'lite tier: Ready checks run at Verify completion'}
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
TASK_ISSUE_MODES = ('required', 'phase-lazy', 'off')
# `project_sync.mode` (REQ-22): full writes every phase, minimal only the tracked ones below (no task sub-issues),
# off runs without a board. Operational like `project_sync.points`: a change never reaches a stage.
PROJECT_SYNC_MODES = ('full', 'minimal', 'off')
MINIMAL_SYNC_PHASES = ('ready', 'in-progress', 'in-review', 'done')
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


W = WORKFLOW_SCRIPT
INSTALL_SCRIPT = 'python .specify/extensions/workflow/scripts/install.py'
# The error registry (AHMED-05): code -> (what happened, why it is refused, the next command). Data only: adding
# a code is one line here; `explain()` adds `explain` and `next` to CLI error output and docs/reference/errors.md
# is generated from it (`python extensions/scripts/check_docs.py --write`). `<feature>` is filled in when known.
ERRORS = {
    'ACTIVE_STAGE_MUST_BE_RESOLVED': ('A feature still holds an active claim.', 'Installing, upgrading or switching hosts would restore files under a running stage.', W + ' status --feature <feature>, then complete, pause or recover that claim'),
    'BYTE_SENSITIVE_EOL_DRIFT': ('Tracked byte-sensitive files have working-tree line endings that differ from the index.', 'Fingerprints use the committed bytes, so tools reading the working tree see other bytes than CI.', 'git ls-files --eol, then git -c core.autocrlf=false checkout -- <path> after adding "*.sql -text" to .gitattributes'),
    'CHECKPOINT_BRANCH_MISMATCH': ('The checked-out branch is not the branch this feature was bound to.', 'Stage evidence is recorded against one branch; running on another would mix histories.', 'git switch <bound branch> (status shows it), or ' + W + ' relocate --feature <feature> --allow-branch-rebind --reason "<why>"'),
    'CHECKPOINT_IDENTITY_MISMATCH': ('The checkpoint is bound to another repository than this one.', 'A copied or forked checkpoint would write evidence for the wrong project.', W + ' relocate --feature <feature> --reason "<why>" if this is the same project moved'),
    'CHECKPOINT_IDENTITY_UNRESOLVABLE': ('The checkpoint records no repository identity that this clone can verify.', 'Without a root commit or remote to compare, ownership of the checkpoint is unknown.', W + ' relocate --feature <feature> --preview --reason "<why>"'),
    'CI_GATE_DISABLED_FILE_PRESENT': ('The policy disables the evidence gate but the managed gate workflow file is still present.', 'A disabled gate must not keep running in CI.', INSTALL_SCRIPT + ' --apply removes it, or re-enable the gate with ' + W + ' ci --gate-mode advisory'),
    'CI_PROVIDER_NONE_FILE_PRESENT': ('The CI provider is "none" but a managed gate workflow file exists.', 'Nothing should run the gate when the project declares no CI.', INSTALL_SCRIPT + ' --apply, or ' + W + ' ci --provider github'),
    'CI_TEMPLATE_UNRENDERABLE': ('A managed CI template cannot be rendered from the recorded ci selection.', 'The selection names a runner or capability the template has no branch for.', W + ' ci --show, then correct the selection with ' + W + ' ci --<platform> <labels>'),
    'CI_WORKFLOW_STALE': ('A managed workflow file no longer matches what the ci selection renders.', 'The selection was changed but never applied.', INSTALL_SCRIPT + ' --apply'),
    'CLAIM_TOKEN_MISMATCH': ("The token given to complete or recover is not the active claim's token.", 'Only the session that claimed a stage may complete it.', W + ' status --feature <feature> to see the claim; recover it with its token if that session stopped'),
    'COMMAND_UNAVAILABLE': ('A stage command has no installed skill under the active host.', 'The dispatcher cannot run a stage whose skill is missing.', INSTALL_SCRIPT + ' --apply, then start a new host session'),
    'DELEGATE_AGENT_CLI_UNAVAILABLE': ('Delegation is enabled but neither the Codex nor the Claude CLI is installed.', 'Delegated work needs a harness to run in.', 'Install the codex or claude CLI, or set delegation.enabled: false in .specify/workflow.yml'),
    'DELEGATE_SKILL_BROKEN': ('The installed delegate-task skill fails its own doctor.', 'A broken skill cannot dispatch workers.', 'python .specify/extensions/workflow/scripts/delegation.py install'),
    'DELEGATE_SKILL_DOCTOR_FAILED': ("The delegate-task skill's doctor reported a failure.", 'Delegation is refused until the skill is healthy.', 'python .specify/extensions/workflow/scripts/delegation.py install (an unowned copy is reported, not replaced)'),
    'DELEGATE_SKILL_INCOMPATIBLE': ('The installed delegate-task skill is not the version this Workflow requires.', 'The dispatcher and the skill must agree on the run contract.', 'python .specify/extensions/workflow/scripts/delegation.py install'),
    'DELEGATE_SKILL_MISSING': ('Delegation is enabled but the delegate-task skill is not installed.', 'Delegated stages need it.', 'python .specify/extensions/workflow/scripts/delegation.py install, or set delegation.enabled: false'),
    'DELEGATION_LINEAGE_SELF': ('accept, adopt, reassign, trust-reset or start was run by a process that descends from a live delegated run of the feature.', "A delegated worker never grades its own or a sibling's work, even with its SANDUQ_* variables removed.", 'Run the command from the top-level session (or the Execute orchestrator, except trust-reset)'),
    'DELEGATION_NONCE_REQUIRED': ('accept, adopt, reassign or trust-reset was run without the dispatcher nonce, or with a wrong one.', "The nonce is kept outside every worker's checkout, so a worker using only what it was given cannot grade work.", 'Pass --nonce with the dispatcher_nonce a start result returned, or the contents of the file the message names'),
    'DELEGATION_SELECTION_EXISTS': ('init was given --delegate but the policy already records a different choice.', 'init never silently flips a recorded selection.', W + ' init --qa <on|off> --manual <on|off> --delegate <on|off> --replace'),
    'DELEGATION_WORKER_CONTEXT': ('A repository-identity command was run inside a delegated process tree.', 'A worker must never rebind or relocate the project it works in.', 'Run the command in the top-level session, outside any delegated run'),
    'NATIVE_ATTESTATION_FORBIDDEN': ('delegate_dispatch.py attest-native was run from a delegated worker, a subagent or a delegated orchestrator.', 'The attestation is the top-level session\'s own word; a subagent never attests itself.', 'Report the stage result to the top-level session, which runs python .specify/extensions/workflow/scripts/delegate_dispatch.py attest-native --feature <feature> --id stage:<stage> --claim-token <token> --requested-model <m> itself'),
    'NATIVE_ATTESTATION_NOT_NEEDED': ('The active claim recorded no delegation route (delegation is off, or a review-kind stage runs natively under the PH-01 interim).', 'complete accepts such a stage without any ledger attempt, so an attestation would record nothing it checks.', W + ' complete --feature <feature> --token <token> --receipt <file>'),
    'DEPENDENCY_CHANGED': ('The installed packages changed since this checkpoint was written.', 'A package change can change what stage evidence means, so it needs a reviewed migration.', W + ' migrate --feature <feature> --reason "<text>" (preview with --preview); an incomplete upgrade is finished with upgrade.py --version <v> --apply'),
    'DEPENDENCY_SOURCE_MISMATCH': ("A required extension, or an installed scope or memory, is not Sanduq's: another repository or author, a catalog install without the release inventory, or files that differ from it.", 'The community package with the same id is not the one Workflow runs.', 'specify extension remove <name>, then ' + INSTALL_SCRIPT + ' --apply'),
    'DEPENDENCY_UNAVAILABLE': ('A required extension is missing, disabled or outside the version range Workflow needs.', "Stages run the companions' commands.", INSTALL_SCRIPT + ' --apply on a fresh install; after an upgrade, the upgrade.py command the message names'),
    'DETACHED_HEAD_UNSUPPORTED': ('HEAD is detached.', 'A feature branch is created from the current branch, so there must be one.', 'git switch <branch>, then run the command again'),
    'DUPLICATE_STAGE_OWNER': ('An extension hook is still enabled for a stage the Workflow dispatcher owns.', 'The stage would run twice.', 'python .specify/extensions/workflow/scripts/reconcile.py --apply'),
    'EVIDENCE_MISSING': ('A receipt names evidence that does not exist on disk.', 'A stage passes only on evidence a reader can open.', 'Write the file, then run complete again with the same receipt'),
    'EXPLICIT_ISSUE_REQUIRED': ('start needs --issue owner/repo#N.', 'A feature is bound to exactly one GitHub issue.', W + ' start --feature <feature> --issue <owner/repo#N>'),
    'EXPLICIT_RELEASE_VERSION_REQUIRED': ('upgrade.py needs --version X.Y.Z.', 'An upgrade targets one released version.', 'python .specify/extensions/workflow/scripts/upgrade.py --version <X.Y.Z> --apply'),
    'FEATURE_BINDING_MISMATCH': ("The feature's scope-source.json is bound to another issue.", 'Scope and Workflow must agree on the issue.', 'Pass the issue scope-source.json names, or run Scope again for this issue'),
    'FEATURE_PATH_INVALID': ('--feature is not a directory under specs/.', 'Features live in specs/<slug>.', W + ' status --feature specs/<slug>'),
    'GIT_ERROR': ("A git command failed; the message carries git's stderr.", 'The runtime reads branches, remotes and history through git.', 'Run the git command from the message yourself; check git remote -v and the current branch'),
    'GITHUB_ISSUE_REQUIRED': ('The issue number does not name an issue of this repository (or names a pull request).', 'A feature is bound to an issue.', 'gh issue view <n> --repo <owner/repo>; create one with gh issue create'),
    'GITHUB_REMOTE_REQUIRED': ('The repository has no GitHub origin remote.', 'Issues, boards and PRs are resolved through origin.', 'git remote add origin https://github.com/<owner>/<repo>.git'),
    'GUARD_HOOK_UNAPPROVED': ('Codex has the Sanduq guard hook registered but not approved.', 'Codex runs project hooks only in a trusted project after /hooks approval.', 'Open Codex in this project, run /hooks and approve the guard'),
    'HISTORY_UNRELATED': ('HEAD shares no commit with origin/HEAD.', 'An orphan or recreated history cannot be merged into the default branch, so the PR would fail.', 'git log --oneline -1 origin/HEAD; start the feature from that history (git switch -c <branch> origin/HEAD)'),
    'HOOK_CONFIG_INVALID': ('.specify/extensions.yml is not a mapping with a hooks mapping.', 'Hook ownership cannot be checked.', 'Restore the file from git, then python .specify/extensions/workflow/scripts/reconcile.py --apply'),
    'HOOK_LIST_INVALID': ('A hook event in .specify/extensions.yml is not a list of mappings.', 'Hook ownership cannot be checked.', 'Restore the file from git, then python .specify/extensions/workflow/scripts/reconcile.py --apply'),
    'HOOK_PYTHON_MISSING': ('The interpreter the host hook commands name is not on PATH.', 'The guard hook allows everything when it cannot run.', 'Install that Python, or re-render the hooks for this machine with ' + INSTALL_SCRIPT + ' --apply'),
    'HOOK_PYTHON_TOO_OLD': ('The interpreter the host hook commands name is older than the hooks need.', 'Every Sanduq extension needs Python 3.11 or later.', 'Install a newer Python first on PATH, then ' + INSTALL_SCRIPT + ' --apply'),
    'HOOK_RECONCILIATION_REQUIRED': ('.specify/extensions.yml is missing.', 'Workflow cannot tell which extension hooks it owns.', 'python .specify/extensions/workflow/scripts/reconcile.py --apply'),
    'HOST_NOT_INSTALLED': ('The host given to host --use is not an installed integration.', 'Only an installed host can be made the default.', 'specify integration install <host>, then ' + W + ' host --use <host>'),
    'HOST_SWITCH_BLOCKED': ('The host switch has blockers; each is listed in the message.', 'A switch runs only when it can complete.', W + ' host --use <host> --preview, then fix each blocker'),
    'HOST_SWITCH_ROLLED_BACK': ('The host switch failed and the snapshot was restored.', 'Managed files are never left half-switched.', 'Read the cause in the message, fix it, then ' + W + ' host --use <host>'),
    'HOST_UNSUPPORTED': ('The active integration is not Codex or Claude skills mode.', 'This release supports those two hosts.', 'specify integration use codex (or claude), then ' + INSTALL_SCRIPT + ' --apply'),
    'INSTALL_INTERRUPTED': ('An install, upgrade or host switch stopped before it finished.', 'Its managed files may be half-written; the backup it took is intact.', INSTALL_SCRIPT + ' --restore <backup folder from the message>'),
    'INSTALL_ROLLED_BACK': ('The install failed and the snapshot was restored.', 'Managed files are never left half-installed.', 'Read the cause in the message, fix it, then ' + INSTALL_SCRIPT + ' --apply'),
    'INSTRUCTION_FILES_DUPLICATED': ('CLAUDE.md and AGENTS.md both exist and CLAUDE.md does not import AGENTS.md.', 'Two standing files drift apart.', 'Put the line @AGENTS.md in CLAUDE.md'),
    'ISSUE_BINDING_CONFLICT': ("This feature's checkpoint is bound to another issue.", 'A feature has one issue.', W + ' status --feature <feature> to see the bound issue; use another feature directory for the new issue'),
    'ISSUE_BRANCH_EXISTS': ("The issue's branch already exists.", 'prepare never switches to a branch it did not create.', 'git branch -vv to find its owner; git switch <branch> if it is yours'),
    'ISSUE_FEATURE_PATH_OCCUPIED': ('specs/<issue slug> exists but holds no workflow checkpoint.', 'prepare never writes into a folder it does not own.', 'Move or remove that folder, or bind it with ' + W + ' start --feature <feature> --issue <owner/repo#N>'),
    'ISSUE_HAS_MULTIPLE_WORKFLOW_FEATURES': ('More than one feature checkpoint is bound to the same issue.', 'The issue cannot be resolved to one feature.', 'Pass --feature specs/<slug> explicitly; archive the duplicate feature'),
    'ISSUE_IDENTITY_CONFLICT': ('The feature folder the issue maps to holds a checkpoint bound to another issue.', 'Two issues cannot share one feature.', 'Rename the issue or use ' + W + ' start --feature <other folder> --issue <owner/repo#N>'),
    'ISSUE_NOT_BOUND': ('No feature checkpoint is bound to that issue number.', 'status --issue resolves the feature through the checkpoint binding.', W + ' prepare --issue <n>, or pass --feature specs/<slug>'),
    'ISSUE_NUMBER_REQUIRED': ('--issue must be a positive integer.', 'Identity is derived from the issue number.', W + ' prepare --issue <n>'),
    'ISSUE_REPOSITORY_MISMATCH': ('The issue names another repository than origin.', 'A feature is bound to an issue of its own repository.', 'git remote -v, then pass --issue <origin owner/repo>#<n>'),
    'ISSUE_TITLE_UNSAFE_FOR_BRANCH': ('The issue title yields no valid git branch name.', 'The branch is derived from the title.', 'Rename the issue, then run the command again'),
    'LEAN_PREFLIGHT_FAILED': ('The lean preflight manifest has a failing check.', 'Lean execution runs only on a green preflight.', 'Fix the failing check named in the message, or correct lean_execution.preflight_manifest'),
    'LEGACY_ALIAS_RECONCILIATION_REQUIRED': ("The speckit-superpowers-bridge skill is an upstream copy, not Sanduq's alias.", 'The upstream command bypasses the managed dispatcher.', INSTALL_SCRIPT + ' --apply (never patch the upstream command)'),
    'LEGACY_EXECUTOR_OWNS_FEATURE': ('A superpowers bridge handoff is still executing or blocked.', 'Managed execution would collide with it.', 'Finish or reconcile the handoff recorded in .specify/superpowers-handoff.json'),
    'PATH_INVALID': ('A path label is empty, contains NUL or is otherwise unusable.', 'Only readable project paths are accepted.', 'Pass a project-relative path such as specs/<slug>/spec.md'),
    'PATH_OUTSIDE_PROJECT': ('A path resolves outside the project root.', 'The runtime reads and writes inside the project only.', 'Pass a project-relative path without .. or a drive letter'),
    'POLICY_CHANGED': ('.specify/workflow.yml changed since the checkpoint was written.', 'Stage evidence was recorded under the old policy.', W + ' migrate --feature <feature> --reason "<text>" (preview with --preview)'),
    'POLICY_EXISTS': ('init found a policy with different process selections.', 'init never silently changes qa or user_manual selections.', W + ' init --qa <on|off> --manual <on|off> --replace'),
    'POLICY_KEY_MISSING': ('A required key is missing from .specify/workflow.yml or from a file the runtime reads.', 'The runtime reads fixed keys; a hand edit or an older file dropped one.', W + ' doctor --project; rewrite the policy with ' + W + ' init --qa <on|off> --manual <on|off> --replace'),
    'CLARIFICATION_FILE_INPUT_REQUIRED': ('With the local clarification transport the Clarify receipt must list specs/<feature>/clarifications.md as an input.', 'The gate verifies the questions and the recorded replies from that file; without it the receipt proves nothing.', 'Add the file to the receipt inputs, then ' + W + ' complete --feature <feature> ...'),
    'DECISION_TRANSPORT_LOCAL': ('This feature answers decisions in specs/<feature>/clarifications.md, not on GitHub.', 'The local transport posts and syncs nothing with the issue, so there are no GitHub questions to upgrade.', 'Record the answers in the file (the option is already selectable there); nothing to run on GitHub'),
    'ORIGIN_IS_FORK': ('The "origin" remote is a fork; its issues live on the parent repository.', 'Sanduq binds the issues of "origin" only, so a fork would bind a nonexistent issue.', 'git remote -v; clone the parent repository and run Scope there'),
    'POLICY_DUPLICATE_KEY': ('.specify/workflow.yml defines the same key twice in one mapping; the message names the line.', 'YAML keeps the last value silently, so one of the two settings would be ignored.', 'Remove the duplicate at the named line, then ' + W + ' doctor'),
    'POLICY_VALUE_INERT': ('A policy value is set to something that changes nothing today (doctor warning).', 'The key is read but every value but the default has no effect yet, so the setting may mislead a reader.', 'Remove the key from .specify/workflow.yml or keep the default; no command needed'),
    'PROJECT_NOT_CONFIGURED': ('No GitHub Project board is configured while the board sync mode needs one.', 'Full and minimal board modes write statuses to the board; without it Ready and the stages cannot sync.', 'Run $speckit-project-init (or set project_sync.mode: off in .specify/workflow.yml), then ' + W + ' doctor --project'),
    'POLICY_KEY_UNKNOWN': ('.specify/workflow.yml has a key Workflow does not know; the message names the closest one.', 'A misspelt key would be silently ignored otherwise.', 'Correct the key in .specify/workflow.yml, then ' + W + ' doctor'),
    'PRESET_NOT_ENABLED': ('A bundled preset is installed but not enabled in .specify/presets/.registry.', 'The overlays it provides would not run.', INSTALL_SCRIPT + ' --apply'),
    'PRESET_REQUIRED': ('A bundled preset is missing.', 'The managed stages run its overlays.', INSTALL_SCRIPT + ' --apply'),
    'PR_CLOSING_REFERENCE_REJECTED': ("The PR body's closing references do not match the bound issue and its prerequisites.", 'The merged PR must close exactly its own issue.', 'Fix the body, regenerate the lint file, then complete the pr stage again'),
    'PR_LINT_BODY_UNREADABLE': ('The PR body file named by the pr receipt cannot be read as UTF-8.', 'Lint recomputes from the exact sent body.', 'Save the body file as UTF-8 at the path the receipt names'),
    'PR_LINT_EVIDENCE_REQUIRED': ('The pr receipt must list distinct pr_body_file and pr_lint_file paths in its evidence.', 'The lint is verified against the body.', "Add both files to the receipt's evidence and the two fields"),
    'PLAN_LINT_FAILED': ('On a tier without an Analyze stage, the lint that Plan completion runs reported an error or a gap only a model Analyze could judge.', 'The lite tier folds Analyze into Plan, so the artifacts must pass lint before Plan is recorded.', 'python .specify/extensions/workflow/scripts/lint.py --feature <feature>, fix each finding in the owning artifact, then complete Plan again'),
    'PR_LINT_RECEIPT_MISMATCH': ('The recorded lint file differs from the lint recomputed for the body.', 'A lint result is accepted only for the exact body sent.', 'Regenerate the lint file for the body, then complete again'),
    'PR_LINT_REPOSITORY_MISMATCH': ('The bound issue names another repository than origin.', 'PR lint is checked against this repository.', 'git remote -v; relocate the feature if the repository moved'),
    'PR_LINT_SCOPE_BINDING_MISMATCH': ('scope-source.json is bound to another issue than the checkpoint.', "Prerequisites come from Scope's binding.", 'Run Scope again for the bound issue'),
    'PR_LINT_SCOPE_PREREQUISITES_REQUIRED': ('scope-source.json lists no dependencies array.', 'Closing references are checked against the prerequisites.', 'Run Scope again so it records dependencies'),
    'PR_SENT_BODY_SHA_MISMATCH': ('pr_body_sha256 in the receipt is not the hash of the body file.', 'The receipt must describe the body that was sent.', 'Set pr_body_sha256 to the sha256 of the body file, then complete again'),
    'PROGRESS_HOOKS_DOUBLE_WIRED': ("Native Progress hooks and Spec Kit's speckit.progress.hook entries are both wired.", 'Each hook event would run twice.', INSTALL_SCRIPT + ' --apply'),
    'PROJECT_CONFIG_INVALID': ('.specify/extensions/project/config.json is not a JSON object.', 'The board binding cannot be read.', 'python .specify/extensions/project/scripts/project_init.py --hooks-mode required --auto-create-columns'),
    'PROJECT_CONFIG_REQUIRED': ('A board binding key is missing from the Project config; the message names it.', 'Project Sync needs the full binding.', 'python .specify/extensions/project/scripts/project_init.py --hooks-mode required --auto-create-columns'),
    'PROJECT_PHASE_UNMAPPED': ('A sync phase maps to no Status column; the message names the phase.', 'Every phase must land on a board column.', 'python .specify/extensions/project/scripts/project_init.py --hooks-mode required --auto-create-columns'),
    'PROJECT_SCOPE_STATUS_MISSING': ('A Scope status is not a column of the board; the message names it.', 'Scope moves issues between these columns.', 'python .specify/extensions/project/scripts/project_init.py --hooks-mode required --auto-create-columns'),
    'PROJECT_STATE_PATH_INVALID': ("The Project config's stateFile is outside the project.", 'Sync state is a project file.', 'Set stateFile to .specify/project-sync-state.json in .specify/extensions/project/config.json'),
    'PROJECT_STATUS_OPTIONS_REQUIRED': ('The Project config lists no Status options.', 'Columns are matched by option id.', 'python .specify/extensions/project/scripts/project_init.py --hooks-mode required --auto-create-columns'),
    'PROJECT_SYNC_MUST_BE_REQUIRED': ('The Project hook mode is not "required".', 'The managed workflow updates the board automatically.', 'python .specify/extensions/project/scripts/project_init.py --hooks-mode required'),
    'RECEIPT_PLACEHOLDER': ('A gating receipt field still holds the <...> placeholder from the claim template.', 'The agent must set every gating field.', 'Fill the field the message names, then complete again'),
    'REQUIRED_PROVIDER_UNAVAILABLE': ('The policy selects superspec for a stage but its command is not installed.', 'A selected provider is required, never substituted.', 'specify extension add superspec, or set the provider to core in .specify/workflow.yml'),
    'RESTORE_BACKUP_INVALID': ('install.py --restore was given a folder without before.json and before.zip.', 'Only a backup the installer wrote can be restored.', 'ls .specify/workflow/backups/*/ and pass the folder doctor named'),
    'ROLLBACK_CONFLICT': ('The rollback found managed files changed by something else; the backup was kept.', 'Restoring over foreign changes would destroy them.', 'Review the backup folder named in the message, then ' + INSTALL_SCRIPT + ' --restore <backup folder>'),
    'SKILL_INVENTORY_LARGE': ('A host loads more skills or description bytes than the configured threshold.', 'Every session pays that fixed cost.', 'Prune ~/.claude/skills, ~/.agents/skills and plugins, or raise skills.inventory_thresholds in .specify/workflow.yml'),
    'SKILL_INVENTORY_UNAVAILABLE': ('The skill inventory scan failed; doctor still ran.', 'An unreadable plugin manifest or odd path stopped the scan.', 'Fix the file named in the message, then ' + W + ' doctor --project'),
    'STAGE_ALREADY_ACTIVE': ('The feature already has an active claim.', 'One session works a stage at a time.', W + ' status --feature <feature>; recover the claim if its owner stopped'),
    'STATUS_TARGET_REQUIRED': ('status was given neither --feature nor --issue.', 'It needs one feature to report on.', W + ' status --feature specs/<slug>, or ' + W + ' status --issue <n>'),
    'STALE_RECEIPT': ("A recorded stage's inputs changed after its receipt was written.", 'Evidence must match the inputs it was produced from.', 'python .specify/extensions/workflow/scripts/gate_explain.py --feature <feature> for the exact amend or redo recipe'),
    'WORKFLOW_BUSY': ('Another process holds the runtime lock; the message names its pid and host.', 'Two commands must not write the same checkpoint at once.', 'Wait for that process, or delete the lock once you have checked the process is gone'),
    'WORKFLOW_DOWNGRADE_UNSUPPORTED': ('upgrade.py was given a version older than the installed one.', 'Downgrades are not supported.', 'python .specify/extensions/workflow/scripts/upgrade.py --version <installed or newer> --apply'),
    'WORKFLOW_INIT_REQUIRED': ('.specify/workflow.yml does not exist.', 'Every command reads the policy.', W + ' init --qa <on|off> --manual <on|off>'),
    'WORKFLOW_LOCK_RELEASE_BUSY': ('A lock could not be released because another process reclaimed it.', 'The lock file changed owner while this command ran.', W + ' status --feature <feature>; run the command again'),
    'WORKFLOW_START_REQUIRED': ('The feature has no checkpoint.', 'Every stage command needs the binding start writes.', W + ' start --feature <feature> --issue <owner/repo#N>'),
    'WORKFLOW_UPGRADE_IN_PROGRESS': ('An upgrade lock exists.', 'Claims and installs wait while an upgrade runs; a crashed upgrade keeps the lock on purpose.', 'Rerun python .specify/extensions/workflow/scripts/upgrade.py --version <v> --apply, which reclaims the lock'),
    'WORKFLOW_UPGRADE_ROLLED_BACK': ('The upgrade failed and the snapshot was restored.', 'Managed files are never left half-upgraded.', 'Read the cause in the message, fix it, then rerun the upgrade'),
}


def explain(message, feature=None):
    """`explain` and `next` for a `CODE[: detail]` message whose code the registry knows; {} otherwise."""
    what, why, command = ERRORS.get(str(message).split(':', 1)[0].strip(), (None, None, None))
    if not what:
        return {}
    return {'explain': what + ' ' + why, 'next': command.replace('<feature>', feature) if feature else command}


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
    result = subprocess.run([GIT, *args], cwd=root, capture_output=True, **options)
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

