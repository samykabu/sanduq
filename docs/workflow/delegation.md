# Optional model-aware delegation

This page is the full reference for routing workflow stages and tasks to another agent CLI and model. Read it before you turn delegation on, change routes, or recover a delegated run. The routing script is [`delegation.py`](../../extensions/workflow/scripts/delegation.py) and the run manager is [`delegate_dispatch.py`](../../extensions/workflow/scripts/delegate_dispatch.py).

Back to the [Workflow guide](../../extensions/workflow/README.md).

Delegation is off by default. It routes workflow stages and implementation
tasks to a preferred agent CLI and model through the bundled `delegate-task`
skill, records every attempt, and leaves the dispatcher in charge of claims and
receipts. A successful delegated run is candidate evidence for the orchestrator
to inspect, never a passed stage or a completed task.

## Turning it on, off or rerouting later

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

## Which installed skill is used

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

## Routes, defaults and overrides

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

## Starting, collecting and recovering

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

## Light-tier evidence and `accept`

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
such as a checked-in README can never pass only because the summary names
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
  process group), not only the immediate child, before anything is read.
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
one that skipped the dispatcher after delegation was already on. Two
earlier exemptions tried to paper over that gap and were both removed as
reviewed bypasses: a stage-wide `delegation_enabled_for_execute`
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
not an assertion. Before running anything it requires `<task>` to actually
exist in `tasks.md` and be currently checked (`DELEGATION_ADOPT_TASK_UNKNOWN`
or `DELEGATION_ADOPT_TASK_NOT_CHECKED` otherwise), closing the gap
where adopting an absent id, then later adding a different checked task
under that same id, let the earlier adoption ride to Ready for work it
never checked at all, and it records on the new attempt a binding to that
task's current content: a sha256 of the task line with its checkbox state
removed and whitespace normalised (`delegation.task_line_content_sha256`).
The Ready gate re-hashes the live line at completion time and refuses with
`DELEGATION_ADOPT_TASK_CHANGED` on a mismatch, so editing the task (or
swapping in different work under the same id) after adoption cannot ride
the earlier check through.

It refuses outright with `DELEGATION_ADOPT_HAS_ATTEMPT` unless *every*
existing attempt for the task is itself an unverified adoption: a fresh task
has none at all, and a task whose only history is a failed `adopt` may be
re-adopted with a corrected check — the supported recovery, since `reassign`
cannot act on an adopted attempt (below). Any other existing attempt —
started, accepted, or a successful adoption already on record — already has
its own resolution path (`accept` for an unverified dispatched result,
`reassign` for a stuck one, and a fresh `adopt` call is pointless once one
has already succeeded), and `adopt` must never open a second, easier route
around it.

Otherwise it runs `--command` with exactly `accept`'s own machinery — no
shell (`build_command_argv`), the BatBadBut shim refusal, a bounded timeout,
a hard output cap with the process tree killed on timeout (`run_capped`),
and the same `counts`/`files` schema, owned-path containment and per-file
sha256 evidence — and only a passing check records a new attempt with
`status: 'successful'` and `adopted: true`; a failing command, a timeout, or
an exit-zero run with no parsable or in-bounds evidence records
`'unverified'` instead, exactly like `accept`. Either way the attempt lands
in `delegations.json` like any other and `latest_attempt` reads it like any
other: the Ready gate never special-cases an adopted attempt beyond the
content binding above. The command runs from the repo root, not pinned to the feature directory as an earlier release had
it — an aggregate, repo-root-relative check can now run at all — while the
feature directory remains the *default* owned root `--expect files`
validates against when `--owned` is not given, unchanged in effect. Like
`trust-reset`, `adopt` is orchestrator-only — every *task* worker brief
forbids `delegate_dispatch.py` entirely, `adopt` included, and a worker must
never be the one judging whether its own unattempted work now counts as
verified. The delegated Execute stage's own brief is the one exception (see
below): it names `adopt` among the commands it may run for its own
feature's tasks, because for it that self-judgement *is* the job.

**Defence in depth: a worker cannot call back into the dispatcher.**
`driver_env` sets one of two, mutually exclusive environment shapes for
every driver subprocess it launches. A plain worker -- any task, and any stage other
than `execute` -- inherits `SANDUQ_DELEGATED_RUN` (this dispatch's own
intent id); `adopt`, `accept`, `reassign`, `trust-reset`, `start` and
`collect` all refuse it outright with `DELEGATION_WORKER_CONTEXT` (a worker
running `delegate_dispatch.py adopt` on its own checked-but-unattempted
task, or `accept` on its own unverified result, would otherwise be able to
self-certify its own work with a fabricated command).

