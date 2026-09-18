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

This is the actual core Tasks-to-Issues invocation with a managed adapter.
Keep prerequisite and repository validation, but replace the upstream global
T001-title deduplication and issue-creation loop with:
1. Read tasks.md and its dependencies. Write a JSON object mapping each task ID to
   prerequisite task IDs (empty list for independent tasks); validate no cycles.
2. Run `.specify/extensions/workflow/scripts/task_issues.py --help`, then its
   dry run with the explicit feature and issue. Inspect the exact target changes.
3. Apply within the user's issue-work authorization. The adapter uses repository,
   parent issue, feature and task ID, and verifies native GitHub sub-issue links.
4. Include its result and journal as evidence. Never also execute the core's old
   MCP creation loop or Project's task creator. A missing adapter is a blocker.

Continue the applicable upstream domain instructions below.
