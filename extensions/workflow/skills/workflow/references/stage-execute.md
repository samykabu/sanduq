# Stage reference: execute

Loaded when `claim` returns `stage: execute`.

## Required work and evidence

Read `references/execution-assign.md`, then `references/execution-report.md`.
Create a dedicated orchestration agent and delegate implementation to workers.
Fill available capacity with tasks whose dependencies, files and resources permit
concurrent work. Open the HTML TODO report before implementation and keep it
current. Verify, commit and push each completed phase within existing
authorization. Routine phase transitions are automatic under `required-only`;
explicit human review markers remain gates. Keep task checkboxes and issue state
current.

## Execution ownership and live progress

Both managed executors use the same execution protocol, split into
`references/execution-assign.md` and `references/execution-report.md`. The
dispatcher owns the stage claim and lifecycle transitions. A dedicated
orchestration agent owns task assignments, integration, report writes and phase
commits/pushes. Worker agents implement the assigned tasks and return evidence.
Record the real agent handles and ownership in the feature handoff. Recover live
work before scheduling replacements; never let two agents own the same writes.

Keep the orchestration agent available after Execute so it can update the report
and schedule fixes during verification, review, documentation and PR checks. The
dispatcher sends it each stage outcome and remains responsible for honest receipts.
Continue all authorized phases automatically. Existing PR and merge authorization
carries forward, while required human decisions and branch protections still apply.
If merge is authorized, watch the exact final PR head, repair failed checks, rerun
affected evidence and merge when required checks and approvals pass. Update the
report from the actual merge result and complete post-merge verification in
`references/stage-pr.md`.

## Core Implement provider (`speckit.implement`)

Before executing a task, read
`.specify/extensions/workflow/skills/workflow/references/stage-execute.md`.
Create a dedicated orchestration agent and have it delegate implementation tasks
to worker subagents. The dispatcher retains the stage claim and lifecycle transitions;
the orchestration agent owns scheduling, integration, report updates and phase commits.
Reuse the recorded orchestration agent when resuming a live execution; do not create
competing orchestrators. Run every ready task that can safely fit the host capacity,
with explicit dependency, file and resource ownership. A single worker handles a
serial task. Never silently replace the required agents with work in the parent.

Generate and open the HTML TODO report before the first implementation task. Keep
it current through every phase, verification, review, CI and authorized PR merge.
Continue through all implementation phases, verify each phase, then commit and push
its completed changes through the orchestration agent. Return the execution result
to the dispatcher for the remaining lifecycle stages. Existing authorization carries
forward; unresolved human decisions and actual permission limits remain gates.
These scheduling and reporting rules apply to the upstream domain instructions below.

## SuperSpec Execute provider (`speckit.superspec.execute`)

When execution.checkpoints is required-only, project policy pre-authorizes
routine phase checkpoints and backend choice. Record the selected execution mode
and continue automatically. This overrides upstream instructions to pause for
approval at every routine phase; do not ask again for approvals already recorded.
Explicit HUMAN-REVIEW tasks, unresolved requirements,
security decisions and deployment approvals still pause. Execute small batches
and hand off only at a reliably measured context limit. Without reliable telemetry,
continue automatically; never stop on estimates or reset a measured budget per task.

It otherwise follows the same Core Implement provider instructions above (read
`references/execution-assign.md`/`references/execution-report.md`, delegate to
worker subagents, keep the HTML TODO report current, and return the execution
result to the dispatcher).
