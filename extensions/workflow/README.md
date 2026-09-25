# Sanduq Workflow

Unreleased Workflow 1.5.0 adds optional model-aware delegation. Workflow 1.4.0
adds token usage per task, phase and feature to the progress
report and makes `--preserve-ci` work on any checkout. Workflow 1.3.0 added issue
decisions and an optional evidence CI gate. Check
the repository catalog for the currently published version. See the
[Delivery implementation plan](../../docs/sanduq-delivery-implementation-plan.md),
[usage guide](../../docs/sanduq-delivery-usage.md), and
[native prototype result](../../docs/native-workflow-prototype-results.md).

Choose QA Assure and User Manual independently during project initialization.
Daily entry points are `speckit.workflow.scope`, `.clarify`, `.continue`, and
`.finalize`. They are entry points into one resumable dispatcher, not mandatory
pauses between every stage.

Scope -> Specify -> Clarify/Brainstorm -> Plan -> one task generator -> selected
QA/manual analysis -> Analyze -> core Tasks-to-Issues -> one executor -> verification
and review -> selected QA/manual documentation -> explicit Finalize -> one PR.
All workflow and clarification illustrations use Archify. The existing PR, Assure
and User Manual Illustrate dependency remains separately versioned.

The dispatcher calls actual installed agent commands. The Python runtime manages
claims, evidence, invalidation and handoffs; it does not implement semantic agent
work or launch a fresh host session by itself. Missing native invocation support
is a blocker, not an instruction to pretend a stage ran.

## Context

Target a maximum 60% context occupancy with a checkpoint at 50% and a 10% reserve.
The default `measured-only` policy continues automatically without reliable host telemetry.
Estimated, missing, stale or invalid readings never force a context pause or a new session. A strict guarantee requires a host that enforces per-call bounds; prompt
instructions alone cannot provide that guarantee. Each handoff includes completed
stages, pending task IDs, identity, evidence and a fresh-session resume prompt.

## Packaging and development

Build archives with `python extensions/scripts/package.py workflow` from Sanduq.
The archive bundles canonical presets from `presets/`, so consumer command edits
are unnecessary. Install a staged extracted package using
`specify extension add --dev <extracted/workflow>`; install its bundled presets
through `specify preset add --dev <preset-path> --priority 1` (workflow) and priority
2 (scope-gate/scope-brainstorm). The isolated native prototype was checked on
Spec Kit 1.0.11, commit 92b7cf7658a177cc417b7ddbeaa4c0a941a5f41b;
its command completion is insufficient for production receipt semantics.
Other versions require compatibility testing.

For a managed project run `workflow.py init --qa on|off --manual on|off --delegate
on|off`, configure
GitHub Project status mappings, run `install.py` preview/apply and run doctor. Only explicit
selections enable processes. The dependency lock records exact intended versions;
those pending releases cannot yet be installed from public release URLs.

Scope's community catalog name is ambiguous. Always use the Sanduq archive URL or
verified staged package, never a bare `specify extension add scope` command.

## State and recovery

Policy lives in `.specify/workflow.yml`. Feature state lives under
`specs/<feature>/workflow/`. Claims prevent concurrent stage ownership. Only an
explicit Specify claim can bind a new branch after verifying scope-source.json.
Use `recover` with the recorded token after inspecting possible remote writes;
use `migrate` after reviewing a dependency upgrade. Both preserve an audit trail.
A migration backs up the checkpoint, preserves still-current historical evidence and invalidates changed command selections. Use `--invalidate-from <stage>` when an upgrade changes a stage contract.

Use `upgrade.py --version X.Y.Z` preview, then `--apply`, to update the workflow
package and its integrations with outer rollback. Local staged testing supports
`--packages <extracted-packages>`. See the [operating guide](../../docs/workflow-guide.md)
and [compatibility contract](../../docs/workflow-compatibility.md) for tested limits.

`task_issues.py` is dry-run by default. The core Tasks-to-Issues preset invokes it
with `--apply` within authorized issue work. Native sub-issues are identified by
repository, parent, feature and task ID; retries recover lost responses. Existing
Project mappings are adopted only after verifying native parent links. Unmapped
children block duplicate creation. `--sync-states` updates task issue completion
without changing the publication evidence.

