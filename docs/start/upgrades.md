# Upgrades and changelogs

Read the published version in the [catalog](../../catalog.json) before you upgrade. Release notes
are in the root [CHANGELOG](../../CHANGELOG.md) and in each package's `CHANGELOG.md`.

## Workflow and its dependencies

If Workflow is installed, upgrade it only through its `upgrade.py`. Workflow pins the versions of
Scope, Project, PR and Illustrate, and of Assure, User Manual and Progress when selected, in
`dependencies.json`. Some releases need them
updated together (Workflow 1.18.0 needs Scope 1.11.0). `specify extension update workflow` on its own
is not supported: it updates Workflow without its companions, and the mismatch can misbehave
without an error. `workflow.py doctor --project` reports a mismatch.

Resolve active [claims](../reference/glossary.md#claim) first. Then preview and apply the
transactional upgrade, substituting the published version:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version <version>
python .specify/extensions/workflow/scripts/upgrade.py --version <version> --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

The first command previews. The second backs up the managed files, upgrades, and restores the old
state if anything fails. Add `--preserve-ci` to keep a project-owned evidence workflow.

If an older upgrade stopped at `HOOK_CHANGED_SINCE_RECONCILE` after an extension refreshed a
disabled hook's prompt or description, use the standard upgrade to published Workflow 1.19.2:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version 1.19.2 --preserve-ci
python .specify/extensions/workflow/scripts/upgrade.py --version 1.19.2 --preserve-ci --apply
```

The upgrader installs the new Workflow first, then runs its installer and reconciler inside
the rollback transaction. No separate repair step is required. Reconciliation accepts only
text matching the installed extension manifest, preserves original enablement, and audits both
metadata versions. Operational changes or unverified text still block; inspect them instead
of editing the journal or enabling hooks. Omit `--preserve-ci` when you do not need to retain
a project-owned evidence workflow.

After an upgrade, a feature that was in progress needs a reviewed migration before it continues:

```bash
python .specify/extensions/workflow/scripts/workflow.py migrate --feature specs/412-refund-approval --reason "Reviewed the upgrade notes"
```

The [operating guide](../workflow/operating-guide.md#updates-and-releases) explains what migration
keeps and what it invalidates.

## One extension

```bash
specify extension update <id>
```

Use this for an extension that Workflow does not pin, such as Memory, or in a project without
Workflow. Then rerun the extension's init or doctor command if its changelog asks for it.

`update` skips `scope` and `memory` without an error when the community catalog wins their IDs.
[Register Sanduq's catalog ahead of it](install-speckit.md#if-you-keep-spec-kits-default-catalogs).

## Adopt Workflow 1.13.0 profiles

Workflow 1.13.0 (with Scope 1.8.0) adds effort-tiered profiles, a deterministic `workflow:lint`
stage, merged plan and tasks on the lower tiers, batch upstream revalidation, a guard hook and role
agents for Claude Code and Codex. Nothing changes until you opt in. After the transactional upgrade
and the per-feature migration above:

1. Add the policy keys you want to `.specify/workflow.yml`. The minimum that changes the front half
   is a new `profiles` section and two keys merged into the existing `clarification` section (the
   file already has one; a second `clarification:` block is refused with `POLICY_DUPLICATE_KEY`):

   ```yaml
   profiles:
     enabled: true
   clarification:                 # merge into the existing clarification section
     transport: github-comments   # already there
     resume_on_reinvoke: reread-answers
     in_session_first_round: true
     max_questions_per_round: 6
   ```

   Optional keys: `artifacts.budgets` and `artifacts.enforce`, `issue_sync.taskstoissues:
   phase-lazy`, `project_sync.points`, `scope.board_cache_seconds`. The
   [workflow changelog](../../extensions/workflow/CHANGELOG.md) lists each key and its default.
2. Run `workflow.py doctor --project`. It confirms the installed packages, reports
   `INSTRUCTION_FILES_DUPLICATED` when both CLAUDE.md and AGENTS.md exist without an import, and
   prints the Codex hook approval instruction when Codex is installed. Approve the guard hook once in
   Codex with `/hooks`.
3. Start the next real issue with `$speckit-workflow-scope <issue>`. Scope records the effort score,
   the first Plan claim fixes the tier (`lite`, `standard` or `full`), and `workflow.py status
   --feature specs/<feature>` lists the stages that tier skips. Features already past Plan keep
   their full stage list.
4. Compare the run with the previous one: `status` shows the profile and the skipped stages, the
   receipts record `command: workflow:lint` where the lint replaced a model Analyze, and the host's
   own usage view gives the token spend. The repository benchmark
   ([benchmarks](../evidence/benchmarks/README.md) in the sanduq repository) measured runtime cost and
   instruction load, not generated tokens, so a live run is the confirmation.

Codex can now install the portable plugin bundles from the same marketplace
(`codex plugin marketplace add samykabu/sanduq`, then `codex plugin add <bundle>@sanduq`); that path
is published but has not been exercised yet, so report what you see.

## Adopt the round-2 releases

Workflow 1.14.0 pins Scope 1.8.1, Project 2.3.0, PR 4.3.0 and Illustrate 2.5.0, and selects Assure
2.4.0, User Manual 1.6.0 and Progress 1.3.0; the transactional upgrade installs them together. What
changes without any policy key:

- **Project.** Sync is one Python script (`project_sync.py`); Python is now required. The claim
  prints the exact sync command, so the agent no longer rereads the sync command file.
- **PR.** `pr_publish.py` writes the body, runs pr-lint and publishes; the receipt fields come from its
  output. The guard hook refuses a `gh pr create|edit --body-file` whose lint receipt does not match
  and a `gh pr create` on the default branch. Approve the changed hook once in Codex with `/hooks`.
- **Assure.** `documentation-gates.yml` is re-rendered: the gate reads the config through
  `assure_state.py status --gate`, and a reformatted config can no longer skip it. A project that kept
  its own copy with `--preserve-ci` should compare it with the shipped one.
- **Illustrate and its consumers.** Diagram steps read the type index plus one type reference; the
  skill's entry file is 11.7 KB instead of 34.7 KB.
- **Memory.** `run.md` reads its references by step; `status` returns the next command.

Opt-in keys, each off or unchanged until set:

```yaml
# .specify/workflow.yml
progress:
  hook_wiring: native            # hooks run hook.py directly; unset: native on new installs, existing keep theirs
  post_tool_matcher: "Bash|Task|Agent|spawn_agent"   # default "" (every tool); fewer activity updates
illustrate:
  hooks:
    self_check: true             # default false; checks every written diagram HTML
```

`User-Manual/manual.yml` takes `lifecycle.impact_scope: evidence` (default `all`) to update only the
modules the changed inputs touch; `assure-config.yml` takes `scan.exclude`; Memory's
`archive-policy.json` takes `guard_hooks: true` (default false). After setting a Progress key, rerun
`install.py` so the host hooks are rewritten; with `native` wiring, run it again after any later
`specify extension` command, which restores Spec Kit's own entries. Each package changelog lists the
details.

## Upgrade to Workflow 1.15.0

Workflow 1.15.0 pins Scope 1.9.0, Project 2.4.0, PR 4.4.0 and Illustrate 2.6.0, and selects Assure
2.5.0, User Manual 1.7.0 and Progress 1.4.0; the transactional upgrade installs them together.
Nothing is renamed and no policy key is added. What you notice after the upgrade:

- **Illustrate hook.** 2.5.0 registered its post-write hook in every project, so each Write or Edit paid
  for a no-op. The upgrade removes those entries from `.claude/settings.json` and `.codex/config.toml`
  and installs a native entry only when `illustrate.hooks.self_check: true` is set; `install-lock.json`
  records what was done per host. Projects without Workflow run
  `python .specify/extensions/illustrate/hooks/self_check_hook.py install --host claude --root .`
  (or `uninstall`) themselves.
- **Codex approvals.** The guard hook changed (it now refuses an unlinted pull-request body in a
  managed project). Approve it once in `/hooks`; `doctor` and `status` report `GUARD_HOOK_UNAPPROVED`
  until you do.
- **Assure gate.** A config that says `require_document_before_pr: false` is off even when a comment on
  that line mentions `true`. The rendered `documentation-gates.yml` changes on upgrade.
- **Pull requests.** `pr_publish.py` rewrites relative image paths to pinned URLs before the lint and
  refuses to publish when it cannot read the existing pull request.
- **Project sync.** Repository names with dots, remotes with ports and differently cased owners now
  match; the token needs the full `project` scope.
- **Faster runtime.** Each Workflow command reads git once, and Scope makes far fewer GitHub calls.
  Nothing to configure.

## Upgrade to Workflow 1.16.0

Workflow 1.16.0 selects Assure 2.5.1 and User Manual 1.7.1 and fixes issue #99. No policy key is
added. What changes:

- **Project Sync.** The claim's `project_sync.command` is
  `python .specify/extensions/workflow/scripts/workflow.py project-sync --feature <f> --phase <p>`.
  It runs the Project script, records the result in the checkpoint, and `next` and `status`
  report a pending or failed sync with its retry command. Run it after `complete` (Execute: before
  implementation, as before).
- **Receipts bind the board entry, not its status.** A receipt that depends on the Project Sync
  state file under `.specify/` records the feature's entry without its status, so a status write no
  longer stales it. Receipts recorded before the upgrade keep the old byte hash until you run
  `workflow.py migrate --feature specs/<feature> --reason "<why>"` (the step every in-progress
  feature runs after an upgrade) or `workflow.py sync-amend --feature specs/<feature> --reason
  "<why>"` with no active claim. Both check the entry against `scope-source.json` and
  `workflow/task-issues.json` and refuse a changed binding; then re-record the stage.
- **Documentation freshness.** Assure and User Manual write freshness logs and status reports to
  their state folders (`.specify/extensions/assure/state/<feature-name>/reports/`,
  `User-Manual/.state/features/<feature-name>/reports/`), and a regenerated declared output no
  longer reports as a changed input. States recorded before the upgrade compare as before.
- **Lean execution** is unchanged; the [operating guide](../workflow/operating-guide.md#adopting-lean-execution)
  now says how to adopt it.

## Round 4 migration (Workflow 1.17.0)

The round ships Workflow 1.17.0, Scope 1.10.0, Assure 2.6.0, User Manual 1.8.0, PR 4.5.0, Project 2.5.0,
Illustrate 2.7.0, Memory 2.5.0 and Progress 1.5.0. Round 4 changes no extension ID, command name or policy key. Finish or recover any active Memory
archive run first (`archive.py status`). Then update Memory before Workflow, and run Memory's
`enable` once:

```bash
specify extension update memory
python .specify/extensions/workflow/scripts/upgrade.py --version <version> --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

```text
$speckit-memory-enable Review the renewed archiving policy and approve it.
```

| Change | What you see | What to do |
| --- | --- | --- |
| Catalog priority (docs) | With Spec Kit's default catalogs listed and Sanduq at priority 10, `add scope` or `add memory` refuses and `update` skips them | [Register Sanduq at priority 1](install-speckit.md#if-you-keep-spec-kits-default-catalogs) |
| Workflow keeps three backup ZIPs | After the next successful apply, older ZIPs under `.specify/workflow/backups/` are deleted. Logs stay; a failed apply deletes nothing | Copy out any older ZIP you want before that apply |
| Install and upgrade wait for Memory | `MEMORY_ARCHIVE_ACTIVE` names the command that resumes the run | Finish or roll back the archive run, then upgrade |
| Memory approval hash | Automatic archiving stays off until you approve again | Run `$speckit-memory-enable` once after the update |
| Old Memory queue entries | `pending` reports entries queued before the new approval as blocked, with the fix | Archive each with `$speckit-memory-run --spec <dir>`, or queue it again from its implementation branch |
| Workflow owns Memory's `session` and `prepare` hooks | The upgrade's reconcile sets `enabled: false` on both. Adding Memory after Workflow gives `DUPLICATE_STAGE_OWNER` in `doctor` | Run `python .specify/extensions/workflow/scripts/reconcile.py --apply`. Do not re-enable the hooks by hand; reconcile undoes it |
| The claim runs Memory's session check | A claim can return `memory_blocked` or `memory_dispatch` with `memory_handoff` instead of a stage | Run its actions, then claim again. Stop running `memory-handoff --transition session` before each claim |
| Workflow's legacy `progress.py` retired | With Progress installed and enabled, a legacy call exits 2 with `error PROGRESS_INSTALLED: ...` and the command to use | Switch prompts and scripts to `.specify/extensions/progress/scripts/progress.py` ([mapping](../workflow/operations.md#reporting-modes-and-the-legacy-call-mapping)) |
| Progress v2 status and classic layout deprecated | Both still work in Progress 1.5.0; later releases refuse them with `PROGRESS_REMOVED` (exit 2) | Read `progress status --json` (`sanduq.progress.v3`); run `progress theme --layout timeline` |
| Assure's gate checks out the PR head | `assure init` and the Workflow upgrade replace an unedited `documentation-gates.yml`. An edited one is kept and init prints the `ref:` line | Add the printed `ref:` line to an edited gate |
| Assure scan skips git-ignored folders | The first scan can drop rows, rewrite `.github/memory/project-memory.md` once and stale recorded document and manual states once | Commit the rewrite and rerun Document and Update when asked |
| Assure Analyze ignores the User Manual task block | An analyze state recorded over a `tasks.md` that held that block goes stale once | Rerun Analyze once |
| Assure config keys removed | `freshness.policy`, `freshness.state_directory` and `output.directory_name` stay in an existing config and do nothing | Nothing; delete them if you like |
| User Manual Update archives | A local Update no longer writes `User-Manual/site/<version>/*.zip` unless `manual.yml` names an approved provider | Nothing; those ZIPs were build output |
| Illustrate self-check fails closed | With `illustrate.hooks.self_check: true`, a `.specify/workflow.yml` the hook cannot read blocks written diagrams with a message | Install PyYAML for the hook's Python, write the key as plain block lines, or set it to `false` |
| PR never edits a merged or closed PR | Rerunning `speckit.pr.generate` after the PR merged exits 3 and publishes nothing | Open a new branch for further changes |
| Project refuses a malformed state file | The sync stops on a malformed `.specify/project-sync-state.json` | Restore it from git or fix it, then rerun |
| Project owner type | A config from an older Init for an organization board says `ownerType: user` | Rerun `$speckit-project-init`, or set `"ownerType": "org"` |
| Scope's `scope-gate` preset changed | A managed Specify claim is no longer told to chain Clarify | Unmanaged projects run `specify preset add` again for `scope-gate`; the Workflow installer re-adds it |

## Lean lite tier (next Workflow release)

A feature whose tier is fixed as `lite` after the upgrade runs seven stages instead of eleven:
Scope, Specify, Clarify, Plan, Execute, Verify and PR. No policy key or command changes. Features
already in flight keep the stage list their tier was fixed with.

| Change | What you see | What to do |
| --- | --- | --- |
| Analyze folds into Plan | Plan's `complete` runs `workflow:lint`; the Plan receipt carries `lint`; a failing lint is `PLAN_LINT_FAILED` | Run `lint.py --feature specs/<f>` before completing Plan and fix findings in the owning artifact |
| Review and Ready fold into Verify | Verify's receipt carries the runtime-owned `ready_checks`; an unchecked task is `READY_CHECKS_FAILED: INCOMPLETE_TASKS`; after Verify, `next` says `ready_to_finalize` | Check every task before Verify; read the diff against the spec in the Verify pass; then finalize |
| No task sub-issues on lite | No Tasks-to-Issues stage; `task_issues.py` refuses with `TASK_ISSUES_SKIPPED`; the Ready task-link check reports `task_links:skipped (lite tier: no task sub-issues)` | Nothing; the parent issue is the only issue |
| Lite documentation no longer fails the gate | The gate's `documentation` rule skips a QA or manual process whose document stage the feature skipped | Nothing; standard and full features are checked as before |
| `status` shows a held claim's receipt template | `status` prints `receipt_template` while a claim is active | Use it to finish a claim resumed in a new session |

## PH-04 train (Workflow 1.22.0)

The train ships Workflow 1.22.0, Scope 1.13.0, Assure 2.7.0, Memory 2.6.1, Illustrate 2.7.3, PR 4.7.1,
Project 2.7.1 and User Manual 1.8.3. Every package now needs Python 3.11 or later. No policy key, command name or
receipt changes. Upgrade every companion together:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version 1.22.0 --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

| Change | What you see | What to do |
| --- | --- | --- |
| The evidence gate runs the base's code and policy | The upgrade and `assure init` replace an unedited `sanduq-workflow-gates.yml` and `documentation-gates.yml`, also in a fresh clone. The gate checks out the base into `.sanduq-base` and grades the head with the base's `ci_gate.py`, policy and Assure scripts; the upgrade PR itself is graded by the base's older gate. A PR that changes `.specify/workflow.yml` can fail with `POLICY_CHANGED` | Waive `receipts` for that PR, or land the policy change in a policy-only PR first. Protect `.github/workflows/` and `.specify/` with CODEOWNERS ([details](../workflow/runner-policy.md#who-grades-the-pr)) |
| You kept your own gate file | With `--preserve-ci`, or an edited file, nothing is replaced and the PR still grades itself | Port the second checkout (`path: .sanduq-base`) and the `.sanduq-base/...` script paths from the shipped template |
| Grading commands need the nonce | `accept`, `adopt`, `reassign` and `trust-reset` without `--nonce` fail with `DELEGATION_NONCE_REQUIRED`; run from inside a delegated run they fail with `DELEGATION_LINEAGE_SELF` | Pass `--nonce <dispatcher_nonce>` from the `start` result (or the file the message names), from the top-level session |
| Spec edits cite trusted answers | A clarification `spec_edits` entry without trusted `question_ids` is refused with `CLARIFICATION_EDIT_UNTRUSTED`; another bot's records are no longer evidence | Cite the answered question each edit applies |
| Python 3.11 required | Every `extension.yml` declares python `>=3.11`; `doctor` reports `HOOK_PYTHON_TOO_OLD` below 3.11 | Point the host hooks at Python 3.11 or later |
| Doctor checks Scope and Memory | `doctor` fails with `DEPENDENCY_SOURCE_MISMATCH` when either names another author or repository, or its files differ from the release's `package-inventory.json` | Reinstall that package from the Sanduq catalog |

## PH-03 train (Workflow 1.21.0)

The train ships Workflow 1.21.0, Scope 1.12.0, Memory 2.6.0, PR 4.7.0, Project 2.7.0 and Progress 1.7.0, with presets
`workflow` 1.3.3, `scope-gate` 1.6.2 and `scope-brainstorm` 1.5.1. New policy keys: `project_sync.mode`,
`issue_sync.taskstoissues: off` and `clarification.transport`; all are optional and none invalidates a receipt. Upgrade
every companion together, then reinstall Scope so the old hook skills are removed:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version 1.21.0 --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

| Change | What you see | What to do |
| --- | --- | --- |
| Errors explain themselves | Error JSON carries `explain` and `next`; `docs/reference/errors.md` lists every code | Follow `next` |
| Later receipts need confirmation | `claim` returns `status: confirm_invalidation` with the receipts it would remove | Read the list, then `claim --confirm-invalidation`, or amend instead |
| Finalize before Ready | `claim --finalize` before Ready returns `not_ready_to_finalize` with the remaining stages | Run `speckit.workflow.continue` |
| Board modes | A missing board in full mode is one `PROJECT_NOT_CONFIGURED` error | Run project init, or `init --board none` / `minimal` |
| Local clarifications | With `clarification.transport: local`, questions live in `specs/<feature>/clarifications.md` and receipts say `self_attested` | Answer in the conversation; the agent records your reply |
| Decision answers | `SD1: B.` and `SD1 - B` count; unreadable answers are listed `unparsed`; a comment a Sanduq process posted never counts | Reply `SD1: A` on its own line |
| Fork origin | Scope refuses `ORIGIN_IS_FORK` naming the parent | Clone the parent repository |
| Unrelated history | `prepare`, `start` and `doctor --project` refuse `HISTORY_UNRELATED` | Start from a branch of `origin/HEAD` |
| Interrupted install | `doctor` reports `INSTALL_INTERRUPTED` with a restore command | Run `install.py --restore <backup>` |
| Native stages | With delegation on, a stage a host subagent did is recorded with `delegate_dispatch.py attest-native` from the top-level session | Never from a worker or subagent; receipts show `native_attestation` |
| Child issue kept whole | A one-leaf re-scope of an edited child carries the parent's approval | Nothing |
| Guard | `git commit -a`, `git add -u` and PowerShell `git add -A` are refused | Stage owned paths by name |
| Source key | Evidence recorded with the key version used before 2026-10-10 is refused | Re-run the CI evidence step |
| Scope hook commands | The five hook-only `speckit-scope-*` skills are gone; `/speckit-scope-reconcile` is replaced | Use `scope.py reconcile --apply` |
| Delegate runs | Run logs are masked and runs older than 30 days are pruned after `collect` | Set `DELEGATE_PRUNE_DAYS=0` to keep them |

## PH-02 train (Workflow 1.20.0)

The train ships Workflow 1.20.0 and Scope 1.11.1, with presets `workflow` 1.3.2 and `scope-gate` 1.6.1.
No extension ID or command name changes; one new route key (`allow_default_model`) and one new
`lean_execution` key (`max_attempts`). The upgrade updates both together:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version 1.20.0 --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

| Change | What you see | What to do |
| --- | --- | --- |
| Receipt placeholders | `complete` refuses `RECEIPT_PLACEHOLDER: <field>` when a gating field still holds the claim template's `<...>` value | Set every gating field from the work done; nothing passes by default |
| Effort score check | The first Plan claim refuses `EFFORT_SCORE_MISMATCH` or `EFFORT_SCORE_UNVERIFIED` | Make the Scope receipt's `effort_score` match the score Scope verified (or the issue's `effort:<n>` label) |
| Unknown policy keys | `POLICY_KEY_UNKNOWN: <path>; did you mean <closest>?` on `.specify/workflow.yml` | Fix the key; a key from a newer release names the `upgrade.py` command |
| Live claims cannot be taken over | `recover` refuses `CLAIM_OWNER_ALIVE`; `status` shows `owner:` and `last_activity:` | Wait, or pass `--force-live-owner "<how you know it stopped>"` |
| Fallback needs confirmation | With delegation on, a rejected model stops `collect` with `FALLBACK_CONFIRMATION_REQUIRED` | Confirm in the conversation; the top-level session runs `collect --confirm-fallback <requested>=<substitute>`. List substitutes in the route's `fallbacks`, or set `allow_default_model: true` for the CLI default |
| Clean delegated environment | Workers see only the allowlisted variables; `GH_TOKEN` only on GitHub-adapter routes | A worker that needs another variable gets it through a `SANDUQ_*` name or the route's harness credentials |
| Native subagent stages | With delegation on, a stage done by the host's own subagent has no ledger attempt and `complete` refuses `DELEGATION_STAGE_NOT_VERIFIED` | The top-level session runs `delegate_dispatch.py attest-native --feature <f> --id stage:<s> --claim-token <t> --requested-model <m>` (self-asserted, labelled `kind: native`), then completes; a worker or subagent is refused |
| Lean attempt cap | `LEAN_ATTEMPT_LIMIT_REACHED` after `max_attempts` (default 3); `LEAN_PROVIDER_REJECTED` on `reassign` after a model rejection | Ask the owner, or start with another eligible harness/model pair |
| Locks recover from a dead owner | `WORKFLOW_BUSY` names pid, host, age and liveness; a lock whose pid exited on this host is reclaimed | Delete a lock from another host or an older version yourself once its process is gone |

