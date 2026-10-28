#!/usr/bin/env python3
"""Sanduq workflow state machine. Commands dispatch agents; this runtime never simulates them."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import re
import shlex
import socket
import stat
import subprocess
import sys
import time
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

# Also supports importlib loading directly from the canonical source tree.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sanduq_hash import eol_drift, portable_content, portable_files, text_attributes
import sanduq_ci
import skill_inventory
import source_key as sk
import lean_policy
import verification_plan
import evidence_snapshot
import execution_tools
import lifecycle
import memory_handoff
import wf_ownership
try:
    import sanduq_remote
except ModuleNotFoundError:  # the source tree; package.py copies it into scripts/
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'shared'))
    import sanduq_remote
# Moved to the shared module (round 4, D4); re-exported for Scope's workflow_policy, memory_handoff and the tests.
from sanduq_remote import _normalize_path_remote, _strip_dotgit, normalize_remote_url, same_github_repository

import yaml
from packaging.specifiers import SpecifierSet
from packaging.version import Version

# The runtime modules (W9), lowest layer first. Every name is re-exported, so `from workflow import X` and
# `w.X` keep working. The operation memo `_OPERATION` lives only in wf_core and is never copied here.
from wf_core import (SCHEMA, CHECKPOINT_SCHEMA, CHECKPOINT_SCHEMAS, RANGES, BASE_STAGES, COMMANDS, CORE_INPUTS,
                     INPUT_ROLES, RECEIPT_POLICY_KEYS, AMENDMENT_ASSESSMENTS, AMENDMENT_DEPENDENTS,
                     RUNTIME_RECEIPT_FIELDS, SOURCE_STAGES, EFFORT_SCORES, TIERS, DEFAULT_PROFILES, LITE_SKIPPED,
                     LITE_FOLDED, LITE_OPTIONAL_INPUTS, LINT_COMMAND, ARTIFACT_BUDGETS, ARTIFACT_ENFORCE, PROJECT_SYNC_PHASES,
                     PROJECT_SYNC_POINTS, PROJECT_SYNC_SCRIPT, PROJECT_SYNC_STEPS, DEFAULT_SYNC_STATE,
                     SYNC_BINDING_PREFIX, SYNC_ADMINISTRATIVE, TASK_ISSUE_MODES, PROJECT_SYNC_MODES,
                     MINIMAL_SYNC_PHASES, SIDE_EFFECTS, RENDER_MARKER,
                     HANDOFF_BEGIN, HANDOFF_END, DOCTOR_CACHE, DOCTOR_CACHE_SECONDS, DOCTOR_CACHE_FILES,
                     WORKFLOW_SCRIPT, WORKFLOW_PACKAGE_PREFIX, WorkflowError, require, now, read, digest,
                     POLICY_DIGEST_VERSION, OPERATIONAL_POLICY, delivery_digest, checkpoint_policy_digest, replace_file,
                     write, inside, portable_label, canonical_path, REPARSE_POINT, _no_link_below, GIT_READS, run_git,
                     git_ok, git, OPERATIONAL_DIRS, operation, _memo, _wrote, default_actor,
                     require_not_delegated_context, RUNTIME_DECLARATION, ensure_local_excludes, locked, ERRORS,
                     explain, GIT, W, INSTALL_SCRIPT)
from wf_identity import (github_repository, previous_branch, target_branch, normalized_remote, origin_url, root_commit_sha,
                         is_shallow_clone, repo_identity, current_identity, root_commit_still_reachable, same_remote,
                         identity_matches, legacy_history_signal, verify_checkpoint_identity, root_history_changed,
                         require_issue_repository_binding, issue_identity, prepare_issue, require_shared_history,
                         feature_for_issue, git_lines)
from wf_fingerprints import (sync_state_label, sync_entry, sync_projection, sync_binding,
                             normalized_text, text_fingerprints, fingerprint_files,
                             git_text_attributes, prefetch_attributes, source_fingerprints, inventory_label,
                             store_source_inventory, source_fingerprints_of, DECISION_RECORDS_PREFIX, DECISION_LEDGER,
                             decision_projection, recorded_decision_ids)
from wf_policy import (default_policy, select_gate, validate_policy, _positive, validate_front_half_policy, tier,
                       state_tier, feature_tier, skipped_stages, project_sync, task_issue_mode, side_effects,
                       matches_side_effect, load_policy, stages, OPERATIONAL_SUBKEYS, policy_cutoff, POLICY_KEYS,
                       unknown_policy_key, parse_policy, PolicyLoader, project_sync_mode, sync_phases,
                       sync_phase_written, board_mode_line)
from wf_health import (registry, compatible, active_host, RUNNING_HOST_ENV, running_host, command_exists, package_digest, resolve_commands,
                       project_errors, SCOPE_STATUSES, project_defaults, MANAGED_CI, preserved_ci_path, ci_errors,
                       delegation_errors, host_warnings, progress_wiring_warnings, guard_approval_warnings,
                       doctor_cache_key, store_doctor_cache, cached_doctor, doctor, lean_preflight, pr_lint_binding,
                       upgrade_command, dependency_errors, PHASE_DEFAULTS, INERT_VALUES, inert_value_warnings,
                       interrupted_install_errors, history_errors, HOOK_PYTHON_PROBE, hook_python_warnings,
                       SANDUQ_REPOSITORY, SANDUQ_AUTHOR, COMPANIONS, companion_inventory_errors)
from wf_receipts import (verify_sync_binding, same_path, recorded_sync_fields, handoff_text, native_run_status,
                         sync_retry, context_gate, measured_context_gate, required_inputs, first_phase_tasks,
                         consulted_inputs, without_required, canonical_receipt, dependency_fingerprints, role_exempt,
                         require_input_roles, validate_input_roles, consulted_drift, gate_settings, affected_command,
                         verification_check, affected_lanes, source_drift, current_source_key, _HEX40, _HEX64,
                         _positive_int, _string_list, diff_review_command, diff_review_shell, diff_review_sha256,
                         ci_evidence_complete, ci_evidence_current, validate_evidence_snapshots, receipt_status,
                         receipt_current, recovery_recipe, upstream_drift, receipt_drift, ready_checks,
                         coding_review_checks, CLAIM_HEARTBEAT_SECONDS, claim_owner, waiting_questions,
                         feature_skipped)


# Where `claim` tells the dispatcher to read this stage's own instructions, project-relative
# (matches the installed layout, e.g. `.specify/extensions/workflow/skills/workflow/
# references/stage-scope.md`). One file per BASE_STAGES entry; see SKILL.md's stage
# reference map and extensions/workflow/tests/test_workflow.py for the completeness check.
def stage_reference(stage):
    return WORKFLOW_PACKAGE_PREFIX + 'skills/workflow/references/stage-' + stage + '.md'


# The one-page lite lifecycle a session reads instead of the dispatcher references (lite re-measure, driver 2).
LITE_CARD = WORKFLOW_PACKAGE_PREFIX + 'skills/workflow/references/lite.md'
CLARIFY_CATEGORIES = ('functional', 'data', 'interaction', 'non_functional', 'integrations', 'edge_cases',
                      'constraints', 'terminology', 'completion', 'placeholders')


def claim_cli(relative, token):
    """The exact complete and pause commands for a held claim, so no `--help` look-up is needed."""
    return {'complete': WORKFLOW_SCRIPT + ' complete --feature ' + relative + ' --token ' + token +
                        ' --receipt <receipt.json>',
            'pause': WORKFLOW_SCRIPT + ' pause --feature ' + relative + ' --reason "<the question or failure>"'}


def reference_text(root, stage, parts=()):
    """The stage reference's content followed by `parts` (names relative to the references folder), each from the
    installed package, else from this package's own tree."""
    folder = WORKFLOW_PACKAGE_PREFIX + 'skills/workflow/references/'
    texts = []
    for relative in [stage_reference(stage)] + [folder + part for part in parts]:
        for path in (Path(root) / relative, Path(__file__).resolve().parents[1] / relative[len(WORKFLOW_PACKAGE_PREFIX):]):
            if path.is_file():
                texts.append(path.read_text(encoding='utf-8-sig'))
                break
        else:
            if not texts:
                return None
    return texts[0] if len(texts) == 1 else '\n'.join(text.rstrip('\n') + '\n' for text in texts)


def protocol_summary(policy, tier):
    """The Execute rules that must hold in every turn, printed on every Execute claim even when the full protocol is not
    (OMAR-18: an agent cannot tell whether compaction kept them)."""
    owner = ('the lifecycle coordinator (lean execution)' if lean_policy.enabled(policy, tier)
             else 'a dedicated orchestration agent')
    return ('Execute protocol summary: ' + owner + ' schedules and integrates. Workers change only their owned paths '
            'and never stage, commit, push, run git stash, git add -A or git add ., or run any delegate_dispatch.py '
            'command; the orchestration agent stages owned paths by name. accept, reassign, adopt and trust-reset run '
            'only in the top-level dispatcher session. A worker returns the eleven-line result in execution-report.md; '
            'copy its Model line beside the requested model into the handoff and the receipt summary. Report only on a '
            'state change; never end a turn owning background work. Full text: claim --verbose.')


def execute_protocol(policy, tier, reporting):
    """The Execute protocol parts that apply: the core, lean or a dedicated orchestration agent, delegated workers
    when delegation is on, and the calls of the reporting mode."""
    parts = ['execution-assign.md', 'execution-report.md',
             'execute/lean.md' if lean_policy.enabled(policy, tier) else 'execute/orchestrator.md']
    if policy['delegation']['enabled']:
        parts.append('execute/delegated-workers.md')
    parts.append('execute/reporting-legacy.md' if reporting == 'legacy' else 'reporting.md')
    return parts


# OMAR-01: receipt fields whose value decides a pass. receipt_template prints them as `<...>` placeholders, and a
# placeholder left in place is refused, so an unedited template never records a passed stage.
RECEIPT_GATING_FIELDS = ('outcome', 'effort_score', 'unresolved', 'answers_applied', 'lint', 'native_links_verified',
                         'blocking_findings', 'images_verified', 'pr_url')
PLACEHOLDER = re.compile(r'<[^<>]+>')


def reject_placeholders(receipt):
    """RECEIPT_PLACEHOLDER naming the first gating field that still holds a `<...>` template value."""
    for field in RECEIPT_GATING_FIELDS:
        value = receipt.get(field)
        for name, item in (value.items() if isinstance(value, dict) else [(None, value)]):
            if isinstance(item, str) and PLACEHOLDER.search(item):
                path = field + ('.' + name if name else '')
                raise WorkflowError('RECEIPT_PLACEHOLDER: ' + path + ' still holds the receipt_template placeholder '
                                    + repr(item) + '; set it to what this stage actually produced (every gating field '
                                    'is set by the agent), then run workflow.py complete again with the edited receipt')
    evidence = receipt.get('evidence')
    for item in evidence if isinstance(evidence, list) else []:
        if isinstance(item, str) and PLACEHOLDER.search(item):
            raise WorkflowError('RECEIPT_PLACEHOLDER: evidence still holds the receipt_template placeholder ' +
                                repr(item) + '; list the existing files that prove the work (test or lint output, '
                                'publication record), then run workflow.py complete again')


def other_feature_command(relative, active):
    """SAMY-12: the exact recover command for another feature's active claim."""
    return (WORKFLOW_SCRIPT + ' recover --feature ' + relative + ' --token ' + str(active.get('token')) +
            ' --reason "<why that claim is abandoned>"')


MANUAL_INIT_NEXT = ('User Manual is selected but User-Manual/manual.yml does not exist. Run $speckit-user-manual-init '
                    'once on the target branch, approve its module map and commit User-Manual/ there; every feature '
                    'then updates that one manual')


