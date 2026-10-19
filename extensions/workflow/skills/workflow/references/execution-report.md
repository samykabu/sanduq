# Implementation orchestration: report

The second half of the execution protocol ([`execution-assign.md`](execution-assign.md) is the
first): finishing phases and delivery. Reporting calls are the claim's reporting part
([`reporting.md`](reporting.md)); no agent is spawned, retained, messaged or polled solely
for reporting.

## Update the report and finish phases

The current coordinator is the sole writer of the progress report and makes only the calls the
reporting part names.

Use `pending`, `running`, `done` or `blocked` for task status. Mark task checkboxes
done only after reviewing their implementation and required checks. Preserve
failed attempts alongside subsequent successful evidence.

Sync native task issues once per phase, not once per task: the dispatcher owns
this call and runs `task_issues.py --sync-states --feature ... --parent ...
--apply --summary` once the phase's tasks are committed and its selected
documentation tasks are done (`sync_states()` already walks every task in
`tasks.md`). Never infer human-review completion from generated evidence: a
human-review task's issue closes only on the human's own signal.

With `issue_sync.taskstoissues: phase-lazy`, publish each phase's task issues at its start:
`task_issues.py --feature ... --parent ... --phase "<Phase heading>"` dry run, then the same with
`--apply --summary`. While a later phase has no issues yet, `--sync-states` refuses with
`UNPUBLISHED_TASK`; then skip the boundary sync and run it once every phase is published, before
Ready.

Prefer `--summary` (a one-line result with counts) for routine protocol calls
to `task_issues.py`, `assure_state.py`, `manual_state.py` and
`project-sync`: it prints `ok` or `error` plus counts, or `skipped
reason=<why>` when the call had nothing to do. Reserve `--json` for a call
whose result must be parsed programmatically.

At each phase boundary run the required checks, inspect the combined diff, and have
the orchestration agent commit and push the phase's changes to the bound branch,
staging only the intended paths and keeping unrelated user changes. Record the
commit SHA and push result; a failed push leaves the phase unpublished until a retry
succeeds. Keep the report directory out of receipt inputs and source inventories.
Existing commit and push authorization carries forward unless the user restricted
it; record the limitation then. Human review tasks, unresolved requirements,
security decisions and deployment approvals remain real gates; record blockers and
continue independent authorized work.

## Report only on state change

A wake-up that carries no new information produces no message beyond the
minimum the harness requires: a background task still running, a poll with an
unchanged status, or a repeat of the same "still running" note are not state
changes. Report when a task is accepted, a commit is pushed, a blocker appears
or a decision is needed, and stop there; do not re-narrate the same pending
state after every notification.

## Structured worker results

A worker returns its result in exactly this ten-line form; the orchestration
agent forwards these lines, or a pointer to them, never the worker's full
prose, to the dispatcher and to the report:

```text
Task: <T### and title>
Status: done | blocked | partial
Files touched: <paths, or "none">
Tests: <RED-to-GREEN summary, e.g. "12 passed, 0 failed (dotnet test, persistence-integration)">
Evidence: <path(s) under specs/<feature>/evidence/>
Diff: <+/- line counts per file, uncommitted>
Consumers checked: <which consumers were checked, or "n/a" with why>
Tokens: <fresh/cached/output if the worker's harness reports them, else "unlogged">
Blockers: <none, or the exact blocking condition>
Next: <what the orchestrator should do, or "none">
```

## Read verification summaries before raw output

When a task's evidence is a verification run, read its summary first: run ID,
per-lane pass/fail counts and artifact paths, from whatever the project's
verification tooling prints. Open a raw reporter file (Playwright, vitest,
dotnet test JSON) only for a lane that failed, and only that failing test's
section. A fully green run is read from its summary alone; the raw artifacts
stay on disk either way, for anyone who needs them later.

## Consumers checklist after a fix

Before returning a result for any fix, a review finding, a mid-execute defect,
a rename or a contract change, the worker checks each of the following and
records which applied in the result's "Consumers checked" line; a consumer is
skipped only when it verifiably does not apply, never by default:

- End-to-end/integration specs that reference the changed name, route or contract.
- The lane registry (titles, counts) if a test's identity or count changed.
- QA capture specs and their generated sample output.
- Manual/User-Manual pages and sample copies describing the changed behavior.
- Contract docs, through the project's pending-artifact-updates convention where one exists.
- PR image pins, when a changed screenshot is embedded in the PR body.

## Continue through delivery

The orchestration agent returns the Execute evidence to the dispatcher. It stays
available to schedule fixes while the dispatcher runs Verify, Review, selected
documentation and Ready. Never complete a claim or call
the next lifecycle stage from a worker or from an executor hook.

When the user's request authorizes a PR, the dispatcher continues through Finalize
automatically once its prerequisites pass. When merge is also authorized, monitor
checks and reviews on the exact final head, delegate fixes, revalidate affected
evidence, and merge through the normal protected path only when required checks
are green and approvals are satisfied. Do not bypass branch protections. Without
merge authorization, record the actual PR state and request only the missing
authorization after the PR is concrete and reviewable. The reporting part names the
calls that record the PR state.

Set `merged` only after reading GitHub's actual merged state and merge SHA. Record
the final check results and post-merge verification in the handoff and report.
PR creation, merge, deployment and live acceptance are separate facts. Report
through all work in the user's authorized scope as `reporting.md` says; a progress
page does not replace test receipts, review evidence or the workflow checkpoint.
