# Invoking the claimed command: delegation and decisions

The stage loop's step 4 in full: how to invoke the claimed command, route it
through delegation when enabled, and pause for a material decision.

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
