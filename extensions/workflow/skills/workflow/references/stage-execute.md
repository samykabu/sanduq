# Stage reference: execute

## Required work and evidence

Read [execution-assign.md](execution-assign.md), then [execution-report.md](execution-report.md);
both providers (`speckit.implement`, `speckit.superspec.execute`) follow them. Fill available
capacity with tasks whose dependencies, files and resources allow concurrent work. Create the
progress report once before implementation, as [reporting.md](reporting.md) says for the mode;
no agent exists solely for it. Verify, commit and push each completed phase within existing
authorization. Routine phase transitions are automatic under `required-only`; explicit human
review markers stay gates. Keep task checkboxes and issue state current. With `phase-lazy`
task issues, publish each phase's issues at its start (execution-report.md).

## Lean mode

With `lean_execution.enabled: true`, the existing lifecycle coordinator owns Execute and the
following verification, documentation and publication work. Do not create the additional
orchestration agent described by the legacy protocol below. Assign bounded workers directly,
each with a concrete artifact and acceptance result; the coordinator keeps claims, integration
and receipts. See `references/delegation-and-decisions.md#opt-in-lean-execution`.

## Legacy protocol: execution ownership

The dispatcher owns the stage claim and lifecycle transitions. A dedicated orchestration agent
owns task assignments, integration and phase commits and pushes; it has no reporting duty.
Workers implement the assigned tasks and return evidence. Recover live work before scheduling
replacements, and never let two agents own the same writes or create competing orchestrators.
Never silently replace the required agents with work in the parent. Continue all authorized
phases automatically; post-merge verification is in `references/stage-pr.md`.

After either provider succeeds, native `complete` invokes the Memory handoff: honor
`memory_handoff`, its exit and returned actions ([memory-lifecycle.md](memory-lifecycle.md)).
Do not dispatch another prepare hook after native completion. With SuperSpec Execute under
`required-only` checkpoints, also follow [superspec-checkpoints.md](superspec-checkpoints.md).
