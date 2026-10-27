# Changelog

## [Unreleased]

- `claim --finalize` and `next --finalize` before Ready claim nothing: they return `status: not_ready_to_finalize` with `remaining` (the stages still to run before Ready, in order), the pending stage's `reason` and `command: speckit.workflow.continue`. Finalize is Ready plus the PR (AHMED-07).
- Decision answers tolerate `SD1: B.`, `SD1 - B`, `SD1 = B` and a ` - feedback` tail; every authorized comment that names a question without a counted answer is listed under that decision's `unparsed` (comment id, URL, author, reason) in the ledger and the `sync` output, including several letters on a single-choice question (AHMED-15).
- A comment a Sanduq process posted through `sanduq_gh` is never a decision answer: `sanduq_gh.api` logs every issue comment it creates in `.specify/workflow/runtime/posted-comments.jsonl` (local runtime, never committed) and `decisions.py` rejects those ids with the reason `posted by a Sanduq process`; a comment older than the question is rejected as `posted before the question`. Docs state that the issue-author default is unsafe on a public repository (SEC-05, DEC-16 A).
- `GIT_ERROR` (no origin) and `GITHUB_ISSUE_REQUIRED` name the repository they looked in and the `git remote` command; `issue_identity` reads `repos/<origin>` first and refuses a fork with `ORIGIN_IS_FORK: ... is a fork of <parent> ...` before anything is bound (AHMED-13).
- `clarification.transport: github-comments | local` (REQ-21). `start` copies it to the checkpoint as `clarification_transport`; it is an operational key, so changing it mid-feature invalidates nothing. Every claim prints `clarification_transport`. With `local`: `decisions.py ask` appends the question (checkbox options, `(Recommended)` suffix) to `specs/<feature>/clarifications.md` and `sync` reads the file (ledger only, `transport: local`, answers `source: local` with the answer line as `quote`; `upgrade-questions` refuses with `DECISION_TRANSPORT_LOCAL`); the Clarify receipt must list the file as an input (`CLARIFICATION_FILE_INPUT_REQUIRED`), every `C<r>Q<n>` in it needs a reply (`CLARIFICATION_UNRESOLVED` names them and the unparsed lines) and the stored receipt carries the runtime-owned `self_attested` field, which the CI gate reports as `CLARIFICATION_SELF_ATTESTED`; worker stage briefs tell the worker to post nothing to GitHub; `status` prints `questions` (`transport`, `answered_in`, `waiting` ids). The `delegation-and-decisions`, `stage-clarify` and Clarify overlay texts are transport-conditional; the github-clarification skill gains `references/local.md`.
- Maintainers: `test_lifecycle_e2e.py` also drives a lite feature with the local transport and asserts no `gh` call; the test harnesses claim with `claim_any` (finalize only at `ready_to_finalize`).

## [1.20.0] - 2026-10-27