**The delegated Execute stage is the one exception.** Its own brief tells
it to dispatch and resolve bounded task workers with exactly those
commands (`references/execution*.md`), so it needs a different scope, not
a blanket refusal: launching `stage:execute` sets
`SANDUQ_DELEGATED_ROLE=orchestrator` plus `SANDUQ_DELEGATED_FEATURE`
instead, never `SANDUQ_DELEGATED_RUN`. Under that role,
`require_not_worker_context` allows `start`, `collect`, `accept`,
`reassign` and `adopt` only for a `T###` identity of that same feature;
`trust-reset`, any `stage:*` identity, and any other feature all still
refuse, now with `DELEGATION_ORCHESTRATOR_SCOPE`. The task workers *it*
launches get an ordinary worker environment from their own `launch()` call
-- `SANDUQ_DELEGATED_RUN` only, with `SANDUQ_DELEGATED_ROLE` and
`SANDUQ_DELEGATED_FEATURE` explicitly stripped from the child environment
so a task worker never inherits its orchestrator's own scope. Either
shape is defence in depth, not a security boundary: a worker or
orchestrator could unset its variables before invoking the dispatcher, so
each brief's own instruction (the Execute brief states the narrower rule in
place of the blanket one; every other brief keeps the blanket one) remains
the primary control. All three `SANDUQ_DELEGATED_*` names are passed to the
driver as `--keep-env` on every launch, so a future `--clean-env` launch
does not silently drop whichever of them was actually set.

**Visibility: every orchestrator-run check is a Ready-gate warning.**
Whenever the Ready gate accepts a task because the orchestrator itself ran
and judged a check — `adopt` for a task with no dispatcher attempt at all,
`accept` for an unverified light-tier result — it appends a warning a
reviewer will actually see, not only a passing check silently indistinguishable
from a worker's own verified attempt: `DELEGATION_TASK_ADOPTED:
<task> via "<command>" (<expect>, exit <code>)` or `DELEGATION_TASK_ACCEPTED:
<task> via "<command>" (<expect>, exit <code>)`. `ci_gate.py` already prints
every warning here to stderr and appends it to `$GITHUB_STEP_SUMMARY` when
the runner sets that variable, exactly as it does for
`DELEGATION_LEDGER_TRUST_UNVERIFIED_LOCAL`, so this needed no separate gate
change. **A reviewer must actually read these two lines when they appear**:
unlike a worker's own delegated attempt, an
orchestrator-context `adopt` or `accept` trusts the orchestrator's own
choice of acceptance command outright, with no independent dispatch to
cross-check it against -- the warning is the only place that trust is
visible, and skipping it defeats the whole point of surfacing it.

**`reassign` and an adopted attempt.** An adopted attempt has no dispatcher
route, task file or retry count to escalate from — it was never dispatched
in the first place — so `reassign` refuses it outright with
`DELEGATION_REASSIGN_ADOPTED_UNSUPPORTED` (it used to
crash with a bare `KeyError` on `retry_count` instead) and points at the two
real recoveries: re-run `adopt` with a corrected acceptance check, or `start`
the task normally to create a real dispatched attempt `reassign` can act on.

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
bytes only because it was asked to — the exact probe this closes is a
hand-edit followed by deleting the local marker (so no mismatch is ever
detected) and then calling `trust-reset`, hoping it blesses the edit; it now
refuses. It also refuses with `DELEGATION_TRUST_RESET_ATTEMPTS_ACTIVE` while
any attempt for the feature is `starting` or `running`, so a reset can never
race a live dispatch that might still change the very bytes under review.

**This detects accidental and local tampering only.** `delegations.json` is a
tracked, committed file: anyone who can commit to the repository can commit a
fabricated ledger as easily as a legitimate one, and this mechanism
cannot tell the difference. CI integrity for delegation evidence ultimately
rests on code review of that commit, the same as any other tracked file — not
on `ledger_trust_state`, which exists only to catch an accidental or purely
local hand-edit on one machine.

## History and evidence

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
Every `progress.py` subcommand accepts `--summary` (one line, e.g.
`ok done=<n> total=<n> pending=<n> running=<n> blocked=<n>`, or `error <message>`
on a validation failure) and `--json` (the full `state.json` content) as
alternatives to the default output (only the report path); `--summary` and
`--json` together is rejected, and exit codes are unchanged either way.
