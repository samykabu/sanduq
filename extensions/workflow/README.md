# Sanduq Workflow

Workflow 1.6.4 pins the released User Manual 1.3.3, whose private preview artifact now keeps `retention-days: 2` instead of 14 so the Cloudflare preview workflow's single read is not blocked by a filled artifact quota; Workflow itself is unchanged. Workflow 1.6.3 stops judging a managed alias by its frontmatter: an alias
is replaced silently only when its whole content hash is the packaged alias, an
accepted legacy or install-lock hash, or exactly what Spec Kit renders for that
command; any other content is refused with `ALIAS_HAS_LOCAL_EDITS` unless
`--replace-unrecognized-aliases` backs it up first. Workflow 1.6.2 makes host switching lossless: installs and upgrades keep every
installed host's skills and managed aliases instead of Spec Kit's registration
wiping the non-default host, and a new `workflow.py host [--use codex|claude]
[--preview]` reports host status or switches the default, re-registering
incomplete hosts and restoring aliases with rollback on failure. Workflow 1.6.1
closes evidence-gate gaps: a Verify receipt's CI evidence must be the
complete record `revalidate` writes and a diff review is bound to a hashed diff, long
GitHub issue titles are shortened instead of rejected, and `ci_gate.py --check-index`
flags evidence paths Git ignores and cross-feature fingerprints. Workflow 1.6.0 hardened
the evidence gate: input roles and assessed amendments on receipts, source-drift
classification through an affected-lanes hook, and CI runs accepted as Verify evidence
through `revalidate --check-run`. Workflow 1.5.0 added optional model-aware delegation. Workflow 1.4.0
added token usage per task, phase and feature to the progress
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

## Switching hosts

A project can have several Spec Kit integrations installed (for example `codex` and
`claude`, listed in `.specify/integration.json` `installed_integrations`), but Spec Kit
registers extension commands and skills only for the default one. Two things follow:

- `specify extension add --force`, which every install and upgrade runs, removes the
  reinstalled extension's skills from every other host folder.
- `specify integration use <host>` regenerates the new default's skills from upstream
  sources, which replaces Sanduq's managed aliases (`speckit-superpowers-bridge`,
  `speckit-scope`) with the upstream content, including the unguarded Bridge executor.

`install.py --apply` (and so `upgrade.py --apply`) therefore re-registers every
installed Codex or Claude host after the packages change: it runs
`specify integration use <other>` for each other host, then
`specify integration use <default>`, and puts `.specify/integration.json` and
`.specify/init-options.json` back byte for byte. It then writes the managed aliases into
every host folder and checks that each host has every command of the installed Sanduq
extensions, the same Sanduq preset overlays and the packaged aliases. Any gap
(`HOST_SKILLS_MISSING`, `HOST_OVERLAY_MISSING`, `ALIAS_NOT_RESTORED`) rolls the install
back. A single-host project runs no extra commands.

An existing alias file is judged by its whole content (CRLF normalised to LF), never by
its frontmatter alone, and by what it held before the transaction, so content Spec Kit
wrote during the transaction is replaced whenever the earlier content is. It is replaced
without asking only when its SHA-256 is one of:

- the packaged alias;
- an accepted legacy alias hash (`assets/legacy-*-alias-hashes.json`);
- the hash `.specify/workflow/install-lock.json` `aliases` recorded for that path;
- exactly the file Spec Kit generates for that command now. Sanduq copies `.specify`
  into an empty temporary project, runs `specify integration use <host>` there and
  compares the full hash of the alias it renders, so the upstream Bridge a bare
  `specify integration use` left behind is replaced. The project is not touched, and
  the render runs only when an alias matches none of the hashes above.

Anything else, such as local instructions added under unchanged upstream frontmatter, is
a local edit: `install.py`, `upgrade.py` and `workflow.py host --use` refuse with
`ALIAS_HAS_LOCAL_EDITS: <path>` before anything changes, and the previews list it. Move
the customization into Sanduq, or pass `--replace-unrecognized-aliases` to replace it
anyway: the file is first copied to `unrecognized-aliases/<path>` in that run's backup
folder (`.specify/workflow/backups/installs/<id>` or `.../hosts/<id>`), and the result
lists each path with its backup under `replaced_unrecognized_aliases`.

Change the default host with the supported command, never with a bare
`specify integration use`:

```text
python .specify/extensions/workflow/scripts/workflow.py host                       # status
python .specify/extensions/workflow/scripts/workflow.py host --use claude --preview
python .specify/extensions/workflow/scripts/workflow.py host --use claude
```

`host` with no option reports the default, the installed hosts, any missing skills or
aliases and the current dependency digest. `--use codex|claude` then:

1. refuses, without changing anything, when the host is not installed
   (`HOST_NOT_INSTALLED`), a stage claim is active, a legacy Bridge handoff is
   executing, an alias has local edits, an upgrade is running, or the delegation policy
   cannot route to the new host (below);
2. under the install and dispatch locks, snapshots the managed files and runs
   `specify integration use <host>`;
3. re-registers any other installed host that is missing managed skills (the repair
   for a project an earlier upgrade left incomplete; `--use <current default>` is
   therefore also the repair command doctor names);
4. restores the managed aliases in every host folder, reconciles the managed hooks and,
   when delegation is enabled, installs the delegate-task skill for the new host at
   `delegation.install_scope`;
5. verifies every host as the installer does, runs doctor and rolls everything back
   (`HOST_SWITCH_ROLLED_BACK`) when a check fails or doctor reports an error it did not
   report before the switch;
6. records the new host, aliases and digest in `.specify/workflow/install-lock.json`.

