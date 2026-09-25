# Changelog

## 1.5.0 (unreleased)

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

## 1.0.0 (unreleased)

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
