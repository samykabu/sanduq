# Issue #99: stream notes

Append under your heading with one shell append. Plan: `issue-99-plan.md`.

## A runtime

Changed: `extensions/workflow/scripts/workflow.py`, `schemas/receipt-v1.schema.json` (fingerprint value may
be `sync-binding:v1:<sha256>`), `schemas/checkpoint-v1.schema.json` (`project_sync`, `lineage` documented),
references `dispatcher-operations.md`, `stage-pr.md`, `receipt-rules.md`; new `tests/test_sync_binding.py`.
Outside the listed files (minimal): `tests/test_front_half_runtime.py` (two exact `project_sync.command`
strings) and `extensions/workflow/README.md` (`sync-amend` added to the "use these instead of editing
checkpoints" list). `delegation-and-decisions.md` contradicts nothing; untouched. `commands/*` list no
subcommands; untouched.

Design 1: `fingerprint_files(..., feature=, like=)` hashes the configured `stateFile` (read from the Project
config, canonicalised, default when unset or invalid) as `sync-binding:v1:` + sha256 of the canonical JSON
(sorted keys, compact) of the entry keyed by the feature folder name, minus administrative keys
(`status`, any key matching `\w*At`, `\w*_at`, `*timestamp`). A missing entry projects `null` (so a vanished
entry stales); unparseable bytes project their own hash (fail closed). Used when recording (`_stamp`), for
the claim baseline and completion check, and in every receipt comparison (`receipt_status`,
`upstream_drift`, `receipt_drift`, `consulted_drift`, revalidate-upstream re-stamp). Repository binding: the
state file does not store the repository (top level is `{slug: entry}`, entry is `issue, issueNodeId,
itemId, status, subIssues`); `issueNodeId`/`itemId` are repository-scoped and stay in the projection, and
`scope-source.json` (repo and issue) is already a required input from Specify on. Clarify's side-effect
permission now names the configured path (`side_effects(..., root)`).

Design 2: `like` keeps a stored raw hash byte-exact. `Run._amend_sync_binding` (used by `migrate` and the
new `sync-amend --feature --reason [--actor]`, no active claim) verifies the entry: present, `issue` equals
`scope-source.json`'s issue, scope-source binds the checkpoint's `repo#issue`, and any `subIssues` match
`workflow/task-issues.json` (identity and per-task numbers). It then replaces only the raw state-file hash in
each receipt and appends to `state['lineage']` (where Clarify's side-effect lineage already lives) a record
`{kind: administrative-amendment, via: sync-amend|migrate, path, reason, actor, at, receipts: {stage: {before,
after, fields}}}`. `fields` compares the entry with the recorded bytes, found in the working tree, HEAD or
the last 50 commits touching the file; not found, or a non-administrative field changed, refuses (see Review
fixes). All checks run before any
hash moves. `migrate` reports `sync_binding: {amended, refused}` and leaves raw hashes when refused.

Design 3: claim `project_sync.command` is `python .specify/extensions/workflow/scripts/workflow.py
project-sync --feature <f> --phase <p>`. `Run.sync_project`: records `pending` (lock, save), runs the Project
script with `--feature <slug> --summary` via `sys.executable` (no lock held), records `done` (exit 0 and an
`ok ` line and the configured status reached) or `failed` with the last output line. A pending or done
attempt at the same phase whose entry already shows the phase's configured status records `done` without
calling the script; a failed attempt always runs again. `next` and `status` add
`project_sync` (with a `retry` command) while pending or failed. Phases: the six scheduled plus `done`.

Design 5: `dispatcher-operations.md` Project Sync section rewritten for the runtime step and the projection,
new "Finalization order" section with the bounded recovery (`sync-amend`/`migrate`, `amend`,
`revalidate-upstream`, `revalidate`, then re-record); `stage-pr.md` new "Order" section; `receipt-rules.md`
side-effect sentence. Kept the inventoried rule phrase "a graceful skip is not success" (test_skill_split).

Regressions (all in `test_sync_binding.py`; run on HEAD before the fix, 15 tests: 5 failures, 12 errors):
- R1 `test_r1_status_only_transition_during_the_pr_claim_completes`: HEAD
  `WorkflowError: UPSTREAM_INPUT_CHANGED_DURING_STAGE: .specify/project-sync-state.json`. Passes.
- R2 `test_r2_post_stage_sync_returns_to_no_stage_and_passes_the_gate`: HEAD `next` returned Specify
  (`None != 'ready_to_finalize'`). Passes, gate passed. Also `test_r2_runtime_sync_after_complete_keeps_specify_current`
  (HEAD: no `sync_project`).
- R3 `test_r3_binding_changes_reject_while_other_features_and_status_do_not` (state at
  `.specify/board/sync-state.json`, another feature's entry, default path byte-hashed): HEAD failed at the
  projection assertion (byte hash recorded; another feature's change would have staled). Issue, issueNodeId,
  itemId, subIssues and a missing entry each stale the receipt and refuse completion; scope-source repo
  change refuses `FEATURE_BINDING_MISMATCH`; status plus another feature's binding change complete.
- R4 `test_r4_retries_are_honest_idempotent_and_write_once`, `test_r4_failure_before_the_write_retries_once`
  (fake Project script in the temp repo; CLI and API): HEAD errors (no subcommand). Pending seen by the
  script, failed recorded and reported by `next`/`status`, failure after the remote write then retry runs
  the script again with no second remote write, a done phase is not run again, later phase writes once.
- R8: existing coverage: `test_lean_execution` (coordinator stage start refuses before launch, coordinator
  claim installs nothing, `CLAIM_TOKEN_MISMATCH`), `test_delegation` (wrong-token dispatch start, attempt
  without this claim's token refused), `test_front_half_runtime` (tier defaults). Added
  `test_r8_ready_and_pr_are_coordinator_mechanics_only_when_lean` (passes on HEAD; guard) and
  `test_r8_lean_ready_and_pr_claims_launch_no_model_and_refuse_a_foreign_token` (HEAD failed only on the
  new command string).
- Legacy: `test_raw_hash_stays_byte_exact_until_sync_amend`, `test_sync_amend_refuses_a_binding_that_differs_from_scope_and_task_mapping`,
  `test_migrate_converts_a_verified_binding_and_keeps_a_differing_one_raw`, `test_sync_amend_command_line`,
  `test_projection_ignores_timestamps_and_key_order`: HEAD errors (no API). Pass.

Tests (Windows, cwd `extensions/workflow/tests`): test_sync_binding 15 OK; test_workflow 44, test_receipt_contract
30, test_project_sync_summary 15, test_lean_execution 20, test_lean_native_integration 18, test_front_half_runtime
47 all OK; test_source_key 12, test_ci_revalidation 37, test_eol_fingerprints 12, test_upgrade 9, test_contracts 1,
test_reporting_instructions 11, test_skill_inventory 57, test_skill_split 11 (rerun after the doc edits, with
test_execution_protocol_b11: 89 OK) all OK; also test_task_issues 25, test_delegation 181, test_gate_explain 13,
test_apply_pending 21, test_ci_gate 29, test_checkpoint_identity 58, test_evidence_snapshot 16, and test_lint,
test_lifecycle, test_decisions, test_verify_affected, test_waivers, test_reconcile 89 (1 skipped) OK. Full
suite not run.

Open:
- A `stateFile` outside the operational folders (not under `.specify/`, `specs/`, ...) is in the source
  inventory, so a status write there is source drift for Verify/Review/Ready. Not changed (source-key scope);
  now documented (dispatcher-operations.md, docs/workflow/state-files.md).
- `sync_entry` keys entries by the feature folder name, as project_sync.py does; a consumer whose sync ran
  with a different `--feature` slug gets a `null` entry (fails closed).
- An entry first created after a receipt listed the state file (no entry → entry) stales that receipt and
  `sync-amend` refuses it; re-record is the route.
- CHANGELOG line 20 still describes the old command; release step owns it.

Review fixes (Codex review of 319e1b7; regressions in `test_sync_binding.py`, each failed on 4001e7a, checked
by running the new file against `git archive HEAD`: 7 failures):
1. `sync-amend`/`migrate` no longer accept an unknown old binding. `recorded_sync_fields` looks for the bytes
   the raw hash names in the working tree, HEAD, then `git rev-list -n 50 HEAD -- <label>`; none matches:
   `SYNC_BINDING_MISMATCH: no version ... re-record the stage`. `fields` is never null. Tests
   `test_review_fix_1_the_recorded_bytes_must_be_found` (HEAD: not raised),
   `..._history_names_the_fields` (HEAD: `None != ['status']`), `..._history_refuses_a_binding_change` (HEAD:
   committed itemId change accepted). Older legacy tests now commit the recorded bytes first.
2. Clarify's permitted re-stamp writes the raw byte hash of the current file into a receipt that held a raw
   hash (projection only into projection receipts); the lineage entry gets `raw: {stage: {path: {before,
   after}}}` with what was written. `test_review_fix_2_clarify_restamp_keeps_a_legacy_hash_raw` (HEAD: wrote
   `sync-binding:v1:...`).
3. The `project-sync` fast path needs the previous record for the phase to be `pending` or `done`; after
   `failed` the script always runs. `test_review_fix_3_...` (HEAD: `(True, 'done')`); R4 updated (the retry
   after a failure now calls the script; the fake script, like Project, skips the remote write when the
   status is set). Added `test_pending_attempt_whose_status_is_set_is_done_without_a_call`.
4. `done` needs the `ok ` line and the entry's status equal to `phaseToStatus[phase]` (`in-progress` also
   accepts the `in-review` status); no target configured keeps the `ok` rule. Otherwise `failed`, summary
   suffixed `(status X is not the configured status)`. `test_review_fix_4_...` (HEAD: `(True, 'done')`).
5. Docs: dispatcher-operations.md (Project Sync section and the sync-amend recovery bullet) and
   docs/workflow/state-files.md say the guarantee holds for a state file under `.specify/` and a state file
   elsewhere is source for Verify, Review and Ready; both describe the recorded-bytes lookup.
Results: test_sync_binding 22, test_workflow 44, test_receipt_contract 30, test_project_sync_summary 15,
test_front_half_runtime 47, test_skill_split 11, test_skill_inventory 57, test_reporting_instructions 11: all OK.
`check_docs.py` OK; `git diff --check` clean.

## B freshness and docs

Changed: `extensions/scripts/shared/sanduq_freshness.py` (document kinds keep declared outputs out of the
implicit inputs; record writes `outputsNotInputs: true`; status excludes the saved outputs only when that
marker is present), the Assure analyze/document and User Manual update commands (report location), the
lean adoption section in `docs/workflow/operating-guide.md` (+ TOC entry; no other index lists its
sections), tests in `extensions/workflow/tests/test_freshness.py`. Partial patch reviewed, corrected
(analyze text, `<feature-slug>`, wrong User Manual path, lean text) and deleted.

Report locations (both already excluded by the helper): Assure `.specify/extensions/assure/state/<feature-name>/reports/`
(states are `state/<feature-name>-<kind>.json`); User Manual `User-Manual/.state/features/<feature-name>/reports/`
(state is `User-Manual/.state/features/<feature-name>.json`; `User-Manual/` is excluded from inputs and
`.state` from default outputs). The plan's `.specify/extensions/user-manual/...` is not the User Manual
state folder, so it was not used.

Backward compatibility: a state without the marker (1.15.0) compares with outputs still counted as inputs,
exactly as recorded; the next `record` writes the new shape. Analyze never gets the marker.

HEAD failure mode (honest): on 1.15.0 a declared output that is also implicitly discovered (feature dir,
changed or untracked file, e.g. `qa/features/<f>/index.html`) is hashed twice. The verdict for a changed or
regenerated output is the same either way; what differs is the diagnostics: a modified guide reports
`changed_inputs: [guide]` as well as `changed_outputs`, so an agent sees a "semantic" change. The incident
itself (an undeclared log written into the feature `qa/` after `record`) stays stale by design (no blanket
exclusion); the fix there is the documented location.

Regressions:
- R5 `test_reports_and_regenerated_outputs_do_not_stale_document_state`: FAILED on HEAD helper
  (`AssertionError: 'qa/features/001-example/index.html' unexpectedly found in {...inputs}`; status on HEAD
  returns `changed_inputs: [guide], changed_outputs: [guide]`). Passes now: identical regeneration and a
  report in the Assure state folder stay current; a modified guide is `changed_outputs` only; a late report
  in the feature `qa/`, a source, a test and the acceptance plan still stale.
- R6 `test_declared_outputs_keep_integrity_wherever_they_live` (guard, passes on HEAD and now): modified,
  corrupt (binary image), deleted outputs, including ones excluded from implicit discovery, stale; record
  with a missing output raises.
- R7 `test_bookkeeping_stays_current_and_semantic_qa_json_stales` and `test_analyze_keeps_its_outputs_as_inputs`
  (guards): checkbox, progress and graph churn stay current; QA JSON, requirement, task meaning and source
  stale; Analyze keeps tasks.md as an input, no marker.
- R9 `test_state_recorded_by_1_15_0_stays_current` (guard; would fail if status excluded outputs
  unconditionally). LF/CRLF, changed/untracked/deleted: existing `test_freshness`/`test_eol_fingerprints`
  cases. Packaged copies: `test_eol_fingerprints` already asserts both archives carry the canonical helper
  byte for byte; no new check added.

Tests (Windows): workflow `test_freshness test_assure_state test_eol_fingerprints test_source_key` 52 OK;
`test_install test_upgrade` 39 OK; `test_delegation test_hosts` 209 OK; Assure suite 24 OK; User Manual
suite 44 OK; `extensions/scripts/tests` 124 OK; `check_docs.py` and `test_check_docs.py` pass;
`git diff --check` clean. Full workflow suite not run (Stream A editing `workflow.py` concurrently).

Open: changelog/version entries for Assure 2.5.1 and User Manual 1.7.1 left to the release step.

## Orchestrator
