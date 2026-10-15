# Invoking the claimed command: delegation and decisions

The stage loop's step 4 in full: how to invoke the claimed command, route it
through delegation when enabled, and pause for a material decision.

## Opt-in lean execution

Select `lean_execution.enabled: true` in `.specify/workflow.yml` to use one
lifecycle coordinator. That coordinator keeps claims, scheduling, integration,
receipts and publication. Do not create or dispatch another coordinator. Claims
for Execute, Tasks-to-Issues, Ready and PR return `execution_owner: coordinator`
without a model route; invoke their mechanics in the selected host. An exact
`delegation.fixed_collection_commands.verify` match also belongs to the
coordinator. Semantic stages retain their delegation routes and successful
attempt/claim-token checks. Every receipt still needs real inputs and evidence.
Absent or disabled lean policy retains the legacy protocol below.

```yaml
lean_execution:
  enabled: true
  timeout_min_seconds: 300
  timeout_max_seconds: 7200
  finalization_seconds: 120
  verification_plan: specs/42-booking-refund/verification-plan.json
  preflight_manifest: specs/42-booking-refund/preflight.json
  scope_analysis: specs/42-booking-refund/scope-analysis.json
```

Only `enabled` is required. Bounds must satisfy finalization < minimum <=
maximum <= 28800 seconds. `verification_plan` is optional; absent selection
retains the whole-source receipt freshness rule. See `verification-plan.md`.
`preflight_manifest` selects aggregate deterministic checks for doctor and before
Execute or later claims. Manifest paths are relative to the manifest directory;
findings return together and block execution. `scope_analysis` is an explicit
initial analysis path. Without one, Scope claim output contains `<analysis.json>`
which must be replaced with the actual new analysis; it never guesses an existing
analysis. Revalidation commands carry no initial flags. `claim.environment`
contains the token/session for native commands and worker launch preserves them.

Use `workflow.py status --feature specs/<feature> --runs <explicit-run-root>`
(repeat `--runs` for worktrees) for compact elapsed/latest-event/next-action and
per-harness usage. Current feature ledger status and independently accepted
evidence appear separately from harness status. Missing acceptance or task verdict
stays unknown; a successful harness is not silently converted to task acceptance.

Failure domain is explicit attribution, separate from technical provenance:
`delegate_dispatch.py classify --feature specs/<feature> --run-id <id>
--attribution <JSON>` accepts `domain` (product, test, environment, workflow,
owner-interruption or unknown), `actor`, concrete `reason` and existing `evidence`.
It fingerprints the evidence and preserves the raw driver provenance and status.
Arbitrary summary prose never supplies a domain.

Deadline guidance and incremental handoffs are worker-context instructions:
comparable elapsed samples select a bounded timeout, and the brief carries the
finalization reserve, correction and diagnosis. The current driver receives its
existing overall timeout. There is no new early deadline signal, cancellation
callback or enforced incremental artifact checkpoint; the worker must write its
partial handoff before the existing watchdog. P07 broad receipt amendment remains
deferred; this package does not add it.

Every lean launch requires `--deliverable "<artifact and acceptance result>"`.
A second attempt for the same identity also needs `--correction-plan "<specific
correction and check>"`. Further attempts require `--diagnosis <project-relative
JSON>` with `cause`, `evidence` (an existing repository file), and `change`.
Cause and change must describe concrete work; a generic retry reason is
insufficient. Admission is checked under the ledger lock, so starting again
with another model or run ID cannot reset the correction history.

Lean launches try the selected candidate only; choose another eligible route
explicitly when a provider or startup failure prevents it running. Lean
collection never automatically escalates failed work. `reassign --reason
"<specific correction>" [--diagnosis <JSON>]` keeps the prior candidate,
including an explicit pin. Eligible configured routes remain unchanged.
Failure categories distinguish provider rejection, harness failure, timeout,
task failure, missing evidence, abandonment and unknown cause. Unknown cause
stays unknown; a timeout observed while collecting is not a failed task.
Start/collect expose bounded `timeout_guidance` from comparable successful runs
of the same work type and candidate, or mark the estimate's usage unknown.
Reserve `finalization_seconds` for an honest partial handoff listing changed
files, executed checks and remaining work. Recover uncertain starts and collect
live runs before admitting replacements.

