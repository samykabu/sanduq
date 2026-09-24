# Sanduq Delivery implementation plan

Status: implementation and PR checks complete; merge and release verification pending.
Source: [design report](sanduq-native-workflow-prototype.html).
The [isolated native prototype result](native-workflow-prototype-results.md) is
currently no-go for production scheduling; the existing dispatcher is retained.
Target: a reusable Sanduq workflow for a new project, with tested installation paths
for an existing repository without Spec Kit and an older Sanduq installation. Bunyan
is a consumer example, not an implementation target.

## Decisions already made

- GitHub issue comments hold material questions and their answers. The feature issue
  is the team discussion record. Project Status remains the lifecycle phase; a
  separate Decision single-select field reports waiting/review/applied state.
- A configured decision authority settles a question. An agent recommendation or a
  local IDE answer is not an authorized decision.
- The workflow evidence CI gate is chosen during initialization: Disabled,
  Advisory, or Required. Enabled gates default to managed-only applicability; a
  PR with no changed feature evidence or explicit feature mapping reports
  `not_applicable` successfully. Rule groups are project-selected.
- QA Assure and User Manual are independent project selections at initialization
  and can be changed later through a reviewed policy migration.
- A native Spec Kit workflow is a prototype candidate for scheduling. It replaces
  Sanduq's scheduler only if stage receipt, recovery, pause/resume, and agent
  dispatch contracts pass. Otherwise the decision service and CI changes ship
  against the existing dispatcher; the prototype remains isolated.

## Phase 1: baseline and contracts

1. Record current versions, source tests, CLI capabilities, dependency lock, package
   layout and GitHub release/catalog rules. Keep the existing HTML design report.
2. Define versioned policy schema for CI gate mode, applicability and rule groups;
   decision authority/field mapping; delivery versus runner policy digests; and
   explicit QA/manual lifecycle changes.
3. Define decision ledger and binding record schemas, stable IDs, answer authority,
   comment revision handling, artifact provenance and transition rules.
4. Define native-stage contract and test the current engine against both Claude and
   Codex dispatch. No user text or issue title enters an interpolated shell command.

Evidence: schema fixtures, CLI/engine behavior probes, a reviewed compatibility
decision, and baseline test results. No consumer repository changes.

## Phase 2: reusable runtime and GitHub collaboration

1. Add a stage-neutral decision adapter that publishes/reuses one question comment,
   records the remote ID before claiming success, verifies configured authority,
   rereads edited answers on resume, and writes an applied outcome to a committed
   ledger. Treat conflicting/deleted answers and uncertain remote writes as pending.
2. Route material questions from Tasks and Analyze, then all managed stages, through
   the adapter. Analyze remains read-only and sends accepted changes to the owning
   Specify/Plan/Tasks stage. An open question cannot produce a passed receipt.
3. Add Project Decision-field synchronization, keeping Status at its current phase.
   Detect existing Project field IDs and automations; never derive an answer from the
   field value alone.
4. Prototype `sanduq-delivery` as a separately packaged native workflow. One stage
   completes only with a current matching Sanduq receipt and no open decision.
   Demonstrate a controlled new generation for earlier-input invalidation; do not
   edit the native engine's `state.json` by hand. If its supported step/timeout model
   cannot satisfy this, retain the existing dispatcher as the production scheduler.

Evidence: fake-remote crash/retry tests, issue-authority tests, changed-answer tests,
Claude and Codex CLI dispatch traces, pause/resume and stale-input traces.

## Phase 3: optional CI gate and project policy

1. Add gate choices to initialization and a later `ci` policy command. Disabled
   installs no workflow-evidence job; Advisory reports findings without blocking;
   Required has a stable job that succeeds with an explicit `not_applicable` result
   for ordinary non-managed PRs.
2. Refactor `ci_gate.py` into typed applicability plus selectable rules: fixed
   identity baseline; receipts, decisions, tasks, task links, documentation,
   portability, candidate-merge freshness, and live answers. Validate rule
   dependencies. Existing application test jobs stay project-owned.
3. Keep code-only managed PR opt-in through `pr-features.json`. Make all-PR mapping
   an explicit stricter scope. Add exact rule/feature/PR waivers only when an
   authorized GitHub reviewer and reason/expiry can be verified.
4. Version delivery and CI policy digests separately. Migrate old checkpoints with
   an audit trail; runner-only changes must not invalidate delivery receipts.
5. Render workflows from project-selected runner/capability policy, preserve
   customized CI when requested, and inspect branch rules for a stale required
   check before disabling or renaming the job.

Evidence: Disabled/Advisory/Required and rule-matrix tests; ordinary bug-fix PR;
mapped feature PR; runner-only migration; candidate-merge drift; waiver authority;
clean-checkout verification.

## Phase 4: installation and lifecycle

1. Package the new workflow and deterministic adapters with Sanduq, preserving
   extension/preset source ownership and a pinned compatibility contract.
2. Test a fresh repository; an existing codebase initialized in place using the
   supported Spec Kit path; and an older Sanduq setup. A clean managed reset is
   offered only after backup/diff and no active claims or unmapped custom data.
3. Add an explicit reviewed policy-change path to opt in or out of QA Assure and
   User Manual after initial use. Installer updates selected dependencies and CI
   assets; existing artifacts and historical receipts stay intact. A policy change
   invalidates only affected current work.
4. Keep issue-derived branch/feature naming for issue-bound work, with a separate
   non-issue Spec Kit route. Never rename an active feature during adoption.

Evidence: install/upgrade/rollback receipts, doctor output, package validation,
feature migration tests, selected-process matrix and non-feature bug-fix walkthrough.

## Phase 5: release documents and delivery

1. Update root and workflow READMEs; replace stale staged-version claims. Bump the
   workflow extension to the next minor version and update catalog/pending-release
   metadata through the repository's release conventions.
2. Publish a dedicated usage guide covering greenfield, brownfield, older-version
   reset, non-Spec Kit bug fixes and PRs, optional CI gate, issue decisions, QA and
   User Manual opt-in during initialization, later opt-in, and later opt-out.
3. Run focused and full Sanduq checks, package/install validation, CLI integration
   probes, and a clean candidate checkout. Keep unrun or skipped scenarios open.
4. Commit and push the branch, open a PR with exact evidence, verify remote checks
   and review/branch-rule requirements, merge the authorized PR, and verify the
   merge SHA and final repository state. A merged PR does not certify a deployment.

## Completion rule

Every item above needs current file, command, test, GitHub, or rendered-artifact
evidence. A native-workflow prototype that fails its contract is recorded as a
no-go and cannot be described as the production scheduler. CI modes and rule
coverage must be reported exactly; `not_applicable` is never feature verification.