The result reports `dependency_digest.before`, `.after` and `.changed`. The digest
fingerprints `.specify/integration.json` and `.specify/init-options.json`, so a real
switch always changes it, and `checkpoints_to_migrate` lists every feature checkpoint
whose recorded digest no longer matches, with its branch and the exact commands
(`git switch <branch>`, `workflow.py migrate --feature <feature> --preview`, then
`migrate --feature <feature> --reason "Host switched from <old> to <new>"`);
`already_stale: true` marks one that did not match the digest before the switch either
and so needed `migrate` regardless. Until a
checkpoint is migrated, `claim` refuses it with `DEPENDENCY_CHANGED`.

The delegation check reads `.specify/workflow.yml` and never rewrites it. With
delegation enabled, `delegation.required_changes` lists what must change before the
switch can apply: a missing `delegation.models.<host>` tier, a tier model that names
the other host's model family (for example a `gpt-*` model under `models.claude`), a
route that follows the selected host but pins the other host's model, or an unknown
tier. `delegation.notes` lists routes that pin a harness explicitly and so keep
delegating to it after the switch. With delegation disabled the same findings are
`advisories` and do not block.

`--preview` changes nothing, runs no command and returns the same plan: the commands it
would run, the skills each host lacks now, the aliases it would restore, the delegation
findings, whether the digest will change and the checkpoints that will need `migrate`,
plus `blockers` and `can_apply`. The switch does not restore templates or scripts that
`specify integration use` refreshes outside the managed files; without `--force` Spec
Kit keeps customized ones. Doctor warns (`HOST_SKILLS_MISSING: <other host>`) when a
host other than the default has lost managed skills, with the repair command.

## State and recovery

Policy lives in `.specify/workflow.yml`. Feature state lives under
`specs/<feature>/workflow/`. Claims prevent concurrent stage ownership. Only an
explicit Specify claim can bind a new branch after verifying scope-source.json.
Use `recover` with the recorded token after inspecting possible remote writes;
use `migrate` after reviewing a dependency upgrade. Both preserve an audit trail.
A migration backs up the checkpoint, preserves still-current historical evidence and invalidates changed command selections. Use `--invalidate-from <stage>` when an upgrade changes a stage contract.
`migrate --preview` writes nothing and returns the exact `invalidated` and
`preserved_as_historical` lists the migration would record, with any blockers;
the applying `migrate` returns the saved `migrations[]` entry. Both load the
checkpoint through the bound-branch check, so run them on the feature's branch.

### Receipt contract (1.6.0)

Receipts stay backward-compatible: `inputs` is still a list of paths, and every
new field is optional (`input_roles`, `amendments`, `head`, `source_key`,
`ci_evidence`, `diff_reviewed`; see `schemas/receipt-v1.schema.json`). Reading a
1.3.0-1.5.x checkpoint needs no migration; continuing it after the upgrade needs
the reviewed `migrate` above, which invalidates nothing when no semantic policy
changed.

- **Input roles.** `input_roles: {"<path>": {"role": "dependency" | "consulted",
  "because": "<text>"}}` declares why each input is listed. Only dependencies
  decide whether a receipt is current and whether a later stage fails with
  `UPSTREAM_INPUT_CHANGED_DURING_STAGE`. A consulted input needs a `because`,
  keeps its recorded hash (it is never re-stamped) and, when it changes, is
  reported by `next` as `advisory_drift`. Evidence and a stage's required
  artifacts cannot be consulted. A receipt without roles is read as
  all-dependency, exactly as before. The policy key
  `receipts.require_input_roles` (default `false`) makes `complete` refuse an
  undeclared role for any input outside `specs/<feature>/` and
  `.specify/memory/`. Changing it is a policy change that invalidates no
  completed receipt; run `migrate` once to record the new policy digest.
- **Assessed amendments.** `workflow.py amend --feature specs/<feature> --stage
  <stage> --evidence <path> --reason "<why>" --assessment unchanged|changed`
  re-hashes that one evidence entry of that receipt and appends
  `{path, old_hash, new_hash, reason, assessment, actor, at}` to its
  `amendments[]`; every other hash is kept and the checkpoint is backed up.
  `unchanged` keeps the receipt current; `changed` marks Verify, Review and
  Ready (from the amended stage on) stale so they are re-recorded. A path that
  is not listed as that receipt's evidence is refused, as is an active claim.
  `ci_gate.py` accepts amended receipts and lists each amendment in its result.

### Source drift and CI evidence (1.6.0)

Verify, Review and Ready receipts inventory the source tree
(`source_fingerprints`), so before 1.6.0 any later commit to a source path
staled all three, even a README edit. They now also record `head` and
`source_key`: the canonical key `bunyan-source-key/1` of HEAD's tree, computed
by `scripts/source_key.py` from `git ls-tree -r -z --full-tree` on raw bytes
(paths under `.specify/`, `.agents/`, `.claude/`, `.codex/`, `specs/`,
`User-Manual/`, `docs/`, `graphify-out/`, `artifacts/` and every `*.md` are
left out). The key is recorded only when no source path differs from HEAD.
The shared fixture file `tests/fixtures/source-key.fixtures.json` is
byte-identical to the consumer's copy and pinned by SHA-256 in the tests.

Explicit fingerprints (inputs and evidence) keep their byte-hash check in every
case. When the source inventory drifted:

- **Affected-lane hook** (`ci.gate.affected_command`, optional). A command
  string or argv list that reads a JSON list of repository paths on stdin and
  prints `{"paths": {"<path>": ["<lane>", ...]}}`. A receipt with a
  `source_key` stays current when every drifted path maps to no lane and none of
  them is one of the receipt's explicit fingerprints. Markdown or committed
  artifacts therefore keep Review current; a test, workflow or product-source
  change stales it. A hook that fails, prints anything else or leaves a path out
  fails closed (the receipt is stale). Without the hook, and for a legacy
  receipt without `source_key`, the identity rule applies as before.
