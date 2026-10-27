# Issue #99: plan

https://github.com/samykabu/sanduq/issues/99, validated on main 07dc50f (Workflow 1.15.0) on 2026-10-20.
Branch `fix/issue-99`, worktree `D:\Projects\Personal\sanduq-issue99`. Notes: `issue-99-notes.md`.

## Validation

- **F1 valid.** `workflow.py` completion (around line 3506) refuses any change to a path an earlier receipt
  depends on unless the claimed stage lists it in `SIDE_EFFECTS`; only Clarify lists
  `.specify/project-sync-state.json`. After completion, `receipt_status` compares every dependency hash, so a
  later status-only write stales the earlier receipt (`explicit-drift`). The state file is not a required
  input; it enters receipts because agents list it (Clarify edits it, Specify reads it). `project_sync.py`
  keeps one entry per feature slug: `issue`, `issueNodeId`, `itemId`, `status`, `subIssues`.
- **F2 valid.** `sanduq_freshness.inputs` takes every feature file plus every changed or untracked file
  (document kind); nothing under the feature or `<root>/qa/` is excluded, so a report written after `record`
  is a new input and status turns stale. `.specify/extensions/` is already excluded.
- **F3** needs no code: `lean_policy.py` already makes Ready, PR, Execute coordination and Tasks-to-Issues
  coordinator-owned when enabled. Document adoption.
- **F4** is a documentation and contract gap (finalization order).

## Design (smallest change consistent with the existing contracts)

1. **Semantic projection of the sync state (F1).** For the configured state file (`stateFile` in
   `.specify/extensions/project/config.json`, default `.specify/project-sync-state.json`), the runtime
   fingerprints a receipt dependency as `sync-binding:v1:<sha256>` of the canonical JSON of the bound
   feature's entry with administrative fields removed (`status` and any timestamp fields). Status-only
   transitions therefore never stale a receipt or refuse a completion, whoever runs the sync and in either
   order; changes to `issue`, `issueNodeId`, `itemId` or `subIssues`, a missing entry, or a foreign repository
   still do; other features' entries no longer matter. Every other path keeps byte hashing.
2. **Legacy receipts.** A receipt recorded before this release holds a raw byte hash for the state file.
   Comparison stays byte-exact for those (fail closed). `workflow.py migrate` (the step every in-progress
   feature already runs after an upgrade) and a new `workflow.py sync-amend --feature <f> --reason <text>`
   convert them: verify the current entry's binding against `scope-source.json` (repository and issue) and
   `workflow/task-issues.json` (task mapping), then replace the raw hash with the projection in each
   receipt that depends on it, appending an `administrative-amendment` lineage record (old and new value,
   fields that changed, reason, time). Never rewrite any other hash; refuse when the binding differs.
3. **One runtime-owned sync step (F1, R4).** The claim's `project_sync.command` becomes
   `python .specify/extensions/workflow/scripts/workflow.py project-sync --feature <f> --phase <p>`. It runs
   the Project script with `--summary`, records `project_sync: {phase, state: pending|done|failed, at,
   summary}` in the checkpoint (pending before the call, done or failed after), is idempotent (an already
   applied phase whose entry already shows that status succeeds without a second remote write), and `next`
   and `status` report a pending or failed sync for retry. Contract: run it after `complete` (Execute:
   before the claim, as today); before `complete` it is also safe now because of design 1.
4. **Reports out of the semantic inputs (F2).** The supported location for generated freshness logs and
   status reports is the extension's state folder (`.specify/extensions/assure/state/<feature>/reports/`,
   `.specify/extensions/user-manual/...` likewise), already excluded. Commands write logs there and finish
   them before the final `record`/`status`. The helper additionally excludes, for the document kinds only,
   the paths it was told are this record's outputs from the implicit inputs (they stay hashed as outputs,
   so a missing or modified output still stales the state); Analyze keeps today's behaviour. No blanket
   exclusion of QA files, JSON, Markdown or logs.
5. **Documentation (F3, F4).** `dispatcher-operations.md` and `stage-pr.md` state the finalization order
   (code and affected tests; independent review; documentation and portable evidence; Ready; freeze the
   candidate; indexed and clean-candidate gates; publish or reuse one PR with `pr_publish.py`; `complete`;
   `project-sync`; exact final-head check) and the bounded recovery (`sync-amend`, evidence amendment,
   scoped revalidation before another semantic agent). `docs/workflow/` gets the lean adoption note
   (`lean_execution.enabled: true`, never during an active claim, what stays semantic).

## Streams (Opus 5.5 high)

| Stream | Owns |
| --- | --- |
| A runtime | `extensions/workflow/scripts/workflow.py`, `extensions/workflow/schemas/*`, `extensions/workflow/commands/*` if a command lists the new subcommands, `skills/workflow/references/dispatcher-operations.md`, `stage-pr.md`, `receipt-rules.md`, `delegation-and-decisions.md`, tests `test_workflow.py`, `test_receipt_contract.py`, `test_project_sync_summary.py`, `test_lean_execution.py`, `test_lean_native_integration.py`, a new `test_sync_binding.py` |
| B freshness and docs | `extensions/scripts/shared/sanduq_freshness.py`, `extensions/assure/**`, `extensions/user-manual/**` (non-vendored), `docs/workflow/*.md` (lean adoption), tests `test_freshness.py` and the assure and user-manual suites |

Regression cases R1 to R9 from the issue map to: A covers R1, R2, R3, R4, R8; B covers R5, R6, R7, R9
(packaged helper copies equal the canonical file). Each defect test fails before the fix.

## Release

Workflow 1.16.0 (new subcommands, changed claim field), Assure 2.5.1 and User Manual 1.7.1 (shared helper);
`release.py bump`, changelogs, `pending-releases.json` ready, PR with every CI job green, release, comment on
#99. The consumer rollout and the two-pass consumer acceptance are the consumer's steps; this repo
ships the fix, the upgrade notes and a synthetic two-pass test.