- Runtime locks (`dispatch.lock`, feature, upgrade, install and decision locks) recover from a killed owner: a lock whose recorded pid has exited on this host is reclaimed by the next command, with no manual cleanup. A live owner still refuses with `WORKFLOW_BUSY`, which now names the owner's pid, host, age and liveness (`alive: yes` or `unknown`) and how to check it. A lock from another host, or one written by an earlier Workflow version (no host recorded), is never taken automatically; delete it once you have checked that its process is gone. A crashed upgrade's `upgrade.lock` still blocks claims on purpose: rerun the upgrade, which reclaims the lock.
- Subprocesses that run under the dispatch and feature locks are bounded: the Memory helper (120 s, `MEMORY_HELPER_TIMEOUT`), the delegation doctor's node probes (15 s each, `DELEGATE_DOCTOR_TIMEOUT`) and the incremental-review diff (300 s, `DIFF_REVIEW_TIMEOUT`). Each error names the command to run next; the locks are released.
- Internal: one shared lock, atomic JSON write and bounded runner, `sanduq_fs.py`, packaged into `scripts/`. `delegation.file_lock`, `recover_stale_lock` and `process_alive` keep their names.
- A second session can no longer take over a live claim. The active claim records its host, an owner pid (when the claimer is a long-running process; a CLI claim records none, since the CLI exits at once) and `heartbeat_at`, refreshed by `pause`, `bind` and `Run.heartbeat` (a rejected `complete` leaves the claim unchanged). `recover` refuses with `CLAIM_OWNER_ALIVE` while that pid runs on this host, or while the last activity is under 15 minutes old and no exited pid disproves it; the message names the owner, session and the `status` command. `--force-live-owner "<how you know it stopped>"` overrides and is recorded with the recovery. `status` shows `owner: alive | dead | unknown` and `last_activity: N min ago`. Claims written before this release keep the old `recover`.
- `OTHER_FEATURE_OWNERSHIP_RECOVERY_REQUIRED` names the other feature's stage, `claimed_at`, session and the exact `workflow.py recover --feature <other> --token <token> --reason ...` command.
- The claim's `receipt_template` no longer pre-fills passing values: `outcome`, `blocking_findings`, `unresolved`, `answers_applied`, `native_links_verified` and `images_verified` are `<...>` placeholders the agent sets. `complete` refuses any placeholder left in a gating field with `RECEIPT_PLACEHOLDER: <field>`.
- The first Plan claim checks the Scope receipt's `effort_score` against the score Scope verified (cached in `scope-source.json` at bind, else the issue's `effort:<n>` label, read once) and refuses a mismatch with `EFFORT_SCORE_MISMATCH` naming both values, or `EFFORT_SCORE_UNVERIFIED` when neither exists.
- `.specify/workflow.yml`: an unknown top-level key, or an unknown key of a fixed-schema section, is refused with `POLICY_KEY_UNKNOWN: <path>; did you mean <closest>?` and the allowed keys. A key from a newer Workflow release gets the same error, which names the `upgrade.py` command. `delegation`, `ci` and `lean_execution` keep their own key checks.
- Worker briefs no longer carry the orchestrator's "spawn a batch of workers" paragraph; a worker gets "You do not spawn agents; return your result to whoever spawned you" and the blocking-wait rule under `## Return and wait rules (F2)`.
- References: `accept`, `adopt`, `reassign` and `trust-reset` run only in the top-level dispatcher session (the guard already refuses them in any host subagent); the orchestration agent reports "needs accept/adopt for T###" at a batch boundary. `trust-reset` needs the user's explicit approval, quoted in `--reason`. Every managed overlay that composes upstream text states that the claim's `reference_text` wins over it and that upstream hook prompts are skipped inside a claim; `dispatcher-operations.md` gives the full precedence order.
- Delegated runs start in a clean environment: every external launch passes the driver `--clean-env` with an explicit `--keep-env` allowlist (runtime basics, `PATH`, home and temp folders, proxy and CA variables, the chosen harness's own provider credentials and every `SANDUQ_*` name except `SANDUQ_ROLE`). `GH_TOKEN`/`GITHUB_TOKEN` reach only routes that use the GitHub adapter (the Execute orchestrator and the discovery and coordination stages); review and analysis routes start in the driver's read-only `--sandbox`. The ledger attempt records `clean_env`, `kept_env_names` (names only), `github_access` and `permission`. Review work stays refused through the external driver (`DELEGATION_REVIEW_ROUTE_UNSAFE`) until the read-only evidence step lands.
- A rejected model is never swapped silently. When a harness rejects the requested model, `collect` stops with `FALLBACK_CONFIRMATION_REQUIRED`, naming the requested and substitute model and the three commands (confirm, start with another allowed model, run natively). Only the user may confirm, in the conversation; the top-level session then runs `delegate_dispatch.py collect ... --confirm-fallback <requested>=<substitute>` (`default` for the CLI default). The substitute must be listed in the route's `fallbacks`, or be the CLI default with the route's new `allow_default_model: true`; otherwise `FALLBACK_SUBSTITUTE_NOT_LISTED`. The guard and the dispatcher refuse `--confirm-fallback` from a worker, subagent or delegated orchestrator. Ledger attempt, `collect` output, `status` and the receipt's `fallback` block carry `requested_model`, `substitute_model`, `actual_model` (harness telemetry only, else `unreported`), `confirmed_by` and `fallback_used`.
- Lean execution: `lean_execution.max_attempts` (default 3) caps attempts per identity and the next one fails with `LEAN_ATTEMPT_LIMIT_REACHED`; `reassign` after a model rejection is refused with `LEAN_PROVIDER_REJECTED` (start with another eligible harness/model pair instead). Failure categories stay distinct.
- The dispatcher bounds the driver: `start` fails with `DELEGATE_START_FAILED` after 60 s without an answer, `collect` with `DELEGATE_COLLECT_TIMEOUT` after 120 s and records nothing; candidate selection reads the doctor's cached health instead of re-probing every node. A coordinator's `collect` refreshes its own claim heartbeat.
- Maintainers: `test_lifecycle_e2e.py` runs a managed feature end to end; the CI matrix declares `memory -> workflow` and `workflow -> scope, pr` dependents and the injected `sanduq_fs.py`, and `test_ci_matrix.py` fails on an undeclared cross-suite reference. The release workflow releases only a `main` commit whose Windows workflow and memory suites also passed (scheduled or dispatched run) and no longer starts twice for one commit. Presets `workflow` 1.3.2 and `scope-gate` 1.6.1 add the precedence clause (`reference_text` wins over composed upstream text).

## [1.19.2] - 2026-10-27

- Reconcile accepts disabled hook prompt/description refreshes only when they match the installed extension manifest. It preserves operational fields and the originally recorded enabled state, and records the old and new metadata in the integration backup and command report. Other disabled hook edits remain blocked.
- Use the standard upgrade to 1.19.2 for this metadata-only blocker. The new installer reconciles hooks inside the rollback transaction and retains metadata decisions in its result, receipt and backup audit, including a later failure. No separate repair, journal edits or temporary hook enablement are needed.

## [1.19.1] - 2026-10-26

- `status` and exact-token `recover` work from another branch, including after the original branch was deleted. Recovery keeps the recorded branch, receipts and an audit of the original claim, actor, reason and terminal writer evidence. It refuses starting, running, unknown or untrusted delegated ownership.
- A dependent claim reconciles a leftover owner only after trusted terminal delegation and live GitHub REST checks prove the bound feature PR merged into its target and closed its issue. Native and legacy claims without terminal writer evidence report the public recovery action. Closure alone cannot release ownership.
- Verified post-merge follow-up reconciles ownership before checking whether Memory is enabled. External delivery can supply the exact PR binding without a PR stage receipt; it never creates acceptance receipts or archives the feature. Worker reservations recheck claim ownership under the delegation lock.

## [1.19.0] - 2026-10-26

- `tested_spec_kit` in `dependencies.json` is Spec Kit 1.1.3, commit `0282d03eb6fc3091b3deaa3a855d4030dc40cd6c` (was 1.0.11, `8147943`).
- `doctor --project` reports a needed extension, or an installed optional one, that is older than the installed Workflow's `dependencies.json` as `DEPENDENCY_UNAVAILABLE`. Every `DEPENDENCY_UNAVAILABLE` message now names the installed and required versions and the fix: `python .specify/extensions/workflow/scripts/upgrade.py --version <workflow version> --apply`.
- Security interim (SEC-01): external delegated runs launch the agent CLI in permission-bypass mode with the full environment, so a `review` route, or any route on the `review` model profile, is refused with `DELEGATION_REVIEW_ROUTE_UNSAFE` at claim and start until the clean-environment launch (PH-02). `doctor` lists the refused routes as a warning; tasks.md marks a refused task `refused:DELEGATION_REVIEW_ROUTE_UNSAFE`. Run reviews natively. Other routes are unchanged.
- Claim: when delegation is on, a review-kind stage (Analyze, Review) is claimed without a delegation route and runs natively in the selected host; the claim records `delegation_refused` and completion needs no dispatcher attempt. Other stages are unchanged.
- `DEPENDENCY_CHANGED` names the `workflow.py migrate` command and the `upgrade.py` fix.
- License: this package is MIT; versions before this one were PolyForm Noncommercial 1.0.0. The archive now ships its LICENSE and a THIRD_PARTY_NOTICES.md for the vendored delegate-task and progress-report material.


## [1.18.0] - 2026-10-21

- The checkpoint has its own schema version, separate from the policy's. Version 2 drops `repo_path`. Workflow, the CI gate and Scope's claim check read versions 1 and 2; `start`, `relocate` and every other write produce version 2. `schemas/checkpoint-v1.schema.json` accepts both and refuses `repo_path` on version 2.
- Removed `worker_brief.project_result` and `project_usage` (used only by a test).
- Path containment for recorded labels checks each existing component with `lstat` and resolves fully at any symlink, junction or name Windows rewrites, instead of resolving every label. `..`, absolute, drive and UNC labels are still refused.
- `decisions.py`, `task_issues.py` and `ci_evidence.py` call `gh` through the shared `sanduq_gh.py`. Error codes and messages are unchanged; a missing `gh` is now reported with them instead of a traceback. A GET in `decisions.py` and `task_issues.py` is retried once after a 5xx or a timeout; writes and CI evidence downloads never are. `decisions.py` reaches Scope's GitHub client through `sanduq_scope_github.py` and no longer loads `scope.py`.
- One git runner (`workflow.run_git`) and one file SHA-256 helper (`execution_tools.sha256_file`) inside the package. Digests are unchanged.
- Internal: `workflow.py` is split into modules (`wf_core.py`, `wf_identity.py`, `wf_fingerprints.py`, `wf_policy.py`, `wf_health.py`, `wf_receipts.py`). Every name is still importable from `workflow`; behaviour is unchanged.

### Migration

- Checkpoints from 1.17 and earlier (version 1) load unchanged. The first command that writes one (a claim, `complete`, `migrate`, `relocate`) rewrites it as version 2 without `repo_path`. Nothing to run.
- Update Scope together with Workflow: an older Scope does not see an existing-feature claim in a version-2 checkpoint.
- Workflow 1.17 and earlier cannot read a version-2 checkpoint (`WORKFLOW_START_REQUIRED`). Do not downgrade Workflow after the first write.

## [1.17.1] - 2026-10-21

Fixes from the review of round 4 (PR #101).

- The packaged `sanduq_remote.py` gains `origin_url(..., resolve=True)` for Scope and Project. Workflow itself still reads the raw `remote.origin.url`, so its repository identity is unchanged.

## [1.17.0] - 2026-10-21

Optimization round 4. No renames.

- `reconcile` accepts an owned hook that Spec Kit (`extension add`/`update`) or Memory's installer registered again with `enabled: true`: apply disables it again and journals the new entry; restore keeps it. A disabled entry edited after reconcile is still refused with `HOOK_CHANGED_SINCE_RECONCILE`. Re-enabling an owned hook by hand is reversed by the next reconcile.
- One hook-ownership rule (`reconcile.managed_hook`) for reconcile and doctor. Doctor's `DUPLICATE_STAGE_OWNER` names the reconcile command.
- `sync-amend` and `migrate` find a legacy receipt's recorded bytes in a CRLF commit of the Project Sync state file (the history hash is CRLF-folded like the receipt's).
- The `gh` calls in `task_issues.py` (120 s) and `ci_evidence.py` (300 s) time out with their existing errors (`GITHUB_API_FAILED`, the evidence error).
- The GitHub remote reading and the PR closing-reference lint come from the shared `sanduq_remote.py` and `sanduq_pr_lint.py`; `workflow.py` and `execution_tools.py` re-export the old names.
- New descriptions for `speckit.workflow.finalize` and `speckit.workflow.status`.
- In a managed project `reconcile` also disables Memory's `speckit.memory.session` (before Specify) and `speckit.memory.prepare` (after Implement); `speckit.memory.impact` stays. The runtime does both steps: every claim runs the Memory session handoff, under the dispatch lock it already holds (one `archive.py pending`, about 0.4 s; the model-supplied `session_id` is not trusted to skip it). Any `blocked` result, or Memory work to dispatch first, comes back instead of a stage (`status: memory_blocked` or `memory_dispatch`, with `memory_handoff`); the run is recorded in the checkpoint (`memory_session`) only after it succeeded. Execute's handoff queues with the Memory policy's `default_checks`; the prepare hook's early `archive.py preflight` no longer runs at Implement (verify and archive still run it). The handoff reads `policy` and `policy_hash` from Memory's `pending` when it carries them (one helper process fewer).
- `scripts/progress_shim.py` is removed. With Progress installed and enabled, a legacy `scripts/progress.py` call writes nothing, exits 2 and prints one `error PROGRESS_INSTALLED: ...` line naming the Progress command to use. Without Progress, or with it disabled, the legacy reporter runs as before. `progress_bridge.status` (the v2 projection reader) is removed with it.
- `status` carries Progress's one text status line as `progress_status` (no v2 projection); the dispatcher no longer runs `progress.py status` itself.
- A claim reuses a green delegation health probe for up to an hour (`.specify/workflow/runtime/delegation-health.json`), while the host, scope, driver copy and the `node`, `codex` and `claude` executables are unchanged. A red result is never kept; a driver start failure drops it; `doctor` always probes. Measured here: 2.1 to 2.8 s for a probe, 0.05 to 0.07 s for a hit.
- The recovery for a pre-1.16.0 raw hash of the Project Sync state names `sync-amend` first. Its rules moved from `dispatcher-operations.md` to `recovery.md` (read on drift).
- `doctor` and `status` warn `PROGRESS_HOOKS_DOUBLE_WIRED` when `progress.hook_wiring: native` and a host file also holds Spec Kit's `speckit.progress.hook` entry, and name `install.py --apply`.
- `setup-and-updates.md` names the policy values that change nothing today. Dead code removed: `clear_caches`, `scope_decision`.
- The Brainstorm overlay states the one question limit (`clarification.max_questions_per_round`) instead of "no question count limit".
- Install, upgrade and `host --use` keep only the three newest backup zips across `installs/`, `upgrades/` and `hosts/` after a successful apply. `before.json`, `result.json` and alias backups stay. A failed apply deletes nothing. The apply result reports `backups: {zips, bytes}`; an explicit `doctor` reports them too.
- The branch-rule check in the installer times out after 60 s with `CI_BRANCH_RULE_INSPECTION_FAILED`.
- Install and upgrade refuse while a Memory archive run is active (`MEMORY_ARCHIVE_ACTIVE`) and name the command that resumes it.
- Install no longer refuses an unedited `documentation-gates.yml` rendered from an earlier Assure template (`LEGACY_CI_HAS_LOCAL_EDITS`); it is removed as before.
- Install and `host --use` no longer fail after Spec Kit or Memory registered an owned hook again.
- `project-defaults` also returns `statuses`, the exact column names doctor requires, so Project init can create the missing ones.
- `dispatcher-operations.md` says to write the usage JSON under `.specify/workflow/runtime/`: Windows Python cannot open Git Bash's `/tmp`.
- `stage-plan.md` says source files that Execute will change are not Plan inputs (or are `consulted`), so Execute's completion no longer fails once with `UPSTREAM_INPUT_CHANGED_DURING_STAGE` on them.
- Workflow records the exclude lines it writes for its runtime files in `.git/info/sanduq-runtime.json` (key `workflow`), so Memory can tell them from feature content.

### Migration

- Older backup zips are deleted on the next successful apply after this release (not on the upgrade into it). Copy any you still want out of `.specify/workflow/backups/` first.
- Finish or roll back an active Memory archive run before upgrading.
- Upgrade Memory first, then Workflow. Memory's approval hash changed format: run `speckit.memory.enable` once after the upgrade. Queue entries from before keep their `enabled_at` and `pending` reports them blocked with the fix; they are never re-stamped.
- The upgrade's `reconcile --apply` sets `enabled: false` on Memory's `session` and `prepare` hooks. A project that adds Memory after Workflow now also needs `reconcile --apply`; doctor names it (`DUPLICATE_STAGE_OWNER: ...; run "python .specify/extensions/workflow/scripts/reconcile.py --apply"`). Re-enabling an owned hook by hand is undone by the next reconcile.
- A claim can now stop on a Memory blocker (an interrupted archive run, a busy writer, a missing Memory command) and return `memory_handoff` instead of a stage. Run its actions, then claim again. Do not run `memory-handoff --transition session` before each claim any more.
- Prompts or scripts that call `.specify/extensions/workflow/scripts/progress.py init|task|usage|sync|phase|pr|event` while Progress is installed now get exit 2 and the Progress command to use. Switch them to `.specify/extensions/progress/scripts/progress.py` (see `references/reporting.md`).

## [1.16.0] - 2026-10-20

Fixes for issue #99 (finalization loops). New subcommands `project-sync` and `sync-amend`; the claim's `project_sync.command` changes.

- Receipts fingerprint the configured Project Sync state file (`stateFile`, under `.specify/`) as `sync-binding:v1:<sha256>` of the bound feature's entry without `status` and timestamp fields. A board status write no longer stales an earlier receipt or refuses a completion with `UPSTREAM_INPUT_CHANGED_DURING_STAGE`; a changed issue, node ID, item ID or sub-issue mapping, or a missing entry, still does, and other features' entries no longer count.
- A receipt recorded before 1.16.0 keeps its raw hash and is compared byte for byte. `migrate` and the new `workflow.py sync-amend --feature <f> --reason <text>` convert it once the entry matches `scope-source.json` and `workflow/task-issues.json` and the recorded bytes are found with only administrative fields changed; each conversion is an `administrative-amendment` record in the checkpoint's `lineage`. Clarify's permitted re-stamp keeps a raw hash raw.
- The claim prints `project_sync.command` as `workflow.py project-sync --feature <f> --phase <p>`. It runs the Project script with `--summary` and records `project_sync: {phase, state, at, summary}` (pending, then done or failed); done needs the entry to show the phase's configured status. A retry after a lost result does not repeat the remote write. `next` and `status` report a pending or failed sync with its retry command.
- `dispatcher-operations.md` and `stage-pr.md` state one finalization order (review, documentation, Ready, frozen candidate, gates, one PR, `complete`, `project-sync`, exact final head) and the bounded recovery before another semantic agent.
- Selected pins move to Assure 2.5.1 and User Manual 1.7.1.

## [1.15.0] - 2026-10-20

Optimization round 3. No policy key added; defaults unchanged.

- Each runtime command reads git once: an operation-scoped cache holds the origin, the root commit, git attributes and the source inventory and drops what a write could change. A full lifecycle runs 316 git subprocesses instead of 744; claim and complete are about twice as fast.
- The Execute claim carries the mode-neutral core plus only the text for its mode (lean or orchestrator, delegation on or off, Progress projection or the legacy reporter), 20 to 30 KB instead of 34.8 KB, and prints it in full once per mode and content (later claims name the files). Delegation text moved to `references/delegation.md`, read only when a claim routes through delegation.
- `claim` prints a `receipt_template`; `receipt-rules.md` no longer asks for inputs the runtime adds.
- `doctor` and `status` warn `GUARD_HOOK_UNAPPROVED` with the `/hooks` step when Codex has not approved the guard hook.
- The guard hook refuses, in a managed project, `gh pr create|edit` with an inline body and `gh pr create` without a linted `--body-file`. Codex users approve the changed hook once.
- The installer installs or removes Illustrate's post-write hook on every apply and upgrade, per `illustrate.hooks.self_check` (this removes the always-registered entries Illustrate 2.5.0 left), records it per host in `install-lock.json`, and rolls back both hosts' files on failure. It records the Progress hook's cost class with a hint at `progress.hook_wiring: native`, re-adds presets only when they changed, and installs only the runtime part of delegate-task.
- Thirteen descriptions shortened to 1,995 characters in total.
- Required pins: Scope 1.9.0, Project 2.4.0, PR 4.4.0, Illustrate 2.6.0; selected Assure 2.5.0 and User Manual 1.7.0; optional Progress 1.4.0.

## [1.14.0] - 2026-10-19

Optimization round 2 (cross-cutting parts). Every new key is opt-in.

- `claim` prints `project_sync: {"phase": ..., "command": "python .specify/extensions/project/scripts/project_sync.py --phase <phase> --summary"}` instead of `true`, from one stage-to-phase map, and `false` where no sync runs.
- `validate_policy` accepts `progress: {hook_wiring: speckit | native, post_tool_matcher: <regex>}` and `illustrate: {hooks: {self_check: <bool>}}`; absent keys keep today's behaviour.
- The installer applies `progress.hook_wiring: native` and `progress.post_tool_matcher` per host and records them in `install-lock.json`; `.codex/config.toml` joins the rollback set.
- The guard hook refuses `gh pr create|edit --body-file <f>` in a managed project when the lint receipt for `<f>` is missing or does not match, and `gh pr create` on the default branch. Codex users approve the changed hook once in `/hooks`.
- The PR stage reference points at PR 4.3.0's `pr_publish.py`, and reporting states the never-spawn rule once.
- Required pins: Scope 1.8.1, Project 2.3.0, PR 4.3.0, Illustrate 2.5.0; selected Assure 2.4.0 and User Manual 1.6.0; optional Progress 1.3.0.

## [1.13.1] - 2026-10-19

Fixes for issue #94 (the shipped workflow gate in CI). Rendered CI files are tracked in `install-lock.json`; an upgrade re-renders them.

- Evidence snapshots validate in a fresh checkout: a git record whose local retention ref (`refs/sanduq/evidence/*`) is absent or points elsewhere is accepted when its commit is an ancestor of `HEAD`; the blob and SHA-256 checks are unchanged. Before, the gate refused every feature that had recorded an evidence snapshot, because the refs are never pushed.
- `workflow-gates.yml`: when the project's linux runner set is not GitHub-hosted, the job carries `if: github.event.pull_request.head.repo.full_name == github.repository` (new `self_hosted` flag in `sanduq_ci.py`), so a fork pull request never runs on a self-hosted runner. The base-ref fetch takes the ref through `env` with an explicit refspec instead of an expression inside `run`. `actions/checkout` is pinned to v4.3.0 and `actions/setup-python` to v5.6.0 by commit, with the version in a comment.
- Selected pins move to Assure 2.3.4 and User Manual 1.5.4, whose templates carry the same guard and pins.

## [1.13.0] - 2026-10-18

Front-half rebuild. Every item below is opt-in through `.specify/workflow.yml` unless it says otherwise; an absent key keeps the 1.12 behaviour. Measured on the scripted small feature in `docs/internal/benchmarks/`.

- Profiles (`profiles: {enabled, lite: {max_score: 3}, standard: {max_score: 8}}`). The Scope receipt records `effort_score`; the first Plan claim freezes `profile: {tier, score, fixed_at}` in the checkpoint. `standard` merges Tasks into Plan (the Plan claim returns `merged: ['tasks']` and its receipt lists `tasks.md`) and runs Analyze as the runtime stage `workflow:lint`; `lite` also skips the QA and User Manual stages and treats research, data model, quickstart and contracts as optional inputs. Skipped stages are stored as `skipped: {stage: reason}` and logged as lifecycle `skipped` events. `lean_execution` is on by default for lite and standard unless the policy sets it false.
- `workflow:lint` (`scripts/lint.py --feature <f> [--tier] [--json] [--record --token <t>]`): requirement coverage, task ids, dependency cycles, 200-character headlines, leftover `[NEEDS CLARIFICATION`, unreferenced contracts and the `artifacts.budgets` byte budgets (`enforce: lite-standard | all | warn`). `--record` completes the Analyze claim when the lint passes; `needs_model_analyze` escalates to a model Analyze whose receipt carries `command: speckit.analyze`.
- `claim` prints `reference_text` (the stage reference), `side_effects`, `project_sync`, and on a merged Plan `merged` and `profile`; it omits `baseline` unless `--verbose`. `complete` prints `{ok, stage, next}` unless `--verbose`. `status --feature` works without `--runs` and lists the profile, skipped stages and the next action.
- `revalidate-upstream --feature <f> --through <stage> [--receipt <file>] [--plan]` re-records every stale receipt from Specify through `<stage>` in one locked operation and one lifecycle episode (`revalidate-upstream` events). Whitespace-only changes to Markdown inputs are re-stamped without a receipt (receipts now also store `text_fingerprints`).
- Side effects replace the permitted-change list: Clarify may change `spec.md`, `.specify/project-sync-state.json` and `checklists/*.md`; `claim` prints the globs.
- Verify, Review and Ready receipts keep their source inventory in `workflow/inventory/<stage>-<claim>.json` (`source_inventory: {path, sha256}`); inline `source_fingerprints` stay readable. `resume-prompt.md` now says to run `workflow.py status`, never to read the checkpoint, and `handoff.md` rewrites only the block between `<!-- sanduq-handoff:begin -->` and `<!-- sanduq-handoff:end -->`.
- `claim` reuses a green `doctor --project` result cached in `.specify/workflow/runtime/doctor-cache.json` for 600 s while the package digest, policy digest and registration files are unchanged; the skill inventory and line-ending scan run only in the explicit `doctor`.
- A spec.md that starts with `<!-- sanduq-scope:rendered <sha256> -->` (written by Scope 1.8.0 `render-spec`) makes the Specify claim `mode: bind-only`: bind and record, no model pass.
- `issue_sync.taskstoissues: phase-lazy`: `task_issues.py --phase "<heading>"` publishes one phase; the Tasks-to-Issues receipt records `lazy: true` after the first phase; `--sync-states --allow-unpublished` (automatic under phase-lazy) skips tasks without an issue; Ready still requires every task mapped.
- `project_sync.points` (default: the six existing points) selects where the dispatcher runs Project Sync; `clarification.max_questions_per_round`, `clarification.in_session_first_round` and `scope.board_cache_seconds` are validated here and read by Scope 1.8.0.
- Guard hook for Claude Code and Codex (`hooks/hooks.json`, `hooks/guard.py`), installed into `.claude/settings.json` and `.codex/hooks.json` by the installer: `git add -A`, `git add .` and `git stash` are refused unless `SANDUQ_ROLE=coordinator`; `delegate_dispatch.py accept|reassign|adopt|trust-reset` are refused in a worker or subagent context. Codex runs it after approval in `/hooks`.
- Worker and reviewer roles (`assets/roles/*.yml`) render to `.claude/agents/sanduq-<role>.md` and `.codex/agents/sanduq-<role>.toml`; `worker-brief` emits a task card of at most 1.5 KB when the role files exist.
- `install.py --with-aliases` / `--without-aliases`: the `speckit-scope` and `speckit-superpowers-bridge` alias skills are opt-in for new installs; the five hook-only Scope skills get `user-invocable: false` on Claude Code. `doctor` warns `INSTRUCTION_FILES_DUPLICATED` when CLAUDE.md and AGENTS.md coexist without an import.
- Instruction text: the dispatcher skill is `speckit-workflow` (3.6 KB core); references deduplicated (`scope-binding.md`, `superspec-checkpoints.md`, `recovery.md`, `setup-and-updates.md`, `evidence-capture.md`), review identifiers removed, every stage reference self-sufficient; every command and overlay has a what, when and trigger description. Preset 1.2.0 composes Clarify and SuperSpec Brainstorm with `strategy: replace`.
- `workflow.write` retries `os.replace` briefly on Windows `PermissionError`.
- Requires Scope 1.8.0.

## [1.12.0] - 2026-10-18

- Lifecycle events carry two more ids. `accepted` writes `candidate_run_id`, the stage attempt the exact-claim check validated (`null` without a delegation route), while `delegation_run_ids` stays claim membership. The `invalidated` events a claim writes for the receipts it removes have `claim_id` and `episode_id` `null` and name the new claim in `caused_by_claim_id`. Every other event writes both as `null`. `paused` with `stage: null` is a valid feature-level event.
- The lifecycle log is never read, repaired or appended through a symbolic link or reparse point, on the file or its `workflow/` folder. The write is refused with `LIFECYCLE_LOG_UNSAFE` and the events stay queued in the checkpoint.
- A stored receipt carries `claim_id`, and a recovery record carries `claim.claim_id`. The `accepted` and `recovered` events use the receipt's `completed_at` and the recovery's `at` as their own `at`, so a reader can join them exactly.
- `rejected-completion` also carries `candidate_run_id` when the refusal came after the exact-claim delegation check passed; it is `null` at or before that check.
- A lifecycle log whose last record lacks only its newline keeps that record and terminates it before the replay is deduplicated. `complete` also records a rejection for `ValueError` (delegation and verification-plan errors), not only `WorkflowError`.
- Progress capability detection reads `extension.yml`, else the package `VERSION`, else probes `lane new --workstream` once per process. The `--schema v2` retry happens only for an unknown version and only when the failure names the flag.
- `next_action` is evaluated once per command: `save` hands its result to the `next` call that follows.
- Lifecycle events: `specs/<feature>/workflow/lifecycle.jsonl` records `claim`, `resume`, `accepted`, `rejected-completion`, `recovered`, `paused`, `invalidated`, `revalidated` and `revalidation-stale`. Each record carries `workflow_run_id`, `generation`, `stage`, `episode_id`, `claim_id`, `delegation_run_ids` and a short `reason`. `claim_id` is a one-way hash of the claim token, never the token. Receipts a claim removes are recorded as `invalidated` before they are deleted; `migrate`, `refresh` and changed amendments record the stages they invalidate.
- A completion that fails validation after the claim is authenticated is recorded as `rejected-completion`. The claim stays active, nothing is accepted, and the CLI prints the same error and exits 1 as before.
- Events are queued in the checkpoint (`lifecycle_outbox`) with the state change and appended under the feature lock. An interrupted append is replayed on the next write and deduplicated by `event_id`. `lifecycle.read_events` tolerates a torn final line and the next append repairs it.
- The checkpoint stores `stage_plan` (the selected, policy-filtered stage order) and `next_action` (Workflow's own next evaluation with `evaluated_at` and `generation`, either an active claim or the next stage). The active claim also records `claim_id`.
- Delegation attempts record `intent_id`, `claim_id` (stage attempts) and `replaces_run_id` next to the existing `parent_run_id`.
- Reporting: on a Codex worktree whose hooks are not approved, the coordinator reports its own model and effort with `progress bind --host codex --model <m> --effort <e>` (needs Progress 1.2.0 or later). From Progress 1.2.0 the `progress.py` forwarder creates lanes with `--workstream`; older Progress versions get no flag.
- Progress compatibility: the bridge reads `progress status --json --schema v2`, so Workflow keeps the v2 projection when Progress 1.2.0 defaults to v3. A Progress known to be older than 1.2.0 is called without it; for an unknown version, a usage-error rejection (exit 2) is retried once without the flag.
- Requires Scope 1.7.0, which writes the clarification records Progress 1.2.0 reads.
- The vendored `delegate-task` is re-pinned to `agent-tools-v1.4.2` without file changes, and Progress 1.2.0 is the optional
  Progress version.

## [1.11.2] - 2026-10-18

- Force UTF-8 only for Memory helper I/O so Unicode recovery journals remain readable under Windows legacy code pages.
- Queue Memory work after accepted Execute completion for both Core and SuperSpec. Repeated handoffs preserve existing queue entries; missing dependencies, disabled approval and check coverage failures keep their actual pending or blocked reason.
- Add one local handoff for session entry and verified post-merge follow-up. It binds the exact feature, repository, PR and target, prioritizes active recovery and returns registered Memory actions for verification, synthesis and review. Product receipts and `pr_open` keep their existing meaning.
- The QA Document stage may refresh the generated `.github/memory/project-memory.md` inventory. The runtime records the old and new hashes in lineage and advances the earlier receipts' source fingerprints instead of failing with `UPSTREAM_INPUT_CHANGED_DURING_STAGE`.
- Pin the selected QA and User Manual dependencies to Assure 2.3.3 and User Manual 1.5.3. Their packages ship the reviewed shared freshness helper, which excludes generated Progress reports (`specs/*/progress/`, `.specify/progress/`) from QA and manual freshness inputs while preserving true source changes. Workflow and Memory do not ship that helper.

## [1.11.1] - 2026-10-17

- Reporting instructions: lifecycle stage runs (scope, specify, clarify...) are recorded by the delegation ledger and get no `progress lane` call. `progress lane` is only for real Execute workstreams, once per workstream, and a new worker updates that lane's owner. The legacy shim reuses the open lane that already carries a task and updates its owner instead of adding a lane per worker.
- The vendored `delegate-task` is re-pinned to `agent-tools-v1.3.1`. Check batches resolve every launcher before starting; on Linux, containment falls back to a `/proc/*/stat` scan when the kernel has no children file; on Windows, environment overrides match names without regard to case, and a check cancelled before launch starts nothing.

## [1.11.0] - 2026-10-17

- Immutable verification attempts and validated recoverable evidence snapshots.
- Use shared check-input fingerprints and retain legacy evidence compatibility.
- Stage the canonical delegate-task native runner, bounded collection and startup diagnostics from agent-tools 1.3.0.

## [1.10.3] - 2026-10-16

- On Codex, `progress_bridge.py mode` counts the Progress hooks as active only when Codex will run them: the project is `trusted` in `$CODEX_HOME/config.toml` (or `~/.codex/config.toml`) and a `[hooks.state."<config file>:<event>:<group>:<hook>"]` entry with a `trusted_hash` exists for the hook. Registered but unapproved hooks select `refresh` instead of `projection`; the text line becomes `reporting: refresh (codex hooks not approved)` and `--json` adds `reason`. The hash is not verified, so a hook changed after approval is not detected. User-level `hooks.json` hooks follow the same rule. Claude is unchanged.

## [1.10.2] - 2026-10-16

- Offer Progress 1.1.0 as the optional Progress version. It vendors the portable `progress-report` skill and adds plan mode; the Workflow bridge and the `progress.py` forwarding are unchanged. The vendored `delegate-task` is re-pinned to `agent-tools-v1.2.0` without file changes.

## [1.10.1] - 2026-10-15

- `progress_bridge.py mode` detects the active host (`--host claude|codex`, else from the environment) without starting a Progress process. An unknown host selects `refresh`. A Progress that the registry disables selects `legacy`.
- Remove the unused Progress status call and the `extensions.yml` parser from the bridge.
- A forwarded legacy `progress.py` call spawns fewer Progress subprocesses.
- Lean `execution_tools.py progress` uses the Progress run collector only when it covers every run under the requested root.

## [1.10.0] - 2026-10-15

- Add opt-in lean execution: the coordinator owns lifecycle mechanics, coding review waits for completed implementation/testing, and retries require bounded correction evidence. Existing projects keep their current behavior until enabled.
- Bind verification reuse to selected commands, source/fixture bytes, environment and passing evidence. Add aggregate preflight, bounded worker briefs and per-harness progress from normalized run records.
- Expose initial/revalidation Scope commands and validate bound PR closing references. Preserve explicit model allowlists, claim ownership and unknown usage.
- Make the optional Progress extension the preferred way to report. One reference, `references/reporting.md`, now decides the mode: `projection` (Progress collects automatically; the coordinator records only lanes, blockers and notes), `refresh` (Progress installed without automatic collection) or `legacy` (Progress absent, the existing `progress.py` calls unchanged). `scripts/progress_bridge.py mode` prints the mode. In every mode no agent is spawned, retained, messaged or polled solely for reporting; the rules to keep an orchestration agent alive after Execute to update the report, to reserve capacity for it and to re-verify the report page are removed. The orchestration agent stays where it does real scheduling and integration work.
- `scripts/progress.py` forwards its subcommands to the Progress CLI when Progress is installed (`init`, `task`, `event`, `phase`, `usage`, `sync`, `pr`), writes no legacy state, and keeps the `--summary` line. Usage is recorded as a legacy attempt with its explicit log path, time window and reported counters. `--json` and `init --title` have no faithful mapping and fail with a compatibility error. Without Progress the legacy reporter runs as before.
- Lean `execution_tools.py progress` and `workflow.py status --runs` read normalized runs from `progress runs --json` (schema `progress.runs.v1`) when Progress is installed, and use their own code otherwise. Elapsed time is wall time, a stalled run is a heuristic, and a harness's terminal status is not acceptance, as before.
- `install.py --with progress` (and `upgrade.py --with progress`) installs Progress as an optional extension offered in `dependencies.json`; an installed Progress is kept in step. It is never required. `reconcile.py` leaves Progress hooks and events enabled.

## [1.9.5] - 2026-10-11

- Receipts that label files with Windows separators (`dir\file`) now read the real file on every
  platform. Stored labels and hashes are kept as written; only the path read is made portable.
  Labels that are absolute, drive-lettered, UNC, empty, contain `..` or resolve outside the project
  are refused. A consulted label that is the backslash form of a required input stays a dependency.
  New receipts store forward-slash inputs, evidence and input roles, and two role entries for one
  file must match or the receipt is refused. The CI index check resolves the same labels
  against Git's file names. Staleness, task lineage and claim checks are unchanged.
- `delegate_dispatch.py start` accepts a paired `--harness` and `--model`. The pair must exactly
  match a candidate of the route already resolved for the work (a task override, the configured
  route or the claim's frozen stage snapshot). An unpaired, unknown, mismatched or unavailable
  choice is refused before any ledger intent or driver launch, and there is no fallback after an
  explicit choice: the attempt keeps only that candidate, is marked `pinned`, and neither an
  automatic retry nor `reassign` leaves it. The ledger records an `explicit-pin` route decision
  with the original candidate index. Without the pair the default first-candidate selection and
  fallback order are unchanged. The choice never widens a role's model allowlist; it only picks
  among candidates that were already eligible.
- A stage start whose `--type` differs from the stage's real work type is refused
  (`DELEGATION_STAGE_TYPE_MISMATCH`) instead of silently ignored; the identical type is accepted.

## [1.9.4] - 2026-10-11

- `dependencies.json` pins Illustrate 2.4.1 (exports keep page styles, so diagrams no longer render
  black). No workflow behaviour change.

## [1.9.3] - 2026-10-10

- Issue decisions are selectable. `decisions.py ask` posts a native GitHub task list, every box
  unticked, with an optional `(Recommended)` suffix (`--recommended B`). `--mode single` (default)
  needs exactly one tick; `--mode multiple` accepts one or more. A tick is read without a new
  comment and records no author, because GitHub does not say who edited the box. Typed replies
  (`SD1: B`, or `SD1: A, C` for multiple) still work, and a tick that disagrees with a reply is a
  conflict. Any other edit to a question (choice text, markers, recommendation) fails closed.
- `decisions.py upgrade-questions` rewrites legacy `- A.` question comments into the selectable
  format. It keeps IDs, options, request digests and every real reply, never ticks a box, and is
  safe to repeat. Legacy v1 questions and replies are still read unchanged.
- A pending or conflicting decision parks a mapped Backlog or Feature Specification issue in the
  mapped Need Clarifications status. Once nothing is pending, the issue returns to the mapped
  Feature Specification only if Decisions parked it and the project's
  `clarification.resume_on_reinvoke` is `reread-answers`. Any other status is left alone, so an
  advanced issue never regresses. `decisions.lifecycle_status: false` opts out. The Decision
  field is still synced as before.
- Decision commands bind a pre-Specify checkpoint to its issue without a `scope-source.json` or an
  active claim. Only valid paused pre-Specify work may read across branches; active or bound work
  requires its checkpoint branch and current executor token and session. Foreign issue or feature
  ledgers fail closed. The dispatcher passes verified ownership on completion.
- Decision and lifecycle Project writes are reread remotely, with durable pre-write parking
  intents for interruption recovery, and use the shared Scope REST transport when GraphQL is
  exhausted.
- Pins Scope 1.6.1 (fresh issue-bound gate and verified REST fallback for Project operations);
  review it before installing.

## [1.9.2] - 2026-10-10

- `dependencies.json` pins Illustrate 2.4.0 (animated arrows, GIF export). No workflow behaviour change.

## [1.9.1] - 2026-10-10

- `dependencies.json` pins Illustrate 2.3.0 (animated SVG export). No workflow behaviour change.

## [1.9.0] - 2026-10-10

- The canonical source key is now `sanduq-source-key/1`. New receipts and CI plans use it;
  evidence recorded under the previous key version is still verified, and a plan is recomputed
  with the key version it declares. `source_key.source_keys()` returns a tree's key under every
  accepted version. Consumer CI that computes the key should move to the new version.
- Neutral wording and synthetic repositories in documentation and test fixtures.
- `dependencies.json` pins Scope 1.6.0, Illustrate 2.2.1 and User Manual 1.5.2. Scope 1.6.0 draws the
  dependency plan and clarification diagrams with Illustrate and requires it.
- The bundled Delegate Task driver is vendored from samykabu/sanduq-skills (agent-tools 1.1.2):
  Claude runs now report the model that did the work, not a side call.
- The 1,380-line README is split into a short guide and reference pages under `docs/workflow/`
  (stages, state files, schemas, runner policy, utilities, delegation, development). No content removed.
- `dependencies.json` pins Assure 2.3.2, PR 4.2.2 and Project 2.2.2 (documentation patches).

## [1.8.5] - 2026-10-06

- `dependencies.json` pins Illustrate 2.2.0 (44 diagram types, import, theme apply). No workflow
  behaviour change.

## [1.8.4] - 2026-10-06

- Link setup and complete usage examples from the package README; links work in installed copies.
- Pin the documentation patch releases of managed dependencies. Runtime behavior is unchanged.

## 1.8.3

- `dependencies.json` pins User Manual 1.5.0 (selectable MkDocs theme, RTL
  styling for non-Material themes, localized navigation). No workflow
  behaviour change.

## 1.8.2

- **spec-kit 1.1 compatibility, bundled preset.** The `workflow` preset (now 1.1.1)
  widens `requires.speckit_version` from `>=1.0.0,<1.1.0` to `>=1.0.0,<2.0.0`. 1.8.1
  widened only the extension manifest, so `install.py --apply` still failed on spec-kit
  1.1.x with `INSTALL_ROLLED_BACK: INSTALL_COMMAND_FAILED: specify preset add ...`.
  A new test keeps every bundled preset's range at least as wide as the extension's.

## 1.8.1

- **spec-kit 1.1 compatibility.** `requires.speckit_version` widens from
  `>=1.0.0,<1.1.0` to `>=1.0.0,<2.0.0`. The `<1.1.0` cap blocked
  `specify extension add workflow` on spec-kit 1.1.x with a Compatibility
  Error, although nothing in the extension depends on 1.0-only behaviour.
  Verified by installing 1.8.1 with `specify` 1.1.1.dev0.

## 1.8.0

- **Checkpoint identity design fix.** A checkpoint no longer hard-gates every
  command on the absolute `repo_path` it was started from, which failed
  `CHECKPOINT_IDENTITY_MISMATCH` on any other clone, worktree, instance,
  delegated worker or CI runner, with no supported fix. It now records a
  portable `repo_identity`: the normalised `origin` remote and/or the
  repository's root commit, chosen so a shallow CI checkout of the same
  origin still matches, and a root commit that is no longer the current
  deterministic pick (e.g. after `git merge --allow-unrelated-histories`
  adds an older one) is still accepted when it remains reachable from
  HEAD. `Run.load()` compares this portable identity *and* requires the
  checkpoint's bound issue to name this repository's own GitHub remote
  (the same binding `start` and the scope extension's `bound_claim`
  already require), resolved from any remote form (any scheme, an
  embedded token, with or without `.git`) and compared case-insensitively;
  without a GitHub remote to check that against, it is refused and pointed
  at `relocate`. When neither repository being compared is a shallow
  clone, the root commit must also match even when the remote does (a
  shared remote is still just local Git config, and this catches one
  simply copied into an unrelated clone); see the README's threat model
  for what this identity check does and does not defend against. A
  checkpoint copied from a genuinely different repository is still
  refused, whether legacy or new.
  - A legacy (pre-1.8.0) checkpoint that only has `repo_path` is adopted
    once both of those checks pass, only when it records a full-hex commit
    id (`head`, or a receipt `head`) reachable from this repository's HEAD
    (otherwise it is refused with an error naming `relocate
    --allow-history-change`), and is upgraded to `repo_identity` on its
    next write.
  - `repo_path` is still written (by `start`, the legacy-upgrade path and
    `relocate`) as the current absolute root, purely so a pre-1.8.0 reader
    does not `KeyError` on a checkpoint this version writes; nothing in
    this version reads or compares it. It will be removed once no
    supported release still needs it.
  - `schemas/checkpoint-v1.schema.json`: `repo_path` is no longer required
    (kept, optional); adds optional `repo_identity` (`remote`,
    `root_commit`, `shallow`) and `relocations[]`.
  - The scope extension's `bound_claim` runs the same identity gate
    (`verify_checkpoint_identity`) and no longer compares `repo_path`;
    this needs scope 1.5.0 (pinned in `dependencies.json`).
- **New `workflow.py relocate --feature <f> [--preview] --reason "<why>"`.**
  The explicit, logged rebind for a checkpoint whose identity legitimately
  moved (a renamed remote, a migrated org, or a fork). Preview reports the
  old and new identity without writing; applying appends a `relocations[]`
  entry with actor, time, reason and both identities. Every receipt is
  preserved and no stage is invalidated.
  - Refuses a branch mismatch unless `--allow-branch-rebind` is also
    passed (logged either way); refuses when the checkpoint's bound issue
    names a different GitHub repository than this one now resolves to,
    unless `--allow-repository-rename` is also passed (logged either way).
    This is the check that stops `relocate` itself from laundering a
    foreign checkpoint into an unrelated repository.
  - Blocks a checkpoint whose recorded root history is not this
    repository's unless `--allow-history-change` is passed (recorded as
    `history_changed` in the `relocations[]` entry), and requires a
    resolved GitHub remote to apply.
  - A repository change never rebinds the issue automatically: it stays
    blocked until `--keep-issue-number` (a rename/transfer only, never a
    fork) or `--issue <owner/repo#n>` (naming the exact new issue) says
    which; both are refused when the repository did not change
    (`RELOCATE_ISSUE_NOT_APPLICABLE`). `scope-source.json` is rebound in
    the same locked write as the checkpoint (and restored if the
    checkpoint write fails), so a later `start` for the rebound issue does
    not fail `FEATURE_BINDING_MISMATCH` against a source file still naming
    the old repository.
  - Refuses inside a delegated worker or orchestrator context, and reaches
    the checkpoint directly, bypassing the identity gate it exists to get
    past, recomputing everything from a fresh read taken under the lock
    rather than trusting values read before it.
- `normalize_remote_url` (and `github_repository`, built on it) now parses
  a scheme URL with `urllib.parse` instead of an ad-hoc regex, fixing a
  real collision (an SSH URL's explicit port, e.g. `ssh://host:22/team/app`,
  no longer folds into the same identity as an unrelated path that happens
  to start with a numeric segment, e.g. `https://host/22/team/app`) and a
  URL-confusion risk (a malformed remote, e.g. a non-numeric port, now
  falls back to an opaque, unfolded identity instead of risking a
  misparse), and accepts every valid GitHub remote form (`ssh://`, an
  embedded token). A port equal to its scheme's well-known default (22 for
  `ssh`, 443 for `https`) carries no identity and is folded away. A
  local-path remote (a bare path, `file://`, or a Windows drive path) is
  never case-folded, except a Windows drive letter itself (`C:`/`c:`),
  which genuinely is case-insensitive.
- The installer enforces a sibling package's `requires.extensions` entry
  naming `workflow` (Spec Kit itself only validates that `requires` is a
  mapping): `install.py` refuses a staged or already-installed package whose
  manifest needs a workflow version outside this installer's own, with
  `WORKFLOW_VERSION_UNSUPPORTED`. Scope 1.5.0 declares `workflow
  >=1.8.0,<2.0.0`. A package fetched from a release URL is checked once it is
  installed, on the next install or upgrade run.
- **B13 — five new utility skills.** Five new entry points, none a claimed
  stage, each shipped as a command plus a runtime script with unit tests:
  - `speckit-workflow-verify-affected` (`verify_affected.py`): runs a
    feature's affected lanes locally, reusing the existing
    `ci.gate.affected_command` classify contract and a new optional
    `ci.gate.verify_command` (a project-local runner read
    `{"lanes": [...], "results_path": "<path>"}` on stdin), into the same
    results.json shape the project's own CI tier writes. It diffs the
    actual working tree (staged, unstaged and untracked paths, not only
    `base_ref..HEAD`); validates its results (every requested lane present
    and passed, else `ok: false` with `missing_lanes`/`failed_lanes`, exit
    1); stamps them `source: "local"`/`ci_grade: false`, so they must
    never be recorded as Verify `ci_evidence`; confines `--results` inside
    the repository; and kills the whole process tree of a timed-out verify
    command or of one whose output passes `HARD_OUTPUT_LIMIT` (10x
    `OUTPUT_CAP`) while it runs, with output capped.
  - `speckit-workflow-ci-report` (`ci_report.py`): summarizes the last N
    runs of a CI workflow into a leg/lane/wall-clock-span table, fixed vs
    test time (from `--fixed-job`) and cancelled-run counts, reading only
    through the GitHub REST API (`ci_evidence.GhClient`). It paginates past
    GitHub's 100-per-page cap for both runs and jobs (with a constant
    `per_page` across a page sequence) and URL-encodes `--branch`; the
    span field is named `wall_clock_span_seconds`, not "critical path".
  - `speckit-workflow-gate-explain` (`gate_explain.py`): explains a
    `STALE_RECEIPT` gate failure with the exact `recovery_recipe` the gate
    itself would print, and offers `--auto-fix` only for drift the existing
    `explicit-drift` classification already confines to a receipt's own
    `evidence` paths, never a dependency or a source/lane finding. The fix
    runs `Run.amend` (a checked re-hash); nothing is re-stamped without a
    check (standing rule 4), and `--reason` is never fabricated.
    `--auto-fix` requires `--assessment` (no default), excludes any
    drifted path that is a declared input or a required core artifact (a
    path can be both evidence and input, and amending it under `unchanged`
    would launder a real change), rechecks eligibility against the live
    receipt, and re-validates every eligible path before amending any
    (all-or-nothing). `Run.amend` gains an `evidence_only` guard evaluated
    under its lock.
  - `speckit-workflow-worker-brief` (`worker_brief.py`): generates a 3-5 KB
    brief for one task: its exact line, owned paths, verbatim requirement
    lines, a contract excerpt, the turn budget (T0) and forbidden-commands
    paragraph (S6) and the ten-line result template (T7), reading the
    last three live from `execution-assign.md`/`execution-report.md`
    instead of a copy that could drift from them. It reuses
    `delegate_dispatch.NO_DISPATCHER_COMMANDS`/`QA_COLLECT_ADDENDUM`
    rather than a second S6 paragraph, includes the F1/F2/F3/T8 rules,
    drops `qa_collect` from `--class` (light-tier only behind a `[Collect]`
    task marker), enforces its target (drops the contract excerpt first,
    then reports `oversized: true`), refuses to write an oversized brief
    unless `--allow-oversized` is passed (its fixed text is trimmed so the
    heaviest `[Collect]` brief keeps every mandatory rule inside 5 KB), and
    builds its CLI JSON with `json.dumps` (a Windows path's backslashes
    broke hand-built strings).
  - `speckit-workflow-apply-pending` (`apply_pending.py`): applies
    `workflow/pending-artifact-updates.md` (F15) to the contracts,
    data-model and research files it targets, marking each entry `applied`
    or `rejected`, and reports which already-passed receipts the touched
    paths stale, with their recovery recipe. Every target is confined to
    `<feature>/contracts/**`, `data-model.md` or `research.md`: the lexical
    path is judged, absolute paths, `..` and any symlink or junction on the
    path are refused, and the pending file itself is contained. It
    accumulates replacements per file and writes each once, atomically,
    marking an entry applied only after its write succeeded, and a
    staleness-check failure is reported as `stale: null` + `stale_error`,
    never folded into an empty `[]`. `--apply` also refuses while a claim
    is active.
  - `gate_explain.py --auto-fix`, `apply_pending.py --apply` and
    `Run.amend` all refuse inside a delegated worker or orchestrator
    process (`SANDUQ_DELEGATED_RUN`/`SANDUQ_DELEGATED_ROLE`, reusing
    `delegate_dispatch.require_not_worker_context`).

  New optional policy key `ci.gate.verify_command`, validated by
  `sanduq_ci.py` and settable with `workflow.py ci --verify-command`, the
  same way as `affected_command`.