def manual_missing(root, policy):
    """F4: the manual is selected but not initialised, so each feature would propose and create its own."""
    return policy['processes']['user_manual'] and not (Path(root) / 'User-Manual/manual.yml').is_file()


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
        require(state and state.get('schema_version') in CHECKPOINT_SCHEMAS, 'WORKFLOW_START_REQUIRED')
        require(state['feature'] == self.relative, 'CHECKPOINT_IDENTITY_MISMATCH')
        adopted = verify_checkpoint_identity(self.root, state, self.relative)
        if adopted is not None:
            # A pre-1.8.0 checkpoint is upgraded in memory only -- every
            # mutating command loads through here and then calls `save`,
            # which persists whatever `state` it was handed -- so a
            # read-only `load` (e.g. `next`) never writes anything itself.
            state['repo_identity'] = adopted
        require(allow_branch_change or state['branch'] == git(self.root, 'branch', '--show-current'), 'CHECKPOINT_BRANCH_MISMATCH')
        self.reconcile_skipped(state)
        return state

    def reconcile_skipped(self, state):
        """`issue_sync.taskstoissues` is operational (AHMED-30), so the recorded Tasks-to-Issues skip follows the
        current policy and the required inputs follow the stage selection. Switched back on, the skip stays once a
        later stage has a receipt: running Tasks-to-Issues then would invalidate those receipts."""
        skipped = dict(state.get('skipped') or {})
        if task_issue_mode(self.policy) == 'off':
            if 'taskstoissues' not in state['receipts']:
                skipped.setdefault('taskstoissues', 'issue_sync.taskstoissues: off')
        elif skipped.get('taskstoissues') == 'issue_sync.taskstoissues: off' and not any(
                BASE_STAGES.index(stage) > BASE_STAGES.index('taskstoissues') for stage in state['receipts']):
            # Only the board-mode skip follows the policy; the lite tier's skip is fixed with the tier.
            del skipped['taskstoissues']
        self.record_skipped(state, skipped)

    def _relocate_plan(self, state, allow_branch_rebind, allow_repository_rename, new_issue, keep_issue_number,
                       allow_history_change=False):
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
        # Codex round 1, finding 6: an issue choice only means something when
        # the repository changed; silently ignoring it would let a caller
        # believe an issue was rebound when nothing was.
        require(repository_renamed or not (new_issue or keep_issue_number),
                'RELOCATE_ISSUE_NOT_APPLICABLE: the repository has not changed (still ' + old_repo +
                '), so --issue and --keep-issue-number do not apply; omit them')
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
        history_changed = root_history_changed(self.root, state, new_identity)
        blockers = []
        if new_repo is None:
            # `load` requires a resolvable GitHub remote, so a relocate that
            # succeeded without one would write a checkpoint nothing can read
            # (Codex round 1, finding 3), whatever `--issue` claims.
            blockers.append('RELOCATE_GITHUB_REMOTE_REQUIRED: this repository has no resolvable GitHub '
                            'remote (origin), so a relocated checkpoint could not be loaded here; configure '
                            'origin first')
        if history_changed and not allow_history_change:
            blockers.append('HISTORY_CHANGED: this checkpoint records a root history that is not the history of this '
                            'repository (a recreated or unrelated repository sharing the remote); pass '
                            '--allow-history-change to confirm it is the same project with rewritten or '
                            'recreated history, not a foreign checkpoint; recorded in the relocation log')
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
                'repository_renamed': repository_renamed, 'new_issue': resolved_issue,
                'history_changed': history_changed, 'blockers': blockers}

    def relocate(self, reason, preview=False, allow_branch_rebind=False, allow_repository_rename=False,
                new_issue=None, keep_issue_number=False, actor=None, allow_history_change=False):
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

        A checkpoint whose recorded root history is not this repository's
        (Codex round 1, finding 2) is also a blocker unless
        `allow_history_change` acknowledges it; `history_changed` is
        recorded on the relocation entry either way.

        Either way, the whole decision is appended to `relocations[]` with
        its actor, reason and both identities/repositories, never silently.
        """
        require_not_delegated_context('relocate')
        require(isinstance(reason, str) and reason.strip(), 'RELOCATE_REASON_REQUIRED')
        require(not (new_issue and keep_issue_number),
                'RELOCATE_ISSUE_OPTIONS_CONFLICT: pass --issue or --keep-issue-number, not both')
        if preview:
            state = read(self.path)
            require(state and state.get('schema_version') in CHECKPOINT_SCHEMAS, 'WORKFLOW_START_REQUIRED')
            require(state['feature'] == self.relative, 'RELOCATE_FEATURE_MISMATCH')
            plan = self._relocate_plan(state, allow_branch_rebind, allow_repository_rename, new_issue, keep_issue_number,
                                       allow_history_change)
            return {'preview': True, 'feature': self.relative, 'old_identity': plan['old_identity'],
                    'new_identity': plan['new_identity'], 'branch_from': state['branch'],
                    'branch_to': plan['current_branch'], 'branch_matches': plan['branch_matches'],
                    'allow_branch_rebind': allow_branch_rebind, 'old_repository': plan['old_repo'],
                    'new_repository': plan['new_repo'], 'repository_renamed': plan['repository_renamed'],
                    'allow_repository_rename': allow_repository_rename, 'new_issue': plan['new_issue'],
                    'history_changed': plan['history_changed'], 'allow_history_change': allow_history_change,
                    'blockers': plan['blockers'], 'can_apply': not plan['blockers']}
        scope_rebind = None
        with locked(self.lock):
            state = read(self.path)
            require(state and state.get('schema_version') in CHECKPOINT_SCHEMAS, 'WORKFLOW_START_REQUIRED')
            require(state['feature'] == self.relative, 'RELOCATE_FEATURE_MISMATCH')
            require(not state['active'], 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_RELOCATE')
            plan = self._relocate_plan(state, allow_branch_rebind, allow_repository_rename, new_issue, keep_issue_number,
                                       allow_history_change)
            require(not plan['blockers'], '; '.join(plan['blockers']))
            entry = {'actor': actor or default_actor(self.root), 'at': now(), 'reason': reason.strip(),
                     'old_identity': plan['old_identity'], 'new_identity': plan['new_identity'],
                     'branch_rebound': False, 'history_changed': plan['history_changed']}
            if not plan['branch_matches']:
                entry.update(branch_rebound=True, branch_from=state['branch'], branch_to=plan['current_branch'])
                state['branch'] = plan['current_branch']
            if plan['repository_renamed']:
                entry.update(repository_renamed=True, old_repository=plan['old_repo'],
                            new_repository=plan['new_repo'], new_issue=plan['new_issue'])
                # `scope-source.json` binds the same issue independently (`start`,
                # `bind` and the scope extension's `bound_claim` all compare it),
                # so it is rebound together with the checkpoint (Codex round 1,
                # finding 4): the new content is prepared first, then replaced
                # in just before the checkpoint write, and put back to its
                # original bytes if that write fails, so a failure between the
                # two never leaves the pair split. A hard kill between them
                # still leaves the scope file ahead of the checkpoint, which
                # re-running relocate recomputes and rewrites identically.
                source_path = self.feature / 'scope-source.json'
                source = read(source_path, {})
                if source:
                    new_owner_repo, new_number = plan['new_issue'].split('#')
                    scope_rebind = (source_path, source_path.read_bytes(),
                                    {**source, 'repo': new_owner_repo, 'issue': int(new_number)})
                state['issue'] = plan['new_issue']
            state['repo_identity'] = plan['new_identity']
            state.setdefault('relocations', []).append(entry)
            if scope_rebind:
                source_path, original_bytes, rebound = scope_rebind
                write(source_path, rebound)
            try:
                self.save(state)
            except BaseException:
                if scope_rebind:
                    restore = source_path.with_name(source_path.name + '.' + uuid.uuid4().hex + '.tmp')
                    restore.write_bytes(original_bytes)
                    os.replace(restore, source_path)
                raise
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
            state['active']['heartbeat_at'] = now()
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
            for stage in plan['invalidated']:
                state['receipts'].pop(stage)
                lifecycle.queue(state, stage, 'invalidated', reason='migrate: ' + reason.strip())
            try:
                record = self._amend_sync_binding(state, reason, 'migrate')
                sync = {'amended': sorted((record or {}).get('receipts', {})), 'refused': None}
            except WorkflowError as exc:  # the raw hashes stay byte-exact until sync-amend
                sync = {'amended': [], 'refused': str(exc)}
            self.save(state)
            return {'migrated': True, 'migration': copy.deepcopy(entry), 'sync_binding': sync, 'next': self.next(state)}

    def migration_plan(self, state, invalidate_from=None):
        """What a migration of this checkpoint would record, computed without writing.

        `preview_migration` and `migrate` share this, so the reviewed lists are
        exactly the lists the write records.
        """
        if invalidate_from:
            require(invalidate_from in BASE_STAGES, 'INVALID_MIGRATION_STAGE')
        old_policy_digest = state['policy_digest']
        policy_digest = delivery_digest(self.policy)
        commands = resolve_commands(self.root, self.policy, state_tier(state))
        selected = stages(self.policy, state_tier(state), state.get('skipped'))
        changed = [stage for stage in selected if state['commands'].get(stage) != commands[stage]]
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
                    stage for stage in selected if state['commands'].get(stage) != commands[stage]),
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
                for name in affected:
                    state['receipts'].pop(name)
                    lifecycle.queue(state, name, 'invalidated', reason='refresh ' + stage + ': ' + reason.strip())
                self.save(state)
            return {'refreshed': list(affected), 'next': self.next(state)}

    # Receipt fields a re-record keeps from the receipt it replaces unless the entry restates them.
    CARRIED_FIELDS = ('unresolved', 'answers_applied', 'parent_issue', 'native_links_verified', 'lazy', 'effort_score')
    UPSTREAM_ENTRY_FIELDS = ('summary', 'evidence', 'inputs', 'input_roles', 'evidence_snapshots', 'lint') + CARRIED_FIELDS

    def upstream_plan(self, state, through):
        """Per stale or removed receipt from Specify through `through`: the changed input paths, which stages
        only changed by whitespace in Markdown (re-stamped without a model pass), and which need a receipt."""
        tier = self.tier_of(state)
        first, last = BASE_STAGES.index('specify'), BASE_STAGES.index(through)
        changed, restamp, needs = {}, [], []
        for stage in stages(self.policy, state_tier(state), state.get('skipped')):
            if not first <= BASE_STAGES.index(stage) <= last:
                continue
            receipt = state['receipts'].get(stage)
            if receipt is None:
                changed[stage] = required_inputs(self.root, self.relative, stage, tier)
                needs.append(stage)
                continue
            status = receipt_status(self.root, self.relative, stage, receipt, self.policy, tier)
            if status['current']:
                continue
            paths = upstream_drift(self.root, self.relative, stage, receipt, tier)
            changed[stage] = paths
            (restamp if status.get('reason') == 'explicit-drift' and not paths else needs).append(stage)
        return {'changed': changed, 'restamp': restamp, 'needs_receipt': needs}

    def revalidate_upstream(self, through, receipts=None, plan=False, actor=None):
        """Re-record stale upstream receipts (Specify through `through`) in one locked operation.

        `plan` only reports `changed: {stage: [paths]}`. Otherwise `receipts` is `{stages: {<stage>:
        {summary, evidence[], inputs[]}}}` with an entry for every stage that needs one; each is checked the
        way `complete` checks a receipt (binding, decisions ledger, required inputs). A stage whose only drift
        is whitespace in Markdown inputs is re-stamped with the new byte hashes and no entry."""
        require(through in BASE_STAGES and BASE_STAGES.index('specify') <= BASE_STAGES.index(through)
                < BASE_STAGES.index('execute'), 'REVALIDATE_UPSTREAM_STAGE_INVALID: --through names a stage from '
                'specify to taskstoissues')
        with locked(self.lock):
            state = self.load()
            active = state['active']
            require(not active, 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_REVALIDATE_UPSTREAM: recover the ' +
                    str((active or {}).get('stage')) + ' claim first')
            if state['policy_digest'] != checkpoint_policy_digest(state, self.policy):
                require(policy_cutoff(state.get('policy'), self.policy) > BASE_STAGES.index(through),
                        'POLICY_CHANGED: the policy change reaches a stage through ' + through + '; claim it instead')
            found = self.upstream_plan(state, through)
            if plan:
                return {'plan': True, 'feature': self.relative, 'through': through, **found}
            require(found['changed'], 'REVALIDATE_UPSTREAM_NOT_NEEDED: every receipt through ' + through + ' is current')
            entries = (receipts or {}).get('stages') if isinstance(receipts, dict) else None
            require(isinstance(entries, dict), 'REVALIDATE_UPSTREAM_RECEIPT_INVALID: expected {stages: {<stage>: '
                    '{summary, evidence, inputs}}}')
            extra = sorted(set(entries) - set(found['needs_receipt']))
            require(not extra, 'REVALIDATE_UPSTREAM_STAGE_NOT_STALE: ' + ', '.join(extra) +
                    ' (only stale or removed stages with changed inputs take an entry; see --plan)')
            missing = [stage for stage in found['needs_receipt'] if stage not in entries]
            require(not missing, 'REVALIDATE_UPSTREAM_RECEIPT_MISSING: ' + ', '.join(missing))
            tier = self.tier_of(state)
            episode = 'revalidate-upstream:' + uuid.uuid4().hex
            at = now()
            record = {'episode_id': episode, 'at': at, 'actor': actor or default_actor(self.root)}
            for stage in [s for s in BASE_STAGES if s in found['changed']]:
                old = state['receipts'].get(stage) or {}
                if stage in found['restamp']:
                    stored = copy.deepcopy(old)
                    current = fingerprint_files(self.root, stored['fingerprints'], feature=self.relative,
                                                like=stored['fingerprints'])
                    drifted = sorted(path for path in stored['fingerprints'] if current[path] != stored['fingerprints'][path])
                    stored['fingerprints'].update(current)
                    stored['revalidated_upstream'] = {**record, 'via': 'whitespace-only', 'paths': drifted}
                    reason = 'whitespace-only: ' + ', '.join(drifted)
                else:
                    entry = entries[stage]
                    require(isinstance(entry, dict) and set(entry) <= set(self.UPSTREAM_ENTRY_FIELDS),
                            'REVALIDATE_UPSTREAM_RECEIPT_INVALID: ' + stage + ' takes ' + ', '.join(self.UPSTREAM_ENTRY_FIELDS))
                    carried = {key: old[key] for key in self.CARRIED_FIELDS if key in old}
                    receipt = self._check_receipt(stage, {**carried, **entry, 'stage': stage, 'outcome': 'passed'}, tier)
                    self._check_stage_rules(state, stage, receipt)
                    stored = copy.deepcopy(receipt)
                    if stored.get('input_roles') is None:
                        stored.pop('input_roles', None)
                    self._stamp(state, stage, receipt, stored, tier)
                    stored['revalidated_upstream'] = {**record, 'via': 'receipt', 'paths': found['changed'][stage]}
                    reason = 're-recorded: ' + ', '.join(found['changed'][stage])
                stored['completed_at'] = at
                state['receipts'][stage] = stored
                lifecycle.queue(state, stage, 'revalidate-upstream', episode_id=episode, at=at, reason=reason)
            ensure_local_excludes(self.root)
            write(self.path.parent / 'backups' / (uuid.uuid4().hex + '.json'), read(self.path))
            self.save(state)
            return {'revalidated': [s for s in BASE_STAGES if s in found['needs_receipt']],
                    'restamped': found['restamp'], 'changed': found['changed'], 'episode_id': episode,
                    'next': self.next(state)}

    def amend(self, stage, evidence, reason, assessment, actor=None, evidence_only=False):
        """Re-hash one evidence entry of a completed receipt under a recorded assessment.

        Every other fingerprint keeps its hash. `unchanged` asserts the stage's
        conclusion and claimed checks still hold (an editorial fix); `changed`
        says they moved, so the receipts resting on them (verify, review, ready,
        from the amended stage on) are marked stale and must be re-recorded.
        """
        require(stage in BASE_STAGES, 'INVALID_AMEND_STAGE: ' + str(stage))
        require(assessment in AMENDMENT_ASSESSMENTS, 'AMENDMENT_ASSESSMENT_INVALID: expected unchanged or changed')
        require(isinstance(reason, str) and reason.strip(), 'AMENDMENT_REASON_REQUIRED')
        from delegate_dispatch import require_not_worker_context
        require_not_worker_context(self.relative)
        with locked(self.lock):
            state = self.load()
            require(not state['active'], 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_AMEND')
            receipt = state['receipts'].get(stage)
            require(receipt, 'RECEIPT_MISSING: ' + stage)
            require(evidence in receipt.get('evidence', []) and evidence in receipt.get('fingerprints', {}),
                    'AMEND_PATH_NOT_EVIDENCE: ' + str(evidence) + ' is not listed as evidence of ' + stage)
            if evidence_only:
                # A caller that classified this path as evidence-only earlier
                # (gate-explain --auto-fix) is re-checked against the receipt
                # as it is now, under this lock, immediately before the write.
                require(evidence not in set(receipt.get('inputs') or []) | set(required_inputs(
                        self.root, self.relative, stage, self.tier_of(state))),
                        'AMEND_PATH_IS_A_DEPENDENCY: ' + str(evidence) + ' is a declared input of ' + stage)
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
                        lifecycle.queue(state, name, 'invalidated',
                                        reason='changed amendment of ' + stage + ': ' + reason.strip())
            record['staled'] = staled
            receipt['fingerprints'][evidence] = new_hash
            receipt.setdefault('amendments', []).append(record)
            self.save(state)
            return {'amended': True, 'stage': stage, 'amendment': copy.deepcopy(record),
                    'current': receipt_status(self.root, self.relative, stage, receipt, self.policy,
                                              self.tier_of(state))['current'],
                    'stale': staled, 'next': self.next(state)}

    def _amend_sync_binding(self, state, reason, via, actor=None):
        """Replace each legacy raw hash of the Project Sync state with the binding projection, once the entry is
        verified (`verify_sync_binding`) and the recorded bytes are found with only administrative fields changed
        (`recorded_sync_fields`); the old and new values and those fields go to an `administrative-amendment` lineage
        record. No other hash moves. Returns the record, or None when no receipt holds a raw hash."""
        label = sync_state_label(self.root)
        raw = {}
        for stage, receipt in state['receipts'].items():
            for path, value in receipt['fingerprints'].items():
                if same_path(self.root, path, label) and not value.startswith(SYNC_BINDING_PREFIX):
                    raw[stage, path] = value
        if not raw:
            return None
        entry = verify_sync_binding(self.root, self.relative, state)
        new = sync_binding(self.root, self.relative)
        record = {'kind': 'administrative-amendment', 'via': via, 'path': label, 'reason': reason.strip(),
                  'actor': actor or default_actor(self.root), 'at': now(), 'receipts': {}}
        for (stage, path), old in raw.items():
            fields = recorded_sync_fields(self.root, label, self.relative, old, entry)
            changed = [field for field in fields if not SYNC_ADMINISTRATIVE.fullmatch(field)]
            require(not changed, 'SYNC_BINDING_MISMATCH: ' + stage + ' was recorded with other ' + ', '.join(changed))
            record['receipts'][stage] = {'before': old, 'after': new, 'fields': fields}
        for stage, path in raw:  # only once every receipt passed
            state['receipts'][stage]['fingerprints'][path] = new
        state.setdefault('lineage', []).append(record)
        return record

    def sync_amend(self, reason, actor=None):
        """Convert receipts whose Project Sync state dependency is a raw byte hash (recorded before 1.16.0)."""
        require(isinstance(reason, str) and reason.strip(), 'SYNC_AMEND_REASON_REQUIRED')
        from delegate_dispatch import require_not_worker_context
        require_not_worker_context(self.relative)
        with locked(self.lock):
            state = self.load()
            require(not state['active'], 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_SYNC_AMEND')
            record = self._amend_sync_binding(state, reason, 'sync-amend', actor)
            require(record, 'SYNC_AMEND_NOT_NEEDED: no receipt holds a raw hash of ' + sync_state_label(self.root))
            ensure_local_excludes(self.root)
            write(self.path.parent / 'backups' / (uuid.uuid4().hex + '.json'), read(self.path))
            self.save(state)
            return {'amended': sorted(record['receipts']), 'amendment': copy.deepcopy(record), 'next': self.next(state)}

    def sync_project(self, phase):
        """Run the Project script for `phase`, recording `project_sync` pending before the call and done or failed
        after it. Done needs an `ok` line and the entry showing the phase's configured status. A pending or done
        attempt at this phase whose entry already shows that status is done without another call, so a retry after
        a lost result never repeats the remote write; a failed attempt always runs again."""
        require(phase in PROJECT_SYNC_STEPS, 'PROJECT_SYNC_PHASE_INVALID: ' + str(phase))
        if not sync_phase_written(self.policy, phase):
            # REQ-22: a parking phase in minimal mode, or any phase in off mode, is a no-op write, recorded as such.
            with locked(self.lock):
                state = self.load()
                state['project_sync'] = {'phase': phase, 'state': 'done', 'at': now(),
                                         'summary': 'skipped: project_sync.mode ' + project_sync_mode(self.policy) +
                                                    ' does not write phase ' + phase}
                self.save(state)
            return {'ok': True, 'applied': False, 'project_sync': state['project_sync']}
        with locked(self.lock):
            state = self.load()
            record = state.get('project_sync') or {}
            status, reached, targeted = self.sync_reached(phase)
            applied = record.get('phase') == phase and record.get('state') in ('pending', 'done') and targeted and reached
            state['project_sync'] = {'phase': phase, 'state': 'done' if applied else 'pending', 'at': now(),
                                     'summary': 'already applied: status ' + status if applied else None}
            self.save(state)
        if applied:
            return {'ok': True, 'applied': False, 'project_sync': state['project_sync']}
        done = subprocess.run([sys.executable, str(self.root / PROJECT_SYNC_SCRIPT), '--phase', phase,
                               '--feature', self.feature.name, '--summary'],
                              cwd=self.root, capture_output=True, text=True, encoding='utf-8', errors='replace')
        lines = (done.stdout.strip() or done.stderr.strip() or 'error exit=' + str(done.returncode)).splitlines()
        status, reached, _ = self.sync_reached(phase)
        # An `ok` run can leave the status unchanged (an unmapped column, no project item): not done.
        ok = done.returncode == 0 and lines[-1].startswith('ok ') and reached
        summary = lines[-1] if reached else lines[-1] + ' (status ' + str(status) + ' is not the configured status)'
        with locked(self.lock):
            state = self.load()
            state['project_sync'] = {'phase': phase, 'state': 'done' if ok else 'failed', 'at': now(),
                                     'summary': summary[:500]}
            self.save(state)
        return {'ok': ok, 'applied': True, 'project_sync': state['project_sync']}

    def sync_reached(self, phase):
        """(the entry's status, whether it is `phase`'s configured status, whether one is configured). With none
        configured it counts as reached. In-progress also accepts the in-review status Project moves to on an open PR."""
        phases = read(self.root / '.specify/extensions/project/config.json', {}).get('phaseToStatus') or {}
        try:
            status = read(self.root / sync_state_label(self.root), {}).get(self.feature.name, {}).get('status')
        except (ValueError, AttributeError):
            status = None
        targets = {phases.get(phase)} | ({phases.get('in-review')} if phase == 'in-progress' else set())
        targets.discard(None)
        return status, status in targets if targets else True, bool(targets)

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
            if stage == 'review':
                coding_review_checks(self.root, self.relative, self.policy, state)
            tier = self.tier_of(state)
            selected = stages(self.policy, state_tier(state), state.get('skipped'))
            require(stage in selected, 'STAGE_NOT_SELECTED: ' + stage)
            receipt = state['receipts'].get(stage)
            require(receipt, 'RECEIPT_MISSING: ' + stage)
            if state['policy_digest'] != checkpoint_policy_digest(state, self.policy):
                require(BASE_STAGES.index(stage) < policy_cutoff(state.get('policy'), self.policy),
                        'POLICY_CHANGED: the policy change reaches ' + stage + '; re-record it')
            for earlier in selected[:selected.index(stage)]:
                prior = state['receipts'].get(earlier)
                require(prior, 'EARLIER_STAGE_NOT_CURRENT: ' + earlier + ' has no receipt')
                prior_status = receipt_status(self.root, self.relative, earlier, prior, self.policy, tier)
                require(prior_status['current'], 'EARLIER_STAGE_NOT_CURRENT: ' + earlier + ' (make it current before ' +
                        stage + '). Recovery: ' + ' | '.join(
                            recovery_recipe(self.relative, earlier, prior_status, self.policy, prior, self.root)))
            mark = receipt.get('stale')
            require(not mark or (stage == 'verify' and mark.get('reason') == 'ci-lane-gap'),
                    'RECEIPT_MARKED_STALE: ' + json.dumps(mark) + '; a changed amendment needs a re-record')
            status = receipt_status(self.root, self.relative, stage, {**receipt, 'stale': None}, self.policy, tier)
            if status.get('reason') == 'explicit-drift':
                raise WorkflowError('EXPLICIT_FINGERPRINTS_CHANGED: ' + json.dumps(status['paths']) +
                                    '; revalidation never re-hashes inputs or evidence. Recovery: ' +
                                    ' | '.join(recovery_recipe(self.relative, stage, status, self.policy, receipt, self.root)))
            require(not status['current'] or mark, 'REVALIDATION_NOT_NEEDED: ' + stage + ' is current')
            dirty = sk.dirty_source_paths(self.root)
            require(not dirty, 'SOURCE_TREE_DIRTY: commit or stash source changes first: ' + ', '.join(dirty[:10]))
            head, key = git(self.root, 'rev-parse', 'HEAD'), sk.source_key(self.root, 'HEAD')
            inventory = source_fingerprints(self.root)
            drift = source_drift(receipt, inventory, self.root, self.relative)
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
                    lifecycle.queue(state, stage, 'revalidation-stale', episode_id='revalidation',
                                    reason='ci-lane-gap: ' + ', '.join(str(l) for l in lanes['gap']))
                    self.save(state)
                    return {'revalidated': False, 'stage': stage, 'lane_gap': lanes['gap'],
                            'run_id': evidence['run_id'], 'revalidation': copy.deepcopy(record),
                            'recovery': recovery_recipe(self.relative, stage, {'reason': 'marked-stale',
                                                        'stale': receipt['stale']}, self.policy, receipt),
                            'next': self.next(state)}
                checks = self.folded_ready_checks(state)
                if checks is not None:
                    record['checks'] = receipt['ready_checks'] = checks
                receipt['ci_evidence'] = evidence
                if lean_policy.enabled(self.policy, tier):
                    selected_plan = lean_policy.settings(self.policy).get('verification_plan')
                    if selected_plan:
                        try:
                            receipt['verification_snapshot'] = verification_plan.snapshot(self.root, selected_plan)
                        except ValueError as exc:
                            raise WorkflowError(str(exc)) from exc
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
            superseded = self.store_inventory(receipt, stage, inventory, uuid.uuid4().hex[:8])
            receipt['head'], receipt['source_key'] = head, key
            receipt.setdefault('revalidations', []).append(record)
            lifecycle.queue(state, stage, 'revalidated', episode_id='revalidation', reason=reason)
            self.save(state)
            self.drop_inventories([superseded])
            return {'revalidated': True, 'stage': stage, 'revalidation': copy.deepcopy(record),
                    'current': receipt_status(self.root, self.relative, stage, receipt, self.policy, tier)['current'],
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
                local = {'tree': sk.tree_of(self.root, plan['headSha']),
                         'key': sk.source_key(self.root, plan['headSha'], ci_evidence.plan_key_version(plan))}
            except sk.SourceKeyError:
                local = {'tree': 'unavailable (fetch ' + plan['headSha'] + ')', 'key': 'unavailable'}
        errors = ci_evidence.validate(evidence, repository, int(run_id), check['name'], check['workflow'],
                                      attempt and int(attempt), local, check['artifact_prefix'])
        if not errors and plan['headSha'] != head:
            if not git_ok(self.root, 'merge-base', '--is-ancestor', plan['headSha'], head):
                errors.append(f'Run head {plan["headSha"]} is not a commit of this branch (an ancestor of {head}).')
        if not errors and plan['sourceKey'] != sk.source_key(self.root, head, ci_evidence.plan_key_version(plan)):
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
        require(git_ok(self.root, 'merge-base', '--is-ancestor', base, head),
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
        if re.fullmatch(r'#?[1-9]\d*', str(issue or '')):
            # R5: a bare number, as `prepare` takes it, names an issue of origin.
            issue = github_repository(self.root) + '#' + str(issue).lstrip('#')
        require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9]\d*', issue), 'EXPLICIT_ISSUE_REQUIRED')
        require(same_github_repository(github_repository(self.root), issue.split('#')[0]), 'ISSUE_REPOSITORY_MISMATCH')
        require_shared_history(self.root)
        source = read(self.feature / 'scope-source.json', {})
        require(not source or f"{source.get('repo')}#{source.get('issue')}" == issue, 'FEATURE_BINDING_MISMATCH')
        with locked(self.lock):
            if self.path.exists():
                state = self.load()
                require(state['issue'] == issue, 'ISSUE_BINDING_CONFLICT')
                return state
            commands = resolve_commands(self.root, self.policy)
            target, corrected = target_branch(self.root)
            state = {'schema_version': CHECKPOINT_SCHEMA, 'run_id': uuid.uuid4().hex,
                     'repo_identity': repo_identity(self.root),
                     'branch': git(self.root, 'branch', '--show-current'), 'feature': self.relative,
                     'issue': issue, 'policy_digest_version': POLICY_DIGEST_VERSION,
                     'policy_digest': delivery_digest(self.policy),
                     'ci_policy_digest': digest(self.policy['ci']), 'commands': commands,
                     'policy': copy.deepcopy(self.policy), 'target_branch': target,
                     # REQ-21: frozen per feature here, outside the policy cutoff; a later policy edit changes
                     # only features started after it.
                     'clarification_transport': self.policy['clarification'].get('transport', 'github-comments'),
                     'receipts': {}, 'generation': 0, 'active': None, 'status': 'in-progress'}
            state['dependency_digest'] = package_digest(self.root)
            self.record_skipped(state, skipped_stages(self.policy, None))
            self.save(state)
            warnings = [corrected] if corrected else []
            if manual_missing(self.root, self.policy):
                warnings.append('MANUAL_NOT_INITIALIZED: ' + MANUAL_INIT_NEXT)
            return {**state, 'warnings': warnings} if warnings else state

    def record_skipped(self, state, skipped):
        """Record the stages this feature does not run (the tier's, the board mode's), once each in the log."""
        for name, reason in skipped.items():
            if name not in (state.get('skipped') or {}):
                lifecycle.queue(state, name, 'skipped', reason=reason)
        if skipped or state.get('skipped'):
            state['skipped'] = skipped

    def tier_of(self, state):
        """The frozen tier, or `full` (never None, so no helper re-reads the checkpoint mid-operation)."""
        return state_tier(state) or 'full'

    def store_inventory(self, receipt, stage, inventory, suffix=None):
        """Point a receipt at a freshly written inventory side file. Returns the superseded file's label, if any:
        it is removed only after the checkpoint naming the new one is saved, so a crash leaves a readable pair."""
        old = (receipt.get('source_inventory') or {}).get('path')
        receipt['source_inventory'] = store_source_inventory(
            self.root, self.relative, inventory_label(stage, receipt.get('claim_id'), suffix), inventory)
        receipt.pop('source_fingerprints', None)
        return old if old != receipt['source_inventory']['path'] else None

    def drop_inventories(self, labels):
        for label in filter(None, labels):
            try:
                inside(self.root, self.relative + '/' + label).unlink(missing_ok=True)
            except OSError:
                pass  # an orphaned inventory is harmless; the checkpoint no longer names it

    def save(self, state, preserve_head=False):
        self.__dict__.pop('_saved_next', None)
        # Every write is a version-2 checkpoint; a loaded version 1 is migrated here (W27).
        state['schema_version'] = CHECKPOINT_SCHEMA
        state.pop('repo_path', None)
        state['generation'] += 1
        state['updated_at'] = now()
        if not preserve_head:
            state['head'] = git(self.root, 'rev-parse', 'HEAD')
        state['stage_plan'] = {'v': 1, 'generation': state['generation'], 'stages': stages(self.policy, state_tier(state), state.get('skipped'))}
        state['next_action'] = self.evaluate_next_action(state)
        write(self.path, state)
        # The queued lifecycle events were written with the state; append them now, under the caller's
        # lock. A crash here leaves them queued and the next save replays them (deduplicated by event_id).
        if lifecycle.flush(state, self.feature):
            write(self.path, state)

    def evaluate_next_action(self, state):
        """Workflow's own next/next_stage evaluation, cached with its time and generation."""
        stamp = {'evaluated_at': now(), 'generation': state['generation']}
        active = state.get('active')
        if active:
            return {'text': 'Complete or recover the active ' + active['stage'] + ' claim',
                    'stage': active['stage'], 'kind': 'active-claim', **stamp}
        try:
            result = self.next_stage(state)
        except Exception:  # an evaluation that cannot run is recorded as absent, never guessed
            return None
        # The command usually asks for the same answer right after the save; hand it over once.
        self._saved_next = (state, state['generation'], copy.deepcopy(result))
        # R6: `status` agrees with `next` once the PR stage is recorded, and stops saying so when a stage reopens.
        if result.get('status') == 'pr_open' and state.get('status') != 'paused':
            state['status'] = 'pr_open'
            state.pop('pause', None)
        elif state.get('status') == 'pr_open':
            state['status'] = 'in-progress'
        if result.get('stage'):
            text = 'Run ' + result['stage'] + (' (' + result['command'] + ')' if result.get('command') else '')
            if result.get('reason') in ('inputs-or-evidence-changed', 'policy-changed'):
                text = 'Re-run ' + result['stage'] + ': ' + result['reason'].replace('-', ' ')
        elif result.get('status') == 'ready_to_finalize':
            text = 'Finalize the feature (' + result.get('command', 'speckit.workflow.finalize') + ')'
        else:
            text = 'No stage remains: ' + str(result.get('status'))
        return {'text': text, 'stage': result.get('stage'), 'kind': 'next-stage', **stamp}

    def next(self, state, finalize=False):
        result = self.next_stage(state, finalize)
        if finalize and result.get('stage') and BASE_STAGES.index(result['stage']) < BASE_STAGES.index('ready'):
            # AHMED-07: finalize is Ready plus PR, never "run everything that remains".
            remaining = [stage for stage in stages(self.policy, state_tier(state), state.get('skipped'))
                         if BASE_STAGES.index(result['stage']) <= BASE_STAGES.index(stage) < BASE_STAGES.index('ready')]
            result = {'stage': None, 'status': 'not_ready_to_finalize', 'remaining': remaining,
                      'reason': result.get('reason'), 'command': 'speckit.workflow.continue'}
        drift = consulted_drift(self.root, self.relative, state['receipts'], self.tier_of(state))
        if drift:
            # Advisory only: a consulted input never stales its receipt.
            result['advisory_drift'] = drift
        if state.get('profile'):
            result['profile'] = state['profile']
        if state.get('skipped'):
            result['skipped'] = state['skipped']
        if sync_retry(state, self.relative):
            result['project_sync'] = sync_retry(state, self.relative)
        return result

    def next_stage(self, state, finalize=False):
        saved = self.__dict__.pop('_saved_next', None)
        if saved and not finalize and saved[0] is state and saved[1] == state['generation']:
            return saved[2]
        policy_changed = state['policy_digest'] != checkpoint_policy_digest(state, self.policy)
        cutoff = policy_cutoff(state.get('policy'), self.policy) if policy_changed else len(BASE_STAGES)
        prefetch_attributes(self.root, [path for receipt in state['receipts'].values()
                                        for path in receipt.get('fingerprints') or {}])
        for stage in stages(self.policy, state_tier(state), state.get('skipped')):
            receipt = state['receipts'].get(stage)
            if receipt and BASE_STAGES.index(stage) >= cutoff:
                return {'stage':stage,'command':state['commands'][stage],'reason':'policy-changed'}
            if receipt:
                status = receipt_status(self.root, self.relative, stage, receipt, self.policy, self.tier_of(state))
                if status['current']:
                    continue
                return {'stage': stage, 'reason': 'inputs-or-evidence-changed',
                        'recovery': recovery_recipe(self.relative, stage, status, self.policy, receipt, self.root)}
            if stage == 'pr' and not finalize:
                return {'stage': None, 'status': 'ready_to_finalize', 'command': 'speckit.workflow.finalize'}
            return {'stage': stage, 'command': state['commands'][stage], 'reason': 'pending'}
        return {'stage': None, 'status': 'pr_open'}

    def claim(self, usage, finalize=False, verbose=False, owner_pid=None, confirm_invalidation=False):
        """`owner_pid` is the process that holds the claim; the CLI passes none, since it exits at once and the
        heartbeat then governs `recover` (AHMED-01). A claim that would remove receipts of later stages returns
        `confirm_invalidation` listing them unless `confirm_invalidation` is set (AHMED-12, DEC-15 stage 1)."""
        with operation(), locked(self.root / '.specify/workflow/runtime/dispatch.lock'), locked(self.lock):
            require(not (self.root / '.specify/workflow/runtime/upgrade.lock').exists(), 'WORKFLOW_UPGRADE_IN_PROGRESS')
            state = self.load()
            require(not state['active'], 'STAGE_ALREADY_ACTIVE: recover or finish the recorded claim')
            for path in (self.root / 'specs').glob('*/workflow/checkpoint.json'):
                held = read(path, {}).get('active')
                if path != self.path and held:
                    other = Run(self.root, path.parent.parent.relative_to(self.root).as_posix())
                    try:
                        other.release_ownership(automatic=True, dispatch_locked=True)
                    except (WorkflowError, ValueError, KeyError, OSError) as exc:
                        raise WorkflowError(
                            'OTHER_FEATURE_OWNERSHIP_RECOVERY_REQUIRED: ' + other.relative + ' has an active ' +
                            str(held.get('stage')) + ' claim (claimed_at ' + str(held.get('claimed_at')) +
                            ', session ' + str(held.get('session_id')) + '); ' + str(exc) + '; inspect it with "' +
                            WORKFLOW_SCRIPT + ' status --feature ' + other.relative + '", then finish it there or, '
                            'once its owner has stopped, run "' + other_feature_command(other.relative, held) +
                            '"') from None
            require(state['dependency_digest'] == package_digest(self.root),
                    'DEPENDENCY_CHANGED: the installed packages changed since this checkpoint was written; review the '
                    'upgrade notes, then run "python .specify/extensions/workflow/scripts/workflow.py migrate --feature ' +
                    self.relative + ' --reason <text>" before execution (an incomplete upgrade is fixed by "' +
                    upgrade_command(self.root)[0] + '")')
            # Delegation health is checked below, after every rejection, because
            # the claim may install the skill it would otherwise report missing.
            health = cached_doctor(self.root, self.policy, state['dependency_digest'])
            require(health['ok'], '; '.join(health['errors']))
            agent_host, default_host = running_host(), active_host(self.root)
            require(agent_host in (None, default_host) or default_host not in RUNNING_HOST_ENV,  # unsupported: doctor's
                    'HOST_MISMATCH: this session runs under ' + str(agent_host) + ' but the project default host is ' +
                    str(default_host) + '; continue in ' + str(default_host) + ', or preview the switch with "' +
                    WORKFLOW_SCRIPT + ' host --use ' + str(agent_host) + ' --preview"')
            gate = context_gate(self.policy, usage)
            if gate['pause']:
                return self.checkpoint(state, 'context-budget', gate)
            nxt = self.next(state, finalize)
            if not nxt.get('stage'):
                return nxt
            stage = nxt['stage']
            # Before any side effect (Memory handoff, tasks.md annotation): the receipts this claim would remove.
            downstream = [name for name in BASE_STAGES[BASE_STAGES.index(stage) + 1:] if name in state['receipts']]
            if downstream and not confirm_invalidation:
                at = ' --feature ' + self.relative
                return {'status': 'confirm_invalidation', 'stage': stage, 'reason': nxt.get('reason'),
                        'invalidates': downstream,
                        'invalidation': self.invalidation_preview(state, stage, nxt),
                        'recovery': nxt.get('recovery') or (
                            [WORKFLOW_SCRIPT + ' migrate' + at + ' --preview'] if nxt.get('reason') == 'policy-changed' else []),
                        'explain': 'python .specify/extensions/workflow/scripts/gate_explain.py' + at,
                        'confirm': WORKFLOW_SCRIPT + ' claim' + at + ' --usage <usage.json> --confirm-invalidation',
                        'message': 'Claiming ' + stage + ' removes the receipts of ' + ', '.join(downstream) +
                                   '. If the change is cosmetic, amend it (gate_explain lists the amend commands); '
                                   'otherwise ask the user, then re-run claim with --confirm-invalidation. A claim '
                                   'recovered before any work ran gets these receipts back'}
            memory = self.memory_session(state, stage, usage['session_id'])
            if memory is not None:
                return memory
            if BASE_STAGES.index(stage) >= BASE_STAGES.index('execute'):
                preflight = lean_preflight(self.root, self.policy)
                require(not preflight or preflight['ok'], 'LEAN_PREFLIGHT_FAILED: ' + json.dumps(preflight))
            if stage == 'review':
                coding_review_checks(self.root, self.relative, self.policy, state)
            current_policy_digest = checkpoint_policy_digest(state, self.policy)
            prior_policy_digest = state['policy_digest']
            if state['policy_digest'] != current_policy_digest:
                if (state.get('policy') or {}).get('profiles') != self.policy.get('profiles'):
                    # The profile bands changed: the next Plan claim (which the cutoff forces) fixes it again.
                    state.pop('profile', None)
                    state.pop('skipped', None)
                state.setdefault('policy_changes', []).append({'from':state['policy_digest'],'to':current_policy_digest,'at':now()})
                state['policy_digest'] = current_policy_digest
                state['policy'] = copy.deepcopy(self.policy)
                state['commands'] = resolve_commands(self.root, self.policy, state_tier(state))
            if stage == 'plan' and not state.get('profile') and (self.policy.get('profiles') or {}).get('enabled'):
                self.fix_profile(state)
            lean = lean_policy.enabled(self.policy, state_tier(state))
            coordinator_owned = lean_policy.coordinator_owned(self.policy, stage, state['commands'], state_tier(state))
            if self.policy['delegation']['enabled'] and not coordinator_owned:
                # Side effects only once a stage will be claimed: a rejected claim
                # leaves tasks.md and every skill location untouched.
                from delegation import annotate_tasks, cached_health, health_error
                delegation_health = cached_health(self.root, active_host(self.root),
                                                  self.policy['delegation']['install_scope'])
                require(delegation_health['ok'], health_error(delegation_health))
                require(any(delegation_health['harnesses'].values()),
                        'DELEGATE_AGENT_CLI_UNAVAILABLE: no supported Codex or Claude CLI')
                annotate_tasks(self.root, self.relative, self.policy['delegation'], lean=lean)
                notices = delegation_health.get('notices') or []
            else:
                notices = []
            resuming = state.get('status') == 'paused'
            removed = [name for name in BASE_STAGES[BASE_STAGES.index(stage):] if name in state['receipts']]
            retained = {name: copy.deepcopy(state['receipts'][name]) for name in removed}
            token = uuid.uuid4().hex
            claim_id = lifecycle.claim_id_for(token)
            for downstream in removed:
                # Captured before deletion: the receipts this claim removes are recorded as invalidated.
                # The removed receipt belongs to no claim or episode; the cause is a separate field.
                lifecycle.queue(state, downstream, 'invalidated', caused_by_claim_id=claim_id,
                                reason='removed when ' + stage + ' was claimed (completed '
                                       + str(state['receipts'][downstream].get('completed_at')) + ')')
                state['receipts'].pop(downstream, None)
            claimed_at = now()
            state['active'] = {'stage': stage, 'token': token, 'claim_id': claim_id, 'claimed_at': claimed_at,
                               'session_id': usage['session_id'], 'context': gate, 'pid': owner_pid,
                               'host': socket.gethostname(), 'heartbeat_at': claimed_at,
                               'agent_host': agent_host or 'unknown'}
            lifecycle.queue(state, stage, 'resume' if resuming else 'claim', claim_id=claim_id,
                            episode_id=lifecycle.episode_for_claim(claim_id),
                            reason='resumed after a pause' if resuming else None)
            source = read(self.feature / 'scope-source.json', {})
            existing = (self.feature / 'spec.md').is_file() and f"{source.get('repo')}#{source.get('issue')}" == state['issue']
            state['active']['mode'] = 'revalidate' if existing and stage in ('scope', 'specify', 'clarify', 'plan', 'tasks') else 'initial'
            scope_mode = state['active']['mode']
            if stage == 'specify' and self.rendered_spec():
                # Scope rendered spec.md from the approved analysis: Specify only binds, no model pass.
                state['active']['mode'] = 'bind-only'
            if coordinator_owned:
                state['active']['execution_owner'] = 'coordinator'
            if self.policy['delegation']['enabled'] and not coordinator_owned:
                from delegation import DelegationError, selected_route, stage_work_type
                work_type = stage_work_type(state['commands'], stage,
                                            self.policy['delegation'].get('fixed_collection_commands'))
                try:
                    candidates = selected_route(self.policy['delegation'], work_type, active_host(self.root))
                except DelegationError as exc:
                    if not str(exc).startswith('DELEGATION_REVIEW_ROUTE_UNSAFE'):
                        raise
                    # SEC-01 interim: a review-kind stage runs natively in the selected host instead of
                    # through the external driver; no route is recorded, so completion needs no
                    # dispatcher attempt, and the refusal stays visible on the claim.
                    state['active']['delegation_refused'] = {'task_type': work_type,
                                                             'rule': 'refused:DELEGATION_REVIEW_ROUTE_UNSAFE',
                                                             'reason': str(exc)}
                else:
                    state['active']['delegation'] = {
                        'identity': self.relative + '/stage:' + stage,
                        'task_type': work_type,
                        'candidates': candidates,
                        # The first candidate's kind decides: native means this session or a native subagent
                        # does the stage and records it with delegate_dispatch.py record-native.
                        'route_kind': candidates[0]['route_kind'],
                    }
                    if candidates[0]['route_kind'] == 'native':
                        from delegate_dispatch import git_porcelain
                        state['active']['delegation']['git_status_at_claim'] = git_porcelain(self.root)
            state['active']['baseline'] = fingerprint_files(self.root, [p for r in state['receipts'].values() for p in r['fingerprints']],
                                                            feature=self.relative)
            state['status'] = 'in-progress'
            state.pop('pause', None)  # R6: a resumed claim ends the pause; the lifecycle log keeps it
            write(self.root / '.specify/feature.json', {'feature_directory': self.relative})
            text, protocol, reporting = reference_text(self.root, stage), None, None
            if stage == 'execute':
                import progress_bridge
                decided = progress_bridge.mode(self.root, host=progress_bridge.detect_host() or active_host(self.root))
                reporting = {'mode': decided['mode'], 'reason': decided.get('reason') or decided.get('source')}
                parts = execute_protocol(self.policy, state_tier(state), reporting['mode'])
                full = reference_text(self.root, stage, parts)
                protocol = {'files': parts, 'digest': digest([parts, full]),
                            'summary': protocol_summary(self.policy, state_tier(state))}
                # The full protocol is printed once per mode and content; an unchanged re-claim names the files.
                protocol['printed'] = verbose or (state.get('execute_protocol') or {}).get('digest') != protocol['digest']
                if protocol['printed']:
                    text = full
                    state['execute_protocol'] = {'files': parts, 'digest': protocol['digest'], 'printed_at': now()}
                else:
                    protocol['note'] = ('unchanged since the last Execute claim; follow the summary, and reread the files '
                                        'whenever you cannot recall the full protocol')
            if retained:
                # #112: runtime-held proof that `recover` reads to give an unused claim's removed receipts back.
                state['active']['retained'] = {'receipts': retained, 'policy_digest': prior_policy_digest,
                                               'digest': self.unused_claim_digest(state, retained)}
            self.save(state)
            claimed = {**state['active'], 'command': state['commands'][stage], 'feature': self.relative, 'issue': state['issue'],
                       'reference': stage_reference(stage), 'reference_text': text,
                       'side_effects': side_effects(self.policy, self.relative, stage, self.root),
                       'project_sync': project_sync(self.policy, stage, self.relative),
                       'clarification_transport': state.get('clarification_transport', 'github-comments')}
            if claimed.pop('retained', None):
                claimed['invalidated'] = removed  # kept in the checkpoint until the claim completes or is recovered
            claimed['receipt_template'] = self.receipt_template(state, stage)
            claimed['lean_execution'] = lean_policy.describe(self.policy, state_tier(state))
            if reporting:
                claimed['reporting'], claimed['execute_protocol'] = reporting, protocol
            if stage == 'plan' and state_tier(state) in ('lite', 'standard'):
                claimed['merged'] = ['tasks']
                claimed['profile'] = state['profile']
            if lean:
                claimed['environment'] = {'SANDUQ_WORKFLOW_CLAIM_TOKEN': state['active']['token'],
                                          'SANDUQ_WORKFLOW_SESSION_ID': usage['session_id']}
            if lean and stage in ('scope', 'specify'):
                mode = scope_mode
                params = ({'feature': self.relative, 'token': state['active']['token'],
                           'session': usage['session_id'], 'analysis': lean_policy.settings(self.policy).get(
                               'scope_analysis', '<analysis.json>')} if mode == 'initial' else {})
                claimed['scope_command'] = execution_tools.scope_command(
                    mode, 'gate' if stage == 'scope' else 'bind', state['issue'].split('#')[1], **params)
                claimed['scope_analysis_required'] = mode == 'initial'
            card = self.lite_card(state)
            if card:
                claimed['instructions'] = card
                claimed['cli'] = claim_cli(self.relative, state['active']['token'])
                if stage == 'clarify':
                    round_ = self.clarification_round(state, state['active']['token'], usage['session_id'])
                    if round_:
                        claimed['clarification_round'] = round_
            if notices:
                # Reported to the caller only; the checkpoint keeps the claim itself.
                claimed['notices'] = notices
            return claimed

    def release_ownership(self, token=None, reason=None, actor=None, automatic=False, report=None,
                          dispatch_locked=False, force_live_owner=None):
        """Release bookkeeping only; ordinary execution stays bound to the original branch."""
        from contextlib import nullcontext
        from delegate_dispatch import ledger_lock
        require_not_delegated_context('recover')
        require(automatic or isinstance(reason, str) and reason.strip(), 'RECOVER_REASON_REQUIRED')
        with operation(), (nullcontext() if dispatch_locked else
                           locked(self.root / '.specify/workflow/runtime/dispatch.lock')), locked(self.lock), \
                ledger_lock(self.root, self.relative):
            require(not (self.root / '.specify/workflow/runtime/upgrade.lock').exists(), 'WORKFLOW_UPGRADE_IN_PROGRESS')
            state = self.load(allow_branch_change=True)
            active = copy.deepcopy(state.get('active'))
            if not active:
                if not automatic:
                    require(any(r.get('claim', {}).get('token') == token for r in state.get('recoveries', [])),
                            'CLAIM_TOKEN_MISMATCH')
                prompt_path = self.path.parent / 'resume-prompt.md'
                return {'feature': self.relative, 'released': False, 'status': state.get('status'),
                        'checkpoint': str(self.path),
                        'prompt': prompt_path.read_text(encoding='utf-8-sig') if prompt_path.is_file() else None}
            require(automatic or active['token'] == token, 'CLAIM_TOKEN_MISMATCH')
            # AHMED-01: a live pid, or a recent heartbeat the pid does not disprove, means the owner may still work.
            liveness = None if automatic else claim_owner(active)
            if liveness and (liveness['owner'] == 'alive' or liveness['owner'] != 'dead' and liveness['heartbeat_recent']):
                require(isinstance(force_live_owner, str) and force_live_owner.strip(),
                        'CLAIM_OWNER_ALIVE: the ' + active['stage'] + ' claim on ' + self.relative + ' may still be '
                        'owned (owner ' + liveness['owner'] + ', pid ' + str(liveness['pid']) + ' on ' +
                        str(liveness['host']) + ', last activity ' + str(liveness['last_activity_minutes']) +
                        ' min ago, session ' + str(active.get('session_id')) + ', claimed_at ' +
                        str(active.get('claimed_at')) + '); inspect it with "' + WORKFLOW_SCRIPT + ' status --feature ' +
                        self.relative + '" and let that session finish or pause. Only once you have confirmed it '
                        'stopped, rerun recover with --force-live-owner "<how you know the owner stopped>"; '
                        'otherwise wait until its last activity is ' + str(CLAIM_HEARTBEAT_SECONDS // 60) +
                        ' minutes old')
            else:
                force_live_owner = None
            evidence = wf_ownership.writer_evidence(SimpleNamespace(**globals()), self, state, automatic)
            if automatic:
                evidence['delivery'] = wf_ownership.merged_delivery(SimpleNamespace(**globals()), self, state, report)
            # The ledger lock fences dispatcher reservations. Compare again after external reads.
            latest = self.load(allow_branch_change=True)
            require(latest.get('active') == active and latest.get('generation') == state.get('generation'),
                    'OWNERSHIP_CHANGED: retry with the current claim; nothing was released')
            claim_id = active.get('claim_id') or lifecycle.claim_id_for(active['token'])
            at = now()
            reason = reason or 'Verified merged delivery; terminal delegated ownership released'
            retained = self.restore_unused_claim(state, active, evidence)
            state.setdefault('recoveries', []).append({'claim': {**active, 'claim_id': claim_id},
                'reason': reason, 'actor': actor or default_actor(self.root), 'at': at,
                'branch': state['branch'], 'terminal_evidence': evidence,
                'source': 'postmerge' if automatic else 'recover'})
            if retained:
                state['recoveries'][-1]['retained'] = retained
            if force_live_owner:
                state['recoveries'][-1]['forced_live_owner'] = {'reason': force_live_owner, **liveness}
            restored = (retained or {}).get('restored')
            lifecycle.queue(state, active['stage'], 'recovered', claim_id=claim_id, at=at,
                            episode_id=lifecycle.episode_for_claim(claim_id),
                            reason=('restored unused-claim receipts ' + ', '.join(restored) + '; ' if restored else '') + reason,
                            delegation_run_ids=lifecycle.delegation_runs_for(self.feature, active['token'], claim_id))
            state['active'] = None
            paused = self.checkpoint(state, reason, preserve_head=True)
            return {**paused, 'feature': self.relative, 'released': True, 'claim_id': claim_id,
                    'terminal_evidence': evidence, **({'retained': retained} if retained else {})}

    def unused_claim_digest(self, state, retained):
        """One digest of the bytes of every source file and every path a held or removed receipt fingerprints."""
        paths = sorted({path for receipt in [*retained.values(), *state['receipts'].values()]
                        for path in receipt.get('fingerprints') or {}})
        return digest([source_fingerprints(self.root), fingerprint_files(self.root, paths, feature=self.relative)])

    def restore_unused_claim(self, state, active, evidence):
        """#112: give back the receipts a claim removed when the claim did no work; otherwise keep them as history.

        "No work" is read only from state the runtime wrote, never from a worker's report: no delegated or native run
        bound to the claim in the trusted ledger, the policy the claim saw, and the same bytes as when the claim was
        made (a rejected completion that changed no file leaves nothing to undo). A restored receipt keeps its own fingerprints and is evaluated again, so
        one that was stale before the claim is stale again, never current."""
        held = active.get('retained')
        if not held:
            return None
        names = sorted(held['receipts'], key=BASE_STAGES.index)
        blockers = []
        if evidence.get('writer') != 'owner-confirmed':
            blockers.append('a delegated or native run was recorded for the claim')
        if held['policy_digest'] != checkpoint_policy_digest(state, self.policy):
            blockers.append('the policy changed')
        elif held['digest'] != self.unused_claim_digest(state, held['receipts']):
            blockers.append('source or a recorded dependency changed after the claim')
        if blockers:
            return {'restored': [], 'kept_as_history': names, 'because': blockers}
        for name in names:
            state['receipts'].setdefault(name, held['receipts'][name])
        return {'restored': names}

    def invalidation_preview(self, state, stage, nxt):
        """Each receipt a claim of `stage` would remove and why, computed before anything is written."""
        preview = []
        for name in BASE_STAGES[BASE_STAGES.index(stage):]:
            receipt = state['receipts'].get(name)
            if receipt is None:
                continue
            item = {'stage': name, 'completed_at': receipt.get('completed_at')}
            if nxt.get('reason') == 'policy-changed':
                item['why'] = 'policy-changed: the claimed stage and every later receipt follow the policy cutoff'
            else:
                status = receipt_status(self.root, self.relative, name, receipt, self.policy, self.tier_of(state))
                item['current'] = status['current']
                item['why'] = ('stale: ' + str(status.get('reason')) if not status['current'] else
                               'current; removed only because it follows ' + stage)
                item.update({key: status[key] for key in ('paths', 'rule', 'lanes', 'detail') if key in status})
            preview.append(item)
        return preview

    def heartbeat(self, token=None):
        """Refresh the active claim's heartbeat (AHMED-01) for an owner still at work, such as `delegate_dispatch
        collect`. Returns False when there is no active claim, or it holds another token."""
        with locked(self.lock):
            state = self.load(allow_branch_change=True)
            active = state.get('active')
            if not active or token is not None and active.get('token') != token:
                return False
            active['heartbeat_at'] = now()
            write(self.path, state)
            return True

    def memory_session(self, state, stage, session_id):
        """W14: the session handoff Memory's before_specify hook ran, now run by the claim under the dispatch lock it
        holds, at every claim: the usage `session_id` comes from the model, not the host, so it never skips the
        handoff (one `archive.py pending`, about 0.4 s). A blocked result, or Memory work to dispatch first, is
        returned instead of a stage; otherwise the run is recorded (saved with the claim) and None goes on."""
        result = memory_handoff.handoff(SimpleNamespace(**globals()), self.root, 'session', lock=False)
        if result['status'] in ('blocked', 'dispatch'):
            return {'stage': None, 'status': 'memory_' + result['status'], 'ok': result['status'] != 'blocked',
                    'memory_handoff': result,
                    'next': 'run memory_handoff.actions in order, then claim again'}
        state['memory_session'] = {'session_id': session_id, 'status': result['status'], 'at': now()}
        return None

    def rendered_spec(self):
        """The analysis hash of a spec.md Scope rendered (`<!-- sanduq-scope:rendered <sha256> -->`), else None."""
        path = self.feature / 'spec.md'
        if not path.is_file():
            return None
        with path.open('r', encoding='utf-8-sig', errors='replace') as handle:
            match = RENDER_MARKER.fullmatch(handle.readline().strip())
        return match[1] if match else None

    def lite_card(self, state):
        """LITE_CARD when the feature runs the lite tier, or (before Plan fixes it) the Scope receipt's score, else the
        analysis's proposed root score, falls in the lite band; None otherwise (the dispatcher references apply)."""
        name = state_tier(state)
        if name is None and (self.policy.get('profiles') or {}).get('enabled'):
            score = ((state.get('receipts') or {}).get('scope') or {}).get('effort_score')
            if score is None:
                try:
                    score = ((read(self.feature / 'scope-analysis.json', {}) or {}).get('tree') or {}).get('score')
                except (ValueError, AttributeError):
                    score = None
            name = tier(self.policy, score) if score in EFFORT_SCORES else None
        return LITE_CARD if name == 'lite' else None

    def clarification_round(self, state, token, session_id):
        """A zero-question Clarify round's exact steps, or None: only for a spec Scope rendered from the approved
        analysis that holds no `[NEEDS CLARIFICATION` marker, on the GitHub transport. The coverage scan stays the
        agent's; the steps replace loading the clarification skill."""
        spec = self.feature / 'spec.md'
        if state.get('clarification_transport', 'github-comments') == 'local' or not self.rendered_spec() \
                or '[NEEDS CLARIFICATION' in spec.read_text(encoding='utf-8-sig'):
            return None
        n, f = state['issue'].split('#')[1], self.relative
        script = 'python .specify/extensions/scope/scripts/clarification.py'
        snapshot = '.specify/scope/clarification-' + n + '-snapshot.json'
        review = f + '/clarify-review.json'
        return {'expected_questions': 0,
                'why': 'spec.md was rendered from the approved Scope analysis and has no [NEEDS CLARIFICATION] marker',
                'steps': [
                    'export SANDUQ_WORKFLOW_CLAIM_TOKEN=' + token + ' SANDUQ_WORKFLOW_SESSION_ID=' + str(session_id),
                    script + ' inspect ' + n + ' --output ' + snapshot + ' (prints snapshot_digest, round, '
                    'prior_questions, suggested_answers, unmatched_comments; above 0 for any of them: load the '
                    'clarification skill instead, since the issue discussion must be read)',
                    'Read ' + f + '/spec.md and mark each coverage category Clear, Partial or Missing: ' +
                    ', '.join(CLARIFY_CATEGORIES) + '. A material question: load the clarification skill instead.',
                    'Write ' + review + ' as {"version": 1, "issue": ' + n + ', "snapshot_digest": "<from inspect>", '
                    '"engine": "clarify", "coverage": {"<category>": "Clear: <why>", ...}, "summary": "<one line>", '
                    '"answers": [], "questions": [], "spec_edits": []}',
                    script + ' publish ' + n + ' --analysis ' + review + ' (dry run), then the same with --apply: it '
                    'records the round and moves the issue to Ready',
                    'Receipt: unresolved 0, answers_applied true, inputs and evidence ' + review + ' and ' + snapshot]}

    def verified_effort_score(self, state, gh=None):
        """OMAR-05: the effort score Scope's gate verified against the issue's Scope receipt and `effort:<n>` label,
        as `(score, source)`. Scope's bind caches the gate result in scope-source.json; without it, one GitHub read
        of the issue's labels."""
        cached = read(self.feature / 'scope-source.json', {}).get('score')
        if cached is not None:
            return cached, 'scope-source.json (verified by Scope at bind)'
        repo, number = state['issue'].split('#')
        if gh is None:
            from decisions import GitHub
            gh = GitHub()
        labels = [label.get('name') or '' for label in gh.api('repos/' + repo + '/issues/' + number).get('labels', [])]
        scores = [int(label[len('effort:'):]) for label in labels if re.fullmatch(r'effort:\d+', label)]
        require(len(scores) == 1, 'EFFORT_SCORE_UNVERIFIED: ' + state['issue'] + ' carries ' + str(len(scores)) +
                ' effort:<n> labels and scope-source.json records no Scope-verified score; rerun Scope for the issue '
                '(/speckit-scope-run ' + number + ') so its receipt and label agree, then claim again')
        return scores[0], 'effort:' + str(scores[0]) + ' label on ' + state['issue']

    def fix_profile(self, state, gh=None):
        """Freeze the tier at the first Plan claim from the Scope receipt's effort score, and record what it skips.
        The score must equal the one Scope verified (OMAR-05)."""
        score = (state['receipts'].get('scope') or {}).get('effort_score')
        verified, source = self.verified_effort_score(state, gh)
        require(score == verified, 'EFFORT_SCORE_MISMATCH: the Scope receipt records effort_score ' + str(score) +
                ' but ' + source + ' says ' + str(verified) + '; the tier comes from the verified score, so rerun '
                'Scope: "' + WORKFLOW_SCRIPT + ' refresh --feature ' + self.relative + ' --from-stage scope --reason '
                '\"effort score mismatch\"", then complete Scope with effort_score ' + str(verified))
        fixed = tier(self.policy, score)
        state['profile'] = {'tier': fixed, 'score': score, 'fixed_at': now()}
        skipped = skipped_stages(self.policy, fixed)
        self.record_skipped(state, skipped)
        state['skipped'] = skipped
        state['commands'] = resolve_commands(self.root, self.policy, fixed)

    def complete(self, token, receipt):
        with operation(), locked(self.lock):
            state = self.load()
            active = state['active']
            require(active and active['token'] == token, 'CLAIM_TOKEN_MISMATCH')
            self._validated_candidate = None  # set once the exact-claim delegation check has passed
            try:
                return self._accept_completion(state, active, token, receipt)
            except (WorkflowError, ValueError) as exc:
                try:
                    self._record_rejection(token, exc)
                except Exception:  # the log must never hide the rejection the caller has to see
                    pass
                raise

    def _record_rejection(self, token, exc):
        """Record a rejected completion without clearing the claim or accepting the candidate.

        The checkpoint is re-read, so nothing a half-finished validation changed in memory is written.
        """
        try:
            fresh = self.load()
        except WorkflowError:
            return  # the original rejection is what the caller must see
        held = fresh.get('active')
        if not held or held.get('token') != token:
            return
        claim_id = held.get('claim_id') or lifecycle.claim_id_for(token)
        lifecycle.queue(fresh, held['stage'], 'rejected-completion', claim_id=claim_id,
                        generation=fresh.get('generation', 0), episode_id=lifecycle.episode_for_claim(claim_id),
                        candidate_run_id=getattr(self, '_validated_candidate', None),
                        delegation_run_ids=lifecycle.delegation_runs_for(self.feature, token, claim_id),
                        reason=str(exc))
        write(self.path, fresh)
        if lifecycle.flush(fresh, self.feature):
            write(self.path, fresh)

    def _check_receipt(self, stage, receipt, tier):
        """The shape every recorded receipt meets (complete and revalidate-upstream). Returns the canonical copy."""
        reject_placeholders(receipt)
        require(receipt.get('stage') == stage and receipt.get('outcome') == 'passed', 'STAGE_NOT_PASSED')
        require(receipt.get('summary') and receipt.get('evidence'), 'EVIDENCE_REQUIRED')
        require(isinstance(receipt.get('inputs'), list) and receipt['inputs'], 'INPUT_MANIFEST_REQUIRED')
        require(not any(field in receipt for field in RUNTIME_RECEIPT_FIELDS),
                'RECEIPT_FIELD_RESERVED: ' + ', '.join(f for f in RUNTIME_RECEIPT_FIELDS if f in receipt))
        receipt = canonical_receipt(self.root, receipt)
        validate_input_roles(self.root, self.relative, stage, receipt, self.policy, tier)
        if BASE_STAGES.index(stage) < BASE_STAGES.index('execute'):
            # F10: a file tasks.md hands to Execute is context before Execute, whichever host wrote the receipt;
            # as an undeclared dependency it would refuse Execute's completion.
            tasks = self.feature / 'tasks.md'
            text = tasks.read_text(encoding='utf-8-sig') if tasks.is_file() else ''
            roles = receipt.get('input_roles') or {}
            protected = set(receipt['evidence']) | set(required_inputs(self.root, self.relative, stage, tier))
            targets = [path for path in receipt['inputs'] if path not in roles and path not in protected
                       and not role_exempt(self.relative, path) and portable_label(path) in text]
            if targets:
                receipt['input_roles'] = {**roles, **{path: {'role': 'consulted', 'because': 'tasks.md assigns '
                                                             'this file to Execute'} for path in targets}}
        for path in receipt['evidence']:
            require(inside(self.root, path).is_file(), 'EVIDENCE_MISSING: ' + path)
        validate_evidence_snapshots(self.root, receipt)
        return receipt

    def folded_ready_checks(self, state):
        """A lite feature folds Ready into Verify: Verify's completion and revalidation run the Ready checks (tasks,
        task links, selected documentation) and record what ran. None when the feature runs its own Ready."""
        if 'ready' not in (state.get('skipped') or {}):
            return None
        try:
            return ready_checks(self.root, self.relative, self.policy, state, state.get('target_branch'))
        except Exception as exc:  # the task parser raises the importing module's error class
            if type(exc).__name__ != 'WorkflowError':
                raise
            raise WorkflowError('READY_CHECKS_FAILED: ' + str(exc)) from exc

    def receipt_template(self, state, stage):
        """The receipt skeleton `claim` prints: the fields `_check_receipt` and `_check_stage_rules` require for this
        stage and tier. Inputs the runtime adds itself (`_stamp`: required artifacts, the decision ledger) are left
        out; `<...>` values are placeholders to replace, and every gating field is one (OMAR-01)."""
        # R2: evidence is required, so the template never shows an empty list that `complete` refuses.
        template = {'stage': stage, 'outcome': '<passed|failed|blocked>', 'summary': '', 'inputs': [],
                    'evidence': ['<existing file that proves the work>']}
        if stage == 'scope' and (self.policy.get('profiles') or {}).get('enabled'):
            template['effort_score'] = '<one of ' + ', '.join(map(str, EFFORT_SCORES)) + '>'
        if stage == 'clarify':
            template.update(unresolved='<count>', answers_applied='<true|false>')
            if state.get('clarification_transport') == 'local':
                template['inputs'] = [self.relative + '/clarifications.md']
        if stage == 'plan' and state_tier(state) in ('lite', 'standard'):
            template['inputs'] = [self.relative + '/tasks.md']
        if stage == 'plan' and state_tier(state) == 'lite':
            # Lite folds Analyze into Plan: the lint output is the evidence (stage-plan.md names the command).
            template['evidence'] = [self.relative + '/evidence/plan-lint.json']
        if stage == 'analyze' and state['commands'].get(stage) == LINT_COMMAND:
            template['lint'] = {'ok': True, 'findings': '<count lint.py reported>'}
        if stage == 'taskstoissues':
            template.update(parent_issue=state['issue'], native_links_verified='<true after verification>')
            if task_issue_mode(self.policy) == 'phase-lazy':
                template['lazy'] = True
        if stage in SOURCE_STAGES:
            template['blocking_findings'] = '<count>'
        if stage == 'pr':
            template.update(pr_url='https://github.com/' + state['issue'].split('#')[0] + '/pull/<number>',
                            images_verified='<true|false>')
        return template

    def _check_stage_rules(self, state, stage, receipt, token=None, session_id=None):
        """Binding, the decisions ledger and each stage's own fields (complete and revalidate-upstream)."""
        if stage == 'scope':
            score = receipt.get('effort_score')
            if (self.policy.get('profiles') or {}).get('enabled') or score is not None:
                require(type(score) is int and score in EFFORT_SCORES, 'EFFORT_SCORE_REQUIRED: the Scope receipt '
                        'records effort_score, one of ' + ', '.join(map(str, EFFORT_SCORES)))
        if stage == 'clarify':
            require(receipt.get('unresolved') == 0 and receipt.get('answers_applied') is True, 'CLARIFICATION_UNRESOLVED')
            if state.get('clarification_transport') == 'local':
                # REQ-21: the file is the only record of the questions and the user's replies.
                from decisions import LOCAL_FILE, local_sections
                label = self.relative + '/' + LOCAL_FILE
                require(label in receipt['inputs'] and (self.root / label).is_file(),
                        'CLARIFICATION_FILE_INPUT_REQUIRED: with the local transport the Clarify receipt lists '
                        + label + ' (the questions asked in the conversation and the user\'s replies) as an input')
                sections = local_sections((self.root / label).read_text(encoding='utf-8-sig'))
                open_ids = [qid for qid, section in sections.items()
                            if qid.startswith('C') and not (section['ticked'] or section['answers'])]
                require(not open_ids, 'CLARIFICATION_UNRESOLVED: ' + ', '.join(open_ids) + ' in ' + label
                        + ' has no recorded reply (a line `<ID>: <letter>` or a ticked box); unparsed lines: '
                        + json.dumps({qid: sections[qid]['unparsed'] for qid in open_ids}))
        if BASE_STAGES.index(stage) >= BASE_STAGES.index('specify'):
            source = read(self.feature / 'scope-source.json', {})
            require(f"{source.get('repo')}#{source.get('issue')}" == state['issue'], 'FEATURE_BINDING_MISMATCH')
        ledger_path = self.feature / 'workflow/decisions.json'
        if ledger_path.is_file():
            from decisions import reconcile, verify_ledger
            verify_ledger(self.root, self.relative, reconcile(
                self.root, self.relative, claim_token=token, session_id=session_id))
        if stage == 'plan' and state_tier(state) in ('lite', 'standard'):
            require(self.relative + '/tasks.md' in receipt['inputs'], 'MERGED_TASKS_REQUIRED: on the ' +
                    state_tier(state) + ' tier Plan also writes tasks.md; list ' + self.relative +
                    '/tasks.md in the receipt inputs')
        if stage == 'plan' and 'analyze' in (state.get('skipped') or {}):
            # Lite folds Analyze into Plan: the deterministic lint runs here, and a gap only a model Analyze could
            # judge is fixed in the artifacts, since there is no Analyze stage to escalate to.
            import lint  # imports this module; loaded only on this path
            result = lint.run(self.root, self.relative, self.policy, self.tier_of(state))
            require(result['ok'] and not result['needs_model_analyze'],
                    'PLAN_LINT_FAILED: on this tier Plan completion runs workflow:lint (there is no Analyze stage); '
                    'fix the owning artifact, then complete again: ' + '; '.join(
                        f['severity'] + ' ' + f['code'] + ' ' + f['path'] + ': ' + f['message']
                        for f in result['findings'] if f['severity'] != 'info')[:2000])
            receipt['lint'] = {'ok': True, 'findings': len(result['findings'])}
        if stage == 'analyze' and state['commands'].get(stage) == LINT_COMMAND \
                and receipt.get('command') != COMMANDS['analyze']:
            lint = receipt.get('lint')
            require(receipt.get('command') in (None, LINT_COMMAND) and isinstance(lint, dict) and lint.get('ok') is True
                    and type(lint.get('findings')) is int and lint['findings'] >= 0,
                    'LINT_RECEIPT_REQUIRED: Analyze runs as workflow:lint on this tier; record it with "lint.py '
                    '--feature ' + self.relative + ' --record --token <token>", or complete a model Analyze '
                    '(command ' + COMMANDS['analyze'] + ') when lint reports needs_model_analyze')
        if stage == 'taskstoissues':
            require(receipt.get('parent_issue') == state['issue'] and receipt.get('native_links_verified') is True, 'TASK_PARENT_NOT_VERIFIED')
            if task_issue_mode(self.policy) == 'phase-lazy':
                require(receipt.get('lazy') is True, 'TASK_ISSUES_LAZY_REQUIRED: issue_sync.taskstoissues is phase-lazy; '
                        'the receipt records lazy: true after mapping the first phase')
                tasks_path = self.feature / 'tasks.md'
                first = first_phase_tasks(tasks_path.read_text(encoding='utf-8-sig')) if tasks_path.is_file() else []
                mapping = read(self.feature / 'workflow/task-issues.json', {}).get('tasks', {})
                unmapped = [task for task in first if not (mapping.get(task) or {}).get('linked')]
                require(not unmapped, 'TASK_MAPPING_FIRST_PHASE_INCOMPLETE: ' + ', '.join(unmapped) +
                        '; run task_issues.py --phase "<first phase heading>" before completing Tasks-to-Issues')

    def _stamp(self, state, stage, receipt, stored, tier):
        """The runtime-owned fields of a recorded receipt: command, digests and fingerprints."""
        model_analyze = (stage == 'analyze' and state['commands'].get(stage) == LINT_COMMAND
                         and receipt.get('command') == COMMANDS['analyze'])
        stored['command'] = COMMANDS['analyze'] if model_analyze else state['commands'][stage]
        stored['dependency_digest'] = state['dependency_digest']
        if stage == 'clarify' and state.get('clarification_transport') == 'local':
            # The agent transcribed the replies itself; no GitHub record vouches for them.
            stored['self_attested'] = {'answers': 'local', 'file': self.relative + '/clarifications.md'}
        decision_input = [self.relative + '/workflow/decisions.json'] if (self.feature / 'workflow/decisions.json').is_file() else []
        stored['fingerprints'] = fingerprint_files(self.root, receipt['inputs'] + receipt['evidence'] + required_inputs(
            self.root, self.relative, stage, tier) + decision_input, feature=self.relative)
        require(all(v is not None for v in stored['fingerprints'].values()), 'INPUT_MISSING')
        # Whitespace-normalised Markdown hashes: revalidate-upstream's drift decision only.
        text = text_fingerprints(self.root, stored['fingerprints'])
        if text:
            stored['text_fingerprints'] = text

    def _accept_completion(self, state, active, token, receipt):
        stage = active['stage']
        tier = self.tier_of(state)
        lean = lean_policy.enabled(self.policy, state_tier(state))
        if stage == 'review':
            coding_review_checks(self.root, self.relative, self.policy, state)
        receipt = self._check_receipt(stage, receipt, tier)
        delegation_ledger_trust = None
        stage_attempt = None
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
                    ' --reason <text> --nonce <dispatcher_nonce>" only after reviewing exactly what changed')
            stage_attempt = latest_attempt(self.root, self.relative, 'stage:' + stage)
            require(stage_attempt is not None and stage_attempt.get('status') == 'successful' and
                    stage_attempt.get('claim_token') == token,
                    'DELEGATION_STAGE_NOT_VERIFIED: the latest delegate_dispatch attempt for stage:' +
                    stage + ' is ' + (str(stage_attempt.get('status')) if stage_attempt else 'missing') +
                    ' or was not started under this claim; collect, accept or reassign it before '
                    'completing this stage, or, when a native subagent of the host did the stage, record '
                    '"delegate_dispatch.py attest-native --feature ' + self.relative + ' --id stage:' + stage +
                    ' --claim-token <token> --requested-model <m>" from the top-level session. A legacy attempt '
                    'recorded before claim_token existed has none and will never match; re-delegate the stage '
                    'once under this workflow release')
            self._validated_candidate = stage_attempt.get('run_id')
        if self.policy['delegation']['enabled'] and (active.get('delegation') or active.get('delegation_refused')):
            # A native review or QA attempt of this claim (a review-kind stage records one with no route) must
            # not come from the agent lineage that authored the work it checks.
            from delegation import latest_attempt, ledger_attempts, same_lineage_author
            native = stage_attempt or latest_attempt(self.root, self.relative, 'stage:' + stage)
            if (native or {}).get('kind') == 'native' and native.get('claim_token') == token:
                author = same_lineage_author(ledger_attempts(self.root, self.relative), native)
                require(author is None, 'SAME_LINEAGE_REVIEW: stage:' + stage + ' was checked by agent lineage ' +
                        ' > '.join(native.get('author_lineage') or ()) + ', which also authored ' + str(author) +
                        '; have another agent review it and record that with delegate_dispatch.py record-native')
        self._check_stage_rules(state, stage, receipt, token, active.get('session_id'))
        if stage in SOURCE_STAGES:
            require(receipt.get('blocking_findings') == 0, 'BLOCKING_FINDINGS_REMAIN')
        folded_ready = self.folded_ready_checks(state) if stage == 'verify' else None
        if stage == 'pr':
            require(receipt.get('images_verified') is True and receipt.get('pr_url', '').startswith('https://github.com/' + state['issue'].split('#')[0] + '/pull/'), 'PR_EVIDENCE_INCOMPLETE')
            if lean:
                binding = pr_lint_binding(self.root, self.relative, state, receipt)
                receipt['inputs'] = list(dict.fromkeys(receipt['inputs'] + [binding['scope']]))
                if receipt.get('input_roles') is not None:
                    for path in (binding['scope'], binding['body'], binding['lint']):
                        if path in receipt['inputs']:
                            receipt['input_roles'][path] = {'role': 'dependency'}
        if stage in ('tasks', 'plan', 'qa_analyze', 'manual_analyze') and self.policy['delegation']['enabled'] \
                and (stage != 'plan' or tier in ('lite', 'standard')):
            from delegation import annotate_tasks
            annotate_tasks(self.root, self.relative, self.policy['delegation'], lean=lean)
        # Known semantic transformations advance upstream artifact snapshots with an
        # explicit lineage record. They do not pretend the old artifact remained current.
        permitted = side_effects(self.policy, self.relative, stage, self.root)
        after = fingerprint_files(self.root, active['baseline'], feature=self.relative, like=active['baseline'])
        changed = [p for p, before in active['baseline'].items() if after[p] != before]
        # Only an earlier receipt's dependency can be undermined by this stage.
        # A path every earlier receipt only consulted keeps its recorded hash
        # (nothing is re-stamped) and `next` reports it as advisory drift.
        dependencies = set()
        for name, prior in state['receipts'].items():
            dependencies.update(dependency_fingerprints(prior, required_inputs(self.root, self.relative, name, tier)))
        consulted = [p for p in changed if p not in dependencies]
        changed = [p for p in changed if p in dependencies]
        unexpected = [p for p in changed if not matches_side_effect(p, permitted)]
        require(not unexpected, 'UPSTREAM_INPUT_CHANGED_DURING_STAGE: ' + ', '.join(unexpected))
        if stage == 'qa_document':
            require(all(after[p] is not None for p in changed), 'INPUT_MISSING')
        claim_id = active.get('claim_id') or lifecycle.claim_id_for(token)
        inventories = []  # (receipt, stage, inventory) side files written just before the save
        if consulted:
            state.setdefault('lineage', []).append({'stage': stage, 'advisory': True, 'consulted': {
                p: {'before': active['baseline'][p], 'after': after[p]} for p in consulted}, 'at': now()})
        if changed:
            lineage = {'stage': stage, 'changes': {p: {'before': active['baseline'][p], 'after': after[p]} for p in changed}, 'at': now()}
            state.setdefault('lineage', []).append(lineage)
            for name, prior in state['receipts'].items():
                for path in changed:
                    if path in prior['fingerprints']:
                        value = after[path]
                        if str(value).startswith(SYNC_BINDING_PREFIX) \
                                and not str(prior['fingerprints'][path]).startswith(SYNC_BINDING_PREFIX):
                            # A legacy raw hash stays byte-exact until migrate or sync-amend verifies the binding.
                            value = fingerprint_files(self.root, [path])[path]
                            lineage.setdefault('raw', {}).setdefault(name, {})[path] = {
                                'before': prior['fingerprints'][path], 'after': value}
                        prior['fingerprints'][path] = value
                # Verify/Review also inventory this root-relative context file.
                # Advance only the accepted QA-document transformation, retaining
                # its old/new hashes in the same runtime-owned lineage above.
                if stage == 'qa_document' and name in SOURCE_STAGES:
                    inventory = source_fingerprints_of(self.root, prior, self.relative)
                    hits = [path for path in changed if portable_label(path) in inventory]
                    for path in hits:
                        inventory[portable_label(path)] = after[path]
                    if hits and prior.get('source_inventory'):
                        inventories.append((prior, name, inventory, claim_id))
                    elif hits:
                        prior['source_fingerprints'] = inventory
        if stage in ('qa_document', 'manual_update'):
            # F9: this stage's declared outputs (its evidence and side effects) are not inputs of the earlier
            # Verify and Review; their source inventories take the new hashes instead of going stale.
            declared = {portable_label(path) for path in receipt.get('evidence', [])}
            current = source_fingerprints(self.root)
            outputs = {path: value for path, value in current.items()
                       if path in declared or matches_side_effect(path, permitted)}
            for name, prior in state['receipts'].items():
                if name not in SOURCE_STAGES or not outputs:
                    continue
                pending = next((entry[2] for entry in inventories if entry[0] is prior), None)
                inventory = pending if pending is not None else source_fingerprints_of(self.root, prior, self.relative)
                hits = sorted(path for path, value in outputs.items() if inventory.get(path) != value)
                if not hits:
                    continue
                inventory.update({path: outputs[path] for path in hits})
                state.setdefault('lineage', []).append({'stage': stage, 'outputs_not_inputs': {
                    name: hits}, 'at': now()})
                if pending is not None:
                    continue  # the side file queued above now carries these hashes too
                if prior.get('source_inventory'):
                    inventories.append((prior, name, inventory, claim_id))
                else:
                    prior['source_fingerprints'] = inventory
        stored = copy.deepcopy(receipt)
        if folded_ready is not None:
            stored['ready_checks'] = folded_ready
        if stage == 'pr' and lean:
            stored['pr_lint_binding'] = binding
        if stage == 'verify' and lean:
            selected_plan = lean_policy.settings(self.policy).get('verification_plan')
            if selected_plan:
                try:
                    stored['verification_snapshot'] = verification_plan.snapshot(self.root, selected_plan)
                except ValueError as exc:
                    raise WorkflowError(str(exc)) from exc
        if stored.get('input_roles') is None:
            stored.pop('input_roles', None)  # absent means all-dependency
        if delegation_ledger_trust is not None:
            # A warning record, never a block: 'unverified-local' means no
            # local dispatcher-write marker existed to check against (a
            # fresh checkout or CI runner), not that anything was wrong.
            stored['delegation_ledger_trust'] = delegation_ledger_trust
        if (stage_attempt or {}).get('kind') == 'native':
            # Self-asserted by the top-level session: labelled so it is never read as a dispatched run.
            from delegate_dispatch import native_attestation_fields
            stored['native_attestation'] = native_attestation_fields(stage_attempt)
        self._stamp(state, stage, receipt, stored, tier)
        stored['completed_at'] = now()
        stored['claim_id'] = claim_id  # links this receipt to its lifecycle events
        if active.get('agent_host'):
            stored['agent_host'] = active['agent_host']  # the host CLI that claimed it (T05); older claims have none
        if stage in SOURCE_STAGES:
            inventories.append((stored, stage, source_fingerprints(self.root), None))
            # The commit and its source key bind the inventory; with source
            # changes outside HEAD the key would not describe it, so none is
            # recorded and the identity rule applies to this receipt.
            head, key = current_source_key(self.root)
            if key:
                stored['head'], stored['source_key'] = head, key
        state['receipts'][stage] = stored
        state['active'] = None
        lifecycle.queue(state, stage, 'accepted', claim_id=claim_id, at=stored['completed_at'],
                        episode_id=lifecycle.episode_for_claim(claim_id),
                        candidate_run_id=(stage_attempt or {}).get('run_id'),
                        delegation_run_ids=lifecycle.delegation_runs_for(self.feature, token, claim_id))
        superseded = [self.store_inventory(owner, name, inventory, suffix)
                      for owner, name, inventory, suffix in inventories]
        self.save(state)
        self.drop_inventories(superseded)
        result = {**self.next(state), 'completed': stage}
        if stage == 'execute':
            result['memory_handoff'] = memory_handoff.handoff(
                SimpleNamespace(**globals()), self.root, 'execute', self.relative)
            # Product acceptance is already durable. Memory failure is a
            # separate recoverable operation, never an unpassed Execute.
            if result['memory_handoff']['ok'] is False:
                result['ok'] = False
        return result

    def checkpoint(self, state, reason, context=None, preserve_head=False):
        state['status'] = 'paused'
        state['pause'] = {'reason': reason, 'context': context, 'at': now()}
        held = state.get('active')
        if held:
            held['heartbeat_at'] = state['pause']['at']
        claim_id = (held.get('claim_id') or lifecycle.claim_id_for(held['token'])) if held else None
        lifecycle.queue(state, held['stage'] if held else None, 'paused', claim_id=claim_id,
                        episode_id=lifecycle.episode_for_claim(claim_id), reason=reason)
        self.save(state, preserve_head=preserve_head)
        pending = self.next(state)
        task_path = self.feature / 'tasks.md'
        pending_tasks = re.findall(r'(?m)^\s*- \[ \]\s+(T\d{3,})\b', task_path.read_text(encoding='utf-8-sig')) if task_path.is_file() else []
        active_summary = {k: state['active'].get(k) for k in ('stage', 'session_id', 'claimed_at')} if state['active'] else None
        block = '\n'.join([
            HANDOFF_BEGIN, '# Workflow handoff\n',
            '- Feature: ' + self.relative, '- Issue: ' + state['issue'], '- Branch: ' + state['branch'],
            '- Head: ' + state['head'], '- Reason: ' + reason, '- Next: ' + str(pending),
            '- Completed stages: ' + ', '.join(state['receipts']),
            '- Active claim: ' + str(active_summary),
            '- Pending task IDs: ' + ', '.join(pending_tasks[:100]) + (' (more in tasks.md)' if len(pending_tasks) > 100 else ''),
            '\nRead evidence paths and summaries with workflow.py status; do not infer skipped tests passed.',
            '\nInspect git status before continuing; do not discard uncommitted files.', HANDOFF_END])
        handoff = self.path.parent / 'handoff.md'
        (self.path.parent).mkdir(parents=True, exist_ok=True)
        handoff.write_text(handoff_text(handoff.read_text(encoding='utf-8-sig') if handoff.is_file() else '', block),
                           encoding='utf-8')
        prompt = (f'Run {WORKFLOW_SCRIPT} status --feature {self.relative} and continue with '
                  'speckit.workflow.continue; do not read checkpoint.json directly.\n')
        (self.path.parent / 'resume-prompt.md').write_text(prompt, encoding='utf-8')
        return {'status': 'paused', 'checkpoint': str(self.path), 'prompt': prompt}