## October 2026 train (Workflow 1.19.0)

The train ships Workflow 1.19.0, Assure 2.6.2, Illustrate 2.7.2, PR 4.6.1, Progress 1.6.1, Project 2.6.1,
User Manual 1.8.2 and Memory 2.5.1, with the `workflow` preset 1.3.1. No extension ID, command name or policy
key changes. The upgrade updates every companion together:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version 1.19.0 --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

| Change | What you see | What to do |
| --- | --- | --- |
| Every package is MIT | Each archive carries a `LICENSE` and, where it vendors upstream material, a `THIRD_PARTY_NOTICES.md`. Versions before this train stay PolyForm Noncommercial 1.0.0 ([licenses](../reference/licenses.md)) | Nothing |
| Tested Spec Kit is 1.1.3 | `dependencies.json` names Spec Kit 1.1.3 (commit `0282d03e`); 1.0.11 is no longer tested and cannot install Progress | Install the [prerequisites](prerequisites.md) version |
| Dependency errors name the fix | `doctor --project` fails on a companion older than Workflow's lock with `DEPENDENCY_UNAVAILABLE: <id> <installed> is installed; Workflow 1.19.0 requires <id> <required>; run "...upgrade.py --version 1.19.0 --apply"`. `DEPENDENCY_CHANGED` names `workflow.py migrate` and the same `upgrade.py` line | Run the command the message prints; then `migrate` each feature in progress with a reason |
| Review work is not delegated externally (security interim) | With delegation on, a `review` route, or any route on the `review` model profile, is refused with `DELEGATION_REVIEW_ROUTE_UNSAFE` at `doctor`, `claim` and `start`; `doctor` lists the refused routes as a warning; a review-kind stage (Analyze, Review) is claimed without a route and runs in the selected host; `tasks.md` marks a refused task `refused:DELEGATION_REVIEW_ROUTE_UNSAFE` | Run reviews natively. External review routes return with the clean-environment launch planned next |
| Maintainers: catalog promotion by pull request | `main` requires a pull request and the `lint` check; the release workflow opens `release/catalog-<run id>` and auto-merges it. The `vendor-update` workflow has no schedule | Run `vendor-update` by hand as part of each train ([release process](release-process.md)) |

