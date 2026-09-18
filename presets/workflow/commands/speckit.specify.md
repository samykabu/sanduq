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
task generator, executor, or PR hook. Check context before each bounded batch.

Pass the active run's exact feature path as SPECIFY_FEATURE_DIRECTORY. Do not
allocate a second feature. Preserve pending ambiguities in spec.md and route them
through the next Clarify stage, without invoking the upstream chat question loop.
For a `mode: revalidate` claim with an existing bound specification, review that
specification in place. Skip new-feature/branch creation and template overwrites;
preserve its plan, tasks and implementation. Run the Scope guard and binding checks
against the same issue. A matching managed claim permits an existing open feature
to retain its board position while being rechecked; it does not waive fresh scope.
After core Specify and Scope Bind, run `workflow.py bind --feature <path> --token
<active-token>` to accept the new branch only after scope-source.json matches the
same repository and issue. Then record the Specify receipt and return.

Continue the applicable upstream domain instructions below.