def compact_completion(result):
    """What a dispatcher needs after `complete`: the stage it may run next and why. A failed Memory
    handoff is kept, since it is the reason `ok` is false."""
    compact = {'ok': result.get('ok', True), 'stage': result.get('completed'),
               'next': {key: result.get(key) for key in ('stage', 'command', 'reason')}}
    if result.get('status'):
        compact['next']['status'] = result['status']
    if result.get('ok') is False and result.get('memory_handoff'):
        compact['memory_handoff'] = result['memory_handoff']
    return compact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='action', required=True)
    memory = sub.add_parser('memory-handoff', help='Dispatch local Memory work without changing product stage receipts')
    memory.add_argument('--transition', choices=('execute', 'session', 'postmerge'), required=True)
    memory.add_argument('--feature', help='Exact feature; required for execute and postmerge')
    memory.add_argument('--check', action='append', default=None, help='Existing Memory policy check name (repeatable)')
    memory.add_argument('--report', type=Path, help='Verified post-merge binding JSON; see memory-lifecycle reference')
    init = sub.add_parser('init')
    init.add_argument('--qa', choices=['on', 'off'], required=True)
    init.add_argument('--manual', choices=['on', 'off'], required=True)
    init.add_argument('--delegate', choices=['on', 'off'],
                      help='Opt into model-aware delegation; omitted on existing projects preserves their selection')
    init.add_argument('--board', choices=['none', 'minimal', 'full'],
                      help='GitHub Project board sync: full (every phase, task sub-issues), minimal (Ready, In progress, '
                           'In review, Done; no task sub-issues) or none (no board); omitted keeps the current mode, '
                           'fresh policies default to full')
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
    ci_parser.add_argument('--verify-command', metavar='COMMAND',
                           help='Local runner speckit-workflow-verify-affected uses to run affected lanes '
                                '(JSON {lanes, results_path} on stdin), or "none" to remove')
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
    relocate_parser.add_argument('--allow-history-change', action='store_true',
                                 help='Confirm a checkpoint whose recorded root history is not the history of this repository '
                                      '(recreated or rewritten history sharing the remote) is the same project; '
                                      'logged in the relocation record')
    relocate_parser.add_argument('--actor', help='Defaults to the Git user name')
    for name in ('start', 'next', 'status', 'claim', 'complete', 'pause', 'recover', 'bind', 'migrate', 'refresh', 'amend',
                 'revalidate', 'revalidate-upstream', 'project-sync', 'sync-amend'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--feature', required=name != 'status')
        if name == 'start': cmd.add_argument('--issue', required=True)
        if name == 'status': cmd.add_argument('--issue', help='Issue number; resolved through the checkpoint binding')
        if name in ('next', 'claim'): cmd.add_argument('--finalize', action='store_true')
        if name == 'claim': cmd.add_argument('--usage', type=Path, required=True)
        if name == 'claim': cmd.add_argument('--confirm-invalidation', action='store_true',
                                             help='Remove the receipts of later stages a confirm_invalidation result listed')
        if name in ('claim', 'complete'):
            cmd.add_argument('--verbose', action='store_true',
                             help='Print the full result (claim: with the baseline fingerprints and the full Execute protocol; '
                                  'complete: with next details)')
        if name == 'status': cmd.add_argument('--runs', action='append', type=Path, default=[],
                                            help='Explicit normalized run root/worktree (repeatable)')
        if name == 'complete':
            cmd.add_argument('--token', required=True)
            cmd.add_argument('--receipt', type=Path, required=True)
        if name == 'revalidate-upstream':
            cmd.add_argument('--through', required=True, choices=BASE_STAGES[BASE_STAGES.index('specify'):
                                                                             BASE_STAGES.index('execute')],
                             help='Last upstream stage to re-record (specify to taskstoissues)')
            cmd.add_argument('--receipt', type=Path,
                             help='{stages: {<stage>: {summary, evidence[], inputs[]}}}; required unless --plan')
            cmd.add_argument('--plan', action='store_true', help='Print the changed inputs per stage without writing')
            cmd.add_argument('--actor', help='Defaults to the Git user name')
        if name in ('pause', 'recover', 'refresh', 'amend', 'sync-amend'): cmd.add_argument('--reason', required=True)
        if name == 'sync-amend': cmd.add_argument('--actor', help='Defaults to the Git user name')
        if name == 'project-sync': cmd.add_argument('--phase', required=True, choices=PROJECT_SYNC_STEPS)
        if name == 'migrate': cmd.add_argument('--reason', help='Required unless --preview')
        if name in ('recover', 'bind'): cmd.add_argument('--token', required=True)
        if name == 'recover':
            cmd.add_argument('--force-live-owner', metavar='REASON',
                             help='Recover a claim whose owner looks alive (CLAIM_OWNER_ALIVE); say how you know it stopped')
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
    with operation():
        return run_command(args)


def run_command(args):
    """One parsed CLI command, inside the operation scope `main` opens."""
    root = args.root.resolve()
    try:
        if args.action == 'memory-handoff':
            require(args.transition == 'session' or args.feature, 'EXPLICIT_FEATURE_REQUIRED')
            result = memory_handoff.handoff(SimpleNamespace(**globals()), root, args.transition,
                                            args.feature, args.check, read(args.report) if args.report else None)
        elif args.action == 'init':
            ensure_local_excludes(root)
            path = root / '.specify/workflow.yml'
            policy = default_policy(args.qa == 'on', args.manual == 'on')
            raw = path.read_bytes() if path.exists() else None
            if raw is not None:
                old = load_policy(root)
                require(args.replace or old['processes'] == policy['processes'], 'POLICY_EXISTS: use --replace after reviewing changed selections')
                if args.delegate is not None:
                    require(args.replace or old['delegation']['enabled'] == (args.delegate == 'on'),
                            'DELEGATION_SELECTION_EXISTS: use --replace after reviewing the changed selection')
                policy = old
                policy['processes'] = {'qa': args.qa == 'on', 'user_manual': args.manual == 'on'}
            if args.delegate is not None:
                policy['delegation']['enabled'] = args.delegate == 'on'
            if args.board:
                # The two mode keys are operational (OPERATIONAL_SUBKEYS): changing them invalidates no receipt.
                policy.setdefault('project_sync', {})['mode'] = {'none': 'off'}.get(args.board, args.board)
                policy['issue_sync']['taskstoissues'] = 'off' if args.board != 'full' else (
                    'required' if policy['issue_sync']['taskstoissues'] == 'off' else policy['issue_sync']['taskstoissues'])
            select_gate(policy['ci'], args.gate_mode, args.gate_scope, args.gate_rule)
            if args.decision_owner:
                policy.setdefault('decisions', default_policy(False, False)['decisions'])['authorized_users'] = args.decision_owner
            validate_policy(policy, root)
            # AHMED-08: an unchanged policy keeps the file's bytes (and comments); a rewrite backs up the raw bytes.
            written = raw is None or parse_policy(raw.decode('utf-8-sig')) != policy
            result = {'configured': True, 'written': written, 'processes': policy['processes'],
                      'board': board_mode_line(policy), 'gate': sanduq_ci.gate_config(policy['ci'])}
            if written:
                if raw is not None:
                    backup = root / '.specify/workflow/backups' / (uuid.uuid4().hex + '.workflow.yml')
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    backup.write_bytes(raw)
                    result['backup'] = backup.relative_to(root).as_posix()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding='utf-8')
            if args.replace:
                # The features whose receipts the new policy invalidates, from the same plan `migrate` records.
                affected = []
                for checkpoint in sorted((root / 'specs').glob('*/workflow/checkpoint.json')):
                    state = read(checkpoint, {})
                    if not isinstance(state, dict) or not state.get('receipts'):
                        continue
                    feature = checkpoint.parent.parent.relative_to(root).as_posix()
                    plan = Run(root, feature).migration_plan(state)
                    if plan['invalidated']:
                        affected.append({'feature': feature, 'restarts_from': plan['invalidated'][0],
                                         'invalidated': plan['invalidated'],
                                         'migrate': WORKFLOW_SCRIPT + ' migrate --feature ' + feature + ' --reason "<why>"'})
                result['affected_features'] = affected
            result['doctor'] = doctor(root, policy)
            if manual_missing(root, policy):
                result['next'] = MANUAL_INIT_NEXT
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
                dropped = []
                if ci['policy'] == 'self-hosted-required':
                    # F7: a hosted default the command did not name and no exception covers is dropped, so the
                    # selection is one the installer can apply.
                    documented = {entry.get('platform') for entry in ci.get('exceptions', [])}
                    for platform, labels in list(ci['runners'].items()):
                        if getattr(args, platform) is None and sanduq_ci.hosted(labels) and platform not in documented:
                            require(platform != 'linux', 'CI_HOSTED_RUNNER_UNDOCUMENTED: linux runs on '
                                    + ', '.join(labels) + '; pass --linux self-hosted,<label>')
                            dropped.append(platform)
                            ci['runners'].pop(platform)
                select_gate(ci, args.gate_mode, args.gate_scope, args.gate_rule,
                            {'affected_command': args.affected_command,
                             'verification_check': args.verification_check,
                             'verify_command': args.verify_command})
                write(root / '.specify/workflow/backups' / (uuid.uuid4().hex + '.json'), load_policy(root))
                (root / '.specify/workflow.yml').write_text(
                    yaml.safe_dump(validate_policy(policy, root), sort_keys=False), encoding='utf-8')
            # The recorded selection is not live until the installer re-renders
            # each managed workflow file from it.
            result = {'ci': ci, 'saved': not args.show, 'doctor': doctor(root, policy)}
            if not args.show and dropped:
                result['dropped_hosted_platforms'] = dropped
        elif args.action == 'decisions':
            policy = load_policy(root)
            config = policy.setdefault('decisions', default_policy(False, False)['decisions'])
            if not args.show and (args.owner or args.field_name):
                if args.owner: config['authorized_users'] = args.owner
                if args.field_name: config['project_field'] = args.field_name
                validate_policy(policy, root)
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
            policy = load_policy(root)
            result = doctor(root, policy, project=args.project, explicit=True)
            store_doctor_cache(root, policy, result)
        elif args.action == 'project-defaults':
            result = project_defaults(root, load_policy(root))
        elif args.action == 'identity':
            result = issue_identity(root, args.issue)
        elif args.action == 'prepare':
            result = prepare_issue(root, args.issue)
        else:
            if args.action == 'status' and not args.feature:
                require(args.issue, 'STATUS_TARGET_REQUIRED: pass --feature specs/<slug> or --issue <n>')
                args.feature = feature_for_issue(root, args.issue)
            run = Run(root, args.feature)
            if args.action == 'start': result = run.start(args.issue)
            elif args.action == 'next': result = run.next(run.load(), args.finalize)
            elif args.action == 'status':
                state = run.load(allow_branch_change=True)
                result = native_run_status(root, run.relative, state, args.runs)
                result['lean_execution'] = lean_policy.describe(run.policy, state_tier(state))
                if state.get('active'):
                    # A session resuming a held claim needs the receipt shape without re-claiming.
                    result['receipt_template'] = run.receipt_template(state, state['active']['stage'])
                card = run.lite_card(state)
                if card:
                    result['instructions'] = card
                    if state.get('active'):
                        result['cli'] = claim_cli(run.relative, state['active']['token'])
            elif args.action == 'claim':
                result = run.claim(read(args.usage), args.finalize, args.verbose,
                                   confirm_invalidation=args.confirm_invalidation)
                if not args.verbose:
                    result.pop('baseline', None)  # kept in the checkpoint; --verbose prints it
            elif args.action == 'complete':
                result = run.complete(args.token, read(args.receipt, {}))
                if not args.verbose:
                    result = compact_completion(result)
            elif args.action == 'revalidate-upstream':
                require(args.plan or args.receipt, 'REVALIDATE_UPSTREAM_RECEIPT_REQUIRED: pass --receipt, or --plan')
                result = run.revalidate_upstream(args.through, read(args.receipt) if args.receipt else None,
                                                 args.plan, args.actor)
            elif args.action == 'bind': result = run.bind(args.token)
            elif args.action == 'recover':
                result = run.release_ownership(args.token, args.reason, force_live_owner=args.force_live_owner)
            elif args.action == 'relocate':
                result = run.relocate(args.reason, args.preview, args.allow_branch_rebind,
                                      args.allow_repository_rename, args.issue, args.keep_issue_number, args.actor,
                                      args.allow_history_change)
                if args.preview and not result['can_apply']: result['ok'] = False
            elif args.action == 'migrate' and args.preview: result = run.preview_migration(args.invalidate_from)
            elif args.action == 'migrate': result = run.migrate(args.reason, args.invalidate_from)
            elif args.action == 'amend':
                result = run.amend(args.stage, args.evidence, args.reason, args.assessment, args.actor)
            elif args.action == 'refresh': result = run.refresh(args.from_stage, args.reason)
            elif args.action == 'project-sync': result = run.sync_project(args.phase)
            elif args.action == 'sync-amend': result = run.sync_amend(args.reason, args.actor)
            elif args.action == 'revalidate':
                result = run.revalidate(args.stage, args.check_run, args.attempt, args.diff_reviewed, args.base_ref,
                                        args.reason, args.actor)
                if not result['revalidated']:
                    result['ok'] = False
            else:
                with locked(run.lock):
                    state = run.load()
                    result = run.checkpoint(state, args.reason)
        print(json.dumps(result, indent=2))
        return 1 if result.get('ok') is False else 0
    except (WorkflowError, ValueError, KeyError, yaml.YAMLError) as exc:
        # A bare KeyError prints as the quoted key; name the condition instead (AHMED-05).
        message = 'POLICY_KEY_MISSING: ' + str(exc.args[0] if exc.args else exc) if isinstance(exc, KeyError) else str(exc)
        print(json.dumps({'ok': False, 'error': message, **explain(message, getattr(args, 'feature', None))}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