## Round 5 migration (Workflow 1.18.0)

The round ships Workflow 1.18.0, Scope 1.11.0, Project 2.6.0, PR 4.6.0, Progress 1.6.0, Illustrate 2.7.1,
User Manual 1.8.1 and Assure 2.6.1, with presets scope-gate 1.6.0, scope-brainstorm 1.5.0 and workflow 1.3.0.
No extension ID, command name or policy key changes. Workflow 1.18.0 requires Scope 1.11.0 or later; the upgrade
updates both together:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version 1.18.0 --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

| Change | What you see | What to do |
| --- | --- | --- |
| Checkpoint version 2 | Version 1 checkpoints load unchanged. The first write (a claim, `complete`, `migrate`, `relocate`) rewrites one as version 2 without `repo_path`. Workflow 1.17 and earlier cannot read it (`WORKFLOW_START_REQUIRED`), and an older Scope misses its existing-feature claim | Update Workflow and Scope together. Do not downgrade Workflow after the first write |
| Native Progress wiring for new installs | `install.py --with progress` on a project with no Progress wiring writes hooks that run `hook.py` directly. Existing installs keep their wiring | To keep Spec Kit's dispatcher, set `progress.hook_wiring: speckit` before the install |
| Optional package needs a newer Spec Kit | The installer refuses Progress on Spec Kit below 1.1.1 with `OPTIONAL_PACKAGE_SPECKIT_INCOMPATIBLE`, before it changes anything | Upgrade Spec Kit, or install without `--with progress` |
| Progress v2 and classic layout removed | Progress 1.6.0 needs Workflow 1.17.0 or later. `--schema v2` and `--layout classic` exit 2 with `PROGRESS_REMOVED`; Workflow 1.16 and earlier ask for v2 and get it. A stored `layout: classic` shows the Timeline with one notice | Upgrade Workflow first. Read `progress status --json` (`sanduq.progress.v3`); run `progress theme --layout timeline` |
| Scope readiness stops at Done | A Done prerequisite whose own prerequisite was reopened no longer blocks. Cancelled, or closed without Done, still blocks | Nothing |
| `scope-gate` and `scope-brainstorm` overlays replace the command | Unmanaged Clarify and Brainstorm no longer compose the upstream command under the overlay. Spec Kit scaffolds `speckit.superspec.brainstorm` even without Superspec; Scope picks Brainstorm only when Superspec is installed and enabled | Unmanaged projects run `specify preset add` again for both presets; the Workflow installer re-adds them |
| `accept_plan.py` options removed | `--spec` and `--archify` are refused | Use `--html` |
| Project init in Python | `project-init.sh` and `project-init.ps1` print the `project_init.py` line and pass every flag through, for this release only. `jq` is no longer needed. Several projects for an owner gives exit 4 and a JSON `needs` line (was exit 1) | Call `python .specify/extensions/project/scripts/project_init.py` |
| PR review feedback from an approved plan | `speckit.pr.review-feedback` writes a plan file and shows its digest; a changed plan shows a new one. After the push it shows the pushed commit and a second digest | Approve the first digest before replies, and the second before threads are resolved |
| Illustrate verifiers share `svg_scan.py` | Diagrams and verifier output are unchanged | Keep `svg_scan.py` beside a verifier copied out of the skill |
| User Manual Init vendored | Init copies nothing into `User-Manual/tools/`. A new `manual.yml` has `lifecycle:` after `renderer:`; existing files are not rewritten | Nothing |