- **A CI run as Verify evidence** (`ci.gate.verification_check`, optional: the
  job name, or `{name, workflow, artifact_prefix}`; for Bunyan
  `"Bootstrap required lanes"`). `workflow.py revalidate --feature
  specs/<feature> --stage verify --check-run <run id> [--attempt <n>]` reads the
  run, its jobs and its plan artifact `<prefix>-<run>-<attempt>`
  (`verification-plan.json`, the consumer's verification-plan contract) through
  the GitHub REST API (`gh api`). It requires the run completed, not cancelled,
  with the named job concluding `success`; every plan field matching the run;
  the plan's tree equal to the head commit's tree through the API and locally;
  the plan's source key equal to the key recomputed locally and to the key of
  the current clean HEAD; the run's head a commit of this branch; the receipt's
  explicit fingerprints still byte-matching; and the run's lanes a superset of
  the lanes the hook assigns to the drifted source paths (so the hook is
  required when source drifted). It then writes `ci_evidence {run_id, head,
  source_key, tier, lanes, conclusion, ...}`, re-inventories
  `source_fingerprints` at HEAD and records a `revalidations[]` entry. Evidence,
  summary and `blocking_findings` are untouched. A run whose lanes miss a
  required lane records the gap, marks Verify `stale` (`ci-lane-gap`) and
  exits 1; a later run covering the lanes closes it. The gate accepts a Verify
  receipt whose inventory drifted while its CI run still covers the current
  source key, and only when its `ci_evidence` is the complete record
  `revalidate` writes: `run_id` and `attempt` positive integers, `head` 40-hex
  and the receipt's `head` (or a commit of it), `source_key` 64-hex, a
  non-empty `tier`, `lanes` and `required_lanes` lists of strings with
  `required_lanes` inside `lanes`, `conclusion: success` and an empty
  `lane_gap`. A missing or malformed field is not current (fail closed). The
  checkpoint is a committed file, so `ci_gate.py` never trusts the record
  alone: it always re-reads every run a Verify receipt is accepted through
  (the check job, the plan artifact, the tree and the source key) through the
  REST API, and fails closed when it cannot (`CI_EVIDENCE_UNREADABLE`: an API
  error, no token or no `gh`; `CI_VERIFICATION_CHECK_UNSET`: no
  `ci.gate.verification_check` to read it by) or when the run no longer
  matches (`CI_EVIDENCE_REJECTED`). The shipped gate job has
  `permissions: actions: read` and passes `GH_TOKEN` for this;
  `--verify-ci-evidence` (1.6.0) is still accepted and changes nothing.
- **Review** is revalidated only after an incremental review of the source
  diff `<review head>..HEAD` is recorded under `specs/<feature>/` with four
  lines: `Diff reviewed: <review head>..<HEAD>`, `Diff sha256: <hash>`,
  `Reviewer: <name>` (non-empty) and `Blocking findings: 0`. The hash binds the
  note to the exact diff, so a note written without the diff, or kept from an
  earlier range, is refused (`DIFF_REVIEW_HASH_MISSING`,
  `DIFF_REVIEW_HASH_MISMATCH`, `DIFF_REVIEW_REVIEWER_MISSING`, each printing
  the command below). It is the SHA-256 of the exact bytes this command
  prints, run in a POSIX shell (Git Bash on Windows):

  ```sh
  git -c core.quotePath=true diff-tree -r -p --binary --no-renames <review head> <HEAD> -- . \
    ':(exclude).specify/' ':(exclude).agents/' ':(exclude).claude/' ':(exclude).codex/' \
    ':(exclude)specs/' ':(exclude)User-Manual/' ':(exclude)docs/' ':(exclude)graphify-out/' \
    ':(exclude)artifacts/' ':(exclude,glob,icase)**/*.md' | sha256sum
  ```

  `diff-tree` is plumbing, so personal diff settings (prefixes, colour,
  renames, algorithm, external or textconv drivers) cannot change the bytes,
  and the pathspec keeps exactly the paths the source key counts (the
  source-key exclusions, and `*.md` in any case). `revalidate --stage review
  --diff-reviewed <file>` recomputes it, adds the file to the receipt's
  evidence (with its hash) and records `diff_reviewed` with `diff_sha256` and
  `reviewer`. A review receipt without `head` (written before 1.6.0) is
  re-recorded instead.
- **Ready**: `revalidate --stage ready` re-runs task completion, the
  task-issue mapping and the selected documentation freshness checks
  (`--base-ref` defaults to the bound target branch).

Revalidation needs every earlier stage current, no active claim and no
uncommitted source change; it never re-hashes an input or evidence path and is
never accepted on a `--reason` alone. A receipt a `changed` amendment staled is
re-recorded. Both `next` (`recovery`) and a failing gate (`STALE_RECEIPT: ...;
recovery: ...`) print the exact commands: `amend` for changed evidence,
`revalidate` where a checked route applies, otherwise the `claim`/`complete`
re-record. A typical sequence after a test change: push, wait for the check,
`revalidate --stage verify --check-run <run>`, review the diff and record it,
`revalidate --stage review --diff-reviewed <file>`, `revalidate --stage ready`,
then commit the checkpoint (an operational path, so the source key is unchanged).

Use `upgrade.py --version X.Y.Z` preview, then `--apply`, to update the workflow
package and its integrations with outer rollback. Local staged testing supports
`--packages <extracted-packages>`. See the [operating guide](../../docs/workflow-guide.md)
and [compatibility contract](../../docs/workflow-compatibility.md) for tested limits.

`task_issues.py` is dry-run by default. The core Tasks-to-Issues preset invokes it
with `--apply` within authorized issue work. Native sub-issues are identified by
repository, parent, feature and task ID; retries recover lost responses. Existing
Project mappings are adopted only after verifying native parent links. Unmapped
children block duplicate creation. `--sync-states` updates task issue completion
without changing the publication evidence. A task title (`T### : description`)
over GitHub's 256-character issue title limit is shortened to the headline
instead of rejected; the full description is always kept in the issue body.
Shortening is deterministic, so re-syncing an unchanged task recomputes the
same title and body and neither creates a duplicate issue nor rewrites it.

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
path; the command never stages files. When a missing path is one Git itself
ignores (e.g. a `*.log` match), the report names the exact `git add -f <path>`
recipe to recover it. It also warns, without failing the check, when a
receipt's recorded evidence references a path under another feature's
`specs/` directory (surfaced as `index_warnings` on that feature's gate
result) -- a likely copy/paste or fixture mistake worth reviewing before
publication. Target-branch source changes invalidate old verification even
when Git merges cleanly. Configure `workflow-evidence` as a required branch
check only when this project has deliberately selected Required mode;
otherwise leave its branch rule optional.

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
skill. A dangling symlink or Windows junction at the install target (its folder
is gone, for example on an unplugged drive) is moved aside the same way, as the
link itself with its target unchanged, and reported with the reason
`dangling link`. If the swap fails, the previous copy or link is restored, and
nothing that was already at the target is deleted. The install result,
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

If the driver's own `doctor` then fails, only the copy that failed is
refreshed, and only where it is: a real folder at the project or global
location Sanduq installs to is replaced in place and moved to that scope's
backup folder. Sanduq never installs at the configured scope instead, since the
failing copy would stay first in the search order and be refreshed again on
every dispatch. A copy Sanduq does not own (a `SANDUQ_DELEGATE_DRIVER`
override, a plugin copy, `~/.codex/skills`, or a symlinked folder or Windows
directory junction) is never replaced: `DELEGATE_SKILL_DOCTOR_FAILED` names its
path and says to repair it or remove it so a Sanduq install is used. A
symlinked or junctioned skill folder is otherwise a normal install; the driver
answers through the link.

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
| discovery | standard | gpt-6-sol | sonnet | scope, specify, clarify, plan, tasks |
| implementation | standard | gpt-6-sol | sonnet | tasks only |
| qa_author | standard | gpt-6-sol | sonnet | qa_analyze, verify (always, by default) |
| qa_collect | light | gpt-6-terra | haiku | `verify`, only when `delegation.fixed_collection_commands.verify` names its resolved command exactly (nothing by default); `[Collect]`-marked tasks |
| documentation | documentation | gpt-6-sol | opus | manual_analyze, manual_update, qa_document |
| review | review | gpt-6-sol | opus | analyze, review |
| coordination | high | gpt-6-astra | opus | taskstoissues, execute, ready, pr |

Discovery is never light: its default is standard (Scope and Plan may still be
overridden to high by policy), and the schema rejects a `light` preferred or
fallback tier anywhere in `delegation.routes.discovery`
(`DELEGATION_DISCOVERY_LIGHT_FORBIDDEN`). Coordination defaults to high (never
light): it claims and completes workflow stages and issues, not a cheap
default (standing rule 5, C2). `verify` is not a fixed script by default: it
selects tests, handles lane gaps and reports blocking findings (see the
workflow skill), so it always routes to `qa_author` unless the project's
`delegation.fixed_collection_commands` policy map names `verify` with the
exact command string it must still resolve to. That map's only allowed key is
`verify` (the schema's own `propertyNames` rejects any other stage, including
every discovery stage), and its value may never start with `workflow:` or
`speckit.` — not even `verify`'s own real default,
`"workflow:verification"`, since naming a stage's fixed pseudo-command or
skill invocation is never a genuinely fixed *external* script and would
silently restore the very inference this restriction exists to prevent.
`doctor` warns (`DELEGATION_LIGHT_TIER_ROUTE`) whenever `qa_author` or
`coordination` still routes to light in the loaded policy, whatever the
reason.

`qa` (pre-1.7) split into `qa_author` (authoring and analysing QA work,
standard) and `qa_collect` (running an existing, fixed check and reporting its
result, light-eligible and guarded; see below); the schema accepts either the
deprecated `qa` key or both `qa_author` and `qa_collect`, so it never rejects
what `load_policy` itself accepts. A policy that still has a single `qa` route
keeps working: reading it maps that route onto `qa_author` in place (unless
that route, the pre-1.7 default, had a light-tier candidate itself — then
`qa_author` resets to the new standard default instead, so a legacy install
never keeps sending authored QA work to the light tier) and adds a fresh,
light-eligible `qa_collect` route; nothing is rewritten to disk, and a ledger
with historical `"task_type": "qa"` entries stays readable.

The model names are editable preferences in `delegation.models`, not proof that
a CLI accepts them. Use `delegation.py route --feature specs/<feature> --id T001
--type implementation` to inspect a resolved route. For example, merge this
override into the existing `delegation:` block, keeping the generated `models:`
and all seven `routes:` entries:

```yaml
delegation:
  enabled: true
  install_scope: project
  overrides:
    specs/26-add-opt-in-model-aware-task-delegation/T001:
      preferred: {harness: claude, tier: high}
      fallbacks:
        - {harness: selected, model: null}
  fixed_collection_commands:
    verify: "scripts/run-fixed-verification.sh"
```

`fixed_collection_commands` is empty by default, so no stage is ever inferred
as `qa_collect`; naming `verify` there (the only key the schema allows) opts
it in only while its resolved command still matches the given string exactly,
and only for a genuinely external script — never a `workflow:` pseudo-command
or a `speckit.` skill invocation.

A task's type comes from an explicit marker in its leading tags: `[Impl]`,
`[Implementation]` or `[Code]`; `[QA]`, `[Test]`, `[Tests]` or `[TDD]` (routes
to `qa_author`, standard); `[Doc]`, `[Docs]`, `[Documentation]` or `[Manual]`;
`[Review]`. The implementation marker wins over the others and is the escape
for any task the rules below misread. Without a marker, only an unambiguous
leading action counts: "Run ... tests", "Write/Add ... tests for ...", "Test
<something>", "Capture ... screenshots"; "Document the ...", "Update
README/docs/guide/release notes" followed by a preposition or the end of the
line; "Review/Audit/Inspect <something>". These heuristics, and every explicit
marker above, route only to `qa_author`, `documentation` or `review`: nothing
is ever inferred as `qa_collect`. A documentation file named as the object also counts:
"Update README.md with setup instructions", "Update docs/quickstart.md", "Add
docs/api.md section for auth", "Document API endpoints in docs/api.md". That
means a README, changelog or contributing file with or without its extension,
a path under a top-level `docs/` folder, or any `.md`, `.mdx`, `.rst` or `.adoc`
file. Code under a nested docs folder ("Update src/docs/parser.py") and
"Document <thing>" without a documentation destination ("Document upload API")
stay implementation. When the word after "Test", "Review", "Audit" or "Inspect" names
something being built (log, queue, API, endpoint, service, page, component,
runner, pipeline and similar), the task is implementation: "Audit log
retention", "Review queue API endpoint", "Test runner integration". A check
that also asks for a code change ("Inspect the parser and fix the crash",
"Run tests and fix failures") is implementation too, as is "Create guide page
component". Anything else is implementation. Route type only chooses
a model. It never makes a run read-only, so a delegated review can write its
evidence and run checks.

`[Collect]` is the sole explicit route to `qa_collect`: run an existing,
fixed check and report its result, never author new tests or code. It is
checked before every other marker and every heuristic, so it is never inferred
from unmarked task text. Combined with any other explicit marker in the same
leading tag block (for example `[QA] [Collect]`) it is ambiguous and falls
back to implementation (standard), never a guess at which one wins. The other
explicit route to a light-eligible tier is a per-task override in
`delegation.overrides` naming `tier: light` for that task's identity: also
explicit, never a heuristic. `qa_document` (writing the QA test manual) is
`documentation`, not `qa_author` or `qa_collect`, since it is authored prose,
not a check to run.

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
- **Dispatcher bookkeeping is not worker work.** The driver measures the whole
  repository, and the dispatcher writes the tracked ledger while runs are live
  (its own start record, and every parallel start or collect). A changed ledger
  path is set aside only when the run worked in this checkout and the ledger
  still holds exactly the bytes a dispatcher last saved, recorded in
  `.specify/workflow/runtime/delegation-<hash>.written`. Before every save, the
  dispatcher compares the file with that record. If anything else wrote it (a
  worker, a rollback, or a ledger with no record at all), every `starting` or
  `running` attempt is stamped `ledger_foreign_write_seen`, and that run's
  ledger change stays a worker change even after a later dispatcher save has
  absorbed the edit. The attempt records the raw `changed_paths`, the `dispatcher_paths_changed` set
  aside, any `unattributed_bookkeeping_paths`, and the `worker_changed_paths`
  that fallback and stronger retry decisions use. Setting a path aside never
  makes an incomplete measurement complete. `tasks.md` is not set aside: the
  driver reports paths, not content, so a marker refresh cannot be told apart
  from a worker edit. Annotation happens at claims and stage completion, not
  during task runs.
- **Route snapshots.** A running attempt keeps its start-time route when YAML
  changes. Each claimed stage records its route in the checkpoint.

`collect` follows a `replacement` run ID when one was started. Concurrent
dispatchers serialize their ledger writes, so parallel starts and collects never
lose an attempt or start the same work twice. A busy ledger returns the
retryable `DELEGATION_LEDGER_BUSY` after 15 seconds, naming the lock owner's
process and host.

An upgrade or install rolls back every ledger if it fails, so neither runs
while an attempt is live and no dispatcher writes while one runs. `start`,
`collect`, `reassign`, `recover`, `abandon` and a skill install refuse with the
`WORKFLOW_UPGRADE_IN_PROGRESS` while
`.specify/workflow/runtime/upgrade.lock` or `install.lock` exists. They check
inside the ledger or skill-install lock. The error names the lock and the
process ID recorded in it. These locks are never recovered automatically. If
that process is still running, retry once it finishes. If it is not
(`tasklist /FI "PID eq <pid>"` on Windows, `ps -p <pid>` elsewhere), the
upgrade or install crashed: delete the lock file and rerun the upgrade or
install, because its rollback may not have completed. After taking its own lock, `upgrade.py`
and `install.py --apply` wait for any skill install in progress and take each
feature's ledger lock in turn. They refuse with `DELEGATION_ATTEMPTS_ACTIVE`,
naming each run or intent, while any attempt is `starting` or `running`.
Collect, recover or abandon those first. The one exception is a start that had
already reserved its attempt when the upgrade began: it may still record its
run, because that reservation has already made the upgrade refuse.

The ledger lock is `.specify/workflow/runtime/delegation-<hash>.lock` and records
its owner's process ID, host and a token. A lock whose owner has exited on this
host is recovered automatically, and so is a lock whose owner record was never
written once it is 60 seconds old. A lock held by a live process, or by any
process on another host, is never taken. Recovery captures the lock with a
single rename and puts it back if it turned out to belong to a live owner. A
dispatcher that finds its own lock replaced refuses to save the ledger. If the
owner's process ID was reused by an unrelated process, the lock looks live:
confirm the named process is not a dispatcher, then delete the lock file.
On Windows, releasing a lock retries brief file-sharing conflicts while
checking the owner token before each attempt. A persistent conflict returns
`DELEGATION_LOCK_RELEASE_BUSY` and names the lock file; a new owner's lock is
never removed by the former owner.

### Light-tier evidence and `accept`

A light-tier run is never taken on trust. The guard applies whenever the
selected candidate's own tier is `light`; the candidate has no tier at all
(a fallback chosen by explicit `model`, or an override) and the task's
classified type is `qa_collect` (an explicit standard-or-above tier — for
example a `reassign` escalation — is exempt from this one rule, since a
task's classification never changes on reassignment and applying it
unconditionally would mean a `qa_collect` task could never actually resolve
through a standard-tier `reassign`); or the requested or harness-reported
actual model matches that harness's configured `light` model *by family*: the
same identifier, or one fully containing the other as a whole dash-delimited
token run that includes at least one non-generic token
(`claude-haiku-4-5-20260101` matches the configured alias `haiku`; exact
string equality alone let a real light-tier run escape whenever the harness
reported its full name instead of the alias). A shared provider prefix or
trailing qualifier alone is never enough — `claude-opus-4-7` does not match
`claude-haiku-4-5`, `gpt-6-sol` does not match the bare family prefix
`gpt-6`, and bare `codex` does not match `gpt-6-sol-codex` (`codex`,
`openai` and `anthropic`, like the provider names, are generic tokens on
their own). A contained run immediately followed by an effort word (`high`
or `xhigh` — not `max`, `pro` or `large`, which are ordinary size words a
real light-tier variant can carry, such as `haiku-large-ctx` or
`gpt-6-terra-pro`) is rejected only when the *fuller* identifier is itself
one of the harness's own configured models for some other tier: `o4-mini`
fails to match `o4-mini-high` only when policy configures `o4-mini-high` as
some other tier's model, confirming it is a genuinely different,
higher-effort tier rather than an incidental suffix. Without that
confirmation the match still holds — a wrongly rejected match would let a
light-tier run skip the guard entirely, which is worse than an unnecessary
guard on a model that turns out to be genuinely different. `collect` records the driver's
raw `successful`/`failed`/`abandoned` verdict as usual, but when the guard
applies and the verdict is `successful`, the ledger outcome becomes
`unverified` unless the worker's own summary names a produced-file list (as
JSON `{"files": ["<path>", ...]}`) whose every path is both inside the
task's declared owned paths (see below) and among the paths the driver
itself measured this run as having changed — an unrelated, pre-existing file
such as a checked-in README can never pass just because the summary names
it. Raw reporter counts in a worker's own summary are never accepted at
all, at any time: only `accept`'s independently run command, or a future
driver-captured command transcript, may supply counts. `unverified` is a
terminal ledger status like `successful`, `failed` and `abandoned`; a note
never changes it, because nothing in the ledger accepts free text as
evidence, and neither `complete` nor the Ready task gate accepts one on a
bare claim of success either (see below). Collecting an already-terminal run
again (one `accept` already resolved, in particular) returns the recorded
result unchanged rather than re-running the driver and the guard a second
time, which could otherwise downgrade an accepted `successful` back to
`unverified`.

