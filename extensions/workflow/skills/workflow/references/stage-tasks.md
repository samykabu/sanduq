# Stage reference: tasks

## Required work and evidence

Exactly one generator: a compatible enabled SuperSpec Tasks, otherwise core Tasks. Keep stable
task IDs. When revalidating an existing tasks.md, reconcile only changed requirements: keep task
IDs, completed checkboxes, execution markers and native issue mappings for unchanged work, add
new work, and reopen genuinely invalidated tasks with a recorded reason. Never replace the list
with a freshly numbered template.

A material task breakdown or acceptance choice goes to the bound GitHub issue through the
workflow decision adapter (`decisions.py`); pause the claim and resume from an authorized issue
answer, never a local chat answer or an agent recommendation. Record the applied decision and
tasks.md as evidence before a passed receipt.

## SuperSpec Tasks provider (`speckit.superspec.tasks`)

Follow [superspec-checkpoints.md](superspec-checkpoints.md).