The project selects Disabled, Advisory, or Required CI evidence gating and
individual rules at initialization or later. Managed-only scope lets ordinary
source-only bug-fix PRs pass with an explicit `not_applicable` result. Enabled
rules distinguish committed receipts and decision evidence from live GitHub
checks and human acceptance. Disabling the job checks active branch rules so a
required check is not stranded. Finalize also verifies that each inline PR visual
loads in an authenticated private-repository view.

Before publication, run `ci_gate.py --feature specs/<feature> --base-ref <target-sha>
--check-index` after staging reviewed evidence, then repeat the gate in a clean
checkout of the candidate commit. Missing/unstaged dependencies are reported by
path; the command never stages files. Target-branch source changes invalidate old
verification even when Git merges cleanly. Configure `workflow-evidence` as a
required branch check only when this project has deliberately selected Required
mode; otherwise leave its branch rule optional.

UTF-8 text fingerprints normalize CRLF across checkout platforms. Explicit Git
`-text`, SQL, NUL-bearing and non-UTF-8 files remain byte exact; lone CR is not
normalized. Shared QA/manual hashing follows the same contract. Generated graph
files are excluded from implicit documentation input discovery but remain checked
when explicitly declared as outputs. Revalidate affected historical receipts after
adopting this changed contract; do not relabel old evidence.

The dispatcher ends at PR publication. Its `pr_open` state is not post-merge
certification. Follow the skill's post-merge protocol and retain an external-state
report of exact SHAs, checks and rollout observations. See the
[Review Home pilot findings](../../docs/workflow-pilot-review.md).

## Optional model-aware delegation

Delegation is off by default. It routes workflow stages and implementation
tasks to a preferred agent CLI and model through the bundled `delegate-task`
skill, records every attempt, and leaves the dispatcher in charge of claims and
receipts. A successful delegated run is candidate evidence for the orchestrator
to inspect, never a passed stage or a completed task.

### Turning it on, off or rerouting later

Select it during init with `--delegate on`, or opt in later without
reinitializing:

1. Set `delegation.enabled: true` in `.specify/workflow.yml`, with any model,
   route, `install_scope` or override edits.
2. Run `python .specify/extensions/workflow/scripts/workflow.py doctor --project`.
   Doctor is read-only. If no usable skill exists it reports
   `DELEGATE_SKILL_MISSING`, `DELEGATE_SKILL_BROKEN` or
   `DELEGATE_SKILL_INCOMPATIBLE` (with each rejected path and the reason) and
   names the next command.
3. Run `python .specify/extensions/workflow/scripts/delegation.py install`.
   It reuses a usable project or global copy. Only when neither is usable does
   it install the bundled copy at the configured `install_scope` (`project`,
   the default, or `global`).
4. Run `python .specify/extensions/workflow/scripts/delegation.py annotate
   --feature specs/<feature>` to add routing metadata to pending tasks, then
   claim the next stage as usual.

A claim also installs a missing skill and refreshes pending task metadata, but
only after it has passed every other check and found a stage to claim. A
rejected claim, or one with no next stage (`ready_to_finalize`, `pr_open`),
leaves `tasks.md` and every skill location untouched.

Enabling, disabling or rerouting delegation is not a semantic policy change.
It does not invalidate stage receipts, migrate a checkpoint or fail the CI
evidence gate with `POLICY_CHANGED`, including for features already at
`ready_to_finalize` or `pr_open`. Checkpoints written before the delegation
section existed are compared as they were written. Other policy edits still
invalidate the stages they reach. When delegation is disabled, existing
routing comments are ignored and work runs with the user's selected model.
Runs already started can still be collected.

### Which installed skill is used

A copy is usable only when its driver answers `node delegate.mjs contract` with
contract `delegate-task.driver.v1`, result schema `delegate-task.result.v2`, and
the flags, environment variable, exit codes and result fields the dispatcher
reads. Those fields include `requested_model`, `actual_model`,
`model_observed` and `coverage_complete`. Files that merely exist do not count.
An older or customized copy that passes this check is reused unchanged. A broken
or incompatible copy at the install target is replaced by the bundled version.
The new copy is built and checked in a staging folder first, so a failed install
never leaves a partial skill. The old copy is then moved aside in one rename,
not deleted, to `.specify/workflow/backups/delegate-task/` for project scope or
`~/.sanduq/backups/delegate-task/` for global scope. Both are outside every
skill discovery directory, so the backup's `SKILL.md` never appears as a second
skill. If the swap fails, the previous copy is restored. The install result,
`delegate_dispatch.py start` and a claim report the replacement as a
`DELEGATE_SKILL_REPLACED` notice naming the old path, why it was rejected and
its backup, so a customization can be carried over by hand.

