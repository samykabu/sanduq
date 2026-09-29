# Stage reference: tasks

Loaded when `claim` returns `stage: tasks`.

## Required work and evidence

Exactly one generator: compatible enabled SuperSpec Tasks, else core Tasks. Keep
stable task IDs.

## Core Tasks provider (`speckit.tasks`)

When revalidating an existing tasks.md, reconcile only changed requirements. Keep
stable task IDs, completed checkboxes and native issue mappings for unchanged work.
Add new work and reopen genuinely invalidated tasks with a recorded reason. Do not
replace the existing task list with a fresh numbered template.

For material task breakdown or acceptance choices, use the workflow decision
adapter on the bound GitHub issue. Post options there, pause the claimed stage,
and resume from authorized issue answers. Do not ask in the VS Code conversation.
Record the applied decision and tasks.md as evidence before returning a passed
Tasks receipt.

## SuperSpec Tasks provider (`speckit.superspec.tasks`)

When execution.checkpoints is required-only, project policy pre-authorizes
routine phase checkpoints and backend choice. Record the selected execution mode
and continue automatically. Explicit HUMAN-REVIEW tasks, unresolved requirements,
security decisions and deployment approvals still pause. Execute small batches
and hand off only at a reliably measured context limit. Without reliable telemetry,
continue automatically; never stop on estimates or reset a measured budget per task.

When revalidating an existing tasks.md, reconcile only changed requirements. Keep
stable task IDs, completed checkboxes, execution markers and native issue mappings
for unchanged work. Add or reopen genuinely changed work with a recorded reason;
do not renumber the feature or reset all progress.

For material task or acceptance choices, post a stable question through the
workflow decision adapter on the bound GitHub issue, then pause. Resume from an
authorized issue answer, apply it to tasks.md, and record the application
evidence. Do not solicit a local VS Code answer or treat an agent recommendation
as approval.
