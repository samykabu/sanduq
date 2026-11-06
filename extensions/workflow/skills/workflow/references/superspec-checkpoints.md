# SuperSpec checkpoints under required-only

Applies to the SuperSpec Brainstorm, Tasks, Execute and Review providers. When
`execution.checkpoints` is `required-only`, project policy pre-authorizes routine phase
checkpoints and backend choice: record the selected execution mode and continue automatically,
overriding upstream instructions to pause for approval at every routine phase, and do not ask
again for approvals already recorded. Explicit HUMAN-REVIEW tasks, unresolved requirements,
security decisions and deployment approvals still pause. Execute small batches and hand off
only at a reliably measured context limit. Without reliable telemetry, continue automatically;
never stop on estimates or reset a measured budget per task.