`delegate-task.sanduq-backup-*` folders that earlier builds left inside
`.agents/skills`, `.claude/skills` or `.codex/skills` are moved out on every
install or reuse, not only when a copy is replaced. Project backups go to the
project backup folder and global ones to `~/.sanduq/backups/delegate-task/`;
nothing is written to the home folder unless a global legacy backup or a global
install needs it. Each move is reported as `DELEGATE_SKILL_LEGACY_BACKUP_MOVED`.

Installs are serialized per scope with a lock file
(`.specify/workflow/runtime/delegate-skill-install.lock`, or
`~/.sanduq/runtime/delegate-skill-install.lock` for global work). Concurrent
dispatchers or claims wait, then re-inspect and reuse the copy the first one
installed; a lock still held after 180 seconds returns the retryable
`DELEGATE_SKILL_INSTALL_BUSY`. Other diagnoses: `NODE_MISSING` or `NODE_18_REQUIRED`,
`DELEGATE_SKILL_DOCTOR_FAILED`, and `DELEGATE_AGENT_CLI_UNAVAILABLE` when neither
Codex nor Claude works. A missing or broken individual CLI (`AGENT_CLI_MISSING`,
`AGENT_CLI_BROKEN`) is recorded as a skipped route.

A running attempt remembers the driver copy that started it. `collect` uses
that copy even if both project and global copies exist or `install_scope`
changes later. The stored path must still be a recognized skill location
(`DELEGATION_DRIVER_UNTRUSTED` otherwise).

### Routes, defaults and overrides

Each stage and task has a work type. Its route resolves in this order: a
feature-qualified task override, the YAML route for the work type, then the
shipped default. Every shipped default prefers a tier on the selected host and
falls back to that CLI's own default model (`model: null`).

| Work type | Default tier | Codex model | Claude model | Stages |
| --- | --- | --- | --- | --- |
| discovery | high | gpt-6-astra | opus | scope, specify, clarify, plan, tasks |
| implementation | standard | gpt-6-sol | sonnet | tasks only |
| qa | light | gpt-6-terra | haiku | qa_analyze, verify, qa_document |
| documentation | documentation | gpt-6-sol | opus | manual_analyze, manual_update |
| review | review | gpt-6-sol | opus | analyze, review |
| coordination | light | gpt-6-terra | haiku | taskstoissues, execute, ready, pr |

The model names are editable preferences in `delegation.models`, not proof that
a CLI accepts them. Use `delegation.py route --feature specs/<feature> --id T001
--type implementation` to inspect a resolved route. For example, merge this
override into the existing `delegation:` block, keeping the generated `models:`
and all six `routes:` entries:

```yaml
delegation:
  enabled: true
  install_scope: project
  overrides:
    specs/26-add-opt-in-model-aware-task-delegation/T001:
      preferred: {harness: claude, tier: high}
      fallbacks:
        - {harness: selected, model: null}
```

A task's type comes from an explicit marker in its leading tags: `[Impl]`,
`[Implementation]` or `[Code]`; `[QA]`, `[Test]`, `[Tests]` or `[TDD]`; `[Doc]`,
`[Docs]`, `[Documentation]` or `[Manual]`; `[Review]`. The implementation
marker wins over the others and is the escape for any task the rules below
misread. Without a marker, only an unambiguous leading action counts: "Run ...
tests", "Write/Add ... tests for ...", "Test <something>", "Capture ...
screenshots"; "Document the ...", "Update README/docs/guide/release notes"
followed by a preposition or the end of the line; "Review/Audit/Inspect
<something>". When the word after "Test", "Review", "Audit" or "Inspect" names
something being built (log, queue, API, endpoint, service, page, component,
runner, pipeline and similar), the task is implementation: "Audit log
retention", "Review queue API endpoint", "Test runner integration". A check
that also asks for a code change ("Inspect the parser and fix the crash",
"Run tests and fix failures") is implementation too, as is "Create guide page
component". Anything else is implementation. Route type only chooses
a model. It never makes a run read-only, so a delegated review can write its
evidence and run checks.

`annotate` writes an HTML comment below each pending `T###` line. It never
changes checkbox lines, completed tasks, running tasks or the semantic task
fingerprints; a final task line without a newline gains one before its marker.

### Starting, collecting and recovering