## 1.7.0

- **B7 — quiet output.** `task_issues.py` and `progress.py` gain `--summary`
  (one line: `ok`/`error` plus counts, e.g. `ok created=2 reused=5 total=7
  dry_run=0` or `ok done=3 total=8 pending=2 running=2 blocked=1`) and an
  explicit `--json`. `task_issues.py --json` matches the previous default
  output byte for byte; `progress.py --json` is new, since the previous
  default only ever printed the report path. `--summary` and `--json`
  together is rejected in both; default (no flag) behaviour and every exit
  code are unchanged, and an unhandled exception is reported under
  `--summary` as one `error <Type>: <message>` line instead of a raw
  traceback. `task_issues.py --sync-states` now runs once per phase
  boundary rather than once per task, and the dispatcher's own token usage
  is recorded with `progress.py usage --overhead dispatcher --agent <id>
  --collect claude --log <path>` at every phase commit.

- **B8 — dispatcher core split.** `skills/workflow/SKILL.md` (29 KB) is
  split into a core dispatcher (entry points, stage loop, receipt rules,
  <= 6 KB) plus one `skills/workflow/references/stage-<name>.md` per
  claimable stage; `claim` returns a `reference` field naming the exact
  file to read for the claimed stage. Cross-cutting detail moved to
  `references/dispatcher-operations.md`, `references/delegation-and-
  decisions.md` and `references/receipt-rules.md`; `references/
  execution.md` split into `references/execution-assign.md` (start/resume,
  assign work) and `references/execution-report.md` (report updates,
  finishing phases, delivery). This is a packaging change only: no rule was
  dropped and no script behaviour changed, verified by a test that diffs
  the pre-split files against the new set.

