---
description: Sanduq managed lifecycle overlay
---

<!-- sanduq-workflow-managed:v1 -->
If `.specify/workflow.yml` is absent, continue with the upstream command unchanged.
Otherwise read `.specify/extensions/workflow/skills/workflow/SKILL.md` and the
checkpoint for the explicitly bound feature. If this invocation has no active
matching stage claim, enter the dispatcher (scope for a new issue, continue for
an existing feature) and STOP this outer invocation when it returns. Inside a
matching claim, execute the domain work below once, then return control to the
dispatcher. Never recursively enter the dispatcher from the claimed command.
The dispatcher alone chooses and calls the next stage. Keep mandatory safety and
binding guards. Disabled hooks stay disabled. Do not independently invoke another
task generator, executor, or PR hook. Use bounded batches. Only reliable measured context can trigger a context pause;
missing, estimated or stale usage must not stop automatic continuation.


Before executing a task, read
`.specify/extensions/workflow/skills/workflow/references/execution.md`.
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