Three ways resolve an `unverified` attempt:

- **`reassign`** to a standard (or stronger) tier, as for any other terminal
  result; the replacement run's own evidence resolves the identity once
  collected.
- **`delegate_dispatch.py accept --feature specs/<feature> --run-id <id>
  --command "<acceptance command>" --expect counts|files [--timeout <seconds>]
  [--owned <path>]`** runs that command itself, independently of the worker's
  own report, and judges its output by the same schema below. The command
  runs with no shell: on POSIX, `shlex.split` into an argv list (there is no
  shell here to parse quoting, so this module must); on Windows, the raw
  command string is passed straight to `subprocess`, which hands it to
  `CreateProcess` directly (never through `cmd.exe`) for Windows' own native
  quoting — `shlex.split(..., posix=False)` would leave literal quote
  characters inside each argument, which is wrong once that is one argv
  element. It runs inside the task's own recorded working directory, or, when
  that directory is outside the project root (an isolated worktree given to
  `start --cwd`), a worktree `git worktree list --porcelain` itself confirms
  belongs to this repository — never an arbitrary caller-supplied path.
  stdout and stderr are captured to spooled temp files rather than in-memory
  pipes, under a bounded timeout (default 1800s, max 28800s) with only the
  first 200,000 bytes of each stream ever read back, so a runaway or hostile
  command cannot exhaust the dispatcher's own memory; on a timeout the whole
  process tree is killed (Windows `taskkill /T /F /PID`, POSIX its own
  process group), not just the immediate child, before anything is read.
  It refuses outright, before running anything, when the command's own
  executable is (or, unresolved, would resolve on PATH to) a Windows
  `.bat`/`.cmd` shim (`DELEGATION_ACCEPT_COMMAND_IS_SHIM`): Windows always
  routes a batch file through `cmd.exe` even though this dispatcher never
  sets `shell=True` and never builds a shell command line itself, reopening
  the very class of injection risk `shell=False` is meant to close (the
  "BatBadBut" vulnerability class) — an `npx` invocation resolves to
  `npx.cmd` on Windows, for example, so run the underlying executable
  directly instead (`node <script>.js` rather than the `npx.cmd` shim).
  It accepts only when the command exits `0` and, for `counts`, parses to
  `total > 0` and `failed == 0` (see the reporter formats below), or, for
  `files`, every path exists, is non-empty and resolves inside a declared
  owned path: an absolute path, a literal `..` segment, a missing or empty
  file, or a symlink whose real target lands outside every owned root are all
  rejected (paths are fully resolved, following any symlink to its real
  location, before containment is checked). Each accepted file's evidence
  records its sha256 and size. Exit-zero empty output, a bare free-text note
  with no structured evidence, an unparsable result, a failed command and a
  timeout all leave the attempt `unverified`. Every attempt, accepted or not,
  is recorded under the ledger attempt's `acceptance_attempts`: the command,
  exit code, whether it timed out or its output was truncated, and the
  (capped) raw output. `accept` refuses with `DELEGATION_RUN_NOT_UNVERIFIED`
  on any run that is not currently `unverified`.