`delegate_dispatch.py start` and `collect` run semantic stages (`--id
stage:<stage> --claim-token <token>`) and bounded tasks (`--id T###`) through
the skill. `--feature` accepts `specs/<name>`, `specs\<name>`, a trailing slash
or an absolute path inside the project, here and in `delegation.py annotate` and
`route`. All of these resolve to one `specs/<name>` identity for the ledger,
the task markers and overrides. Paths outside `specs/` and `..` traversal are
rejected with `DELEGATION_FEATURE_INVALID`. A second start of a task or stage that is
already starting or running is refused with `DELEGATION_ALREADY_RUNNING`.

- **Unavailable model.** When the CLI rejects the requested model ("unknown
  model", "model ... does not exist", `model_not_found`, `not_found_error`,
  "may not exist", and similar), the dispatcher records the decision and starts
  the next configured fallback. It never substitutes a stronger model for a
  rejected one. The wording must appear in the driver's status reason or the
  last 40 lines of the CLI's stderr, and must name the requested model; a
  structured `model_not_found` code needs no name. Worker output that merely
  mentions a model, such as a test failing with "Model matching query does not
  exist", does not count.
- **Failed start.** If the driver exits without creating a run for the
  attempt, nothing started. The same holds when the driver exits 5 because its
  supervisor never acknowledged the start, and the run it left proves no agent
  ran: its finalized result is `failed` with `containment_evidence: "the
  harness never launched"`, its journal holds only `created` and `terminal`,
  and the supervisor process is no longer alive. Either way the failure is
  recorded (with the dead run's ID for exit 5) and the next candidate is tried.
  If any of those proofs is missing, the start is uncertain instead. If every
  candidate fails, the attempt is `blocked` and the task can be started again.
- **Uncertain start.** If the driver's answer is lost, the dispatcher keeps a
  `starting` intent and returns `DELEGATION_START_UNCERTAIN` rather than risk a
  duplicate. Run `delegate_dispatch.py recover --feature specs/<feature>
  --intent-id <id>` to bind the driver run. If `recover` reports `found: false`,
  close the intent with `delegate_dispatch.py abandon --feature specs/<feature>
  --intent-id <id> --reason "<why>"` and start again. `abandon` refuses when a
  driver run exists for the intent, other than one already proved never
  launched. It also waits 300 seconds after the start
  when no launch outcome was recorded, since another dispatcher may still be
  starting it.
- **Automatic stronger retry.** At most `delegation.stronger_retry` (default 1)
  stronger-tier reassignment runs for failed work. It runs only when the driver
  measured no edits: `dirty_paths_changed` is `[]`, `head_changed` and
  `index_changed` are `false`, and `coverage_complete` is `true`. Any of these
  missing, null or different means no automatic retry. For a terminal result that is still
  incomplete, the orchestrator may run `delegate_dispatch.py reassign --feature
  specs/<feature> --run-id <id> --reason "<gap>"` within the same limit.
- **Route snapshots.** A running attempt keeps its start-time route when YAML
  changes. Each claimed stage records its route in the checkpoint.

`collect` follows a `replacement` run ID when one was started. Concurrent
dispatchers serialize their ledger writes, so parallel starts and collects never
lose an attempt or start the same work twice. A busy ledger returns the
retryable `DELEGATION_LEDGER_BUSY` after 15 seconds, naming the lock owner's
process and host.

The ledger lock is `.specify/workflow/runtime/delegation-<hash>.lock` and records
its owner's process ID, host and a token. A lock whose owner has exited on this
host is recovered automatically, and so is an owner record that was never
written once it is 60 seconds old. A lock held by a live process, or by any
process on another host, is never taken. Recovery captures the lock with a
single rename and puts it back if it turned out to belong to a live owner. A
dispatcher that finds its own lock replaced refuses to save the ledger. If the
owner's process ID was reused by an unrelated process, the lock looks live:
confirm the named process is not a dispatcher, then delete the lock file.

### History and evidence

The tracked `specs/<feature>/workflow/delegations.json` records every attempt,
requested route, skipped or fallback decision, start failure, abandoned intent,
result and token usage. It survives upgrades and is included in installer
rollback snapshots. The requested model and the model the harness reported are
kept apart. When a harness does not report its actual model, the ledger and
report say `unverified`; the requested model is never shown as measured fact.
Raw prompts and logs stay in the git-ignored `.delegate/runs/`, and
`progress.py sync` rebuilds the local HTML history view from the ledger.