- **B10 — skill inventory in doctor.** `doctor --project` reports a
  `skill_inventory` block, one entry per **host session load** rather than
  a cross-host sum: `hosts.claude` (`~/.claude/skills` + project
  `.claude/skills` + installed plugin skills) and `hosts.codex`
  (`$CODEX_HOME`/`~/.codex` skills + `~/.agents/skills` + project
  `.agents/skills`), each with its own totals and same-host duplicates; a
  name shared between a claude root and a codex root is reported
  separately under `mirrors`, never double-counted. Doctor warns
  (non-blocking) `SKILL_INVENTORY_LARGE` past 200 skills or 40 KiB of a
  host's own combined description bytes, both overridable under
  `policy['skills']['inventory_thresholds']`. `claude_plugins` confines
  itself to the current project's plugin scope, honours
  `enabledPlugins`/`settings.local.json`, and requires every `installPath`
  to resolve inside `~/.claude/plugins`; anything rejected is listed under
  `claude_plugins.skipped_install_paths`. A scan failure is reported as
  `SKILL_INVENTORY_UNAVAILABLE`, never a doctor failure.

  **Upgrade note:** the home-override environment variable is renamed
  `SANDUQ_SKILLS_HOME` (was `SANDUQ_HOME`); update any script or CI job
  that set the old name.