**Owned paths.** A light-tier result's file evidence (in a worker's summary or
in `accept`'s command output) must resolve inside the task's declared owned
paths, not merely its whole working directory. A start is required to
declare `--owned <path>` itself (repeatable) — there is no silent default to
the whole `--cwd` — whenever *any* candidate anywhere in the route's fallback
chain is light, not only the preferred one (a fallback beyond the first can
still land the run on the light tier); omitting `--owned` there is refused
with `DELEGATION_OWNED_PATHS_REQUIRED`. They carry forward unchanged across
an automatic stronger retry or a manual `reassign`. `accept --owned <path>`
narrows them for that one acceptance call only, without changing what is
recorded on the attempt; it can never widen them past what was recorded at
`start` (`DELEGATION_ACCEPT_OWNED_MUST_NARROW` otherwise).

**Reporter count formats** (`accept --expect counts`, and JSON forms only for
a worker's own self-report, which never supplies counts at all): JSON
`{"total": N, "passed": N, "failed": N}` (`passed` optional, computed as
`total - failed`) or JUnit-style `{"tests": N, "failures": N, "errors": N}`
(`errors` optional; `failed = failures + errors`); or one of seven text
formats, each requiring that reporter's own real framing so a bare "N passed,
N failed" fragment pasted out of context (or invented) never parses as a
false success: pytest's `"===== ... in N.Ns ====="` summary bar; Jest's
`"Tests: ..."` line; a JUnit/Maven aggregate `"Results:"` section, including
the real Maven layout with `[INFO]`/`[ERROR]` line prefixes and a blank,
log-prefixed line between `"Results:"` and the aggregate (an earlier
per-class `"Tests run:"` line with no `"Results:"` header is ignored, even
elsewhere in the same transcript); Python unittest's `"Ran N tests ..."`
followed by `"OK"` or `"FAILED (...)"`; dotnet test's `"Passed!"`/`"Failed!"`
summary line, and its older VSTest console form (`"Total tests: N"` with
`Passed`/`Failed` on the same or following lines); and node's `--test`
runner's `"# tests"`/`"# pass"`/`"# fail"` lines (not necessarily adjacent —
real output interleaves other fields between them). Every text format reads
its outcomes independently of their order within the line or block. Most
formats use only their last occurrence (a rerun's final state, not an
earlier attempt pasted earlier in the same log); pytest's bar and dotnet's
`"Passed!"`/`"Failed!"` line instead use the last occurrence that has
`failed > 0`, if any, else their own last occurrence: a "rerun failed tests
only" pytest invocation, or one failing project in a multi-project dotnet
solution, can print a real failure and then a later, clean bar or project,
and taking the literal last one would silently report the whole run as
passing. If more than one format produces a result and they disagree, the
parse is ambiguous and returns unparsed rather than guessing between them.

