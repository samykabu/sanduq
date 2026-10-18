# Invoking the claimed command: delegation and decisions

Stage loop step 4: invoke the claimed command, route it through delegation when enabled, and
pause for a material decision.

## Invoking

Invoke the selected command in this host through its installed skill or command registration.
Read its current instruction source rather than guessing from a name. Native semantic commands
may pause for real decisions; the managed preset prevents duplicate chaining. With `mode:
revalidate`, keep the bound issue, feature path and branch, and update existing artifacts in
place: no new spec directory, no overwritten task history, no forced move back to Backlog.
Scope still checks approval, labels, prerequisites and requirement fingerprints; a claim never
bypasses stale scope or unresolved human questions.

## Delegation

When `delegation.enabled` is true, use the claim's `delegation` route: `delegate_dispatch.py
start --feature specs/<feature> --id stage:<stage> --claim-token <token>`, then
`delegate_dispatch.py collect --feature specs/<feature> --run-id <id>` until terminal,
following any `replacement` run ID. A successful delegate result is candidate evidence, not a
passed stage: inspect outputs and checks before the receipt. Failed, abandoned or unresolved
work keeps the claim active. An unreported actual model stays unverified. Disabled mode ignores
routing tags and uses the user's selected model.

A rejected model falls back to the next candidate automatically, as does a start that provably
created no run (or whose driver exited 5 with proof no agent launched). On
`DELEGATION_START_UNCERTAIN`, never start again: run `delegate_dispatch.py recover --feature
specs/<feature> --intent-id <id>`; collect a bound run, or on `found: false` close the intent
with `delegate_dispatch.py abandon --feature specs/<feature> --intent-id <id> --reason
"<why>"` and start again. On `DELEGATION_LEDGER_BUSY` or `DELEGATE_SKILL_INSTALL_BUSY`, retry;
a dead owner's lock on this host is recovered automatically, so never delete a lock whose named
process is running. An observation timeout is not a failed run.

To choose a candidate, add `--harness <codex|claude> --model <id>` to `start`, always together.
The pair must already be in the stage's resolved route; it selects, never adds, and each stage
keeps its own allowlist. An invalid or unavailable pair fails before any launch. After an
explicit choice there is no fallback, automatic retry or `reassign`. `--type` on a stage start
must equal the stage's own type.

## Opt-in lean execution

`lean_execution.enabled: true` (the default for the lite and standard tiers unless the policy
sets it false) makes one lifecycle coordinator keep claims, scheduling, integration, receipts
and publication; never create or dispatch another coordinator. Execute, Tasks-to-Issues, Ready
and PR claims return `execution_owner: coordinator` without a model route, as does an exact
`delegation.fixed_collection_commands.verify` match. Semantic stages keep their routes and
successful attempt checks. Without lean policy the legacy protocol applies.

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

Only `enabled` is required; bounds satisfy finalization < minimum <= maximum <= 28800 seconds.
`verification_plan`: see [verification-plan.md](verification-plan.md). `preflight_manifest`
selects deterministic checks for doctor and before Execute or later claims; findings block
execution. `scope_analysis` is the initial analysis path; without it the Scope claim prints
`<analysis.json>`, which must be replaced with the actual new analysis. `claim.environment`
carries the token and session for native commands and worker launches.

Every lean launch needs `--deliverable "<artifact and acceptance result>"`; a second attempt for
the same identity also `--correction-plan "<specific correction and check>"`; further attempts
`--diagnosis <project-relative JSON>` with concrete `cause`, `evidence` (an existing file) and
`change`. Admission is checked under the ledger lock, so another model or run ID cannot reset
the history. Lean launches try the selected candidate only and never escalate failed work
automatically; `reassign --reason "<specific correction>" [--diagnosis <JSON>]` keeps the prior
candidate. Failure categories (provider rejection, harness failure, timeout, task failure,
missing evidence, abandonment, unknown) stay distinct; a timeout while collecting is not a
failed task. Reserve `finalization_seconds` for an honest partial handoff listing changed
files, executed checks and remaining work; the worker writes it before the watchdog fires.

`workflow.py status --feature specs/<feature> --runs <run-root>` (repeat for worktrees) shows
elapsed time, latest event, next action and per-harness usage; a successful harness is never
silently task acceptance. `delegate_dispatch.py classify --feature specs/<feature> --run-id
<id> --attribution <JSON>` records the failure `domain` (product, test, environment, workflow,
owner-interruption or unknown), `actor`, `reason` and existing `evidence`.

## Decisions

For a material choice in any stage, run `scripts/decisions.py --feature specs/<bound-feature>
ask --question ... --option ... --option ...` to post a stable question on the bound issue as an
unticked task list (`--mode multiple` when several may apply, `--recommended B` to mark, never
tick, a suggestion). Never ask for the answer in the IDE. Pause the claim with the question URL
and token. On return run `decisions.py ... sync --project-field`, inspect authorized answers
and conflicts, apply the result to the artifacts, and record it with `decisions.py ... apply
--id SDn --evidence <path>`. Never tick a box for the reviewer or infer an answer from the
Project field or a recommendation. Edited answers reopen the decision. Reuse question IDs on
retries. `decisions.py ... upgrade-questions` makes earlier-release questions selectable.

Only a paused pre-Specify checkpoint may read on a changed branch; bound or active work uses the
checkpoint branch. Active decision commands need `SANDUQ_WORKFLOW_CLAIM_TOKEN` and
`SANDUQ_WORKFLOW_SESSION_ID` from the current claim. Pending decisions park the issue in mapped
Backlog or Feature Specification; answers return an owned park to Feature Specification and
advanced states stay protected. Decision and Status writes are reread, and a durable pre-write
intent recovers lost-response retries.