- **B11 — execution protocol.** `references/execution-assign.md` and
  `references/execution-report.md` state the review's rules as concrete,
  checkable instructions: parallel worker spawns block and their results
  return to the orchestration agent, never the dispatcher; no agent ends
  its turn while it owns running background work; report only on a state
  change; a turn-budget table per task class with a planned hand-off at
  ~150K resident context; a fixed ten-line worker result; read a
  verification summary before raw reporter output; `git stash` and
  `git add -A`/`git add .` are forbidden for workers; a consumers checklist
  follows every fix.

- **B12 — delegation guard.** `qa` splits into `qa_author` (standard-tier
  authoring and analysis) and `qa_collect` (light-eligible: running an
  existing, fixed check and reporting its result). Coordination now
  defaults to `high`, never light: it claims and completes workflow stages
  and issues, not a cheap default. Discovery is never light. Routing to
  `qa_collect` is never a heuristic: only an explicit `[Collect]` task
  marker or a per-task override reaches it; `verify` always routes to
  `qa_author` unless `delegation.fixed_collection_commands.verify` names
  its resolved command exactly. A light-tier or `qa_collect` `start` must
  declare `--owned` itself; there is no silent whole-checkout default.

  A light-tier "successful" result is never taken on trust: `collect`
  marks it `unverified` unless the worker's own produced-file list is both
  inside the task's owned paths and among the paths the driver itself
  measured as changed; counts are accepted only from `accept`, never from
  a worker's own summary. New `delegate_dispatch.py accept --run-id <id>
  --command <acceptance command> --expect counts|files [--owned <path>]`
  runs that command with a bounded timeout and no shell, and resolves
  `unverified` to `successful` only when it exits `0` and its output
  satisfies the schema. The reporter-counts parser requires a real
  reporter's own framing (pytest, Jest, JUnit/Maven, Python unittest,
  dotnet test, node `--test`) and returns unparsed, never a guess, when two
  formats disagree.

  The ledger's trust state is tri-state: `'unverified-local'` (no local
  `.written` marker, as on a fresh clone or CI checkout) is a warning only;
  a genuine mismatch (`'untrusted'`) still refuses and is sticky until
  `delegate_dispatch.py trust-reset --feature <f> --reason "<text>"`, which
  is orchestrator-only and requires an existing tamper flag. This detects
  accidental and local tampering only; CI integrity still rests on review,
  not on this mechanism.

  `complete` and the Ready task gate both require the dispatcher's own
  ledger — never a receipt's self-report — to show the claimed stage's or
  task's latest delegated attempt as `successful`, with `claim_token`
  matching the exact claim being completed; a checked task with **no**
  attempt at all now also fails the gate.

  **Upgrade note:** a project that enables delegation mid-feature can no
  longer wave a batch of already-checked tasks through with a stage-wide
  flag or a self-certification command; adopt each already-checked task
  once instead, with `delegate_dispatch.py adopt --feature <f> --id <task>
  --command "<acceptance check>" --expect counts|files [--owned <path>]`,
  which runs the acceptance check itself and records a binding to the
  task's exact current content. `adopt` and `accept` run by the
  orchestrator are visible: the Ready gate emits a
  `DELEGATION_TASK_ADOPTED`/`DELEGATION_TASK_ACCEPTED` warning a reviewer
  must read, since neither has an independent dispatch to cross-check it
  against. `reassign` refuses an adopted attempt outright
  (`DELEGATION_REASSIGN_ADOPTED_UNSUPPORTED`); re-adopt with a corrected
  check, or `start` the task normally.

  **Upgrade note:** a stage attempt recorded before this release added
  `claim_token` has none and can never match a later claim's token, so
  `complete` refuses it as `DELEGATION_STAGE_NOT_VERIFIED` even if the
  attempt itself succeeded. Re-delegate the stage once
  (`delegate_dispatch.py start --id stage:<stage> --claim-token <token>`)
  under this release; this is a one-time cost per open, already-delegated
  stage claim.

  **Upgrade note:** legacy `qa` routes map to `qa_author` automatically. A
  pre-1.7 policy's single `qa` route keeps working, read in place as
  `qa_author`, with a fresh `qa_collect` route added; a legacy route with
  any light-tier candidate resets `qa_author` to the new standard default
  instead of inheriting it, so a legacy install never keeps routing
  authored QA work to the light tier.

  The delegated Execute stage is the one exception to "a worker cannot
  call back into the dispatcher": launching it sets
  `SANDUQ_DELEGATED_ROLE=orchestrator` (never `SANDUQ_DELEGATED_RUN`),
  under which `start`, `collect`, `accept`, `reassign`, `adopt`, `recover`
  and `abandon` are allowed only for a `T###` task of its own feature;
  every other stage identity, and any other feature, still refuses with
  `DELEGATION_ORCHESTRATOR_SCOPE`. The task workers it launches get an
  ordinary worker environment with the orchestrator's own scope variables
  stripped, so they never inherit it.

