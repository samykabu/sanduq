---
description: Respect the managed workflow execution owner
---

<!-- sanduq-workflow-legacy-guard:v1 -->
If `.specify/workflow.yml` exists, the Sanduq dispatcher owns lifecycle transitions.
Run workflow doctor first. An executing or blocked legacy handoff must be inspected
and reconciled from actual evidence; never change it to complete merely to pass a
guard. Do not start a second executor or write another legacy handoff. For execute,
invoke `speckit.workflow.continue` for the explicitly bound feature and return.
For guard/handoff, report the managed owner and return without mutating legacy state.
STOP this invocation before the upstream legacy instructions below. Unmanaged
projects retain those upstream instructions unchanged.
