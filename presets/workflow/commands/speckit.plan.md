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


For a `mode: revalidate` claim with an existing plan, update only what changed.
Preserve established decisions and task history, and do not blindly copy a new plan
template over reviewed content. Keep the clarification gate: a managed claim can
recheck an open feature already in progress only with resolved clarification evidence.

Continue the applicable upstream domain instructions below.