## 1.6.4

- Pin the released User Manual 1.3.3 in `dependencies.json`. User Manual 1.3.3
  drops the private preview artifact's `upload-artifact` retention from 14 days
  to 2: the Cloudflare preview workflow reads it once, right after the run, and
  14 days of ~20 MB copies per push had filled the org's artifact storage and
  was blocking every Bootstrap run. Workflow itself is unchanged; a project on
  1.6.3 that already carried the 2-day retention as a local edit (as the pilot project did)
  saw its installed workflow file marked `CI_WORKFLOW_STALE` because the
  template still rendered 14 days. Upgrading to 1.6.4 clears that.

## 1.6.3

- An alias file (`speckit-superpowers-bridge`, `speckit-scope` in `.agents/skills` or
  `.claude/skills`) is no longer classified by its frontmatter. 1.6.2 replaced any
  alias whose frontmatter `name` was the alias and whose `metadata.source` named an
  installed extension, whatever its body, so local instructions added under
  unchanged upstream frontmatter were lost on the next reinstall or
  `workflow.py host --use`. Now an existing alias is replaced silently only when the
  SHA-256 of its whole content (CRLF normalised) is the packaged alias, an accepted
  legacy hash, the hash in `install-lock.json` `aliases`, or exactly what Spec Kit
  generates for that command: Sanduq renders it with `specify integration use <host>`
  in a temporary copy of `.specify` and compares the full hash. Content Spec Kit
  writes during the same transaction is still replaced. Anything else is refused
  with `ALIAS_HAS_LOCAL_EDITS: <path>` before anything changes; `install.py` and
  `workflow.py host --use` previews list it.
- New `--replace-unrecognized-aliases` on `install.py`, `upgrade.py` and
  `workflow.py host --use`: backs each unrecognised alias up to
  `unrecognized-aliases/<path>` in the run's backup folder, then replaces it, and
  reports each path and backup under `replaced_unrecognized_aliases`.

## 1.6.2

