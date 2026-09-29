# Changelog

## Unreleased

- `task_issues.py` and `progress.py` gain `--summary` (one line: `ok`/`error`
  plus counts, e.g. `ok created=2 reused=5 total=7 dry_run=0` or `ok done=3
  total=8 pending=2 running=2 blocked=1`) and an explicit `--json`.
  `task_issues.py --json` prints exactly today's default output, byte for
  byte (its default was already the full JSON result). `progress.py --json`
  is new: today's default only ever printed the report path, so `--json`
  is an additional way to get the full `state.json` content, not a repeat of
  today's output. `--summary` and `--json` together is rejected in both.
  Default (no flag) behaviour and every exit code are unchanged, including
  for an exception outside each script's previously-handled set, which
  `--summary` now also reports as one `error <Type>: <message>` line instead
  of a raw traceback. `task_issues.py --sync-states` already walks every
  task in `tasks.md` per call, so it needs no change to be called once per
  phase for a batch of newly completed tasks instead of once per task (B7).
- `doctor --project` reports a `skill_inventory` block (new `skill_inventory.py`),
  per **host session load** rather than one cross-host sum: `hosts.claude`
  (`~/.claude/skills` + project `.claude/skills` + installed plugin skills, read
  from `~/.claude/plugins/installed_plugins.json`) and `hosts.codex`
  (`$CODEX_HOME`/`~/.codex` skills + `~/.agents/skills` + project `.agents/skills`),
  each with its own `combined` totals and same-host `duplicates`; a name shared
  between a claude root and a codex root (Sanduq installs the same command skill
  into both) is reported separately under `mirrors`, not counted as a duplicate or
  summed twice. Per-root numbers (`skill_count`, total/max frontmatter
  `description:` bytes, total `SKILL.md` bytes) are still reported in full, even
  below threshold, so C4 (skill pruning) can use them. Doctor warns
  `SKILL_INVENTORY_LARGE` (non-blocking) per host past 200 skills or 40 KiB of
  that host's own combined description bytes (measured against Bunyan; see the
  README); either threshold is overridable per-project under
  `policy['skills']['inventory_thresholds']`, now also in `policy-v1.schema.json`.
  The scan runs only on `doctor --project` (not on every `migrate`/`upgrade`
  doctor call) and a scan failure is caught and reported as
  `SKILL_INVENTORY_UNAVAILABLE`, never a doctor failure. The home-override env var
  is `SANDUQ_SKILLS_HOME` (was `SANDUQ_HOME`); `$CODEX_HOME` is honoured for the
  Codex root. See the README's "Skill inventory (doctor)" section for the
  reasoning and JSON shape. "Never invoked" pruning stays out of scope until a
  telemetry source and window exist.
- `claude_plugins` now filters and confines what it scans from
  `installed_plugins.json`: a `project`/`local`-scoped entry only counts for
  the matching project (`projectPath`), a plugin turned off in
  `enabledPlugins` (user `settings.json`, overridden by the project's own,
  overridden by its `settings.local.json`) is skipped, and every `installPath`
  must resolve (following symlinks) inside `~/.claude/plugins` itself; a UNC
  path is rejected by its literal text before any filesystem access. Anything
  rejected on the confinement/UNC check is listed under
  `claude_plugins.skipped_install_paths` instead of silently dropped.
  `$CODEX_HOME/skills` is confirmed live (cited in the README and in
  `skill_inventory.codex_home_root`'s docstring, checked against the installed
  Codex CLI 0.159.0), so it stays a normal counted root, not `legacy`.
- Split `skills/workflow/SKILL.md` (29 KB) into a core dispatcher (entry points,
  stage loop, receipt rules, <= 6 KB) plus one `skills/workflow/references/
  stage-<name>.md` per claimable stage. `claim` now returns a `reference` field
  (`workflow.stage_reference(stage)`) naming the exact file to read for the
  claimed stage. Cross-cutting detail moved to `references/dispatcher-
  operations.md`, `references/delegation-and-decisions.md` and `references/
  receipt-rules.md`. `references/execution.md` split into `references/
  execution-assign.md` (start/resume, assign work) and `references/
  execution-report.md` (report updates, finishing phases, delivery); every
  overlay in `presets/workflow/commands/*.md` shrank to a <= 5-line pointer,
  and the three `speckit-superpowers-bridge` legacy overlays point at a new
  shared `references/legacy-guard.md`. No rule was dropped: `extensions/
  workflow/tests/test_skill_split.py` diffs the pre-split files (read from git
  history) against the new set and fails on anything not moved, with an
  explicit, reasoned list for the handful of pointer sentences whose target
  relocated. `extensions/scripts/smoke_install.py`, `smoke_upgrade.py` and
  `test_execution_policy.py` were updated for the new paths and additionally
  assert every stage's reference is present in the built archive and an
  installed fixture project. No version bump; no script behavior changed
  beyond packaging the new files.
- Execution protocol updates (B11): `references/execution-assign.md` and
  `references/execution-report.md` now state the retrospective's rules as
  concrete, checkable instructions instead of prose: blocking parallel worker
  spawns whose results return to the orchestration agent, never the dispatcher
  (F1); no agent ends a turn while it owns running background work (F2);
  report only on a state change (F3); a turn-budget table per task class
  (implementation, qa_author, qa_collect, documentation, review) plus a
  planned hand-off at ~150K resident context (T0); a fixed ten-line worker
  result (T7); read a verification summary before raw reporter output, opened
  only for a failed lane (T8); `git stash` and `git add -A`/`git add .`
  forbidden for workers (S6); a consumers checklist after every fix (F11).
  `task_issues.py --sync-states` now runs once per phase boundary, not once
  per task (from B7), and the dispatcher's own token usage is recorded with
  `progress.py usage --overhead dispatcher --agent <id> --collect claude --log
  <path>` at every phase commit. Every routine `task_issues.py` and
  `progress.py` example call now carries `--summary` (B7: `ok`/`error` plus
  counts, or `skipped reason=...`), with `--json` reserved for a call whose
  result must be parsed programmatically. A marked placeholder section,
  "Light-tier collection results (B12)", awaits B12's final text.
  New `extensions/workflow/tests/test_execution_protocol_b11.py` asserts every
  rule above is present in the installed reference files, following
  `test_skill_split.py`'s style. No version bump; no script behavior changed.

## 1.6.4

- Pin the released User Manual 1.3.3 in `dependencies.json`. User Manual 1.3.3
  drops the private preview artifact's `upload-artifact` retention from 14 days
  to 2: the Cloudflare preview workflow reads it once, right after the run, and
  14 days of ~20 MB copies per push had filled the org's artifact storage and
  was blocking every Bootstrap run. Workflow itself is unchanged; a project on
  1.6.3 that already carried the 2-day retention as a local edit (as Bunyan did)
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
  attempt still fails. Same rule as Bunyan's `plan-evidence.mjs`.
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
  `bunyan-source-key/1` from `git ls-tree -r -z --full-tree <tree>` on raw bytes
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
  real recorded Bunyan plan artifact validated against its run metadata.

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