## Moved documentation

Pages moved in October 2026. The forwarding stubs at the old paths have been removed:

| Old page | New page |
| --- | --- |
| `docs/getting-started.md` | [Install by host](install-by-host.md) and the [scenarios](../README.md#choose-an-adoption-level) |
| `docs/skills.md` | [Skills only](../scenarios/skills-only.md) |
| `docs/extensions.md` | [Extension pages](../README.md#extensions) and the [command reference](../reference/commands.md) |
| `docs/extension-workflows.md` | [Extension pages](../README.md#extensions) and [managed Workflow](../scenarios/managed-workflow.md) |
| `docs/skill-guide.md` | [Worked lifecycle](../workflow/lifecycle.md) |
| `docs/workflow-guide.md` | [Operating guide](../workflow/operating-guide.md) |
| `docs/workflow-operations.md` | [State, evidence and runners](../workflow/operations.md) |
| `docs/sanduq-delivery-usage.md` | [Delivery policy](../workflow/delivery-policy.md) |
| `docs/workflow-compatibility.md` | [Compatibility](../reference/compatibility.md) |

`install.sh` and `install.ps1` were removed. Use the Spec Kit catalog.

## Limits

- An upgrade does not certify old receipts against the new package. Review the migration.
- A newer compatible dependency is kept, not downgraded to the pinned version.