Invoke the selected command in this host using its installed skill/command registration.
When `delegation.enabled` is true, instead use the claim's `delegation` route:
run `delegate_dispatch.py start --feature specs/<feature> --id stage:<stage>
--claim-token <token>`, then `delegate_dispatch.py collect --feature
specs/<feature> --run-id <id>` until terminal. If it returns a `replacement`,
collect that new run ID. Inspect actual outputs and checks before writing and
completing the normal stage receipt. A successful delegate result is candidate
evidence, not a passed stage. Failed, abandoned or unresolved work keeps the
claim active. The adapter distinguishes requested from harness-reported models;
an unreported actual model remains unverified. Disabled mode ignores old
routing tags and runs with the user's selected host model.
A rejected model is followed by the configured fallback automatically; a
start that provably created no run, or whose driver exited 5 with proof that
no agent launched, moves to the next candidate. On
`DELEGATION_START_UNCERTAIN`, never start the stage again: run
`delegate_dispatch.py recover --feature specs/<feature> --intent-id <id>`.
If it binds a run, collect it. If it reports `found: false`, close the intent
with `delegate_dispatch.py abandon --feature specs/<feature> --intent-id <id>
--reason "<why>"` and then start again; `abandon` refuses while a driver run
exists or a start may still be in flight. On `DELEGATION_LEDGER_BUSY` or
`DELEGATE_SKILL_INSTALL_BUSY`, retry the same command; a lock left by a dead
dispatcher on this host is recovered automatically, so never delete a lock
file whose named owner process is still running. An observation timeout is not a failed run.
To choose one candidate yourself, add `--harness <codex|claude> --model <id>` to `start`, always
together. The pair must match a candidate of the route already resolved for that task or frozen in
the stage claim, so it selects among eligible routes and never adds one. Picking Opus for a
discovery stage does not make it eligible for another stage; each stage keeps its own allowlist.
A pair that is missing half, unknown, not in the route or whose harness is unavailable fails before
any intent or launch. After an explicit choice there is no fallback, automatic retry or `reassign`:
start again with another eligible pair. `--type` on a stage start must equal the stage's own type.
Read its current instruction source rather than guessing from a name. Native semantic
commands may pause for real decisions. The managed preset prevents duplicate chaining.
With `mode: revalidate`, retain the bound issue, feature path and existing branch.
Review and update existing artifacts in place; do not create another spec directory,
overwrite completed task history or require moving an advanced issue back to Backlog.
Scope still checks current approval, labels, prerequisites and requirement fingerprints;
a claim is not permission to bypass stale scope or unresolved human questions.
For a material choice during any stage, use `scripts/decisions.py --feature
specs/<bound-feature> ask --question ... --option ... --option ...` to post a
stable question on the bound GitHub issue. It posts the options as an unticked task list. Add
`--mode multiple` when several options may apply and `--recommended B` to mark
a suggested option (it is never pre-ticked). Do not request its answer in the IDE.
Pause the active claim with the question URL and token. On return, run
`decisions.py ... sync --project-field`, inspect all authorized answers and
conflicts, then apply the selected result to the actual artifacts. Record
that application with `decisions.py ... apply --id SDn --evidence <path>`.
A ticked box records no author; never tick one for the reviewer. Run
`decisions.py ... upgrade-questions` once to make questions from an earlier release
selectable. Edited answers reopen the decision; an applied artifact that changed must be
reviewed again. Reuse existing question IDs on retries. Never infer an
answer from the Project field or an agent recommendation.


Decision binding and publication: only a paused pre-Specify checkpoint may read on a
changed branch. Bound/later or active work uses the checkpoint branch. Active decision
commands require `SANDUQ_WORKFLOW_CLAIM_TOKEN` and `SANDUQ_WORKFLOW_SESSION_ID` from
the current claim. The dispatcher passes its verified token/session when completing a stage.
Marker semantics and canonical choices are protected by the recorded ledger; legacy
conversion changes presentation only and retains real reply/application evidence.
Pending decisions park mapped Backlog or Feature Specification. Answers return an owned
park to Feature Specification; advanced states remain protected. Both Decision and Status
writes are reread, and a durable pre-write intent recovers lost-response retries. The shared
Scope transport falls back to REST on GraphQL exhaustion and records the served transport.