**Enforcement.** A delegated stage's claim recording a route is not itself
completion: `complete` requires the dispatcher's own ledger — never the
receipt's self-report — to show the claimed stage's latest delegated attempt
(following any `reassign` chain to its terminal end) as `successful` and
started under this exact claim (its recorded `claim_token`, from `start`,
matching the claim being completed — a successful attempt left over from an
earlier claim of the same stage cannot satisfy a different, later re-claim;
a legacy attempt recorded before `claim_token` existed has none and can
never match, so re-delegate the stage once after upgrading), and refuses
with `DELEGATION_STAGE_NOT_VERIFIED` otherwise. The Ready task gate
(`ci_gate.py`'s `tasks` rule, and `revalidate --stage ready`) similarly
refuses a checked `[x]` task whose latest delegated attempt is anything but
`successful` (running, starting, failed, abandoned or unverified) with
`DELEGATION_TASK_UNVERIFIED`, naming every such task — including one with
**no** attempt at all, not only one that exists and failed.

**A checked task with no attempt at all: adopt it, never exempt it.**
`tasks.md` never timestamps an individual checkbox, so the gate cannot on
its own tell a task done before delegation was enabled for this feature from
one that simply skipped the dispatcher after delegation was already on. Two
earlier exemptions tried to paper over that gap and were both removed as
reviewed bypasses (round 7): a stage-wide `delegation_enabled_for_execute`
field stamped once on the `execute` receipt — mutable, unfingerprinted, and
never read by any digest or signature — would wave through *every* task in
the stage on a single flag; and an `orchestrator-executed` command let
anyone holding the CLI (a worker included, since nothing separately enforced
who called it) self-certify a specific task as done outside the dispatcher
with a free-text reason nothing checked. Neither is read any more. A
checkpoint or ledger still carrying either from that release is inert: it
does not exempt anything, and `ready_checks` no longer imports the function
that used to read it.

The only way a checked task without its own dispatcher attempt now earns
Ready is `delegate_dispatch.py adopt --feature <f> --id <task> --command
"<acceptance check>" --expect counts|files [--owned <path>]` — evidence,
not an assertion. It is for a task genuinely done before delegation existed
for this feature (or otherwise never dispatched) and refuses outright with
`DELEGATION_ADOPT_HAS_ATTEMPT` the moment *any* attempt already exists for
that task, whatever its status: a task once started, accepted, or left
unverified already has its own resolution path (`accept` or `reassign`), and
`adopt` must never open a second, easier one next to it. Otherwise it runs
`--command` with exactly `accept`'s own machinery — no shell
(`build_command_argv`), the BatBadBut shim refusal, a bounded timeout, a
hard output cap with the process tree killed on timeout (`run_capped`), and
the same `counts`/`files` schema, owned-path containment and per-file
sha256 evidence — and only a passing check records a new attempt with
`status: 'successful'` and `adopted: true`; a failing command, a timeout, or
an exit-zero run with no parsable or in-bounds evidence records
`'unverified'` instead, exactly like `accept`. Either way the attempt lands
in `delegations.json` like any other and `latest_attempt` reads it like any
other: the Ready gate never special-cases an adopted attempt, because it
does not need to. Like `trust-reset`, `adopt` is orchestrator-only — every
worker brief forbids `delegate_dispatch.py` entirely, `adopt` included — a
worker must never be the one judging whether its own unattempted work now
counts as verified.

A project that enables delegation mid-feature adopts each already-checked
task with its own acceptance check, once, rather than relying on any
checkpoint field or self-report to wave the whole batch through.

**Ledger trust.** Both `complete` and the Ready gate also read
`delegation.ledger_trust_state`, a tri-state check: `'trusted'` (the local
`.written` marker matches the ledger's current bytes); `'unverified-local'`
(no local marker at all — the normal state for a CI checkout or a fresh
clone, since `delegations.json` is committed but its marker lives in
gitignored runtime state); or `'untrusted'` (a marker that disagrees, or a
persisted tamper flag not yet cleared). Only `'unverified-local'` is a
warning: it is recorded as `delegation_ledger_trust` on the completed
receipt and appended to `ci_gate.py`'s `warnings`, while task and stage
status are still fully enforced. `'untrusted'` still refuses with
`DELEGATION_LEDGER_UNTRUSTED`. `ci_gate.py` prints every collected warning to
stderr, and appends it to `$GITHUB_STEP_SUMMARY` when the runner sets that
variable, so a reviewer sees `DELEGATION_LEDGER_TRUST_UNVERIFIED_LOCAL` even
though it never changes the gate's exit code. Note that deleting the local
`.written` marker by hand does not clear a detected tamper honestly — it
downgrades what would read as `'untrusted'` back down to `'unverified-local'`
(no marker to disagree with), which is exactly why detecting a genuine
tamper is sticky (below) rather than relying on the marker's mere presence.

Detecting a genuine tamper (a marker that existed and now disagrees) persists
a feature-level flag that a later, perfectly legitimate dispatcher write does
**not** clear on its own — only `delegate_dispatch.py trust-reset --feature
<f> --reason "<text>"` does, after a human reviews exactly what changed; it
records the actor, time, reason and the exact bytes on both sides.
**`trust-reset` is an orchestrator-only, human-authorised command, never a
worker's**: both `stage_brief` and `task_brief` explicitly forbid a worker
from running any `delegate_dispatch.py` command (`start`, `collect`,
`accept`, `reassign`, `recover`, `abandon` or `trust-reset`) at all — on its
own run, another run, or another task. `trust-reset` itself also refuses
outright with `DELEGATION_TRUST_RESET_NOTHING_TO_RESET` when there is no
persisted tamper flag to clear: it only ever clears an *already-detected*
tamper, and never mints a fresh `'trusted'` marker over the ledger's current
bytes just because it was asked to — the exact probe this closes is a
hand-edit followed by deleting the local marker (so no mismatch is ever
detected) and then calling `trust-reset`, hoping it blesses the edit; it now
refuses. It also refuses with `DELEGATION_TRUST_RESET_ATTEMPTS_ACTIVE` while
any attempt for the feature is `starting` or `running`, so a reset can never
race a live dispatch that might still change the very bytes under review.

**This detects accidental and local tampering only.** `delegations.json` is a
tracked, committed file: anyone who can commit to the repository can commit a
fabricated ledger just as easily as a legitimate one, and this mechanism
cannot tell the difference. CI integrity for delegation evidence ultimately
rests on code review of that commit, the same as any other tracked file — not
on `ledger_trust_state`, which exists only to catch an accidental or purely
local hand-edit on one machine.

### History and evidence

The tracked `specs/<feature>/workflow/delegations.json` records every attempt,
requested route, skipped or fallback decision, start failure, abandoned intent,
result and token usage. It survives upgrades and is included in installer
rollback snapshots. Rollback snapshots take a project `delegate-task` skill
folder's own files but not its raw `runs/` or `node_modules/` folders. A
symlinked skill folder is recorded and restored as the link itself, never
followed, and always as a folder link, even while its target is missing. A
Windows directory junction (`mklink /J`) is handled the same way and is
restored as a junction, never as a symlink. Rollback writes the junction's
reparse data directly rather than running `mklink` through `cmd`, so a target
path containing `%NAME%`, `&`, `^` or `!` comes back exactly, and a missing
target is not created. Rollback makes each junction before
it changes anything; if one cannot be made, it stops with
`ROLLBACK_JUNCTION_FAILED`, leaves every file and the moved-aside original link
as they are, and keeps the backup. A link is restored only where rollback leaves no unmanaged file behind
(`ROLLBACK_CONFLICT` otherwise). The requested model and the model the harness reported are
kept apart. When a harness does not report its actual model, the ledger and
report say `unverified`; the requested model is never shown as measured fact.
Raw prompts and logs stay in the git-ignored `.delegate/runs/`, and
`progress.py sync` rebuilds the local HTML history view from the ledger.