- Installs and upgrades keep every installed integration. Spec Kit registers
  extension skills only for the default integration, so `specify extension add
  --force` removed the other host's skills on every `install.py`/`upgrade.py
  --apply`. The installer now re-registers each other Codex or Claude host in
  `.specify/integration.json` `installed_integrations` through
  `specify integration use`, restores the recorded default and its integration
  files byte for byte, re-applies the managed aliases to every host folder, and
  rolls back on `HOST_SKILLS_MISSING`, `HOST_OVERLAY_MISSING` or
  `ALIAS_NOT_RESTORED`.
- Managed aliases are judged for local edits by their content before the
  transaction, so upstream Bridge content that Spec Kit regenerates during it is
  replaced instead of failing with `ALIAS_HAS_LOCAL_EDITS`; a real local edit is
  still refused, now before anything changes during a host switch. An alias
  that holds the skill Spec Kit rendered for an installed extension (frontmatter
  `name` is the alias, `metadata.source` names that extension), as a bare
  `specify integration use` leaves it, is replaced rather than refused.
- New `workflow.py host [--use codex|claude] [--preview]`: reports host status,
  or switches the default host through `specify integration use`, re-registers
  incomplete hosts, restores the managed aliases, installs the delegate-task
  skill for the new host when delegation is enabled, verifies every host, runs
  doctor, rolls back on failure, and reports the dependency digest change and the
  exact `migrate` commands for each affected checkpoint. It refuses (and
  `--preview` reports) delegation policy that cannot route to the new host,
  without rewriting `.specify/workflow.yml`. `--preview` changes nothing.
- Doctor warns when a host other than the default is missing managed skills or
  aliases, naming `workflow.py host --use <default>` as the repair.
- `smoke_install.py --second-host <host>` exercises a two-integration project with
  the real Spec Kit CLI.

## 1.6.1

- A Verify receipt's `ci_evidence` is current only when it is the complete
  record `revalidate --stage verify` writes (`run_id` and `attempt` positive
  integers, `head` 40-hex and the receipt's head or a commit of it,
  `source_key` 64-hex, a non-empty `tier`, `lanes` and `required_lanes` lists
  of strings with `required_lanes` inside `lanes`, `conclusion: success`, an
  empty `lane_gap`). A hand-edited or partial record in the committed
  checkpoint no longer passes on defaults (fail closed).
- `ci_gate.py` always re-reads, through the REST API, every CI run a Verify
  receipt is accepted through, and fails closed when it cannot read it
  (`CI_EVIDENCE_UNREADABLE`), when no `ci.gate.verification_check` names the
  check to read it by (`CI_VERIFICATION_CHECK_UNSET`), or when the run no
  longer matches (`CI_EVIDENCE_REJECTED`). `--verify-ci-evidence` is still
  accepted and changes nothing. The shipped `workflow-gates.yml` gate job
  gains `permissions: actions: read` (with `contents` and `issues: read`) so
  its existing `GH_TOKEN` can read runs and artifacts.
- `revalidate --stage review --diff-reviewed <file>` binds the note to the
  exact diff: besides `Diff reviewed: <review head>..<HEAD>` and
  `Blocking findings: 0` it requires `Diff sha256: <hash>`, the SHA-256 of the
  bytes of `git -c core.quotePath=true diff-tree -r -p --binary --no-renames
  <review head> <HEAD> -- .` plus one `:(exclude)<prefix>` per source-key
  exclusion and `:(exclude,glob,icase)**/*.md`, and a non-empty `Reviewer:`
  line. A stale or wrong hash (`DIFF_REVIEW_HASH_MISMATCH`), a missing hash
  (`DIFF_REVIEW_HASH_MISSING`) or reviewer (`DIFF_REVIEW_REVIEWER_MISSING`) is
  refused with the exact command to compute it; `diff_reviewed` records
  `diff_sha256` and `reviewer`.
- `revalidate --stage verify --check-run` accepts the plan artifact of the
  latest attempt at or before the checked one, instead of only the checked
  attempt's own. Re-running just the failed jobs of a verification run starts
  a new attempt that reuses the earlier plan job, so no plan artifact exists
  for the new attempt; `collect()` now takes that earlier attempt's plan and
  `validate()` requires `runAttempt` to name it. A run with no plan at any
  attempt still fails. Same rule as the consumer-side plan validator.
- `task_issues.py` no longer rejects a task whose title (`T### : description`)
  would exceed GitHub's 256-character issue title limit. The title is
  shortened to the headline (truncated to fit, with a trailing `...`) while
  the issue body still carries the full, untruncated description. Shortening
  is a pure function of the task ID and description, so a re-sync recomputes
  the same title and body every time and neither creates a duplicate issue
  nor keeps rewriting the body (F14).
- `ci_gate.py --check-index` now reports, for each evidence path missing from
  the Git index that Git itself ignores (e.g. a `*.log` match), the exact
  `git add -f <path>` recipe to recover it, alongside the existing
  `not_in_index`/`unstaged` report. It also warns (without failing the check)
  when a receipt's recorded fingerprints reference a path under another
  feature's `specs/` directory, surfaced as `index_warnings` on the gate
  result for that feature (F17).

## 1.6.0

- The shipped `workflow-gates.yml` gate job no longer clones every branch and
  tag in the remote just to compute one merge-base. `actions/checkout` now
  fetches only `${{ github.event.pull_request.commits + 1 }}` generations of
  the PR head (enough to reach the commit it forked from), and a new step
  fetches the PR base branch's full history explicitly; `ci_gate.py`'s
  `resolve_features()` still finds the same merge-base either way (G5).
- `workflow.py start` records the branch the feature branch was created from
  as `target_branch` in the checkpoint (via Git's `@{-1}` previous-checkout
  shorthand), best-effort and `null` when Git cannot determine it (a shallow
  or single-branch checkout, or no prior checkout in this reflog).
  `assure_state.py` and `manual_state.py` use it to default `--base-ref` to
  the feature's actual bound target instead of always assuming the origin
  HEAD default branch (F16).
- Receipt and checkpoint compatibility contract. `inputs` stays a list of
  paths; `receipt-v1.schema.json` gains the optional `input_roles`,
  `amendments`, `head`, `source_key`, `ci_evidence` and `diff_reviewed` fields
  (and the runtime-written `stale` mark), `checkpoint-v1.schema.json` documents
  `migrations[]`, and `policy-v1.schema.json` the optional `receipts` section.
  A receipt without `input_roles` is read as all-dependency, so no existing
  receipt becomes weaker. An anonymised 1.3.0 checkpoint of a finished feature
  is read, previewed, migrated with every receipt kept byte for byte, gated
  with the same verdict before and after, and continued with a claim in tests.
- `workflow.py migrate --preview` returns, without writing, the exact
  `invalidated` and `preserved_as_historical` lists, the digest changes and any
  blockers the migration would record. The applying `migrate` shares the same
  computation and returns the saved `migrations[]` entry, which now also records
  the new dependency digest (`to`).
- Declared input roles. `complete` accepts `input_roles: {path: {role:
  dependency|consulted, because}}`, checks every key against the receipt's
  `inputs`, requires a `because` for a consulted input and refuses a consulted
  role on evidence or on a stage's required artifacts. Only dependencies decide
  `receipt_current` and the upstream-change check, so a consulted file changed
  by a later stage (the implementation-target cascade) no longer raises
  `UPSTREAM_INPUT_CHANGED_DURING_STAGE`; its recorded hash is kept, the change
  is logged as an advisory lineage entry and `next` reports it as
  `advisory_drift`. A dependency, or an undeclared input, still fails.
- New policy key `receipts.require_input_roles` (default `false`). When `true`,
  `complete` refuses an undeclared role for any input outside `specs/<feature>/`
  and `.specify/memory/`. It is never filled into an existing policy, so policy
  digests do not move on upgrade; turning it on invalidates no completed receipt.
- `workflow.py amend --feature --stage --evidence <path> --reason --assessment
  unchanged|changed` re-hashes one evidence entry of one receipt and appends
  `{path, old_hash, new_hash, reason, assessment, actor, at}` to its
  `amendments[]`, after backing up the checkpoint. `changed` marks Verify,
  Review and Ready (from the amended stage on) stale. A path that is not that
  receipt's evidence, an unchanged file, a missing file or an active claim is
  refused. `ci_gate.py` accepts amended receipts, lists every amendment in its
  result and names a changed amendment when it reports a stale receipt.
- A submitted receipt may not carry the runtime-written `amendments`, `stale`,
  `head`, `source_key`, `ci_evidence`, `diff_reviewed` or `revalidations`
  fields.
- Canonical source key (B3). New `scripts/source_key.py` computes
  the canonical source key from `git ls-tree -r -z --full-tree <tree>` on raw bytes
  (words and workflow-state paths left out), reproducing every case of the
  shared `tests/fixtures/source-key.fixtures.json` (byte-identical to the
  consumer's copy, pinned by SHA-256 and marked `-text`), also through real
  trees with executable, symlink and submodule entries. Verify, Review and Ready
  receipts record `head` and `source_key` when no source path differs from HEAD.
- Source-drift classification (B3, G1). New optional policy key
  `ci.gate.affected_command` (schema and validation): a hook that reads a JSON
  path list on stdin and prints `{"paths": {path: [lanes]}}`. `receipt_current`
  keeps a Verify, Review or Ready receipt with a `source_key` current when every
  drifted source path maps to no lane and none is among its explicit
  fingerprints; a failing hook fails closed. Without the hook, and for a receipt
  without `source_key`, the identity rule applies unchanged.
- CI run as Verify evidence and checked revalidation (B4, G2). New optional
  policy key `ci.gate.verification_check`. `workflow.py revalidate --stage
  verify --check-run <run id>` reads the run, its jobs and its plan artifact
  (`<prefix>-<run>-<attempt>/verification-plan.json`) through the GitHub REST
  API (`scripts/ci_evidence.py`, an injectable `gh api` client), requires
  success, every plan field matching the run, the tree and source key
  recomputed locally, the current source key, explicit fingerprints
  byte-matching and the run's lanes covering every lane the drift reaches; it
  writes `ci_evidence {run_id, head, source_key, tier, lanes, conclusion, ...}`
  and re-inventories the source. A lane gap is recorded, marks Verify stale
  (`ci-lane-gap`) and stays until a covering run. `revalidate --stage review
  --diff-reviewed <evidence>` requires a recorded incremental review of
  `git diff <review head>..HEAD` (`diff_reviewed`); `revalidate --stage ready`
  re-runs the Ready checks. Every revalidation is appended to `revalidations[]`
  and none is accepted on a note. `ci_gate.py` accepts a Verify receipt through
  `ci_evidence` on the current source key, lists revalidations and accepted
  drift, and with `--verify-ci-evidence` re-reads each such run through the API.
  `workflow.py ci --affected-command/--verification-check` sets or removes the
  keys. Neither key changes a policy digest.
- Recovery recipes (G6). `next` returns `recovery` with a stale stage, and a
  failing gate appends `recovery: ...` to `STALE_RECEIPT`: the exact `amend`,
  `revalidate` or `claim`/`complete` commands for that receipt. `POLICY_CHANGED`
  names the `migrate --preview` then `migrate --reason` sequence.
- Tests replay both 007 failure shapes (changed verification inputs; a changed
  integration test) to a passing gate through `revalidate`, show that a narrower
  check leaves Verify stale, that Review revalidation without a diff review is
  refused, the 008 shape (legacy receipts) against a fake plan artifact, and a
  real recorded plan artifact validated against its run metadata.

## 1.5.0

- Add opt-in model-aware routing across workflow stages and implementation
  tasks. Policy, model preferences, fallbacks and task overrides live in the
  consumer's `.specify/workflow.yml`; delegation remains disabled by default.
- Bundle `delegate-task` with the workflow package for project or global
  installation. Record requested and harness-reported actual models separately,
  including an explicit unverified state, fallback decisions, run evidence and
  token usage in a feature-scoped ledger that survives upgrades.
- Annotate pending tasks without changing their checkbox lines or semantic
  fingerprints, including a final task line without a newline. Preserve active
  route snapshots and show attempts in the local progress report.
- Reuse a usable project or global `delegate-task` copy and install the bundled
  one at the configured scope only when neither is usable. A copy is usable only
  when `delegate.mjs contract` reports the `delegate-task.driver.v1` contract,
  with result schema v2, requested/observed model fields and
  `coverage_complete`. The bundled copy is built and checked in a staging folder
  before it replaces anything. A broken or incompatible copy is moved to
  `.specify/workflow/backups/delegate-task/` or
  `~/.sanduq/backups/delegate-task/`, outside every skill discovery folder,
  restored if the swap fails, and reported as a `DELEGATE_SKILL_REPLACED` notice
  from install, dispatch and claim output. Installs are serialized per scope, so
  concurrent dispatchers install once and then reuse that copy. Legacy
  `delegate-task.sanduq-backup-*` folders leave every project and global skill
  folder on each install or reuse, each into its own scope's backup folder.
  `doctor` stays read-only and names `delegation.py install` and the configured
  scope.
- Enabling, disabling or rerouting delegation is not a semantic policy change:
  receipts, migrations and the CI evidence gate ignore it (checkpoint digest
  version 3), and older checkpoints are compared in their recorded format.
- Claims install the skill and annotate tasks only after every other check
  passes and a next stage exists.
- Classify tasks by explicit markers or an unambiguous leading action. A domain
  noun stays implementation wherever it appears, including at the start ("Audit
  log retention", "Review queue API endpoint", "Test runner integration",
  "Create guide page component"), and a check that also asks for a fix ("Inspect
  the parser and fix the crash") is implementation. `[Impl]`,
  `[Implementation]` or `[Code]` forces implementation. Routing never makes a
  run read-only.
- Serialize ledger writes across dispatchers and refuse a duplicate start. A
  ledger lock left by a dispatcher that died on this host is recovered by a
  single atomic capture; a live or other-host owner's lock is never taken, and
  a displaced owner refuses to save.
- Follow a rejected model with the configured fallback. Only a model error in
  the status reason or the stderr tail that names the requested model (or a
  structured `model_not_found` code) counts, not worker output that mentions a
  model. Move past starts that provably created no run, and past a driver exit 5
  whose finalized result, journal and dead supervisor prove no agent launched.
  Keep any other uncertain start for `recover`. The new
  `delegate_dispatch.py abandon --reason` closes an intent that has no run.
- Automatic stronger retry needs a complete measurement showing no edits,
  including `coverage_complete: true`.
- Normalize `--feature` spellings to `specs/<name>` in the dispatcher and in
  `delegation.py annotate` and `route`, so overrides and markers match. Collect
  each run with the driver copy that started it.
- Stop counting the dispatcher's own ledger writes as worker edits. A changed
  `delegations.json` is set aside only when the run worked in this checkout and
  the file still holds exactly the bytes a dispatcher last saved. Anything else
  still counts, so a rejected model now reaches its fallback, and failed work
  with no edits gets its stronger retry, even while parallel runs update the
  ledger. Attempts record the raw `changed_paths` beside
  `dispatcher_paths_changed`, `unattributed_bookkeeping_paths` and
  `worker_changed_paths`. An unchanged ledger is no longer rewritten. A
  foreign write seen before any dispatcher save stamps every live attempt
  `ledger_foreign_write_seen`. A later save can no longer launder a worker's
  ledger edit into bookkeeping and trigger a retry.
- Install and upgrade work with a symlinked project `delegate-task` folder again,
  even with delegation off. The link is snapshotted and restored as a folder
  link, even when its target is missing, and is never followed. Rollback
  snapshots leave out raw `runs/` and `node_modules/` data, and a link is not
  restored over unmanaged files.
- Treat a Windows directory junction at a `delegate-task` folder as a link,
  like a symlink. Install and upgrade no longer walk into its target and refuse
  with `MANAGED_PATH_SYMLINK_UNSUPPORTED`. Rollback restores it as a junction,
  including a dangling one, or stops with `ROLLBACK_JUNCTION_FAILED` before
  changing anything. `doctor` no longer takes a junctioned copy for a Sanduq
  install and replaces it. Junction detection works on Python versions without
  `Path.is_junction`.
- Rollback writes a junction's reparse data directly instead of falling back to
  `cmd /c mklink /J`. `cmd` expanded `%NAME%` inside the quoted target, so a
  dangling junction whose target held a defined variable such as `%OS%` could
  not be recreated and the rollback stopped. Targets with `%`, `&`, `^` or `!`
  now come back exactly, and a missing target is never created.
- A skill install over a dangling project `delegate-task` junction no longer
  deletes it. A junction whose target is missing is neither `exists()` nor a
  symlink, so it was not moved aside, the swap failed, and the cleanup removed
  the link. It is now moved to the backup folder as the link itself (reason
  `dangling link`) and put back if the install fails. Cleanup removes only the
  copy the install itself placed.
- Upgrades and installs refuse with `DELEGATION_ATTEMPTS_ACTIVE` while any
  attempt is starting or running. Dispatcher `start`, `collect`, `reassign`,
  `recover` and `abandon`, and skill installs, refuse with
  `WORKFLOW_UPGRADE_IN_PROGRESS` while an upgrade or install holds its lock.
  The error names the lock's recorded process ID. It says how to confirm a
  crashed owner and remove the stale lock, because waiting never clears one.
  Both sides check under the ledger and skill-install locks, so a rollback can
  no longer overwrite a live attempt's record.
- Retry lock-file removal when a transient Windows reader causes a sharing
  violation. Every retry checks the owner token, so a replacement lock is left
  alone; a persistent failure reports `DELEGATION_LOCK_RELEASE_BUSY`.
- Route documentation tasks that name a documentation file ("Update README.md
  with setup instructions", "Update docs/quickstart.md", "Document API
  endpoints in docs/api.md") to the documentation tier. Code under a nested docs
  folder and "Document <thing>" with no documentation destination stay
  implementation.
- When the driver's `doctor` fails, refresh only the copy that failed, in place,
  if it is a Sanduq install location. Sanduq no longer reinstalls at the
  configured scope on every dispatch. It reports a copy it does not own
  (override, plugin, symlinked folder, other discovery root) with its path and
  the repair action instead of replacing it.

## 1.4.0

- The implementation progress report shows token usage (#24): fresh input,
  cached input and output for each task, a total of the tasks the filters show,
  each phase, orchestration and review overhead, and the whole feature. The new
  `progress.py usage` command reads the figures from the agents' own harness logs
  (Claude Code subagent transcripts, Codex rollouts, delegate-task results). It
  reads token counters only, never message content. Collecting again replaces a
  figure instead of adding to it, a worker reused across tasks is split by each
  task's running-to-done window, and a missing log shows as a gap, never as zero.
  The total covers implementation only; scoping, specification and planning come
  before the report exists.
- The report uses the Sanduq mark as its page icon.
- `install.py --preserve-ci` and `upgrade.py --preserve-ci` no longer roll back
  with `CI_WORKFLOW_STALE` on a clone, worktree or machine without the
  git-excluded `install-receipt.json` (#22). The installer hands the preserved
  path straight to its health check, and the tracked `install-lock.json` now
  records `preserved_ci` so every checkout treats that file as project-owned.
  A lock that records nothing preserved takes precedence over an old local
  receipt that still names the file.
- `upgrade.py --preserve-ci` records the preserved file in the receipt before
  it runs the target package's installer, so a target that reads only the
  receipt also passes its health check. The upgrade snapshot restores the
  receipt on rollback.
- Upgrading to 1.3.0 with `--preserve-ci` from a checkout without the receipt
  still fails, because 1.3.0's installer carries the original defect. Target
  1.4.0 instead.

## 1.3.0

- Issue-bound feature identity uses the GitHub issue number and title for the
  initial branch and spec directory. Standalone non-issue Specify stays upstream.
- Material workflow decisions use stable questions and authorized answers in the
  bound GitHub issue, with a separate Project Decision field, a committed
  application ledger, conflict/edit detection, and artifact freshness checks.
- Select Disabled, Advisory, or Required evidence CI, managed-only or all-PR
  applicability, and individual rule groups during init or later. Ordinary
  non-feature bug-fix PRs return `not_applicable` under managed-only scope.
  Disabling an installed gate checks active GitHub branch rules before removing
  its managed job. Optional live-answer and candidate-merge rules are available.
  Exact, dated PR-rule waivers require an authorized GitHub reviewer and the
  current head SHA; identity checks remain mandatory.
- CI runner policy changes have a separate digest from delivery policy so they
  do not invalidate feature receipts. Reviewed migrations preserve older
  checkpoint hashes and audit invalidation.
- QA Assure and User Manual can be independently selected or deselected after
  initialization through reviewed policy and installer changes. The native
  Spec Kit workflow prototype remains isolated; Sanduq's receipt-based
  dispatcher remains the production scheduler.

## 1.2.4

- Evidence fingerprints no longer depend on how Git checked a byte-sensitive file
  out. A tracked `.sql` (or `-text`) file whose working tree differs from the
  index only by Git's checkout conversion (`core.autocrlf`, `eol` attributes) is
  fingerprinted as its committed blob, which is what a clean CI checkout holds.
  A Windows `core.autocrlf=true` checkout wrote LF-committed SQL as CRLF, so
  local receipts hashed CRLF bytes and the CI evidence gate reported
  `STALE_RECEIPT` for unchanged files. Real edits still hash the working-tree
  bytes, untracked files are unchanged, SQL committed as CRLF keeps its CRLF
  hash, and SQL content is still never normalized. Git is queried in batches
  (`ls-files --stage`, `hash-object --stdin-paths`, `cat-file --batch`), and not
  at all for files already identical to the index.
- `doctor` reports a `BYTE_SENSITIVE_EOL_DRIFT` warning (not an error) naming how
  many tracked byte-sensitive files have working-tree line endings different
  from the index (`i/lf w/crlf` or `i/crlf w/lf`) and how to re-checkout them.
  The report now always carries a `warnings` list.

## 1.2.3

- The implementation progress report is titled with the feature: `init` takes
  the plan's `# Tasks: <feature>` heading by default, `--title` renames an
  existing report without losing its evidence, and the browser tab shows the
  same title instead of a fixed "Implementation progress".
- The report shows the Sanduq logo (light and dark variants shipped under
  `assets/report/` and copied beside the page), adds a Phase column, filters
  tasks by Status and Phase, and moves the activity log to its own tab. Filters
  and the selected tab are kept in the URL fragment, so the five-second refresh
  no longer resets them; without JavaScript the page still refreshes.

## 1.2.2

- Depend on user-manual 1.3.0, which stages an edition's reachable assets so a
  strict manual build resolves every link.


## 1.2.1

- A reviewed migration now rebinds a checkpoint to the current policy. A release
  that only adds a policy section (1.2.0 added `ci:`) left every finished feature
  reading `POLICY_CHANGED` in the CI gate even though no work had changed.
  `migrate` records the policy change, invalidates exactly the stages the policy
  cutoff says a semantic change reached, and preserves the rest as historical.

## 1.2.0

- Where CI runs is a project decision recorded under `ci:` in `.specify/workflow.yml`;
  shipped workflow assets are rendered from it instead of carrying a fixed runner.

## 1.0.0

- Review Home pilot hardening: shared portable UTF-8 hashes across Workflow,
  QA and manuals, respecting `-text`, binary data, SQL bytes and lone CR.
- Publication index preflight and path-level stale-receipt diagnostics; no
  automatic staging and no relaxation of source freshness after target merges.
- Exclude derived graph output from implicit documentation inputs, retain
  explicit graph output integrity, and document exact-head/post-merge verification.
- Upgrading existing pilot state can invalidate receipts where hash semantics
  or implicit inputs changed. Review drift and migrate/revalidate affected stages;
  never rewrite historical receipts as new test execution.

- Live-pilot correction: only reliable measured context can pause the default workflow.
  Unknown/estimated/stale telemetry continues automatically; explicit strict mode remains opt-in.

- Initial managed workflow runtime, presets, issue adapters and local verification. Release and live acceptance pending.
- Exact-source dependency and preset installer, host registration checks, local backups,
  symlink-preserving rollback and an outer transaction for workflow package updates.
- Required artifact/source freshness, parent-scoped task mappings, reviewed migrations,
  versioned state contracts and policy-aware CI gates.
- Explicit clarification refresh, existing-feature revalidation, owned legacy alias
  upgrades and project readiness checks before dispatch.
- Resolve PR features from the target/head common ancestor, excluding unrelated
  target-branch changes; missing shallow history blocks with a fetch instruction.
