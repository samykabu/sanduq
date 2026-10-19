# Stage reference: execute

## Required work and evidence

The Execute claim's `reference_text` is this file followed by the protocol for the claim's
mode, which `execute_protocol` lists: [execution-assign.md](execution-assign.md),
[execution-report.md](execution-report.md), then from `references/execute/` the lean
coordinator or the dedicated orchestration agent, the delegated workers when delegation is
enabled, and the reporting calls for the claim's `reporting` mode ([reporting.md](reporting.md)
for `projection` and `refresh`, the legacy reporter for `legacy`). Read that text; do not open
the separate files. A later Execute claim whose protocol is unchanged prints
`execute_protocol.printed: false` and leaves it out; read the listed files only if your context
was reset (`claim --verbose` prints it again). Both providers (`speckit.implement`, `speckit.superspec.execute`) follow it.

Fill available capacity with tasks whose dependencies, files and resources allow concurrent
work. Create the progress report once before implementation, as the reporting part says; no
agent exists solely for it. Verify, commit and push each completed phase within existing
authorization. Routine phase transitions are automatic under `required-only`; explicit human
review markers stay gates. Keep task checkboxes and issue state current. With `phase-lazy` task
issues, publish each phase's issues at its start (execution-report.md). Recover live work before
scheduling replacements, and never let two agents own the same writes or create competing
orchestrators.

After either provider succeeds, native `complete` invokes the Memory handoff: honor
`memory_handoff`, its exit and returned actions ([memory-lifecycle.md](memory-lifecycle.md)).
Do not dispatch another prepare hook after native completion. With SuperSpec Execute under
`required-only` checkpoints, also follow [superspec-checkpoints.md](superspec-checkpoints.md).
